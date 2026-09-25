#!/usr/bin/env python3
"""Analyze captured Phase 1K.27 Force-pipeline records; never launches CFD."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "run-20260925T090832Z-e0da50c"
RUN = ROOT / "evidence/phase1k27_force_pipeline" / RUN_ID
G2 = ROOT / "evidence/phase1k26_earliest_divergence/run-20260925T-phase1k26-4182ac9/selected_causal_test_G2"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise SystemExit("PHASE1K27_ANALYSIS_BLOCKED: " + message)


def load_json(path: Path):
    require(path.is_file(), f"missing evidence file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    require(path.is_file(), f"missing evidence file: {path}")
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
    return records


def flat_numeric(value) -> list[float]:
    if isinstance(value, (list, tuple)):
        out: list[float] = []
        for item in value:
            out.extend(flat_numeric(item))
        return out
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        require(math.isfinite(number), "non-finite value in captured evidence")
        return [number]
    raise SystemExit(f"expected numeric array, got {type(value).__name__}")


def doubles_sha(values) -> str:
    digest = hashlib.sha256()
    for value in flat_numeric(values):
        digest.update(struct.pack("<d", value))
    return digest.hexdigest()


def ids_sha(values) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(struct.pack("<q", int(value)))
    return digest.hexdigest()


def vector_xy(row: dict, key: str) -> list[float]:
    vector = row[key]
    require(len(vector) >= 2, f"{key} has fewer than two components")
    return [float(vector[0]), float(vector[1])]


def delta(a: list[float], b: list[float]) -> dict:
    require(len(a) == len(b), "cannot compare vectors of different dimensions")
    components = [y - x for x, y in zip(a, b)]
    return {"components": components, "norm": math.sqrt(sum(x * x for x in components))}


def normalize_stage(record: dict) -> dict:
    # These identify the record/process, not the physical state trajectory.
    return {key: value for key, value in record.items() if key not in {"solve_id", "pid"}}


def stage_pair_diff(first_id: int, second_id: int) -> dict:
    stage_dir = RUN / "stages"
    first_files = {p.name[len(f"stage_{first_id}_"):]: p for p in stage_dir.glob(f"stage_{first_id}_*.json")}
    second_files = {p.name[len(f"stage_{second_id}_"):]: p for p in stage_dir.glob(f"stage_{second_id}_*.json")}
    require(first_files and second_files, "solver stage traces are missing for solve IDs 3/4")
    require(set(first_files) == set(second_files), "stage name sets differ between solve IDs 3/4")
    rows = []
    for suffix in sorted(first_files):
        one, two = load_json(first_files[suffix]), load_json(second_files[suffix])
        one_norm, two_norm = normalize_stage(one), normalize_stage(two)
        rows.append({
            "stage_file_suffix": suffix,
            "stage": one.get("stage"),
            "attempt_3_sha256_canonical_json": hashlib.sha256(
                json.dumps(one_norm, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "attempt_4_sha256_canonical_json": hashlib.sha256(
                json.dumps(two_norm, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "equal_after_excluding_solve_id_and_pid": one_norm == two_norm,
            "attempt_3_time_identity": {k: one.get(k) for k in ("time_s", "time_index", "delta_t_s")},
            "attempt_4_time_identity": {k: two.get(k) for k in ("time_s", "time_index", "delta_t_s")},
        })
    return {
        "solve_id_pair": [first_id, second_id],
        "compared_stage_count": len(rows),
        "all_equal": all(row["equal_after_excluding_solve_id_and_pid"] for row in rows),
        "stage_records": rows,
    }


def extract_iqn_observations() -> dict:
    case = RUN / "prepared/case"
    iterations = case / "precice-Fluid_0000-iterations.log"
    convergence = case / "precice-Fluid_0000-convergence.log"
    stdout = RUN / "fluid.stdout"
    for src, dest in (
        (iterations, RUN / "precice_iterations.log"),
        (convergence, RUN / "precice_convergence.log"),
    ):
        require(src.is_file(), f"missing preCICE diagnostic log: {src}")
        dest.write_bytes(src.read_bytes())
    iteration_text = iterations.read_text(encoding="utf-8", errors="replace")
    convergence_text = convergence.read_text(encoding="utf-8", errors="replace")
    stdout_text = stdout.read_text(encoding="utf-8", errors="replace") if stdout.is_file() else ""
    summary_lines = [line for line in iteration_text.splitlines() if line.strip()]
    table_rows = []
    for line in summary_lines:
        fields = line.split()
        if fields and fields[0].isdigit() and len(fields) == 7:
            table_rows.append({
                "time_window": int(fields[0]), "total_iterations": int(fields[1]),
                "iterations": int(fields[2]), "convergence_flag": int(fields[3]),
                "qn_columns": int(fields[4]), "deleted_qn_columns": int(fields[5]),
                "dropped_qn_columns": int(fields[6]),
            })
    iqn_lines = [line for line in stdout_text.splitlines()
                 if re.search(r"IQN|QNColumns|DroppedQN|DeletedQN|acceleration|column", line, re.I)]
    return {
        "iterations_log_path": str(RUN / "precice_iterations.log"),
        "iterations_log_sha256": hashlib.sha256((RUN / "precice_iterations.log").read_bytes()).hexdigest(),
        "iterations_log_lines": summary_lines,
        "parsed_iterations_rows": table_rows,
        "convergence_log_path": str(RUN / "precice_convergence.log"),
        "convergence_log_sha256": hashlib.sha256((RUN / "precice_convergence.log").read_bytes()).hexdigest(),
        "convergence_log_known_anomaly": "all per-data residual values are zero in this generated log; not used as quantitative force/displacement residual evidence",
        "convergence_log_lines": [line for line in convergence_text.splitlines() if line.strip()],
        "participant_iqn_lines": iqn_lines,
        "detailed_preCICE_convergence_messages": [
            line for line in stdout_text.splitlines() if "measureConvergence" in line
        ],
        "recorded_mapping_events": [
            line for line in stdout_text.splitlines() if 'Mapping "Force"' in line
        ],
        "pre_acceleration_vector": "NOT_DIRECTLY_OBSERVABLE",
        "diagnostic_interpretation": "preCICE writeData receives the adapter preWrite array; mapping and implicit acceleration are applied in advance() before the Structure read. The installed runtime's internal pre-acceleration vector was not instrumented.",
    }


def main() -> int:
    if len(sys.argv) != 2 or Path(sys.argv[1]).resolve() != RUN.resolve():
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} {RUN}")
    direct = load_jsonl(RUN / "direct_force_trace.jsonl")
    prewrite = load_jsonl(RUN / "adapter_prewrite_force.jsonl")
    fluid_inputs = load_jsonl(RUN / "fluid_input_trace.jsonl")
    structure = load_json(RUN / "fixed_structure_result.json")
    require(structure.get("role") == "Structure_0000", "unexpected Structure result identity")

    direct_by_write = {int(row["write_index"]): row for row in direct}
    payload_by_write = {int(row["write_index"]): row for row in prewrite}
    require(len(direct_by_write) == len(direct) and len(payload_by_write) == len(prewrite),
            "duplicate adapter writer ordinal")
    require(set(direct_by_write) == set(payload_by_write), "direct force and preWrite ordinals differ")
    require(sorted(direct_by_write) == [0, 1, 2, 3, 4], "expected initial Force plus four attempt Force records")
    require(sorted(payload_by_write) == [0, 1, 2, 3, 4], "expected initial payload plus four attempt payloads")

    attempt_rows = {int(row["attempt"]): row for row in structure["records"] if row.get("stage") == "attempt"}
    require(sorted(attempt_rows) == [1, 2, 3, 4], "expected exactly attempts 1..4 in Structure result")
    inputs_by_solve = {int(row["next_fluid_solve_index"]): row for row in fluid_inputs}
    require(len(inputs_by_solve) == len(fluid_inputs), "duplicate next Fluid solve index in input trace")

    input3 = inputs_by_solve.get(3)
    input4 = inputs_by_solve.get(4)
    require(input3 is not None and input4 is not None, "no actual Fluid-read displacement records align to solves 3/4")
    input_values3 = flat_numeric(input3["values"])
    input_values4 = flat_numeric(input4["values"])
    require(len(input_values3) == len(input_values4) == 400, "Fluid displacement input is not 200 2-D vertices")

    stage_diff = stage_pair_diff(3, 4)
    solve_ids = sorted({int(path.name.split("_", 2)[1]) for path in (RUN / "stages").glob("stage_*.json")})
    require(solve_ids == [1, 2, 3, 4], f"unexpected Fluid solve identities: {solve_ids}")
    attempt_alignment = {
        "attempt_pair": [3, 4],
        "basis": "Fluid displacement read ordinal + next_fluid_solve_index; adapter Force writer ordinal; Structure attempt ordinal; matching physical time/timeIndex; G2 solver solve_id",
        "fluid_input_3": {
            "read_index": input3["read_index"], "next_fluid_solve_index": input3["next_fluid_solve_index"],
            "relative_read_time_s": input3["relative_read_time_s"], "global_time_s": input3["global_time_s"],
            "time_index": input3["time_index"], "vertex_count": len(input3["vertex_ids"]),
            "value_count": len(input_values3), "values_sha256_ieee754_le": doubles_sha(input_values3),
            "first_8_values": input_values3[:8], "max_abs_value": max(map(abs, input_values3)),
            "vertex_ids_sha256_int64_le": ids_sha(input3["vertex_ids"]),
        },
        "fluid_input_4": {
            "read_index": input4["read_index"], "next_fluid_solve_index": input4["next_fluid_solve_index"],
            "relative_read_time_s": input4["relative_read_time_s"], "global_time_s": input4["global_time_s"],
            "time_index": input4["time_index"], "vertex_count": len(input4["vertex_ids"]),
            "value_count": len(input_values4), "values_sha256_ieee754_le": doubles_sha(input_values4),
            "first_8_values": input_values4[:8], "max_abs_value": max(map(abs, input_values4)),
            "vertex_ids_sha256_int64_le": ids_sha(input4["vertex_ids"]),
        },
        "actual_fluid_read_displacements_equal": input_values3 == input_values4,
        "same_read_offset": input3["relative_read_time_s"] == input4["relative_read_time_s"],
        "same_time_identity": (input3["global_time_s"], input3["time_index"])
            == (input4["global_time_s"], input4["time_index"]),
        "adapter_read_call_openfoam_time_s": input3["global_time_s"],
        "adapter_read_call_time_index": input3["time_index"],
        "next_fluid_solve_target_global_time_s": load_json(
            RUN / "stages/stage_3_S01_before_mesh_move.json")["time_s"],
        "force_source_global_time_s": 30.0002,
        "window_target_global_time_s": 30.0002,
        "stage_records_3_4": stage_diff,
        "force_writer_ordinals": [3, 4],
        "structure_attempt_ids": [3, 4],
    }
    require(attempt_alignment["actual_fluid_read_displacements_equal"],
            "Fluid-read displacement differs: cannot treat attempts 3/4 as a same-input pair")
    require(attempt_alignment["same_read_offset"] and attempt_alignment["same_time_identity"],
            "Fluid read branch or time identity differs for attempts 3/4")
    attempt_alignment["structure_force_read_offsets_s"] = {
        "attempt_3_retry_endpoint": attempt_rows[3]["relative_read_time_s"],
        "attempt_4_accepted_boundary": attempt_rows[4]["relative_read_time_s"],
    }
    attempt_alignment["same_structure_force_read_offset"] = (
        attempt_rows[3]["relative_read_time_s"] == attempt_rows[4]["relative_read_time_s"])

    comparisons = {}
    for attempt in (3, 4):
        drow, prow = direct_by_write[attempt], payload_by_write[attempt]
        forcefaces = drow["faces"]
        require(len(forcefaces) == 200, f"direct force attempt {attempt} did not capture 200 faces")
        require(prow["vertex_count"] == 200 and prow["value_count"] == 400,
                f"preWrite attempt {attempt} did not capture 200 2-D vertices")
        direct_xy = [component for face in forcefaces for component in face["total_xyz"][:2]]
        require(len(direct_xy) == len(prow["values"]), "raw per-face x/y and preWrite buffer dimensions differ")
        direct_time = (drow["global_time_s"], drow["time_index"])
        stage_s11 = load_json(RUN / "stages" / f"stage_{attempt}_S11_before_runTime_write.json")
        require(direct_time == (stage_s11["time_s"], stage_s11["time_index"]),
                f"Force event ordinal {attempt} does not match solver stage time identity")
        comparisons[attempt] = {
            "physical_window_index": 1,
            "coupling_attempt_index": attempt,
            "write_index": attempt,
            "global_time_s": drow["global_time_s"],
            "time_index": drow["time_index"],
            "direct_face_count": len(forcefaces),
            "face_ordering": drow["face_ordering"],
            "pressure_array_sha256_ieee754_le": doubles_sha([f["pressure_xyz"] for f in forcefaces]),
            "viscous_array_sha256_ieee754_le": doubles_sha([f["viscous_xyz"] for f in forcefaces]),
            "raw_total_array_sha256_ieee754_le": doubles_sha([f["total_xyz"] for f in forcefaces]),
            "raw_integrated_xyz_N": drow["raw_integrated_xyz"],
            "pressure_integrated_xyz_N": drow["pressure_integrated_xyz"],
            "viscous_integrated_xyz_N": drow["viscous_integrated_xyz"],
            "adapter_vertex_ids_sha256_int64_le": ids_sha(prow["vertex_ids"]),
            "adapter_prewrite_buffer_sha256_ieee754_le": doubles_sha(prow["values"]),
            "adapter_prewrite_sum_xy_N": prow["sum_xy"],
            "direct_face_total_xy_sha256_ieee754_le": doubles_sha(direct_xy),
            "direct_face_total_xy_equals_prewrite_exactly": direct_xy == flat_numeric(prow["values"]),
            "structure_received_force_N": flat_numeric(attempt_rows[attempt]["force_received"]),
            "structure_force_read_offset_s": attempt_rows[attempt]["relative_read_time_s"],
            "structure_rollback_requested": attempt_rows[attempt]["rollback_requested"],
        }

    raw3 = vector_xy(comparisons[3], "raw_integrated_xyz_N")
    raw4 = vector_xy(comparisons[4], "raw_integrated_xyz_N")
    pressure3 = vector_xy(comparisons[3], "pressure_integrated_xyz_N")
    pressure4 = vector_xy(comparisons[4], "pressure_integrated_xyz_N")
    viscous3 = vector_xy(comparisons[3], "viscous_integrated_xyz_N")
    viscous4 = vector_xy(comparisons[4], "viscous_integrated_xyz_N")
    payload3 = flat_numeric(payload_by_write[3]["values"])
    payload4 = flat_numeric(payload_by_write[4]["values"])
    struct3 = flat_numeric(attempt_rows[3]["force_received"])
    struct4 = flat_numeric(attempt_rows[4]["force_received"])

    force_diff = {
        "raw_openfoam_force": {
            "attempt_3_xy_N": raw3, "attempt_4_xy_N": raw4,
            "difference": delta(raw3, raw4),
            "per_face_total_hash_equal": comparisons[3]["raw_total_array_sha256_ieee754_le"]
                == comparisons[4]["raw_total_array_sha256_ieee754_le"],
        },
        "pressure_contribution": {
            "attempt_3_xy_N": pressure3, "attempt_4_xy_N": pressure4,
            "difference": delta(pressure3, pressure4),
            "per_face_hash_equal": comparisons[3]["pressure_array_sha256_ieee754_le"]
                == comparisons[4]["pressure_array_sha256_ieee754_le"],
        },
        "viscous_contribution": {
            "attempt_3_xy_N": viscous3, "attempt_4_xy_N": viscous4,
            "difference": delta(viscous3, viscous4),
            "per_face_hash_equal": comparisons[3]["viscous_array_sha256_ieee754_le"]
                == comparisons[4]["viscous_array_sha256_ieee754_le"],
        },
        "adapter_prewrite_payload": {
            "attempt_3_sum_xy_N": payload_by_write[3]["sum_xy"],
            "attempt_4_sum_xy_N": payload_by_write[4]["sum_xy"],
            "attempt_3_sha256_ieee754_le": comparisons[3]["adapter_prewrite_buffer_sha256_ieee754_le"],
            "attempt_4_sha256_ieee754_le": comparisons[4]["adapter_prewrite_buffer_sha256_ieee754_le"],
            "full_buffer_equal": payload3 == payload4,
            "vertex_ids_equal": payload_by_write[3]["vertex_ids"] == payload_by_write[4]["vertex_ids"],
            "sum_difference": delta(payload_by_write[3]["sum_xy"], payload_by_write[4]["sum_xy"]),
            "full_buffer_difference_l2": math.sqrt(sum((b - a) ** 2 for a, b in zip(payload3, payload4))),
            "direct_xy_matches_prewrite_attempt3": comparisons[3]["direct_face_total_xy_equals_prewrite_exactly"],
            "direct_xy_matches_prewrite_attempt4": comparisons[4]["direct_face_total_xy_equals_prewrite_exactly"],
        },
        "structure_received_force": {
            "attempt_3_N": struct3, "attempt_4_N": struct4,
            "difference": delta(struct3, struct4),
        },
    }

    initial_direct = direct_by_write[0]
    initial_received = next(row for row in structure["records"] if row.get("stage") == "initial")
    f0_expected = [0.0655270406896, 0.05872987414832]
    f0_direct = vector_xy(initial_direct, "raw_integrated_xyz")
    f0_received = flat_numeric(initial_received["force_at_relative_0"])
    require(len(f0_received) == 2, "initial Structure Force is not a single 2-D vector")
    f0_direct_diff = delta(f0_expected, f0_direct)
    f0_received_diff = delta(f0_expected, f0_received)
    f0_direct_component_abs = [abs(x) for x in f0_direct_diff["components"]]
    f0_received_component_abs = [abs(x) for x in f0_received_diff["components"]]
    f0_gate = {
        "expected_raw_xy_N": f0_expected,
        "direct_openfoam_initial_raw_xy_N": f0_direct,
        "structure_initial_received_xy_N": f0_received,
        "direct_difference_norm_N": f0_direct_diff["norm"],
        "structure_difference_norm_N": f0_received_diff["norm"],
        "qualified_tolerance_N": 5e-13,
        "tolerance_interpretation": "component-wise x/y, consistent with the frozen qualification statement",
        "direct_component_abs_differences_N": f0_direct_component_abs,
        "structure_component_abs_differences_N": f0_received_component_abs,
        "pass": max(f0_direct_component_abs + f0_received_component_abs) < 5e-13,
    }

    raw_equal = force_diff["raw_openfoam_force"]["difference"]["norm"] == 0.0 and force_diff["raw_openfoam_force"]["per_face_total_hash_equal"]
    payload_equal = force_diff["adapter_prewrite_payload"]["full_buffer_equal"] and force_diff["adapter_prewrite_payload"]["vertex_ids_equal"]
    direct_payload_consistent = all(force_diff["adapter_prewrite_payload"][key] for key in (
        "direct_xy_matches_prewrite_attempt3", "direct_xy_matches_prewrite_attempt4"))

    if not f0_gate["pass"]:
        classification = "BLOCKED_BY_FORCE_OBSERVABILITY"
        reason = "The diagnostic initial raw/received Force does not match the frozen new-mesh F0 tolerance."
    elif not stage_diff["all_equal"]:
        classification = "FORCE_PIPELINE_DIVERGENCE_UNRESOLVED"
        reason = "K26 G2 solver stages 3/4 are not equal in the reproduced runtime; downstream Force attribution is not isolated."
    elif not raw_equal:
        classification = "DIRECT_OPENFOAM_FORCE_NOT_REPEATABLE"
        reason = "The same-input pair differs in direct per-face/integrated OpenFOAM Force."
    elif not payload_equal:
        classification = "ADAPTER_FORCE_PAYLOAD_STATE_CAUSAL"
        reason = "Direct OpenFOAM Force repeats, but the exact adapter preWrite payload or vertex IDs differ."
    elif not direct_payload_consistent:
        classification = "FORCE_PIPELINE_DIVERGENCE_UNRESOLVED"
        reason = "Per-face raw force and preWrite payload do not agree exactly; inspect packing/summation before attribution."
    elif force_diff["structure_received_force"]["difference"]["norm"] != 0.0:
        classification = "PRECICE_DOWNSTREAM_STATE_EXPLAINS_RECEIVED_FORCE_DIFFERENCE"
        reason = ("Raw per-face Force and exact adapter preWrite array repeat, while Structure reads differ downstream of adapter write. "
                  "The required read offsets differ (retry dt versus accepted-boundary 0), so this locates the difference downstream but does not isolate IQN-history effects from temporal read sampling.")
    else:
        classification = "FLUID_OPERATOR_REPEATABILITY_ESTABLISHED_ON_TESTED_G2_BRANCH"
        reason = "Same Fluid input yields matching raw force and adapter payload; Structure read also matches for this pair."

    precice_audit = extract_iqn_observations()
    require(len(precice_audit["parsed_iterations_rows"]) == 1,
            "expected exactly one preCICE summary row for the one-window diagnostic")
    iteration_row = precice_audit["parsed_iterations_rows"][0]
    require(iteration_row["time_window"] == 1 and iteration_row["iterations"] == len(attempt_rows),
            "preCICE iteration summary and Structure attempt count disagree")
    if iteration_row["convergence_flag"] == 1:
        acceptance = "CONVERGED_BEFORE_DIAGNOSTIC_CEILING"
    elif iteration_row["iterations"] == 4:
        acceptance = "ACCEPTED_AT_ITERATION_LIMIT"
    else:
        acceptance = "NOT_CONVERGED_OR_ACCEPTANCE_STATUS_UNRESOLVED"
    precice_audit.update({
        "coupling_scheme": "parallel-implicit",
        "participant_order": ["Structure_0000", "Fluid_0000"],
        "mapping_force": {"direction": "write", "from": "Fluid-Mesh", "to": "Structure-Mesh", "type": "nearest-neighbor", "constraint": "conservative"},
        "mapping_displacement": {"direction": "read", "from": "Structure-Mesh", "to": "Fluid-Mesh", "type": "nearest-neighbor", "constraint": "consistent"},
        "iqn_ils_primary_data": ["Displacement", "Force"],
        "iqn_ils_max_used_iterations": 1,
        "force_mapping_and_acceleration_internal_values": "NOT_DIRECTLY_OBSERVABLE",
        "mapped_force_scalar_per_attempt": "NOT_DIRECTLY_OBSERVABLE_AS_A_SEPARATE_BUFFER; conservative write mapping is configured, and exact identical preWrite arrays imply identical mapping input",
        "structure_read_is_raw_force": False,
        "structure_force_read_offsets_s": attempt_alignment["structure_force_read_offsets_s"],
        "same_structure_force_read_branch_attempts_3_4": attempt_alignment["same_structure_force_read_offset"],
        "force_read_timing_interpretation": "Attempt 3 uses dt at the retry endpoint; attempt 4 uses 0 at the accepted boundary. This is the required participant contract, but means the two Structure reads are not a same-offset comparison.",
        "window_acceptance_classification": acceptance,
    })

    attempt_alignment["result_classification"] = classification
    attempt_alignment["decision_reason"] = reason
    attempt_alignment["same_fluid_input_and_stage_prerequisites"] = bool(
        attempt_alignment["actual_fluid_read_displacements_equal"] and stage_diff["all_equal"])
    (RUN / "attempt_alignment.json").write_text(json.dumps(attempt_alignment, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (RUN / "force_stage_diff.json").write_text(json.dumps({
        "initial_f0_gate": f0_gate,
        "attempts": comparisons,
        "differences": force_diff,
        "classification": classification,
        "reason": reason,
        "hash_encoding": "SHA256 of IEEE-754 binary64 little-endian values in recorded array order; vertex IDs are signed int64 little-endian in recorded order.",
    }, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (RUN / "precice_acceleration_audit.json").write_text(json.dumps(precice_audit, indent=2) + "\n", encoding="utf-8")

    structure_force_records = []
    for attempt in sorted(attempt_rows):
        row = attempt_rows[attempt]
        structure_force_records.append({
            "physical_window_index": 1,
            "coupling_attempt_index": attempt,
            "force_source_global_time_s": 30.0002,
            "window_target_global_time_s": 30.0002,
            "force_read_offset_s": row["relative_read_time_s"],
            "force_vector_received_N": flat_numeric(row["force_received"]),
            "rollback_requested": row["rollback_requested"],
            "force_semantics": "Structure read value after preCICE advance; mapped/accelerated coupling iterate, not raw OpenFOAM force",
        })
    (RUN / "structure_received_force.jsonl").write_text(
        "".join(json.dumps(row, allow_nan=False) + "\n" for row in structure_force_records), encoding="utf-8")

    stage_records = []
    for path in sorted((RUN / "stages").glob("stage_*.json")):
        stage_records.append(load_json(path))
    (RUN / "solver_stage_trace.jsonl").write_text(
        "".join(json.dumps(row, allow_nan=False) + "\n" for row in stage_records), encoding="utf-8")

    pipeline_map = {
        "raw_openfoam_force": "FSI/ForceBase.C::writeToBuffer; per-face pressure plus viscous traction in Force field, integrated here before mapping/acceleration",
        "adapter_unaccelerated_write_payload": "Interface.C::writeCouplingData; dataBuffer and vertexIDs immediately before precice_.writeData(Force)",
        "precice_mapping": "Fluid-Mesh to Structure-Mesh, nearest-neighbor conservative write mapping, performed during advance()",
        "precice_accelerated_iterate": "parallel-implicit IQN-ILS coupling data after mapping/exchange/acceleration during advance(); internal pre-acceleration vector is not directly exposed",
        "structure_received_force": "Structure participant read_data Force after advance at the required retry/accepted read offset",
        "same_input_pair": [3, 4],
        "structure_force_read_offsets_s": {"attempt_3": attempt_rows[3]["relative_read_time_s"],
                                            "attempt_4": attempt_rows[4]["relative_read_time_s"]},
        "same_structure_force_read_branch": attempt_alignment["same_structure_force_read_offset"],
        "native_attempt_id_available_inside_adapter": False,
        "alignment_basis": attempt_alignment["basis"],
        "diagnostic_adapter_sha256": json.loads((RUN / "runtime_identity.json").read_text())["adapter_sha256"],
        "diagnostic_adapter_build_id": json.loads((RUN / "runtime_identity.json").read_text())["adapter_build_id"],
    }
    (RUN / "force_pipeline_map.json").write_text(json.dumps(pipeline_map, indent=2) + "\n", encoding="utf-8")

    profiling = RUN / "prepared/case/precice-profiling"
    if profiling.is_dir():
        import shutil
        shutil.copytree(profiling, RUN / "precice-profiling", dirs_exist_ok=True)

    summary = {
        "phase": "1K.27",
        "classification": classification,
        "diagnostic_only": True,
        "physical_windows_completed": 1,
        "structure_attempt_count": len(attempt_rows),
        "iterations_per_window": [iteration_row["iterations"]],
        "window_acceptance_classification": acceptance,
        "diagnostic_iteration_ceiling": 4,
        "window_converged": False,
        "acceptance_semantics": "not a convergence pass; one-window diagnostic ceiling only",
        "attempts_3_4_same_actual_fluid_input": attempt_alignment["actual_fluid_read_displacements_equal"],
        "attempts_3_4_all_solver_stages_equal": stage_diff["all_equal"],
        "attempts_3_4_raw_openfoam_force_repeatable": raw_equal,
        "attempts_3_4_adapter_prewrite_repeatable": payload_equal,
        "attempts_3_4_structure_received_force_difference_N": force_diff["structure_received_force"]["difference"]["norm"],
        "attempts_3_4_structure_read_offsets_s": attempt_alignment["structure_force_read_offsets_s"],
        "attempts_3_4_structure_read_branches_match": attempt_alignment["same_structure_force_read_offset"],
        "pre_acceleration_vector_directly_observed": False,
        "cfd_inner_convergence_ab_authorized_next": bool(f0_gate["pass"] and raw_equal and payload_equal and direct_payload_consistent and stage_diff["all_equal"]),
        "initial_f0_gate": f0_gate,
        "iqn_retest_authorized": False,
        "runtime_repair_or_parameter_change": False,
        "process_cleanup_path": str(RUN / "process_cleanup.json"),
        "evidence_path": str(RUN),
    }
    (RUN / "qualification_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
