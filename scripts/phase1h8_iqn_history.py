#!/usr/bin/env python3
"""One-shot, isolated two-window IQN-ILS history-length sensitivity run.

Reuses the already reviewed Phase 1H.7 process/identity recorder, while making
three independent scratch copies and overriding only its config/trace checks
for the two-window Phase 1H.8 experiment. Production sources and configuration
are never edited by this script.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Mapping
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import phase1h7_iqn_ab as h7  # noqa: E402

HISTORY_LENGTHS = (1, 2, 3)
PHYSICAL_WINDOWS = 2
EXPECTED_XML_SOURCE_SHA = "cd943e0cfa04d7937d6a421305a032a642ae5a80d7e842b6a1651ec11517bff9"
EXPECTED_BASE_XML_WINDOWS = 5
EVIDENCE_ROOT = REPO / "evidence" / "phase1h8_iqn_history"
TIMEOUT_S = 900.0
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class HistoryStudyError(RuntimeError):
    """Fail-closed Phase 1H.8 preparation or execution error."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HistoryStudyError(message)


def local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1]


def find_one(parent: ET.Element, name: str, label: str) -> ET.Element:
    found = [node for node in parent.iter() if local_tag(node.tag) == name]
    require(len(found) == 1, f"expected one {label}, found {len(found)}")
    return found[0]


def check_candidate_config(path: Path, variant: str) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    scheme = find_one(root, "parallel-implicit", "parallel-implicit scheme")
    windows = find_one(scheme, "max-time-windows", "max-time-windows")
    dt = find_one(scheme, "time-window-size", "time-window-size")
    minimum = find_one(scheme, "min-iterations", "min-iterations")
    maximum = find_one(scheme, "max-iterations", "max-iterations")
    require(windows.attrib.get("value") == str(PHYSICAL_WINDOWS),
            f"{variant}: preCICE hard limit must be exactly {PHYSICAL_WINDOWS} windows")
    require(h7.bq._xml_numeric(dt.attrib.get("value"), "time-window-size") == h7.EXPECTED_DT,
            f"{variant}: dt differs from the accepted 0.0002 s")
    require(minimum.attrib.get("value") == "2" and maximum.attrib.get("value") == "20",
            f"{variant}: min/max implicit iterations changed")

    acceleration = find_one(scheme, "IQN-ILS", "IQN-ILS acceleration")
    initial = find_one(acceleration, "initial-relaxation", "initial-relaxation")
    used = find_one(acceleration, "max-used-iterations", "max-used-iterations")
    reused = find_one(acceleration, "time-windows-reused", "time-windows-reused")
    filter_node = find_one(acceleration, "filter", "QR3 filter")
    preconditioner = find_one(acceleration, "preconditioner", "preconditioner")
    primary_data = [node.attrib.get("name") for node in acceleration
                    if local_tag(node.tag) == "data"]
    require(acceleration.attrib.get("reduced-time-grid") == "true",
            f"{variant}: reduced-time-grid must remain true")
    require(initial.attrib.get("value") == "0.2" and initial.attrib.get("enforce") == "true",
            f"{variant}: initial relaxation contract changed")
    require(used.attrib.get("value") in {str(value) for value in HISTORY_LENGTHS},
            f"{variant}: unsupported max-used-iterations value")
    require(reused.attrib.get("value") == "1", f"{variant}: time-windows-reused changed")
    require(primary_data == ["Displacement", "Force"], f"{variant}: IQN primary data changed")
    require(filter_node.attrib.get("type") == "QR3" and filter_node.attrib.get("limit") == "1e-2",
            f"{variant}: QR3 filter changed")
    require(preconditioner.attrib.get("type") == "residual-sum",
            f"{variant}: residual-sum preconditioner changed")
    force_exchange = next((node for node in scheme if local_tag(node.tag) == "exchange"
                           and node.attrib.get("data") == "Force"), None)
    require(force_exchange is not None and force_exchange.attrib.get("initialize") == "yes",
            f"{variant}: physical initial Force exchange is not enabled")
    sockets = [node for node in root.iter() if local_tag(node.tag) == "sockets"]
    require(len(sockets) == 1 and bool(sockets[0].attrib.get("exchange-directory")),
            f"{variant}: expected one explicit exchange directory")
    return {
        "acceleration": {
            "type": "IQN-ILS", "max_used_iterations": int(used.attrib["value"]),
            "initial_relaxation": 0.2, "enforce": True, "time_windows_reused": 1,
            "primary_data": primary_data, "preconditioner": "residual-sum",
            "filter": {"type": "QR3", "limit": "1e-2"}, "reduced_time_grid": True,
        },
        "time_window_size_s": h7.EXPECTED_DT, "max_time_windows": PHYSICAL_WINDOWS,
        "max_iterations": 20, "force_initialize": "yes",
    }


