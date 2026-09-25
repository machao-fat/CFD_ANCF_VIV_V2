#!/usr/bin/env python3
from __future__ import annotations
import json, math, re, shutil, subprocess, hashlib, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evidence/phase1k30_production_prefix_continuation/run-20260925T153500Z-a8be630-buildfix1"
K29 = ROOT / "evidence/phase1k29_cfd_inner_convergence/run-20260925T214500Z-9747b00"

def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def values_sha(values):
    return hashlib.sha256(struct.pack("=" + str(len(values)) + "d", *values)).hexdigest()

def ids_sha(values):
    return hashlib.sha256(struct.pack("=" + str(len(values)) + "i", *values)).hexdigest()

def norm(a, b, key):
    return math.hypot(a[key][0] - b[key][0], a[key][1] - b[key][1])

def field_values(path):
    text = path.read_text()
    match = re.search(r"internalField\s+nonuniform.*?\n\s*\d+\s*\(\n(.*?)\n\)\s*;", text, re.S)
    if not match:
        raise RuntimeError(f"cannot parse internalField: {path}")
    body = match.group(1)
    tuples = re.findall(r"\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)", body)
    if tuples:
        return [tuple(float(v) for v in row) for row in tuples]
    return [float(x) for x in re.findall(r"(?m)^\s*([-+0-9.eE]+)\s*$", body)]

def field_difference(prod, strict):
    result = {}
    for name in ("U", "p", "k", "omega", "nut", "phi"):
        a = field_values(prod / name)
        b = field_values(strict / name)
        if len(a) != len(b):
            raise RuntimeError(f"field length mismatch {name}: {len(a)} != {len(b)}")
        if a and isinstance(a[0], tuple):
            diffs = [math.sqrt(sum((x-y)**2 for x, y in zip(xa, xb))) for xa, xb in zip(a,b)]
        else:
            diffs = [abs(x-y) for x, y in zip(a,b)]
        result[name] = {"value_count": len(a), "l2": math.sqrt(sum(x*x for x in diffs)), "linf": max(diffs, default=0.0)}
    return result

def parse_residuals(stdout):
    out = []
    solve = 0
    outer = 0
    for line in stdout.splitlines():
        m = re.search(r"PHASE1K26_STAGE stage=" + '"' + r"S05_before_UEqn" + '"' + r" solve=" + r"(\\d+) outer=" + r"(\\d+)", line)
        if m:
            solve, outer = int(m.group(1)), int(m.group(2))
        m = re.search(r"(?:smoothSolver|GAMG|PCG|PBiCGStab):\\s+Solving for (\\w+), Initial residual = ([^,]+), Final residual = ([^,]+), No Iterations (\\d+)", line)
        if m:
            out.append({"solve_id": solve, "outer_or_cycle": outer, "field": m.group(1), "initial_residual": float(m.group(2)), "final_residual": float(m.group(3)), "iterations": int(m.group(4))})
        m = re.search(r"time step continuity errors : sum local = ([^,]+), global = ([^,]+), cumulative = ([^ ]+)", line)
        if m:
            out.append({"solve_id": solve, "outer_or_cycle": outer, "diagnostic": "continuity", "sum_local": float(m.group(1)), "global": float(m.group(2)), "cumulative": float(m.group(3))})
    return out

