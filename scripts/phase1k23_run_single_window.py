#!/usr/bin/env python3
"""Run one Phase 1K.23 diagnostic coupling window in an isolated case.

This runner is deliberately separate from the production launcher.  It only
accepts a prepared scratch directory, verifies the frozen K22 identities and
the one-window diagnostic XML, then starts Fluid and the diagnostic Structure
copy in their scratch case working directory.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import re


ROOT = Path(__file__).resolve().parents[1]
K22 = ROOT / "evidence/phase1k22_five_window_experimental/run-20260924T170918Z-c2245ff-r6j6GB"
K11_STAGING = ROOT / "evidence/phase1k11_25window_rbf_fsi/staging-20260924T093404Z-c2245ff"
ADAPTER = ROOT / "evidence/phase1k20_point_checkpoint/run-20260924T164027Z-c2245ff-Gu2Hg5/build/libpreciceAdapterPhase1K20.so"
RBF = ROOT / "evidence/phase1k20_point_checkpoint/run-20260924T164027Z-c2245ff-Gu2Hg5/build/libRBFMeshMotionSolverPhase1K187BStopDiag.so"
WORKER = ROOT / "build/phase1d6_worker/cfd_ancf_ancf_kernel_worker"
PARTICIPANT_SOURCE = K22 / "participant_trace.py"

EXPECTED = {
    "adapter_sha256": "225ecab227b8271f01119fe476370e3a0b705ca06e1ca3a7739200266499b165",
    "rbf_sha256": "508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11",
    "worker_sha256": "3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596",
    "worker_source_sha256": "c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e",
    "dt_s": 0.0002,
    "max_iterations": 40,
    "min_iterations": 2,
    "xml_max_windows": 1,
    "participant_authorized_windows": 5,
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("PHASE1K23_PREFLIGHT_FAIL: " + message)


def json_load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def prepare_case(run: Path) -> Path:
    case = run / "case"
    require(not run.exists() or not any(run.iterdir()), f"run directory is not empty: {run}")
    run.mkdir(parents=True, exist_ok=True)
    source_case = K22 / "case"
    case.mkdir()
    # Copy only the unadvanced restart and case configuration.  K22 contains
    # later output directories; carrying those into this run would violate the
    # exact-30.0-scratch contract even if the solver ignored them.
    for name in ("30", "constant", "system"):
        shutil.copytree(source_case / name, case / name)
    for path in source_case.iterdir():
        if path.is_file():
            shutil.copy2(path, case / path.name)
    # The K22 contract references these immutable release artifacts one level
    # above case/.  K22's saved directory omitted new_restart_provenance.json;
    # recover that exact hash-pinned artifact from its recorded K11 staging
    # source instead of weakening the contract or fabricating a replacement.
    for name, source in (
        ("new_restart_provenance.json", K11_STAGING / "new_restart_provenance.json"),
        ("new_f0_qualified_result.json", K22 / "new_f0_qualified_result.json"),
        ("f0_recovery_report_frozen.md", K22 / "f0_recovery_report_frozen.md"),
    ):
        require(source.is_file(), f"frozen release artifact missing: {source}")
        shutil.copy2(source, run / name)
    shutil.copy2(PARTICIPANT_SOURCE, run / "participant_trace.py")
    return case


def patch_scratch_contract(case: Path, run: Path) -> None:
    xml_path = case / "precice-config.xml"
    # Preserve the namespace prefixes from the validated K22 XML.  Foundation
    # preCICE 3.4.1 accepts the declared project prefixes but rejects the
    # generic ns0/ns1 prefixes emitted by ElementTree serialization.
    xml = xml_path.read_text(encoding="utf-8")
    require(xml.count('<max-time-windows value="5"/>') == 1, "K22 max-time-windows token is not unique")
    require(xml.count('<max-iterations value="20"/>') == 1, "K22 max-iterations token is not unique")
    require(xml.count('exchange-directory="') == 1, "K22 socket attribute is not unique")
    xml = xml.replace('<max-time-windows value="5"/>', '<max-time-windows value="1"/>')
    xml = xml.replace('<max-iterations value="20"/>', '<max-iterations value="40"/>')
    xml = re.sub(r'exchange-directory="[^"]+"', f'exchange-directory="{run / "precice-sockets"}"', xml, count=1)
    xml_path.write_text(xml, encoding="utf-8")

    contract_path = case / "contract.json"
    contract = json_load(contract_path)
    contract["coupling"]["max_iterations"] = EXPECTED["max_iterations"]
    auth = contract["execution_authorization"]
    require(auth["max_windows"] == EXPECTED["participant_authorized_windows"], "K22 participant authorization changed")
    require(auth["adapter_runtime_sha256"] == EXPECTED["adapter_sha256"], "K20 adapter contract SHA changed")
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")


def preflight(run: Path, case: Path) -> dict:
    require(case.resolve().is_dir(), "scratch case missing")
    time_text = (case / "30/uniform/time").read_text(encoding="utf-8")
    time_value = re.search(r"^\s*value\s+([-+0-9.eE]+)\s*;", time_text, re.MULTILINE)
    require(time_value is not None and float(time_value.group(1)) == 30.0, "restart time is not 30")
    for relative in ("30/uniform/time", "30/U", "30/p", "30/k", "30/omega", "30/nut", "30/pointDisplacement",
                     "constant/polyMesh/points", "constant/polyMesh/faces", "constant/polyMesh/owner",
                     "constant/polyMesh/neighbour", "constant/polyMesh/boundary"):
        require(sha(case / relative) == sha(K22 / "case" / relative), f"K22 frozen input differs: {relative}")
    for path, key in ((ADAPTER, "adapter_sha256"), (RBF, "rbf_sha256"), (WORKER, "worker_sha256")):
        require(path.is_file() and os.access(path, os.X_OK), f"missing/non-executable identity: {path}")
        require(sha(path) == EXPECTED[key], f"{key} mismatch: {path}")
    contract = json_load(case / "contract.json")
    require(contract["coupling"]["max_iterations"] == EXPECTED["max_iterations"], "contract max_iterations mismatch")
    require(contract["execution_authorization"]["max_windows"] == EXPECTED["participant_authorized_windows"], "authorization mismatch")
    require(contract["execution_authorization"]["adapter_runtime_sha256"] == EXPECTED["adapter_sha256"], "adapter contract mismatch")
    xml_root = ET.parse(case / "precice-config.xml").getroot()
    get = lambda name: [e for e in xml_root.iter() if e.tag.split("}")[-1] == name]
    require(get("max-time-windows")[0].get("value") == "1", "XML is not one-window bounded")
    require(get("max-iterations")[0].get("value") == str(EXPECTED["max_iterations"]), "XML diagnostic ceiling mismatch")
    require(get("min-iterations")[0].get("value") == str(EXPECTED["min_iterations"]), "XML min iterations changed")
    require(get("time-window-size")[0].get("value") == "0.0002", "XML dt changed")
    require(not (run / "precice-sockets").exists(), "stale socket directory exists")
    validator = subprocess.run(["precice-config-validate", str(case / "precice-config.xml")], capture_output=True, text=True, timeout=60)
    (run / "precice_config_validate.stdout").write_text(validator.stdout, encoding="utf-8")
    (run / "precice_config_validate.stderr").write_text(validator.stderr, encoding="utf-8")
    require(validator.returncode == 0, "preCICE XML validation failed")
    audit = subprocess.run(["/usr/bin/python3.10", str(run / "participant_trace.py"), "--case", str(case), "--audit-only"],
                           cwd=case, capture_output=True, text=True, timeout=60)
    (run / "structure_audit_preflight.stdout").write_text(audit.stdout, encoding="utf-8")
    (run / "structure_audit_preflight.stderr").write_text(audit.stderr, encoding="utf-8")
    require(audit.returncode == 0 and '"status": "PASS"' in audit.stdout, "Structure audit failed")
    identity = {
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "openfoam_bashrc": "/opt/openfoam10/etc/bashrc",
        "precice_runtime_expected": "3.4.1",
        "python_executable": "/usr/bin/python3.10",
        "pyprecice_metadata_expected": "3.4.0",
        "worker_source_sha256": EXPECTED["worker_source_sha256"],
        "worker_binary_sha256": EXPECTED["worker_sha256"],
        "adapter_path": str(ADAPTER), "adapter_sha256": EXPECTED["adapter_sha256"],
        "rbf_path": str(RBF), "rbf_sha256": EXPECTED["rbf_sha256"],
        "restart_global_time_s": 30.0,
        "restart_field_hashes": {relative: sha(case / relative) for relative in (
            "30/uniform/time", "30/U", "30/p", "30/k", "30/omega", "30/nut", "30/pointDisplacement")},
        "mesh_hashes": {relative: sha(case / relative) for relative in (
            "constant/polyMesh/points", "constant/polyMesh/faces", "constant/polyMesh/owner",
            "constant/polyMesh/neighbour", "constant/polyMesh/boundary")},
        "phase1k22_case_hashes": {relative: sha(case / relative) for relative in (
            "system/fvSolution", "system/fvSchemes", "constant/dynamicMeshDict", "precice-config.xml", "contract.json")},
        "experimental_adapter_source_provenance_resolved": False,
        "qualified_historical_adapter_used": False,
    }
    (run / "runtime_identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    configuration = {relative: sha(case / relative) for relative in (
        "system/fvSolution", "system/fvSchemes", "constant/dynamicMeshDict", "system/preciceDict",
        "precice-config.xml", "contract.json")}
    (run / "configuration_sha256.json").write_text(json.dumps(configuration, indent=2) + "\n", encoding="utf-8")
    return identity


def launch(run: Path, case: Path) -> dict:
    (run / "precice-sockets").mkdir()
    (run / "diagnostics").mkdir()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PHASE1K18_DIAG_DIR"] = str(run / "diagnostics")
    env["PHASE1K18_7B_ANCF_TRACE"] = str(run / "ancf_checkpoint_stages.jsonl")
    env["PHASE1K18_7B_PRE_ADVANCE_TRACE"] = str(run / "pre_advance_attempts.jsonl")
    env.pop("PHASE1K18_7B_STOP_AFTER_RETRY_S5", None)
    fluid_command = ["/bin/bash", "-c", "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; cd \"$1\" || exit 91; test \"$(pwd -P)\" = \"$(realpath \"$1\")\" || exit 92; printf 'PHASE1K23_FLUID_PWD=%s\\n' \"$(pwd -P)\"; exec pimpleFoam -case .", "phase1k23-fluid", str(case)]
    structure_command = ["/usr/bin/python3.10", str(run / "participant_trace.py"), "--case", str(case), "--run", "--worker", str(WORKER), "--max-windows", "5", "--trace-output", str(run / "structure_trace.jsonl"), "--audit-output", str(run / "structure_audit_live.json")]
    handles = []
    processes = {}
    for role, command in (("fluid", fluid_command), ("structure", structure_command)):
        out = (run / f"{role}.stdout").open("x")
        err = (run / f"{role}.stderr").open("x")
        handles.extend([out, err])
        processes[role] = subprocess.Popen(command, cwd=case, env=env, stdout=out, stderr=err, start_new_session=True)
    loaded = set()
    worker_pids = set()
    started = time.monotonic()
    reason = None
    deadline = started + 1200
    try:
        while any(p.poll() is None for p in processes.values()):
            fluid_pid = processes["fluid"].pid
            maps = Path(f"/proc/{fluid_pid}/maps")
            if maps.exists():
                for line in maps.read_text().splitlines():
                    if "libpreciceAdapter" in line or "libRBFMeshMotionSolver" in line:
                        loaded.add(line.split()[-1])
            structure_pid = processes["structure"].pid
            child_file = Path(f"/proc/{structure_pid}/task/{structure_pid}/children")
            if child_file.exists():
                worker_pids.update(child_file.read_text().split())
            if time.monotonic() > deadline:
                reason = "1200-second hard timeout"
                break
            failed = [role for role, proc in processes.items() if proc.poll() not in (None, 0)]
            if failed:
                reason = "participant exited nonzero: " + ",".join(failed)
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
    result = {
        "fluid_command": fluid_command, "structure_command": structure_command,
        "fluid_pid": processes["fluid"].pid, "structure_pid": processes["structure"].pid,
        "observed_worker_pids": sorted(worker_pids), "loaded_libraries_observed": sorted(loaded),
        "exit_codes": {role: proc.returncode for role, proc in processes.items()},
        "stop_reason": reason, "wall_duration_s": time.monotonic() - started,
        "working_directory": str(case), "authorized_physical_windows": 1,
    }
    (run / "process_cleanup.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    require(len(sys.argv) in (2, 3) and (len(sys.argv) == 2 or sys.argv[1] in ("--preflight-only", "--launch-existing")),
            "usage: phase1k23_run_single_window.py [--preflight-only|--launch-existing] RUN_DIR")
    run = Path(sys.argv[-1]).expanduser().resolve()
    existing = len(sys.argv) == 3 and sys.argv[1] == "--launch-existing"
    if existing:
        case = run / "case"
        require(case.is_dir(), f"existing scratch case missing: {case}")
    else:
        case = prepare_case(run)
        patch_scratch_contract(case, run)
    preflight(run, case)
    (run / "preflight_status.json").write_text(json.dumps({"status": "PASS_PREFLIGHT_ONLY", "actual_window_cap": 1, "diagnostic_iteration_ceiling": 40}, indent=2) + "\n", encoding="utf-8")
    if len(sys.argv) == 3 and sys.argv[1] == "--preflight-only":
        print(json.dumps({"status": "PASS_PREFLIGHT_ONLY", "actual_window_cap": 1, "diagnostic_iteration_ceiling": 40}, indent=2))
        return 0
    result = launch(run, case)
    (run / "qualification_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if all(value == 0 for value in result["exit_codes"].values()) and result["stop_reason"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
