#!/usr/bin/python3.10
"""Fail-closed one-retry localization from the preserved nonzero 1K.7A state."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


RUN = Path(__file__).resolve().parent
REPO = RUN.parents[2]
CASE = RUN / "case"
DIAG = RUN / "diagnostics"
STATE = RUN / "ancf_accepted_state.json"
MANIFEST = RUN / "accepted_cfd_state_manifest.json"
PARTICIPANT = RUN / "participant_restart.py"
WORKER = REPO / "build/phase1d6_worker/cfd_ancf_ancf_kernel_worker"
ADAPTER = RUN / "build/libpreciceAdapterPhase1K18Diag.so"
RBF = RUN / "build/libRBFMeshMotionSolverPhase1K187BStopDiag.so"
PHASE17_ADAPTER = REPO / "evidence/phase1k17_adapter/lib/libpreciceAdapterPhase1K17.so"
QUALIFIED_ADAPTER = Path("/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so")
QUALIFIED_RBF = Path("/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libRBFMeshMotionSolver.so")
PRECICE_LIB = Path("/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1")
TIMEOUT_S = 90

EXPECTED = {
    "head": "c2245ff396ff42dfa5e80fee6555a9ede93e3b04",
    "worker": "3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596",
    "phase17_adapter": "1bc5cf6a1ea481082b01b903d317313be01212413c8bf2718481fa43c485c495",
    "diag_adapter": "cab6f4bffcc71ea24f296ece6c67ec9f1c6011e7139b39f2af62d2145422f71e",
    "diag_adapter_build_id": "f17adc69bf9540ce23982d09165628fff2ce8c03",
    "qualified_adapter": "26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572",
    "qualified_rbf": "b27b347c4ba3026a495517ae7ae237ceb5cd8408ac0db9af6a58ccd83647a20c",
    "precice": "b20729622d2dbbafdea3d6ead0480ec66be98cb947db3500cc3c27ed4e3039c7",
    "state": "fae2cedc42186475a27ee01e48deced15580d8d3537c4aa32ec02b0d28cc747c",
    "endpoint": "30.0002",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha_json(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def source_tree_sha(root: Path) -> tuple[str, list[str]]:
    files = [p for p in root.rglob("*") if p.is_file() and "lnInclude" not in p.parts
             and "linux64GccDPInt32Opt" not in p.parts
             and (p.suffix in {".C", ".H"} or p.name in {"files", "options"})]
    records = []
    for path in sorted(files):
        records.append((path.relative_to(root).as_posix(), sha(path)))
    h = hashlib.sha256()
    for name, digest in records:
        h.update(name.encode("utf-8")); h.update(bytes.fromhex(digest))
    return h.hexdigest(), [name for name, _ in records]


def run_capture(command: list[str], *, cwd: Path, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout, check=False)


def json_write(path: Path, value: object, *, exclusive: bool = True) -> None:
    with path.open("x" if exclusive else "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def foam_time(path: Path) -> float:
    match = re.search(r"^\s*value\s+([-+0-9.eE]+)\s*;", path.read_text(), re.MULTILINE)
    if not match:
        raise RuntimeError(f"cannot parse OpenFOAM time file: {path}")
    return float(match.group(1))


def build_id(path: Path) -> str:
    result = run_capture(["readelf", "-n", str(path)], cwd=RUN)
    match = re.search(r"Build ID:\s*([0-9a-fA-F]+)", result.stdout)
    if result.returncode or not match:
        raise RuntimeError(f"cannot identify ELF Build ID: {path}")
    return match.group(1).lower()


def endpoint_fields() -> dict[str, str]:
    document = json.loads(MANIFEST.read_text())
    # Phase 1K.7A manifest stores the endpoint digest map at the root.
    expected = document["file_sha256"]
    endpoint = CASE / EXPECTED["endpoint"]
    observed = {}
    for relative, digest in expected.items():
        path = endpoint / relative
        if not path.is_file() or sha(path) != digest:
            raise RuntimeError(f"accepted CFD endpoint field/hash mismatch: {path}")
        observed[relative] = digest
    return observed


def parse_force_record() -> dict[str, object]:
    path = RUN / "force_eval/case/postProcessing/cylinderForces/30.0002/forces.dat"
    records = [line.strip() for line in path.read_text().splitlines()
               if line.strip() and not line.lstrip().startswith("#")]
    matching = [line for line in records if re.match(r"^30\.0002\s", line)]
    if len(matching) != 1:
        raise RuntimeError(f"expected one forces record at 30.0002 s; found {len(matching)}")
    numbers = [float(value) for value in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", matching[0])]
    if len(numbers) < 7 or abs(numbers[0] - 30.0002) > 1.0e-12:
        raise RuntimeError("cannot parse pressure/viscous force vectors from the 30.0002 s record")
    pressure, viscous = numbers[1:4], numbers[4:7]
    total = [pressure[i] + viscous[i] for i in range(3)]
    return {"source": str(path), "source_sha256": sha(path), "record": matching[0],
            "pressure_N": pressure, "viscous_N": viscous, "total_N": total,
            "evaluation_command": "pimpleFoam -postProcess -case <isolated-force-eval-case> -time 30.0002",
            "time_advanced": False}


def process_executable_matches(names: set[str]) -> list[dict[str, object]]:
    found = []
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            exe = Path(os.readlink(entry / "exe"))
            if exe.name in names:
                found.append({"pid": int(entry.name), "exe": str(exe)})
        except (OSError, ValueError):
            continue
    return found


def preflight() -> dict[str, object]:
    if not (REPO / ".git").exists() or not CASE.is_dir():
        raise RuntimeError("repository or isolated scratch case missing")
    head = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()
    branch = subprocess.check_output(["git", "-C", str(REPO), "branch", "--show-current"], text=True).strip()
    if head != EXPECTED["head"] or branch != "repair/worker-lineage-implicit-contract-v1":
        raise RuntimeError(f"unexpected Git identity: {branch} {head}")
    for args in (("diff", "--quiet"), ("diff", "--cached", "--quiet")):
        if subprocess.run(["git", "-C", str(REPO), *args]).returncode:
            raise RuntimeError("tracked/index changes found; refusing diagnostic runtime")

    for path in (STATE, MANIFEST, PARTICIPANT, WORKER, ADAPTER, RBF, PHASE17_ADAPTER,
                 QUALIFIED_ADAPTER, QUALIFIED_RBF, PRECICE_LIB):
        if not path.is_file():
            raise RuntimeError(f"required provenance/runtime file missing: {path}")
    if sha(STATE) != EXPECTED["state"]:
        raise RuntimeError("preserved ANCF state snapshot hash mismatch")
    if sha(WORKER) != EXPECTED["worker"] or not os.access(WORKER, os.X_OK):
        raise RuntimeError("qualified worker binary identity mismatch")
    if sha(PHASE17_ADAPTER) != EXPECTED["phase17_adapter"]:
        raise RuntimeError("Phase 1K.17 base experimental adapter identity mismatch")
    if sha(ADAPTER) != EXPECTED["diag_adapter"] or build_id(ADAPTER) != EXPECTED["diag_adapter_build_id"]:
        raise RuntimeError("diagnostic adapter identity mismatch")
    if sha(QUALIFIED_ADAPTER) != EXPECTED["qualified_adapter"] or sha(QUALIFIED_RBF) != EXPECTED["qualified_rbf"]:
        raise RuntimeError("qualified historical adapter/RBF identity changed")
    if sha(PRECICE_LIB) != EXPECTED["precice"]:
        raise RuntimeError("preCICE 3.4.1 runtime identity mismatch")
    if sha(RBF) == "" or not build_id(RBF):
        raise RuntimeError("experimental diagnostic RBF identity missing")

    state = json.loads(STATE.read_text())
    accepted = state["accepted_state"]
    checkpoint = state["physical_checkpoint"]
    if state.get("schema") != "PHASE1K18_7A_ACCEPTED_ANCF_STATE_V1" or state.get("checkpoint_active_after_commit") is not False:
        raise RuntimeError("unexpected accepted-state/checkpoint schema")
    if state["physical_identity"].get("accepted_global_time_s") != 30.0002:
        raise RuntimeError("accepted ANCF checkpoint is not at global time 30.0002 s")
    if len(accepted["q"]) != 198 or len(accepted["qdot"]) != 198 or len(accepted["qddot"]) != 198:
        raise RuntimeError("accepted ANCF state is not the expected 198-DOF state")
    if any(accepted[name + "_sha256"] != hashlib.sha256(__import__("struct").pack("<" + "d" * len(accepted[name]), *accepted[name])).hexdigest()
           for name in ("q", "qdot", "qddot")):
        raise RuntimeError("accepted q/qdot/qddot contents fail their embedded hashes")
    if checkpoint["checkpoint_id"] != "hh06-window-1" or checkpoint["sha256"] != "5901032d3f4f01250ffe79346f1979ca5b8161bcefa59607975c2fd7c049a0b5":
        raise RuntimeError("accepted-state physical checkpoint metadata identity mismatch")

    numeric_dirs = sorted((float(p.name), p.name) for p in CASE.iterdir() if p.is_dir() and re.fullmatch(r"\d+(?:\.\d+)?", p.name))
    if numeric_dirs != [(30.0, "30"), (30.0002, "30.0002")]:
        raise RuntimeError(f"scratch must contain only 30.0 and 30.0002 restart times: {numeric_dirs}")
    if foam_time(CASE / "30.0002/uniform/time") != 30.0002:
        raise RuntimeError("scratch CFD endpoint time is not exactly 30.0002 s")
    field_hashes = endpoint_fields()
    if sha(CASE / EXPECTED["endpoint"] / "polyMesh/points") != field_hashes["polyMesh/points"]:
        raise RuntimeError("accepted time-directory mesh points do not match endpoint identity")
    motion_fields = (CASE / "30.0002/pointDisplacement", CASE / "30.0002/cellDisplacement")
    if any(not path.is_file() for path in motion_fields):
        raise RuntimeError("accepted nonzero point/cell displacement snapshot is incomplete")

    contract = json.loads((CASE / "contract.json").read_text())
    restart = contract["phase1k18_7b_restart"]
    if (restart.get("accepted_window_count") != 1 or restart.get("global_time_s") != 30.0002
            or restart.get("time_origin_global_s") != 30.0
            or restart.get("ancf_state_sha256") != sha(STATE)):
        raise RuntimeError("scratch restart metadata does not bind to the preserved accepted state")
    force = parse_force_record()
    expected_force = restart["force_seed_raw_N"]
    force_tolerance = float(restart["force_tolerance_N"])
    if any(abs(force["total_N"][i] - expected_force[i]) > force_tolerance for i in range(3)):
        raise RuntimeError("scratch restart Force seed differs from isolated postProcess result beyond its recorded tolerance")
    if not 0.0 < force_tolerance <= 2.0e-10:
        raise RuntimeError("restart-force comparison tolerance is not the documented printed-precision bound")

    xml_path = CASE / "precice-config.xml"
    root = ET.parse(xml_path).getroot()
    tags = [e for e in root.iter() if e.tag.split("}")[-1] in {"max-time-windows", "max-iterations", "min-iterations", "time-window-size"}]
    values = {e.tag.split("}")[-1]: e.attrib.get("value") for e in tags}
    if values != {"max-time-windows": "1", "time-window-size": "0.0002", "min-iterations": "2", "max-iterations": "2"}:
        raise RuntimeError(f"preCICE retry bound differs from exact one-retry profile: {values}")
    exchanges = [e.attrib for e in root.iter() if e.tag.split("}")[-1] == "exchange"]
    if not any(x.get("data") == "Force" and x.get("from") == "Fluid_0000" and x.get("to") == "Structure_0000" and x.get("initialize") == "yes" for x in exchanges):
        raise RuntimeError("scratch Force initial-data exchange is not enabled")
    socket_match = re.search(r'exchange-directory="([^"]+)"', xml_path.read_text())
    socket_dir = Path(socket_match.group(1)).resolve() if socket_match else None
    if socket_dir != (RUN / "precice-sockets").resolve() or socket_dir.exists() and any(socket_dir.iterdir()):
        raise RuntimeError("preCICE socket path is not the unique empty Phase 1K.18.7B directory")
    dynamic = (CASE / "constant/dynamicMeshDict").read_text()
    control = (CASE / "system/controlDict").read_text()
    if str(RBF) not in dynamic or str(ADAPTER) not in control:
        raise RuntimeError("scratch case does not reference the pinned diagnostic libraries")
    if not re.search(r"^startFrom\s+latestTime\s*;", control, re.M) or not re.search(r"^endTime\s+30\.0004\s*;", control, re.M) or not re.search(r"^deltaT\s+2e-4\s*;", control, re.M):
        raise RuntimeError("OpenFOAM restart/endTime/deltaT contract mismatch")

    active = process_executable_matches({"pimpleFoam", "cfd_ancf_ancf_kernel_worker"})
    if active:
        raise RuntimeError(f"stale solver/worker process exists before run: {active}")
    if any((RUN / name).exists() for name in ("runtime_identity.json", "launch_started.json", "fluid.stdout", "structure.stdout", "process_cleanup.json", "diagnostic_summary.json")):
        raise RuntimeError("run output already exists; refusing overwrite/reuse")
    if any(DIAG.iterdir()):
        raise RuntimeError("diagnostic snapshot directory is not empty")

    validate = run_capture(["precice-config-validate", str(xml_path)], cwd=CASE)
    if validate.returncode or "No major issues detected" not in validate.stdout:
        raise RuntimeError("preCICE XML validation failed: " + validate.stdout)
    audit = run_capture(["/usr/bin/python3.10", str(PARTICIPANT), "--case", str(CASE), "--audit-only"], cwd=CASE)
    if audit.returncode or '"status": "PASS"' not in audit.stdout:
        raise RuntimeError("diagnostic participant audit failed: " + audit.stdout)
    foam = run_capture(["bash", "-c", "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; foamVersion"], cwd=CASE)
    if foam.returncode or "OpenFOAM-10" not in foam.stdout:
        raise RuntimeError("OpenFOAM-10 preflight failed")
    pimple = run_capture(["bash", "-c", "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; command -v pimpleFoam"], cwd=CASE)
    if pimple.returncode:
        raise RuntimeError("pimpleFoam is unavailable")
    binding_cmd = ["/usr/bin/python3.10", "-c", "import importlib.metadata as m,pathlib,precice,sys; print(sys.version.split()[0]); print(m.version('pyprecice')); print(precice.__file__); print('\\n'.join(sorted(set(x.split()[-1] for x in pathlib.Path('/proc/self/maps').read_text().splitlines() if 'libprecice' in x))))"]
    binding = run_capture(binding_cmd, cwd=CASE)
    if binding.returncode or "/libprecice.so.3.4.1" not in binding.stdout:
        raise RuntimeError("Python/preCICE binding does not load 3.4.1")
    build_log = (RUN / "rbf_build.log").read_text(errors="replace")
    if "-std=c++14" not in build_log or "-I/home/machao/projects/CFD_ANCF_VIV_V2/evidence/phase1k13b_rbf_diag/build-20260924T105315Z-c2245ff/eigen/usr/include/eigen3" not in build_log:
        raise RuntimeError("clean RBF build did not use the recorded compiler/Eigen include")
    source_hash, source_files = source_tree_sha(RUN / "rbf-source")
    return {
        "git": {"branch": branch, "head": head, "tracked_and_index_clean": True},
        "restart": {"case": str(CASE), "global_time_s": 30.0002, "field_sha256": field_hashes,
                    "ancf_state_sha256": sha(STATE), "checkpoint_id": checkpoint["checkpoint_id"],
                    "checkpoint_sha256": checkpoint["sha256"]},
        "force_seed": force,
        "software": {"openfoam": foam.stdout.strip(), "pimpleFoam": pimple.stdout.strip(),
                     "preCICE_validation": validate.stdout.strip(), "preCICE_sha256": sha(PRECICE_LIB),
                     "python_binding_output": binding.stdout.strip(), "gxx": run_capture(["g++", "--version"], cwd=RUN).stdout.splitlines()[0]},
        "worker": {"path": str(WORKER), "sha256": sha(WORKER)},
        "adapter": {"base_phase1k17_sha256": sha(PHASE17_ADAPTER), "diagnostic_sha256": sha(ADAPTER),
                    "diagnostic_build_id": build_id(ADAPTER), "qualified_adapter_not_loaded_sha256": sha(QUALIFIED_ADAPTER)},
        "rbf": {"diagnostic_path": str(RBF), "sha256": sha(RBF), "build_id": build_id(RBF),
                "source_tree_sha256": source_hash, "source_files": source_files,
                "qualified_rbf_not_loaded_sha256": sha(QUALIFIED_RBF),
                "build_command": "source /opt/openfoam10/etc/bashrc; EIGEN3_INCLUDE_DIR=<preserved Phase1K.13B Eigen 3.4.0 headers>; FOAM_USER_LIBBIN=<run>/build; wclean .; wmake libso ."},
        "participant_restart_variant": {"path": str(PARTICIPANT), "sha256": sha(PARTICIPANT)},
        "preCICE_profile": {"max_time_windows": 1, "max_iterations": 2, "min_iterations": 2,
                             "time_window_size_s": 0.0002, "iqn_ils": "unchanged Phase 1K profile"},
        "socket_directory": str(socket_dir),
        "scope": "one physical window from accepted window-1 state; exactly one retry; controlled stop at first retry S5; no acceptance of next window",
    }


def process_maps(pid: int) -> list[str]:
    path = Path(f"/proc/{pid}/maps")
    if not path.exists():
        return []
    return [line for line in path.read_text(errors="replace").splitlines()
            if any(token in line for token in ("libprecice.so", "libpreciceAdapterPhase1K18Diag", "libRBFMeshMotionSolverPhase1K187BStopDiag", "cfd_ancf_ancf_kernel_worker"))]


def descendants(pid: int) -> list[int]:
    found, pending = [], [pid]
    while pending:
        current = pending.pop()
        path = Path(f"/proc/{current}/task/{current}/children")
        if not path.exists():
            continue
        try:
            children = [int(item) for item in path.read_text().split()]
        except (OSError, ValueError):
            children = []
        found.extend(children); pending.extend(children)
    return sorted(set(found))


def stop_group(proc: subprocess.Popen[bytes], reason: str) -> dict[str, object]:
    record: dict[str, object] = {"pid": proc.pid, "reason": reason, "signal_sent": None, "exit_code": proc.poll()}
    if proc.poll() is None:
        record["signal_sent"] = "SIGTERM"
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            record["exit_code"] = proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            record["signal_sent"] = "SIGKILL_after_SIGTERM_timeout"
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            record["exit_code"] = proc.wait(timeout=2)
    return record


def vector_delta(a: list[list[float]], b: list[list[float]]) -> tuple[int, float]:
    if len(a) != len(b):
        raise RuntimeError(f"vector-array length changed: {len(a)} vs {len(b)}")
    changed, maximum = 0, 0.0
    for left, right in zip(a, b):
        if len(left) != 3 or len(right) != 3:
            raise RuntimeError("diagnostic field contains a non-3D vector")
        delta = math.sqrt(sum((float(left[i]) - float(right[i])) ** 2 for i in range(3)))
        if left != right:
            changed += 1
        maximum = max(maximum, delta)
    return changed, maximum


def field_parts(snapshot: dict[str, object], name: str) -> tuple[list[list[float]], dict[str, list[list[float]]]]:
    field = snapshot[name]
    internal = field["internal"]
    boundary_obj = field["boundary"]
    if name == "pointDisplacement":
        boundary = {patch: record["values"] for patch, record in boundary_obj.items()}
    else:
        boundary = boundary_obj
    return internal, boundary


def compare_field(previous: tuple[list[list[float]], dict[str, list[list[float]]]] | None,
                  current: tuple[list[list[float]], dict[str, list[list[float]]]]) -> dict[str, object]:
    internal, boundary = current
    full = {"internal": internal, "boundary": boundary}
    result: dict[str, object] = {
        "full_sha256": sha_json(full),
        "internal_sha256": sha_json(internal),
        "boundary_sha256": sha_json(boundary),
        "internal_vectors": len(internal),
        "boundary_vectors": sum(len(v) for v in boundary.values()),
    }
    if previous is None:
        result.update({"changed_internal_entries": None, "changed_boundary_entries": None,
                       "changed_full_entries": None, "max_delta_from_previous": None})
        return result
    prev_internal, prev_boundary = previous
    ci, di = vector_delta(prev_internal, internal)
    if set(prev_boundary) != set(boundary):
        raise RuntimeError("boundary patch names changed between snapshots")
    cb, db = 0, 0.0
    for patch in sorted(boundary):
        changed, delta = vector_delta(prev_boundary[patch], boundary[patch])
        cb += changed; db = max(db, delta)
    result.update({"changed_internal_entries": ci, "changed_boundary_entries": cb,
                   "changed_full_entries": ci + cb, "max_delta_from_previous": max(di, db)})
    return result


def summarize_snapshots(stop_record: dict[str, object]) -> dict[str, object]:
    required = {
        "S0": next(DIAG.glob("S0_after_checkpoint_save_*.json"), None),
        "S1": next(DIAG.glob("S1_after_rollback_restore_retry_*.json"), None),
        "S2": next(DIAG.glob("S2_after_readData_dt_retry_*.json"), None),
    }
    stage = str(stop_record.get("stage", ""))
    match = re.search(r"call_(\d+)$", stage)
    if not match:
        raise RuntimeError(f"controlled stop has no RBF call identity: {stage}")
    call = match.group(1)
    required.update({
        "S3": DIAG / f"S3_before_correctBoundaryConditions_call_{call}.json",
        "S4": DIAG / f"S4_after_correctBoundaryConditions_call_{call}.json",
        "S5": DIAG / (stage + ".json"),
    })
    if any(path is None or not path.is_file() for path in required.values()):
        raise RuntimeError(f"S0-S5 stage set incomplete: {required}")
    metrics: dict[str, object] = {"selected_rbf_call": int(call), "stages": {}, "rollback": {}, "post_restore_mutation": {}}
    prev_fields: dict[str, tuple[list[list[float]], dict[str, list[list[float]]]] | None] = {
        "pointDisplacement": None, "cellDisplacement": None}
    prev_mesh: list[list[float]] | None = None
    stage_data: dict[str, dict[str, object]] = {}
    for stage_name in ("S0", "S1", "S2", "S3", "S4", "S5"):
        path = required[stage_name]
        snapshot = json.loads(path.read_text())
        stage_data[stage_name] = snapshot
        record: dict[str, object] = {"file": str(path), "file_sha256": sha(path),
                                     "time_s": snapshot["time_s"], "time_dir": snapshot["time_dir"]}
        for field_name in ("pointDisplacement", "cellDisplacement"):
            parts = field_parts(snapshot, field_name)
            record[field_name] = compare_field(prev_fields[field_name], parts)
            prev_fields[field_name] = parts
        points = snapshot["mesh_points"]
        record["mesh_points"] = {"sha256": sha_json(points), "point_count": len(points)}
        if prev_mesh is None:
            record["mesh_points"].update({"changed_points": None, "max_point_delta_m": None})
        else:
            changed, delta = vector_delta(prev_mesh, points)
            record["mesh_points"].update({"changed_points": changed, "max_point_delta_m": delta})
        prev_mesh = points
        if "rbf_candidate_mesh_points" in snapshot:
            candidate = snapshot["rbf_candidate_mesh_points"]
            changed, delta = vector_delta(snapshot["mesh_points"], candidate)
            record["rbf_candidate_mesh_points"] = {
                "sha256": sha_json(candidate), "point_count": len(candidate),
                "changed_from_current_mesh_points": changed, "max_delta_from_current_mesh_m": delta,
            }
        metrics["stages"][stage_name] = record

    point0 = metrics["stages"]["S0"]["pointDisplacement"]["full_sha256"]
    point1 = metrics["stages"]["S1"]["pointDisplacement"]["full_sha256"]
    cell0 = metrics["stages"]["S0"]["cellDisplacement"]["full_sha256"]
    cell1 = metrics["stages"]["S1"]["cellDisplacement"]["full_sha256"]
    mesh0 = metrics["stages"]["S0"]["mesh_points"]["sha256"]
    mesh1 = metrics["stages"]["S1"]["mesh_points"]["sha256"]
    metrics["rollback"] = {
        "pointDisplacement_S0_equals_S1": point0 == point1,
        "cellDisplacement_S0_equals_S1": cell0 == cell1,
        "mesh_points_S0_equals_S1": mesh0 == mesh1,
        "all_checkpointed_mesh_fields_restore_exactly": point0 == point1 and cell0 == cell1 and mesh0 == mesh1,
    }
    changes = []
    for before, after in zip(("S1", "S2", "S3", "S4"), ("S2", "S3", "S4", "S5")):
        if (metrics["stages"][after]["pointDisplacement"]["changed_full_entries"] or
                metrics["stages"][after]["cellDisplacement"]["changed_full_entries"] or
                metrics["stages"][after]["mesh_points"]["changed_points"]):
            changes.append({"from": before, "to": after})
    metrics["post_restore_mutation"]["observed"] = bool(changes)
    metrics["post_restore_mutation"]["transitions"] = changes
    metrics["classification"] = (
        "NONZERO_ROLLBACK_RESTORE_MISMATCH"
        if not metrics["rollback"]["all_checkpointed_mesh_fields_restore_exactly"]
        else "DISPLACEMENT_READ_OR_RBF_STAGE_MUTATION" if changes
        else "NONZERO_ROLLBACK_PASS"
    )
    return metrics


def execute(identity: dict[str, object]) -> dict[str, object]:
    socket_dir = Path(identity["socket_directory"])
    if socket_dir.exists() and any(socket_dir.iterdir()):
        raise RuntimeError("socket directory became nonempty after preflight")
    outputs = [RUN / name for name in ("runtime_identity.json", "launch_started.json", "fluid.stdout", "fluid.stderr",
              "structure.stdout", "structure.stderr", "structure_trace.jsonl", "structure_audit.json",
              "process_cleanup.json", "diagnostic_summary.json", "ancf_checkpoint_stages.jsonl", "pre_advance_attempts.jsonl")]
    if any(path.exists() for path in outputs):
        raise RuntimeError("single-use run output exists; refusing to overwrite")
    json_write(RUN / "runtime_identity.json", identity)
    marker = {"run_id": RUN.name, "start_unix": time.time(), "max_new_physical_windows": 1,
              "max_retries": 1, "controlled_stop_stage": "first RBF S5 after S2 readData(dt)"}
    json_write(RUN / "launch_started.json", marker)

    fluid_script = (
        "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; set -u; "
        "cd \"$1\" || exit 91; "
        "case_pwd=$(pwd -P); expected_pwd=$(realpath \"$1\"); "
        "printf 'PHASE1K18_7B_FLUID_PWD=%s\\n' \"$case_pwd\"; "
        "test \"$case_pwd\" = \"$expected_pwd\" || exit 92; "
        "export LD_LIBRARY_PATH=\"$2:$LD_LIBRARY_PATH\"; "
        "export PHASE1K18_DIAG_DIR=\"$3\"; "
        "export PHASE1K18_7B_STOP_AFTER_RETRY_S5=1; "
        "exec pimpleFoam -case ."
    )
    fluid_cmd = ["bash", "-c", fluid_script, "phase1k18-7b-fluid", str(CASE), str(RUN / "build"), str(DIAG)]
    structure_cmd = ["/usr/bin/python3.10", str(PARTICIPANT), "--case", str(CASE), "--run", "--worker", str(WORKER),
                     "--max-windows", "25", "--audit-output", str(RUN / "structure_audit.json"),
                     "--trace-output", str(RUN / "structure_trace.jsonl")]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PHASE1K18_7B_ANCF_TRACE"] = str(RUN / "ancf_checkpoint_stages.jsonl")
    env["PHASE1K18_7B_PRE_ADVANCE_TRACE"] = str(RUN / "pre_advance_attempts.jsonl")
    processes: dict[str, subprocess.Popen[bytes]] = {}
    maps: dict[str, dict[str, list[str]]] = {"Fluid": {}, "Structure": {}}
    seen_descendants: set[int] = set()
    started = time.monotonic()
    cleanup: dict[str, object] = {"started_unix": marker["start_unix"], "processes": {},
                                  "loaded_library_maps": maps, "descendant_pids": [],
                                  "controlled_stop_observed": False, "hard_stop_reason": None}
    with (RUN / "fluid.stdout").open("xb") as fluid_out, (RUN / "fluid.stderr").open("xb") as fluid_err, \
         (RUN / "structure.stdout").open("xb") as structure_out, (RUN / "structure.stderr").open("xb") as structure_err:
        processes["Fluid"] = subprocess.Popen(fluid_cmd, cwd=CASE, env=env, stdout=fluid_out, stderr=fluid_err, start_new_session=True)
        processes["Structure"] = subprocess.Popen(structure_cmd, cwd=CASE, env=env, stdout=structure_out, stderr=structure_err, start_new_session=True)
        cleanup["processes"] = {name: {"pid": proc.pid} for name, proc in processes.items()}
        reason = None
        controlled = False
        while True:
            stop_file = DIAG / "controlled_stop_after_retry_S5.json"
            if stop_file.is_file():
                controlled = True
                cleanup["controlled_stop_observed"] = True
                cleanup["controlled_stop_record_sha256"] = sha(stop_file)
                cleanup["hard_stop_reason"] = "instrumented stop immediately after retry S5; no next Fluid advance"
                break
            for name, proc in processes.items():
                if proc.poll() is not None and proc.returncode not in (0, None):
                    reason = f"{name} exited nonzero before controlled S5 stop: {proc.returncode}"
                    break
                if proc.poll() is None:
                    child_pids = descendants(proc.pid)
                    seen_descendants.update(child_pids)
                    for pid in [proc.pid, *child_pids]:
                        snapshot = process_maps(pid)
                        if snapshot:
                            maps[name][str(pid)] = snapshot
            if reason:
                break
            s1_count = len(list(DIAG.glob("S1_after_rollback_restore_retry_*.json")))
            s2_count = len(list(DIAG.glob("S2_after_readData_dt_retry_*.json")))
            attempt_file = RUN / "pre_advance_attempts.jsonl"
            attempt_count = len(attempt_file.read_text().splitlines()) if attempt_file.exists() else 0
            if s1_count > 1 or s2_count > 1 or attempt_count > 2:
                reason = "second rollback/read or third Structure attempt detected"
                break
            time_dirs = []
            for path in CASE.iterdir():
                if path.is_dir():
                    try: time_dirs.append(float(path.name))
                    except ValueError: pass
            if any(value > 30.0004000001 for value in time_dirs):
                reason = f"OpenFOAM advanced beyond the single retry endpoint: {time_dirs}"
                break
            for log in (RUN / "fluid.stdout", RUN / "fluid.stderr", RUN / "structure.stdout", RUN / "structure.stderr"):
                if log.exists():
                    tail = log.read_bytes()[-65536:].decode(errors="replace")
                    if re.search(r"FOAM FATAL|(?<![A-Za-z0-9_])SIGFPE\b|Floating point exception", tail):
                        reason = f"unplanned solver fatal marker in {log.name}"
                        break
            if reason:
                break
            if all(proc.poll() is not None for proc in processes.values()):
                reason = "both participants exited before the expected controlled S5 stop"
                break
            if time.monotonic() - started > TIMEOUT_S:
                reason = f"diagnostic hard timeout {TIMEOUT_S}s exceeded"
                break
            time.sleep(0.05)

        cleanup["hard_stop_reason"] = cleanup["hard_stop_reason"] or reason
        for name, proc in processes.items():
            if controlled and proc.poll() is None:
                cleanup["processes"][name].update(stop_group(proc, "peer stopped after S5 diagnostic marker"))
            elif reason:
                cleanup["processes"][name].update(stop_group(proc, reason))
            else:
                cleanup["processes"][name]["exit_code"] = proc.wait(timeout=3)
                cleanup["processes"][name]["signal_sent"] = None
    cleanup["elapsed_wall_s"] = time.monotonic() - started
    cleanup["finished_unix"] = time.time()
    cleanup["descendant_pids"] = sorted(seen_descendants)
    cleanup["post_run_solver_worker_processes"] = process_executable_matches({"pimpleFoam", "cfd_ancf_ancf_kernel_worker"})
    json_write(RUN / "process_cleanup.json", cleanup)

    stop_path = DIAG / "controlled_stop_after_retry_S5.json"
    if controlled and stop_path.is_file():
        stop_record = json.loads(stop_path.read_text())
        metrics = summarize_snapshots(stop_record)
        json_write(RUN / "field_stage_metrics.json", metrics)
        ancf_rows = [json.loads(line) for line in (RUN / "ancf_checkpoint_stages.jsonl").read_text().splitlines() if line.strip()]
        attempts = [json.loads(line) for line in (RUN / "pre_advance_attempts.jsonl").read_text().splitlines() if line.strip()]
        summary = {
            "classification": metrics["classification"],
            "controlled_stop": "CONTROLLED_STOP_AFTER_FIRST_RETRY_S5",
            "accepted_endpoint_source_global_time_s": 30.0002,
            "next_trial_target_global_time_s": 30.0004,
            "new_physical_window_accepted": False,
            "rollback_count": len(list(DIAG.glob("S1_after_rollback_restore_retry_*.json"))),
            "S0_S1_snapshot_count": len(ancf_rows),
            "pre_advance_attempt_count": len(attempts),
            "pre_advance_attempts": attempts,
            "ANCF_checkpoint_events": ancf_rows,
            "field_stage_metrics": str(RUN / "field_stage_metrics.json"),
            "process_cleanup": str(RUN / "process_cleanup.json"),
            "elapsed_wall_s": cleanup["elapsed_wall_s"],
        }
        json_write(RUN / "diagnostic_summary.json", summary)
        return summary
    return {"classification": "RUNTIME_STOPPED_BEFORE_COMPLETE_S0_S5", "hard_stop_reason": reason,
            "process_cleanup": str(RUN / "process_cleanup.json"), "elapsed_wall_s": cleanup["elapsed_wall_s"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight-only", action="store_true")
    group.add_argument("--run", action="store_true")
    group.add_argument("--summarize-existing", action="store_true",
                       help="analyze already captured S0-S5 evidence; never launches participants")
    args = parser.parse_args()
    try:
        if args.summarize_existing:
            stop_path = DIAG / "controlled_stop_after_retry_S5.json"
            summary_path = RUN / "diagnostic_summary.json"
            metrics_path = RUN / "field_stage_metrics.json"
            if not stop_path.is_file() or summary_path.exists() or metrics_path.exists():
                raise RuntimeError("complete stop marker required and existing summaries are never overwritten")
            metrics = summarize_snapshots(json.loads(stop_path.read_text()))
            json_write(metrics_path, metrics)
            ancf_rows = [json.loads(line) for line in (RUN / "ancf_checkpoint_stages.jsonl").read_text().splitlines() if line.strip()]
            attempts = [json.loads(line) for line in (RUN / "pre_advance_attempts.jsonl").read_text().splitlines() if line.strip()]
            summary = {
                "classification": metrics["classification"],
                "controlled_stop": "CONTROLLED_STOP_AFTER_FIRST_RETRY_S5",
                "accepted_endpoint_source_global_time_s": 30.0002,
                "next_trial_target_global_time_s": 30.0004,
                "new_physical_window_accepted": False,
                "rollback_count": len(list(DIAG.glob("S1_after_rollback_restore_retry_*.json"))),
                "S0_S1_snapshot_count": len(ancf_rows),
                "pre_advance_attempt_count": len(attempts),
                "pre_advance_attempts": attempts,
                "ANCF_checkpoint_events": ancf_rows,
                "field_stage_metrics": str(metrics_path),
                "process_cleanup": str(RUN / "process_cleanup.json"),
                "elapsed_wall_s": json.loads((RUN / "process_cleanup.json").read_text()).get("elapsed_wall_s"),
            }
            json_write(summary_path, summary)
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
        identity = preflight()
        if args.preflight_only:
            if (RUN / "preflight.json").exists():
                raise RuntimeError("preflight artifact already exists; refusing overwrite")
            json_write(RUN / "preflight.json", {"classification": "PASS_PREFLIGHT_ONLY", "identity": identity})
            print("PASS_PREFLIGHT_ONLY")
            return 0
        preflight_path = RUN / "preflight.json"
        if not preflight_path.is_file() or json.loads(preflight_path.read_text()).get("classification") != "PASS_PREFLIGHT_ONLY":
            raise RuntimeError("accepted preflight-only artifact is required before runtime")
        summary = execute(identity)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if summary.get("controlled_stop") == "CONTROLLED_STOP_AFTER_FIRST_RETRY_S5" else 3
    except Exception as exc:
        print(f"PHASE1K18_7B_PREFLIGHT_OR_RUN_BLOCKED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