def make_candidate_xml(source: str, history: int, socket_dir: Path) -> str:
    xml, count_windows = re.subn(
        r'(<max-time-windows\s+value=")5("\s*/>)',
        rf"\g<1>{PHYSICAL_WINDOWS}\2", source, count=1,
    )
    require(count_windows == 1, "source IQN XML does not contain one max-time-windows=5")
    xml, count_history = re.subn(
        r'(<max-used-iterations\s+value=")1("\s*/>)',
        rf"\g<1>{history}\2", xml, count=1,
    )
    require(count_history == 1, "source IQN XML does not contain one max-used-iterations=1")
    xml, count_socket = re.subn(
        r'(exchange-directory=")[^"]+("?)',
        lambda match: f'{match.group(1)}{socket_dir.resolve()}{match.group(2)}',
        xml, count=1,
    )
    require(count_socket == 1, "source IQN XML must contain exactly one socket path")
    return xml


def copy_text_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        stream.write(text)


def write_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "x" if exclusive else "w"
    with path.open(mode, encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"),
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    require(isinstance(value, dict), f"expected a JSON object: {path}")
    return value


def make_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                           capture_output=True, text=True, check=True).stdout.strip()
    return f"run-{stamp}-{short}-pid{os.getpid()}"


def build_candidate_xmls(run_dir: Path, socket_dir: Path) -> dict[str, dict[str, Any]]:
    require(h7.sha256(h7.IQN_XML) == EXPECTED_XML_SOURCE_SHA,
            "reviewed Phase 1H.6 IQN source XML hash mismatch")
    source = h7.IQN_XML.read_text(encoding="utf-8")
    candidate_dir = run_dir / "candidate_xml"
    candidate_dir.mkdir(exist_ok=False)
    result: dict[str, dict[str, Any]] = {}
    normalized: list[str] = []
    for history in HISTORY_LENGTHS:
        key = f"max-used-iterations-{history}"
        path = candidate_dir / f"iqn-ils-{key}.xml"
        xml = make_candidate_xml(source, history, socket_dir)
        settings = check_candidate_config_from_text(xml, key)
        copy_text_exclusive(path, xml)
        validator = shutil.which("precice-config-validate")
        require(validator is not None, "precice-config-validate is unavailable")
        validation = subprocess.run([validator, str(path)], cwd=REPO, capture_output=True,
                                    text=True, timeout=30, check=False)
        validation_pass = validation.returncode == 0 and not re.search(
            r"\bwarning\b", validation.stdout + validation.stderr, flags=re.IGNORECASE)
        validation_path = candidate_dir / f"iqn-ils-{key}.validation.json"
        write_json(validation_path, {
            "command": [validator, str(path)], "preCICE_version": "3.4.1",
            "return_code": validation.returncode, "stdout": validation.stdout,
            "stderr": validation.stderr, "warnings": re.findall(
                r".*\bwarning\b.*", validation.stdout + validation.stderr,
                flags=re.IGNORECASE), "passed": validation_pass,
        }, exclusive=True)
        require(validation_pass,
                f"{key}: preCICE 3.4.1 rejected candidate or emitted a warning; see {validation_path}")
        normalized.append(h7.normalized_config(xml))
        result[key] = {
            "xml_path": str(path.resolve()), "xml_sha256": h7.sha256(path),
            "validation_path": str(validation_path.resolve()), "validation_return_code": validation.returncode,
            "validation_stdout": validation.stdout, "validation_stderr": validation.stderr,
            "settings": settings,
        }
    require(len(set(normalized)) == 1,
            "candidate XMLs differ outside acceleration block / common two-window socket configuration")
    return result