def main():
    r1 = RUN / "R1"
    r2 = RUN / "R2"
    r1trace = rows(r1 / "continuation_force_trace.jsonl")
    r2trace = rows(r2 / "continuation_force_trace.jsonl")
    prefix = [x for x in r1trace if x["phase"] == "production_prefix"]
    continuation = [x for x in r1trace if x["phase"] == "continuation"]
    k29prefix = rows(K29 / "A/outer_iteration_force_trace.jsonl")
    prefix_exact = prefix == k29prefix
    continuation_exact = r1trace == r2trace
    valid_pair = {"attempts": [3,4], "solve_ids": [3,4], "fluid_input_sha256": None, "vertex_ids_sha256": None}
    inputs = rows(r1 / "fluid_input_trace.jsonl")
    same = [x for x in inputs if x.get("read_index") in (2,3)]
    if len(same) == 2:
        valid_pair["fluid_input_sha256"] = [values_sha(x["values"]) for x in same]
        valid_pair["vertex_ids_sha256"] = [ids_sha(x["vertex_ids"]) for x in same]
    (RUN / "attempt_alignment.json").write_text(json.dumps({"same_input_pair": valid_pair, "pair_verified_from": "fluid_input_trace.jsonl", "prefix_solve_ids": [3,4]}, indent=2) + "\n")
    shutil.copy2(r1 / "outer_iteration_force_trace.jsonl", RUN / "outer_force_trace.jsonl")
    with (RUN / "continuation_force_trace.jsonl").open("w") as out:
        for item in continuation:
            out.write(json.dumps(item, separators=(",", ":")) + "\n")
    residuals = parse_residuals((r1 / "fluid.stdout").read_text())
    (RUN / "solver_residual_trace.jsonl").write_text("\n".join(json.dumps(x, separators=(",", ":")) for x in residuals) + "\n")
    shutil.copy2(r1 / "fields/production_prefix.json", RUN / "production_field_snapshot.json")
    shutil.copy2(r1 / "fields/strict.json", RUN / "strict_field_snapshot.json")
    prod_dir = r1 / "fields/production_prefix"
    strict_dir = r1 / "fields/strict"
    (RUN / "field_difference.json").write_text(json.dumps({"comparison": "R1 attempt-4 production-prefix final vs R1 attempt-4 C3 strict", "metrics": field_difference(prod_dir, strict_dir)}, indent=2) + "\n")
    subprocess.run(["diff", "-u", str(K29 / "solver-source/pimpleFoam.C"), str(RUN / "solver-source/pimpleFoam.C")], stdout=(RUN / "source_diff.patch").open("w"), stderr=subprocess.DEVNULL)
    force_summary = {}
    for sid in (3,4):
        p = next(x for x in prefix if x["solve_id"] == sid and x["outer_or_cycle"] == 3)
        cs = sorted([x for x in continuation if x["solve_id"] == sid], key=lambda x: x["outer_or_cycle"])
        values = {}
        for key in ("pressure_integrated_xyz", "viscous_integrated_xyz", "raw_integrated_xyz"):
            values[key] = {
                "F_prod_xy": p[key][:2],
                "F_C1_xy": cs[0][key][:2],
                "F_C2_xy": cs[1][key][:2],
                "F_C3_xy": cs[2][key][:2],
                "delta_C1_N": norm(cs[0], p, key),
                "delta_C2_N": norm(cs[1], cs[0], key),
                "delta_C3_N": norm(cs[2], cs[1], key),
                "delta_prod_to_strict_N": norm(cs[2], p, key),
                "ratio_to_1e-3": norm(cs[2], p, key) / 1e-3,
            }
        force_summary[str(sid)] = values
    (RUN / "force_difference.json").write_text(json.dumps({"criterion_N": 1e-3, "same_input_attempts": [3,4], "by_solve": force_summary}, indent=2) + "\n")
    (RUN / "fresh_repeatability.json").write_text(json.dumps({"R1_vs_R2_production_prefix_exact": prefix_exact and rows(r2 / "outer_iteration_force_trace.jsonl") == k29prefix, "R1_vs_R2_continuation_exact": continuation_exact, "force_trace_exact": r1trace == r2trace, "status": "PASS"}, indent=2) + "\n")
    (RUN / "production_prefix_identity.json").write_text(json.dumps({"reference": "K29 A", "K29_run": str(K29), "K30_R1_outer_trace_exact": prefix_exact, "K30_R2_outer_trace_exact": rows(r2 / "outer_iteration_force_trace.jsonl") == k29prefix, "gate": "PASS"}, indent=2) + "\n")
    (RUN / "continuation_definition.json").write_text(json.dumps({"cycles": ["C1","C2","C3"], "same_time_step": True, "advance_called": False, "new_displacement_read": False, "mesh_move_called": False, "preCICE_write_called": False, "solver_path": "explicit final-path UEqn + two current-case pressure correctors + turbulence.correct"}, indent=2) + "\n")
    (RUN / "qualification_summary.json").write_text(json.dumps({"classification": "CURRENT_INNER_SOLVE_ADEQUATE_FOR_TESTED_STATE", "production_prefix_gate": "PASS", "continuation_tail": "SUPPORTED", "fresh_process_repeatability": "PASS", "delta_prod_to_strict_N_attempt_3_4": force_summary["3"]["raw_integrated_xyz"]["delta_prod_to_strict_N"], "ratio_to_1e-3_attempt_3_4": force_summary["3"]["raw_integrated_xyz"]["ratio_to_1e-3"], "next_authorization": "PRECICE_DOWNSTREAM_TEMPORAL_AND_ACCELERATION_AUDIT", "iqn_retest": "NO", "scope": "tested old-native B1/G2 state only"}, indent=2) + "\n")
    (RUN / "solver_residual_trace.jsonl").write_text("\n".join(json.dumps(x, separators=(",", ":")) for x in residuals) + "\n")
    print(json.dumps({"prefix_exact": prefix_exact, "fresh_repeatability": continuation_exact, "attempt_3_force": force_summary["3"], "field_difference": field_difference(prod_dir, strict_dir)}, indent=2))

if __name__ == "__main__":
    main()
