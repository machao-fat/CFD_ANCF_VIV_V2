#!/usr/bin/python3.10
"""Diagnostic launcher: capture the first accepted physical ANCF state."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "src/coupling/hh06_structure_0000/structure_0000_participant.py"
sys.path.insert(0, str(ROOT / "src"))
from coupling.arbitrary_n_live_orchestration_v1.coordinator import checkpoint_sha256


spec = importlib.util.spec_from_file_location("phase1k18_7a_structure", SOURCE)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load authoritative participant: {SOURCE}")
participant = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = participant
spec.loader.exec_module(participant)

Coordinator = participant.GenericStructuralCoordinator
original_commit = Coordinator.commit


def _capture_first_commit(coordinator):
    output = Path(os.environ["PHASE1K18_7A_ANCF_STATE_OUTPUT"])
    checkpoint = copy.deepcopy(coordinator._checkpoint)
    original_commit(coordinator)
    if coordinator.committed_structural_advances != 1:
        return
    payload = {
        "schema": "PHASE1K18_7A_ACCEPTED_ANCF_STATE_V1",
        "capture_point": "immediately after first accepted coordinator.commit()",
        "accepted_window_index": coordinator.committed_structural_advances,
        "checkpoint_active_after_commit": coordinator._checkpoint is not None,
    }
    try:
        backend = coordinator.backend
        dt_s = float(backend.bundle.dt_s)
        source_time_s = float(backend.bundle.root["initial_state"]["openfoam_global_time_s"])
        payload.update({
            "physical_identity": {
                "global_step": backend.committed_advance_count,
                "bridge_step": backend.committed_advance_count,
                "integer_tick": int(round(dt_s * 1.0e9)),
                "case_local_time_s": dt_s,
                "source_global_time_s": source_time_s,
                "accepted_global_time_s": source_time_s + dt_s,
                "dt_s": dt_s,
            },
            "accepted_state": {
                "q": list(backend.q),
                "qdot": list(backend.qdot),
                "qddot": list(backend.qddot),
                "q_sha256": participant._sha256_numbers(backend.q),
                "qdot_sha256": participant._sha256_numbers(backend.qdot),
                "qddot_sha256": participant._sha256_numbers(backend.qddot),
                "dof_count": backend.model.ndof,
                "committed_advance_count": backend.committed_advance_count,
                "attempted_advance_count": backend.attempted_advance_count,
                "transport_counters": {
                    "sequence": backend._transport_sequence_counter,
                    "request_id": backend._transport_request_id_counter,
                    "transaction_id": backend._transport_transaction_id_counter,
                },
                "pending": backend._pending,
            },
            "physical_checkpoint": None if checkpoint is None else checkpoint.to_dict(),
        })
        if checkpoint is not None:
            payload["physical_checkpoint"]["sha256"] = checkpoint_sha256(checkpoint)
    except Exception as exc:  # Preserve participant shutdown even if diagnostics fail.
        payload["capture_error"] = f"{type(exc).__name__}: {exc}"
        payload["capture_traceback"] = traceback.format_exc()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


Coordinator.commit = _capture_first_commit
raise SystemExit(participant.main(sys.argv[1:]))