def check_candidate_config_from_text(xml: str, label: str) -> dict[str, Any]:
    root = ET.fromstring(xml)
    # Route through a temporary in-memory parse to keep all candidate checks
    # identical without creating another untracked/generated XML file.
    scheme = find_one(root, "parallel-implicit", "parallel-implicit scheme")
    windows = find_one(scheme, "max-time-windows", "max-time-windows")
    used = find_one(scheme, "max-used-iterations", "max-used-iterations")
    require(windows.attrib.get("value") == "2", f"{label}: XML window bound is not two")
    value = used.attrib.get("value")
    require(value in {str(item) for item in HISTORY_LENGTHS}, f"{label}: invalid history length")
    # XML parser validation is also performed by check_candidate_config on
    # the preserved candidate file during scratch staging.
    return {
        "acceleration": {
            "type": "IQN-ILS", "max_used_iterations": int(value),
            "initial_relaxation": 0.2, "enforce": True, "time_windows_reused": 1,
            "primary_data": ["Displacement", "Force"], "preconditioner": "residual-sum",
            "filter": {"type": "QR3", "limit": "1e-2"}, "reduced_time_grid": True,
        },
        "time_window_size_s": h7.EXPECTED_DT, "max_time_windows": 2,
        "max_iterations": 20, "force_initialize": "yes",
    }


def attempt_metrics(records: list[dict[str, Any]], output_dir: Path,
                    variant: str) -> dict[str, Any]:
    require(records, f"{variant}: empty Structure trace")
    require(all(record.get("case_id") == "ANCF_SINGLE_SLICE_HIGHRE_0P2S_PREP_V1"
                for record in records), f"{variant}: trace case identity mismatch")
    windows = sorted({int(record["window_index"]) for record in records})
    require(windows == [1, 2], f"{variant}: expected exactly windows 1 and 2, got {windows}")
    for key in ("sequence", "request_id", "transaction_id"):
        values = [int(record[key]) for record in records]
        require(values == sorted(set(values)), f"{variant}: {key} is not strictly monotonic/unique")
    groups = {window: [record for record in records if int(record["window_index"]) == window]
              for window in windows}
    for window, attempts in groups.items():
        require([int(record["iteration_index"]) for record in attempts]
                == list(range(1, len(attempts) + 1)),
                f"{variant}: window {window} iteration indices are not contiguous")
        for record in attempts:
            require(record.get("D_written_to_precice_m") == record.get("D_trial_interface_m"),
                    f"{variant}: D_written differs from D_trial in window {window}")
            if record.get("rollback_request"):
                require(record.get("force_read_offset_s") == h7.EXPECTED_DT,
                        f"{variant}: retry Force read did not use dt")
            else:
                require(record.get("force_read_offset_s") == 0.0,
                        f"{variant}: accepted Force read did not use offset zero")
            if int(record["iteration_index"]) > 1:
                require(record.get("force_input_read_offset_s") == h7.EXPECTED_DT,
                        f"{variant}: retry ANCF input did not use prior endpoint Force")
    first_force = groups[1][0]["force_input_vector_raw_N"]
    require(abs(first_force[0] - h7.EXPECTED_F0[0]) < 5e-13
            and abs(first_force[1] - h7.EXPECTED_F0[1]) < 5e-13,
            f"{variant}: first physical release Force differs from qualified F0: {first_force}")
    require(groups[1][0].get("force_input_read_offset_s") == 0.0,
            f"{variant}: F0 was not read at offset zero")
    require(groups[2][0]["force_input_vector_raw_N"] == groups[1][-1]["returned_force_raw_N"],
            f"{variant}: window-2 Force is not the preceding accepted exchange")

    iteration_headers, iteration_rows = h7.parse_precice_table(
        output_dir / "case" / "precice-Fluid_0000-iterations.log")
    require([row["TimeWindow"] for row in iteration_rows] == [1, 2],
            f"{variant}: preCICE did not stop after exactly two windows")
    require([row["Iterations"] for row in iteration_rows]
            == [len(groups[1]), len(groups[2])],
            f"{variant}: preCICE advance counts differ from the Structure trace")
    require(sum(row["Iterations"] for row in iteration_rows) == len(records),
            f"{variant}: total CFD advances differ from coupling attempts")

    convergence_headers, convergence_rows = h7.parse_precice_table(
        output_dir / "case" / "precice-Fluid_0000-convergence.log")
    require(len(convergence_rows) == len(records),
            f"{variant}: preCICE convergence history length differs from attempts")
    by_window = {window: [row for row in convergence_rows if row["TimeWindow"] == window]
                 for window in windows}
    per_window: dict[str, Any] = {}
    for window, row in zip(windows, iteration_rows):
        attempts = groups[window]
        converged = bool(row["Convergence"])
        count = len(attempts)
        if converged and count < 20:
            acceptance = "CONVERGED_BEFORE_CAP"
        elif converged and count == 20:
            acceptance = "CONVERGED_AT_ITERATION_CAP"
        elif not converged and count == 20:
            acceptance = "ACCEPTED_AT_ITERATION_LIMIT"
        else:
            raise HistoryStudyError(
                f"{variant}: window {window} neither converged nor honestly reached the 20-iteration cap")
        per_window[str(window)] = {
            "attempt_count": count,
            "rollback_count": sum(bool(record.get("rollback_request")) for record in attempts),
            "preCICE_converged": converged,
            "acceptance": acceptance,
            "participant_final_status": attempts[-1].get("convergence_status"),
            "preCICE_final_residuals": {
                key: value for key, value in by_window[window][-1].items()
                if key not in {"TimeWindow", "Iteration"}},
            "preCICE_residual_history": by_window[window],
            "force_input_sequence_raw_N": [record["force_input_vector_raw_N"] for record in attempts],
            "force_returned_sequence_raw_N": [record["returned_force_raw_N"] for record in attempts],
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
            "qn_diagnostics": {key: row[key] for key in
                               ("QNColumns", "DeletedQNColumns", "DroppedQNColumns") if key in row},
        }
    require(all(window["D_written_equals_D_trial_all_attempts"] for window in per_window.values()),
            f"{variant}: at least one attempt did not write the current trial")
    return {
        "iterations_log_headers": iteration_headers,
        "iterations_log_rows": iteration_rows,
        "convergence_log_headers": convergence_headers,
        "attempt_count": len(records),
        "rollback_count": sum(bool(record.get("rollback_request")) for record in records),
        "total_cfd_advance_calls": sum(row["Iterations"] for row in iteration_rows),
        "sequence_range": [records[0]["sequence"], records[-1]["sequence"]],
        "request_id_range": [records[0]["request_id"], records[-1]["request_id"]],
        "transaction_id_range": [records[0]["transaction_id"], records[-1]["transaction_id"]],
        "per_window": per_window,
        "raw_records": len(records),
    }


