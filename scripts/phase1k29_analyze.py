#!/usr/bin/env python3
"""Offline analysis for the completed bounded Phase 1K.29 runtime."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evidence/phase1k29_cfd_inner_convergence/run-20260925T214500Z-9747b00"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def norm(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def diff(a: list[float], b: list[float]) -> dict:
    return {"components": [float(y) - float(x) for x, y in zip(a, b)], "norm_N": norm(a, b)}


def doubles_sha(values) -> str:
    digest = hashlib.sha256()
    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        else:
            digest.update(struct.pack("<d", float(value)))
    visit(values)
    return digest.hexdigest()


def parse_residuals(label: str) -> list[dict]:
    text = (RUN / label / "fluid.stdout").read_text(encoding="utf-8", errors="replace")
    stage = re.compile(r'PHASE1K26_STAGE stage="S05_before_UEqn" solve=(\d+) outer=(\d+)')
    solve = re.compile(r'^(?:smoothSolver|GAMG):\s+Solving for (\w+), Initial residual = ([^,]+), Final residual = ([^,]+), No Iterations (\d+)')
    continuity = re.compile(r'time step continuity errors : sum local = ([^,]+), global = ([^,]+), cumulative = ([^\s]+)')
    current = None
    result = []
    for line in text.splitlines():
        hit = stage.search(line)
        if hit:
            current = {"solve_id": int(hit.group(1)), "outer": int(hit.group(2))}
        hit = solve.search(line)
        if hit and current is not None and hit.group(1) in {"Ux", "Uy", "p", "k", "omega"}:
            result.append({**current, "field": hit.group(1), "initial_residual": float(hit.group(2)), "final_residual": float(hit.group(3)), "iterations": int(hit.group(4))})
        hit = continuity.search(line)
        if hit and current is not None:
            result.append({**current, "diagnostic": "continuity", "sum_local": float(hit.group(1)), "global": float(hit.group(2)), "cumulative": float(hit.group(3))})
    return result


def final_direct(label: str) -> dict:
    records = rows(RUN / label / "direct_force_trace.jsonl")
    return next(x for x in records if x.get("coupling_attempt_index") == 4)


def outer(label: str) -> list[dict]:
    return rows(RUN / label / "outer_iteration_force_trace.jsonl")


def common_compare() -> dict:
    a = {(x["solve_id"], x["outer"]): x for x in outer("A")}
    b = {(x["solve_id"], x["outer"]): x for x in outer("B1")}
    result = []
    for key in sorted(set(a) & set(b)):
        if key[1] > 3:
            continue
        result.append({
            "solve_id": key[0], "outer": key[1],
            "raw_difference": diff(a[key]["raw_integrated_xyz"], b[key]["raw_integrated_xyz"]),
            "pressure_difference": diff(a[key]["pressure_integrated_xyz"], b[key]["pressure_integrated_xyz"]),
            "viscous_difference": diff(a[key]["viscous_integrated_xyz"], b[key]["viscous_integrated_xyz"]),
            "raw_array_hash_equal": a[key]["raw_array_hash"] == b[key]["raw_array_hash"],
        })
    return {"comparison": "A vs B1 corresponding solve/outer 1..3", "records": result,
            "all_equal": all(x["raw_difference"]["norm_N"] == 0 and x["raw_array_hash_equal"] for x in result),
            "first_divergence": next((x for x in result if not x["raw_array_hash_equal"]), None)}


def repeatability() -> dict:
    b1 = {(x["solve_id"], x["outer"]): x for x in outer("B1")}
    b2 = {(x["solve_id"], x["outer"]): x for x in outer("B2")}
    records = []
    for key in sorted(b1):
        records.append({"solve_id": key[0], "outer": key[1], "raw_difference": diff(b1[key]["raw_integrated_xyz"], b2[key]["raw_integrated_xyz"]), "raw_array_hash_equal": b1[key]["raw_array_hash"] == b2[key]["raw_array_hash"]})
    f1, f2 = final_direct("B1"), final_direct("B2")
    p1 = next(x for x in rows(RUN / "B1" / "adapter_prewrite_force.jsonl") if x.get("coupling_attempt_index") == 4)
    p2 = next(x for x in rows(RUN / "B2" / "adapter_prewrite_force.jsonl") if x.get("coupling_attempt_index") == 4)
    return {"B1_vs_B2": records, "all_outer_records_equal": all(x["raw_difference"]["norm_N"] == 0 and x["raw_array_hash_equal"] for x in records),
            "final_raw_force_B1": f1["raw_integrated_xyz"], "final_raw_force_B2": f2["raw_integrated_xyz"], "final_difference": diff(f1["raw_integrated_xyz"], f2["raw_integrated_xyz"]),
            "final_adapter_prewrite_sha256_B1": doubles_sha(p1["values"]), "final_adapter_prewrite_sha256_B2": doubles_sha(p2["values"]),
            "final_adapter_prewrite_l2_difference": norm(p1["values"], p2["values"]),
            "status": "PASS" if all(x["raw_difference"]["norm_N"] == 0 for x in records) and p1["values"] == p2["values"] else "FAIL"}


def main() -> int:
    identity = {
        "schema": "phase1k29_runtime_identity_v1",
        "git_head": "9747b00884e9a0f7f74160520c17353e2d1f7518",
        "git_branch": "diagnostic/phase1k29-cfd-inner-convergence-v1",
        "openfoam": "Foundation OpenFOAM 10", "precice": "3.4.1",
        "adapter_sha256": "0edcfae77d51d8a57a354a1b745c77f6c15108bf532be0d4893394e80a2d785d",
        "diagnostic_solver_sha256": json.loads((RUN / "solver_identity.json").read_text())["diagnostic_solver_sha256"],
        "d_star_m": [1.0633832164606064e-07, 9.530777190012017e-08], "dt_s": 0.0002,
        "one_physical_window": True, "attempt_ceiling": 4,
    }
    (RUN / "runtime_identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    restart = json.loads((RUN / "A/configuration.json").read_text())
    (RUN / "restart_identity.json").write_text(json.dumps({"global_time_s": 30.0, "mapFields_used": False, "restart_hashes": restart["restart_hashes"], "mesh_is_old_authoritative": True}, indent=2) + "\n")
    shutil.copy2(RUN / "A/configuration.json", RUN / "configuration_A.json")
    shutil.copy2(RUN / "B1/configuration.json", RUN / "configuration_B.json")
    for source, target in (("A", "A"), ("B1", "B")):
        (RUN / f"outer_iteration_force_trace_{target}.jsonl").write_text((RUN / source / "outer_iteration_force_trace.jsonl").read_text())
        (RUN / f"solver_residual_trace_{target}.jsonl").write_text("\n".join(json.dumps(x) for x in parse_residuals(source)) + "\n")
        structure = [x for x in json.loads((RUN / source / "fixed_structure_result.json").read_text())["records"] if x.get("stage") == "attempt"]
        (RUN / f"structure_received_force_{target}.jsonl").write_text("\n".join(json.dumps(x) for x in structure) + "\n")

    common = common_compare()
    (RUN / "trajectory_comparison.json").write_text(json.dumps(common, indent=2) + "\n")
    rep = repeatability()
    (RUN / "repeatability_B.json").write_text(json.dumps(rep, indent=2) + "\n")
    a, b = final_direct("A"), final_direct("B1")
    payload_a = next(x for x in rows(RUN / "A" / "adapter_prewrite_force.jsonl") if x.get("coupling_attempt_index") == 4)
    payload_b = next(x for x in rows(RUN / "B1" / "adapter_prewrite_force.jsonl") if x.get("coupling_attempt_index") == 4)
    outer_a = next(x for x in outer("A") if x["solve_id"] == 4 and x["outer"] == 3)
    outer_b = next(x for x in outer("B1") if x["solve_id"] == 4 and x["outer"] == 6)
    force = {"criterion": "conditional only; A/B common outer trajectory is not controlled", "A_final_raw_force_N": a["raw_integrated_xyz"], "B_final_raw_force_N": b["raw_integrated_xyz"],
             "observed_final_difference": diff(a["raw_integrated_xyz"], b["raw_integrated_xyz"]), "pressure_difference": diff(a["pressure_integrated_xyz"], b["pressure_integrated_xyz"]), "viscous_difference": diff(a["viscous_integrated_xyz"], b["viscous_integrated_xyz"]),
             "ratio_to_1e-3_N": norm(a["raw_integrated_xyz"], b["raw_integrated_xyz"]) / 1e-3, "relative_difference_to_A": norm(a["raw_integrated_xyz"], b["raw_integrated_xyz"]) / math.sqrt(sum(v*v for v in a["raw_integrated_xyz"])),
             "raw_array_hash_A": outer_a["raw_array_hash"], "raw_array_hash_B": outer_b["raw_array_hash"],
             "pressure_array_hash_A": outer_a["pressure_array_hash"], "pressure_array_hash_B": outer_b["pressure_array_hash"],
             "viscous_array_hash_A": outer_a["viscous_array_hash"], "viscous_array_hash_B": outer_b["viscous_array_hash"],
             "adapter_prewrite_value_sha256_A": doubles_sha(payload_a["values"]), "adapter_prewrite_value_sha256_B": doubles_sha(payload_b["values"]),
             "adapter_prewrite_value_l2_difference": norm(payload_a["values"], payload_b["values"]),
             "note": "A final outer=3 uses final solver entries; B outer=3 is not final because B has six outer correctors."}
    (RUN / "force_difference_A_vs_B.json").write_text(json.dumps(force, indent=2) + "\n")
    field_diff = {"fields": ["U", "p", "k", "omega", "nut", "phi"], "A_vs_B_final_hashes": {f: {"A": next(x for x in outer("A") if x["solve_id"] == 4 and x["outer"] == 3)["field_stats"][f]["hash"], "B": next(x for x in outer("B1") if x["solve_id"] == 4 and x["outer"] == 6)["field_stats"][f]["hash"]} for f in ["U", "p", "k", "omega", "nut", "phi"]}, "L2_difference": "NOT_OBSERVABLE_FROM_RECORDED_HASH_AND_STATS", "Linf_difference": "NOT_OBSERVABLE_FROM_RECORDED_HASH_AND_STATS", "reason": "K29 outer trace records field hashes and norms, but no full field snapshot was emitted by the isolated solver."}
    (RUN / "field_difference_A_vs_B.json").write_text(json.dumps(field_diff, indent=2) + "\n")
    summary = {"schema": "phase1k29_cfd_inner_convergence_qualification_v1", "classification": "INNER_AB_NOT_CONTROLLED", "A_configuration": {"nOuterCorrectors": 3, "nCorrectors": 2, "nNonOrthogonalCorrectors": 0, "momentumPredictor": True}, "B_configuration": {"nOuterCorrectors": 6, "nCorrectors": 2, "nNonOrthogonalCorrectors": 0, "momentumPredictor": True}, "common_outer_1_to_3_trajectory_equivalent": common["all_equal"], "first_divergence": common["first_divergence"], "B_fresh_repeatability": rep["status"], "observed_final_force_difference_N": force["observed_final_difference"]["norm_N"], "inner_adequacy_for_tested_state": "UNRESOLVED", "reason": "The first three common outer trajectories are not controlled because A outer 3 uses final solver settings while B outer 3 does not.", "next_cfd_inner_solver_repair_study": "NOT_AUTHORIZED_BY_K29; redesign control first", "iqn_retest": "NO"}
    (RUN / "qualification_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
