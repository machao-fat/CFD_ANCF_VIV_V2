#!/usr/bin/env python3
"""Read-only Phase 1K.11 evidence reduction; creates JSON summaries, never runs FSI."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[3]
NEW = ROOT / "evidence/phase1k11_25window_rbf_fsi/run-20260924T095422Z-c2245ff"
OLD = ROOT / "evidence/phase1i_25window_iqn/run-20260923T143029Z-c2245ff"
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def put(name: str, value):
    (NEW / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def field_series(root: Path, name: str, labels: tuple[str, ...]):
    path = root / "case/postProcessing" / name / "30/volFieldValue.dat"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        tokens = line.split()
        if len(tokens) < len(labels) + 1:
            continue
        try:
            numbers = [float(item) for item in tokens[:len(labels) + 1]]
        except ValueError:
            continue
        rows.append({"global_time_s": numbers[0], **dict(zip(labels, numbers[1:]))})
    return rows


def extrema(rows, label):
    values = [row[label] for row in rows if label in row]
    return {"min": min(values), "max": max(values)} if values else None


def forces(root: Path):
    path = root / "case/postProcessing/cylinderForces/30/forces.dat"
    if not path.is_file():
        return []
    rows = []
    pattern = re.compile(rf"^\s*({NUMBER})\s+\(\(([^)]+)\)\s+\(([^)]+)\)\)")
    for line in path.read_text().splitlines():
        match = pattern.search(line)
        if not match:
            continue
        pressure = [float(x) for x in match.group(2).split()]
        viscous = [float(x) for x in match.group(3).split()]
        total = [a + b for a, b in zip(pressure, viscous)]
        rows.append({"global_time_s": float(match.group(1)), "pressure_N": pressure,
                     "viscous_N": viscous, "total_N": total,
                     "xy_norm_N": math.hypot(*total[:2])})
    return rows


def log_metrics(root: Path):
    text = (root / "fluid.stdout").read_text(errors="replace")
    stderr = (root / "fluid.stderr").read_text(errors="replace")
    fluid_co = [float(x) for x in re.findall(rf"^Courant Number mean:\s*{NUMBER}\s+max:\s*({NUMBER})", text, re.M)]
    mesh_co = [float(x) for x in re.findall(rf"^Mesh Courant Number mean:\s*{NUMBER}\s+max:\s*({NUMBER})", text, re.M)]
    return {"fluid_Co_max": max(fluid_co, default=None), "mesh_Co_max": max(mesh_co, default=None),
            "fluid_Co_samples": len(fluid_co), "mesh_Co_samples": len(mesh_co),
            "cfd_advances": len(re.findall(r"^Time\s*=", text, re.M)),
            "openfoam_fatal": "FOAM FATAL" in text,
            "sigfpe": "Floating point exception" in text + stderr or "GAMGSolver::scale" in text + stderr,
            "rbf_control_point_selections": [list(map(int, m)) for m in re.findall(
                r"RBF interpolation coarsening: selected (\d+)/(\d+) points", text)],
            "rbf_max_interpolation_error": max((float(x) for x in re.findall(
                rf"RBF interpolation coarsening: .*?max\(error\) = ({NUMBER})", text)), default=None)}


def point_coords(path: Path):
    data = path.read_bytes()
    match = re.search(rb"\n(\d+)\s*\(", data)
    if match is None:
        raise ValueError(f"cannot parse OpenFOAM point list: {path}")
    count = int(match.group(1))
    end = match.end() + count * 24
    if data[end:end + 1] != b")":
        raise ValueError(f"incomplete binary OpenFOAM point list: {path}")
    return [xyz for xyz in struct.iter_unpack("<ddd", data[match.end():end])]


def saved_cell_volume_metrics(root: Path):
    observations = []
    for directory in (root / "case").iterdir():
        if not directory.is_dir() or not (directory / "V").is_file():
            continue
        try:
            global_time = float(directory.name)
        except ValueError:
            continue
        data = (directory / "V").read_bytes()
        match = re.search(rb"internalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\(\s*", data)
        if match is None:
            continue
        end = match.end() + int(match.group(1)) * 8
        if data[end:end+1] != b")":
            continue
        values = [item[0] for item in struct.iter_unpack("<d", data[match.end():end])]
        observations.append({"global_time_s": global_time, "min_cell_volume_m3": min(values),
                             "non_positive_cells": sum(value <= 0 for value in values)})
    return {"min_cell_volume_m3": min((row["min_cell_volume_m3"] for row in observations), default=None),
            "max_non_positive_cells_in_saved_field": max((row["non_positive_cells"] for row in observations), default=None),
            "saved_time_observations": sorted(observations, key=lambda x: x["global_time_s"])}


def mesh_metrics(root: Path):
    snapshots = []
    previous = point_coords(root / "case/constant/polyMesh/points")
    base = previous
    for window in range(1, 26):
        time = format(30 + 0.0002 * window, ".4f").rstrip("0")
        path = root / "case" / time / "polyMesh/points"
        current = point_coords(path)
        if len(current) != len(previous):
            raise ValueError(f"point-count changed at window {window}")
        step_max = max(math.dist(a, b) for a, b in zip(current, previous))
        displacement_max = max(math.dist(a, b) for a, b in zip(current, base))
        snapshots.append({"window": window, "global_time_s": float(time),
                          "accepted_mesh_max_step_displacement_m": step_max,
                          "accepted_mesh_max_displacement_from_release_m": displacement_max,
                          "accepted_mesh_max_velocity_estimate_mps": step_max / 0.0002,
                          "points_sha256": sha(path)})
        previous = current
    checks = {}
    for window in (1, 5, 10, 15, 20, 25):
        text = (root / f"checkMesh_window{window}.log").read_text()
        def value(pattern):
            match = re.search(pattern, text)
            return float(match.group(1)) if match else None
        checks[str(window)] = {"mesh_ok": "Mesh OK." in text,
                               "min_cell_volume_m3": value(rf"Min volume = ({NUMBER})"),
                               "max_nonorthogonality_deg": value(rf"Mesh non-orthogonality Max: ({NUMBER})"),
                               "max_skewness": value(rf"Max skewness = ({NUMBER})")}
    return {"accepted_window_snapshots": snapshots, "selected_checkMesh": checks,
            "all_accepted_mesh_point_coordinates_equal_release": all(
                row["accepted_mesh_max_displacement_from_release_m"] == 0.0 for row in snapshots),
            "mesh_velocity_scope": "accepted-window point difference / dt; not a per-attempt mesh-velocity maximum"}


def iqn(root: Path):
    path = root / "precice-Fluid_0000-iterations.log"
    rows = []
    for line in path.read_text().splitlines()[1:]:
        words = line.split()
        if len(words) >= 7 and words[0].isdigit():
            values = list(map(int, words[:7]))
            rows.append(dict(zip(("window", "total_iterations", "iterations", "convergence_flag",
                                  "qn_columns", "deleted_qn_columns_cumulative",
                                  "dropped_qn_columns_cumulative"), values)))
    text = (root / "fluid.stdout").read_text(errors="replace")
    warnings = [line.strip() for line in text.splitlines() if "WARNING" in line or "Warning" in line]
    return {"per_window": rows, "warnings": warnings,
            "warning_count": len(warnings), "final_qn_columns": rows[-1]["qn_columns"] if rows else None,
            "final_deleted_columns": rows[-1]["deleted_qn_columns_cumulative"] if rows else None,
            "final_dropped_columns": rows[-1]["dropped_qn_columns_cumulative"] if rows else None}


def main():
    summary = read_json(NEW / "qualification_summary.json")
    trace = [json.loads(line) for line in (NEW / "structure_trace.jsonl").read_text().splitlines() if line.strip()]
    old_summary = read_json(OLD / "qualification_summary.json")
    new_log, old_log = log_metrics(NEW), log_metrics(OLD)
    new_forces, old_forces = forces(NEW), forces(OLD)
    series = {}
    for name, labels in (("phase1iUMax", ("max_U_mps",)),
                         ("phase1iTurbulenceMax", ("max_k", "max_omega", "max_nut")),
                         ("phase1k11PMin", ("min_p",)), ("phase1k11PMax", ("max_p",)),
                         ("phase1k11TurbulenceMin", ("min_k", "min_omega", "min_nut"))):
        series[name] = field_series(NEW, name, labels)
    mesh = mesh_metrics(NEW)
    new_volumes = saved_cell_volume_metrics(NEW)
    old_volumes = saved_cell_volume_metrics(OLD)
    iqn_result = iqn(NEW)
    max_force = max(new_forces, key=lambda x: x["xy_norm_N"])
    first_force = [x for x in new_forces if x["global_time_s"] <= 30.0002 + 1e-10]
    first_returned = [{"window": record["window_index"],
                       "xy_norm_N": math.hypot(*record["returned_force_raw_N"][:2])}
                      for record in trace if record["iteration_index"] == 1]
    accepted_returned = [{"window": record["window_index"],
                          "xy_norm_N": math.hypot(*record["returned_force_raw_N"][:2])}
                         for record in trace if record["commit_status"] == "committed"]
    fluid = {**new_log, "saved_cell_volumes": new_volumes,
             "field_extrema": {label: extrema(rows, label) for name, rows in series.items()
                               for label in (rows[0].keys() if rows else []) if label != "global_time_s"},
             "raw_force_max_xy_norm": max_force,
             "raw_force_max_abs_fx_N": max(abs(row["total_N"][0]) for row in new_forces),
             "raw_force_max_abs_fy_N": max(abs(row["total_N"][1]) for row in new_forces),
             "first_window_force_records": first_force,
             "first_trial_returned_force_by_window": first_returned,
             "accepted_returned_force_by_window": accepted_returned,
             "raw_force_history": new_forces}
    put("fluid_metrics.json", fluid)
    put("rbf_metrics.json", {"rbf_log": {key: value for key, value in new_log.items() if key.startswith("rbf_")},
                             **mesh, "saved_cell_volumes": new_volumes})
    put("iqn_metrics.json", iqn_result)
    put("mesh_identity.json", {"restart_mesh_sha256": read_json(NEW / "runtime_identity.json")["restart"]["mesh_hashes_sha256"],
                               "mesh_cell_count": 46826, "cylinder_faces": 200,
                               "rbf_library": read_json(NEW / "runtime_identity.json")["rbf"]})
    put("restart_identity.json", read_json(NEW / "runtime_identity.json")["restart"])
    put("new_f0.json", read_json(Path(__file__).resolve().parent / "new_f0_qualified_result.json"))
    force_ratio = 1.98 / 0.028
    max_applied = max(math.hypot(*record["force_input_applied_N"][:2]) for record in trace)
    max_displacement = max(math.hypot(*record["D_trial_interface_m"][:2]) for record in trace)
    contract = {"D_written_equals_D_trial_all_attempts": all(
                    record["D_written_to_precice_m"] == record["D_trial_interface_m"] for record in trace),
                "retry_force_chain_all_attempts": all(
                    trace[i]["force_input_vector_raw_N"] == trace[i-1]["returned_force_raw_N"]
                    for i in range(1, len(trace)) if trace[i]["window_index"] == trace[i-1]["window_index"]),
                "retry_read_offset_dt_all_attempts": all(
                    record["force_input_read_offset_s"] == 0.0002 for record in trace
                    if record["iteration_index"] > 1),
                "transport_sequences": [record["sequence"] for record in trace],
                "max_interface_displacement_xy_norm_m": max_displacement,
                "max_applied_strip_force_xy_norm_N": max_applied,
                "force_scale_strip_per_raw": force_ratio,
                "total_ancf_newton_iterations": sum(record["ancf_newton_iterations"] for record in trace),
                "total_ancf_solves": len(trace)}
    put("coupling_contract_metrics.json", contract)
    historical = {"comparison_scope": "Phase 1I old-mesh Laplacian and Phase 1K.11 mapped new-mesh TPS-RBF differ in mesh, ALE and mapped release field; not a single-variable causal isolation",
                  "old": {"completed_windows": old_summary["completed_windows"],
                          "failure": old_summary["failure"], "coupling_attempts": old_summary["coupling_attempts"],
                          "wall_clock_s": old_summary["wall_clock_seconds"], **old_log,
                          "max_raw_force_xy_norm_N": max((x["xy_norm_N"] for x in old_forces), default=None),
                          "iterations_per_window": old_summary["iterations_per_window"],
                          "saved_cell_volumes": old_volumes,
                          "max_U_mps": (extrema(field_series(OLD, "phase1iUMax", ("max_U_mps",)), "max_U_mps") or {}).get("max"),
                          "max_omega": (extrema(field_series(OLD, "phase1iTurbulenceMax", ("max_k", "max_omega", "max_nut")), "max_omega") or {}).get("max")},
                  "new": {"completed_windows": summary["completed_windows"],
                          "failure": summary["failure"], "coupling_attempts": summary["coupling_attempts"],
                          "wall_clock_s": summary["wall_clock_seconds"], **new_log,
                          "max_raw_force_xy_norm_N": max_force["xy_norm_N"],
                          "iterations_per_window": summary["iterations_per_window"],
                          "saved_cell_volumes": new_volumes,
                          "max_U_mps": fluid["field_extrema"]["max_U_mps"]["max"],
                          "max_omega": fluid["field_extrema"]["max_omega"]["max"]}}
    put("historical_comparison.json", historical)
    put("qualification_assessment.json", {
        "final_classification": "REVIEW_REQUIRED",
        "runtime_completed_25_windows": summary["completed_windows"] == 25,
        "implicit_contract": "PASS" if all(isinstance(value, bool) and value for value in contract.values()
                                              if isinstance(value, bool)) else "FAIL",
        "reason": "Large recurring rejected-trial pressure/Force spikes grow through window 25; "
                  "all saved accepted-window mesh coordinates equal release despite nonzero structural displacement. "
                  "The 25-window endpoint is reached without Co, volume, or solver failure, but RBF/ALE physical "
                  "displacement transfer and stress-response mechanism need a read-only forensic audit.",
        "max_rejected_raw_force_xy_norm_N": max_force["xy_norm_N"],
        "max_structure_trial_displacement_m": max_displacement,
        "accepted_mesh_stationary": mesh["all_accepted_mesh_point_coordinates_equal_release"],
        "no_automatic_rerun": True,
    })
    print(json.dumps({"classification": summary["classification"], "fluid_Co": new_log["fluid_Co_max"],
                      "mesh_Co": new_log["mesh_Co_max"], "max_raw_force": max_force,
                      "max_applied_strip_force_N": max_applied, "max_D_m": max_displacement,
                      "max_mesh_velocity_estimate_mps": max(x["accepted_mesh_max_velocity_estimate_mps"]
                                                          for x in mesh["accepted_window_snapshots"]),
                      "IQN": {k: iqn_result[k] for k in ("warning_count", "final_qn_columns", "final_deleted_columns", "final_dropped_columns")},
                      "contract": {key: value for key, value in contract.items() if isinstance(value, bool)}}, indent=2))


if __name__ == "__main__":
    main()
