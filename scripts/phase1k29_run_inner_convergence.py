#!/usr/bin/env python3
"""Bounded Phase 1K.29 A/B inner-convergence diagnostic.

This runner creates only ignored scratch cases under the K29 evidence tree.
The production case, adapter, mesh, and restart are never modified.
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


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/phase1k29_cfd_inner_convergence"
RUN_ID = "run-20260925T214500Z-9747b00"
RUN = EVIDENCE / RUN_ID
SOURCE_CASE = ROOT / "cases/hh06_single_slice"
K26_SOURCE = ROOT / "evidence/phase1k26_earliest_divergence/source/pimpleFoam"
K26_STRUCTURE = ROOT / "evidence/phase1k26_earliest_divergence/run-20260925T-phase1k26-4182ac9/selected_causal_test_G2/fixed_structure.py"
K28_RUN = ROOT / "evidence/phase1k28_old_native_reference/run-20260925T113000Z-fc0f94d-b1-g2b"
ADAPTER = K28_RUN / "adapter-build/libpreciceAdapterPhase1K28OldNativeB1G2Diag.so"
EXPECTED_HEAD = "9747b00884e9a0f7f74160520c17353e2d1f7518"
EXPECTED_ADAPTER_SHA = "0edcfae77d51d8a57a354a1b745c77f6c15108bf532be0d4893394e80a2d785d"
EXPECTED_SOLVER_BASE_SHA = "e895e5f1788146da2205e4c8bb0b959f99f66e426c92dc7233d7ac303fd91e96"
DSTAR = [1.0633832164606064e-07, 9.530777190012017e-08]
DT = 0.0002


def fail(message: str) -> None:
    raise SystemExit("PHASE1K29_BLOCKED: " + message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_text(command: list[str], cwd: Path = ROOT) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=120)
    require(result.returncode == 0, f"command failed: {' '.join(command)}\n{result.stderr}")
    return result.stdout.strip()


def copy_case(target: Path) -> None:
    require(not target.exists(), f"refusing to overwrite scratch case {target}")
    target.mkdir(parents=True)
    for name in ("30", "constant", "system"):
        shutil.copytree(SOURCE_CASE / name, target / name)
    shutil.copy2(SOURCE_CASE / "precice-config.xml", target / "precice-config.xml")
    shutil.copy2(SOURCE_CASE / "contract.json", target / "contract.json")


def prepare_case(target: Path, outer_count: int, label: str) -> None:
    copy_case(target)
    xml_path = target / "precice-config.xml"
    xml = xml_path.read_text(encoding="utf-8")
    require('<max-time-windows value="25"/>' in xml, "unexpected source max-time-windows")
    require('<max-iterations value="20"/>' in xml, "unexpected source max-iterations")
    xml = xml.replace('<max-time-windows value="25"/>', '<max-time-windows value="1"/>')
    xml = xml.replace('<max-iterations value="20"/>', '<max-iterations value="4"/>')
    xml = re.sub(r'exchange-directory="[^"]+"', f'exchange-directory="{RUN / label / "precice-sockets"}"', xml, count=1)
    xml_path.write_text(xml, encoding="utf-8")

    control = target / "system/controlDict"
    control_text = control.read_text(encoding="utf-8")
    require("libpreciceAdapterFunctionObject.so" in control_text, "adapter entry missing")
    control.write_text(control_text.replace("libpreciceAdapterFunctionObject.so", str(ADAPTER)), encoding="utf-8")

    fv = target / "system/fvSolution"
    fv_text = fv.read_text(encoding="utf-8")
    require(re.search(r"nOuterCorrectors\s+3;", fv_text), "K28 current nOuterCorrectors is not 3")
    if outer_count != 3:
        fv.write_text(re.sub(r"(nOuterCorrectors\s+)3(;)", rf"\g<1>{outer_count}\2", fv_text, count=1), encoding="utf-8")

    contract = json.loads((target / "contract.json").read_text(encoding="utf-8"))
    contract.setdefault("execution_authorization", {})["max_windows"] = 1
    contract.setdefault("coupling", {})["max_iterations"] = 4
    contract["coupling"]["accepted_window_limit"] = 1
    contract["coupling"]["duration_s"] = DT
    (target / "contract.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")


def build_solver() -> Path:
    source = RUN / "solver-source"
    require(not source.exists(), f"refusing to overwrite solver source {source}")
    shutil.copytree(K26_SOURCE, source)
    shutil.copy2(ROOT / "scripts/phase1k29_inner_trace.H", source / "phase1k29_inner_trace.H")
    main = source / "pimpleFoam.C"
    text = main.read_text(encoding="utf-8")
    require('#include "Phase1K26StageTrace.H"' in text, "K26 solver source marker missing")
    text = text.replace('#include "Phase1K26StageTrace.H"', '#include "Phase1K26StageTrace.H"\n#include "phase1k29_inner_trace.H"')
    marker = 'phase1k26diag::write(mesh, "S08_after_turbulence", phase1k26SolveId, phase1k26Outer);'
    require(text.count(marker) == 1, "solver stage insertion point is not unique")
    text = text.replace(marker, marker + '\n            phase1k29diag::writeOuter(mesh, p, U, turbulence->k(), turbulence->omega(), turbulence->nut(), phi, *turbulence, phase1k26SolveId, phase1k26Outer);')
    main.write_text(text, encoding="utf-8")
    make_files = source / "Make/files"
    make_text = make_files.read_text(encoding="utf-8")
    require("pimpleFoamPhase1K26Diag" in make_text, "unexpected Make/files")
    make_files.write_text(make_text.replace("pimpleFoamPhase1K26Diag", "pimpleFoamPhase1K29Diag"), encoding="utf-8")
    build_log = RUN / "solver-build.log"
    command = "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; cd \"$1\"; wmake"
    result = subprocess.run(["/bin/bash", "-c", command, "phase1k29-build", str(source)], capture_output=True, text=True, timeout=900)
    build_log.write_text(result.stdout + result.stderr, encoding="utf-8")
    require(result.returncode == 0, f"diagnostic solver build failed; see {build_log}")
    solver = Path("/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/bin/pimpleFoamPhase1K29Diag")
    require(solver.is_file(), f"diagnostic solver missing: {solver}")
    return solver


def loaded_libraries(pid: int) -> set[str]:
    maps = Path(f"/proc/{pid}/maps")
    if not maps.is_file():
        return set()
    return {line.split()[-1].removesuffix(" (deleted)") for line in maps.read_text(errors="replace").splitlines()
            if line.split() and any(x in line for x in ("libpreciceAdapter", "libprecice.so"))}


def launch(label: str, solver: Path) -> dict:
    root = RUN / label
    case = root / "case"
    (root / "precice-sockets").mkdir(parents=True)
    for name in ("diagnostics", "rbf_diagnostics", "stages", "fields"):
        (root / name).mkdir()
    env = os.environ.copy()
    env.update({
        "PYTHONUNBUFFERED": "1",
        "PHASE1K24_DIAG_DIR": str(root / "diagnostics"),
        "PHASE1K18_DIAG_DIR": str(root / "rbf_diagnostics"),
        "PHASE1K26_STAGE_DIR": str(root / "stages"),
        "PHASE1K27_DIRECT_FORCE_TRACE": str(root / "direct_force_trace.jsonl"),
        "PHASE1K27_ADAPTER_PREWRITE_TRACE": str(root / "adapter_prewrite_force.jsonl"),
        "PHASE1K27_FLUID_INPUT_TRACE": str(root / "fluid_input_trace.jsonl"),
        "PHASE1K29_OUTER_FORCE_TRACE": str(root / "outer_iteration_force_trace.jsonl"),
        "PHASE1K29_FIELD_SNAPSHOT_DIR": str(root / "fields"),
    })
    fluid = ["/bin/bash", "-c", "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; cd \"$1\"; exec \"$2\" -case .", "phase1k29-fluid", str(case), str(solver)]
    structure = ["/usr/bin/python3.10", str(RUN / "fixed_structure.py"), str(case / "precice-config.xml"), str(root / "fixed_structure_result.json"), str(DSTAR[0]), str(DSTAR[1])]
    processes: dict[str, subprocess.Popen] = {}
    handles = []
    observed = {"fluid": set(), "structure": set()}
    reason = None
    started = time.monotonic()
    try:
        for role, command in (("fluid", fluid), ("structure", structure)):
            out = (root / f"{role}.stdout").open("x")
            err = (root / f"{role}.stderr").open("x")
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
        "socket_entries_after_shutdown": sorted(p.name for p in (root / "precice-sockets").iterdir()),
    }
    (root / "process_cleanup.json").write_text(json.dumps(cleanup, indent=2) + "\n", encoding="utf-8")
    require(reason is None, f"{label} runtime stopped: {reason}")
    require(cleanup["exit_codes"] == {"fluid": 0, "structure": 0}, f"{label} nonzero participant exits")
    require(any(ADAPTER.name in x for x in cleanup["loaded_libraries_by_role"]["fluid"]), f"{label} B1 adapter was not loaded")
    return cleanup


def record_config(label: str, outer_count: int) -> None:
    case = RUN / label / "case"
    files = ["system/fvSolution", "system/fvSchemes", "constant/momentumTransport", "constant/physicalProperties", "constant/dynamicMeshDict", "system/controlDict", "system/preciceDict", "precice-config.xml", "contract.json"]
    restart = ["30/uniform/time", "30/U", "30/p", "30/k", "30/omega", "30/nut", "30/pointDisplacement", "30/cellDisplacement", "30/phi", "30/phi_0", "30/U_0", "30/k_0", "30/omega_0", "constant/polyMesh/points", "constant/polyMesh/faces", "constant/polyMesh/owner", "constant/polyMesh/neighbour", "constant/polyMesh/boundary"]
    data = {"label": label, "outer_count": outer_count, "nCorrectors": 2, "nNonOrthogonalCorrectors": 0, "momentumPredictor": True,
            "adapter_sha256": sha(ADAPTER), "adapter_build_id": run_text(["readelf", "-n", str(ADAPTER)]).split("Build ID:", 1)[1].splitlines()[0].strip(),
            "configuration_hashes": {rel: sha(case / rel) for rel in files}, "restart_hashes": {rel: sha(case / rel) for rel in restart}}
    (RUN / label / "configuration.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    require(run_text(["git", "rev-parse", "HEAD"]) == EXPECTED_HEAD, "K29 must start at frozen K28 HEAD")
    require(sha(ADAPTER) == EXPECTED_ADAPTER_SHA, "K28 B1/G2 adapter SHA mismatch")
    require(sha(Path("/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1")) == "b20729622d2dbbafdea3d6ead0480ec66be98cb947db3500cc3c27ed4e3039c7", "preCICE SHA mismatch")
    require(SOURCE_CASE.is_dir() and K26_SOURCE.is_dir() and K26_STRUCTURE.is_file(), "K28 provenance source missing")
    require(len(sys.argv) == 2 and sys.argv[1] in {"preflight", "run"}, "usage: preflight|run")
    if sys.argv[1] == "preflight":
        require(not RUN.exists(), f"refusing to overwrite run {RUN}")
        RUN.mkdir(parents=True)
        shutil.copy2(K26_STRUCTURE, RUN / "fixed_structure.py")
        solver = build_solver()
        (RUN / "solver_identity.json").write_text(json.dumps({"base_solver_sha256": EXPECTED_SOLVER_BASE_SHA, "diagnostic_solver": str(solver), "diagnostic_solver_sha256": sha(solver), "source": str(RUN / "solver-source")}, indent=2) + "\n")
        for label, outer in (("A", 3), ("B1", 6), ("B2", 6)):
            (RUN / label).mkdir()
            prepare_case(RUN / label / "case", outer, label)
            record_config(label, outer)
        (RUN / "preflight_status.json").write_text(json.dumps({"status": "PASS_PREFLIGHT_ONLY", "runtime_started": False, "physical_windows": 0, "A_outer": 3, "B_outer": 6}, indent=2) + "\n")
        return 0

    status = json.loads((RUN / "preflight_status.json").read_text())
    require(status == {"status": "PASS_PREFLIGHT_ONLY", "runtime_started": False, "physical_windows": 0, "A_outer": 3, "B_outer": 6}, "preflight gate mismatch")
    solver = Path(json.loads((RUN / "solver_identity.json").read_text())["diagnostic_solver"])
    for label in ("A", "B1", "B2"):
        launch(label, solver)
    (RUN / "process_cleanup.json").write_text(json.dumps({label: json.loads((RUN / label / "process_cleanup.json").read_text()) for label in ("A", "B1", "B2")}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
