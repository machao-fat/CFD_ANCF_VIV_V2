#!/usr/bin/env python3
"""Run one fixed-displacement Fluid replay for Phase 1K.23 repeatability."""

from __future__ import annotations

import json
from pathlib import Path
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase1k23_run_single_window import (  # noqa: E402
    ADAPTER, EXPECTED, K22, RBF, WORKER, prepare_case, patch_scratch_contract, require, sha,
)


SOURCE_DIAGNOSTIC = Path(__file__).resolve().parents[1] / "evidence/phase1k23_single_window_convergence/run-20260925T055605Z-d3890de-e/structure_trace.jsonl"
FAKE_STRUCTURE = Path(__file__).resolve().parent / "phase1k23_fixed_displacement_structure.py"


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: phase1k23_run_repeatability.py RUN_DIR")
    run = Path(sys.argv[1]).expanduser().resolve()
    case = prepare_case(run)
    patch_scratch_contract(case, run)
    xml_path = case / "precice-config.xml"
    xml = xml_path.read_text(encoding="utf-8")
    require(xml.count('<max-iterations value="40"/>') == 1, "diagnostic XML max-iterations is not 40")
    xml_path.write_text(xml.replace('<max-iterations value="40"/>', '<max-iterations value="4"/>'), encoding="utf-8")
    contract_path = case / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["coupling"]["max_iterations"] = 4
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(FAKE_STRUCTURE, run / "fixed_structure.py")
    (run / "diagnostics").mkdir()
    validator = subprocess.run(["precice-config-validate", str(xml_path)], capture_output=True, text=True, timeout=60)
    (run / "precice_config_validate.stdout").write_text(validator.stdout, encoding="utf-8")
    (run / "precice_config_validate.stderr").write_text(validator.stderr, encoding="utf-8")
    require(validator.returncode == 0, "repeatability XML validation failed")
    rows = [json.loads(line) for line in SOURCE_DIAGNOSTIC.read_text(encoding="utf-8").splitlines() if line.strip()]
    d_star = rows[0]["D_trial_from_ancf_m"][:2]
    source_trace_sha = sha(SOURCE_DIAGNOSTIC)
    identity = {
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1], text=True).strip(),
        "restart_source": str(K22 / "case/30"), "restart_time_s": 30.0,
        "adapter_sha256": sha(ADAPTER), "rbf_sha256": sha(RBF), "worker_sha256": sha(WORKER),
        "experimental_adapter_source_provenance_resolved": False,
        "d_star": d_star, "d_star_source": str(SOURCE_DIAGNOSTIC), "d_star_source_sha256": source_trace_sha,
        "max_iterations": 4, "max_windows": 1, "dt_s": 0.0002,
    }
    (run / "runtime_identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PHASE1K18_DIAG_DIR"] = str(run / "diagnostics")
    fluid_cmd = ["/bin/bash", "-c", "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; cd \"$1\" || exit 91; test \"$(pwd -P)\" = \"$(realpath \"$1\")\" || exit 92; printf 'PHASE1K23_REPEAT_FLUID_PWD=%s\\n' \"$(pwd -P)\"; exec pimpleFoam -case .", "phase1k23-repeat-fluid", str(case)]
    structure_cmd = ["/usr/bin/python3.10", str(run / "fixed_structure.py"), str(case / "precice-config.xml"), str(run / "fixed_structure_result.json"), str(d_star[0]), str(d_star[1])]
    (run / "precice-sockets").mkdir()
    processes = {}; handles = []
    for role, cmd in (("fluid", fluid_cmd), ("structure", structure_cmd)):
        out = (run / f"{role}.stdout").open("x"); err = (run / f"{role}.stderr").open("x")
        handles.extend((out, err)); processes[role] = subprocess.Popen(cmd, cwd=case, env=env, stdout=out, stderr=err, start_new_session=True)
    loaded = set(); reason = None; start = time.monotonic(); deadline = start + 600
    try:
        while any(p.poll() is None for p in processes.values()):
            maps = Path(f"/proc/{processes['fluid'].pid}/maps")
            if maps.exists():
                for line in maps.read_text().splitlines():
                    if "libpreciceAdapter" in line or "libRBFMeshMotionSolver" in line:
                        loaded.add(line.split()[-1])
            if time.monotonic() > deadline:
                reason = "600-second hard timeout"; break
            failed = [role for role, p in processes.items() if p.poll() not in (None, 0)]
            if failed:
                reason = "participant exited nonzero: " + ",".join(failed); break
            time.sleep(0.2)
        if reason:
            for p in processes.values():
                if p.poll() is None: p.terminate()
            time.sleep(2)
            for p in processes.values():
                if p.poll() is None: p.kill()
    finally:
        for p in processes.values(): p.wait(timeout=30)
        for handle in handles: handle.close()
    cleanup = {"fluid_command": fluid_cmd, "structure_command": structure_cmd,
               "exit_codes": {role: p.returncode for role, p in processes.items()},
               "loaded_libraries_observed": sorted(loaded), "stop_reason": reason,
               "wall_duration_s": time.monotonic() - start, "working_directory": str(case)}
    (run / "process_cleanup.json").write_text(json.dumps(cleanup, indent=2) + "\n", encoding="utf-8")
    require(reason is None and all(code == 0 for code in cleanup["exit_codes"].values()), "repeatability runtime failed; inspect logs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
