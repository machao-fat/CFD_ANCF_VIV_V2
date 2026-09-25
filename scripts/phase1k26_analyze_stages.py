#!/usr/bin/env python3
"""Summarize the frozen one-window Phase 1K.26 stage evidence.

This is read-only with respect to runtime cases. It does not equate the
preCICE-received (accelerated) Force with a direct OpenFOAM patch force.
"""

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evidence/phase1k26_earliest_divergence/run-20260925T-phase1k26-4182ac9"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def stages(run, attempt):
    return {f.name.replace(f"stage_{attempt}_", ""): read(f)
            for f in (RUN / run / "stages").glob(f"stage_{attempt}_*.json")}


def stage_diff(run, left, right):
    a, b = stages(run, left), stages(run, right)
    if a.keys() != b.keys():
        raise ValueError(f"stage sets differ: {run} {left}/{right}")
    result = []
    for stage in sorted(a):
        x, y = a[stage], b[stage]
        field_diffs = {
            key: {field_key: [x["fields"][key].get(field_key),
                              y["fields"][key].get(field_key)]
                  for field_key in x["fields"][key].keys()
                  if x["fields"][key].get(field_key) != y["fields"][key].get(field_key)}
            for key in x["fields"] if x["fields"][key] != y["fields"][key]
        }
        other_diffs = {
            key: [x[key], y[key]] for key in x
            if key not in ("fields", "solve_id", "pid") and x[key] != y[key]
        }
        result.append({"stage": stage, "field_differences": field_diffs,
                       "other_differences": other_diffs})
    return result


def forces(run):
    records = read(RUN / run / "fixed_structure_result.json")["records"]
    return [item["force_received"][0] for item in records if item["stage"] == "attempt"]


def postrollback_diff(run):
    directory = RUN / run / "diagnostics"
    a = read(directory / "S1_after_rollback_restore_retry_2.json")
    b = read(directory / "S1_after_rollback_restore_retry_3.json")
    return {group: [name for name in a[group] if a[group][name] != b[group].get(name)]
            for group in ("volScalarField", "volVectorField", "surfaceScalarField",
                          "surfaceVectorField", "pointVectorField", "mesh")}


