#!/usr/bin/env python3
"""Phase 1K.24 isolated Fluid-state rollback/replay diagnostics.

This runner never edits the authoritative case.  It copies only the frozen
30.0 s K22 case into a new evidence run directory, loads the separately named
Phase 1K.24 diagnostic adapter, and records process/runtime identities.
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
BASE = ROOT / "evidence/phase1k24_fluid_state_repeatability/run-20260925T074500Z-d3890de"
SOURCE_30 = BASE / "source_30"
SOURCE_CONSTANT = BASE / "source_constant"
SOURCE_SYSTEM = BASE / "source_system"
SOURCE_XML = BASE / "source_precice-config.xml"
SOURCE_CONTRACT = BASE / "source_contract.json"
FAKE_STRUCTURE = ROOT / "scripts/phase1k23_fixed_displacement_structure.py"
ADAPTER = BASE / "adapter-build/libpreciceAdapterPhase1K24StateDiag.so"
RBF = ROOT / "evidence/phase1k20_point_checkpoint/run-20260924T164027Z-c2245ff-Gu2Hg5/build/libRBFMeshMotionSolverPhase1K187BStopDiag.so"
WORKER = ROOT / "build/phase1d6_worker/cfd_ancf_ancf_kernel_worker"
K22_RBF = "/home/machao/projects/CFD_ANCF_VIV_V2/evidence/phase1k20_point_checkpoint/run-20260924T164027Z-c2245ff-Gu2Hg5/build/libRBFMeshMotionSolverPhase1K187BStopDiag.so"
OLD_ADAPTER = "/home/machao/projects/CFD_ANCF_VIV_V2/evidence/phase1k20_point_checkpoint/run-20260924T164027Z-c2245ff-Gu2Hg5/build/libpreciceAdapterPhase1K20.so"

DSTAR = [1.0633832164606064e-07, 9.530777190012017e-08]
EXPECTED_WORKER = "3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596"
EXPECTED_RBF = "508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11"
EXPECTED_DT = 0.0002


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("PHASE1K24_PREFLIGHT_FAIL: " + message)


def copy_case(run: Path) -> Path:
    require(not run.exists() or not any(run.iterdir()), f"run directory is not empty: {run}")
    run.mkdir(parents=True, exist_ok=True)
    case = run / "case"
    case.mkdir()
    for name, source in (("30", SOURCE_30), ("constant", SOURCE_CONSTANT), ("system", SOURCE_SYSTEM)):
        shutil.copytree(source, case / name)
    shutil.copy2(SOURCE_XML, case / "precice-config.xml")
    shutil.copy2(SOURCE_CONTRACT, case / "contract.json")
    for artifact in ("controlDict",):
        # controlDict is part of the frozen system directory, but retaining
        # this assertion makes accidental incomplete copies fail closed.
        require((case / "system" / artifact).is_file(), f"missing case artifact: {artifact}")
    shutil.copy2(FAKE_STRUCTURE, run / "fixed_structure.py")
    return case


def patch_case(case: Path, run: Path, max_iterations: int, min_iterations: int) -> None:
    xml_path = case / "precice-config.xml"
    xml = xml_path.read_text(encoding="utf-8")
    require(xml.count('<max-time-windows value="5"/>') == 1, "unexpected max-time-windows source")
    require(xml.count('<max-iterations value="20"/>') == 1, "unexpected max-iterations source")
    require(xml.count('<min-iterations value="2"/>') == 1, "unexpected min-iterations source")
    require(xml.count('exchange-directory="') == 1, "unexpected exchange-directory count")
    xml = xml.replace('<max-time-windows value="5"/>', '<max-time-windows value="1"/>')
    xml = xml.replace('<max-iterations value="20"/>', f'<max-iterations value="{max_iterations}"/>')
    xml = xml.replace('<min-iterations value="2"/>', f'<min-iterations value="{min_iterations}"/>')
    xml = re.sub(r'exchange-directory="[^"]+"', f'exchange-directory="{run / "precice-sockets"}"', xml, count=1)
    xml_path.write_text(xml, encoding="utf-8")

    control_path = case / "system/controlDict"
    control = control_path.read_text(encoding="utf-8")
    require(OLD_ADAPTER in control, "frozen adapter path not found in controlDict")
    control_path.write_text(control.replace(OLD_ADAPTER, str(ADAPTER)), encoding="utf-8")

    dynamic_path = case / "constant/dynamicMeshDict"
    dynamic = dynamic_path.read_text(encoding="utf-8")
    require(K22_RBF in dynamic, "frozen RBF path not found in dynamicMeshDict")
    dynamic_path.write_text(dynamic.replace(K22_RBF, str(RBF)), encoding="utf-8")

    contract = json.loads((case / "contract.json").read_text(encoding="utf-8"))
    contract["coupling"]["max_iterations"] = max_iterations
    (case / "contract.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")


def record_identity(run: Path, case: Path, mode: str, max_iterations: int, min_iterations: int) -> dict:
    time_text = (case / "30/uniform/time").read_text(encoding="utf-8")
    match = re.search(r"^\s*value\s+([-+0-9.eE]+)\s*;", time_text, re.MULTILINE)
    require(match is not None and float(match.group(1)) == 30.0, "restart is not exactly 30.0 s")
    required = (
        "30/uniform/time", "30/U", "30/p", "30/k", "30/omega", "30/nut",
        "30/pointDisplacement", "constant/polyMesh/points", "constant/polyMesh/faces",
        "constant/polyMesh/owner", "constant/polyMesh/neighbour", "constant/polyMesh/boundary",
    )
    for relative in required:
        require((case / relative).is_file(), f"missing restart input {relative}")
        require(sha(case / relative) == sha({
            "30/uniform/time": SOURCE_30 / "uniform/time", "30/U": SOURCE_30 / "U",
            "30/p": SOURCE_30 / "p", "30/k": SOURCE_30 / "k", "30/omega": SOURCE_30 / "omega",
            "30/nut": SOURCE_30 / "nut", "30/pointDisplacement": SOURCE_30 / "pointDisplacement",
            "constant/polyMesh/points": SOURCE_CONSTANT / "polyMesh/points",
            "constant/polyMesh/faces": SOURCE_CONSTANT / "polyMesh/faces",
            "constant/polyMesh/owner": SOURCE_CONSTANT / "polyMesh/owner",
            "constant/polyMesh/neighbour": SOURCE_CONSTANT / "polyMesh/neighbour",
            "constant/polyMesh/boundary": SOURCE_CONSTANT / "polyMesh/boundary",
        }[relative]), f"restart hash changed: {relative}")
    for path, expected, label in ((ADAPTER, None, "adapter"), (RBF, EXPECTED_RBF, "RBF"), (WORKER, EXPECTED_WORKER, "worker")):
        require(path.is_file(), f"missing {label}: {path}")
        if expected is not None:
            require(sha(path) == expected, f"{label} SHA mismatch")
    identity = {
        "mode": mode,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "openfoam_bashrc": "/opt/openfoam10/etc/bashrc",
        "python_executable": "/usr/bin/python3.10",
        "precice_runtime_expected": "3.4.1",
        "pyprecice_metadata_expected": "3.4.0",
        "restart_global_time_s": 30.0,
        "dt_s": EXPECTED_DT,
        "max_time_windows": 1,
        "max_iterations": max_iterations,
        "min_iterations": min_iterations,
        "d_star_m": DSTAR,
        "adapter_path": str(ADAPTER), "adapter_sha256": sha(ADAPTER),
        "rbf_path": str(RBF), "rbf_sha256": sha(RBF),
        "worker_path": str(WORKER), "worker_sha256": sha(WORKER),
        "worker_source_sha256": "c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e",
        "qualified_historical_adapter_used": False,
        "experimental_adapter_source_provenance_resolved": False,
        "restart_field_hashes": {relative: sha(case / relative) for relative in required},
        "configuration_hashes": {relative: sha(case / relative) for relative in (
            "system/fvSolution", "system/fvSchemes", "system/controlDict",
            "constant/dynamicMeshDict", "system/preciceDict", "precice-config.xml", "contract.json",
        )},
    }
    (run / "runtime_identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    (run / "restart_identity.json").write_text(json.dumps({
        "source": str(BASE / "source_30"), "global_time_s": 30.0,
        "field_hashes": identity["restart_field_hashes"],
        "mesh_hashes": {relative: identity["restart_field_hashes"][relative] for relative in required if "polyMesh" in relative},
    }, indent=2) + "\n", encoding="utf-8")
    return identity


def validate(run: Path, case: Path) -> None:
    result = subprocess.run(["precice-config-validate", str(case / "precice-config.xml")], capture_output=True, text=True, timeout=60)
    (run / "precice_config_validate.stdout").write_text(result.stdout, encoding="utf-8")
    (run / "precice_config_validate.stderr").write_text(result.stderr, encoding="utf-8")
    require(result.returncode == 0, "preCICE XML validation failed")


def launch(run: Path, case: Path) -> dict:
    (run / "precice-sockets").mkdir()
    (run / "diagnostics").mkdir()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PHASE1K24_DIAG_DIR"] = str(run / "diagnostics")
    env["PHASE1K18_DIAG_DIR"] = str(run / "rbf_diagnostics")
    (run / "rbf_diagnostics").mkdir()
    fluid_cmd = [
        "/bin/bash", "-c",
        "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; cd \"$1\" || exit 91; test \"$(pwd -P)\" = \"$(realpath \"$1\")\" || exit 92; printf 'PHASE1K24_FLUID_PWD=%s\\n' \"$(pwd -P)\"; exec pimpleFoam -case .",
        "phase1k24-fluid", str(case),
    ]
    structure_cmd = ["/usr/bin/python3.10", str(run / "fixed_structure.py"), str(case / "precice-config.xml"), str(run / "fixed_structure_result.json"), str(DSTAR[0]), str(DSTAR[1])]
    processes = {}
    handles = []
    for role, command in (("fluid", fluid_cmd), ("structure", structure_cmd)):
        stdout = (run / f"{role}.stdout").open("x")
        stderr = (run / f"{role}.stderr").open("x")
        handles.extend((stdout, stderr))
        processes[role] = subprocess.Popen(command, cwd=case, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
    loaded = set()
    start = time.monotonic()
    reason = None
    deadline = start + 900
    try:
        while any(proc.poll() is None for proc in processes.values()):
            maps = Path(f"/proc/{processes['fluid'].pid}/maps")
            if maps.exists():
                for line in maps.read_text(encoding="utf-8", errors="replace").splitlines():
                    if "libpreciceAdapter" in line or "libRBFMeshMotionSolver" in line or "libprecice.so" in line:
                        loaded.add(line.split()[-1])
            if time.monotonic() > deadline:
                reason = "900-second hard timeout"
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
    cleanup = {
        "fluid_command": fluid_cmd, "structure_command": structure_cmd,
        "fluid_pid": processes["fluid"].pid, "structure_pid": processes["structure"].pid,
        "exit_codes": {role: proc.returncode for role, proc in processes.items()},
        "loaded_libraries_observed": sorted(loaded), "stop_reason": reason,
        "wall_duration_s": time.monotonic() - start, "working_directory": str(case),
    }
    (run / "process_cleanup.json").write_text(json.dumps(cleanup, indent=2) + "\n", encoding="utf-8")
    return cleanup


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in ("same-process", "fresh-process-a", "fresh-process-b"):
        raise SystemExit("usage: phase1k24_fluid_state_replay.py MODE RUN_DIR")
    mode = sys.argv[1]
    run = Path(sys.argv[2]).expanduser().resolve()
    max_iterations, min_iterations = (4, 2) if mode == "same-process" else (1, 1)
    case = copy_case(run)
    patch_case(case, run, max_iterations, min_iterations)
    identity = record_identity(run, case, mode, max_iterations, min_iterations)
    validate(run, case)
    (run / "preflight_status.json").write_text(json.dumps({"status": "PASS_PREFLIGHT_ONLY", "identity": identity}, indent=2) + "\n", encoding="utf-8")
    cleanup = launch(run, case)
    require(cleanup["stop_reason"] is None, "runtime stopped before clean completion")
    require(all(code == 0 for code in cleanup["exit_codes"].values()), "runtime participant failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
