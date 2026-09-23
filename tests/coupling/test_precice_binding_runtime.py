from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / "evidence" / "phase1d6_python_precice_binding"
PARTICIPANT_PROBE = r'''
import json
import os
import sys
from pathlib import Path
import numpy as np
import precice

repo = Path(os.environ["PHASE1D6_REPO_ROOT"])
sys.path.insert(0, str(repo / "cases" / "hh06_single_slice"))
import bounded_qualification

role, config = sys.argv[1], sys.argv[2]
if role == "Structure":
    mesh = "Structure-Mesh"
    vertex = [0.5, 0.5]
    initial_data, initial_values = "Displacement", [[0.0, 0.0]]
    received_data = "Force"
    written_data, written_values = "Displacement", [[0.125, -0.25]]
else:
    mesh = "Fluid-Mesh"
    vertex = [0.5, 0.5]
    initial_data, initial_values = "Force", [[3.25, -2.5]]
    received_data = "Displacement"
    written_data, written_values = "Force", [[4.0, -3.0]]

participant = precice.Participant(role, config, 0, 1)
vertex_ids = participant.set_mesh_vertices(mesh, [vertex])
requires_initial = bool(participant.requires_initial_data())
if not requires_initial:
    raise RuntimeError(role + " did not request configured initial data")
participant.write_data(mesh, initial_data, vertex_ids, initial_values)
init_result = participant.initialize()
max_dt = float(init_result if init_result is not None else participant.get_max_time_step_size())
if max_dt < 1.0e-3 - 1.0e-15:
    raise RuntimeError("unexpected initial max timestep: " + repr(max_dt))
received_initial = participant.read_data(mesh, received_data, vertex_ids, 0.0).tolist()
participant.write_data(mesh, written_data, vertex_ids, written_values)
participant.advance(1.0e-3)
ongoing_after_advance = bool(participant.is_coupling_ongoing())
participant.finalize()
print(json.dumps({
    "role": role,
    "requires_initial_data": requires_initial,
    "initial_data_written": initial_data,
    "initial_received_data": received_initial,
    "step_data_written": written_data,
    "step_values_written": written_values,
    "max_timestep_s": max_dt,
    "advance_completed": True,
    "coupling_ongoing_after_one_window": ongoing_after_advance,
    "events": ["Participant", "set_mesh_vertices", "requires_initial_data", "write_initial_data", "initialize", "read_initial_data_relative_0", "write_data", "advance", "finalize"],
    "runtime_identity": bounded_qualification.binding_runtime_identity(),
}, sort_keys=True))
'''


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _config(socket_dir: Path) -> str:
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
    <provide-mesh name="Structure-Mesh"/>
    <write-data name="Displacement" mesh="Structure-Mesh"/>
    <read-data name="Force" mesh="Structure-Mesh"/>
  </participant>
  <participant name="Fluid">
    <receive-mesh name="Structure-Mesh" from="Structure"/>
    <provide-mesh name="Fluid-Mesh"/>
    <mapping:nearest-neighbor direction="read" from="Structure-Mesh" to="Fluid-Mesh" constraint="consistent"/>
    <mapping:nearest-neighbor direction="write" from="Fluid-Mesh" to="Structure-Mesh" constraint="conservative"/>
    <write-data name="Force" mesh="Fluid-Mesh"/>
    <read-data name="Displacement" mesh="Fluid-Mesh"/>
  </participant>
  <coupling-scheme:parallel-explicit>
    <participants first="Structure" second="Fluid"/>
    <max-time-windows value="1"/>
    <time-window-size value="0.001"/>
    <exchange data="Displacement" mesh="Structure-Mesh" from="Structure" to="Fluid" initialize="yes" substeps="false"/>
    <exchange data="Force" mesh="Structure-Mesh" from="Fluid" to="Structure" initialize="yes" substeps="false"/>
  </coupling-scheme:parallel-explicit>