def main():
    for run in ("same_process", "fresh_A", "fresh_B", "selected_causal_test_G2"):
        cleanup = read(RUN / run / "process_cleanup.json")
        if cleanup["stop_reason"] is not None or cleanup["exit_codes"] != {"fluid": 0, "structure": 0}:
            raise ValueError(f"unclean runtime: {run}")
        if len(stages(run, 1)) != 15:
            raise ValueError(f"incomplete stage trace: {run}")

    baseline = stage_diff("same_process", 3, 4)
    intervention = stage_diff("selected_causal_test_G2", 3, 4)
    first = next((x for x in baseline if x["field_differences"] or x["other_differences"]), None)
    if not first or first["stage"] != "S01_before_mesh_move.json" or "meshPhi" not in first["field_differences"]:
        raise ValueError("baseline earliest-stage expectation failed")
    if any(x["field_differences"] or x["other_differences"] for x in intervention):
        raise ValueError("G2 solver-stage equality expectation failed")
    s00_baseline = postrollback_diff("same_process")
    s00_g2 = postrollback_diff("selected_causal_test_G2")
    if s00_baseline["surfaceScalarField"] != ["meshPhi", "meshPhi_0"]:
        raise ValueError("unexpected post-rollback S00 divergence")
    if any(s00_g2.values()):
        raise ValueError("G2 post-rollback S00 states still differ")

    fresh_a = stages("fresh_A", 1)
    fresh_b = stages("fresh_B", 1)
    fresh_differences = []
    for attempt in range(1, 5):
        a, b = stages("fresh_A", attempt), stages("fresh_B", attempt)
        if a.keys() != b.keys():
            raise ValueError("fresh stage sets differ")
        for stage in a:
            x, y = dict(a[stage]), dict(b[stage])
            x.pop("pid", None)
            y.pop("pid", None)
            if x != y:
                fresh_differences.append(f"attempt {attempt}: {stage}")
    if fresh_differences:
        raise ValueError("fresh-process stage trajectories differ")

    baseline_forces = forces("same_process")
    g2_forces = forces("selected_causal_test_G2")
    if baseline_forces != forces("fresh_A") or baseline_forces != forces("fresh_B"):
        raise ValueError("fresh-process received-Force trajectories differ")
    baseline_delta = math.dist(baseline_forces[2], baseline_forces[3])
    g2_delta = math.dist(g2_forces[2], g2_forces[3])
    rbf = RUN / "same_process/rbf_diagnostics"
    rbf_5 = read(rbf / "S5_after_RBF_solve_call_5.json")
    rbf_7 = read(rbf / "S5_after_RBF_solve_call_7.json")
    rbf_diffs = {key: [rbf_5[key], rbf_7[key]] for key in rbf_5
                 if key not in ("stage", "pid") and rbf_5[key] != rbf_7[key]}

    write(RUN / "stage_diff.json", {
        "S00_postrollback_attempt_3_vs_4": s00_baseline,
        "G2_S00_postrollback_attempt_3_vs_4": s00_g2,
        "baseline_attempt_3_vs_4": baseline,
        "G2_attempt_3_vs_4": intervention,
        "fresh_A_vs_B_compared_stage_count": 4 * len(fresh_a),
        "fresh_A_vs_B_differences": fresh_differences,
        "RBF_call_5_vs_7_differences": rbf_diffs,
    })
    write(RUN / "earliest_divergence.json", {
        "valid_same_actual_fluid_input_pair": [3, 4],
        "invalid_same_input_pair": [1, 2],
        "earliest_divergence": {"stage": "S00_postrollback_before_readData_dt",
                                "objects": s00_baseline["surfaceScalarField"]},
        "first_solver_stage_divergence": first,
        "region": "ALE_FLUX_AFTER_ROLLBACK_BEFORE_READ_DATA_AND_MESH_MOVE",
        "candidate_qualifier": "meshPhi zeroing removes this stage difference but does not establish full Force-channel repeatability",
    })
    write(RUN / "force_comparison.json", {
        "force_kind": "Structure preCICE-received Force after exchange/acceleration; NOT direct OpenFOAM integrated Force",
        "baseline_received_force_N_per_attempt": baseline_forces,
        "G2_received_force_N_per_attempt": g2_forces,
        "baseline_attempt_3_to_4_difference_N": baseline_delta,
        "G2_attempt_3_to_4_difference_N": g2_delta,
        "difference_reduction_fraction": 1 - g2_delta / baseline_delta,
        "G2_difference_over_force_abs_limit_1e_3_N": g2_delta / 1e-3,
        "fresh_A_B_received_force_sequences_identical": True,
        "direct_openfoam_force_per_attempt": "NOT_MEASURED",
        "adapter_outgoing_unaccelerated_force_per_attempt": "NOT_MEASURED",
    })
    write(RUN / "qualification_summary.json", {
        "classification": "EARLIEST_DIVERGENCE_LOCALIZED_CAUSE_UNRESOLVED",
        "first_observable_difference": "meshPhi and meshPhi_0 at S00 after rollback, attempts 3 vs 4",
        "G2_causal_contribution_to_received_force_difference": True,
        "G2_sufficient_for_operator_repeatability": False,
        "fresh_process_stage_trajectory_reproducible": True,
        "RBF_same_input_output_identical": not rbf_diffs,
        "turbulence_runtime_causality": "NOT_SUPPORTED_BY_EARLIEST_STAGE",
        "RBF_runtime_causality": "NOT_SUPPORTED_BY_SAME_INPUT_RBF_OUTPUT",
        "inner_convergence_AB_authorized": False,
        "IQN_requalification_authorized": False,
    })


if __name__ == "__main__":
    main()
