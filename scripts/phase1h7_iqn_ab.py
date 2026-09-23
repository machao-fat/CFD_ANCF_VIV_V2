#!/usr/bin/env python3
"""One-shot, scratch-isolated Phase 1H.7 constant-relaxation vs IQN-ILS run.

The script stages two independent cases from the exact 30 s restart, performs
the same fail-closed checks for both, then executes baseline followed by IQN-ILS
once. It never launches the authoritative case and never changes its files.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Mapping
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[1]
CASE_SOURCE = REPO / "cases" / "hh06_single_slice"
PARTICIPANT = REPO / "src" / "coupling" / "hh06_structure_0000" / "structure_0000_participant.py"
BASELINE_XML = CASE_SOURCE / "precice-config.xml"
IQN_XML = REPO / "evidence" / "phase1h6_iqn_ils_candidate" / "precice-config.xml"
EVIDENCE_ROOT = REPO / "evidence" / "phase1h7_iqn_comparison"
EXPECTED_BASELINE_XML_SHA = "e4987ec7d768517feefe312a9ddcbd391ff052981aa84bae6934b555e97d1f71"
EXPECTED_IQN_XML_SHA = "cd943e0cfa04d7937d6a421305a032a642ae5a80d7e842b6a1651ec11517bff9"
EXPECTED_WORKER_SOURCE_SHA = "c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e"
EXPECTED_WORKER_BINARY_SHA = "3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596"
EXPECTED_ADAPTER_SHA = "26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572"
EXPECTED_ADAPTER = Path(
    "/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/"
    "libpreciceAdapterFunctionObject.so"
)
EXPECTED_HEAD = "02d9a1f180082e83bcc9f7acdcb090502262b2d1"
EXPECTED_DT = 0.0002
EXPECTED_F0 = (0.0655270406544, 0.05872987413554, -2.44420351566e-21)
EXPECTED_WINDOWS = 5
EXPECTED_ITERATIONS = 20
EXPECTED_PYTHON = Path("/usr/bin/python3.10")
TIMEOUT_S = 1800.0
VARIANTS = ("baseline", "iqn_ils")

sys.path.insert(0, str(CASE_SOURCE))
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
import bounded_qualification as bq  # noqa: E402


class ABError(RuntimeError):
    """Fail-closed Phase 1H.7 staging or run error."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ABError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "x" if exclusive else "w"
    with path.open(mode, encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def read_json(path: Path) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number {value}")

    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def finite_tree(value: Any, path: str = "root") -> None:
    if isinstance(value, float):
        require(math.isfinite(value), f"non-finite trace value at {path}: {value}")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            finite_tree(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            finite_tree(item, f"{path}[{index}]")


def load_bounded_module() -> Any:
    return bq


def git_identity() -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)
        require(result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    status = git("status", "--porcelain=v1")
    head = git("rev-parse", "HEAD")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    require(branch == "repair/worker-lineage-implicit-contract-v1", f"unexpected branch: {branch}")
    require(head == EXPECTED_HEAD, f"HEAD differs from reviewed Phase 1H.6 baseline: {head}")
    return {"branch": branch, "head": head, "worktree_clean": not bool(status),
            "status_porcelain": status.splitlines()}


def openfoam_identity() -> dict[str, str]:
    executable = shutil.which("pimpleFoam")
    require(executable is not None and os.access(executable, os.X_OK),
            "pimpleFoam unavailable; source the qualified OpenFOAM 10 environment")
    version_command = shutil.which("foamVersion")
    if version_command:
        version = subprocess.run([version_command], capture_output=True, text=True, check=False)
        require(version.returncode == 0, f"foamVersion failed: {version.stderr.strip()}")
        version_text = version.stdout.strip()
    else:
        version_text = os.environ.get("WM_PROJECT_VERSION", "")
    require(version_text.startswith("10"), f"OpenFOAM runtime is not version 10: {version_text!r}")
    return {"version": version_text, "pimpleFoam": str(Path(executable).resolve())}


def runtime_identities(worker: Path) -> dict[str, Any]:
    require(Path(sys.executable).resolve() == EXPECTED_PYTHON,
            f"must run with {EXPECTED_PYTHON}, got {sys.executable}")
    require(EXPECTED_ADAPTER.is_file(), f"qualified adapter missing: {EXPECTED_ADAPTER}")
    adapter_sha = sha256(EXPECTED_ADAPTER)
    require(adapter_sha == EXPECTED_ADAPTER_SHA, f"adapter SHA mismatch: {adapter_sha}")
    os.environ["ANCF_PRECICE_ADAPTER_LIBRARY"] = str(EXPECTED_ADAPTER)
    os.environ["ANCF_ADAPTER_RUNTIME_PATH"] = str(EXPECTED_ADAPTER)
    os.environ["ANCF_ADAPTER_RUNTIME_SHA256"] = adapter_sha
    adapter_dir = str(EXPECTED_ADAPTER.parent)
    old_library_path = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = adapter_dir + (":" + old_library_path if old_library_path else "")

    worker_check = bq._verify_worker(str(worker), bq.load_json_strict(CASE_SOURCE / "contract.json")["execution_authorization"])
    adapter_check = bq._verify_adapter(bq.load_json_strict(CASE_SOURCE / "contract.json")["execution_authorization"])
    binding = bq._verify_binding_qualification()
    precice_version = subprocess.run(["precice-version"], capture_output=True, text=True, check=False)
    require(precice_version.returncode == 0 and precice_version.stdout.startswith("3.4.1;"),
            f"preCICE runtime identity mismatch: {precice_version.stdout.strip()} {precice_version.stderr.strip()}")
    readelf = shutil.which("readelf")
    require(readelf is not None, "readelf unavailable for adapter Build ID verification")
    notes = subprocess.run([readelf, "-n", str(EXPECTED_ADAPTER)], capture_output=True, text=True, check=False)
    require(notes.returncode == 0, "readelf failed on qualified Fluid adapter")
    build_match = re.search(r"Build ID:\s*(\S+)", notes.stdout)
    require(build_match is not None and build_match.group(1) == "e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b",
            "Fluid adapter Build ID differs from Phase 1C.7C qualification")
    foam = openfoam_identity()

    source_hashes = {
        "worker_source": sha256(REPO / "src/ancf/ancf_worker_main.cpp"),
        "participant": sha256(PARTICIPANT),
        "precice_backend": sha256(REPO / "src/coupling/arbitrary_n_live_orchestration_v1/precice_backend.py"),
        "coordinator": sha256(REPO / "src/coupling/arbitrary_n_live_orchestration_v1/coordinator.py"),
        "bounded_qualification": sha256(CASE_SOURCE / "bounded_qualification.py"),
    }
    require(source_hashes["worker_source"] == EXPECTED_WORKER_SOURCE_SHA,
            f"worker source SHA mismatch: {source_hashes['worker_source']}")
    active = active_coupling_processes()
    require(not active, f"unrelated or stale coupling process is active; refusing A/B runtime: {active}")
    active_workers = find_worker_processes(worker)
    require(not active_workers, f"qualified worker process already active: {active_workers}")
    return {
        "git": git_identity(), "worker": worker_check, "adapter": {
            **adapter_check, "path": str(EXPECTED_ADAPTER), "build_id": build_match.group(1),
            "source_provenance_resolved": False,
        },
        "precice": {"version_information": precice_version.stdout.strip()},
        "python_precice_binding": binding,
        "openfoam": foam,
        "source_sha256": source_hashes,
    }


def numeric_time_dirs(case_dir: Path) -> list[str]:
    return sorted((entry.name for entry in case_dir.iterdir()
                   if entry.is_dir() and re.fullmatch(r"\d+(?:\.\d+)?", entry.name)),
                  key=float)


def active_coupling_processes() -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            comm = (entry / "comm").read_text(encoding="utf-8").strip()
            argv = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
        except OSError:
            continue
        if comm == "pimpleFoam" or "structure_0000_participant.py" in argv:
            active.append({"pid": int(entry.name), "comm": comm, "cmdline": argv})
    return active


def _case_ignore(directory: str, names: list[str]) -> set[str]:
    base = Path(directory).resolve()
    ignored = {"__pycache__", "postProcessing", "precice-profiling"}
    if base == CASE_SOURCE.resolve():
        ignored.update(name for name in names if name.startswith("precice-") and name.endswith(".log"))
    return {name for name in names if name in ignored}


def copy_release_evidence(run_dir: Path, contract: Mapping[str, Any]) -> dict[str, str]:
    provenance = contract["initial_state"]["release_force_provenance"]
    sources = {
        "result_json": (CASE_SOURCE / provenance["result_json"]).resolve(),
        "provenance_json": (CASE_SOURCE / provenance["provenance_json"]).resolve(),
        "recovery_report": (CASE_SOURCE / provenance["recovery_report"]).resolve(),
    }
    expected = {
        "result_json": provenance["result_json_sha256"],
        "provenance_json": provenance["provenance_json_sha256"],
        "recovery_report": provenance["recovery_report_sha256"],
    }
    result: dict[str, str] = {}
    for key, source in sources.items():
        require(source.is_file() and sha256(source) == expected[key], f"frozen F0 evidence mismatch: {source}")
        if key == "recovery_report":
            dest = run_dir / "docs" / source.name
        else:
            dest = run_dir / "evidence" / "phase1c7a_release_force" / source.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        require(sha256(dest) == expected[key], f"copied F0 evidence hash mismatch: {dest}")
        result[key] = str(dest)
    return result


def accel_element(root: ET.Element) -> ET.Element:
    scheme = bq._one([node for node in root.iter() if bq._local(node.tag) == "parallel-implicit"],
                     "parallel-implicit coupling scheme")
    return bq._one([node for node in scheme if "acceleration" in node.tag], "acceleration element")


def config_acceleration_check(config_path: Path, variant: str) -> dict[str, Any]:
    root = ET.parse(config_path).getroot()
    scheme = bq._one([node for node in root.iter() if bq._local(node.tag) == "parallel-implicit"],
                     "parallel-implicit coupling scheme")
    windows = bq._one([node for node in scheme if bq._local(node.tag) == "max-time-windows"], "max-time-windows")
    dt = bq._one([node for node in scheme if bq._local(node.tag) == "time-window-size"], "time-window-size")
    maximum = bq._one([node for node in scheme if bq._local(node.tag) == "max-iterations"], "max-iterations")
    minimum = bq._one([node for node in scheme if bq._local(node.tag) == "min-iterations"], "min-iterations")
    require(windows.attrib.get("value") == "5", f"{variant}: max-time-windows must be 5")
    require(bq._xml_numeric(dt.attrib.get("value"), "time-window-size") == EXPECTED_DT,
            f"{variant}: timestep differs from 0.0002 s")
    require(maximum.attrib.get("value") == "20" and minimum.attrib.get("value") == "2",
            f"{variant}: implicit iteration bounds changed")
    acceleration = accel_element(root)
    kind = bq._local(acceleration.tag)
    if variant == "baseline":
        require(kind == "constant", "baseline must use constant relaxation")
        relax = bq._one([node for node in acceleration if bq._local(node.tag) == "relaxation"], "relaxation")
        require(relax.attrib.get("value") == "0.2", "baseline relaxation differs from 0.2")
        settings: dict[str, Any] = {"type": kind, "relaxation": 0.2}
    else:
        require(kind == "IQN-ILS", "candidate must use IQN-ILS")
        initial = bq._one([node for node in acceleration if bq._local(node.tag) == "initial-relaxation"],
                          "initial-relaxation")
        maximum_used = bq._one([node for node in acceleration if bq._local(node.tag) == "max-used-iterations"],
                               "max-used-iterations")
        reused = bq._one([node for node in acceleration if bq._local(node.tag) == "time-windows-reused"],
                         "time-windows-reused")
        filter_node = bq._one([node for node in acceleration if bq._local(node.tag) == "filter"], "filter")
        preconditioner = bq._one([node for node in acceleration if bq._local(node.tag) == "preconditioner"],
                                 "preconditioner")
        primary = [node.attrib.get("name") for node in acceleration if bq._local(node.tag) == "data"]
        require(acceleration.attrib.get("reduced-time-grid") == "true", "IQN reduced-time-grid must be true")
        require(initial.attrib.get("value") == "0.2" and initial.attrib.get("enforce") == "true",
                "IQN initial relaxation must be 0.2 with enforce=true")
        require(maximum_used.attrib.get("value") == "1" and reused.attrib.get("value") == "1",
                "IQN history limits differ from the reviewed candidate")
        require(primary == ["Displacement", "Force"], "IQN primary data must be Displacement and Force")
        require(filter_node.attrib.get("type") == "QR3" and filter_node.attrib.get("limit") == "1e-2",
                "IQN filter differs from the reviewed QR3 candidate")
        require(preconditioner.attrib.get("type") == "residual-sum",
                "IQN preconditioner differs from residual-sum")
        settings = {
            "type": kind, "initial_relaxation": 0.2, "enforce": True,
            "max_used_iterations": 1, "time_windows_reused": 1,
            "primary_data": primary, "filter": filter_node.attrib.copy(),
            "preconditioner": preconditioner.attrib.copy(),
            "reduced_time_grid": True,
        }
    force_exchange = bq._one([node for node in scheme if bq._local(node.tag) == "exchange"
                              and node.attrib.get("data") == "Force"], "Force exchange")
    require(force_exchange.attrib.get("initialize") == "yes", f"{variant}: initial Force exchange disabled")
    return {"acceleration": settings, "time_window_size_s": EXPECTED_DT,
            "max_time_windows": 5, "max_iterations": 20,
            "force_initialize": force_exchange.attrib.get("initialize")}


def normalized_config(text: str) -> str:
    replaced, count = re.subn(
        r"(?s)    <acceleration:(?P<kind>constant|IQN-ILS)\b.*?</acceleration:(?P=kind)>",
        "<ACCELERATION_BLOCK>", text, count=1,
    )
    require(count == 1, "cannot isolate exactly one acceleration block in the XML")
    return replaced


def stage_case(source_xml: Path, destination: Path, socket_dir: Path, variant: str) -> dict[str, Any]:
    require(not destination.exists(), f"scratch case target already exists; refusing overwrite: {destination}")
    require(numeric_time_dirs(CASE_SOURCE) == ["30"], "authoritative case is not a clean exact 30 s restart")
    shutil.copytree(CASE_SOURCE, destination, ignore=_case_ignore)
    config = destination / "precice-config.xml"
    source_text = source_xml.read_text(encoding="utf-8")
    old_paths = re.findall(r'exchange-directory="([^"]+)"', source_text)
    require(len(old_paths) == 1, f"{variant}: expected one socket exchange-directory")
    require(source_text.count(old_paths[0]) == 1, f"{variant}: socket path occurrence is ambiguous")
    config_text = source_text.replace(old_paths[0], str(socket_dir.resolve()), 1)
    config.write_text(config_text, encoding="utf-8", newline="")
    return {"case_dir": str(destination.resolve()), "source_xml": str(source_xml.resolve()),
            "source_xml_sha256": sha256(source_xml), "scratch_xml_sha256": sha256(config),
            "scratch_contract_sha256": sha256(destination / "contract.json"),
            "scratch_precice_dict_sha256": sha256(destination / "system" / "preciceDict"),
            "socket_directory": str(socket_dir.resolve()),
            "acceleration": config_acceleration_check(config, variant)}


def make_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                           capture_output=True, text=True, check=True).stdout.strip()
    return f"run-{stamp}-{short}-pid{os.getpid()}"


def prepare(worker: Path, timeout_s: float) -> Path:
    identities = runtime_identities(worker)
    require(sha256(BASELINE_XML) == EXPECTED_BASELINE_XML_SHA,
            "current production baseline XML differs from the accepted Phase 1H.6 baseline")
    require(sha256(IQN_XML) == EXPECTED_IQN_XML_SHA,
            "reviewed Phase 1H.6 IQN-ILS candidate hash mismatch")
    source_contract = bq.load_json_strict(CASE_SOURCE / "contract.json")
    source_initial = source_contract["initial_state"]
    source_restart = bq._verify_restart(CASE_SOURCE, source_contract, source_initial)
    baseline_settings = config_acceleration_check(BASELINE_XML, "baseline")
    candidate_settings = config_acceleration_check(IQN_XML, "iqn_ils")
    baseline_text = BASELINE_XML.read_text(encoding="utf-8")
    candidate_text = IQN_XML.read_text(encoding="utf-8")
    require(normalized_config(baseline_text) == normalized_config(candidate_text),
            "baseline and IQN source XML differ outside the acceleration block")

    run_id = make_run_id()
    run_dir = EVIDENCE_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    copied_f0 = copy_release_evidence(run_dir, source_contract)
    socket_dir = run_dir / "precice-sockets"
    socket_dir.mkdir()
    scratch_root = run_dir

    variants: dict[str, Any] = {}
    for name, xml in (("baseline", BASELINE_XML), ("iqn_ils", IQN_XML)):
        variant_dir = run_dir / name
        variant_dir.mkdir()
        case_dir = variant_dir / "case"
        variants[name] = stage_case(xml, case_dir, socket_dir, name)
    baseline_scratch_text = Path(variants["baseline"]["case_dir"], "precice-config.xml").read_text(encoding="utf-8")
    iqn_scratch_text = Path(variants["iqn_ils"]["case_dir"], "precice-config.xml").read_text(encoding="utf-8")
    require(normalized_config(baseline_scratch_text) == normalized_config(iqn_scratch_text),
            "scratch configs differ outside the acceleration block")
    require(variants["baseline"]["scratch_contract_sha256"] == variants["iqn_ils"]["scratch_contract_sha256"],
            "scratch case contracts differ between A/B runs")

    preflight: dict[str, Any] = {}
    for name in VARIANTS:
        preflight[name] = verify_scratch_case(Path(variants[name]["case_dir"]), name, worker,
                                               expected_restart=source_restart)
    manifest = {
        "status": "PREPARED_FOR_ONE_SHOT_EXECUTION",
        "run_id": run_id,
        "run_directory": str(run_dir.resolve()),
        "scratch_root": str(scratch_root.resolve()),
        "execution_authorization": {"mode": "BOUNDED_COUPLING_QUALIFICATION", "max_windows": 5},
        "dt_s": EXPECTED_DT, "max_iterations": EXPECTED_ITERATIONS,
        "baseline_source_xml": str(BASELINE_XML), "iqn_source_xml": str(IQN_XML),
        "baseline_source_xml_sha256": sha256(BASELINE_XML),
        "iqn_source_xml_sha256": sha256(IQN_XML),
        "scratch_xml_sha256": {name: variants[name]["scratch_xml_sha256"] for name in VARIANTS},
        "only_acceleration_differs_after_common_run_socket_path": True,
        "socket_directory": str(socket_dir.resolve()),
        "f0_evidence_copies": copied_f0,
        "source_restart": source_restart,
        "runtime_identities": identities,
        "variants": variants,
        "preflight": preflight,
        "timeout_s_per_run": timeout_s,
        "participants_not_started": True,
    }
    write_json(run_dir / "preparation_manifest.json", manifest, exclusive=True)
    return run_dir


def verify_scratch_case(case_dir: Path, variant: str, worker: Path,
                        expected_restart: Mapping[str, Any] | None = None) -> dict[str, Any]:
    case_dir = case_dir.resolve()
    try:
        case_dir.relative_to(REPO)
    except ValueError as exc:
        raise ABError(f"scratch case escapes repository evidence root: {case_dir}") from exc
    contract = bq.load_json_strict(case_dir / "contract.json")
    require(contract.get("status") == "READY_FOR_DRY_RUN", "case maturity must remain READY_FOR_DRY_RUN")
    auth = contract.get("execution_authorization", {})
    require(auth.get("mode") == "BOUNDED_COUPLING_QUALIFICATION" and auth.get("max_windows") == 5,
            "five-window execution authorization mismatch")
    coupling = contract.get("coupling", {})
    require(coupling.get("dt_s") == EXPECTED_DT and coupling.get("max_iterations") == EXPECTED_ITERATIONS,
            "contract dt/max-iterations mismatch")
    bq._validate_linked_launch_boundaries(bq.load_json_strict(case_dir / "structure_contract.json"),
                                          bq.load_json_strict(case_dir / "interface_contract.json"))
    config = case_dir / "precice-config.xml"
    variant_settings = config_acceleration_check(config, variant)
    validator = shutil.which("precice-config-validate")
    require(validator is not None, "precice-config-validate unavailable")
    validation = subprocess.run([validator, str(config)], cwd=REPO, capture_output=True, text=True,
                                timeout=30, check=False)
    require(validation.returncode == 0, f"{variant}: preCICE 3.4.1 XML validation failed: "
            f"{validation.stdout}{validation.stderr}")
    require(not re.search(r"\bwarning\b", validation.stdout + validation.stderr, flags=re.IGNORECASE),
            f"{variant}: parser warning emitted: {validation.stdout}{validation.stderr}")

    restart = bq._verify_restart(case_dir, contract, contract["initial_state"])
    if expected_restart is not None:
        require(restart["F0_raw_N"] == expected_restart["F0_raw_N"], f"{variant}: F0 differs from source")
        require(restart["field_hashes_verified"] == expected_restart["field_hashes_verified"],
                f"{variant}: restart field hashes differ from source")
        require(restart["polyMesh_hashes_verified"] == expected_restart["polyMesh_hashes_verified"],
                f"{variant}: mesh hashes differ from source")
    worker_identity = bq._verify_worker(str(worker), auth)
    adapter_identity = bq._verify_adapter(auth)
    binding = bq._verify_binding_qualification()
    audit = bq._participant_audit(case_dir)
    process_matches = bq._case_processes(case_dir, worker)
    require(not process_matches, f"{variant}: matching participant/worker process already active: {process_matches}")
    xml_root = ET.parse(config).getroot()
    socket_dir = bq._socket_directory(case_dir, xml_root)
    socket_state = bq._check_socket_directory(socket_dir, case_dir)
    socket_users = bq._active_socket_users(socket_dir, config, case_dir)
    require(not socket_users, f"{variant}: socket path has an active user: {socket_users}")
    active = active_coupling_processes()
    require(not active, f"{variant}: active Fluid/Structure process detected before launch: {active}")
    require(numeric_time_dirs(case_dir) == ["30"],
            f"{variant}: scratch restart is not a clean time-30 case: {numeric_time_dirs(case_dir)}")
    return {
        "status": "PASS_PREFLIGHT_ONLY", "case_dir": str(case_dir),
        "restart": restart, "worker": worker_identity,
        "adapter": adapter_identity, "python_precice_binding": binding,
        "participant_audit": audit, "configuration_validation": {
            "command": [validator, str(config)], "return_code": validation.returncode,
            "stdout": validation.stdout, "stderr": validation.stderr,
        },
        "settings": variant_settings, "socket": socket_state,
        "openfoam_executable": openfoam_identity()["pimpleFoam"],
        "active_socket_processes": socket_users, "numeric_time_directories": ["30"],
        "runtime_started": False,
    }


def loaded_runtime(pid: int) -> dict[str, Any]:
    maps_path = Path(f"/proc/{pid}/maps")
    try:
        maps = maps_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    paths: set[Path] = set()
    for line in maps.splitlines():
        fields = line.split()
        if fields and fields[-1].startswith("/") and ("libprecice.so" in fields[-1]
                                                        or "libpreciceAdapterFunctionObject.so" in fields[-1]):
            paths.add(Path(fields[-1].removesuffix(" (deleted)")).resolve())
    result: dict[str, Any] = {}
    for path in sorted(paths):
        if not path.is_file():
            continue
        result[str(path)] = {"sha256": sha256(path)}
    return result


def find_worker_processes(worker: Path) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            exe = Path(os.readlink(entry / "exe")).resolve()
            if exe != worker.resolve():
                continue
            stat = (entry / "stat").read_text(encoding="utf-8").split()
            cmd = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
            matches.append({"pid": int(entry.name), "ppid": int(stat[3]), "cmdline": cmd})
        except (OSError, ValueError, IndexError):
            continue
    return matches


def terminate_owned(processes: Mapping[str, subprocess.Popen[str]]) -> dict[str, int | None]:
    for process in processes.values():
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for process in processes.values():
        if process.poll() is None:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
    return {name: process.poll() for name, process in processes.items()}


def parse_trace(path: Path) -> list[dict[str, Any]]:
    require(path.is_file(), f"missing Structure attempt trace: {path}")
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            record = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite value {value}")))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ABError(f"invalid trace JSON at {path}:{number}: {exc}") from exc
        require(isinstance(record, dict), f"trace row is not an object: {path}:{number}")
        finite_tree(record, f"trace[{number}]")
        records.append(record)
    require(bool(records), f"empty Structure trace: {path}")
    return records


def parse_precice_table(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    require(path.is_file(), f"missing preCICE output table: {path}")
    lines = [line.split() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(len(lines) >= 2, f"empty preCICE output table: {path}")
    headers = lines[0]
    rows: list[dict[str, Any]] = []
    for number, fields in enumerate(lines[1:], 2):
        require(len(fields) == len(headers), f"column mismatch in {path}:{number}")
        row: dict[str, Any] = {}
        for header, field in zip(headers, fields):
            if header in {"TimeWindow", "TotalIterations", "Iterations", "Convergence",
                          "QNColumns", "DeletedQNColumns", "DroppedQNColumns"}:
                row[header] = int(field)
            else:
                try:
                    number_value = float(field)
                except ValueError as exc:
                    raise ABError(f"nonnumeric preCICE residual {field!r} in {path}:{number}") from exc
                require(math.isfinite(number_value), f"non-finite preCICE metric in {path}:{number}")
                row[header] = number_value
        rows.append(row)
    return headers, rows


def attempt_metrics(records: list[dict[str, Any]], output_dir: Path, variant: str) -> dict[str, Any]:
    require(all(record.get("case_id") == "ANCF_SINGLE_SLICE_HIGHRE_0P2S_PREP_V1" for record in records),
            f"{variant}: trace case identity mismatch")
    windows = sorted({int(record["window_index"]) for record in records})
    require(windows == [1, 2, 3, 4, 5], f"{variant}: expected exactly five windows, found {windows}")
    sequences = [int(record["sequence"]) for record in records]
    request_ids = [int(record["request_id"]) for record in records]
    transaction_ids = [int(record["transaction_id"]) for record in records]
    for values, name in ((sequences, "sequence"), (request_ids, "request_id"),
                         (transaction_ids, "transaction_id")):
        require(values == sorted(set(values)), f"{variant}: {name} is not strictly monotonic and unique")
    for record in records:
        require(record.get("D_written_to_precice_m") == record.get("D_trial_interface_m"),
                f"{variant}: D_written != D_trial at window {record.get('window_index')} "
                f"iteration {record.get('iteration_index')}")
        if record.get("rollback_request"):
            require(record.get("force_read_offset_s") == EXPECTED_DT,
                    f"{variant}: retry Force read offset is not dt")
        else:
            require(record.get("force_read_offset_s") == 0.0,
                    f"{variant}: accepted Force read offset is not zero")
        iteration = int(record["iteration_index"])
        if iteration > 1:
            require(record.get("force_input_read_offset_s") == EXPECTED_DT,
                    f"{variant}: retry ANCF input did not use the previous endpoint Force")
        elif int(record["window_index"]) == 1:
            f0 = tuple(float(value) for value in record["force_input_vector_raw_N"])
            require(all(abs(f0[i] - EXPECTED_F0[i]) < 5e-13 for i in (0, 1)),
                    f"{variant}: initial physical F0 mismatch: {f0}")
            require(record.get("force_input_read_offset_s") == 0.0,
                    f"{variant}: first F0 read offset is not zero")
        else:
            require(record.get("force_input_read_offset_s") == 0.0,
                    f"{variant}: new-window Force read offset is not zero")

    iteration_headers, iteration_rows = parse_precice_table(
        output_dir / "case" / "precice-Fluid_0000-iterations.log")
    require([row["TimeWindow"] for row in iteration_rows] == windows,
            f"{variant}: preCICE iteration window count differs from Structure trace")
    trace_attempts_by_window = {window: sum(int(rec["window_index"]) == window for rec in records)
                                for window in windows}
    require([row["Iterations"] for row in iteration_rows]
            == [trace_attempts_by_window[window] for window in windows],
            f"{variant}: Fluid CFD advance count differs from attempt trace")

    convergence_headers, convergence_rows = parse_precice_table(
        output_dir / "case" / "precice-Fluid_0000-convergence.log")
    require(len(convergence_rows) == len(records),
            f"{variant}: preCICE convergence history length differs from attempts")
    convergence_by_window: dict[int, list[dict[str, Any]]] = {window: [] for window in windows}
    for row in convergence_rows:
        window = int(row["TimeWindow"])
        require(window in convergence_by_window, f"{variant}: unexpected convergence-log window {window}")
        convergence_by_window[window].append(row)
    trace_by_window: dict[int, list[dict[str, Any]]] = {window: [] for window in windows}
    for record in records:
        trace_by_window[int(record["window_index"])].append(record)

    per_window: dict[str, Any] = {}
    for window in windows:
        attempts = trace_by_window[window]
        final = attempts[-1]
        iteration_row = iteration_rows[window - 1]
        require(len(attempts) == iteration_row["Iterations"], f"{variant}: window attempt count mismatch")
        converged = bool(iteration_row["Convergence"])
        accepted_status = str(final.get("convergence_status"))
        if converged:
            require(accepted_status == "accepted_by_precice_before_iteration_limit",
                    f"{variant}: preCICE convergence and Structure status disagree in window {window}")
        else:
            require(accepted_status == "ACCEPTED_AT_ITERATION_LIMIT",
                    f"{variant}: nonconverged preCICE window is not honestly classified at cap")
        conv_rows = convergence_by_window[window]
        per_window[str(window)] = {
            "attempt_count": len(attempts),
            "rollback_count": sum(bool(record.get("rollback_request")) for record in attempts),
            "acceptance": "converged_before_cap" if converged else "ACCEPTED_AT_ITERATION_LIMIT",
            "preCICE_converged": converged,
            "preCICE_final_residuals": {key: value for key, value in conv_rows[-1].items()
                                        if key not in {"TimeWindow", "Iteration"}},
            "preCICE_residual_history": conv_rows,
            "structure_force_input_sequence_raw_N": [record["force_input_vector_raw_N"] for record in attempts],
            "structure_force_returned_sequence_raw_N": [record["returned_force_raw_N"] for record in attempts],
            "force_read_offsets_input_s": [record["force_input_read_offset_s"] for record in attempts],
            "force_read_offsets_returned_s": [record["force_read_offset_s"] for record in attempts],
            "D_trial_sequence_m": [record["D_trial_interface_m"] for record in attempts],
            "D_written_sequence_m": [record["D_written_to_precice_m"] for record in attempts],
            "D_written_equals_D_trial_all_attempts": all(
                record["D_written_to_precice_m"] == record["D_trial_interface_m"] for record in attempts),
            "force_residual_raw_N": [record.get("force_residual_raw_N") for record in attempts],
            "force_residual_applied_N": [record.get("force_residual_applied_N") for record in attempts],
            "trial_displacement_residual_m": [record.get("trial_displacement_residual_m") for record in attempts],
            "ancf_newton_iterations": [record.get("ancf_newton_iterations") for record in attempts],
            "ancf_nonlinear_residual": [record.get("ancf_residual") for record in attempts],
        }
    return {
        "iterations_log_headers": iteration_headers,
        "iterations_log_rows": iteration_rows,
        "convergence_log_headers": convergence_headers,
        "attempt_count": len(records),
        "rollback_count": sum(bool(record.get("rollback_request")) for record in records),
        "total_cfd_advance_calls": sum(int(row["Iterations"]) for row in iteration_rows),
        "sequence_range": [sequences[0], sequences[-1]],
        "request_id_range": [request_ids[0], request_ids[-1]],
        "transaction_id_range": [transaction_ids[0], transaction_ids[-1]],
        "per_window": per_window,
        "raw_records": len(records),
    }


def sample_proc_runtime(pid: int, name: str, seen: dict[str, Any]) -> None:
    data = loaded_runtime(pid)
    if data:
        seen[name] = {"pid": pid, "loaded_libraries": data}


def run_one(run_dir: Path, variant: str, worker: Path, timeout_s: float,
            expected_restart: Mapping[str, Any]) -> dict[str, Any]:
    output_dir = run_dir / variant
    case_dir = output_dir / "case"
    started_wall = datetime.now(timezone.utc).isoformat()
    start_ns = time.monotonic_ns()
    preflight = verify_scratch_case(case_dir, variant, worker, expected_restart=expected_restart)
    preflight_done_ns = time.monotonic_ns()
    identity = runtime_identities(worker)
    identity.update({
        "run_id": run_dir.name, "variant": variant,
        "restart_global_time_s": 30.0,
        "restart_field_hashes": preflight["restart"]["field_hashes_verified"],
        "mesh_hashes": preflight["restart"]["polyMesh_hashes_verified"],
        "release_force": {"raw_N": list(EXPECTED_F0), "source_global_time_s": 30.0,
                          "result_json_sha256": preflight["restart"]["result_json_sha256"]},
        "configuration": {"path": str(case_dir / "precice-config.xml"),
                           "sha256": sha256(case_dir / "precice-config.xml"),
                           "acceleration": preflight["settings"]["acceleration"]},
        "case_contract_sha256": sha256(case_dir / "contract.json"),
        "preflight_status": preflight["status"],
    })
    write_json(output_dir / "runtime_identity.json", identity)
    write_json(output_dir / "preflight.json", preflight)

    plan = bq.construct_commands(case_dir, worker, EXPECTED_WINDOWS,
                                 preflight["openfoam_executable"] if "openfoam_executable" in preflight
                                 else openfoam_identity()["pimpleFoam"], output_dir)
    require(plan.socket_directory == Path(preflight["socket"]["path"]).resolve(),
            f"{variant}: launch plan socket path mismatch")
    require(plan.fluid_command[1:] == ("-case", str(case_dir.resolve())),
            f"{variant}: unexpected Fluid command: {plan.fluid_command}")

    env = os.environ.copy()
    env["ANCF_PRECICE_ADAPTER_LIBRARY"] = str(EXPECTED_ADAPTER)
    env["ANCF_ADAPTER_RUNTIME_PATH"] = str(EXPECTED_ADAPTER)
    env["ANCF_ADAPTER_RUNTIME_SHA256"] = EXPECTED_ADAPTER_SHA
    if "PYTHONUNBUFFERED" not in env:
        env["PYTHONUNBUFFERED"] = "1"
    stream_paths = {"Structure": output_dir / "structure.stdout",
                    "Fluid": output_dir / "fluid.stdout"}
    error_paths = {"Structure": output_dir / "structure.stderr",
                   "Fluid": output_dir / "fluid.stderr"}
    require(all(not path.exists() for path in (*stream_paths.values(), *error_paths.values())),
            f"{variant}: refusing to overwrite an existing participant log")
    processes: dict[str, subprocess.Popen[str]] = {}
    samples: dict[str, Any] = {}
    worker_seen: dict[int, dict[str, Any]] = {}
    exit_codes: dict[str, int | None] = {}
    failure: str | None = None
    with (stream_paths["Structure"].open("x", encoding="utf-8") as structure_out,
          error_paths["Structure"].open("x", encoding="utf-8") as structure_err,
          stream_paths["Fluid"].open("x", encoding="utf-8") as fluid_out,
          error_paths["Fluid"].open("x", encoding="utf-8") as fluid_err):
        try:
            # Timing begins at this launcher boundary for both variants and ends
            # only after both participants exit.
            processes["Structure"] = subprocess.Popen(
                list(plan.structure_command), cwd=case_dir, env=env,
                stdout=structure_out, stderr=structure_err, text=True, start_new_session=True,
            )
            processes["Fluid"] = subprocess.Popen(
                list(plan.fluid_command), cwd=case_dir, env=env,
                stdout=fluid_out, stderr=fluid_err, text=True, start_new_session=True,
            )
            deadline = time.monotonic() + timeout_s
            while any(process.poll() is None for process in processes.values()):
                for name, process in processes.items():
                    sample_proc_runtime(process.pid, name, samples)
                for entry in Path("/proc").iterdir():
                    if not entry.name.isdigit():
                        continue
                    try:
                        exe = Path(os.readlink(entry / "exe")).resolve()
                        if exe == worker.resolve():
                            stat = (entry / "stat").read_text(encoding="utf-8").split()
                            worker_seen[int(entry.name)] = {"pid": int(entry.name), "ppid": int(stat[3]),
                                                            "loaded_libraries": loaded_runtime(int(entry.name))}
                    except (OSError, ValueError, IndexError):
                        continue
                bad = {name: process.returncode for name, process in processes.items()
                       if process.poll() is not None and process.returncode != 0}
                if bad:
                    failure = f"participant nonzero exit: {bad}"
                    break
                if time.monotonic() >= deadline:
                    failure = f"bounded run exceeded infrastructure timeout {timeout_s}s"
                    break
                time.sleep(0.25)
        except BaseException:
            terminate_owned(processes)
            raise
        if failure is not None:
            exit_codes.update(terminate_owned(processes))
        else:
            exit_codes.update({name: process.wait() for name, process in processes.items()})
    end_ns = time.monotonic_ns()
    wall_s = (end_ns - start_ns) / 1e9
    worker_remaining = find_worker_processes(worker)
    process_cleanup = {
        "started_utc": started_wall,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "wall_s_launcher_start_to_all_participants_exit": wall_s,
        "preflight_included_in_wall_time": True,
        "preflight_s": (preflight_done_ns - start_ns) / 1e9,
        "participant_pids_and_exit_codes": {
            name: {"pid": process.pid, "exit_code": exit_codes.get(name)}
            for name, process in processes.items()
        },
        "worker_processes_observed": list(worker_seen.values()),
        "worker_processes_remaining": worker_remaining,
        "loaded_runtime_samples": samples,
        "all_owned_processes_exited": all(code is not None for code in exit_codes.values()),
        "worker_absent_after_shutdown": not worker_remaining,
        "failure": failure,
    }
    write_json(output_dir / "process_cleanup.json", process_cleanup)
    if failure:
        raise ABError(f"{variant}: {failure}; evidence preserved under {output_dir}")
    require(exit_codes == {"Structure": 0, "Fluid": 0},
            f"{variant}: unexpected participant exit codes {exit_codes}")
    require(not worker_remaining, f"{variant}: orphan worker remains: {worker_remaining}")
    require("Fluid" in samples and any(str(EXPECTED_ADAPTER.resolve()) in key for key in
                                      samples["Fluid"].get("loaded_libraries", {})),
            f"{variant}: actual Fluid process did not expose the SHA-pinned adapter in /proc maps")
    require(any("libprecice.so" in key for key in samples["Fluid"].get("loaded_libraries", {})),
            f"{variant}: Fluid did not expose loaded libprecice in /proc maps")
    require(any("libprecice.so" in key for key in samples.get("Structure", {}).get("loaded_libraries", {})),
            f"{variant}: Structure did not expose loaded libprecice in /proc maps")

    # Check original restart inputs remain byte-identical inside each scratch
    # copy after the CFD run; all advanced fields are separate later times.
    for rel, expected in expected_restart["field_hashes_verified"].items():
        require(sha256(case_dir / "30" / rel) == expected, f"{variant}: restart field changed: {rel}")
    for rel, expected in expected_restart["polyMesh_hashes_verified"].items():
        require(sha256(case_dir / "constant" / "polyMesh" / rel) == expected,
                f"{variant}: mesh input changed: {rel}")
    for rel, expected in expected_restart["runtime_configuration_hashes_verified"].items():
        require(sha256(case_dir / rel) == expected, f"{variant}: frozen CFD configuration changed: {rel}")

    trace = parse_trace(output_dir / "structure_trace.jsonl")
    metrics = attempt_metrics(trace, output_dir, variant)
    iterations_rows = metrics["iterations_log_rows"]
    # Stock preCICE 3.4.1 iterations logs expose QN column, QR deletion and
    # history-drop counts when a quasi-Newton acceleration is active.
    qn_fields = {"QNColumns", "DeletedQNColumns", "DroppedQNColumns"}
    if variant == "iqn_ils":
        require(qn_fields.issubset(set(metrics["iterations_log_headers"])),
                "IQN run iterations log is missing QNColumns/filter/history diagnostics")
    profile_files = sorted(str(path.relative_to(case_dir)) for path in
                           (case_dir / "precice-profiling").rglob("*") if path.is_file()) \
        if (case_dir / "precice-profiling").is_dir() else []
    log_files = sorted(str(path.relative_to(case_dir)) for path in case_dir.glob("precice-*") if path.is_file())
    acceleration_info = case_dir / "precice-accelerationInfo.log"
    warning_lines: list[str] = []
    for log in [*stream_paths.values(), *error_paths.values(),
                *(case_dir / name for name in log_files),
                *(case_dir / name for name in profile_files)]:
        if not log.is_file():
            continue
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.search(r"\b(warning|warn|fatal|error)\b", line, flags=re.IGNORECASE):
                warning_lines.append(f"{log.relative_to(output_dir) if log.is_relative_to(output_dir) else log}: {line}")

    result = {
        "variant": variant, "classification": "RUN_COMPLETED",
        "runtime_identity": identity,
        "timing": {"launcher_start_to_all_participants_exit_s": wall_s,
                   "average_s_per_coupling_attempt": wall_s / metrics["attempt_count"],
                   "preflight_included": True},
        "process_cleanup": process_cleanup,
        "restart_inputs_unchanged_after_run": True,
        "iterations_per_window": {window: row["Iterations"] for window, row in
                                   ((str(item["TimeWindow"]), item) for item in iterations_rows)},
        "total_coupling_attempts": metrics["attempt_count"],
        "total_cfd_advance_calls": metrics["total_cfd_advance_calls"],
        "rollback_count": metrics["rollback_count"],
        "per_window": metrics["per_window"],
        "precice_iterations_log_headers": metrics["iterations_log_headers"],
        "precice_convergence_log_headers": metrics["convergence_log_headers"],
        "iqn_diagnostics": {
            "iterations_log_rows": iterations_rows,
            "acceleration_info_log_present": acceleration_info.is_file(),
            "acceleration_info_log": str(acceleration_info) if acceleration_info.is_file() else None,
            "preconditioner_configured": "residual-sum" if variant == "iqn_ils" else None,
            "runtime_preconditioner_status": "not separately exposed by stock runtime log",
            "warning_and_error_lines": warning_lines,
            "profiling_files": profile_files,
        },
        "files": {
            "structure_trace": str(output_dir / "structure_trace.jsonl"),
            "structure_audit": str(output_dir / "structure_audit.json"),
            "fluid_stdout": str(stream_paths["Fluid"]), "fluid_stderr": str(error_paths["Fluid"]),
            "structure_stdout": str(stream_paths["Structure"]), "structure_stderr": str(error_paths["Structure"]),
            "case_precice_logs": log_files,
            "case_precice_profiling": profile_files,
        },
    }
    write_json(output_dir / "run_summary.json", result)
    return result


def classify_comparison(baseline: Mapping[str, Any], iqn: Mapping[str, Any]) -> str:
    b_attempts = int(baseline["total_coupling_attempts"])
    i_attempts = int(iqn["total_coupling_attempts"])
    b_caps = sum(item["acceptance"] == "ACCEPTED_AT_ITERATION_LIMIT"
                 for item in baseline["per_window"].values())
    i_caps = sum(item["acceptance"] == "ACCEPTED_AT_ITERATION_LIMIT"
                 for item in iqn["per_window"].values())
    b_wall = float(baseline["timing"]["launcher_start_to_all_participants_exit_s"])
    i_wall = float(iqn["timing"]["launcher_start_to_all_participants_exit_s"])
    if i_attempts <= 0.70 * b_attempts and i_caps <= b_caps and i_wall < b_wall:
        return "IQN_IMPROVES_SINGLE_SLICE_EFFICIENCY"
    if i_attempts < b_attempts and i_caps <= b_caps and i_wall < b_wall:
        return "IQN_LIMITED_IMPROVEMENT"
    return "IQN_NO_SIGNIFICANT_IMPROVEMENT"


def execute(run_dir: Path, worker: Path, timeout_s: float) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    try:
        run_dir.relative_to(EVIDENCE_ROOT.resolve())
    except ValueError as exc:
        raise ABError(f"run directory is outside {EVIDENCE_ROOT}: {run_dir}") from exc
    manifest_path = run_dir / "preparation_manifest.json"
    require(manifest_path.is_file(), f"prepared run manifest missing: {manifest_path}")
    manifest = read_json(manifest_path)
    require(manifest.get("status") == "PREPARED_FOR_ONE_SHOT_EXECUTION", "run was not prepared by this tool")
    require(not (run_dir / "execution_started.json").exists(),
            "one-shot execution marker exists; refusing a second real run")
    require(float(manifest.get("timeout_s_per_run", -1)) == timeout_s,
            "execution timeout differs from prepared manifest")
    identities = runtime_identities(worker)
    require(identities["git"]["head"] == manifest["runtime_identities"]["git"]["head"],
            "Git HEAD changed after preparation")
    expected_restart = manifest["source_restart"]
    all_preflights = {
        variant: verify_scratch_case(Path(manifest["variants"][variant]["case_dir"]), variant,
                                     worker, expected_restart=expected_restart)
        for variant in VARIANTS
    }
    write_json(run_dir / "execution_preflight.json", all_preflights, exclusive=True)
    write_json(run_dir / "execution_started.json", {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": identities["git"]["head"],
        "exact_runs": ["baseline", "iqn_ils"], "max_windows_each": 5,
        "dt_s": EXPECTED_DT, "max_iterations": EXPECTED_ITERATIONS,
    }, exclusive=True)

    completed: dict[str, Any] = {}
    try:
        for variant in VARIANTS:
            # Repeat each fail-closed check immediately before that participant
            # pair starts; the second run is never a continuation of the first.
            completed[variant] = run_one(
                run_dir, variant, worker, timeout_s,
                expected_restart=expected_restart,
            )
            if variant == "baseline":
                socket_state = bq._check_socket_directory(Path(manifest["socket_directory"]),
                                                          Path(manifest["variants"][variant]["case_dir"]))
                require(not socket_state["stale_files"],
                        "baseline left a stale preCICE socket artifact; IQN run not started")
                require(not bq._active_socket_users(Path(manifest["socket_directory"]),
                                                    Path(manifest["variants"][variant]["case_dir"]) / "precice-config.xml",
                                                    Path(manifest["variants"][variant]["case_dir"])),
                        "baseline left an active preCICE socket user; IQN run not started")
        classification = classify_comparison(completed["baseline"], completed["iqn_ils"])
        summary = {
            "classification": classification,
            "run_id": run_dir.name,
            "git_head": identities["git"]["head"],
            "max_windows": 5, "dt_s": EXPECTED_DT, "max_iterations": EXPECTED_ITERATIONS,
            "runs": completed,
            "direct_comparison": {
                "iterations_per_window": {
                    "baseline": completed["baseline"]["iterations_per_window"],
                    "iqn_ils": completed["iqn_ils"]["iterations_per_window"],
                },
                "cap_acceptances": {
                    name: sum(item["acceptance"] == "ACCEPTED_AT_ITERATION_LIMIT"
                              for item in completed[name]["per_window"].values())
                    for name in VARIANTS
                },
                "total_coupling_attempts": {name: completed[name]["total_coupling_attempts"] for name in VARIANTS},
                "total_cfd_advance_calls": {name: completed[name]["total_cfd_advance_calls"] for name in VARIANTS},
                "total_wall_s": {name: completed[name]["timing"]["launcher_start_to_all_participants_exit_s"]
                                 for name in VARIANTS},
                "average_s_per_attempt": {name: completed[name]["timing"]["average_s_per_coupling_attempt"]
                                           for name in VARIANTS},
            },
            "exactly_two_five_window_runs_completed": True,
            "runtime_started": True,
            "hh06_validation_claim": False,
            "long_run_stability_claim": False,
        }
        write_json(run_dir / "qualification_summary.json", summary, exclusive=True)
        write_json(run_dir / "execution_completed.json", {
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "runs_completed": list(completed), "classification": classification,
        }, exclusive=True)
        return summary
    except BaseException as exc:
        summary = {
            "classification": "REVIEW_REQUIRED",
            "run_id": run_dir.name,
            "git_head": identities["git"]["head"],
            "failure": f"{type(exc).__name__}: {exc}",
            "runs_completed": list(completed),
            "runtime_started": bool(completed) or any((run_dir / name / "process_cleanup.json").exists()
                                                        for name in VARIANTS),
            "next_run_not_started_after_failure": True,
        }
        write_json(run_dir / "qualification_summary.json", summary)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 1H.7 one-shot isolated five-window A/B runner")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true", help="copy/validate both fresh cases; start no runtime")
    mode.add_argument("--execute", action="store_true", help="execute exactly baseline then IQN-ILS once")
    parser.add_argument("--worker", type=Path, required=True, help="explicit SHA-pinned worker executable")
    parser.add_argument("--run-directory", type=Path, help="prepared run directory required with --execute")
    parser.add_argument("--timeout-seconds", type=float, default=TIMEOUT_S)
    args = parser.parse_args(argv)
    worker = args.worker.expanduser().resolve()
    try:
        require(args.timeout_seconds > 0.0 and math.isfinite(args.timeout_seconds), "timeout must be finite and positive")
        if args.prepare_only:
            require(args.run_directory is None, "--run-directory is valid only with --execute")
            run_dir = prepare(worker, args.timeout_seconds)
            print(json.dumps({"status": "PREPARED_FOR_ONE_SHOT_EXECUTION",
                              "run_directory": str(run_dir),
                              "participants_started": False}, indent=2))
            return 0
        require(args.run_directory is not None, "--run-directory is required with --execute")
        summary = execute(args.run_directory, worker, args.timeout_seconds)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"PHASE1H7_PRE_RUN_OR_RUNTIME_FAILURE: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
