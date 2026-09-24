#!/usr/bin/env python3
"""Verify the frozen Phase 1K.21 two-window diagnostic evidence."""

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
    for window in (1, 2):
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
        base = baselines[current["time_s"]]
        window = 1 if current["time_s"] == per_window[1]["checkpoint_time_s"] else 2
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
    for window in (1, 2):
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
                for window in (1, 2)}
    written_trial_match = all(
        a["D_written_to_precice_m"] == a["D_trial_interface_m"] for a in trace
    )
    force_chain = all(
        current["force_input_vector_raw_N"] == previous["force_read_vector_raw_N"]
        for window in (1, 2)
        for previous, current in zip(trace_by_window[window], trace_by_window[window][1:])
    )
    fluid_log = (RUN / "fluid.stdout").read_text(errors="replace")
    offset_events = re.findall(
        r"PHASE1K16_READ_OFFSET retry=(\d) windowComplete=(\d) offset=([\d.]+)", fluid_log
    )
    retry_offsets = [event for event in offset_events if event[0] == "1"]
    accepted_offsets = [event for event in offset_events if event[0] == "0"]
    result = {
        "classification": "PASS_EXPERIMENTAL_TWO_WINDOW_LIFECYCLE" if (
            len(trace_by_window[1]) == 20
            and len(trace_by_window[2]) == 20
            and len(accepted[1]) == len(accepted[2]) == 1
            and len(retries) == 38
            and all(r["point_matches_S0"] and r["cell_matches_S0"] and r["mesh_matches_S0"] for r in retries)
            and all(ancf_check[w]["q_qdot_qddot_all_match"] and ancf_check[w]["restore_count"] == 19
                    for w in (1, 2))
            and written_trial_match and force_chain
            and len(retry_offsets) == 38 and all(float(e[2]) == 0.0002 for e in retry_offsets)
            and len(accepted_offsets) == 1 and float(accepted_offsets[0][2]) == 0.0
            and per_window[2]["point_max_norm_m"] > 0.0
        ) else "REVIEW_REQUIRED",
        "window_summaries": per_window,
        "attempts_per_window": {w: len(trace_by_window[w]) for w in (1, 2)},
        "accepted_per_window": {w: len(accepted[w]) for w in (1, 2)},
        "retry_snapshots": retries,
        "ancf": ancf_check,
        "written_equals_trial_all_attempts": written_trial_match,
        "force_retry_chain_all_attempts": force_chain,
        "fluid_read_offset_events": Counter(offset_events).__repr__(),
        "retry_read_dt_count": len(retry_offsets),
        "accepted_boundary_read_zero_count": len(accepted_offsets),
    }
    (RUN / "qualification_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "retry_snapshots"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
