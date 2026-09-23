#!/usr/bin/env python3
"""Fail-closed preflight and exact 25-window HH06 launch wrapper.

Preflight-only mode is read-only with respect to the case and starts no solver,
participant, worker, or ANCF process.  Runtime mode is separately opt-in.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import difflib
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASE = REPO_ROOT / "cases" / "hh06_single_slice"
PARTICIPANT = REPO_ROOT / "src" / "coupling" / "hh06_structure_0000" / "structure_0000_participant.py"
EXPECTED_ADAPTER = Path(
    "/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/"
    "libpreciceAdapterFunctionObject.so"
)
EXPECTED_ADAPTER_SHA256 = "26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572"
EXPECTED_WORKER_SOURCE = "src/ancf/ancf_worker_main.cpp"
EXPECTED_WORKER_SOURCE_SHA256 = "c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e"
EXPECTED_WORKER_BINARY_SHA256 = "3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596"
EXPECTED_PYPRECICE_METADATA_VERSION = "3.4.0"
EXPECTED_PRECICE_RUNTIME_VERSION = "3.4.1"
EXPECTED_MAX_WINDOWS = 25
EXPECTED_MAX_ITERATIONS = 20
EXPECTED_DT = 0.0002
EXPECTED_RELEASE_TIME = 30.0
EXPECTED_F0 = (0.0655270406544, 0.05872987413554, -2.44420351566e-21)
EXPECTED_F0_RESULT_SHA256 = "6b272f695ebefe28daa176723483f611c42f8d25dbae8d83de928f3790811b8a"
EXPECTED_F0_REPORT_SHA256 = "6737908b9b29f4ff8550ba4353ff88ad90ad5cfc1355a57a885d655f7d3d7b3b"
EXPECTED_F0_PROVENANCE_SHA256 = "1df1d2ca0876372874b1e6ac0eca2296e2f3ab8f8900e0b3903b53f2566e72d2"
BINDING_EVIDENCE = REPO_ROOT / "evidence" / "phase1d6_python_precice_binding" / "qualification.json"
RUN_EVIDENCE_ROOT = REPO_ROOT / "evidence" / "phase1i_25window_iqn"


class LaunchContractError(RuntimeError):
    """Raised when any bounded launch precondition is absent or inconsistent."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LaunchContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json_strict(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LaunchContractError(f"invalid or unreadable JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LaunchContractError(f"JSON root must be an object: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LaunchContractError(message)


def _numeric(value: Any, name: str) -> float:
    _require(not isinstance(value, bool) and isinstance(value, (int, float)), f"{name} must be numeric")
    number = float(value)
    _require(math.isfinite(number), f"{name} must be finite")
    return number


def _xml_numeric(value: Any, name: str) -> float:
    _require(isinstance(value, str), f"{name} must be a numeric XML attribute")
    try:
        number = float(value)
    except ValueError as exc:
        raise LaunchContractError(f"{name} must be numeric") from exc
    _require(math.isfinite(number), f"{name} must be finite")
    return number


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1]


def _one(items: list[Any], name: str) -> Any:
    _require(len(items) == 1, f"expected exactly one {name}, found {len(items)}")
    return items[0]


def _validate_iqn_ils_profile(implicit: ET.Element) -> dict[str, Any]:
    acceleration_nodes = [
        item for item in implicit
        if item.tag.startswith("{http://www.precice.org/schemas/acceleration}")
    ]
    acceleration = _one(acceleration_nodes, "preCICE acceleration configuration")
    _require(_local(acceleration.tag) == "IQN-ILS", "frozen Phase 1I profile requires IQN-ILS")
    _require(acceleration.attrib.get("reduced-time-grid") == "true", "IQN-ILS reduced-time-grid must remain true")
    _require(sorted(_local(item.tag) for item in acceleration) == sorted([
        "initial-relaxation", "max-used-iterations", "time-windows-reused",
        "data", "data", "filter", "preconditioner",
    ]), "IQN-ILS acceleration block contains unexpected or missing settings")

    initial = _one([item for item in acceleration if _local(item.tag) == "initial-relaxation"],
                   "IQN-ILS initial-relaxation")
    _require(_xml_numeric(initial.attrib.get("value"), "IQN-ILS initial-relaxation") == 0.2
             and initial.attrib.get("enforce") == "true",
             "IQN-ILS initial relaxation must be 0.2 with enforce=true")
    used = _one([item for item in acceleration if _local(item.tag) == "max-used-iterations"],
                "IQN-ILS max-used-iterations")
    _require(used.attrib.get("value") == "1", "IQN-ILS max-used-iterations must remain 1")
    reused = _one([item for item in acceleration if _local(item.tag) == "time-windows-reused"],
                  "IQN-ILS time-windows-reused")
    _require(reused.attrib.get("value") == "1", "IQN-ILS time-windows-reused must remain 1")

    data = [item for item in acceleration if _local(item.tag) == "data"]
    data_pairs = [(item.attrib.get("name"), item.attrib.get("mesh")) for item in data]
    _require(all(isinstance(name, str) and isinstance(mesh, str) for name, mesh in data_pairs)
             and sorted(data_pairs) == [("Displacement", "Structure-Mesh"), ("Force", "Structure-Mesh")],
             "IQN-ILS primary data must be exactly Displacement and Force on Structure-Mesh")
    filter_node = _one([item for item in acceleration if _local(item.tag) == "filter"], "IQN-ILS filter")
    _require(filter_node.attrib.get("type") == "QR3"
             and _xml_numeric(filter_node.attrib.get("limit"), "IQN-ILS QR3 filter limit") == 1e-2,
             "IQN-ILS filter must remain QR3 with limit=1e-2")
    preconditioner = _one([item for item in acceleration if _local(item.tag) == "preconditioner"],
                          "IQN-ILS preconditioner")
    _require(preconditioner.attrib.get("type") == "residual-sum",
             "IQN-ILS preconditioner must remain residual-sum")
    return {
        "type": "IQN-ILS", "reduced_time_grid": True, "initial_relaxation": 0.2,
        "enforce_initial_relaxation": True, "max_used_iterations": 1,
        "time_windows_reused": 1, "primary_data": data_pairs,
        "primary_scalar_dimension": 4, "preconditioner": "residual-sum",
        "filter": "QR3", "filter_limit": 1e-2,
    }


def _validate_iteration_bounds(implicit: ET.Element) -> dict[str, int]:
    min_iterations_node = _one([item for item in implicit if _local(item.tag) == "min-iterations"],
                               "min-iterations")
    max_iterations_node = _one([item for item in implicit if _local(item.tag) == "max-iterations"],
                               "max-iterations")
    _require(min_iterations_node.attrib.get("value") == "2", "preCICE min-iterations must remain 2")
    _require(max_iterations_node.attrib.get("value") == "20", "preCICE max-iterations must remain 20")
    return {"min_iterations": 2, "max_iterations": 20}


def _verify_sha(path: Path, expected: str, label: str) -> str:
    _require(path.is_file(), f"missing {label}: {path}")
    actual = sha256(path)
    _require(actual == expected, f"{label} SHA256 mismatch: {path}: {actual} != {expected}")
    return actual


def _frozen_sha(entry: Any, label: str) -> str:
    if isinstance(entry, str):
        return entry
    _require(isinstance(entry, Mapping), f"{label} hash record is invalid")
    before, after = entry.get("before"), entry.get("after")
    _require(isinstance(before, str) and before == after, f"{label} changed in frozen evidence")
    return before


def _safe_repo_file(case_dir: Path, relative: str, label: str) -> Path:
    path = (case_dir / relative).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise LaunchContractError(f"{label} path escapes the authoritative repository: {path}") from exc
    _require(path.is_file(), f"missing {label}: {path}")
    return path


