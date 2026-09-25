#!/usr/bin/env python3
"""Run the bounded Phase 1K.28 old-native B0 diagnostic.

B0 keeps the K27 direct-force and payload instrumentation, removes the K25 G2
meshPhi canonicalization from the isolated adapter source, and uses the
repository's old-mesh native displacementLaplacian case. It never modifies the
authoritative case or any production binary.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from phase1k24_fluid_state_replay import DSTAR, ROOT, require, sha


RUN_ID = "run-20260925T113000Z-fc0f94d-b0"
RUN = ROOT / "evidence/phase1k28_old_native_reference" / RUN_ID
SOURCE_CASE = ROOT / "cases/hh06_single_slice"
K27_SOURCE = ROOT / "evidence/phase1k27_force_pipeline/run-20260925T090832Z-e0da50c/adapter-source"
K26_STRUCTURE = ROOT / "evidence/phase1k26_earliest_divergence/run-20260925T-phase1k26-4182ac9/selected_causal_test_G2/fixed_structure.py"
SOLVER = Path("/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/bin/pimpleFoamPhase1K26Diag")
EXPECTED_CHECKPOINT = "ed3e8e2d5cb49e5d1dd7ebe3b2a91ea586494545"
EXPECTED_BRANCH = "diagnostic/phase1k28-old-mesh-native-reference-v1"
EXPECTED_DT = 0.0002
EXPECTED_DSTAR = [1.0633832164606064e-07, 9.530777190012017e-08]

B0_PATCH = """diff --git a/Adapter.C b/Adapter.C
--- a/Adapter.C
+++ b/Adapter.C
@@ -6,1 +6,0 @@
-#include \"Phase1K25Group2MeshPhiCanonicalization.H\"
@@ -1184,4 +1184,0 @@
-        // Phase 1K.25 Group 2 diagnostic only: canonicalize the
-        // post-rollback mesh-motion flux values to the zero-flux S0 proxy.
-        // This does not alter fvMesh moving/changing or V/V0/V00 state.
-        phase1k25g2::canonicalizeMeshPhiAfterReload(mesh_);
diff --git a/Phase1K25Group2MeshPhiCanonicalization.H b/Phase1K25Group2MeshPhiCanonicalization.H
deleted file mode 100644
--- a/Phase1K25Group2MeshPhiCanonicalization.H
+++ /dev/null
@@ -1,43 +0,0 @@
-#ifndef PHASE1K25_GROUP2_MESHPHI_CANONICALIZATION_H
-#define PHASE1K25_GROUP2_MESHPHI_CANONICALIZATION_H
-
-#include \"fvMesh.H\"
-#include \"dimensionedTypes.H\"
-#include \"IOstreams.H\"
-
-namespace phase1k25g2
-{
-inline void canonicalizeMeshPhiAfterReload(const Foam::fvMesh& mesh)
-{
-    if (!mesh.moving())
-    {
-        FatalErrorInFunction
-            << \"GROUP2 expected an existing moving mesh after rollback\"
-            << Foam::exit(Foam::FatalError);
-    }
-
-    if (!mesh.foundObject<Foam::surfaceScalarField>(\"meshPhi\"))
-    {
-        FatalErrorInFunction
-            << \"GROUP2 expected meshPhi to exist after rollback\"
-            << Foam::exit(Foam::FatalError);
-    }
-
-    Foam::surfaceScalarField& meshPhi =
-        const_cast<Foam::fvMesh&>(mesh).lookupObjectRef<Foam::surfaceScalarField>(\"meshPhi\");
-    meshPhi = Foam::dimensionedScalar(Foam::dimVolume/Foam::dimTime, 0);
-    if (meshPhi.nOldTimes() >= 1)
-    {
-        meshPhi.oldTime() = Foam::dimensionedScalar(Foam::dimVolume/Foam::dimTime, 0);
-    }
-    if (meshPhi.nOldTimes() >= 2)
-    {
-        meshPhi.oldTime().oldTime() = Foam::dimensionedScalar(Foam::dimVolume/Foam::dimTime, 0);
-    }
-
-    Foam::Info << \"PHASE1K25_GROUP2_CANONICALIZED meshPhi nOldTimes=\"
-               << meshPhi.nOldTimes() << Foam::endl;
-}
-}
-
-#endif
"""


def run_text(command: list[str], cwd: Path | None = None, timeout: int = 60) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    require(result.returncode == 0, f"command failed: {' '.join(command)}\n{result.stderr}")
    return result.stdout.strip()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    excluded = {".git", "lnInclude", "linux64GccDPInt32Opt"}
    files = []
    for path in root.rglob("*"):
        if path.is_file() and not any(part in excluded for part in path.relative_to(root).parts):
            files.append((path.relative_to(root).as_posix(), path))
    for name, path in sorted(files):
        digest.update(name.encode() + b"\0" + bytes.fromhex(sha(path)))
    return digest.hexdigest()


def copy_old_case(case: Path) -> None:
    require(SOURCE_CASE.is_dir(), f"old-native repository case missing: {SOURCE_CASE}")
    require(not case.exists(), f"refusing to overwrite existing case scratch: {case}")
    case.mkdir(parents=True)
    for name in ("30", "constant", "system"):
        shutil.copytree(SOURCE_CASE / name, case / name)
    shutil.copy2(SOURCE_CASE / "precice-config.xml", case / "precice-config.xml")
    shutil.copy2(SOURCE_CASE / "contract.json", case / "contract.json")
    shutil.copy2(K26_STRUCTURE, RUN / "fixed_structure.py")


def prepare_case(case: Path, adapter: Path) -> None:
    dynamic = (case / "constant/dynamicMeshDict").read_text(encoding="utf-8")
    require("displacementLaplacian" in dynamic, "old-native motion solver is not displacementLaplacian")
    require("RBF" not in dynamic and "RBFMesh" not in dynamic, "old-native case unexpectedly contains RBF motion")

    xml_path = case / "precice-config.xml"
    xml = xml_path.read_text(encoding="utf-8")
    require('<max-time-windows value="25"/>' in xml, "unexpected source max-time-windows")
    require('<max-iterations value="20"/>' in xml, "unexpected source max-iterations")
    xml = xml.replace('<max-time-windows value="25"/>', '<max-time-windows value="1"/>')
    xml = xml.replace('<max-iterations value="20"/>', '<max-iterations value="4"/>')
    xml = re.sub(r'exchange-directory="[^"]+"', f'exchange-directory="{RUN / "precice-sockets"}"', xml, count=1)
    xml_path.write_text(xml, encoding="utf-8")

    control_path = case / "system/controlDict"
    control = control_path.read_text(encoding="utf-8")
    require("libpreciceAdapterFunctionObject.so" in control, "native controlDict adapter entry missing")
    control_path.write_text(control.replace("libpreciceAdapterFunctionObject.so", str(adapter)), encoding="utf-8")

    contract_path = case / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract.setdefault("execution_authorization", {})["max_windows"] = 1
    contract.setdefault("coupling", {})["max_iterations"] = 4
    contract["coupling"]["accepted_window_limit"] = 1
    contract["coupling"]["duration_s"] = EXPECTED_DT
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")


def build_adapter() -> tuple[Path, Path]:
    require(K27_SOURCE.is_dir(), f"K27 force-instrumented source missing: {K27_SOURCE}")
    source = RUN / "adapter-source"
    shutil.copytree(K27_SOURCE, source, ignore=shutil.ignore_patterns(".git", "lnInclude", "linux64GccDPInt32Opt"))
    patch_path = RUN / "source_diff.patch"
    patch_path.write_text(B0_PATCH, encoding="utf-8")
    result = subprocess.run(["patch", "-p1", "--forward", "--batch"], cwd=source,
                            input=B0_PATCH, text=True, capture_output=True)
    require(result.returncode == 0, f"B0 source patch failed: {result.stdout}\n{result.stderr}")
    require("Phase1K25Group2MeshPhiCanonicalization.H" not in (source / "Adapter.C").read_text(),
            "B0 source still includes G2 header")
    require("canonicalizeMeshPhiAfterReload" not in (source / "Adapter.C").read_text(),
            "B0 source still calls G2 canonicalization")
    make_files = source / "Make/files"
    make_text = make_files.read_text(encoding="utf-8")
    make_files.write_text(make_text.replace("libpreciceAdapterPhase1K27ForceDiag", "libpreciceAdapterPhase1K28OldNativeB0Diag"), encoding="utf-8")
    build = RUN / "adapter-build"
    build.mkdir()
    env = os.environ.copy()
    command = "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; export ADAPTER_TARGET_DIR=\"$1\"; cd \"$2\"; wmake libso ."
    result = subprocess.run(["/bin/bash", "-c", command, "phase1k28-build", str(build), str(source)],
                            capture_output=True, text=True, env=env, timeout=900)
    (build / "build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    require(result.returncode == 0, f"B0 adapter build failed; see {build / 'build.log'}")
    adapter = build / "libpreciceAdapterPhase1K28OldNativeB0Diag.so"
    require(adapter.is_file(), f"B0 adapter binary missing: {adapter}")
    return adapter, patch_path


def record_identity(case: Path, adapter: Path, patch_path: Path) -> None:
    required = [
        "30/uniform/time", "30/U", "30/p", "30/k", "30/omega", "30/nut",
        "30/pointDisplacement", "30/cellDisplacement", "30/phi", "30/phi_0",
        "30/U_0", "30/k_0", "30/omega_0", "30/yPlus",
        "constant/polyMesh/points", "constant/polyMesh/faces", "constant/polyMesh/owner",
        "constant/polyMesh/neighbour", "constant/polyMesh/boundary", "constant/polyMesh/cellZones",
        "constant/polyMesh/faceZones", "constant/polyMesh/pointZones",
    ]
    config = ["constant/dynamicMeshDict", "constant/momentumTransport", "constant/physicalProperties",
              "system/fvSchemes", "system/fvSolution", "system/controlDict", "system/preciceDict",
              "precice-config.xml", "contract.json"]
    for rel in required + config:
        require((case / rel).is_file(), f"missing case identity file: {rel}")
    time_text = (case / "30/uniform/time").read_text(encoding="utf-8")
    require(re.search(r"^\s*value\s+30\s*;", time_text, re.MULTILINE), "restart is not exactly 30 s")
    identity = {
        "schema": "phase1k28_old_native_b0_runtime_identity_v1",
        "run_id": RUN_ID,
        "git_head": run_text(["git", "rev-parse", "HEAD"], ROOT),
        "git_branch": run_text(["git", "branch", "--show-current"], ROOT),
        "git_status_before_runtime": run_text(["git", "status", "--porcelain=v1"], ROOT).splitlines(),
        "restart_source": str(SOURCE_CASE),
        "restart_global_time_s": 30.0,
        "dt_s": EXPECTED_DT,
        "d_star_m": EXPECTED_DSTAR,
        "motion_solver": "displacementLaplacian",
        "rbf_used": False,
        "g2_meshphi_canonicalization": False,
        "adapter_path": str(adapter),
        "adapter_sha256": sha(adapter),
        "adapter_build_id": run_text(["readelf", "-n", str(adapter)], ROOT).split("Build ID:", 1)[1].splitlines()[0].strip(),
        "adapter_source_tree_sha256": tree_sha256(RUN / "adapter-source"),
        "source_diff_patch": str(patch_path),
        "source_diff_patch_sha256": sha(patch_path),
        "diagnostic_solver": str(SOLVER),
        "diagnostic_solver_sha256": sha(SOLVER),
        "openfoam_version": "Foundation OpenFOAM 10",
        "precice_runtime_version": "3.4.1",
        "precice_runtime_path": "/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1",
        "precice_runtime_sha256": sha(Path("/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1")),
        "python_executable": "/usr/bin/python3.10",
        "pyprecice_metadata_version": "3.4.0",
        "restart_field_hashes": {rel: sha(case / rel) for rel in required},
        "configuration_hashes": {rel: sha(case / rel) for rel in config},
        "experimental_only": True,
        "qualified_historical_adapter_used": False,
        "worker_process_started": False,
    }
    (RUN / "runtime_identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    (RUN / "restart_identity.json").write_text(json.dumps({
        "source_case": str(SOURCE_CASE), "global_time_s": 30.0,
        "field_hashes": identity["restart_field_hashes"],
        "mesh_hashes": {rel: identity["restart_field_hashes"][rel] for rel in required if "polyMesh" in rel},
        "mapFields_used": False,
        "motion_solver": "displacementLaplacian",
    }, indent=2) + "\n", encoding="utf-8")


def validate(case: Path) -> None:
    result = subprocess.run(["precice-config-validate", str(case / "precice-config.xml")],
                            capture_output=True, text=True, timeout=60)
    (RUN / "precice_config_validate.stdout").write_text(result.stdout, encoding="utf-8")
    (RUN / "precice_config_validate.stderr").write_text(result.stderr, encoding="utf-8")
    require(result.returncode == 0, "preCICE configuration validation failed")


def loaded_libraries(pid: int) -> set[str]:
    maps = Path(f"/proc/{pid}/maps")
    if not maps.is_file():
        return set()
    return {line.split()[-1].removesuffix(" (deleted)") for line in maps.read_text(errors="replace").splitlines()
            if line.split() and any(x in line for x in ("libpreciceAdapter", "libRBFMeshMotionSolver", "libprecice.so"))}


def launch(case: Path) -> dict:
    (RUN / "precice-sockets").mkdir()
    for name in ("diagnostics", "rbf_diagnostics", "stages"):
        (RUN / name).mkdir()
    env = os.environ.copy()
    env.update({
        "PYTHONUNBUFFERED": "1",
        "PHASE1K24_DIAG_DIR": str(RUN / "diagnostics"),
        "PHASE1K18_DIAG_DIR": str(RUN / "rbf_diagnostics"),
        "PHASE1K26_STAGE_DIR": str(RUN / "stages"),
        "PHASE1K27_DIRECT_FORCE_TRACE": str(RUN / "direct_force_trace.jsonl"),
        "PHASE1K27_ADAPTER_PREWRITE_TRACE": str(RUN / "adapter_prewrite_force.jsonl"),
        "PHASE1K27_FLUID_INPUT_TRACE": str(RUN / "fluid_input_trace.jsonl"),
    })
    fluid = ["/bin/bash", "-c", "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; cd \"$1\"; exec \"$2\" -case .", "phase1k28-fluid", str(case), str(SOLVER)]
    structure = ["/usr/bin/python3.10", str(RUN / "fixed_structure.py"), str(case / "precice-config.xml"), str(RUN / "fixed_structure_result.json"), str(DSTAR[0]), str(DSTAR[1])]
    processes = {}
    handles = []
    observed = {"fluid": set(), "structure": set()}
    reason = None
    started = time.monotonic()
    try:
        for role, command in (("fluid", fluid), ("structure", structure)):
            out = (RUN / f"{role}.stdout").open("x")
            err = (RUN / f"{role}.stderr").open("x")
            handles.extend((out, err))
            processes[role] = subprocess.Popen(command, cwd=case, env=env, stdout=out, stderr=err, start_new_session=True)
        deadline = started + 900
        while any(p.poll() is None for p in processes.values()):
            for role, process in processes.items():
                observed[role].update(loaded_libraries(process.pid))
            failed = [role for role, process in processes.items() if process.poll() not in (None, 0)]
            if failed:
                reason = "participant exited nonzero: " + ",".join(failed)
                break
            if time.monotonic() > deadline:
                reason = "900-second hard timeout"
                break
            time.sleep(0.2)
        if reason:
            for process in processes.values():
                if process.poll() is None:
                    process.terminate()
    finally:
        for process in processes.values():
            process.wait(timeout=30)
        for handle in handles:
            handle.close()
    cleanup = {
        "fluid_command": fluid, "structure_command": structure,
        "pids": {role: process.pid for role, process in processes.items()},
        "exit_codes": {role: process.returncode for role, process in processes.items()},
        "loaded_libraries_by_role": {role: sorted(values) for role, values in observed.items()},
        "stop_reason": reason, "wall_duration_s": time.monotonic() - started,
        "working_directory": str(case), "worker_process": "NOT_STARTED; fixed-displacement diagnostic participant",
        "socket_entries_after_shutdown": sorted(p.name for p in (RUN / "precice-sockets").iterdir()),
    }
    (RUN / "process_cleanup.json").write_text(json.dumps(cleanup, indent=2) + "\n", encoding="utf-8")
    return cleanup


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"preflight", "run"}:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} preflight|run")
    mode = sys.argv[1]
    require(run_text(["git", "rev-parse", "HEAD^"], ROOT) == EXPECTED_CHECKPOINT,
            "K28 runner is not directly based on the frozen audit checkpoint")
    require(run_text(["git", "branch", "--show-current"], ROOT) == EXPECTED_BRANCH, "K28 branch mismatch")
    require(SOLVER.is_file(), f"diagnostic solver missing: {SOLVER}")
    require(sha(SOLVER) == "e895e5f1788146da2205e4c8bb0b959f99f66e426c92dc7233d7ac303fd91e96", "solver SHA mismatch")
    require(sha(Path("/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1")) == "b20729622d2dbbafdea3d6ead0480ec66be98cb947db3500cc3c27ed4e3039c7", "preCICE SHA mismatch")
    if mode == "preflight":
        require(not RUN.exists(), f"refusing to overwrite existing run: {RUN}")
        RUN.mkdir(parents=True)
        case = RUN / "prepared/case"
        case.parent.mkdir(parents=True, exist_ok=True)
        adapter, patch_path = build_adapter()
        copy_old_case(case)
        prepare_case(case, adapter)
        record_identity(case, adapter, patch_path)
        shutil.copy2(SOURCE_CASE / "README.md", RUN / "old_native_case_readme.md")
        validate(case)
        (RUN / "preflight_status.json").write_text(json.dumps({
            "status": "PASS_PREFLIGHT_ONLY", "b0": True, "g2": False,
            "runtime_started": False, "physical_windows": 0,
        }, indent=2) + "\n")
        return 0

    require(RUN.is_dir(), f"preflight run directory missing: {RUN}")
    status_path = RUN / "preflight_status.json"
    require(status_path.is_file(), "preflight status missing")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    require(status.get("status") == "PASS_PREFLIGHT_ONLY" and status.get("runtime_started") is False,
            "preflight gate is not PASS_PREFLIGHT_ONLY")
    case = RUN / "prepared/case"
    adapter = RUN / "adapter-build/libpreciceAdapterPhase1K28OldNativeB0Diag.so"
    require(case.is_dir() and adapter.is_file(), "preflight scratch case or B0 adapter is missing")
    require(not (RUN / "process_cleanup.json").exists(), "refusing to overwrite prior runtime cleanup")
    validate(case)
    cleanup = launch(case)
    require(cleanup["stop_reason"] is None, f"runtime stopped: {cleanup['stop_reason']}")
    require(cleanup["exit_codes"] == {"fluid": 0, "structure": 0}, f"nonzero participant exits: {cleanup['exit_codes']}")
    require(any("libpreciceAdapterPhase1K28OldNativeB0Diag.so" in x for x in cleanup["loaded_libraries_by_role"]["fluid"]), "B0 adapter was not loaded")
    require(not any("libRBFMeshMotionSolver" in x for x in cleanup["loaded_libraries_by_role"]["fluid"]), "RBF library unexpectedly loaded")
    for name, source in (("precice_iterations.log", "precice-Fluid_0000-iterations.log"), ("precice_convergence.log", "precice-Fluid_0000-convergence.log")):
        path = case / source
        require(path.is_file(), f"missing runtime log: {path}")
        shutil.copy2(path, RUN / name)
    result = json.loads((RUN / "fixed_structure_result.json").read_text())
    attempts = [row for row in result.get("records", []) if row.get("stage") == "attempt"]
    require(len(attempts) == 4, f"expected four diagnostic attempts, got {len(attempts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
