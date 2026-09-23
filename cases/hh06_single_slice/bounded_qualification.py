#!/usr/bin/env python3
"""Fail-closed preflight and exact five-window HH06 launch wrapper.

Preflight-only mode is read-only with respect to the case and starts no solver,
participant, worker, or ANCF process.  Runtime mode is separately opt-in.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
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
EXPECTED_MAX_WINDOWS = 5
EXPECTED_MAX_ITERATIONS = 20
EXPECTED_DT = 0.0002
EXPECTED_RELEASE_TIME = 30.0
EXPECTED_F0 = (0.0655270406544, 0.05872987413554, -2.44420351566e-21)
EXPECTED_F0_RESULT_SHA256 = "6b272f695ebefe28daa176723483f611c42f8d25dbae8d83de928f3790811b8a"
EXPECTED_F0_REPORT_SHA256 = "6737908b9b29f4ff8550ba4353ff88ad90ad5cfc1355a57a885d655f7d3d7b3b"
EXPECTED_F0_PROVENANCE_SHA256 = "1df1d2ca0876372874b1e6ac0eca2296e2f3ab8f8900e0b3903b53f2566e72d2"
BINDING_EVIDENCE = REPO_ROOT / "evidence" / "phase1d6_python_precice_binding" / "qualification.json"
RUN_EVIDENCE_ROOT = REPO_ROOT / "evidence" / "phase1f_bounded_5window"


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
    _require(max_windows == EXPECTED_MAX_WINDOWS, "launcher requires exactly --max-windows 5")
    xml_root = ET.parse(case_dir / "precice-config.xml").getroot()
    sockets = _socket_directory(case_dir, xml_root)
    participant = PARTICIPANT.resolve()
    run_dir = run_directory.resolve()
    # OpenFOAM v10 pimpleFoam has no -endTime option. The preCICE adapter's
    # default end-time control delegates simulation termination to preCICE;
    # preflight pins the adapter and requires max-time-windows=5.
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
    contract = load_json_strict(case_dir / "contract.json")
    _require(contract.get("status") == "READY_FOR_DRY_RUN",
             "scientific maturity status must remain READY_FOR_DRY_RUN; do not promote it for execution")
    auth = contract.get("execution_authorization")
    _require(isinstance(auth, Mapping), "explicit execution_authorization object is required")
    _require(auth.get("mode") == "BOUNDED_COUPLING_QUALIFICATION", "execution mode is not bounded qualification")
    _require(type(auth.get("max_windows")) is int and auth.get("max_windows") == EXPECTED_MAX_WINDOWS,
             "execution authorization must set integer max_windows=5")
    _require(max_windows == auth.get("max_windows"), "explicit --max-windows must equal the authorized value 5")
    _require(auth.get("participant_entrypoint") == "src/coupling/hh06_structure_0000/structure_0000_participant.py",
             "contract participant entrypoint identity mismatch")

    # The maturity flags stay at READY_FOR_DRY_RUN and their default launch
    # boundaries remain denied. Only an exact, separately declared five-window
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
             "preCICE max-time-windows must equal 5")
    dt_node = _one([item for item in implicit if _local(item.tag) == "time-window-size"], "time-window-size")
    _require(_xml_numeric(dt_node.attrib.get("value"), "preCICE time-window-size") == EXPECTED_DT,
             "preCICE time-window-size differs from the authorized dt")
    iterations_node = _one([item for item in implicit if _local(item.tag) == "max-iterations"], "max-iterations")
    _require(iterations_node.attrib.get("value") == "20", "preCICE max-iterations must remain 20")
    force_exchanges = [item for item in implicit if _local(item.tag) == "exchange" and item.attrib.get("data") == "Force"]
    force_exchange = _one(force_exchanges, "Force exchange")
    _require(force_exchange.attrib.get("from") == "Fluid_0000" and force_exchange.attrib.get("to") == "Structure_0000",
             "Force initial exchange participant direction mismatch")
    _require(force_exchange.attrib.get("initialize") == "yes", "Force exchange initialize=yes is required")

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
    _require(RUN_EVIDENCE_ROOT.parent.is_dir() and os.access(RUN_EVIDENCE_ROOT.parent, os.W_OK | os.X_OK),
             f"qualification log/evidence parent is unavailable: {RUN_EVIDENCE_ROOT.parent}")
    planned_run_dir = RUN_EVIDENCE_ROOT / "<UNIQUE_RUN_ID>"
    plan = construct_commands(case_dir, worker_path, max_windows, fluid_executable, planned_run_dir)
    report = {
        "status": "PASS_PREFLIGHT_ONLY",
        "scientific_maturity_status": contract["status"],
        "execution_authorization": dict(auth),
        "max_windows": EXPECTED_MAX_WINDOWS,
        "max_iterations": EXPECTED_MAX_ITERATIONS,
        "dt_s": EXPECTED_DT,
        "restart": restart,
        "worker": worker,
        "adapter": adapter,
        "python_precice_binding": binding,
        "participant_audit": participant_audit,
        "precice": {"xml_path": str(xml_path), "socket_directory": socket,
                    "active_socket_processes": socket_users,
                    "max_time_windows": EXPECTED_MAX_WINDOWS, "max_iterations": 20,
                    "force_initial_data": force_exchange.attrib.copy(),
                    "configuration_validation": {
                        "command": [validator, str(xml_path)], "return_code": xml_validation.returncode,
                        "stdout": xml_validation.stdout, "stderr": xml_validation.stderr,
                    }},
        "fluid_executable": str(Path(fluid_executable).resolve()),
        "commands_not_executed": {"Fluid": list(plan.fluid_command), "Structure": list(plan.structure_command)},
        "logs": dict(plan.log_paths),
        "checks": {
            "contract_json": True, "bounded_authorization": True, "max_windows_exactly_5": True,
            "max_iterations_consistent_20": True, "dt_consistent_0p0002": True,
            "F0_provenance_and_restart_hashes": True, "Force_initialize_yes": True,
            "OpenFOAM_adapter_end_time_control_enabled": True,
            "adapter_runtime_binary_pinned": True, "adapter_source_provenance_resolved": False,
            "worker_source_and_binary_identity": True, "participant_path_and_cli": True,
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
    path = RUN_EVIDENCE_ROOT / f"run-{stamp}-pid{os.getpid()}"
    path.mkdir(exist_ok=False)
    return path


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


def run_bounded(plan: LaunchPlan) -> dict[str, Any]:
    lock_key = hashlib.sha256(str(plan.socket_directory).encode()).hexdigest()[:20]
    lock_path = Path(tempfile.gettempdir()) / f"cfd-ancf-precice-{lock_key}.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_stream:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LaunchContractError("another bounded launcher holds the same preCICE socket lock") from exc
        _check_socket_directory(plan.socket_directory, plan.case_dir)
        plan.socket_directory.mkdir(parents=True, exist_ok=True)
        _require(os.access(plan.socket_directory, os.W_OK | os.X_OK), "preCICE socket directory is not writable")
        run_dir = _make_run_directory()
        actual_plan = construct_commands(plan.case_dir, plan.worker_path, EXPECTED_MAX_WINDOWS,
                                         plan.fluid_command[0], run_dir)
        open_streams: dict[str, Any] = {}
        processes: dict[str, subprocess.Popen[str]] = {}
        try:
            for name, path in actual_plan.log_paths.items():
                open_streams[name] = Path(path).open("x", encoding="utf-8")
            structure = subprocess.Popen(
                list(actual_plan.structure_command), cwd=actual_plan.case_dir,
                stdout=open_streams["structure_stdout"], stderr=open_streams["structure_stderr"],
                text=True, start_new_session=True,
            )
            processes["Structure"] = structure
            fluid = subprocess.Popen(
                list(actual_plan.fluid_command), cwd=actual_plan.case_dir,
                stdout=open_streams["fluid_stdout"], stderr=open_streams["fluid_stderr"],
                text=True, start_new_session=True,
            )
            processes["Fluid"] = fluid
            failure: tuple[str, int] | None = None
            while any(process.poll() is None for process in processes.values()):
                for name, process in processes.items():
                    code = process.poll()
                    if code is not None and code != 0:
                        failure = (name, code)
                        break
                if failure:
                    break
                time.sleep(0.1)
            if failure:
                for process in processes.values():
                    _terminate_owned(process)
            exit_codes = {name: process.wait() for name, process in processes.items()}
        except Exception:
            for process in processes.values():
                _terminate_owned(process)
            raise
        finally:
            for stream in open_streams.values():
                stream.close()
        summary = {
            "classification": "BOUNDED_RUNTIME_COMPLETED" if all(code == 0 for code in exit_codes.values()) else "BOUNDED_RUNTIME_FAILED",
            "max_windows": EXPECTED_MAX_WINDOWS, "exit_codes": exit_codes,
            "commands": {"Fluid": list(actual_plan.fluid_command), "Structure": list(actual_plan.structure_command)},
            "logs": dict(actual_plan.log_paths), "runtime_started": True,
            "science_validation_claim": False,
        }
        (run_dir / "launch_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        if any(code != 0 for code in exit_codes.values()):
            raise LaunchContractError(f"bounded coupling processes failed: {exit_codes}; logs={run_dir}")
        return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HH06 single-slice bounded qualification preflight/launcher")
    parser.add_argument("--case", type=Path, default=DEFAULT_CASE)
    parser.add_argument("--worker", required=True, help="explicit executable; SHA-pinned, no default")
    parser.add_argument("--max-windows", type=int, required=True, help="must equal the authorized value 5")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true", help="run all checks; start no participant or solver")
    mode.add_argument("--run-bounded", action="store_true", help="explicitly start the authorized five-window run")
    args = parser.parse_args(argv)
    try:
        plan, report = preflight(args.case, args.worker, args.max_windows)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if args.preflight_only:
            return 0
        result = run_bounded(plan)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"PRE_RUN_BLOCKED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