def _read_foam_value(path: Path, key: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^\s*{re.escape(key)}\s+([^;]+);", text, flags=re.MULTILINE)
    _require(match is not None, f"missing {key} in {path}")
    return match.group(1).strip().strip('"')


def _verify_restart(case_dir: Path, contract: Mapping[str, Any], initial: Mapping[str, Any]) -> dict[str, Any]:
    prov_ref = initial.get("release_force_provenance")
    _require(isinstance(prov_ref, Mapping), "initial_state.release_force_provenance must be an object")
    _require(prov_ref.get("classification") == "RELEASE_FORCE_RECOVERED_REPRODUCIBLY", "release-force classification is not reproducible")
    _require(prov_ref.get("restart_case_id") == contract.get("case_id"), "release-force restart case ID mismatch")
    _require(prov_ref.get("restart_time_directory") == "30", "release-force restart directory must be exactly 30")
    _require(_numeric(prov_ref.get("restart_global_time_s"), "release_force_provenance.restart_global_time_s") == EXPECTED_RELEASE_TIME,
             "release-force source time must be exactly 30.0 s")
    _require(prov_ref.get("patch") == "cylinder", "release-force patch must be cylinder")
    _require(prov_ref.get("raw_force_units") == "N", "release force must remain raw dimensional N")

    result_path = _safe_repo_file(case_dir, str(prov_ref.get("result_json", "")), "F0 result JSON")
    report_path = _safe_repo_file(case_dir, str(prov_ref.get("recovery_report", "")), "F0 recovery report")
    provenance_path = _safe_repo_file(case_dir, str(prov_ref.get("provenance_json", "")), "restart provenance JSON")
    _verify_sha(result_path, EXPECTED_F0_RESULT_SHA256, "frozen F0 result")
    _verify_sha(report_path, EXPECTED_F0_REPORT_SHA256, "frozen F0 report")
    _verify_sha(provenance_path, EXPECTED_F0_PROVENANCE_SHA256, "frozen restart provenance")
    _require(prov_ref.get("result_json_sha256") == EXPECTED_F0_RESULT_SHA256, "contract F0 result hash mismatch")
    _require(prov_ref.get("recovery_report_sha256") == EXPECTED_F0_REPORT_SHA256, "contract F0 report hash mismatch")
    _require(prov_ref.get("provenance_json_sha256") == EXPECTED_F0_PROVENANCE_SHA256, "contract restart provenance hash mismatch")

    force_result = load_json_strict(result_path)
    source_provenance = load_json_strict(provenance_path)
    _require(force_result.get("classification") == "RELEASE_FORCE_RECOVERED_REPRODUCIBLY", "frozen force result classification mismatch")
    _require(force_result.get("case_id") == contract.get("case_id"), "frozen force result case ID mismatch")
    _require(_numeric(force_result.get("global_time_s"), "F0.global_time_s") == EXPECTED_RELEASE_TIME, "frozen F0 time mismatch")
    _require(force_result.get("patch") == "cylinder", "frozen F0 patch mismatch")
    result_force = tuple(_numeric(force_result.get(key), key) for key in ("Fx_raw_N", "Fy_raw_N", "Fz_raw_N"))
    contract_force = (
        _numeric(initial.get("Fx0_total_N"), "initial_state.Fx0_total_N"),
        _numeric(initial.get("Fy0_total_N"), "initial_state.Fy0_total_N"),
        _numeric(prov_ref.get("Fz0_measured_N"), "release_force_provenance.Fz0_measured_N"),
    )
    _require(result_force == EXPECTED_F0, "frozen F0 result no longer matches the qualified numeric tuple")
    _require(contract_force == EXPECTED_F0, "contract F0 numeric tuple differs from frozen release-force evidence")

    conversion = force_result.get("force_conversion", "")
    _require("F_section = F_raw/Lz" in conversion and "F_strip = F_section*DeltaL" in conversion,
             "F0 evidence does not state the qualified one-time force conversion")
    flow = contract.get("flow", {})
    geometry = contract.get("geometry", {})
    mapping_contract = load_json_strict(case_dir / "mapping_contract.json")
    force_conversion = mapping_contract.get("force_conversion", {})
    _require(_numeric(flow.get("Lz_m"), "flow.Lz_m") == 0.028, "qualified CFD span changed")
    _require(_numeric(geometry.get("single_slice_structural_length_m"), "geometry.single_slice_structural_length_m") == 1.98,
             "qualified strip length changed")
    _require(_numeric(mapping_contract.get("structural_reference", {}).get("deltaL_m"),
                      "mapping_contract.structural_reference.deltaL_m") == 1.98,
             "mapping-contract strip length changed")
    _require(force_conversion.get("apply_deltaL_once") is True
             and force_conversion.get("apply_cfd_span_division_once") is True
             and force_conversion.get("double_counting_forbidden") is True,
             "qualified one-time force conversion contract changed")

    restart = source_provenance.get("restart", {})
    _require(restart.get("case_id") == contract.get("case_id"), "restart provenance case ID mismatch")
    _require(restart.get("time_directory") == "30" and _numeric(restart.get("global_time_s"), "restart.global_time_s") == 30.0,
             "restart provenance time identity mismatch")
    uniform_time = restart.get("uniform_time", {})
    _require(uniform_time.get("index") == 150000, "restart provenance index mismatch")
    _require(_numeric(uniform_time.get("deltaT_s"), "restart.uniform_time.deltaT_s") == EXPECTED_DT,
             "restart provenance dt mismatch")

    field_hashes = restart.get("field_hashes_sha256_before_and_after", {})
    _require(isinstance(field_hashes, Mapping) and field_hashes, "restart field hash inventory is missing")
    checked_fields: dict[str, str] = {}
    for name, entry in field_hashes.items():
        before = _frozen_sha(entry, f"restart field {name}")
        path = (case_dir / "30" / name).resolve()
        _verify_sha(path, before, f"restart field {name}")
        checked_fields[name] = before

    mesh_hashes = restart.get("polyMesh_file_hashes_sha256_before_and_after", {})
    _require(isinstance(mesh_hashes, Mapping) and mesh_hashes, "frozen polyMesh hash inventory is missing")
    checked_mesh: dict[str, str] = {}
    for name, entry in mesh_hashes.items():
        before = _frozen_sha(entry, f"polyMesh file {name}")
        path = (case_dir / "constant" / "polyMesh" / name).resolve()
        _verify_sha(path, before, f"polyMesh file {name}")
        checked_mesh[name] = before

    runtime_hashes = restart.get("runtime_configuration_hashes_sha256_before_and_after", {})
    _require(isinstance(runtime_hashes, Mapping) and runtime_hashes, "frozen runtime configuration hash inventory is missing")
    checked_runtime: dict[str, str] = {}
    for name, entry in runtime_hashes.items():
        before = _frozen_sha(entry, f"runtime configuration {name}")
        _verify_sha(case_dir / name, before, f"restart runtime configuration {name}")
        checked_runtime[name] = before

    time_file = case_dir / "30" / "uniform" / "time"
    _require(_read_foam_value(time_file, "value") == "30", "OpenFOAM restart value is not 30")
    _require(_read_foam_value(time_file, "name") == "30", "OpenFOAM restart name is not 30")
    _require(_read_foam_value(time_file, "index") == "150000", "OpenFOAM restart index is not 150000")
    _require(float(_read_foam_value(time_file, "deltaT")) == EXPECTED_DT, "OpenFOAM restart deltaT mismatch")
    numeric_times = sorted(
        entry.name for entry in case_dir.iterdir()
        if entry.is_dir() and re.fullmatch(r"\d+(?:\.\d+)?", entry.name)
    )
    _require(numeric_times == ["30"], f"case is not a clean 30 s restart; numeric time directories={numeric_times}")
    return {
        "time_directory": "30", "global_time_s": EXPECTED_RELEASE_TIME,
        "time_index": 150000, "dt_s": EXPECTED_DT,
        "F0_raw_N": list(result_force), "result_json_sha256": sha256(result_path),
        "report_sha256": sha256(report_path), "provenance_json_sha256": sha256(provenance_path),
        "field_hashes_verified": checked_fields, "polyMesh_hashes_verified": checked_mesh,
        "runtime_configuration_hashes_verified": checked_runtime,
    }


def binding_runtime_identity() -> dict[str, str]:
    try:
        import cyprecice
        import precice
        package_version = importlib.metadata.version("pyprecice")
    except Exception as exc:
        raise LaunchContractError(f"cannot import qualified Python preCICE binding: {exc}") from exc
    loaded_paths: set[Path] = set()
    try:
        maps = Path("/proc/self/maps").read_text(encoding="utf-8")
    except OSError as exc:
        raise LaunchContractError("cannot inspect /proc/self/maps for loaded preCICE runtime") from exc
    for line in maps.splitlines():
        if "libprecice.so" not in line:
            continue
        fields = line.split()
        if fields and fields[-1].startswith("/"):
            loaded_paths.add(Path(fields[-1].removesuffix(" (deleted)")).resolve())
    library = _one(sorted(loaded_paths), "loaded libprecice.so path")
    runtime_info = precice.get_version_information()
    if isinstance(runtime_info, bytes):
        runtime_info = runtime_info.decode("utf-8", errors="replace")
    runtime_version = str(runtime_info).split(";", 1)[0]
    extension = Path(cyprecice.__file__).resolve()
    module = Path(precice.__file__).resolve()
    return {
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": sys.version,
        "pyprecice_metadata_version": package_version,
        "precice_module_path": str(module),
        "precice_module_sha256": sha256(module),
        "cyprecice_extension_path": str(extension),
        "cyprecice_extension_sha256": sha256(extension),
        "libprecice_loaded_path": str(library),
        "libprecice_sha256": sha256(library),
        "libprecice_runtime_version": runtime_version,
        "libprecice_version_information": str(runtime_info),
    }


def _verify_binding_qualification() -> dict[str, Any]:
    artifact = load_json_strict(BINDING_EVIDENCE)
    _require(artifact.get("classification") == "PYTHON_PRECICE_BINDING_RUNTIME_CONFIRMED",
             "isolated Python/preCICE runtime qualification has not passed")
    exits = artifact.get("participant_exit_codes")
    _require(isinstance(exits, Mapping) and exits.get("Fluid") == 0 and exits.get("Structure") == 0,
             "both participants must exit successfully in the Python/preCICE qualification")
    recorded = artifact.get("runtime_identity")
    _require(isinstance(recorded, Mapping), "Python/preCICE runtime identity evidence is missing")
    current = binding_runtime_identity()
    _require(recorded == current, "current Python/preCICE runtime identity differs from the qualified scratch runtime")
    _require(current["pyprecice_metadata_version"] == EXPECTED_PYPRECICE_METADATA_VERSION,
             "pyprecice metadata version differs from the qualified 3.4.0 binding")
    _require(current["libprecice_runtime_version"] == EXPECTED_PRECICE_RUNTIME_VERSION,
             "loaded libprecice runtime is not preCICE 3.4.1")
    return {"classification": artifact["classification"], "runtime_identity": current,
            "participant_exit_codes": dict(exits), "configuration_sha256": artifact.get("configuration_sha256")}


def _verify_worker(worker_arg: str, authorization: Mapping[str, Any]) -> dict[str, str]:
    _require(bool(worker_arg.strip()), "worker path must be supplied explicitly with --worker")
    worker = Path(worker_arg).expanduser().resolve()
    _require(worker.is_file() and os.access(worker, os.X_OK), f"worker must be an executable file: {worker}")
    source_path = REPO_ROOT / EXPECTED_WORKER_SOURCE
    source_sha = sha256(source_path)
    binary_sha = sha256(worker)
    _require(authorization.get("worker_source") == EXPECTED_WORKER_SOURCE, "contract worker source path mismatch")
    _require(authorization.get("worker_source_sha256") == EXPECTED_WORKER_SOURCE_SHA256,
             "contract worker source SHA mismatch")
    _require(authorization.get("worker_binary_sha256") == EXPECTED_WORKER_BINARY_SHA256,
             "contract worker binary SHA mismatch")
    _require(source_sha == EXPECTED_WORKER_SOURCE_SHA256, f"current worker source SHA mismatch: {source_sha}")
    _require(binary_sha == EXPECTED_WORKER_BINARY_SHA256, f"worker binary SHA mismatch: {binary_sha}")
    return {"path": str(worker), "source_path": str(source_path),
            "source_sha256": source_sha, "binary_sha256": binary_sha}


def _verify_adapter(authorization: Mapping[str, Any]) -> dict[str, str]:
    path_raw = os.environ.get("ANCF_ADAPTER_RUNTIME_PATH", "")
    sha_raw = os.environ.get("ANCF_ADAPTER_RUNTIME_SHA256", "")
    _require(path_raw and sha_raw, "adapter SHA guard must run before launcher preflight")
    path = Path(path_raw).resolve()
    _require(path == EXPECTED_ADAPTER.resolve(), f"adapter path is not the SHA-qualified runtime: {path}")
    _require(authorization.get("adapter_runtime_sha256") == EXPECTED_ADAPTER_SHA256,
             "contract adapter SHA does not match the qualified binary")
    _require(sha_raw == EXPECTED_ADAPTER_SHA256, "adapter SHA guard result differs from the qualified SHA")
    actual = _verify_sha(path, EXPECTED_ADAPTER_SHA256, "Fluid preCICE adapter")
    _require(authorization.get("adapter_source_provenance_resolved") is False,
             "adapter source provenance must remain explicitly unresolved")
    return {"path": str(path), "sha256": actual, "source_provenance_resolved": "NO"}


def _verify_openfoam_identity(fluid_executable: str | Path) -> dict[str, str]:
    """Verify the sourced OpenFOAM environment without assuming foamVersion is an executable."""
    version = os.environ.get("WM_PROJECT_VERSION", "")
    project = os.environ.get("WM_PROJECT", "")
    project_dir_raw = os.environ.get("WM_PROJECT_DIR", "")
    app_bin_raw = os.environ.get("FOAM_APPBIN", "")
    _require(version == "10", f"expected WM_PROJECT_VERSION=10, got {version!r}")
    _require(project == "OpenFOAM", f"expected WM_PROJECT=OpenFOAM, got {project!r}")
    _require(bool(project_dir_raw), "WM_PROJECT_DIR is unavailable after sourcing OpenFOAM environment")
    _require(bool(app_bin_raw), "FOAM_APPBIN is unavailable after sourcing OpenFOAM environment")

    project_dir = Path(project_dir_raw).expanduser().resolve()
    app_bin = Path(app_bin_raw).expanduser().resolve()
    expected_project_dir = Path("/opt/openfoam10").resolve()
    _require(project_dir == expected_project_dir,
             f"unexpected OpenFOAM project directory: {project_dir} != {expected_project_dir}")
    try:
        app_bin.relative_to(project_dir)
    except ValueError as exc:
        raise LaunchContractError(f"FOAM_APPBIN escapes the qualified OpenFOAM installation: {app_bin}") from exc

    executable = Path(fluid_executable).expanduser().resolve()
    expected_executable = app_bin / "pimpleFoam"
    _require(executable == expected_executable,
             f"pimpleFoam path differs from sourced FOAM_APPBIN: {executable} != {expected_executable}")
    _require(executable.is_file() and os.access(executable, os.X_OK),
             f"qualified pimpleFoam executable is missing or not executable: {executable}")
    return {
        "version": "OpenFOAM-10",
        "WM_PROJECT_VERSION": version,
        "WM_PROJECT": project,
        "project_dir": str(project_dir),
        "application_bin": str(app_bin),
        "pimpleFoam_executable": str(executable),
    }


def _socket_directory(case_dir: Path, root: ET.Element) -> Path:
    sockets = [item for item in root.iter() if _local(item.tag) == "sockets" and "exchange-directory" in item.attrib]
    element = _one(sockets, "socket exchange-directory")
    raw = element.attrib["exchange-directory"]
    path = Path(raw).expanduser()
    return (case_dir / path).resolve() if not path.is_absolute() else path.resolve()


def _check_socket_directory(path: Path, case_dir: Path) -> dict[str, Any]:
    if path.exists():
        _require(path.is_dir(), f"preCICE exchange path exists but is not a directory: {path}")
        _require(os.access(path, os.W_OK | os.X_OK), f"preCICE exchange directory is not writable: {path}")
    else:
        parent = path.parent
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        _require(parent.is_dir() and os.access(parent, os.W_OK | os.X_OK),
                 f"preCICE exchange directory cannot be safely created under {parent}")
    stale: list[str] = []
    if path.exists():
        for item in path.rglob("*"):
            if item.is_symlink() or item.is_file() or item.is_socket():
                stale.append(str(item))
    _require(not stale, "preCICE exchange directory contains files/sockets; preserved without deletion: " + ", ".join(stale))
    return {"path": str(path), "exists": path.exists(), "writable_or_creatable": True,
            "nonempty_directories_only": bool(path.exists() and any(path.iterdir())),
            "stale_files": stale}


def _case_processes(case_dir: Path, worker_path: Path) -> list[str]:
    active: list[str] = []
    case_text = str(case_dir.resolve())
    worker_text = str(worker_path.resolve())
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return active
    for entry in proc_root.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            argv = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            exe = (entry / "comm").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        case_match = case_text in argv
        relevant = (
            (case_match and ("pimpleFoam" in exe or "structure_0000_participant.py" in argv))
            or (case_match and worker_text in argv)
        )
        if relevant:
            active.append(f"pid={entry.name} comm={exe} argv={argv.strip()}")
    return active


def _active_socket_users(socket_path: Path, config_path: Path, case_dir: Path,
                         proc_root: Path = Path("/proc")) -> list[str]:
    """Fail closed if a visible live process is attached to this exchange path."""
    if not proc_root.is_dir():
        raise LaunchContractError("cannot inspect /proc for active preCICE socket users")
    active: list[str] = []
    socket_resolved = socket_path.resolve()
    socket_text = str(socket_resolved)
    config_text = str(config_path.resolve())
    case_resolved = case_dir.resolve()

    for entry in proc_root.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            raw_argv = (entry / "cmdline").read_bytes()
            argv_items = [part.decode(errors="replace") for part in raw_argv.split(b"\0") if part]
            argv = " ".join(argv_items)
            executable = (entry / "comm").read_text(encoding="utf-8").strip()
            cwd = Path(os.readlink(entry / "cwd")).resolve()
        except OSError:
            continue

        matches = socket_text in argv or config_text in argv
        relevant = (
            executable == "pimpleFoam"
            or "precice" in executable.lower()
            or "precice" in argv.lower()
            or "structure_0000_participant.py" in argv
        )
        if relevant and not matches:
            candidate_case = cwd if cwd.is_dir() else None
            for option in ("-case", "--case"):
                if option not in argv_items:
                    continue
                try:
                    raw_case = Path(argv_items[argv_items.index(option) + 1]).expanduser()
                    candidate_case = (cwd / raw_case).resolve() if not raw_case.is_absolute() else raw_case.resolve()
                except (IndexError, OSError):
                    candidate_case = None
                break

            if candidate_case is not None:
                candidate_dict = candidate_case / "system" / "preciceDict"
                if candidate_dict.is_file():
                    try:
                        config_match = re.search(
                            r'^\s*preciceConfig\s+"?([^";]+)"?\s*;',
                            candidate_dict.read_text(encoding="utf-8"), flags=re.MULTILINE,
                        )
                        if config_match is not None:
                            candidate_config = (candidate_case / config_match.group(1)).resolve()
                            candidate_root = ET.parse(candidate_config).getroot()
                            matches = _socket_directory(candidate_case, candidate_root) == socket_resolved
                    except (OSError, ET.ParseError, LaunchContractError):
                        if candidate_case == case_resolved:
                            matches = True

        if relevant and not matches:
            fd_dir = entry / "fd"
            try:
                for fd in fd_dir.iterdir():
                    try:
                        target = os.readlink(fd)
                    except OSError:
                        continue
                    if target == socket_text or target.startswith(socket_text + "/"):
                        matches = True
                        break
            except OSError:
                pass

        if matches:
            active.append(f"pid={entry.name} comm={executable} argv={argv.strip()}")
    return active


def _participant_audit(case_dir: Path) -> dict[str, Any]:
    help_run = subprocess.run([sys.executable, str(PARTICIPANT), "--help"], cwd=REPO_ROOT,
                              capture_output=True, text=True, timeout=30, check=False)
    _require(help_run.returncode == 0, "authoritative participant --help failed: " + help_run.stderr.strip())
    for option in ("--case", "--run", "--worker", "--max-windows", "--trace-output"):
        _require(option in help_run.stdout, f"authoritative participant CLI is missing {option}")
    _require("--contract" not in help_run.stdout, "obsolete --contract CLI unexpectedly reappeared")
    audit_run = subprocess.run([sys.executable, str(PARTICIPANT), "--case", str(case_dir), "--audit-only"],
                                cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, check=False)
    _require(audit_run.returncode == 0, "authoritative participant offline audit failed: " + audit_run.stderr.strip())
    try:
        audit = json.loads(audit_run.stdout)
    except json.JSONDecodeError as exc:
        raise LaunchContractError("participant audit did not emit valid JSON") from exc
    _require(audit.get("status") == "PASS", "participant offline audit is not PASS")
    cap = audit.get("iteration_cap", {})
    _require(cap.get("contract_json") == EXPECTED_MAX_ITERATIONS and cap.get("precice_xml") == EXPECTED_MAX_ITERATIONS
             and cap.get("values_match") is True, "participant audit reports inconsistent iteration cap")
    _require(audit.get("checks", {}).get("physical_release_force_provenance") is True,
             "participant audit rejected physical F0 provenance")
    _require(audit.get("checks", {}).get("force_initial_data_exchange") is True,
             "participant audit rejected Force initial data")
    return {"status": "PASS", "cli_options": ["--case", "--run", "--worker", "--max-windows", "--trace-output"],
            "iteration_cap": cap, "release_force": audit.get("release_force"),
            "participant_path": str(PARTICIPANT.resolve())}


def _foam_dictionary_value(executable: str, path: Path, entry: str) -> str:
    result = subprocess.run([executable, "-entry", entry, "-value", str(path)],
                            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, check=False)
    _require(result.returncode == 0, f"foamDictionary rejected {path}:{entry}: {result.stderr.strip()}")
    return result.stdout.strip()


def _validate_passive_diagnostic_overlay(case_dir: Path, restart: Mapping[str, Any]) -> dict[str, Any]:
    foam_dictionary = shutil.which("foamDictionary")
    _require(foam_dictionary is not None, "foamDictionary unavailable for passive-diagnostic preflight")
    base_control = case_dir / "system" / "controlDict"
    base_solution = case_dir / "system" / "fvSolution"
    overlay_control = case_dir / "phase1i_observability" / "controlDict"
    overlay_solution = case_dir / "phase1i_observability" / "fvSolution"
    _require(all(path.is_file() for path in (overlay_control, overlay_solution)),
             "Phase 1I passive-diagnostic overlay files are missing")
    _require(sha256(base_control) == restart["runtime_configuration_hashes_verified"]["system/controlDict"]
             and sha256(base_solution) == restart["runtime_configuration_hashes_verified"]["system/fvSolution"],
             "authoritative OpenFOAM control dictionaries differ from frozen restart provenance")

    unchanged_control_entries = ("application", "startFrom", "startTime", "stopAt", "endTime", "deltaT",
                                 "writeInterval", "purgeWrite", "writeFormat", "writePrecision",
                                 "writeCompression", "timeFormat", "timePrecision")
    comparisons: dict[str, dict[str, str]] = {}
    for entry in unchanged_control_entries:
        before = _foam_dictionary_value(foam_dictionary, base_control, entry)
        after = _foam_dictionary_value(foam_dictionary, overlay_control, entry)
        _require(before == after, f"passive diagnostics changed OpenFOAM controlDict.{entry}: {before} -> {after}")
        comparisons[f"controlDict.{entry}"] = {"authoritative": before, "scratch_overlay": after}
    for entry in ("solvers", "relaxationFactors"):
        before = _foam_dictionary_value(foam_dictionary, base_solution, entry)
        after = _foam_dictionary_value(foam_dictionary, overlay_solution, entry)
        _require(before == after, f"passive diagnostics changed fvSolution.{entry}")
    base_pimple = _foam_dictionary_value(foam_dictionary, base_solution, "PIMPLE")
    overlay_pimple = _foam_dictionary_value(foam_dictionary, overlay_solution, "PIMPLE")
    remove_mesh_check = lambda value: "\n".join(
        line for line in value.splitlines() if "checkMeshCourantNo" not in line
    )
    _require(remove_mesh_check(base_pimple) == remove_mesh_check(overlay_pimple),
             "passive mesh-Courant diagnostic changed existing PIMPLE settings")
    _require("checkMeshCourantNo yes;" in overlay_pimple,
             "scratch fvSolution must enable the passive OpenFOAM mesh Courant diagnostic")
    control_text = overlay_control.read_text(encoding="utf-8")
    force_block = re.search(r"cylinderForces\s*\{([^}]*)\}", control_text, flags=re.DOTALL)
    _require(force_block is not None and re.search(r"writeInterval\s+1\s*;", force_block.group(1)) is not None,
             "scratch forces(cylinder) output must be captured at each CFD attempt")
    base_control_text = base_control.read_text(encoding="utf-8")

    def normalized_function_body(text: str, name: str, *, ignore_write_interval: bool = False) -> tuple[str, ...]:
        match = re.search(rf"(?m)^\s*{re.escape(name)}\s*\{{\n(.*?)^\s*\}}", text, flags=re.DOTALL)
        _require(match is not None, f"missing OpenFOAM function object {name}")
        lines = []
        for line in match.group(1).splitlines():
            item = line.split("//", 1)[0].strip()
            if not item or item.startswith("//") or (ignore_write_interval and item.startswith("writeInterval")):
                continue
            lines.append(re.sub(r"\s+", " ", item))
        return tuple(lines)

    _require(normalized_function_body(base_control_text, "cylinderForces", ignore_write_interval=True)
             == normalized_function_body(control_text, "cylinderForces", ignore_write_interval=True),
             "passive diagnostics changed dimensional cylinder force semantics")
    _require(normalized_function_body(base_control_text, "cylinderForceCoeffs")
             == normalized_function_body(control_text, "cylinderForceCoeffs"),
             "passive diagnostics changed forceCoeffs settings")
    _require("phase1iUMax" in control_text and "phase1iTurbulenceMax" in control_text
             and "phase1iCellVolumes" in control_text,
             "scratch controlDict is missing passive U/turbulence/cell-volume diagnostics")
    syntax_checks = {}
    for path, entry in ((overlay_control, "functions"), (overlay_solution, "PIMPLE")):
        parsed = subprocess.run([foam_dictionary, "-entry", entry, str(path)], cwd=REPO_ROOT,
                                capture_output=True, text=True, timeout=30, check=False)
        _require(parsed.returncode == 0,
                 f"OpenFOAM dictionary syntax check failed for {path.name}: {parsed.stderr.strip()}")
        syntax_checks[path.name] = parsed.returncode
    return {
        "classification": "PASS_PASSIVE_DIAGNOSTICS_NO_PHYSICS_CHANGE",
        "overlay_hashes": {"controlDict": sha256(overlay_control), "fvSolution": sha256(overlay_solution)},
        "unchanged_control_entries": comparisons,
        "unchanged_solver_dictionaries": ["fvSolution.solvers", "fvSolution.relaxationFactors", "PIMPLE existing entries"],
        "enabled": ["forces(cylinder) each time step", "Fluid Co (existing)", "mesh Co log",
                    "max |U|", "max k/omega/nut", "cell volume V snapshots"],
        "openfoam_dictionary_syntax_checks": syntax_checks,
        "mesh_velocity_max": "UNAVAILABLE for passive vector output in this mesh-motion setup",
    }


def _validate_linked_launch_boundaries(structure_contract: Mapping[str, Any],
                                       interface_contract: Mapping[str, Any]) -> None:
    """Validate default-deny maturity plus the exact authorized exception."""
    _require(structure_contract.get("status") == "READY_FOR_DRY_RUN"
             and interface_contract.get("status") == "READY_FOR_DRY_RUN",
             "linked contract maturity status must remain READY_FOR_DRY_RUN")
    common_override = {
        "authority": "contract.json#execution_authorization",
        "mode": "BOUNDED_COUPLING_QUALIFICATION", "max_windows": EXPECTED_MAX_WINDOWS,
        "openfoam_solve_allowed": True, "ancf_time_integration_allowed": True,
        "launcher_preflight_required": True, "production_readiness_claim": False,
    }
    structure_override = common_override
    interface_override = {
        **common_override,
        "precice_run_allowed": True, "new_time_directory_allowed": True,
    }
    structure_boundary = structure_contract.get("launch_boundary", {})
    interface_boundary = interface_contract.get("launch_boundary", {})
    _require(structure_boundary.get("openfoam_solve_allowed") is False
             and structure_boundary.get("ancf_time_integration_allowed") is False
             and structure_boundary.get("bounded_qualification_override") == structure_override,
             "structure contract default-deny boundary or bounded override is inconsistent")
    _require(interface_boundary.get("openfoam_solve_allowed") is False
             and interface_boundary.get("precice_run_allowed") is False
             and interface_boundary.get("ancf_time_integration_allowed") is False
             and interface_boundary.get("new_time_directory_allowed") is False
             and interface_boundary.get("bounded_qualification_override") == interface_override,
             "interface contract default-deny boundary or bounded override is inconsistent")


@dataclass(frozen=True)
class LaunchPlan:
    case_dir: Path
    worker_path: Path
    socket_directory: Path
    run_directory: Path
    fluid_command: tuple[str, ...]
    structure_command: tuple[str, ...]
    log_paths: Mapping[str, str]


def construct_commands(case_dir: Path, worker_path: Path, max_windows: int,
                       fluid_executable: str, run_directory: Path) -> LaunchPlan:
    _require(max_windows == EXPECTED_MAX_WINDOWS, "launcher requires exactly --max-windows 25")
    xml_root = ET.parse(case_dir / "precice-config.xml").getroot()
    sockets = _socket_directory(case_dir, xml_root)
    participant = PARTICIPANT.resolve()
    run_dir = run_directory.resolve()
    # OpenFOAM v10 pimpleFoam has no -endTime option. The preCICE adapter's
    # default end-time control delegates simulation termination to preCICE;
    # preflight pins the adapter and requires max-time-windows=25.
    fluid = (fluid_executable, "-case", str(case_dir.resolve()))
    structure = (
        str(Path(sys.executable).resolve()), str(participant), "--case", str(case_dir.resolve()),
        "--run", "--worker", str(worker_path.resolve()), "--max-windows", str(max_windows),
        "--audit-output", str(run_dir / "structure_audit.json"),
        "--trace-output", str(run_dir / "structure_trace.jsonl"),
    )
    logs = {
        "fluid_stdout": str(run_dir / "fluid.stdout"), "fluid_stderr": str(run_dir / "fluid.stderr"),
        "structure_stdout": str(run_dir / "structure.stdout"), "structure_stderr": str(run_dir / "structure.stderr"),
    }
    return LaunchPlan(case_dir.resolve(), worker_path.resolve(), sockets, run_dir, fluid, structure, logs)


def preflight(case_dir: Path, worker_arg: str, max_windows: int) -> tuple[LaunchPlan, dict[str, Any]]:
    case_dir = case_dir.expanduser().resolve()
    _require(case_dir == DEFAULT_CASE.resolve(), f"only the authoritative HH06 case is accepted: {case_dir}")
    _require(case_dir.is_dir(), f"case directory missing: {case_dir}")
    git_identity = _git_identity()
    _require(git_identity["branch"] == "repair/worker-lineage-implicit-contract-v1",
             f"unexpected source branch for Phase 1I: {git_identity['branch']}")
    _require(git_identity["worktree_clean"], "Phase 1I preflight requires a clean source worktree")
    contract = load_json_strict(case_dir / "contract.json")
    _require(contract.get("status") == "READY_FOR_DRY_RUN",
             "scientific maturity status must remain READY_FOR_DRY_RUN; do not promote it for execution")
    auth = contract.get("execution_authorization")
    _require(isinstance(auth, Mapping), "explicit execution_authorization object is required")
    _require(auth.get("mode") == "BOUNDED_COUPLING_QUALIFICATION", "execution mode is not bounded qualification")
    _require(type(auth.get("max_windows")) is int and auth.get("max_windows") == EXPECTED_MAX_WINDOWS,
             "execution authorization must set integer max_windows=25")
    _require(max_windows == auth.get("max_windows"), "explicit --max-windows must equal the authorized value 25")
    _require(auth.get("participant_entrypoint") == "src/coupling/hh06_structure_0000/structure_0000_participant.py",
             "contract participant entrypoint identity mismatch")

    # The maturity flags stay at READY_FOR_DRY_RUN and their default launch
    # boundaries remain denied. Only an exact, separately declared 25-window
    # override in both linked contracts can authorize the bounded profile.
    structure_contract = load_json_strict(case_dir / "structure_contract.json")
    interface_contract = load_json_strict(case_dir / "interface_contract.json")
    _validate_linked_launch_boundaries(structure_contract, interface_contract)

    coupling = contract.get("coupling", {})
    _require(_numeric(coupling.get("dt_s"), "coupling.dt_s") == EXPECTED_DT, "contract dt changed")
    _require(type(coupling.get("max_iterations")) is int and coupling.get("max_iterations") == EXPECTED_MAX_ITERATIONS,
             "contract max_iterations must remain 20")

    xml_path = case_dir / "precice-config.xml"
    xml_root = ET.parse(xml_path).getroot()
    validator = shutil.which("precice-config-validate")
    _require(validator is not None, "precice-config-validate is unavailable")
    xml_validation = subprocess.run([validator, str(xml_path)], cwd=REPO_ROOT,
                                    capture_output=True, text=True, timeout=30, check=False)
    _require(xml_validation.returncode == 0,
             "installed preCICE rejected the production XML: " + xml_validation.stdout + xml_validation.stderr)
    implicit = _one([item for item in xml_root.iter() if _local(item.tag) == "parallel-implicit"],
                    "parallel-implicit scheme")
    windows_nodes = [item for item in implicit if _local(item.tag) == "max-time-windows"]
    max_time_nodes = [item for item in implicit if _local(item.tag) == "max-time"]
    _require(not max_time_nodes, "bounded profile must use max-time-windows, not an unbounded duration setting")
    windows_node = _one(windows_nodes, "max-time-windows")
    _require(windows_node.attrib.get("value") == str(EXPECTED_MAX_WINDOWS),
             "preCICE max-time-windows must equal 25")
    dt_node = _one([item for item in implicit if _local(item.tag) == "time-window-size"], "time-window-size")
    _require(_xml_numeric(dt_node.attrib.get("value"), "preCICE time-window-size") == EXPECTED_DT,
             "preCICE time-window-size differs from the authorized dt")
    iteration_bounds = _validate_iteration_bounds(implicit)
    force_exchanges = [item for item in implicit if _local(item.tag) == "exchange" and item.attrib.get("data") == "Force"]
    force_exchange = _one(force_exchanges, "Force exchange")
    _require(force_exchange.attrib.get("from") == "Fluid_0000" and force_exchange.attrib.get("to") == "Structure_0000",
             "Force initial exchange participant direction mismatch")
    _require(force_exchange.attrib.get("initialize") == "yes", "Force exchange initialize=yes is required")
    iqn_profile = _validate_iqn_ils_profile(implicit)

    dict_text = (case_dir / "system" / "preciceDict").read_text(encoding="utf-8")
    dict_match = re.search(r'^\s*preciceConfig\s+"?([^";]+)"?\s*;', dict_text, flags=re.MULTILINE)
    _require(dict_match is not None, "system/preciceDict has no preciceConfig entry")
    fluid_config = (case_dir / dict_match.group(1)).resolve()
    _require(fluid_config == xml_path.resolve(), "Fluid preciceDict and Structure preCICE XML paths differ")
    control_text = (case_dir / "system" / "controlDict").read_text(encoding="utf-8")
    _require("preciceAdapter" in control_text
             and "type preciceAdapterFunctionObject;" in control_text
             and 'libs ("libpreciceAdapterFunctionObject.so");' in control_text,
             "OpenFOAM preCICE adapter function object is not enabled in controlDict")

    initial = contract.get("initial_state", {})
    restart = _verify_restart(case_dir, contract, initial)
    passive_diagnostics = _validate_passive_diagnostic_overlay(case_dir, restart)
    worker = _verify_worker(worker_arg, auth)
    adapter = _verify_adapter(auth)
    binding = _verify_binding_qualification()
    participant_audit = _participant_audit(case_dir)

    worker_path = Path(worker["path"])
    active = _case_processes(case_dir, worker_path)
    _require(not active, "a matching HH06 process is already active: " + "; ".join(active))
    socket_path = _socket_directory(case_dir, xml_root)
    socket_users = _active_socket_users(socket_path, xml_path, case_dir)
    _require(not socket_users, "configured preCICE exchange path is in use: " + "; ".join(socket_users))
    socket = _check_socket_directory(socket_path, case_dir)
    fluid_executable = shutil.which("pimpleFoam")
    _require(fluid_executable is not None and os.access(fluid_executable, os.X_OK),
             "pimpleFoam is unavailable; source the configured OpenFOAM environment")
    openfoam_identity = _verify_openfoam_identity(fluid_executable)
    _require(RUN_EVIDENCE_ROOT.parent.is_dir() and os.access(RUN_EVIDENCE_ROOT.parent, os.W_OK | os.X_OK),
             f"qualification log/evidence parent is unavailable: {RUN_EVIDENCE_ROOT.parent}")
    planned_run_dir = RUN_EVIDENCE_ROOT / "<UNIQUE_RUN_ID>"
    plan = construct_commands(case_dir, worker_path, max_windows, fluid_executable, planned_run_dir)
    report = {
        "status": "PASS_PREFLIGHT_ONLY",
        "git": git_identity,
        "scientific_maturity_status": contract["status"],
        "execution_authorization": dict(auth),
        "max_windows": EXPECTED_MAX_WINDOWS,
        "max_iterations": EXPECTED_MAX_ITERATIONS,
        "dt_s": EXPECTED_DT,
        "restart": restart,
        "passive_diagnostics": passive_diagnostics,
        "worker": worker,
        "adapter": adapter,
        "python_precice_binding": binding,
        "participant_audit": participant_audit,
        "openfoam": openfoam_identity,
        "precice": {"xml_path": str(xml_path), "xml_sha256": sha256(xml_path),
                    "socket_directory": socket,
                    "active_socket_processes": socket_users,
                    "max_time_windows": EXPECTED_MAX_WINDOWS, "max_iterations": 20,
                    "min_iterations": iteration_bounds["min_iterations"],
                    "acceleration": iqn_profile,
                    "force_initial_data": force_exchange.attrib.copy(),
                    "configuration_validation": {
                        "command": [validator, str(xml_path)], "return_code": xml_validation.returncode,
                        "stdout": xml_validation.stdout, "stderr": xml_validation.stderr,
                    }},
        "fluid_executable": str(Path(fluid_executable).resolve()),
        "commands_not_executed": {"Fluid": list(plan.fluid_command), "Structure": list(plan.structure_command)},
        "logs": dict(plan.log_paths),
        "checks": {
            "contract_json": True, "bounded_authorization": True, "max_windows_exactly_25": True,
            "source_branch_and_clean_worktree": True,
            "max_iterations_consistent_20": True, "dt_consistent_0p0002": True,
            "frozen_iqn_ils_profile": True,
            "F0_provenance_and_restart_hashes": True, "Force_initialize_yes": True,
            "passive_diagnostics_validated_without_physics_change": True,
            "OpenFOAM_adapter_end_time_control_enabled": True,
            "adapter_runtime_binary_pinned": True, "adapter_source_provenance_resolved": False,
            "worker_source_and_binary_identity": True, "participant_path_and_cli": True,
            "OpenFOAM_10_environment_and_solver_path": True,
            "python_precice_binding_runtime_qualified": True, "socket_path_matches_xml": True,
            "socket_has_no_stale_files_or_active_process": True,
            "OpenFOAM_executable_available": True, "log_directory_available": True,
        },
        "runtime_started": False,
    }
    return plan, report


def _make_run_directory() -> Path:
    RUN_EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    path = RUN_EVIDENCE_ROOT / f"run-{stamp}-{head}"
    path.mkdir(exist_ok=False)
    return path


def _git_identity() -> dict[str, Any]:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=REPO_ROOT,
                            capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain=v1"], cwd=REPO_ROOT,
                            capture_output=True, text=True, timeout=10, check=True).stdout
    return {"branch": branch, "head": head, "worktree_clean": not bool(status.strip()),
            "status_porcelain": status}


