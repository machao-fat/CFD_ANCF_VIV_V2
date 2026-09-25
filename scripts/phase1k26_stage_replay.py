#!/usr/bin/env python3
"""Run one isolated, branch-equivalent Phase 1K.26 stage replay.

Every invocation makes a new scratch case from the frozen K24 copy of K22's
30.0 s restart.  The case has exactly one physical window and four diagnostic
attempts.  No production solver, adapter, RBF library, or case is changed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

from phase1k24_fluid_state_replay import (
    ADAPTER, DSTAR, ROOT, copy_case, patch_case, record_identity, require, sha,
    validate,
)


SOLVER = Path("/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/bin/pimpleFoamPhase1K26Diag")
EXPECTED_ADAPTER_SHA = "3d75ae9fcebba444d8e21fa228fddc394e8748959d3b8ae340732fd21b3abd25"
EXPECTED_SOURCE_HEAD = "4182ac91a08b16edd5982a34cd22dbfa050c7fae"
EXPECTED_BRANCH = "diagnostic/phase1k26-earliest-fluid-replay-divergence-v1"
G2_ADAPTER = ROOT / "evidence/phase1k25_minimal_rollback_repair/run-20260925T080000Z-d3890de-G2/candidate-G2/adapter-build/libpreciceAdapterPhase1K25G2Diag.so"
EXPECTED_G2_SHA = "f9a89b21b0a0fe92f297a0c8bceb67bc5df5f52e5f7a9c35fa17df5b7eb8b754"


def launch(run: Path, case: Path) -> dict:
    (run / "precice-sockets").mkdir()
    for name in ("diagnostics", "rbf_diagnostics", "stages"):
        (run / name).mkdir()

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PHASE1K24_DIAG_DIR"] = str(run / "diagnostics")
    env["PHASE1K18_DIAG_DIR"] = str(run / "rbf_diagnostics")
    env["PHASE1K26_STAGE_DIR"] = str(run / "stages")
    fluid_command = [
        "/bin/bash", "-c",
        "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; "
        "cd \"$1\" || exit 91; test \"$(pwd -P)\" = \"$(realpath \"$1\")\" || exit 92; "
        "printf 'PHASE1K26_FLUID_PWD=%s\\n' \"$(pwd -P)\"; exec \"$2\" -case .",
        "phase1k26-fluid", str(case), str(SOLVER),
    ]
    structure_command = [
        "/usr/bin/python3.10", str(run / "fixed_structure.py"),
        str(case / "precice-config.xml"), str(run / "fixed_structure_result.json"),
        str(DSTAR[0]), str(DSTAR[1]),
    ]

    processes = {}
    handles = []
    loaded = set()
    reason = None
    start = time.monotonic()
    try:
        for role, command in (("fluid", fluid_command), ("structure", structure_command)):
            stdout = (run / f"{role}.stdout").open("x")
            stderr = (run / f"{role}.stderr").open("x")
            handles.extend((stdout, stderr))
            processes[role] = subprocess.Popen(
                command, cwd=case, env=env, stdout=stdout, stderr=stderr,
                start_new_session=True,
            )
        deadline = start + 900
        while any(proc.poll() is None for proc in processes.values()):
            maps = Path(f"/proc/{processes['fluid'].pid}/maps")
            if maps.exists():
                for line in maps.read_text(encoding="utf-8", errors="replace").splitlines():
                    if any(token in line for token in ("libpreciceAdapter", "libRBFMeshMotionSolver", "libprecice.so")):
                        loaded.add(line.split()[-1])
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
            time.sleep(2)
            for proc in processes.values():
                if proc.poll() is None:
                    proc.kill()
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
        "loaded_libraries_observed": sorted(loaded),
        "stop_reason": reason,
        "wall_duration_s": time.monotonic() - start,
        "working_directory": str(case),
    }
    (run / "process_cleanup.json").write_text(json.dumps(cleanup, indent=2) + "\n")
    return cleanup


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in ("same", "freshA", "freshB", "g2"):
        raise SystemExit("usage: phase1k26_stage_replay.py same|freshA|freshB|g2 NEW_RUN_DIRECTORY")
    mode = sys.argv[1]
    run = Path(sys.argv[2]).expanduser().resolve()
    require(run.is_relative_to(ROOT / "evidence/phase1k26_earliest_divergence"), "run must be under Phase 1K.26 evidence root")
    require(not run.exists(), "run path already exists")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    require(head == EXPECTED_SOURCE_HEAD, "diagnostic checkpoint HEAD mismatch")
    require(branch == EXPECTED_BRANCH, "diagnostic branch mismatch")
    require(ADAPTER.is_file() and sha(ADAPTER) == EXPECTED_ADAPTER_SHA, "K24 experimental adapter mismatch")
    if mode == "g2":
        require(G2_ADAPTER.is_file() and sha(G2_ADAPTER) == EXPECTED_G2_SHA, "K25 G2 experimental adapter mismatch")
    require(SOLVER.is_file() and os.access(SOLVER, os.X_OK), "diagnostic solver unavailable")

    case = copy_case(run)
    patch_case(case, run, max_iterations=4, min_iterations=2)
    if mode == "g2":
        control_path = case / "system/controlDict"
        control = control_path.read_text(encoding="utf-8")
        require(control.count(str(ADAPTER)) == 1, "unexpected adapter library entry")
        control_path.write_text(control.replace(str(ADAPTER), str(G2_ADAPTER)), encoding="utf-8")
    identity = record_identity(run, case, mode, max_iterations=4, min_iterations=2)
    identity["diagnostic_solver"] = str(SOLVER)
    identity["diagnostic_solver_sha256"] = sha(SOLVER)
    identity["adapter_path"] = str(G2_ADAPTER if mode == "g2" else ADAPTER)
    identity["adapter_sha256"] = EXPECTED_G2_SHA if mode == "g2" else EXPECTED_ADAPTER_SHA
    identity["adapter_expected_sha256"] = identity["adapter_sha256"]
    identity["causal_intervention"] = "K25 G2 post-rollback meshPhi current/oldTime zeroing only" if mode == "g2" else None
    identity["branch_equivalent_protocol"] = "one-window, min=2 max=4, same D*, same read branch"
    (run / "runtime_identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    validate(run, case)
    (run / "preflight_status.json").write_text(json.dumps({"status": "PASS_PREFLIGHT_ONLY", "mode": mode}, indent=2) + "\n")
    cleanup = launch(run, case)
    require(cleanup["stop_reason"] is None, "runtime stopped before clean completion")
    require(all(code == 0 for code in cleanup["exit_codes"].values()), "runtime participant failed")
    require(len(list((run / "stages").glob("stage_*.json"))) > 0, "no stage trace was captured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