def install_two_window_helpers() -> None:
    # Keep the accepted Structure CLI/contract authorization ceiling at five.
    # The scratch preCICE XML is the stricter physical-window stop at exactly 2.
    h7.EXPECTED_WINDOWS = 5
    h7.config_acceleration_check = check_candidate_config
    h7.attempt_metrics = attempt_metrics


def prepare(worker: Path, timeout_s: float) -> Path:
    install_two_window_helpers()
    require(h7.sha256(h7.BASELINE_XML) == h7.EXPECTED_BASELINE_XML_SHA,
            "production baseline XML changed since Phase 1H.7")
    require(h7.sha256(h7.IQN_XML) == EXPECTED_XML_SOURCE_SHA,
            "accepted Phase 1H.6 IQN XML changed")
    identities = h7.runtime_identities(worker)
    contract = h7.bq.load_json_strict(h7.CASE_SOURCE / "contract.json")
    auth = contract.get("execution_authorization", {})
    require(auth.get("mode") == "BOUNDED_COUPLING_QUALIFICATION" and auth.get("max_windows") == 5,
            "current Structure runtime authorization must remain the accepted five-window ceiling")
    require(h7.numeric_time_dirs(h7.CASE_SOURCE) == ["30"],
            "authoritative source case is not an exact time-30 restart")
    source_restart = h7.bq._verify_restart(h7.CASE_SOURCE, contract, contract["initial_state"])
    require(source_restart.get("global_time_s") == 30.0,
            "source restart is not global time 30.0 s")

    run_id = h7.make_run_id()
    run_dir = EVIDENCE_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    socket_dir = run_dir / "precice-sockets"
    socket_dir.mkdir(exist_ok=False)
    candidate_xmls = build_candidate_xmls(run_dir, socket_dir)
    normalized = []
    variants: dict[str, Any] = {}
    for history in HISTORY_LENGTHS:
        key = f"max-used-iterations-{history}"
        variant_root = run_dir / key
        variant_root.mkdir(exist_ok=False)
        h7.copy_release_evidence(variant_root, contract)
        output_dir = variant_root / "iqn_ils"
        output_dir.mkdir(exist_ok=False)
        source_xml = Path(candidate_xmls[key]["xml_path"])
        staged = h7.stage_case(source_xml, output_dir / "case", socket_dir, "iqn_ils")
        preflight = h7.verify_scratch_case(
            Path(staged["case_dir"]), "iqn_ils", worker, expected_restart=source_restart)
        normalized.append(h7.normalized_config(
            Path(staged["case_dir"], "precice-config.xml").read_text(encoding="utf-8")))
        variants[key] = {
            "candidate_xml": candidate_xmls[key], "stage": staged,
            "preflight": preflight, "case_dir": staged["case_dir"],
            "structure_cli_outer_ceiling": 5,
            "precice_physical_window_ceiling": 2,
        }
    require(len(set(normalized)) == 1,
            "scratch IQN configurations differ beyond max-used-iterations and the common two-window bound")
    manifest = {
        "runner_schema_version": 1,
        "status": "PREPARED_FOR_ONE_SHOT_EXECUTION",
        "run_id": run_id, "run_directory": str(run_dir.resolve()),
        "git_head": identities["git"]["head"], "git_branch": identities["git"]["branch"],
        "execution_authorization": {
            "study_physical_windows": PHYSICAL_WINDOWS,
            "preCICE_max_time_windows": PHYSICAL_WINDOWS,
            "structure_cli_authorized_ceiling": 5,
            "reason_for_dual_cap": "authoritative participant fail-closed guard requires --max-windows=5; scratch preCICE XML terminates at 2",
        },
        "dt_s": h7.EXPECTED_DT, "max_iterations": 20,
        "source_iqn_xml": str(h7.IQN_XML.resolve()),
        "source_iqn_xml_sha256": h7.sha256(h7.IQN_XML),
        "production_xml_sha256_before": h7.sha256(h7.BASELINE_XML),
        "socket_directory": str(socket_dir.resolve()),
        "source_restart": source_restart,
        "runtime_identity": identities,
        "candidates": variants,
        "timeout_s_per_candidate": timeout_s,
        "all_three_candidate_preflights": "PASS_PREFLIGHT_ONLY",
        "participants_not_started": True,
    }
    write_json(run_dir / "preparation_manifest.json", manifest, exclusive=True)
    return run_dir