</precice-configuration>
'''


class PythonPreciceBindingRuntimeTests(unittest.TestCase):
    def test_exact_python_binding_runtime_with_two_scratch_participants(self) -> None:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        report_path = EVIDENCE_DIR / "qualification.json"
        with tempfile.TemporaryDirectory(prefix="phase1d6-precice-binding-") as scratch_name:
            scratch = Path(scratch_name)
            socket_dir = scratch / "sockets"
            socket_dir.mkdir()
            config_text = _config(socket_dir)
            config_path = scratch / "precice-config.xml"
            config_path.write_text(config_text, encoding="utf-8")
            validator = shutil_which("precice-config-validate")
            self.assertIsNotNone(validator, "precice-config-validate is unavailable")
            validation = subprocess.run([validator, str(config_path)], capture_output=True, text=True, timeout=30, check=False)

            base_report = {
                "phase": "1D.6",
                "classification": "PYTHON_PRECICE_BINDING_RUNTIME_UNRESOLVED",
                "scope": "isolated two-participant preCICE binding/runtime ABI qualification; no OpenFOAM, ANCF worker, or HH06 case",
                "python_executable": str(Path(sys.executable).resolve()),
                "python_version": sys.version,
                "pyprecice_metadata_version": package_version(),
                "initial_force_seed": {
                    "kind": "SYNTHETIC_OFFLINE_BINDING_PROBE_ONLY",
                    "fluid_vector": [3.25, -2.5],
                    "is_hh06_release_force": False,
                },
                "configuration_sha256": _sha(config_text),
                "configuration_text": config_text,
                "configuration_validation": {
                    "command": [validator, str(config_path)],
                    "return_code": validation.returncode,
                    "stdout": validation.stdout,
                    "stderr": validation.stderr,
                },
                "participants": {},
                "participant_exit_codes": {},
                "runtime_identity": None,
                "scratch_directory": str(scratch),
            }
            if validation.returncode != 0:
                report_path.write_text(json.dumps(base_report, indent=2) + "\n", encoding="utf-8")
                self.fail("scratch preCICE config validation failed; see " + str(report_path))

            env = os.environ.copy()
            env["PHASE1D6_REPO_ROOT"] = str(REPO_ROOT)
            processes: dict[str, subprocess.Popen[str]] = {}
            outputs: dict[str, tuple[str, str]] = {}
            try:
                for role in ("Structure", "Fluid"):
                    processes[role] = subprocess.Popen(
                        [sys.executable, "-c", PARTICIPANT_PROBE, role, str(config_path)],
                        cwd=scratch, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, start_new_session=True,
                    )
                deadline = time.monotonic() + 90.0
                while any(proc.poll() is None for proc in processes.values()) and time.monotonic() < deadline:
                    time.sleep(0.05)
                if any(proc.poll() is None for proc in processes.values()):
                    for proc in processes.values():
                        if proc.poll() is None:
                            try:
                                os.killpg(proc.pid, signal.SIGTERM)
                            except ProcessLookupError:
                                pass
                    for proc in processes.values():
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            try:
                                os.killpg(proc.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            proc.wait(timeout=5)
                for role, proc in processes.items():
                    stdout, stderr = proc.communicate(timeout=5)
                    outputs[role] = (stdout, stderr)
                    base_report["participant_exit_codes"][role] = proc.returncode
                    records = [line for line in stdout.splitlines() if line.startswith("{")]
                    if records:
                        try:
                            base_report["participants"][role] = json.loads(records[-1])
                        except json.JSONDecodeError:
                            pass
                base_report["participant_logs"] = {
                    role: {"stdout": values[0], "stderr": values[1]} for role, values in outputs.items()
                }
                identities = [base_report["participants"].get(role, {}).get("runtime_identity") for role in ("Fluid", "Structure")]
                if identities[0] is not None and identities[0] == identities[1]:
                    base_report["runtime_identity"] = identities[0]
                successful = (
                    set(base_report["participants"]) == {"Fluid", "Structure"}
                    and base_report["participant_exit_codes"] == {"Structure": 0, "Fluid": 0}
                    and base_report["participants"]["Structure"]["initial_received_data"] == [[3.25, -2.5]]
                    and base_report["participants"]["Fluid"]["initial_received_data"] == [[0.0, 0.0]]
                    and base_report["runtime_identity"] is not None
                    and base_report["runtime_identity"]["pyprecice_metadata_version"] == "3.4.0"
                    and base_report["runtime_identity"]["libprecice_runtime_version"] == "3.4.1"
                    and base_report["participants"]["Structure"]["advance_completed"] is True
                    and base_report["participants"]["Fluid"]["advance_completed"] is True
                )
                if successful:
                    base_report["classification"] = "PYTHON_PRECICE_BINDING_RUNTIME_CONFIRMED"
            except Exception as exc:
                base_report["harness_error"] = f"{type(exc).__name__}: {exc}"
                for proc in processes.values():
                    if proc.poll() is None:
                        try:
                            os.killpg(proc.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            pass
            report_path.write_text(json.dumps(base_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        self.assertEqual(base_report["classification"], "PYTHON_PRECICE_BINDING_RUNTIME_CONFIRMED",
                         f"Python/preCICE runtime qualification failed; see {report_path}")
        self.assertEqual(base_report["participant_exit_codes"], {"Structure": 0, "Fluid": 0})
        self.assertEqual(base_report["participants"]["Structure"]["initial_received_data"], [[3.25, -2.5]])
        self.assertEqual(base_report["participants"]["Fluid"]["initial_received_data"], [[0.0, 0.0]])


def shutil_which(command: str) -> str | None:
    import shutil
    return shutil.which(command)


def package_version() -> str:
    from importlib import metadata
    return metadata.version("pyprecice")


if __name__ == "__main__":
    unittest.main()