def _prepare_runtime_case(source_case: Path, run_dir: Path,
                          restart: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    """Create a fresh, evidence-local runtime copy and apply passive-only diagnostics."""
    _require(source_case.resolve() == DEFAULT_CASE.resolve(),
             "Phase 1I scratch source must be the authoritative HH06 case")
    runtime_case = run_dir / "case"
    _require(not runtime_case.exists(), f"refusing to overwrite runtime case: {runtime_case}")

    ignored_names = {"__pycache__", "postProcessing", "precice-profiling"}

    def ignore_generated_outputs(_directory: str, names: list[str]) -> set[str]:
        return {
            name for name in names
            if name in ignored_names or (name.startswith("precice-") and name.endswith(".log"))
        }

    shutil.copytree(source_case, runtime_case, ignore=ignore_generated_outputs, copy_function=shutil.copy2)

    for name, expected in restart["field_hashes_verified"].items():
        source_file = source_case / "30" / name
        scratch_file = runtime_case / "30" / name
        _require(sha256(source_file) == expected and sha256(scratch_file) == expected,
                 f"scratch restart field differs from frozen source: {name}")
    for name, expected in restart["polyMesh_hashes_verified"].items():
        source_file = source_case / "constant" / "polyMesh" / name
        scratch_file = runtime_case / "constant" / "polyMesh" / name
        _require(sha256(source_file) == expected and sha256(scratch_file) == expected,
                 f"scratch mesh differs from frozen source: {name}")
    numeric_times = sorted(
        entry.name for entry in runtime_case.iterdir()
        if entry.is_dir() and re.fullmatch(r"\d+(?:\.\d+)?", entry.name)
    )
    _require(numeric_times == ["30"], f"scratch case is not an untouched 30 s restart: {numeric_times}")

    contract_path = runtime_case / "contract.json"
    contract = load_json_strict(contract_path)
    provenance = contract["initial_state"]["release_force_provenance"]
    relocated_refs: dict[str, str] = {}
    for key in ("result_json", "provenance_json", "recovery_report"):
        original = (source_case / str(provenance[key])).resolve()
        _require(original.is_file(), f"missing frozen release-force source for scratch case: {original}")
        relocated_refs[key] = os.path.relpath(original, runtime_case)
        provenance[key] = relocated_refs[key]
    contract_path.write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    scratch_restart = _verify_restart(runtime_case, contract, contract.get("initial_state", {}))

    overlay_dir = source_case / "phase1i_observability"
    overlay_records: dict[str, Any] = {}
    overlay_diff: list[str] = []
    for name in ("controlDict", "fvSolution"):
        destination = runtime_case / "system" / name
        before_text = destination.read_text(encoding="utf-8")
        before_sha = sha256(destination)
        overlay_source = overlay_dir / name
        _require(overlay_source.is_file(), f"missing passive observability overlay: {overlay_source}")
        shutil.copy2(overlay_source, destination)
        after_text = destination.read_text(encoding="utf-8")
        overlay_records[name] = {
            "restart_provenance_source_sha256": restart["runtime_configuration_hashes_verified"][f"system/{name}"],
            "copied_baseline_sha256": before_sha,
            "overlay_sha256": sha256(overlay_source),
            "runtime_scratch_sha256": sha256(destination),
            "physics_changed": False,
        }
        overlay_diff.extend(difflib.unified_diff(
            before_text.splitlines(keepends=True), after_text.splitlines(keepends=True),
            fromfile=f"authoritative/system/{name}", tofile=f"scratch/system/{name}",
        ))
    (run_dir / "diagnostic_overlay.diff").write_text("".join(overlay_diff), encoding="utf-8")

    xml_path = runtime_case / "precice-config.xml"
    xml_text = xml_path.read_text(encoding="utf-8")
    xml_root = ET.fromstring(xml_text)
    socket_nodes = [item for item in xml_root.iter() if _local(item.tag) == "sockets"
                    and "exchange-directory" in item.attrib]
    socket_node = _one(socket_nodes, "scratch socket exchange-directory")
    template_socket = socket_node.attrib["exchange-directory"]
    unique_socket = run_dir / "precice-sockets"
    _require(not unique_socket.exists(), f"refusing to reuse Phase 1I socket path: {unique_socket}")
    _require(xml_text.count(template_socket) == 1, "cannot uniquely isolate the scratch preCICE socket path")
    xml_path.write_text(xml_text.replace(template_socket, str(unique_socket)), encoding="utf-8")
    runtime_root = ET.parse(xml_path).getroot()
    implicit = _one([item for item in runtime_root.iter() if _local(item.tag) == "parallel-implicit"],
                    "scratch parallel-implicit scheme")
    iqn_profile = _validate_iqn_ils_profile(implicit)
    validator = shutil.which("precice-config-validate")
    _require(validator is not None, "precice-config-validate is unavailable for the scratch XML")
    validation = subprocess.run([validator, str(xml_path)], cwd=REPO_ROOT,
                                capture_output=True, text=True, timeout=30, check=False)
    _require(validation.returncode == 0,
             "preCICE rejected the isolated scratch XML: " + validation.stdout + validation.stderr)

    foam_dictionary = shutil.which("foamDictionary")
    _require(foam_dictionary is not None, "foamDictionary is unavailable for passive-overlay syntax checks")
    dictionary_checks = {}
    for name, entry in (("controlDict", "functions"), ("fvSolution", "PIMPLE")):
        path = runtime_case / "system" / name
        parsed = subprocess.run([foam_dictionary, "-entry", entry, str(path)], cwd=runtime_case,
                                capture_output=True, text=True, timeout=30, check=False)
        _require(parsed.returncode == 0,
                 f"OpenFOAM dictionary syntax check failed for {name}: {parsed.stderr.strip()}")
        dictionary_checks[name] = {"entry": entry, "return_code": parsed.returncode}

    participant_audit = _participant_audit(runtime_case)
    _require(participant_audit["status"] == "PASS", "scratch Structure participant audit failed")
    config_digest = sha256(xml_path)
    provenance_record = {
        "source_case": str(source_case.resolve()), "runtime_case": str(runtime_case.resolve()),
        "restart_time_s": EXPECTED_RELEASE_TIME, "runtime_numeric_time_directories_before_start": numeric_times,
        "restart_field_hashes_verified": dict(restart["field_hashes_verified"]),
        "scratch_restart_verification": scratch_restart,
        "mesh_hashes_verified": dict(restart["polyMesh_hashes_verified"]),
        "frozen_force_references_relocated": relocated_refs,
        "passive_diagnostic_overlays": overlay_records,
        "precice_config_sha256": config_digest,
        "precice_socket_directory": str(unique_socket), "iqn_ils_profile": iqn_profile,
        "precice_config_validation": {"command": [validator, str(xml_path)],
                                       "return_code": validation.returncode,
                                       "stdout": validation.stdout, "stderr": validation.stderr},
        "openfoam_dictionary_parse_checks": dictionary_checks,
        "participant_offline_audit": participant_audit,
        "mesh_velocity_max": "UNAVAILABLE: no passive runtime vector field is emitted by this displacement-based mesh-motion setup",
    }
    (run_dir / "runtime_case_provenance.json").write_text(
        json.dumps(provenance_record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return runtime_case, provenance_record


def _nonfinite_value(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_nonfinite_value(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_nonfinite_value(item) for item in value)
    return False


def _same_interface_xy(left: Any, right: Any) -> bool:
    if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)):
        return False
    if len(left) < 2 or len(right) < 2:
        return False
    return [float(value) for value in left[:2]] == [float(value) for value in right[:2]]


def _monitor_attempt(record: Mapping[str, Any], state: dict[str, Any]) -> None:
    window = record.get("window_index")
    iteration = record.get("iteration_index")
    _require(type(window) is int and 1 <= window <= EXPECTED_MAX_WINDOWS,
             f"unexpected physical window in live trace: {window!r}")
    _require(type(iteration) is int and 1 <= iteration <= EXPECTED_MAX_ITERATIONS,
             f"coupling iteration is outside the configured cap: {iteration!r}")
    _require(not _nonfinite_value(record), f"NaN/Inf detected in Structure trace window {window} iteration {iteration}")

    transport = record.get("transport_ids", {})
    ids = tuple(transport.get(key) for key in ("sequence", "request_id", "transaction_id"))
    _require(all(type(value) is int for value in ids), "invalid transport identity in live trace")
    for key, value in zip(("sequence", "request_id", "transaction_id"), ids):
        previous_value = state.get(f"last_{key}")
        _require(previous_value is None or value > previous_value,
                 f"non-monotonic transport identity {key}: {previous_value} -> {value}")
        state[f"last_{key}"] = value

    written = record.get("D_written_to_precice_m")
    trial_interface = record.get("D_trial_interface_m")
    _require(isinstance(written, list) and isinstance(trial_interface, list) and written == trial_interface,
             f"D_written != D_trial_interface at window {window} iteration {iteration}")

    physical = record.get("physical_identity")
    _require(isinstance(physical, Mapping), "physical identity tuple missing from live trace")
    _require(_numeric(physical.get("dt_s"), "physical_identity.dt_s") == EXPECTED_DT
             and _numeric(record.get("dt_s"), "trace.dt_s") == EXPECTED_DT,
             "physical window dt differs from the frozen 0.0002 s contract")
    previous = state.get("previous_record")
    if previous is not None:
        previous_window = previous["window_index"]
        if window == previous_window:
            _require(iteration == previous["iteration_index"] + 1,
                     f"coupling iteration discontinuity in window {window}")
            _require(dict(physical) == previous["physical_identity"],
                     f"physical identity changed during retry in window {window}")
            _require(record.get("D_previous_committed_m") == previous.get("D_previous_committed_m"),
                     f"committed interface state changed during physical retry in window {window}")
            _require(_xml_numeric(str(record.get("force_input_read_offset_s")), "retry Force read offset") == EXPECTED_DT,
                     f"retry Force read offset is not dt in window {window}")
            returned = previous.get("returned_force_raw_N")
            force_input = record.get("force_input_vector_raw_N")
            _require(isinstance(returned, list) and force_input == returned,
                     f"retry Force input does not match preceding advance endpoint in window {window}")
        else:
            _require(window == previous_window + 1 and iteration == 1,
                     f"physical window sequence skipped or repeated: {previous_window} -> {window}")
            old_physical = previous["physical_identity"]
            expected_tick_increment = int(round(EXPECTED_DT * 1e9))
            _require(physical.get("global_step") == old_physical.get("global_step") + 1
                     and physical.get("bridge_step") == old_physical.get("bridge_step") + 1
                     and physical.get("integer_tick") == old_physical.get("integer_tick") + expected_tick_increment
                     and math.isclose(_numeric(physical.get("time_s"), "physical_identity.time_s"),
                                      _numeric(old_physical.get("time_s"), "previous physical time") + EXPECTED_DT,
                                      rel_tol=0.0, abs_tol=1e-15)
                     and _numeric(physical.get("dt_s"), "physical_identity.dt_s") == EXPECTED_DT,
                     f"physical identity did not advance by exactly one window at window {window}")
            _require(_same_interface_xy(record.get("D_previous_committed_m"),
                                        previous.get("D_trial_interface_m")),
                     f"new window did not start from the previously accepted ANCF interface state: {window}")
            accepted_force = previous.get("force_read_vector_raw_N")
            force_input = record.get("force_input_vector_raw_N")
            _require(isinstance(accepted_force, list) and force_input == accepted_force,
                     f"next window Force input did not inherit accepted boundary Force at window {window}")
            _require(_xml_numeric(str(record.get("force_input_read_offset_s")), "accepted-boundary Force offset") == 0.0,
                     f"new physical window did not begin from relativeReadTime=0 at window {window}")

    if iteration == 1 and window == 1:
        _require(physical.get("global_step") == 1 and physical.get("bridge_step") == 1
                 and physical.get("integer_tick") == int(round(EXPECTED_DT * 1e9))
                 and math.isclose(_numeric(physical.get("time_s"), "physical_identity.time_s"),
                                  EXPECTED_DT, rel_tol=0.0, abs_tol=1e-15),
                 "first physical window identity does not advance exactly once from release")
        initial_force = record.get("force_input_vector_raw_N")
        _require(isinstance(initial_force, list) and len(initial_force) >= 2
                 and abs(float(initial_force[0]) - EXPECTED_F0[0]) <= 5e-13
                 and abs(float(initial_force[1]) - EXPECTED_F0[1]) <= 5e-13,
                 "first ANCF solve did not receive the qualified physical release Force")
    if record.get("commit_status") == "committed":
        _require(record.get("force_read_offset_s") == 0.0,
                 f"accepted window Force read offset is not zero in window {window}")
        state.setdefault("accepted_windows", set()).add(window)
    else:
        _require(record.get("rollback_request") is True,
                 f"non-committed attempt without rollback in window {window}")
        _require(record.get("force_read_offset_s") == EXPECTED_DT,
                 f"retry Force read offset is not dt in window {window}")
    state["previous_record"] = dict(record)


def _read_new_trace_records(path: Path, offset: int, pending: str,
                            state: dict[str, Any]) -> tuple[int, str, int]:
    if not path.is_file():
        return offset, pending, 0
    with path.open("r", encoding="utf-8") as stream:
        stream.seek(offset)
        new_text = stream.read()
        next_offset = stream.tell()
    lines = (pending + new_text).split("\n")
    new_pending = lines.pop()
    count = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LaunchContractError(f"invalid complete Structure trace line: {exc}") from exc
        _monitor_attempt(record, state)
        count += 1
    return next_offset, new_pending, count


def _process_snapshot(pid: int | None) -> dict[str, Any] | None:
    if pid is None or not Path(f"/proc/{pid}").exists():
        return None
    root = Path(f"/proc/{pid}")
    try:
        argv = (root / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
        exe = os.readlink(root / "exe")
        maps = (root / "maps").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"pid": pid, "present": True, "details": "proc snapshot unavailable"}
    libraries = sorted({
        line.split()[-1].removesuffix(" (deleted)")
        for line in maps.splitlines()
        if line.split() and line.split()[-1].startswith("/")
        and ("libprecice.so" in line or "libpreciceAdapterFunctionObject.so" in line)
    })
    return {"pid": pid, "present": True, "exe": exe, "argv": argv, "coupling_libraries": libraries}


def _find_worker_pid(worker_path: Path) -> int | None:
    proc_root = Path("/proc")
    for entry in proc_root.iterdir() if proc_root.is_dir() else ():
        if not entry.name.isdigit():
            continue
        try:
            if int(entry.name) == os.getpid():
                continue
            executable = Path(os.readlink(entry / "exe")).resolve()
        except OSError:
            continue
        if executable == worker_path.resolve():
            return int(entry.name)
    return None


def _worker_process_matches(pid: int, worker_path: Path) -> bool:
    try:
        executable = os.readlink(f"/proc/{pid}/exe").removesuffix(" (deleted)")
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return Path(executable).resolve() == worker_path.resolve()


def _adapter_build_id(path: Path) -> str | None:
    readelf = shutil.which("readelf")
    if readelf is None:
        return None
    result = subprocess.run([readelf, "-n", str(path)], capture_output=True, text=True, timeout=15, check=False)
    if result.returncode != 0:
        return None
    match = re.search(r"Build ID:\s*([0-9a-fA-F]+)", result.stdout)
    return match.group(1).lower() if match else None


def _terminate_owned(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def run_bounded(plan: LaunchPlan, *, preflight_report: Mapping[str, Any] | None = None,
                launcher_started_utc: str | None = None,
                launcher_started_monotonic: float | None = None) -> dict[str, Any]:
    git_identity = _git_identity()
    _require(git_identity["branch"] == "repair/worker-lineage-implicit-contract-v1",
             f"unexpected source branch before Phase 1I: {git_identity['branch']}")
    _require(git_identity["worktree_clean"], "source worktree must be clean before Phase 1I runtime")

    source_contract = load_json_strict(plan.case_dir / "contract.json")
    authorization = source_contract.get("execution_authorization", {})
    source_restart = _verify_restart(plan.case_dir, source_contract, source_contract.get("initial_state", {}))
    worker = _verify_worker(str(plan.worker_path), authorization)
    adapter = _verify_adapter(authorization)
    binding = _verify_binding_qualification()
    openfoam_identity = _verify_openfoam_identity(plan.fluid_command[0])

    run_dir = _make_run_directory()
    started_utc = launcher_started_utc or datetime.now(timezone.utc).isoformat()
    run_started = launcher_started_monotonic if launcher_started_monotonic is not None else time.monotonic()
    processes: dict[str, subprocess.Popen[str]] = {}
    open_streams: dict[str, Any] = {}
    exit_codes: dict[str, int] = {}
    observed_processes: dict[str, Any] = {}
    worker_pid: int | None = None
    monitor_state: dict[str, Any] = {"accepted_windows": set()}
    trace_offset = 0
    trace_pending = ""
    monitored_attempts = 0
    failure_text: str | None = None
    actual_plan: LaunchPlan | None = None
    runtime_case_record: dict[str, Any] | None = None
    identity_path = run_dir / "runtime_identity.json"

    try:
        runtime_case, runtime_case_record = _prepare_runtime_case(plan.case_dir, run_dir, source_restart)
        actual_plan = construct_commands(runtime_case, plan.worker_path, EXPECTED_MAX_WINDOWS,
                                         plan.fluid_command[0], run_dir)
        active = _active_socket_users(actual_plan.socket_directory,
                                      runtime_case / "precice-config.xml", runtime_case)
        _require(not active, "Phase 1I unique preCICE socket is already in use: " + "; ".join(active))
        socket_record = _check_socket_directory(actual_plan.socket_directory, runtime_case)
        _require(not socket_record["stale_files"], "Phase 1I unique socket directory contains stale state")

        identity = {
            "run_id": run_dir.name, "recorded_at_utc": started_utc,
            "git": git_identity,
            "authorization": {"mode": authorization.get("mode"), "max_windows": EXPECTED_MAX_WINDOWS,
                              "max_iterations": EXPECTED_MAX_ITERATIONS, "dt_s": EXPECTED_DT,
                              "physical_endpoint_global_time_s": EXPECTED_RELEASE_TIME + EXPECTED_MAX_WINDOWS * EXPECTED_DT},
            "restart": {"source_case": str(plan.case_dir), "global_time_s": EXPECTED_RELEASE_TIME,
                        "time_index": source_restart["time_index"], "dt_s": source_restart["dt_s"],
                        "F0_raw_N": source_restart["F0_raw_N"],
                        "field_hashes_sha256": source_restart["field_hashes_verified"],
                        "mesh_hashes_sha256": source_restart["polyMesh_hashes_verified"],
                        "post_preflight_restart_hashes_match": True},
            "worker": worker,
            "fluid_adapter": {**adapter, "build_id": _adapter_build_id(Path(adapter["path"])),
                              "source_provenance_resolved": False},
            "openfoam": openfoam_identity,
            "precice": {"runtime_version": binding["runtime_identity"]["libprecice_runtime_version"],
                        "library_path": binding["runtime_identity"]["libprecice_loaded_path"],
                        "library_sha256": binding["runtime_identity"]["libprecice_sha256"],
                        "configuration_path": str(runtime_case / "precice-config.xml"),
                        "configuration_sha256": runtime_case_record["precice_config_sha256"],
                        "socket_directory": str(actual_plan.socket_directory),
                        "socket_prelaunch_status": socket_record,
                        "iqn_ils_profile": runtime_case_record["iqn_ils_profile"]},
            "python": {"executable": binding["runtime_identity"]["python_executable"],
                       "version": binding["runtime_identity"]["python_version"],
                       "pyprecice_metadata_version": binding["runtime_identity"]["pyprecice_metadata_version"],
                       "module_path": binding["runtime_identity"]["precice_module_path"],
                       "extension_path": binding["runtime_identity"]["cyprecice_extension_path"],
                       "runtime_library": binding["runtime_identity"]["libprecice_loaded_path"]},
            "scratch_case": runtime_case_record,
            "preflight_report": dict(preflight_report) if preflight_report is not None else None,
            "processes": {"Structure": None, "Fluid": None, "worker": None},
            "runtime_started": False,
        }
        identity_path.write_text(json.dumps(identity, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if preflight_report is not None:
            (run_dir / "preflight_report.json").write_text(
                json.dumps(preflight_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        lock_key = hashlib.sha256(str(actual_plan.socket_directory).encode()).hexdigest()[:20]
        lock_path = Path(tempfile.gettempdir()) / f"cfd-ancf-precice-{lock_key}.lock"
        with lock_path.open("a+", encoding="utf-8") as lock_stream:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            actual_plan.socket_directory.mkdir(parents=True, exist_ok=False)
            for name, path in actual_plan.log_paths.items():
                open_streams[name] = Path(path).open("x", encoding="utf-8")
            structure = subprocess.Popen(
                list(actual_plan.structure_command), cwd=actual_plan.case_dir,
                stdout=open_streams["structure_stdout"], stderr=open_streams["structure_stderr"],
                text=True, start_new_session=True,
            )
            processes["Structure"] = structure
            identity["processes"]["Structure"] = {"pid": structure.pid}
            fluid = subprocess.Popen(
                list(actual_plan.fluid_command), cwd=actual_plan.case_dir,
                stdout=open_streams["fluid_stdout"], stderr=open_streams["fluid_stderr"],
                text=True, start_new_session=True,
            )
            processes["Fluid"] = fluid
            identity["processes"]["Fluid"] = {"pid": fluid.pid}
            identity["runtime_started"] = True
            identity_path.write_text(json.dumps(identity, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            while any(process.poll() is None for process in processes.values()):
                try:
                    trace_offset, trace_pending, count = _read_new_trace_records(
                        run_dir / "structure_trace.jsonl", trace_offset, trace_pending, monitor_state)
                    monitored_attempts += count
                    for name, process in processes.items():
                        code = process.poll()
                        if code is not None and code != 0:
                            failure_text = f"{name} participant exited with code {code}"
                            break
                        snapshot = _process_snapshot(process.pid)
                        if snapshot is not None:
                            current = observed_processes.setdefault(name, {}).get(process.pid)
                            if current is None or len(snapshot.get("coupling_libraries", [])) > len(current.get("coupling_libraries", [])):
                                observed_processes[name][process.pid] = snapshot
                    found_worker = _find_worker_pid(plan.worker_path)
                    if found_worker is not None:
                        worker_pid = found_worker
                        snapshot = _process_snapshot(worker_pid)
                        if snapshot is not None:
                            observed_processes.setdefault("worker", {})[worker_pid] = snapshot
                    fluid_snapshot = observed_processes.get("Fluid", {}).get(fluid.pid)
                    if fluid_snapshot:
                        adapter_paths = [Path(value).resolve() for value in fluid_snapshot["coupling_libraries"]
                                         if "libpreciceAdapterFunctionObject.so" in value]
                        if adapter_paths:
                            _require(adapter_paths == [Path(EXPECTED_ADAPTER).resolve()],
                                     f"loaded Fluid adapter path mismatch: {adapter_paths}")
                            _verify_sha(adapter_paths[0], EXPECTED_ADAPTER_SHA256, "loaded Fluid adapter")
                    if failure_text:
                        break
                except Exception as exc:
                    failure_text = f"runtime monitor stopped the qualification: {type(exc).__name__}: {exc}"
                    break
                time.sleep(0.1)

            if failure_text:
                for process in processes.values():
                    _terminate_owned(process)
            exit_codes = {name: process.wait() for name, process in processes.items()}
            # Drain the flushed JSONL trace after both participants exit.
            trace_offset, trace_pending, count = _read_new_trace_records(
                run_dir / "structure_trace.jsonl", trace_offset, trace_pending, monitor_state)
            monitored_attempts += count
            if trace_pending.strip():
                failure_text = failure_text or "Structure trace ended with a partial JSONL record"
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)

        if any(code != 0 for code in exit_codes.values()):
            failure_text = failure_text or f"participant process failure: {exit_codes}"
        if sorted(monitor_state["accepted_windows"]) != list(range(1, EXPECTED_MAX_WINDOWS + 1)):
            failure_text = failure_text or (
                "runtime did not commit exactly the authorized windows: "
                f"{sorted(monitor_state['accepted_windows'])}"
            )
        if monitored_attempts == 0:
            failure_text = failure_text or "no coupling-attempt trace records were produced"
        fluid_snapshot = observed_processes.get("Fluid", {}).get(processes.get("Fluid").pid) if "Fluid" in processes else None
        structure_snapshot = observed_processes.get("Structure", {}).get(processes.get("Structure").pid) if "Structure" in processes else None
        fluid_adapter_paths = [Path(value).resolve() for value in (fluid_snapshot or {}).get("coupling_libraries", [])
                               if "libpreciceAdapterFunctionObject.so" in value]
        structure_precice_paths = [Path(value).resolve() for value in (structure_snapshot or {}).get("coupling_libraries", [])
                                   if "libprecice.so" in value]
        expected_precice = Path(binding["runtime_identity"]["libprecice_loaded_path"]).resolve()
        if fluid_adapter_paths != [Path(EXPECTED_ADAPTER).resolve()]:
            failure_text = failure_text or f"actual loaded Fluid adapter was not confirmed: {fluid_adapter_paths}"
        if structure_precice_paths != [expected_precice]:
            failure_text = failure_text or f"actual Structure libprecice mapping was not confirmed: {structure_precice_paths}"
        if worker_pid is None:
            failure_text = failure_text or "persistent ANCF worker PID was not observed"

    except Exception as exc:
        failure_text = failure_text or f"{type(exc).__name__}: {exc}"
        for process in processes.values():
            _terminate_owned(process)
        exit_codes = {name: process.wait() for name, process in processes.items()}
    finally:
        for stream in open_streams.values():
            stream.close()

    if worker_pid is not None:
        worker_exit_deadline = time.monotonic() + 5.0
        while _worker_process_matches(worker_pid, plan.worker_path) and time.monotonic() < worker_exit_deadline:
            time.sleep(0.1)
    worker_still_running = worker_pid is not None and _worker_process_matches(worker_pid, plan.worker_path)
    if worker_still_running:
        failure_text = failure_text or f"orphan ANCF worker remains after participant shutdown: pid={worker_pid}"
    ended_utc = datetime.now(timezone.utc).isoformat()
    elapsed = time.monotonic() - run_started
    process_cleanup = {
        "run_id": run_dir.name, "launcher_pid": os.getpid(), "participant_pids": {
            name: {"pid": process.pid, "exit_code": exit_codes.get(name),
                   "absent_after_shutdown": not Path(f"/proc/{process.pid}").exists()}
            for name, process in processes.items()
        },
        "worker": {"pid": worker_pid, "absent_after_shutdown": not worker_still_running,
                   "still_running_after_shutdown": worker_still_running,
                   "independent_exit_code_exposed": False},
        "observed_process_runtime_maps": observed_processes,
        "socket_directory": str(actual_plan.socket_directory) if actual_plan else None,
        "socket_contents_after_shutdown": sorted(str(path) for path in actual_plan.socket_directory.rglob("*")
                                                   if path.is_file() or path.is_socket()) if actual_plan and actual_plan.socket_directory.exists() else [],
        "launcher_lock_released": True,
        "exit_codes": exit_codes,
    }
    (run_dir / "process_cleanup.json").write_text(
        json.dumps(process_cleanup, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if identity_path.exists():
        identity = load_json_strict(identity_path)
        identity["runtime_process_observations"] = observed_processes
        identity["process_cleanup"] = process_cleanup
        identity["runtime_ended_at_utc"] = ended_utc
        identity_path.write_text(json.dumps(identity, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    trace_path = run_dir / "structure_trace.jsonl"
    trace_records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()
                     if line.strip()] if trace_path.is_file() else []
    iterations_by_window: dict[str, int] = {}
    cap_windows: list[int] = []
    for record in trace_records:
        window = str(record["window_index"])
        iterations_by_window[window] = max(iterations_by_window.get(window, 0), int(record["iteration_index"]))
        if record.get("convergence_status") == "ACCEPTED_AT_ITERATION_LIMIT":
            cap_windows.append(int(record["window_index"]))
    summary = {
        "classification": "PHASE1I_RUNTIME_COMPLETED" if failure_text is None else "PHASE1I_RUNTIME_STOPPED_OR_FAILED",
        "failure": failure_text, "run_id": run_dir.name,
        "max_windows": EXPECTED_MAX_WINDOWS, "max_iterations": EXPECTED_MAX_ITERATIONS,
        "dt_s": EXPECTED_DT, "endpoint_global_time_s": EXPECTED_RELEASE_TIME + EXPECTED_MAX_WINDOWS * EXPECTED_DT,
        "completed_windows": len(monitor_state["accepted_windows"]),
        "accepted_window_indices": sorted(monitor_state["accepted_windows"]),
        "iterations_per_window": iterations_by_window,
        "iteration_limit_accepted_windows": sorted(set(cap_windows)),
        "coupling_attempts": len(trace_records), "monitored_attempts": monitored_attempts,
        "participant_exit_codes": exit_codes, "wall_clock_seconds": elapsed,
        "started_at_utc": started_utc, "ended_at_utc": ended_utc,
        "commands": {"Fluid": list(actual_plan.fluid_command),
                     "Structure": list(actual_plan.structure_command)} if actual_plan else None,
        "evidence_directory": str(run_dir), "runtime_started": bool(processes),
        "science_validation_claim": False,
    }
    (run_dir / "qualification_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (run_dir / "wall_clock_timing.json").write_text(json.dumps({
        "run_id": run_dir.name, "started_at_utc": started_utc, "ended_at_utc": ended_utc,
        "elapsed_seconds": elapsed, "physical_windows": summary["completed_windows"],
        "coupling_attempts": summary["coupling_attempts"],
    }, indent=2) + "\n", encoding="utf-8")
    if actual_plan is not None and actual_plan.case_dir.exists():
        for log_path in actual_plan.case_dir.glob("precice-*.log"):
            shutil.copy2(log_path, run_dir / log_path.name)
        if (actual_plan.case_dir / "precice-profiling").is_dir():
            shutil.copytree(actual_plan.case_dir / "precice-profiling", run_dir / "precice-profiling")
    fluid_log = run_dir / "fluid.stdout"
    fluid_text = fluid_log.read_text(encoding="utf-8", errors="replace") if fluid_log.is_file() else ""
    cfd_advances = len(re.findall(r"^Time\s*=", fluid_text, flags=re.MULTILINE))
    timing = load_json_strict(run_dir / "wall_clock_timing.json")
    timing["total_cfd_advances"] = cfd_advances
    timing["mean_seconds_per_cfd_advance"] = elapsed / cfd_advances if cfd_advances else None
    timing["mean_seconds_per_coupling_attempt"] = elapsed / len(trace_records) if trace_records else None
    (run_dir / "wall_clock_timing.json").write_text(
        json.dumps(timing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    iqn_lines = [line.strip() for line in fluid_text.splitlines()
                 if re.search(r"IQN|QR3|quasi.?Newton|preconditioner|column|acceleration|WARNING", line, re.IGNORECASE)]
    (run_dir / "iqn_diagnostics.json").write_text(json.dumps({
        "run_id": run_dir.name,
        "source_logs": [str(fluid_log), str(run_dir / "structure.stdout")],
        "warning_count": sum("warning" in line.lower() for line in iqn_lines),
        "captured_diagnostic_line_count": len(iqn_lines),
        "used_column_counts": "NOT_EXPOSED_AS_STRUCTURED_DATA_BY_CURRENT_RUNTIME_LOGS",
        "dropped_or_deleted_column_counts": "NOT_EXPOSED_AS_STRUCTURED_DATA_BY_CURRENT_RUNTIME_LOGS",
        "captured_lines": iqn_lines,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if failure_text is not None:
        raise LaunchContractError(f"Phase 1I stopped without retry: {failure_text}; evidence={run_dir}")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HH06 single-slice bounded qualification preflight/launcher")
    parser.add_argument("--case", type=Path, default=DEFAULT_CASE)
    parser.add_argument("--worker", required=True, help="explicit executable; SHA-pinned, no default")
    parser.add_argument("--max-windows", type=int, required=True, help="must equal the authorized value 25")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true", help="run all checks; start no participant or solver")
    mode.add_argument("--run-bounded", action="store_true", help="explicitly start the authorized 25-window run")
    args = parser.parse_args(argv)
    launcher_started_monotonic = time.monotonic()
    launcher_started_utc = datetime.now(timezone.utc).isoformat()
    try:
        plan, report = preflight(args.case, args.worker, args.max_windows)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if args.preflight_only:
            return 0
        result = run_bounded(plan, preflight_report=report, launcher_started_utc=launcher_started_utc,
                             launcher_started_monotonic=launcher_started_monotonic)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"PRE_RUN_BLOCKED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