def classify(completed: Mapping[str, Mapping[str, Any]]) -> tuple[str, dict[str, Any]]:
    base = completed["max-used-iterations-1"]
    base_attempts = int(base["total_coupling_attempts"])
    base_caps = sum(item["acceptance"] == "ACCEPTED_AT_ITERATION_LIMIT"
                    for item in base["per_window"].values())
    base_wall = float(base["timing"]["launcher_start_to_all_participants_exit_s"])
    minimum_material_delta = max(1, math.ceil(0.10 * base_attempts))
    results: dict[str, Any] = {"reference_attempts": base_attempts,
                               "material_attempt_delta": minimum_material_delta,
                               "candidate_comparisons": {}}
    improvements = []
    degradations = []
    for key in ("max-used-iterations-2", "max-used-iterations-3"):
        item = completed[key]
        attempts = int(item["total_coupling_attempts"])
        caps = sum(row["acceptance"] == "ACCEPTED_AT_ITERATION_LIMIT"
                   for row in item["per_window"].values())
        wall = float(item["timing"]["launcher_start_to_all_participants_exit_s"])
        new_warnings = sorted(set(item["iqn_diagnostics"].get("warning_and_error_lines", []))
                              - set(base["iqn_diagnostics"].get("warning_and_error_lines", [])))
        change = {
            "attempts": attempts, "attempt_delta_vs_m1": attempts - base_attempts,
            "cap_acceptances": caps, "cap_delta_vs_m1": caps - base_caps,
            "wall_s": wall, "wall_delta_s_vs_m1": wall - base_wall,
            "new_warning_lines_vs_m1": new_warnings,
        }
        results["candidate_comparisons"][key] = change
        if (attempts <= base_attempts - minimum_material_delta and caps <= base_caps
                and wall < base_wall and not new_warnings):
            improvements.append(key)
        if (attempts >= base_attempts + minimum_material_delta or caps > base_caps or new_warnings):
            degradations.append(key)
    results["improving_candidates"] = improvements
    results["degrading_candidates"] = degradations
    if improvements and degradations:
        return "REVIEW_REQUIRED", results
    if degradations:
        return "IQN_HISTORY_DEGRADES", results
    if improvements:
        return "IQN_HISTORY_IMPROVES", results
    return "IQN_HISTORY_NO_BENEFIT", results


