#!/usr/bin/env python3
"""Isolated preCICE 3.4.1 implicit Force read-time probe.

This runs two fake participants only. It does not import or initialize the
HH06 participant, OpenFOAM, or the ANCF worker.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent
FLUID_CODE = r'''import json, sys
import precice

config = sys.argv[1]
dt = 0.1
p = precice.Participant("Fluid", config, 0, 1)
ids = p.set_mesh_vertices("Fluid-Mesh", [[0.5, 0.5]])
if not p.requires_initial_data():
    raise RuntimeError("Fluid expected initial Force data")
p.write_data("Fluid-Mesh", "Force", ids, [[10.0, -10.0]])
init_dt = p.initialize()
if init_dt is not None:
    dt = float(init_dt)
records = []
attempt = 0
while p.is_coupling_ongoing():
    save = bool(p.requires_writing_checkpoint())
    attempt += 1
    force = [100.0 + attempt, -200.0 - 3.0 * attempt]
    p.write_data("Fluid-Mesh", "Force", ids, [force])
    p.advance(dt)
    retry = bool(p.requires_reading_checkpoint())
    records.append({"attempt": attempt, "force_written_before_advance": force,
                    "checkpoint_requested": save, "rollback_requested": retry})
p.finalize()
print(json.dumps({"role": "Fluid", "records": records}, sort_keys=True))
'''

STRUCTURE_CODE = r'''import json, sys
import precice

config, read_offset_arg = sys.argv[1], sys.argv[2]
dt = 0.1
read_offset = 0.0 if read_offset_arg == "zero" else dt
p = precice.Participant("Structure", config, 0, 1)
ids = p.set_mesh_vertices("Structure-Mesh", [[0.5, 0.5]])
if not p.requires_initial_data():
    raise RuntimeError("Structure expected initial Displacement data")
p.write_data("Structure-Mesh", "Displacement", ids, [[0.0, 0.0]])
init_dt = p.initialize()
if init_dt is not None:
    dt = float(init_dt)
if read_offset_arg == "dt":
    read_offset = dt
records = []
committed = [0.0, 0.0]
saved = committed[:]
attempt = 0
while p.is_coupling_ongoing():
    checkpoint = bool(p.requires_writing_checkpoint())
    if checkpoint:
        saved = committed[:]
    force_at_start = p.read_data("Structure-Mesh", "Force", ids, 0.0).tolist()
    force_at_end = p.read_data("Structure-Mesh", "Force", ids, dt).tolist()
    selected = force_at_start if read_offset_arg == "zero" else force_at_end
    attempt += 1
    trial = [float(attempt), -float(attempt)]
    p.write_data("Structure-Mesh", "Displacement", ids, [trial])
    p.advance(dt)
    rollback = bool(p.requires_reading_checkpoint())
    force_immediately_after_advance_at_start = p.read_data("Structure-Mesh", "Force", ids, 0.0).tolist()
    force_immediately_after_advance_at_end = (
        p.read_data("Structure-Mesh", "Force", ids, dt).tolist() if rollback else None)
    if rollback:
        committed = saved[:]
    else:
        committed = trial[:]
    records.append({"attempt": attempt, "read_offset_s": read_offset,
                    "force_at_relative_0": force_at_start,
                    "force_at_relative_dt": force_at_end,
                    "force_after_advance_relative_0": force_immediately_after_advance_at_start,
                    "force_after_advance_relative_dt": force_immediately_after_advance_at_end,
                    "force_selected_for_fake_solve": selected,
                    "trial_displacement_written": trial,
                    "checkpoint_requested": checkpoint,
                    "rollback_requested": rollback,
                    "committed_fake_state_after_advance": committed[:]})
p.finalize()
print(json.dumps({"role": "Structure", "read_mode": read_offset_arg,
                  "records": records}, sort_keys=True))
'''


def config_text(socket_dir: Path) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<precice-configuration xmlns:data="http://www.precice.org/schemas/data"
  xmlns:m2n="http://www.precice.org/schemas/m2n"
  xmlns:coupling-scheme="http://www.precice.org/schemas/coupling-scheme"
  xmlns:mapping="http://www.precice.org/schemas/mapping">
  <data:vector name="Displacement" waveform-degree="0"/>
  <data:vector name="Force" waveform-degree="0"/>
  <mesh name="Structure-Mesh" dimensions="2"><use-data name="Displacement"/><use-data name="Force"/></mesh>
  <mesh name="Fluid-Mesh" dimensions="2"><use-data name="Displacement"/><use-data name="Force"/></mesh>
  <m2n:sockets acceptor="Structure" connector="Fluid" exchange-directory="{socket_dir}"/>
  <participant name="Structure">
    <provide-mesh name="Structure-Mesh"/><write-data name="Displacement" mesh="Structure-Mesh"/><read-data name="Force" mesh="Structure-Mesh"/>
  </participant>
  <participant name="Fluid">
    <receive-mesh name="Structure-Mesh" from="Structure"/><provide-mesh name="Fluid-Mesh"/>
    <mapping:nearest-neighbor direction="read" from="Structure-Mesh" to="Fluid-Mesh" constraint="consistent"/>
    <mapping:nearest-neighbor direction="write" from="Fluid-Mesh" to="Structure-Mesh" constraint="conservative"/>
    <write-data name="Force" mesh="Fluid-Mesh"/><read-data name="Displacement" mesh="Fluid-Mesh"/>
  </participant>
  <coupling-scheme:parallel-implicit>
    <participants first="Structure" second="Fluid"/>
    <max-time-windows value="1"/><time-window-size value="0.1"/>
    <min-iterations value="2"/><max-iterations value="4"/>
    <absolute-or-relative-convergence-measure data="Force" mesh="Structure-Mesh" abs-limit="1e-12" rel-limit="1e-12"/>
    <exchange data="Displacement" mesh="Structure-Mesh" from="Structure" to="Fluid" initialize="yes" substeps="false"/>
    <exchange data="Force" mesh="Structure-Mesh" from="Fluid" to="Structure" initialize="yes" substeps="false"/>
  </coupling-scheme:parallel-implicit>
</precice-configuration>
'''


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_mode(run_dir: Path, mode: str, validator: str) -> dict:
    scratch = run_dir / f"read-{mode}"
    socket_dir = scratch / "sockets"
    socket_dir.mkdir(parents=True)
    config = scratch / "precice-config.xml"
    config.write_text(config_text(socket_dir), encoding="utf-8")
    structure_script = scratch / "structure_fake.py"
    fluid_script = scratch / "fluid_fake.py"
    structure_script.write_text(STRUCTURE_CODE, encoding="utf-8")
    fluid_script.write_text(FLUID_CODE, encoding="utf-8")
    validation = subprocess.run([validator, str(config)], capture_output=True,
                                text=True, timeout=30, check=False)
    result: dict = {
        "mode": mode,
        "read_offset_s": 0.0 if mode == "zero" else 0.1,
        "configuration_sha256": _sha256(config),
        "configuration_validation": {
            "return_code": validation.returncode,
            "stdout": validation.stdout,
            "stderr": validation.stderr,
        },
        "participant_exit_codes": {},
        "participants": {},
        "participant_logs": {},
    }
    if validation.returncode != 0:
        return result

    env = os.environ.copy()
    processes: dict[str, subprocess.Popen[str]] = {}
    try:
        processes["Structure"] = subprocess.Popen(
            [sys.executable, str(structure_script), str(config), mode], cwd=scratch,
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True)
        processes["Fluid"] = subprocess.Popen(
            [sys.executable, str(fluid_script), str(config)], cwd=scratch,
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True)
        deadline = time.monotonic() + 60.0
        while any(proc.poll() is None for proc in processes.values()) and time.monotonic() < deadline:
            time.sleep(0.05)
        timed_out = any(proc.poll() is None for proc in processes.values())
        if timed_out:
            for proc in processes.values():
                if proc.poll() is None:
                    try:
                        os.killpg(proc.pid, 15)
                    except ProcessLookupError:
                        pass
            for proc in processes.values():
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, 9)
                    except ProcessLookupError:
                        pass
                    proc.wait(timeout=5)
        result["timed_out"] = timed_out
        for role, proc in processes.items():
            stdout, stderr = proc.communicate(timeout=5)
            result["participant_exit_codes"][role] = proc.returncode
            result["participant_logs"][role] = {"stdout": stdout, "stderr": stderr}
            (scratch / f"{role.lower()}.stdout.log").write_text(stdout, encoding="utf-8")
            (scratch / f"{role.lower()}.stderr.log").write_text(stderr, encoding="utf-8")
            records = [line for line in stdout.splitlines() if line.startswith("{")]
            if records:
                try:
                    result["participants"][role] = json.loads(records[-1])
                except json.JSONDecodeError:
                    pass
    except Exception as exc:
        result["harness_error"] = f"{type(exc).__name__}: {exc}"
        for proc in processes.values():
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, 15)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
    return result


def main() -> int:
    validator = shutil.which("precice-config-validate")
    if validator is None:
        raise SystemExit("precice-config-validate not found")
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ") + f"-pid{os.getpid()}"
    run_dir = ROOT / run_id
    run_dir.mkdir(parents=False, exist_ok=False)
    (run_dir / "structure_fake_source.py.txt").write_text(STRUCTURE_CODE, encoding="utf-8")
    (run_dir / "fluid_fake_source.py.txt").write_text(FLUID_CODE, encoding="utf-8")
    results = [_run_mode(run_dir, mode, validator) for mode in ("zero", "dt")]
    identity = subprocess.run(
        [sys.executable, "-c",
         "import importlib.metadata,json,precice,sys; print(json.dumps({'python':sys.executable,'python_version':sys.version,'pyprecice':importlib.metadata.version('pyprecice'),'module':precice.__file__}))"],
        capture_output=True, text=True, check=False)
    report = {
        "classification": "SCRATCH_READ_TIME_TEST_COMPLETED",
        "scope": "two fake pyprecice participants only; no OpenFOAM, HH06, or ANCF worker",
        "preCICE_header": "/usr/include/precice/Participant.hpp",
        "python_identity": identity.stdout.strip(),
        "python_identity_exit_code": identity.returncode,
        "runs": results,
    }
    semantic_checks = {}
    initial_force = [[10.0, -10.0]]
    for run in results:
        mode = run["mode"]
        structure = run.get("participants", {}).get("Structure", {}).get("records", [])
        fluid = run.get("participants", {}).get("Fluid", {}).get("records", [])
        written_force_samples = [item["force_written_before_advance"] for item in fluid]
        expected = ([initial_force] * len(structure) if mode == "zero" else
                    [initial_force] + [[[value[0], value[1]]] for value in written_force_samples[:-1]])
        observed = [item["force_selected_for_fake_solve"] for item in structure]
        semantic_checks[mode] = {
            "all_participants_exit_zero": run.get("participant_exit_codes") == {"Structure": 0, "Fluid": 0},
            "configuration_valid": run.get("configuration_validation", {}).get("return_code") == 0,
            "four_structure_attempts": len(structure) == 4,
            "four_distinct_fluid_force_writes": len(written_force_samples) == 4 and len({tuple(row) for row in written_force_samples}) == 4,
            "rollback_then_accept_sequence": [item.get("rollback_requested") for item in structure] == [True, True, True, False],
            "observed_force_sequence": observed,
            "expected_force_sequence": expected,
            "force_sequence_matches": observed == expected,
            "post_advance_retry_relative_0_is_window_start_force": all(
                item.get("force_after_advance_relative_0") == initial_force
                for item in structure if item["rollback_requested"]),
            "post_advance_accepted_relative_0_is_final_force": [
                item.get("force_after_advance_relative_0") for item in structure if not item["rollback_requested"]
            ] == [[[written_force_samples[-1][0], written_force_samples[-1][1]]]],
            "post_advance_retry_relative_dt_is_same_attempt_fluid_force": [
                item.get("force_after_advance_relative_dt") for item in structure if item["rollback_requested"]
            ] == [[[value[0], value[1]]] for value in written_force_samples[:-1]],
            "post_advance_accepted_attempt_relative_dt_not_read": all(
                item.get("force_after_advance_relative_dt") is None
                for item in structure if not item["rollback_requested"]),
        }
        semantic_checks[mode]["pass"] = all(
            semantic_checks[mode][key] for key in (
                "all_participants_exit_zero", "configuration_valid", "four_structure_attempts",
                "four_distinct_fluid_force_writes", "rollback_then_accept_sequence", "force_sequence_matches",
                "post_advance_retry_relative_0_is_window_start_force",
                "post_advance_accepted_relative_0_is_final_force",
                "post_advance_retry_relative_dt_is_same_attempt_fluid_force",
                "post_advance_accepted_attempt_relative_dt_not_read"))
    report["semantic_checks"] = semantic_checks
    if identity.returncode != 0 or not all(check["pass"] for check in semantic_checks.values()):
        report["classification"] = "SCRATCH_READ_TIME_TEST_FAILED"
    else:
        report["classification"] = "PASS_READ_TIME_CONTRACT"
    report_path = run_dir / "result.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "result": str(report_path),
                      "classification": report["classification"],
                      "participant_exit_codes": [run.get("participant_exit_codes") for run in results]},
                     indent=2))
    return 0 if report["classification"] == "PASS_READ_TIME_CONTRACT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
