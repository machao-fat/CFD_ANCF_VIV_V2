#!/usr/bin/env python3
"""Analyze the completed Phase 1K.28 B0/B1 runs without launching CFD."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/phase1k28_old_native_reference"
B0 = EVIDENCE / "run-20260925T113000Z-fc0f94d-b0"
B1 = EVIDENCE / "run-20260925T113000Z-fc0f94d-b1-g2b"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("PHASE1K28_ANALYSIS_BLOCKED: " + message)


def load(path: Path):
    require(path.is_file(), f"missing evidence: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def rows(run: Path, name: str) -> list[dict]:
    path = run / name
    require(path.is_file(), f"missing JSONL evidence: {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def flat(value) -> list[float]:
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(flat(item))
        return result
    number = float(value)
    require(math.isfinite(number), "non-finite numeric evidence")
    return [number]


def doubles_sha(value) -> str:
    digest = hashlib.sha256()
    for number in flat(value):
        digest.update(struct.pack("<d", number))
    return digest.hexdigest()


def ids_sha(value) -> str:
    digest = hashlib.sha256()
    for number in value:
        digest.update(struct.pack("<q", int(number)))
    return digest.hexdigest()


def norm(a, b) -> float:
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def vector_diff(a, b) -> dict:
    return {"components": [float(y) - float(x) for x, y in zip(a, b)], "norm": norm(a, b)}


def force_summary(run: Path, attempt: int) -> dict:
    direct = next(x for x in rows(run, "direct_force_trace.jsonl")
                  if x.get("coupling_attempt_index") == attempt)
    payload = next(x for x in rows(run, "adapter_prewrite_force.jsonl")
                   if x.get("coupling_attempt_index") == attempt)
    faces = direct["faces"]
    return {
        "attempt": attempt,
        "raw_force_xy_N": direct["raw_integrated_xyz"][:2],
        "pressure_xy_N": direct["pressure_integrated_xyz"][:2],
        "viscous_xy_N": direct["viscous_integrated_xyz"][:2],
        "pressure_array_sha256_ieee754_le": doubles_sha([f["pressure_xyz"] for f in faces]),
        "viscous_array_sha256_ieee754_le": doubles_sha([f["viscous_xyz"] for f in faces]),
        "raw_total_array_sha256_ieee754_le": doubles_sha([f["total_xyz"] for f in faces]),
        "adapter_prewrite_xy_N": payload["sum_xy"],
        "adapter_prewrite_buffer_sha256_ieee754_le": doubles_sha(payload["values"]),
        "adapter_vertex_ids_sha256_int64_le": ids_sha(payload["vertex_ids"]),
        "face_count": len(faces),
        "payload_value_count": len(payload["values"]),
    }


def force_comparison(run: Path) -> dict:
    a, b = force_summary(run, 3), force_summary(run, 4)
    return {
        "attempt_pair": [3, 4],
        "attempt_3": a,
        "attempt_4": b,
        "raw_force_difference": vector_diff(a["raw_force_xy_N"], b["raw_force_xy_N"]),
        "pressure_difference": vector_diff(a["pressure_xy_N"], b["pressure_xy_N"]),
        "viscous_difference": vector_diff(a["viscous_xy_N"], b["viscous_xy_N"]),
        "adapter_prewrite_difference": vector_diff(a["adapter_prewrite_xy_N"], b["adapter_prewrite_xy_N"]),
        "raw_pressure_array_equal": a["pressure_array_sha256_ieee754_le"] == b["pressure_array_sha256_ieee754_le"],
        "raw_viscous_array_equal": a["viscous_array_sha256_ieee754_le"] == b["viscous_array_sha256_ieee754_le"],
        "raw_total_array_equal": a["raw_total_array_sha256_ieee754_le"] == b["raw_total_array_sha256_ieee754_le"],
        "adapter_prewrite_full_buffer_equal": a["adapter_prewrite_buffer_sha256_ieee754_le"] == b["adapter_prewrite_buffer_sha256_ieee754_le"],
    }


def alignment(run: Path) -> dict:
    inputs = rows(run, "fluid_input_trace.jsonl")
    a = next(x for x in inputs if x["next_fluid_solve_index"] == 3)
    b = next(x for x in inputs if x["next_fluid_solve_index"] == 4)
    structures = [x for x in load(run / "fixed_structure_result.json")["records"] if x.get("stage") == "attempt"]
    s3, s4 = structures[2], structures[3]
    return {
        "valid_pair": [3, 4],
        "criterion": "same physical window, same Fluid read offset, same complete displacement values and vertex order, same time identity",
        "fluid_input_3": {"read_index": a["read_index"], "solve_index": a["next_fluid_solve_index"],
                           "relative_read_time_s": a["relative_read_time_s"], "global_time_s": a["global_time_s"],
                           "time_index": a["time_index"], "values_sha256_ieee754_le": doubles_sha(a["values"]),
                           "vertex_ids_sha256_int64_le": ids_sha(a["vertex_ids"]), "value_count": len(a["values"])},
        "fluid_input_4": {"read_index": b["read_index"], "solve_index": b["next_fluid_solve_index"],
                           "relative_read_time_s": b["relative_read_time_s"], "global_time_s": b["global_time_s"],
                           "time_index": b["time_index"], "values_sha256_ieee754_le": doubles_sha(b["values"]),
                           "vertex_ids_sha256_int64_le": ids_sha(b["vertex_ids"]), "value_count": len(b["values"])},
        "actual_fluid_input_equal": a["values"] == b["values"],
        "vertex_order_equal": a["vertex_ids"] == b["vertex_ids"],
        "read_offset_equal": a["relative_read_time_s"] == b["relative_read_time_s"],
        "time_identity_equal": (a["global_time_s"], a["time_index"]) == (b["global_time_s"], b["time_index"]),
        "structure_read_attempt_3": {"force_N": s3["force_received"], "relative_read_time_s": s3["relative_read_time_s"]},
        "structure_read_attempt_4": {"force_N": s4["force_received"], "relative_read_time_s": s4["relative_read_time_s"]},
    }


def state_inventory(run: Path, stage: str) -> dict:
    d = load(run / "diagnostics" / f"{stage}.json")
    result = {"stage": stage, "mesh": d["mesh"], "objects": {}}
    for group in ("volScalarField", "volVectorField", "surfaceScalarField", "surfaceVectorField", "pointVectorField"):
        for name, value in d.get(group, {}).items():
            if isinstance(value, dict) and "state" in value:
                result["objects"][f"{group}:{name}"] = value["state"]
    return result


def stage_trace(run: Path) -> list[dict]:
    records = []
    for path in sorted((run / "stages").glob("stage_*.json")):
        d = load(path)
        fields = {}
        for name, value in d.get("fields", {}).items():
            fields[name] = {k: v for k, v in value.items() if k not in ("values", "boundary_values")}
        records.append({"file": path.name, "solve_id": d["solve_id"], "stage": d["stage"],
                        "outer": d["outer"], "time_s": d["time_s"], "time_index": d["time_index"],
                        "moving": d["moving"], "changing": d["changing"], "points_hash": d["points_hash"],
                        "fields": fields})
    return records


def rollback_trace(run: Path) -> list[dict]:
    return [state_inventory(run, "S0_after_checkpoint_save_1"),
            state_inventory(run, "S1_after_rollback_restore_retry_1")]


def structure_trace(run: Path) -> list[dict]:
    return [x for x in load(run / "fixed_structure_result.json")["records"] if x.get("stage") == "attempt"]


def compare_stages(run: Path) -> dict:
    result = []
    for p in sorted((run / "stages").glob("stage_3_*.json")):
        q = run / "stages" / p.name.replace("stage_3_", "stage_4_")
        a, b = load(p), load(q)
        na = {k: v for k, v in a.items() if k not in ("solve_id", "pid")}
        nb = {k: v for k, v in b.items() if k not in ("solve_id", "pid")}
        result.append({"stage": a["stage"], "file_suffix": p.name.removeprefix("stage_3_"),
                       "equal_excluding_identity": na == nb,
                       "attempt_3_canonical_sha256": hashlib.sha256(json.dumps(na, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                       "attempt_4_canonical_sha256": hashlib.sha256(json.dumps(nb, sort_keys=True, separators=(",", ":")).encode()).hexdigest()})
    return {"pair": [3, 4], "stage_count": len(result), "all_equal_excluding_identity": all(x["equal_excluding_identity"] for x in result), "records": result}


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    for run in (B0, B1):
        require(load(run / "process_cleanup.json")["exit_codes"] == {"fluid": 0, "structure": 0}, f"participant cleanup failed: {run}")
        al = alignment(run)
        require(all(al[x] for x in ("actual_fluid_input_equal", "vertex_order_equal", "read_offset_equal", "time_identity_equal")),
                f"attempts 3/4 are not a valid same-input pair: {run}")
        write(run / "s0_state_inventory.json", state_inventory(run, "S0_after_checkpoint_save_1"))
        write(run / "s1_postrollback_state_inventory.json", state_inventory(run, "S1_after_rollback_restore_retry_1"))
        (run / "rollback_state_trace.jsonl").write_text("\n".join(json.dumps(x) for x in rollback_trace(run)) + "\n", encoding="utf-8")
        write(run / "solver_stage_trace.json", stage_trace(run))
        (run / "structure_received_force.jsonl").write_text("\n".join(json.dumps(x) for x in structure_trace(run)) + "\n", encoding="utf-8")
        write(run / "attempt_alignment.json", al)
        write(run / "force_comparison.json", force_comparison(run))
        write(run / "stage_pair_comparison.json", compare_stages(run))
    b0_force, b1_force = force_comparison(B0), force_comparison(B1)
    write(B0 / "baseline_vs_k27.json", {
        "comparison_scope": "tested same-input attempts 3/4; Structure received Force is not raw Fluid operator output",
        "k27_new_mesh_g2": {"raw_difference_N": 0.0, "adapter_prewrite_difference_N": 0.0,
                             "structure_received_difference_N": 0.01869480300014619,
                             "classification": "FLUID_OPERATOR_REPEATABILITY_ESTABLISHED_ON_TESTED_G2_BRANCH"},
        "k28_old_native_b0": {"raw_difference_N": b0_force["raw_force_difference"]["norm"],
                               "adapter_prewrite_difference_N": b0_force["adapter_prewrite_difference"]["norm"],
                               "classification": "ALE_HISTORY_MISMATCH_PRESENT_EFFECT_ESTABLISHED"},
        "k28_old_native_b1_g2": {"raw_difference_N": b1_force["raw_force_difference"]["norm"],
                                  "adapter_prewrite_difference_N": b1_force["adapter_prewrite_difference"]["norm"],
                                  "classification": "GENERIC_ALE_ROLLBACK_STATE_CAUSAL"},
        "supports": "C_BOTH_BRANCHES_REPEATABLE_AFTER_G2_BUT_DOWNSTREAM_PRECICE_STATEFUL_BEHAVIOR_REMAINS",
    })
    structure_b1 = alignment(B1)
    s3 = flat(structure_b1["structure_read_attempt_3"]["force_N"])
    s4 = flat(structure_b1["structure_read_attempt_4"]["force_N"])
    summary = {
        "schema": "phase1k28_old_native_software_reference_qualification_v1",
        "classification": "GENERIC_ALE_ROLLBACK_STATE_CAUSAL",
        "old_native_restart_mesh_field_consistency": "YES_SCOPED_REFERENCE",
        "valid_same_fluid_input_pair": {"answer": "YES", "attempts": [3, 4],
            "values_sha256_ieee754_le": alignment(B1)["fluid_input_3"]["values_sha256_ieee754_le"],
            "vertex_ids_sha256_int64_le": alignment(B1)["fluid_input_3"]["vertex_ids_sha256_int64_le"]},
        "b0": {"candidate": "OLD_NATIVE_BASELINE_DIAG", "meshphi_mismatch": True,
               "raw_force_difference_N": b0_force["raw_force_difference"]["norm"],
               "adapter_prewrite_difference_N": b0_force["adapter_prewrite_difference"]["norm"],
               "repeatability": "NOT_SUPPORTED"},
        "b1": {"candidate": "OLD_NATIVE_G2_DIAG", "meshphi_s0_s1_canonicalized": True,
               "raw_force_difference_N": b1_force["raw_force_difference"]["norm"],
               "pressure_difference_N": b1_force["pressure_difference"]["norm"],
               "viscous_difference_N": b1_force["viscous_difference"]["norm"],
               "adapter_prewrite_difference_N": b1_force["adapter_prewrite_difference"]["norm"],
               "raw_and_prewrite_repeatability": "SUPPORTED_ON_TESTED_PAIR"},
        "structure_received_force_b1_difference_N": norm(s3, s4),
        "structure_read_offsets_s": {"attempt_3": 0.0002, "attempt_4": 0.0},
        "fluid_operator_old_native": "SUPPORTED_ON_TESTED_B1_G2_BRANCH",
        "g2_required": "YES",
        "next_cfd_inner_convergence_diagnostic": "YES_AUTHORIZED_NEXT_DIAGNOSTIC_ON_B1_G2_REFERENCE_ONLY",
        "iqn_retest": "NO_NOT_AUTHORIZED",
        "convergence_status": "ACCEPTED_AT_ITERATION_LIMIT_NOT_CONVERGED",
        "limitations": ["one physical window", "one same-input pair", "experimental B1 only; not production repair", "no fresh-process B1 control was run under the K28 stop rule"],
    }
    for run, role in ((B0, "B0 baseline"), (B1, "B1 G2 candidate")):
        run_summary = dict(summary)
        run_summary["run_role"] = role
        run_summary["run_id"] = run.name
        write(run / "qualification_summary.json", run_summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