def scan_runtime_warnings(output_dir: Path) -> dict[str, Any]:
    case_dir = output_dir / "case"
    paths = [output_dir / name for name in
             ("fluid.stdout", "fluid.stderr", "structure.stdout", "structure.stderr")]
    paths.extend(path for path in case_dir.glob("precice-*") if path.is_file())
    profiling = case_dir / "precice-profiling"
    if profiling.is_dir():
        paths.extend(path for path in profiling.rglob("*") if path.is_file())
    warning_lines: list[str] = []
    all_text: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = ANSI_ESCAPE.sub("", raw_line)
            all_text.append(line)
            if re.search(r"\b(warning|warn|fatal|error)\b", line, flags=re.IGNORECASE):
                warning_lines.append(f"{path.relative_to(output_dir) if path.is_relative_to(output_dir) else path}: {line}")
    ill_conditioning = [line for line in warning_lines
                        if "exceeded half the number of primary unknowns" in line]
    return {
        "ansi_escape_sequences_removed": True,
        "warning_error_lines": warning_lines,
        "iqn_primary_unknown_ill_conditioning_warnings": ill_conditioning,
        "adapter_runtime_modifiable_warning_present": any(
            "runTimeModifiable" in line and "adjustableTimestep" in line for line in all_text),
        "fatal_or_error_lines": [line for line in warning_lines
                                 if re.search(r"\b(fatal|error)\b", line, flags=re.IGNORECASE)],
    }


def audit_completed_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    require(run_dir.is_relative_to(EVIDENCE_ROOT.resolve()),
            f"run directory escapes evidence root: {run_dir}")
    summary_path = run_dir / "qualification_summary.json"
    require(summary_path.is_file(), f"completed qualification summary missing: {summary_path}")
    summary = read_json(summary_path)
    require(summary.get("exactly_three_independent_two_window_runs_completed") is True,
            "cannot audit a run without all three completed candidates")
    completed: dict[str, Any] = {}
    candidate_audits: dict[str, Any] = {}
    for history in HISTORY_LENGTHS:
        key = f"max-used-iterations-{history}"
        out = run_dir / key / "iqn_ils"
        run_summary_path = out / "run_summary.json"
        result = read_json(run_summary_path)
        original_scan = result.get("iqn_diagnostics", {}).get("warning_and_error_lines", [])
        audit = scan_runtime_warnings(out)
        diagnostics = result["iqn_diagnostics"]
        diagnostics["pre_ansi_warning_scan_lines"] = original_scan
        diagnostics["warning_and_error_lines"] = audit["warning_error_lines"]
        diagnostics["ansi_stripped_warning_scan"] = True
        diagnostics["iqn_primary_unknown_ill_conditioning_warning_count"] = len(
            audit["iqn_primary_unknown_ill_conditioning_warnings"])
        diagnostics["adapter_runtime_modifiable_warning_present"] = audit[
            "adapter_runtime_modifiable_warning_present"]
        write_json(run_summary_path, result)
        write_json(out / "warning_audit.json", audit, exclusive=not (out / "warning_audit.json").exists())
        candidate_audits[key] = audit
        completed[key] = result
    classification, comparison = classify(completed)
    previous = summary.get("classification")
    summary["classification_before_ansi_warning_audit"] = previous
    summary["classification"] = classification
    summary["candidates"] = completed
    summary["history_comparison"] = comparison
    summary["warning_audit"] = "warning_audit.json and per-candidate warning_audit.json"
    write_json(summary_path, summary)
    completed_path = run_dir / "execution_completed.json"
    if completed_path.is_file():
        completed_record = read_json(completed_path)
        completed_record["classification_before_ansi_warning_audit"] = previous
        completed_record["classification"] = classification
        completed_record["warning_audit_completed"] = True
        write_json(completed_path, completed_record)
    audit_result = {
        "classification": classification,
        "previous_runner_classification": previous,
        "reason": "ANSI-colored IQN warning lines are normalized before classification",
        "candidates": candidate_audits,
        "history_comparison": comparison,
        "runtime_repeated": False,
    }
    write_json(run_dir / "warning_audit.json", audit_result)
    return audit_result


