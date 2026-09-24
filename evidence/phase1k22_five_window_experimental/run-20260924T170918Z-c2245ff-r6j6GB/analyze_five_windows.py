#!/usr/bin/env python3
"""Verify the Phase 1K.22 five-window experimental adapter evidence."""

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


RUN = Path(__file__).resolve().parent
DIAG = RUN / "diagnostics"


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def field_checks(snapshot, name):
    field = snapshot[name]
    return {
        "internal_sha256": digest(field["internal"]),
        "boundary_sha256": digest(field["boundary"]),
        "full_sha256": digest({"internal": field["internal"], "boundary": field["boundary"]}),
        "cylinder_boundary_sha256": digest(field["boundary"]["cylinder"]),
    }


def main():
    baselines = {}
    per_window = {}
    for window in range(1, 6):
        snapshot = json.loads((DIAG / f"S0_after_checkpoint_save_{window}.json").read_text())
        baselines[snapshot["time_s"]] = snapshot
        per_window[window] = {
            "checkpoint_time_s": snapshot["time_s"],
            "point_max_norm_m": snapshot["pointDisplacement"]["norms"]["all"]["max_norm"],
            "point": field_checks(snapshot, "pointDisplacement"),
            "cell": field_checks(snapshot, "cellDisplacement"),
            "mesh_points_sha256": digest(snapshot["mesh_points"]),
            "retry_count": 0,
        }
    retries = []
    for path in sorted(DIAG.glob("S1_after_rollback_restore_retry_*.json"),
                       key=lambda p: int(p.stem.rsplit("_", 1)[1])):
        current = json.loads(path.read_text())
        window = next(w for w, s0 in per_window.items()
                      if current["time_s"] == s0["checkpoint_time_s"])
        point = field_checks(current, "pointDisplacement")
        cell = field_checks(current, "cellDisplacement")
        record = {
            "retry_ordinal": int(path.stem.rsplit("_", 1)[1]),
            "window_index": window,
            "time_s": current["time_s"],
            "point": point,
            "cell": cell,
            "mesh_points_sha256": digest(current["mesh_points"]),
            "point_matches_S0": point == per_window[window]["point"],
            "cell_matches_S0": cell == per_window[window]["cell"],
            "mesh_matches_S0": digest(current["mesh_points"]) == per_window[window]["mesh_points_sha256"],
        }
        retries.append(record)
        per_window[window]["retry_count"] += 1

    ancf = [json.loads(line) for line in (RUN / "ancf_checkpoint_stages.jsonl").read_text().splitlines()]
    ancf_by_window = defaultdict(list)
    for entry in ancf:
        window = int(entry["checkpoint_id"].rsplit("-", 1)[1])
        ancf_by_window[window].append(entry)
    ancf_check = {}
    for window in range(1, 6):
        entries = ancf_by_window[window]
        ancf_check[window] = {
            "save_count": sum(e["stage"] == "S0_after_checkpoint_save" for e in entries),
            "restore_count": sum(e["stage"] == "S1_after_rollback_restore" for e in entries),
            "q_qdot_qddot_all_match": all(
                e["live_equals_checkpoint"]
                and e["checkpoint_state_sha256"] == e["live_state_sha256"]
                and all(e["checkpoint_backend_state"][key] == e["live_backend_state"][key]
                        for key in ("q", "qdot", "qddot"))
                for e in entries
            ),
        }

    trace = [json.loads(line) for line in (RUN / "structure_trace.jsonl").read_text().splitlines()]
    trace_by_window = defaultdict(list)
    for attempt in trace:
        trace_by_window[attempt["window_index"]].append(attempt)
    accepted = {window: [a for a in trace_by_window[window] if a["commit_status"] == "committed"]
                for window in range(1, 6)}
    written_trial_match = all(
        a["D_written_to_precice_m"] == a["D_trial_interface_m"] for a in trace
    )
    force_chain = all(
        current["force_input_vector_raw_N"] == previous["force_read_vector_raw_N"]
        for window in range(1, 6)
        for previous, current in zip(trace_by_window[window], trace_by_window[window][1:])
    )
    handoff = all(
        trace_by_window[window][-1]["force_read_vector_raw_N"]
        == trace_by_window[window + 1][0]["force_input_vector_raw_N"]
        for window in range(1, 5) if trace_by_window[window] and trace_by_window[window + 1]
    )
    fluid_log = (RUN / "fluid.stdout").read_text(errors="replace")
    offset_events = re.findall(
        r"PHASE1K16_READ_OFFSET retry=(\d) windowComplete=(\d) offset=([\d.]+)", fluid_log
    )
    retry_offsets = [event for event in offset_events if event[0] == "1"]
    accepted_offsets = [event for event in offset_events if event[0] == "0"]
    iteration_log = RUN / "case/precice-Fluid_0000-iterations.log"
    iqn = []
    if iteration_log.is_file():
        for line in iteration_log.read_text().splitlines()[1:]:
            columns = line.split()
            if len(columns) == 7 and all(part.isdigit() for part in columns):
                iqn.append(dict(zip(
                    ("window", "total_iterations", "iterations", "convergence_flag",
                     "qn_columns", "deleted_qn_columns", "dropped_qn_columns"),
                    map(int, columns))))
    cleanup = json.loads((RUN / "process_cleanup.json").read_text())
    structure_log = (RUN / "structure.stdout").read_text(errors="replace")
    log_seconds = []
    window_start_seconds = {}
    for line in structure_log.splitlines():
        clock = re.search(r"\(0\)\s+(\d{2}):(\d{2}):(\d{2})", line)
        if not clock:
            continue
        second = sum(int(part) * factor for part, factor in zip(clock.groups(), (3600, 60, 1)))
        log_seconds.append(second)
        start = re.search(r"it 1 \(min:.*?time-window (\d+) \(max: 5\)", line)
        if start:
            window_start_seconds.setdefault(int(start.group(1)), second)
    wall_per_window_estimate_s = {}
    if len(window_start_seconds) == 5 and log_seconds:
        for window in range(1, 6):
            endpoint = (window_start_seconds[window + 1] if window < 5 else max(log_seconds))
            wall_per_window_estimate_s[window] = endpoint - window_start_seconds[window]
    profile = (RUN / "case/precice-profiling/Structure_0000-0-1.txt").read_text()
    advance_event = re.search(r"^N(\d+):advance$", profile, re.MULTILINE)
    profile_durations_s = {}
    if advance_event:
        event_id = advance_event.group(1)
        begins = [int(value) for value in re.findall(rf"^B{event_id}:(\d+)$", profile, re.MULTILINE)]
        ends = [int(value) for value in re.findall(rf"^E{event_id}:(\d+)$", profile, re.MULTILINE)]
        if len(begins) == len(ends) == 100:
            for window in range(1, 6):
                start_us = begins[0] if window == 1 else ends[(window - 1) * 20 - 1]
                end_us = ends[window * 20 - 1]
                profile_durations_s[window] = (end_us - start_us) / 1_000_000
    window_results = {}
    for window in range(1, 6):
        attempts = trace_by_window[window]
        window_results[window] = {
            "attempts": len(attempts),
            "rollbacks": sum(a["rollback_request"] for a in attempts),
            "acceptance": [a["convergence_status"] for a in accepted[window]],
            "force_residual_raw_N": [a["force_residual_raw_N"] for a in attempts],
            "trial_displacement_residual_m": [a["trial_displacement_residual_m"] for a in attempts],
            "ancf_newton_iterations": [a["ancf_newton_iterations"] for a in attempts],
            "ancf_residual": [a["ancf_residual"] for a in attempts],
            "iqn": next((row for row in iqn if row["window"] == window), None),
            "wall_time_estimate_s_log_resolution_1s": wall_per_window_estimate_s.get(window),
            "wall_time_precice_profile_s": profile_durations_s.get(window),
        }
    total_rollbacks = sum(result["rollbacks"] for result in window_results.values())
    no_later_window = set(trace_by_window) == set(range(1, 6))
    process_ok = cleanup["exit_codes"] == {"fluid": 0, "structure": 0} and not cleanup["timed_out"]
    all_restored = all(r["point_matches_S0"] and r["cell_matches_S0"] and r["mesh_matches_S0"]
                       for r in retries)
    all_ancf_restored = all(
        ancf_check[w]["q_qdot_qddot_all_match"]
        and ancf_check[w]["save_count"] == 1
        and ancf_check[w]["restore_count"] == window_results[w]["rollbacks"]
        for w in range(1, 6))
    all_windows_accepted = all(
        len(accepted[w]) == 1
        and window_results[w]["rollbacks"] == window_results[w]["attempts"] - 1
        and 2 <= window_results[w]["attempts"] <= 20
        for w in range(1, 6))
    offsets_ok = (len(retry_offsets) == total_rollbacks
                  and all(float(event[2]) == 0.0002 for event in retry_offsets)
                  and len(accepted_offsets) == 4
                  and all(float(event[2]) == 0.0 for event in accepted_offsets))
    result = {
        "classification": "PASS_EXPERIMENTAL_FIVE_WINDOW_LIFECYCLE" if (
            no_later_window and process_ok and all_windows_accepted
            and len(retries) == total_rollbacks and all_restored and all_ancf_restored
            and written_trial_match and force_chain and handoff and offsets_ok
            and per_window[2]["point_max_norm_m"] > 0.0
            and len(iqn) == 5
        ) else "REVIEW_REQUIRED",
        "window_summaries": per_window,
        "window_results": window_results,
        "attempts_per_window": {w: len(trace_by_window[w]) for w in range(1, 6)},
        "accepted_per_window": {w: len(accepted[w]) for w in range(1, 6)},
        "retry_snapshots": retries,
        "ancf": ancf_check,
        "written_equals_trial_all_attempts": written_trial_match,
        "force_retry_chain_all_attempts": force_chain,
        "accepted_force_handoff_all_boundaries": handoff,
        "no_sixth_window": no_later_window,
        "all_retries_restored": all_restored,
        "all_ancf_retries_restored": all_ancf_restored,
        "all_windows_accepted": all_windows_accepted,
        "fluid_read_offset_events": Counter(offset_events).__repr__(),
        "retry_read_dt_count": len(retry_offsets),
        "accepted_boundary_read_zero_count": len(accepted_offsets),
        "offsets_ok": offsets_ok,
        "iqn_iterations_log": iqn,
        "wall_duration_s": cleanup["wall_duration_s"],
        "wall_clock_unix_vs_monotonic_difference_s": (
            cleanup["wall_end_unix_s"] - cleanup["wall_start_unix_s"]
            - cleanup["wall_duration_s"]),
        "wall_per_window_precice_profile_s": profile_durations_s,
        "wall_per_window_estimate_s_log_resolution_1s": wall_per_window_estimate_s,
        "process_exit_codes": cleanup["exit_codes"],
    }
    (RUN / "qualification_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "classification": result["classification"],
        "attempts_per_window": result["attempts_per_window"],
        "retry_read_dt_count": result["retry_read_dt_count"],
        "accepted_boundary_read_zero_count": result["accepted_boundary_read_zero_count"],
        "all_retries_restored": result["all_retries_restored"],
        "all_ancf_retries_restored": result["all_ancf_retries_restored"],
        "iqn_iterations_log": result["iqn_iterations_log"],
        "wall_duration_s": result["wall_duration_s"],
        "wall_per_window_precice_profile_s": result["wall_per_window_precice_profile_s"],
        "wall_clock_unix_vs_monotonic_difference_s": result["wall_clock_unix_vs_monotonic_difference_s"],
        "wall_per_window_estimate_s_log_resolution_1s": result["wall_per_window_estimate_s_log_resolution_1s"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
