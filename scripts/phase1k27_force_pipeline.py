#!/usr/bin/env python3
"""Run one bounded Phase 1K.27 G2 Force-pipeline diagnostic.

The diagnostic reuses the frozen one-window/four-attempt K26 G2 protocol,
loads a separately named K27 adapter build, and captures raw face Force,
unaccelerated adapter payload, Fluid-read displacement, and Structure reads.
It never modifies the authoritative case or any qualified runtime library.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import difflib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from phase1k24_fluid_state_replay import (
    ADAPTER as K24_ADAPTER,
    DSTAR,
    ROOT,
    WORKER,
    RBF,
    copy_case,
    patch_case,
    record_identity,
    require,
    sha,
    validate,
)


RUN_ID = "run-20260925T090832Z-e0da50c"
RUN = ROOT / "evidence/phase1k27_force_pipeline" / RUN_ID
K26_G2 = ROOT / "evidence/phase1k26_earliest_divergence/run-20260925T-phase1k26-4182ac9/selected_causal_test_G2"
K22_F0 = ROOT / "evidence/phase1k11_25window_rbf_fsi/staging-20260924T093404Z-c2245ff"
K25_G2_ADAPTER = ROOT / "evidence/phase1k25_minimal_rollback_repair/run-20260925T080000Z-d3890de-G2/candidate-G2/adapter-build/libpreciceAdapterPhase1K25G2Diag.so"
K27_ADAPTER = RUN / "adapter-build/libpreciceAdapterPhase1K27ForceDiag.so"
SOLVER = Path("/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/bin/pimpleFoamPhase1K26Diag")
EXPECTED_HEAD = "e0da50c5660ec266c4bee50769ab95f94f0b014a"
EXPECTED_BRANCH = "diagnostic/phase1k27-force-pipeline-decomposition-v1"
EXPECTED_K25_G2_SHA = "f9a89b21b0a0fe92f297a0c8bceb67bc5df5f52e5f7a9c35fa17df5b7eb8b754"
EXPECTED_RBF_SHA = "508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11"
EXPECTED_WORKER_SHA = "3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596"
EXPECTED_WORKER_SOURCE_SHA = "c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e"
EXPECTED_SOLVER_SHA = "e895e5f1788146da2205e4c8bb0b959f99f66e426c92dc7233d7ac303fd91e96"
EXPECTED_DT = 0.0002


def run_text(command: list[str], *, cwd: Path | None = None, timeout: int = 60) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    require(result.returncode == 0, f"command failed ({result.returncode}): {' '.join(command)}\n{result.stderr}")
    return result.stdout.strip()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    excluded = {".git", "lnInclude", "linux64GccDPInt32Opt"}
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in excluded for part in rel.parts):
            continue
        if path.name in {"Allwmake.log", "wmake.log", "ldd.log"}:
            continue
        files.append((rel.as_posix(), path))
    for name, path in sorted(files):
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(bytes.fromhex(sha(path)))
    return digest.hexdigest()


def write_source_patch() -> Path:
    baseline = K25_G2_ADAPTER.parent.parent / "adapter-source"
    require(baseline.is_dir(), f"K25 G2 source baseline missing: {baseline}")
    candidate = RUN / "adapter-source"
    excluded = {".git", "lnInclude", "linux64GccDPInt32Opt"}
    names = set()
    for root in (baseline, candidate):
        for path in root.rglob("*"):
            rel = path.relative_to(root)
            if path.is_file() and not any(part in excluded for part in rel.parts):
                names.add(rel.as_posix())
    chunks = []
    for name in sorted(names):
        old_path, new_path = baseline / name, candidate / name
        old = old_path.read_bytes() if old_path.is_file() else b""
        new = new_path.read_bytes() if new_path.is_file() else b""
        if old == new:
            continue
        try:
            old_lines = old.decode("utf-8").splitlines(keepends=True)
            new_lines = new.decode("utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            chunks.append(f"Binary file changed: {name}\n")
            continue
        chunks.extend(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{name}", tofile=f"b/{name}",
        ))
    result = RUN / "adapter_instrumentation.patch"
    result.write_text("".join(chunks), encoding="utf-8")
    require(result.stat().st_size > 0, "expected a non-empty experimental instrumentation patch")
    return result


def verify_git_boundary() -> dict:
    head = run_text(["git", "rev-parse", "HEAD"], cwd=ROOT)
    branch = run_text(["git", "branch", "--show-current"], cwd=ROOT)
    require(head == EXPECTED_HEAD, f"HEAD mismatch: {head}")
    require(branch == EXPECTED_BRANCH, f"branch mismatch: {branch}")
    diff_check = subprocess.run(["git", "diff", "--check"], cwd=ROOT, capture_output=True, text=True)
    require(diff_check.returncode == 0, "git diff --check failed")
    status_lines = run_text(["git", "status", "--porcelain=v1"], cwd=ROOT).splitlines()
    allowed = {
        "?? docs/PHASE1K27_FORCE_PIPELINE_AUDIT.md",
        "?? evidence/phase1k27_force_pipeline/",
        "?? scripts/phase1k27_force_pipeline.py",
        "?? scripts/phase1k27_analyze_force_pipeline.py",
    }
    unexpected = [line for line in status_lines if line not in allowed]
    require(not unexpected, f"unexpected worktree changes before runtime: {unexpected}")
    return {"head": head, "branch": branch, "status_lines": status_lines, "diff_check": "PASS"}


def capture_loaded_libraries(pid: int) -> set[str]:
    maps = Path(f"/proc/{pid}/maps")
    if not maps.is_file():
        return set()
    result = set()
    for line in maps.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if not fields:
            continue
        path = fields[-1]
        if any(key in path for key in ("libpreciceAdapter", "libRBFMeshMotionSolver", "libprecice.so")):
            result.add(path.removesuffix(" (deleted)"))
    return result


def launch(case: Path) -> dict:
    socket_dir = RUN / "precice-sockets"
    socket_dir.mkdir()
    require(not any(socket_dir.iterdir()), "new preCICE socket directory is not empty")
    unix_sockets = Path("/proc/net/unix").read_text(encoding="utf-8", errors="replace")
    require(str(socket_dir) not in unix_sockets, "socket directory already has a live /proc/net/unix entry")

    for name in ("diagnostics", "rbf_diagnostics", "stages"):
        (RUN / name).mkdir()
    structure_script = RUN / "prepared/fixed_structure.py"
    shutil.copy2(K26_G2 / "fixed_structure.py", structure_script)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PHASE1K24_DIAG_DIR"] = str(RUN / "diagnostics")
    env["PHASE1K18_DIAG_DIR"] = str(RUN / "rbf_diagnostics")
    env["PHASE1K26_STAGE_DIR"] = str(RUN / "stages")
    env["PHASE1K27_DIRECT_FORCE_TRACE"] = str(RUN / "direct_force_trace.jsonl")
    env["PHASE1K27_ADAPTER_PREWRITE_TRACE"] = str(RUN / "adapter_prewrite_force.jsonl")
    env["PHASE1K27_FLUID_INPUT_TRACE"] = str(RUN / "fluid_input_trace.jsonl")

    fluid_command = [
        "/bin/bash", "-c",
        "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; "
        "cd \"$1\" || exit 91; test \"$(pwd -P)\" = \"$(realpath \"$1\")\" || exit 92; "
        "printf 'PHASE1K27_FLUID_PWD=%s\\n' \"$(pwd -P)\"; exec \"$2\" -case .",
        "phase1k27-fluid", str(case), str(SOLVER),
    ]
    structure_result = RUN / "fixed_structure_result.json"
    structure_command = [
        "/usr/bin/python3.10", str(structure_script), str(case / "precice-config.xml"),
        str(structure_result), str(DSTAR[0]), str(DSTAR[1]),
    ]

    processes = {}
    handles = []
    loaded = {"fluid": set(), "structure": set()}
    reason = None
    start = time.monotonic()
    try:
        for role, command in (("fluid", fluid_command), ("structure", structure_command)):
            stdout = (RUN / f"{role}.stdout").open("x", encoding="utf-8")
            stderr = (RUN / f"{role}.stderr").open("x", encoding="utf-8")
            handles.extend((stdout, stderr))
            processes[role] = subprocess.Popen(
                command, cwd=case, env=env, stdout=stdout, stderr=stderr,
                start_new_session=True,
            )

        deadline = start + 900
        while any(proc.poll() is None for proc in processes.values()):
            for role, proc in processes.items():
                loaded[role].update(capture_loaded_libraries(proc.pid))
            failed = [role for role, proc in processes.items() if proc.poll() not in (None, 0)]
            if failed:
                reason = "participant exited nonzero: " + ",".join(failed)
                break
            if time.monotonic() > deadline:
                reason = "900-second hard timeout"
                break
            time.sleep(0.2)
        if reason:
            for proc in processes.values():
                if proc.poll() is None:
                    proc.terminate()
            for proc in processes.values():
                if proc.poll() is None:
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
        for role, proc in processes.items():
            loaded[role].update(capture_loaded_libraries(proc.pid))
    finally:
        for proc in processes.values():
            proc.wait(timeout=30)
        for handle in handles:
            handle.close()

    cleanup = {
        "fluid_command": fluid_command,
        "structure_command": structure_command,
        "pids": {role: proc.pid for role, proc in processes.items()},
        "exit_codes": {role: proc.returncode for role, proc in processes.items()},
        "loaded_libraries_by_role": {role: sorted(paths) for role, paths in loaded.items()},
        "stop_reason": reason,
        "wall_duration_s": time.monotonic() - start,
        "working_directory": str(case),
        "worker_process": "NOT_STARTED; fixed-displacement diagnostic participant",
        "socket_cleanup_after_shutdown": {
            "directory_exists": socket_dir.is_dir(),
            "entries": [p.name for p in socket_dir.iterdir()],
        },
    }
    (RUN / "process_cleanup.json").write_text(json.dumps(cleanup, indent=2) + "\n", encoding="utf-8")
    return cleanup


def main() -> int:
    if len(sys.argv) != 2 or Path(sys.argv[1]).resolve() != RUN.resolve():
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} {RUN}")
    require(RUN.is_dir(), f"evidence run directory missing: {RUN}")
    require((RUN / "adapter-source").is_dir(), "isolated K27 adapter source copy is missing")
    git_identity = verify_git_boundary()
    for rel in (
        "prepared", "precice-sockets", "diagnostics", "rbf_diagnostics", "stages",
        "runtime_identity.json", "restart_identity.json", "preflight_status.json",
        "fluid.stdout", "fluid.stderr", "structure.stdout", "structure.stderr",
        "process_cleanup.json", "direct_force_trace.jsonl", "adapter_prewrite_force.jsonl",
        "fluid_input_trace.jsonl", "fixed_structure_result.json", "adapter-build/ldd-r.txt",
    ):
        require(not (RUN / rel).exists(), f"refusing to overwrite existing diagnostic output: {RUN / rel}")

    require(K25_G2_ADAPTER.is_file() and sha(K25_G2_ADAPTER) == EXPECTED_K25_G2_SHA,
            "frozen K25 G2 adapter identity mismatch")
    require(K27_ADAPTER.is_file(), "K27 diagnostic adapter binary missing")
    link_result = subprocess.run([
        "/bin/bash", "-c",
        "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; ldd -r \"$1\"",
        "phase1k27-link-check", str(K27_ADAPTER),
    ], capture_output=True, text=True)
    require(link_result.returncode == 0, f"experimental adapter ldd -r failed: {link_result.stderr}")
    require("not found" not in link_result.stdout and "undefined symbol" not in link_result.stdout,
            "experimental adapter has unresolved runtime dependencies")
    link_log = RUN / "adapter-build/ldd-r.txt"
    link_log.write_text(link_result.stdout + link_result.stderr, encoding="utf-8")
    require(RBF.is_file() and sha(RBF) == EXPECTED_RBF_SHA, "RBF library identity mismatch")
    require(WORKER.is_file() and sha(WORKER) == EXPECTED_WORKER_SHA, "worker binary identity mismatch")
    require(SOLVER.is_file() and sha(SOLVER) == EXPECTED_SOLVER_SHA, "K26 diagnostic solver identity mismatch")
    require(abs(float(DSTAR[0]) - 1.0633832164606064e-07) == 0.0, "D* x mismatch")
    require(abs(float(DSTAR[1]) - 9.530777190012017e-08) == 0.0, "D* y mismatch")

    prep = RUN / "prepared"
    case = copy_case(prep)
    # The scratch XML and the directory created by launch() must identify the
    # same unique socket path. Keep it under this run, not under prepared/.
    patch_case(case, RUN, max_iterations=4, min_iterations=2)
    control_path = case / "system/controlDict"
    control = control_path.read_text(encoding="utf-8")
    require(control.count(str(K24_ADAPTER)) == 1, "unexpected K24 adapter entry in copied controlDict")
    control_path.write_text(control.replace(str(K24_ADAPTER), str(K27_ADAPTER)), encoding="utf-8")
    source_patch_path = write_source_patch()

    # Keep the scratch contract internally bounded to the same diagnostic
    # ceiling as the isolated preCICE XML. Production files remain untouched.
    scratch_contract_path = case / "contract.json"
    scratch_contract = json.loads(scratch_contract_path.read_text(encoding="utf-8"))
    scratch_contract["execution_authorization"]["max_windows"] = 1
    scratch_contract["coupling"]["max_iterations"] = 4
    scratch_contract["coupling"]["accepted_window_limit"] = 1
    scratch_contract["coupling"]["duration_s"] = EXPECTED_DT
    scratch_contract_path.write_text(json.dumps(scratch_contract, indent=2) + "\n", encoding="utf-8")

    k26_restart = json.loads((K26_G2 / "restart_identity.json").read_text(encoding="utf-8"))
    f0_result_path = K22_F0 / "new_f0_qualified_result.json"
    f0_restart_path = K22_F0 / "new_restart_provenance.json"
    f0_report_path = K22_F0 / "f0_recovery_report_frozen.md"
    for path in (f0_result_path, f0_restart_path, f0_report_path):
        require(path.is_file(), f"frozen K22 F0 provenance artifact missing: {path}")
    f0_result = json.loads(f0_result_path.read_text(encoding="utf-8"))
    f0_provenance = scratch_contract["initial_state"]["release_force_provenance"]
    require(f0_result["classification"] == "RELEASE_FORCE_RECOVERED_REPRODUCIBLY"
            and f0_result["global_time_s"] == 30.0
            and f0_result["Fx_raw_N"] == scratch_contract["initial_state"]["Fx0_total_N"]
            and f0_result["Fy_raw_N"] == scratch_contract["initial_state"]["Fy0_total_N"],
            "scratch F0 raw values/time do not match frozen result evidence")
    require(sha(f0_result_path) == f0_provenance["result_json_sha256"]
            and sha(f0_restart_path) == f0_provenance["provenance_json_sha256"]
            and sha(f0_report_path) == f0_provenance["recovery_report_sha256"],
            "one or more frozen K22 F0 provenance hashes mismatch")

    identity = record_identity(prep, case, "g2_force_pipeline", max_iterations=4, min_iterations=2)
    require(identity["restart_field_hashes"] == k26_restart["field_hashes"],
            "fresh diagnostic restart does not match the exact K26 G2 field/mesh hashes")
    identity.update({
        "git_head": git_identity["head"],
        "git_branch": git_identity["branch"],
        "git_status_before_runtime": git_identity["status_lines"],
        "worktree_diff_check": git_identity["diff_check"],
        "adapter_path": str(K27_ADAPTER),
        "adapter_sha256": sha(K27_ADAPTER),
        "adapter_build_id": run_text(["readelf", "-n", str(K27_ADAPTER)], cwd=ROOT)
            .split("Build ID:", 1)[1].splitlines()[0].strip(),
        "adapter_source_base_commit": "d53753b1c927b2413b02299c9da15725b3e772f0",
        "adapter_source_tree_sha256": tree_sha256(RUN / "adapter-source"),
        "adapter_instrumentation_patch_path": str(source_patch_path),
        "adapter_instrumentation_patch_sha256": sha(source_patch_path),
        "adapter_build_command": "source /opt/openfoam10/etc/bashrc; cd <isolated adapter-source>; wmake libso .",
        "adapter_compiler": run_text(["g++", "--version"]).splitlines()[0],
        "adapter_build_options": "-std=c++14; WM_OPTIONS=linux64GccDPInt32Opt",
        "adapter_build_log_sha256": sha(RUN / "adapter-build/build.log"),
        "adapter_link_check_path": str(link_log),
        "adapter_link_check_sha256": sha(link_log),
        "adapter_source_provenance_resolved": False,
        "adapter_candidate_parent_path": str(K25_G2_ADAPTER),
        "adapter_candidate_parent_sha256": sha(K25_G2_ADAPTER),
        "rbf_path": str(RBF),
        "rbf_sha256": sha(RBF),
        "worker_path": str(WORKER),
        "worker_sha256": sha(WORKER),
        "worker_source_sha256": EXPECTED_WORKER_SOURCE_SHA,
        "worker_process_started": False,
        "diagnostic_solver": str(SOLVER),
        "diagnostic_solver_sha256": sha(SOLVER),
        "diagnostic_only": True,
        "qualified_historical_adapter_used": False,
        "diagnostic_ceiling": {"physical_windows": 1, "iterations": 4},
        "fluid_displacement_star_m": DSTAR,
        "fluid_displacement_read_and_direct_force_ordinals_share_attempt_index": True,
    })

    of_env = run_text([
        "/bin/bash", "-c",
        "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; printf '%s|%s|%s|%s' \"$WM_PROJECT\" \"$WM_PROJECT_VERSION\" \"$WM_OPTIONS\" \"$FOAM_LIBBIN\"",
    ])
    project, of_version, wm_options, foam_libbin = of_env.split("|", 3)
    require(project == "OpenFOAM" and of_version == "10", f"unexpected OpenFOAM identity: {of_env}")
    precice_lib = Path("/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1")
    require(precice_lib.is_file(), "expected preCICE 3.4.1 runtime library is missing")
    require("3.4.1" in precice_lib.name, "preCICE runtime SONAME mismatch")
    py_identity = run_text([
        "/usr/bin/python3.10", "-c",
        "import importlib.metadata,precice,sys; print('|'.join([sys.executable,precice.__file__,importlib.metadata.version('pyprecice')]))",
    ])
    py_exe, py_module, py_package = py_identity.split("|", 2)
    require(py_exe == "/usr/bin/python3.10" and py_package == "3.4.0", "Python/preCICE binding identity mismatch")

    xml = (case / "precice-config.xml").read_text(encoding="utf-8")
    require('<max-time-windows value="1"/>' in xml, "diagnostic XML does not enforce one physical window")
    require('<max-iterations value="4"/>' in xml, "diagnostic XML iteration ceiling differs from K26 G2")
    require('<min-iterations value="2"/>' in xml, "diagnostic XML min-iterations differs")
    require('<acceleration:IQN-ILS reduced-time-grid="true">' in xml, "IQN-ILS block missing")
    require(xml.count('<data name="Force" mesh="Structure-Mesh"/>') == 1, "Force IQN primary data changed")
    require(xml.count('<data name="Displacement" mesh="Structure-Mesh"/>') == 1, "Displacement IQN primary data changed")
    require('max-used-iterations value="1"' in xml and 'time-windows-reused value="1"' in xml,
            "frozen IQN-ILS settings changed")
    identity.update({
        "openfoam_project": project,
        "openfoam_version": of_version,
        "openfoam_wm_options": wm_options,
        "openfoam_library_directory": foam_libbin,
        "precice_runtime_version": "3.4.1",
        "precice_runtime_path": str(precice_lib),
        "precice_runtime_sha256": sha(precice_lib),
        "python_executable": py_exe,
        "python_version": run_text([py_exe, "--version"]),
        "pyprecice_metadata_version": py_package,
        "precice_module_path": py_module,
        "restart_global_time_s": 30.0,
        "restart_identity_matches_k26_g2_exactly": True,
        "f0_raw_N": {
            "Fx": f0_result["Fx_raw_N"], "Fy": f0_result["Fy_raw_N"], "Fz": f0_result["Fz_raw_N"],
        },
        "f0_provenance": {
            "classification": f0_result["classification"],
            "result_path": str(f0_result_path), "result_sha256": sha(f0_result_path),
            "restart_provenance_path": str(f0_restart_path), "restart_provenance_sha256": sha(f0_restart_path),
            "recovery_report_path": str(f0_report_path), "recovery_report_sha256": sha(f0_report_path),
            "contract_embedded_result_sha256": f0_provenance["result_json_sha256"],
        },
        "dt_s": EXPECTED_DT,
        "max_time_windows": 1,
        "max_iterations": 4,
        "min_iterations": 2,
        "force_read_timing_contract": {"retry": EXPECTED_DT, "accepted_boundary": 0.0},
        "force_initialization": "initialize=yes; exact 30.0 s release state",
        "configuration_hashes": {relative: sha(case / relative) for relative in (
            "system/fvSolution", "system/fvSchemes", "system/controlDict",
            "constant/dynamicMeshDict", "system/preciceDict", "precice-config.xml", "contract.json",
        )},
        "preCICE_xml_sha256": sha(case / "precice-config.xml"),
        "xml_acceleration_profile": "IQN-ILS unchanged from K26 G2",
        "case_path": str(case),
        "restart_identity_path": str(prep / "restart_identity.json"),
        "k26_g2_runtime_identity_path": str(K26_G2 / "runtime_identity.json"),
    })
    (RUN / "runtime_identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(prep / "restart_identity.json", RUN / "restart_identity.json")

    validate(RUN, case)
    (RUN / "preflight_status.json").write_text(json.dumps({
        "status": "PASS_PREFLIGHT_ONLY",
        "git": git_identity,
        "runtime_identity": identity,
        "preCICE_config_validate": "PASS",
    }, indent=2) + "\n", encoding="utf-8")

    cleanup = launch(case)
    require(cleanup["stop_reason"] is None, f"runtime stopped: {cleanup['stop_reason']}")
    require(cleanup["exit_codes"] == {"fluid": 0, "structure": 0}, f"nonzero participant exits: {cleanup['exit_codes']}")
    require(str(K27_ADAPTER) in cleanup["loaded_libraries_by_role"]["fluid"], "Fluid did not load the K27 diagnostic adapter")
    require(any("libRBFMeshMotionSolver" in path for path in cleanup["loaded_libraries_by_role"]["fluid"]),
            "Fluid did not load the expected RBF solver library")
    require(any("libprecice.so.3.4.1" in path for role in cleanup["loaded_libraries_by_role"].values() for path in role),
            "no process map shows the preCICE 3.4.1 library")
    result = json.loads((RUN / "fixed_structure_result.json").read_text(encoding="utf-8"))
    attempts = [row for row in result["records"] if row.get("stage") == "attempt"]
    require(len(attempts) == 4, f"expected exactly four diagnostic attempts; got {len(attempts)}")
    require([row["attempt"] for row in attempts] == [1, 2, 3, 4], "unexpected attempt identity sequence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