def execute(run_dir: Path, worker: Path, timeout_s: float) -> dict[str, Any]:
    install_two_window_helpers()
    run_dir = run_dir.expanduser().resolve()
    require(run_dir.is_relative_to(EVIDENCE_ROOT.resolve()),
            f"run directory escapes evidence root: {run_dir}")
    manifest_path = run_dir / "preparation_manifest.json"
    manifest = read_json(manifest_path)
    require(manifest.get("status") == "PREPARED_FOR_ONE_SHOT_EXECUTION",
            "run directory was not prepared for one-shot execution")
    require(manifest.get("runner_schema_version") == 1,
            "prepared manifest predates the current runner schema; refusing execution")
    require(not (run_dir / "execution_started.json").exists(),
            "execution marker exists; refusing a second runtime attempt")
    require(float(manifest.get("timeout_s_per_candidate", -1)) == timeout_s,
            "execution timeout differs from prepared manifest")
    identities = h7.runtime_identities(worker)
    require(identities["git"]["head"] == manifest["git_head"],
            "HEAD changed after candidate preparation")
    require(h7.sha256(h7.BASELINE_XML) == manifest["production_xml_sha256_before"],
            "production XML changed after preparation")
    require(h7.sha256(h7.IQN_XML) == EXPECTED_XML_SOURCE_SHA,
            "reviewed Phase 1H.6 candidate changed after preparation")

    expected_restart = manifest["source_restart"]
    preflights: dict[str, Any] = {}
    for key in (f"max-used-iterations-{value}" for value in HISTORY_LENGTHS):
        case_dir = Path(manifest["candidates"][key]["case_dir"])
        preflights[key] = h7.verify_scratch_case(
            case_dir, "iqn_ils", worker, expected_restart=expected_restart)
    write_json(run_dir / "execution_preflight.json", preflights, exclusive=True)
    write_json(run_dir / "execution_started.json", {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": identities["git"]["head"],
        "candidates": [f"max-used-iterations-{item}" for item in HISTORY_LENGTHS],
        "exact_preCICE_windows_per_candidate": 2,
        "structure_cli_outer_ceiling": 5,
        "dt_s": h7.EXPECTED_DT, "max_iterations": 20,
    }, exclusive=True)

    completed: dict[str, Any] = {}
    try:
        socket_dir = Path(manifest["socket_directory"])
        for history in HISTORY_LENGTHS:
            key = f"max-used-iterations-{history}"
            candidate_root = run_dir / key
            case_dir = Path(manifest["candidates"][key]["case_dir"])
            socket_state = h7.bq._check_socket_directory(socket_dir, case_dir)
            require(not socket_state["stale_files"],
                    f"{key}: stale exchange files exist before candidate start")
            require(not h7.bq._active_socket_users(
                socket_dir, case_dir / "precice-config.xml", case_dir),
                f"{key}: an unrelated process is using the candidate socket path")
            result = h7.run_one(candidate_root, "iqn_ils", worker, timeout_s,
                                expected_restart=expected_restart)
            # The generic Phase 1H.7 scanner did not strip ANSI escapes from
            # preCICE's colored warning prefix. Audit the untouched logs before
            # deciding whether retained history introduced a new warning.
            result["iqn_diagnostics"]["pre_ansi_warning_scan_lines"] = list(
                result["iqn_diagnostics"].get("warning_and_error_lines", []))
            warning_audit = scan_runtime_warnings(candidate_root / "iqn_ils")
            result["iqn_diagnostics"]["warning_and_error_lines"] = warning_audit["warning_error_lines"]
            result["iqn_diagnostics"]["ansi_stripped_warning_scan"] = True
            result["iqn_diagnostics"]["iqn_primary_unknown_ill_conditioning_warning_count"] = len(
                warning_audit["iqn_primary_unknown_ill_conditioning_warnings"])
            result["iqn_diagnostics"]["adapter_runtime_modifiable_warning_present"] = warning_audit[
                "adapter_runtime_modifiable_warning_present"]
            write_json(candidate_root / "iqn_ils" / "run_summary.json", result)
            write_json(candidate_root / "iqn_ils" / "warning_audit.json", warning_audit, exclusive=True)
            trace = h7.parse_trace(Path(candidate_root / "iqn_ils" / "structure_trace.jsonl"))
            observed_targets = sorted({round(float(record["physical_time_s"]), 10) for record in trace})
            require(observed_targets == [30.0002, 30.0004],
                    f"{key}: Structure trace does not show exactly two target windows: {observed_targets}")
            fluid_log = (candidate_root / "iqn_ils" / "fluid.stdout").read_text(
                encoding="utf-8", errors="replace")
            fluid_times = [float(value) for value in re.findall(r"Time\s*=\s*([0-9.eE+-]+)s", fluid_log)]
            require(fluid_times and max(fluid_times) <= 30.0004 + 2e-10
                    and any(abs(value - 30.0002) <= 2e-10 for value in fluid_times)
                    and any(abs(value - 30.0004) <= 2e-10 for value in fluid_times),
                    f"{key}: Fluid log does not end at exactly the second bounded window: "
                    f"max={max(fluid_times) if fluid_times else None}")
            # OpenFOAM writeInterval is 0.01 s, so this two-window run (0.0004 s
            # duration) intentionally produces no later numeric field directory.
            require(h7.numeric_time_dirs(case_dir) == ["30"],
                    f"{key}: authoritative input restart directory set changed unexpectedly")
            completed[key] = result
            socket_state = h7.bq._check_socket_directory(socket_dir, case_dir)
            require(not socket_state["stale_files"],
                    f"{key}: stale exchange files remain; stopping before next candidate")
            require(not h7.bq._active_socket_users(
                socket_dir, case_dir / "precice-config.xml", case_dir),
                f"{key}: an active process remains on the candidate socket path")

        classification, comparison = classify(completed)
        summary = {
            "classification": classification,
            "run_id": run_dir.name, "git_head": identities["git"]["head"],
            "physical_windows_per_candidate": 2, "dt_s": h7.EXPECTED_DT,
            "max_iterations": 20, "structure_cli_outer_ceiling": 5,
            "candidates": completed, "history_comparison": comparison,
            "exactly_three_independent_two_window_runs_completed": True,
            "production_xml_modified": False,
            "production_source_modified": False,
            "hh06_validation_claim": False,
            "long_run_stability_claim": False,
        }
        write_json(run_dir / "qualification_summary.json", summary, exclusive=True)
        write_json(run_dir / "execution_completed.json", {
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "candidates_completed": list(completed), "classification": classification,
        }, exclusive=True)
        return summary
    except BaseException as exc:
        summary = {
            "classification": "REVIEW_REQUIRED", "run_id": run_dir.name,
            "git_head": identities["git"]["head"],
            "failure": f"{type(exc).__name__}: {exc}",
            "candidates_completed": list(completed),
            "runtime_started": (run_dir / "execution_started.json").exists(),
            "automatic_retry": False,
        }
        write_json(run_dir / "qualification_summary.json", summary)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--audit-only", action="store_true",
                       help="normalize warnings and reconcile a completed run; starts no participants")
    parser.add_argument("--run-dir", type=Path,
                        help="prepared run directory; required with --execute")
    parser.add_argument("--worker", type=Path, required=True,
                        help="explicit SHA-pinned qualified worker executable")
    parser.add_argument("--timeout-per-candidate", type=float, default=TIMEOUT_S)
    args = parser.parse_args(argv)
    if (args.execute or args.audit_only) and args.run_dir is None:
        parser.error("--run-dir is required with --execute or --audit-only")
    try:
        if args.prepare_only:
            run_dir = prepare(args.worker, args.timeout_per_candidate)
            print(json.dumps({"status": "PREPARED_FOR_ONE_SHOT_EXECUTION",
                              "run_directory": str(run_dir)}, indent=2))
        elif args.audit_only:
            result = audit_completed_run(args.run_dir)
            print(json.dumps({"status": "AUDIT_COMPLETED", "run_directory": str(args.run_dir.resolve()),
                              "classification": result["classification"]}, indent=2))
        else:
            result = execute(args.run_dir, args.worker, args.timeout_per_candidate)
            print(json.dumps({"status": "COMPLETED", "run_directory": str(args.run_dir.resolve()),
                              "classification": result["classification"]}, indent=2))
        return 0
    except Exception as exc:
        print(f"PHASE1H8_BLOCKED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
