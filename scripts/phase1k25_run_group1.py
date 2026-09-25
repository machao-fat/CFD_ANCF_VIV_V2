#!/usr/bin/env python3
"""Run the isolated Phase 1K.25 Group 1 history canonicalization candidate."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from phase1k24_fluid_state_replay import (  # noqa: E402
    ADAPTER,
    BASE,
    EXPECTED_DT,
    RBF,
    WORKER,
    copy_case,
    launch,
    patch_case,
    record_identity,
    validate,
)
import phase1k24_fluid_state_replay as base_runner  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
G1_ROOT = ROOT / "evidence/phase1k25_minimal_rollback_repair/run-20260925T080000Z-d3890de-G1"
G1_ADAPTER = G1_ROOT / "candidate-G1/adapter-build/libpreciceAdapterPhase1K25G1Diag.so"
G2_ROOT = ROOT / "evidence/phase1k25_minimal_rollback_repair/run-20260925T080000Z-d3890de-G2"
G2_ADAPTER = G2_ROOT / "candidate-G2/adapter-build/libpreciceAdapterPhase1K25G2Diag.so"
G3_ROOT = ROOT / "evidence/phase1k25_minimal_rollback_repair/run-20260925T080000Z-d3890de-G3"
G3_ADAPTER = G3_ROOT / "candidate-G3/adapter-build/libpreciceAdapterPhase1K25G3Diag.so"


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in (
        "same-process", "fresh-a", "fresh-b",
        "g2-same-process", "g2-fresh-a", "g2-fresh-b",
        "g3-same-process", "g3-fresh-a", "g3-fresh-b",
    ):
        raise SystemExit("usage: phase1k25_run_group1.py MODE RUN_DIR")
    mode = sys.argv[1]
    run = Path(sys.argv[2]).expanduser().resolve()
    base_runner.ADAPTER = G1_ADAPTER
    candidate = "GROUP1_FIELD_HISTORY_CANONICALIZATION"
    adapter = G1_ADAPTER
    if mode.startswith("g2-"):
        candidate = "GROUP2_MESHPHI_ZERO_CANONICALIZATION"
        adapter = G2_ADAPTER
        mode = mode[3:]
    elif mode.startswith("g3-"):
        candidate = "GROUP3_FVMESH_ZERO_MOTION_CANONICALIZATION"
        adapter = G3_ADAPTER
        mode = mode[3:]
    base_runner.ADAPTER = adapter
    max_iterations, min_iterations = (4, 2) if mode == "same-process" else (1, 1)
    case = copy_case(run)
    patch_case(case, run, max_iterations, min_iterations)
    identity = record_identity(run, case, candidate.lower() + "-" + mode, max_iterations, min_iterations)
    identity.update({
        "candidate": candidate,
        "candidate_classification": "CANONICALIZED_INITIAL_STATE" if candidate.startswith("GROUP1") else "RESTORE_CANONICALIZATION_ONLY",
        "candidate_adapter_sha256": base_runner.sha(adapter),
        "candidate_adapter_path": str(adapter),
    })
    (run / "runtime_identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    validate(run, case)
    (run / "preflight_status.json").write_text(json.dumps({"status": "PASS_PREFLIGHT_ONLY", "candidate": identity}, indent=2) + "\n", encoding="utf-8")
    cleanup = launch(run, case)
    require = base_runner.require
    require(cleanup["stop_reason"] is None, "runtime stopped before clean completion")
    require(all(code == 0 for code in cleanup["exit_codes"].values()), "runtime participant failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
