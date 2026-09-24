#!/usr/bin/python3.10
"""Build and run one bounded Phase 1K.18.7A accepted-window snapshot."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
RUN = Path(__file__).resolve().parent
CASE = RUN / "case"
FROZEN = ROOT / "evidence/phase1k10_new_mesh_restart/run-20260924T085251Z-c2245ff/mapped_candidate_30"
TEMPLATE_RUN = ROOT / "evidence/phase1k18_adapter/run-20260924T121817Z-c2245ff"
TEMPLATE_CASE = TEMPLATE_RUN / "case"
PARTICIPANT = ROOT / "src/coupling/hh06_structure_0000/structure_0000_participant.py"
CAPTURE_LAUNCHER = RUN / "participant_state_capture.py"
WORKER = ROOT / "build/phase1d6_worker/cfd_ancf_ancf_kernel_worker"
ADAPTER = ROOT / "evidence/phase1k17_adapter/lib/libpreciceAdapterPhase1K17.so"
QUALIFIED_ADAPTER = Path("/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so")
RBF = ROOT / "evidence/phase1k13b_rbf_diag/build-20260924T105315Z-c2245ff/lib/libRBFMeshMotionSolverPhase1K13Diag.so"
EXPECTED = {
    "worker": "3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596",
    "adapter": "1bc5cf6a1ea481082b01b903d317313be01212413c8bf2718481fa43c485c495",
    "qualified_adapter": "26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572",
    "rbf": "4a739721bfaa4734151e79bca285545d6934b2f5a9450080a5e833542a4c84ee",
}
FIELDS = ("U", "p", "k", "omega", "nut", "pointDisplacement")
MESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_hashes(path: Path) -> dict[str, str]:
    return {str(p.relative_to(path)): sha(p) for p in sorted(path.rglob("*")) if p.is_file()}


def numeric_time_dirs(path: Path) -> list[Path]:
    found = []
    for p in path.iterdir():
        if not p.is_dir():
            continue
        try:
            float(p.name)
        except ValueError:
            continue
        found.append(p)
    return sorted(found, key=lambda p: float(p.name))


def inspect_staged_case() -> dict:
    """Fail-closed validation for a case staged before a preflight-only stop."""
    if not CASE.is_dir() or (RUN / "launch_started.json").exists():
        raise RuntimeError("staged scratch is missing or already launched")
    if numeric_time_dirs(CASE) != [CASE / "30"]:
        raise RuntimeError("staged scratch has an unexpected physical time directory")
    for field in FIELDS:
        if sha(CASE / "30" / field) != sha(FROZEN / "30" / field):
            raise RuntimeError(f"staged release field no longer matches frozen restart: {field}")
    mesh_hashes = {name: sha(CASE / "constant/polyMesh" / name) for name in MESH_FILES}
    if mesh_hashes != {name: sha(FROZEN / "constant/polyMesh" / name) for name in MESH_FILES}:
        raise RuntimeError("staged mesh no longer matches frozen new mesh")
    socket_path = RUN / "precice-sockets"
    if not socket_path.is_dir() or any(socket_path.iterdir()):
        raise RuntimeError("staged socket directory missing or contains stale state")
    template_xml = (TEMPLATE_CASE / "precice-config.xml").read_text(encoding="utf-8")
    old_socket = re.search(r'exchange-directory="([^"]+)"', template_xml)
    if old_socket is None:
        raise RuntimeError("template XML has no socket path")
    expected_xml = template_xml.replace('max-time-windows value="2"', 'max-time-windows value="1"', 1)
    expected_xml = expected_xml.replace(old_socket.group(1), str(socket_path), 1)
    xml = (CASE / "precice-config.xml").read_text(encoding="utf-8")
    if xml != expected_xml:
        raise RuntimeError("staged XML has differences beyond the one-window bound/socket isolation")
    template_control = (TEMPLATE_CASE / "system/controlDict").read_text(encoding="utf-8")
    expected_control = re.sub(r"^writeInterval\s+0\.01\s*;", "writeInterval   0.0002;", template_control, count=1, flags=re.MULTILINE)
    control_path = CASE / "system/controlDict"
    if control_path.read_text(encoding="utf-8") != expected_control:
        raise RuntimeError("staged controlDict differs beyond endpoint snapshot write cadence")
    if str(ADAPTER) not in expected_control or str(RBF) not in (CASE / "constant/dynamicMeshDict").read_text(encoding="utf-8"):
        raise RuntimeError("staged scratch libraries do not match the authorized experimental identities")
    return {
        "source_restart": str(FROZEN), "source_time_s": 30.0,
        "source_field_sha256": {name: sha(CASE / "30" / name) for name in FIELDS},
        "mesh_sha256": mesh_hashes,
        "xml_sha256": sha(CASE / "precice-config.xml"),
        "dynamicMeshDict_sha256": sha(CASE / "constant/dynamicMeshDict"),
        "controlDict_sha256": sha(control_path),
        "preciceDict_sha256": sha(CASE / "system/preciceDict"),
        "scratch_write_interval_s": 0.0002, "precice_max_time_windows": 1,
        "precice_dt_s": 0.0002, "precice_max_iterations": 20,
        "precice_min_iterations": 2, "socket_directory": str(socket_path),
        "reused_preflight_staging": True,
    }


def run_capture(command: list[str], *, cwd: Path, env=None, timeout=90):
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def sha_build_id(path: Path) -> str:
    result = subprocess.run(["readelf", "-n", str(path)], capture_output=True, text=True, check=True)
    match = re.search(r"Build ID:\s*([0-9a-fA-F]+)", result.stdout)
    return match.group(1).lower() if match else "UNAVAILABLE"


def ensure_case() -> dict:
    if (RUN / "launch_started.json").exists():
        raise RuntimeError("run case or launch marker already exists; refusing reuse")
    if CASE.exists():
        return inspect_staged_case()
    if numeric_time_dirs(FROZEN) != [FROZEN / "30"]:
        raise RuntimeError(f"frozen source is not an unadvanced 30 s restart: {numeric_time_dirs(FROZEN)}")
    shutil.copytree(FROZEN, CASE, symlinks=True)

    # Overlay the already-qualified Phase 1K.18 coupling/ALE case files only;
    # source CFD fields and mesh remain copied from the frozen Phase 1K.10 state.
    overlay = (
        "contract.json", "interface_contract.json", "mapping_contract.json",
        "structure_contract.json", "precice-config.xml",
        "system/controlDict", "system/fvSchemes", "system/fvSolution",
        "system/preciceDict", "constant/dynamicMeshDict",
    )
    for relative in overlay:
        source = TEMPLATE_CASE / relative
        target = CASE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for name in ("new_f0_qualified_result.json", "new_restart_provenance.json", "f0_recovery_report_frozen.md"):
        shutil.copy2(TEMPLATE_RUN / name, RUN / name)

    # Make the final accepted CFD state a restart snapshot. Writing each retry
    # lands at the same physical endpoint; only the final accepted attempt is
    # retained after the participants finish.
    control_path = CASE / "system/controlDict"
    control = control_path.read_text(encoding="utf-8")
    if len(re.findall(r"^writeInterval\s+0\.01\s*;", control, re.MULTILINE)) != 1:
        raise RuntimeError("unexpected Phase 1K.18 writeInterval; no silent config rewrite")
    control_path.write_text(re.sub(r"^writeInterval\s+0\.01\s*;", "writeInterval   0.0002;", control, count=1, flags=re.MULTILINE), encoding="utf-8")

    xml_path = CASE / "precice-config.xml"
    xml = xml_path.read_text(encoding="utf-8")
    if xml.count('max-time-windows value="2"') != 1:
        raise RuntimeError("expected exactly one Phase 1K.18 two-window cap")
    socket_path = RUN / "precice-sockets"
    if socket_path.exists() or socket_path.is_symlink():
        raise RuntimeError("unique run socket path already exists")
    xml = xml.replace('max-time-windows value="2"', 'max-time-windows value="1"', 1)
    xml, changed = re.subn(r'exchange-directory="[^"]+"', f'exchange-directory="{socket_path}"', xml, count=1)
    if changed != 1:
        raise RuntimeError("could not isolate the preCICE socket directory")
    xml_path.write_text(xml, encoding="utf-8")
    socket_path.mkdir()

    required_xml_tokens = (
        '<max-time-windows value="1"/>', '<time-window-size value="0.0002"/>',
        '<min-iterations value="2"/>', '<max-iterations value="20"/>',
        '<acceleration:IQN-ILS reduced-time-grid="true">',
        '<initial-relaxation value="0.2" enforce="true"/>',
        '<max-used-iterations value="1"/>', '<time-windows-reused value="1"/>',
        '<filter type="QR3" limit="1e-2"/>', '<preconditioner type="residual-sum"/>',
        'initialize="yes"', 'name="Displacement"', 'name="Force"',
    )
    if any(token not in xml for token in required_xml_tokens):
        raise RuntimeError("scratch preCICE XML violates a frozen Phase 1K.18 coupling setting")
    if str(ADAPTER) not in control_path.read_text(encoding="utf-8"):
        raise RuntimeError("scratch OpenFOAM controlDict does not load the Phase 1K.17 adapter")
    if str(RBF) not in (CASE / "constant/dynamicMeshDict").read_text(encoding="utf-8"):
        raise RuntimeError("scratch dynamicMeshDict does not load the Phase 1K.13 diagnostic RBF")
    contract = json.loads((CASE / "contract.json").read_text(encoding="utf-8"))
    if contract["initial_state"].get("Fx0_total_N") != 0.0655270406896 or contract["initial_state"].get("Fy0_total_N") != 0.05872987414832:
        raise RuntimeError("new-mesh F0 differs from the accepted Phase 1K.10 value")
    if contract["coupling"].get("max_iterations") != 20:
        raise RuntimeError("contract iteration cap differs from the frozen value 20")
    if contract["execution_authorization"].get("adapter_runtime_sha256") != EXPECTED["adapter"]:
        raise RuntimeError("scratch contract adapter SHA does not identify Phase 1K.17")

    if len(numeric_time_dirs(CASE)) != 1 or numeric_time_dirs(CASE)[0].name != "30":
        raise RuntimeError("scratch case unexpectedly contains an advanced time directory")
    for field in FIELDS:
        if sha(CASE / "30" / field) != sha(FROZEN / "30" / field):
            raise RuntimeError(f"source restart field changed during case staging: {field}")
    mesh_hashes = {name: sha(CASE / "constant/polyMesh" / name) for name in MESH_FILES}
    if mesh_hashes != {name: sha(FROZEN / "constant/polyMesh" / name) for name in MESH_FILES}:
        raise RuntimeError("scratch mesh differs from the frozen new mesh")
    return {
        "source_restart": str(FROZEN),
        "source_time_s": 30.0,
        "source_field_sha256": {name: sha(CASE / "30" / name) for name in FIELDS},
        "mesh_sha256": mesh_hashes,
        "xml_sha256": sha(xml_path),
        "dynamicMeshDict_sha256": sha(CASE / "constant/dynamicMeshDict"),
        "controlDict_sha256": sha(control_path),
        "preciceDict_sha256": sha(CASE / "system/preciceDict"),
        "scratch_write_interval_s": 0.0002,
        "precice_max_time_windows": 1,
        "precice_dt_s": 0.0002,
        "precice_max_iterations": 20,
        "precice_min_iterations": 2,
        "socket_directory": str(socket_path),
    }


def main() -> int:
    if os.environ.get("WM_PROJECT_VERSION"):
        raise RuntimeError("runner must begin outside an inherited OpenFOAM environment")
    if not (ROOT / ".git").exists():
        raise RuntimeError(f"repository root resolution failed: {ROOT}")
    for label, path in (("worker", WORKER), ("adapter", ADAPTER), ("qualified_adapter", QUALIFIED_ADAPTER), ("rbf", RBF)):
        if not path.is_file() or sha(path) != EXPECTED[label]:
            raise RuntimeError(f"runtime identity mismatch: {label} {path}")
    if not PARTICIPANT.is_file() or not CAPTURE_LAUNCHER.is_file():
        raise RuntimeError("authoritative participant or diagnostic capture launcher is missing")

    staged = ensure_case()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    if branch != "repair/worker-lineage-implicit-contract-v1" or head != "c2245ff396ff42dfa5e80fee6555a9ede93e3b04":
        raise RuntimeError("Git branch/HEAD identity differs from the reviewed Phase 1K.18 baseline")
    tracked_dirty = subprocess.run(["git", "diff", "--quiet"], cwd=ROOT).returncode != 0 or subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode != 0
    if tracked_dirty:
        raise RuntimeError("tracked source/configuration changes exist; refusing runtime")

    environment = os.environ.copy()
    foam_info = run_capture(["/bin/bash", "-c", "source /opt/openfoam10/etc/bashrc && foamVersion"], cwd=ROOT, env=environment)
    foam_text = (foam_info.stdout + foam_info.stderr).strip()
    if foam_info.returncode or "OpenFOAM-10" not in foam_text:
        raise RuntimeError("OpenFOAM-10 environment preflight failed: " + foam_info.stderr)
    validation = run_capture(["precice-config-validate", str(CASE / "precice-config.xml")], cwd=CASE, timeout=60)
    if validation.returncode or "No major issues detected" not in validation.stdout:
        raise RuntimeError("preCICE XML validation failed: " + validation.stdout + validation.stderr)
    audit = run_capture(["/usr/bin/python3.10", str(PARTICIPANT), "--case", str(CASE), "--audit-only", "--audit-output", str(RUN / "structure_preflight_audit.json")], cwd=CASE, timeout=60)
    (RUN / "structure_preflight.stdout").write_text(audit.stdout, encoding="utf-8")
    (RUN / "structure_preflight.stderr").write_text(audit.stderr, encoding="utf-8")
    if audit.returncode:
        raise RuntimeError("Structure offline audit failed before launch")

    binding_probe = run_capture([
        "/usr/bin/python3.10", "-c",
        "import importlib.metadata as m, pathlib, precice, sys; print(sys.version.split()[0]); print(m.version('pyprecice')); print(precice.__file__); print('\\n'.join(sorted(set(x.split()[-1] for x in pathlib.Path('/proc/self/maps').read_text().splitlines() if 'libprecice' in x))))",
    ], cwd=CASE, timeout=30)
    if binding_probe.returncode or "/libprecice.so.3.4.1" not in binding_probe.stdout:
        raise RuntimeError("Python/preCICE binding runtime identity preflight failed")

    runtime_identity = {
        "run_id": RUN.name,
        "git": {"branch": branch, "head": head, "tracked_worktree_clean": not tracked_dirty},
        "software": {
            "openfoam_version_output": foam_text,
            "precice_runtime": "3.4.1",
            "python": "/usr/bin/python3.10",
            "python_version": binding_probe.stdout.splitlines()[0],
            "pyprecice_metadata": binding_probe.stdout.splitlines()[1],
            "precice_module": binding_probe.stdout.splitlines()[2],
            "loaded_libprecice": binding_probe.stdout.splitlines()[3:],
        },
        "worker": {"path": str(WORKER), "sha256": sha(WORKER)},
        "experimental_adapter": {"path": str(ADAPTER), "sha256": sha(ADAPTER), "build_id": sha_build_id(ADAPTER)},
        "qualified_adapter_not_loaded": {"path": str(QUALIFIED_ADAPTER), "sha256": sha(QUALIFIED_ADAPTER)},
        "diagnostic_rbf": {"path": str(RBF), "sha256": sha(RBF), "build_id": sha_build_id(RBF)},
        "authoritative_participant": {"path": str(PARTICIPANT), "sha256": sha(PARTICIPANT)},
        "diagnostic_capture_launcher": {"path": str(CAPTURE_LAUNCHER), "sha256": sha(CAPTURE_LAUNCHER)},
        "scratch_case": staged,
        "preCICE_validation_stdout": validation.stdout,
        "preCICE_validation_stderr": validation.stderr,
    }
    (RUN / "runtime_identity.json").write_text(json.dumps(runtime_identity, indent=2) + "\n", encoding="utf-8")
    (RUN / "preflight.json").write_text(json.dumps({"classification": "PASS_PREFLIGHT_ONLY", "runtime_identity_sha256": sha(RUN / "runtime_identity.json")}, indent=2) + "\n", encoding="utf-8")

    capture_path = RUN / "ancf_accepted_state.json"
    if capture_path.exists():
        raise RuntimeError("accepted ANCF state output already exists")
    marker = RUN / "launch_started.json"
    with marker.open("x", encoding="utf-8") as stream:
        json.dump({"run_id": RUN.name, "started_unix": time.time(), "max_physical_windows": 1, "dt_s": 0.0002}, stream)
        stream.write("\n")

    fluid_cmd = ["/bin/bash", "-c", "source /opt/openfoam10/etc/bashrc && printf 'PHASE1K18_7A_FLUID_PWD=%s\\n' \"$PWD\" && exec pimpleFoam -case ."]
    structure_cmd = [
        "/usr/bin/python3.10", str(CAPTURE_LAUNCHER), "--case", str(CASE), "--run",
        "--worker", str(WORKER), "--max-windows", "25",
        "--trace-output", str(RUN / "structure_trace.jsonl"),
        "--audit-output", str(RUN / "structure_audit.json"),
    ]
    run_env = environment.copy()
    run_env["PHASE1K18_7A_ANCF_STATE_OUTPUT"] = str(capture_path)
    processes = {}
    handles = []
    for role, command in (("fluid", fluid_cmd), ("structure", structure_cmd)):
        out = (RUN / f"{role}.stdout").open("x", encoding="utf-8")
        err = (RUN / f"{role}.stderr").open("x", encoding="utf-8")
        handles.extend((out, err))
        processes[role] = subprocess.Popen(command, cwd=CASE, env=run_env, stdout=out, stderr=err, start_new_session=True)

    started = time.monotonic()
    deadline = started + 900.0
    stop_reason = None
    loaded_paths: dict[str, set[str]] = {"fluid": set(), "structure": set()}
    descendant_pids: set[int] = set()
    try:
        while any(proc.poll() is None for proc in processes.values()):
            trace_path = RUN / "structure_trace.jsonl"
            if trace_path.exists():
                for line in trace_path.read_text(encoding="utf-8").splitlines():
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if int(record.get("window_index", 0)) > 1:
                        stop_reason = "unexpected second physical window observed"
                        break
                if stop_reason:
                    break
            for role, proc in processes.items():
                maps = Path(f"/proc/{proc.pid}/maps")
                if maps.exists():
                    for line in maps.read_text(errors="replace").splitlines():
                        if "libprecice" in line or "libpreciceAdapter" in line or "libRBFMeshMotionSolver" in line:
                            loaded_paths[role].add(line.split()[-1])
                children = Path(f"/proc/{proc.pid}/task/{proc.pid}/children")
                if children.exists():
                    for item in children.read_text().split():
                        if item.isdigit():
                            descendant_pids.add(int(item))
                if proc.poll() not in (None, 0):
                    stop_reason = f"{role} participant exited nonzero: {proc.returncode}"
                    break
            if stop_reason:
                break
            if time.monotonic() > deadline:
                stop_reason = "900-second diagnostic run timeout"
                break
            time.sleep(0.2)
        if stop_reason:
            for proc in processes.values():
                if proc.poll() is None:
                    proc.terminate()
            time.sleep(2)
            for proc in processes.values():
                if proc.poll() is None:
                    proc.kill()
    finally:
        for proc in processes.values():
            proc.wait(timeout=20)
        for handle in handles:
            handle.close()

    trace_path = RUN / "structure_trace.jsonl"
    trace = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()] if trace_path.exists() else []
    cleanup = {
        "fluid_pid": processes["fluid"].pid,
        "structure_pid": processes["structure"].pid,
        "descendant_pids": sorted(descendant_pids),
        "exit_codes": {role: proc.returncode for role, proc in processes.items()},
        "loaded_library_paths": {role: sorted(paths) for role, paths in loaded_paths.items()},
        "stop_reason": stop_reason,
        "elapsed_wall_s": time.monotonic() - started,
    }
    (RUN / "process_cleanup.json").write_text(json.dumps(cleanup, indent=2) + "\n", encoding="utf-8")

    endpoint_dirs = [p for p in numeric_time_dirs(CASE) if math.isclose(float(p.name), 30.0002, rel_tol=0.0, abs_tol=1.0e-9)]
    if len(endpoint_dirs) == 1:
        endpoint = endpoint_dirs[0]
        required = ("U", "p", "k", "omega", "nut", "pointDisplacement", "cellDisplacement", "uniform/time", "polyMesh/points")
        missing = [name for name in required if not (endpoint / name).is_file()]
        first_hashes = tree_hashes(endpoint)
        second_hashes = tree_hashes(endpoint)
        endpoint_manifest = {
            "global_time_s": float(endpoint.name),
            "directory": str(endpoint),
            "required_files_present": not missing,
            "missing_files": missing,
            "file_sha256": first_hashes,
            "same_tree_hashes_on_immediate_recheck": first_hashes == second_hashes,
        }
        (RUN / "accepted_cfd_state_manifest.json").write_text(json.dumps(endpoint_manifest, indent=2) + "\n", encoding="utf-8")
    else:
        endpoint_manifest = {"required_files_present": False, "endpoint_directories": [str(p) for p in endpoint_dirs]}
        (RUN / "accepted_cfd_state_manifest.json").write_text(json.dumps(endpoint_manifest, indent=2) + "\n", encoding="utf-8")

    final_source_identity = {
        "source_restart_fields_unchanged": all(sha(FROZEN / "30" / name) == runtime_identity["scratch_case"]["source_field_sha256"][name] for name in FIELDS),
        "source_mesh_unchanged": all(sha(FROZEN / "constant/polyMesh" / name) == runtime_identity["scratch_case"]["mesh_sha256"][name] for name in MESH_FILES),
        "scratch_release_fields_unchanged": all(sha(CASE / "30" / name) == runtime_identity["scratch_case"]["source_field_sha256"][name] for name in FIELDS),
    }
    (RUN / "restart_integrity_after.json").write_text(json.dumps(final_source_identity, indent=2) + "\n", encoding="utf-8")

    accepted = [r for r in trace if r.get("commit_status") == "committed"]
    ancf_state_valid = False
    ancf_state_hash = None
    if capture_path.is_file():
        try:
            state = json.loads(capture_path.read_text(encoding="utf-8"))
            accepted_state = state.get("accepted_state", {})
            checkpoint_state = (state.get("physical_checkpoint") or {}).get("backend_state", {})
            ancf_state_valid = (
                "capture_error" not in state
                and len(accepted_state.get("q", [])) == 198
                and len(accepted_state.get("qdot", [])) == 198
                and len(accepted_state.get("qddot", [])) == 198
                and len(checkpoint_state.get("q", [])) == 198
                and len(checkpoint_state.get("qdot", [])) == 198
                and len(checkpoint_state.get("qddot", [])) == 198
                and accepted_state.get("pending") is False
                and accepted_state.get("committed_advance_count") == 1
                and state.get("checkpoint_active_after_commit") is False
            )
            ancf_state_hash = sha(capture_path)
        except Exception:
            ancf_state_valid = False
    trace_one_window_only = bool(trace) and all(int(r.get("window_index", 0)) == 1 for r in trace)
    transport_sequence = [int(r["sequence"]) for r in trace if r.get("sequence") is not None]
    transport_monotonic = transport_sequence == sorted(set(transport_sequence))
    accepted_displacement_nonzero = bool(accepted and any(abs(float(v)) > 0.0 for v in accepted[0].get("D_trial_interface_m", [])))
    endpoint_tree_valid = bool(endpoint_manifest.get("required_files_present") and endpoint_manifest.get("same_tree_hashes_on_immediate_recheck"))
    fluid_log = (RUN / "fluid.stdout").read_text(encoding="utf-8", errors="replace") if (RUN / "fluid.stdout").exists() else ""
    cell_norms = [float(x) for x in re.findall(r"PHASE1K17_CELL_BOUNDARY patch=cylinder faces=200 max_norm=([0-9.eE+-]+)", fluid_log)]
    point_norms = [float(x) for x in re.findall(r"K13B_TRACE stage=point_boundary_summary[^\n]*max_norm=([0-9.eE+-]+)", fluid_log)]
    mesh_motion_norms = [float(x) for x in re.findall(r"K13B_TRACE stage=mesh_points_summary[^\n]*max_cur_minus_points0=([0-9.eE+-]+)", fluid_log)]
    motion_observation = {
        "cellDisplacement_cylinder_boundary_max_norm_m": max(cell_norms) if cell_norms else None,
        "pointDisplacement_cylinder_boundary_max_norm_m": max(point_norms) if point_norms else None,
        "rbf_mesh_candidate_max_displacement_m": max(mesh_motion_norms) if mesh_motion_norms else None,
    }
    (RUN / "nonzero_motion_observation.json").write_text(json.dumps(motion_observation, indent=2) + "\n", encoding="utf-8")
    restart_integrity_ok = all(final_source_identity.values())
    field_motion_observed = all(motion_observation[name] is not None and motion_observation[name] > 0.0 for name in (
        "cellDisplacement_cylinder_boundary_max_norm_m",
        "pointDisplacement_cylinder_boundary_max_norm_m",
        "rbf_mesh_candidate_max_displacement_m",
    ))
    summary = {
        "classification": "NONZERO_ACCEPTED_STATE_GENERATED" if len(accepted) == 1 and trace_one_window_only and len(trace) <= 20 and transport_monotonic and not stop_reason and all(code == 0 for code in cleanup["exit_codes"].values()) and ancf_state_valid and endpoint_tree_valid and restart_integrity_ok and accepted_displacement_nonzero and field_motion_observed else "REVIEW_REQUIRED",
        "physical_windows_authorized": 1,
        "completed_accepted_windows": len(accepted),
        "attempts": len(trace),
        "rollback_attempts": sum(bool(r.get("rollback_request")) for r in trace),
        "acceptance": accepted[0].get("convergence_status") if accepted else None,
        "accepted_interface_displacement_m": accepted[0].get("D_trial_interface_m") if accepted else None,
        "accepted_interface_displacement_nonzero": accepted_displacement_nonzero,
        "nonzero_fluid_to_rbf_motion_observed": field_motion_observed,
        "trace_one_window_only": trace_one_window_only,
        "transport_ids_monotonic": transport_monotonic,
        "ancf_state_snapshot_valid": ancf_state_valid,
        "ancf_state_snapshot_sha256": ancf_state_hash,
        "motion_observation": motion_observation,
        "endpoint_cfd_snapshot": endpoint_manifest,
        "ancf_state_snapshot_exists": (RUN / "ancf_accepted_state.json").is_file(),
        "restart_integrity": final_source_identity,
        "process_cleanup": cleanup,
        "run_stop_reason": stop_reason,
        "independent_runtime_replay_performed": False,
        "hash_reproducibility_scope": "bytewise manifests and frozen input identities; no second physical replay",
    }
    (RUN / "qualification_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["classification"] == "NONZERO_ACCEPTED_STATE_GENERATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
