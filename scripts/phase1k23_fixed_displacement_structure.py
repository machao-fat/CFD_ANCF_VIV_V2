#!/usr/bin/env python3
"""Minimal Structure participant for the Phase 1K.23 Fluid operator replay."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import precice


def main() -> int:
    if len(sys.argv) != 5:
        raise SystemExit("usage: fixed_structure.py CONFIG OUTPUT DX DY")
    config = sys.argv[1]
    output = Path(sys.argv[2])
    displacement = [float(sys.argv[3]), float(sys.argv[4])]
    participant = precice.Participant("Structure_0000", config, 0, 1)
    vertex_ids = participant.set_mesh_vertices("Structure-Mesh", [[2.97, 0.0]])
    if not participant.requires_initial_data():
        raise RuntimeError("repeatability structure expected initialized coupling data")
    participant.write_data("Structure-Mesh", "Displacement", vertex_ids, [[0.0, 0.0]])
    initialized_dt = participant.initialize()
    dt = 0.0002 if initialized_dt is None else float(initialized_dt)
    records = [{
        "stage": "initial",
        "displacement_written": [0.0, 0.0],
        "force_at_relative_0": participant.read_data("Structure-Mesh", "Force", vertex_ids, 0.0).tolist(),
    }]
    attempt = 0
    while participant.is_coupling_ongoing():
        checkpoint = bool(participant.requires_writing_checkpoint())
        attempt += 1
        participant.write_data("Structure-Mesh", "Displacement", vertex_ids, [displacement])
        participant.advance(dt)
        retry = bool(participant.requires_reading_checkpoint())
        offset = dt if retry else 0.0
        force = participant.read_data("Structure-Mesh", "Force", vertex_ids, offset).tolist()
        records.append({
            "stage": "attempt",
            "attempt": attempt,
            "checkpoint_requested": checkpoint,
            "rollback_requested": retry,
            "relative_read_time_s": offset,
            "displacement_written": displacement,
            "force_received": force,
        })
    participant.finalize()
    output.write_text(json.dumps({
        "role": "Structure_0000",
        "displacement_star": displacement,
        "records": records,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"role": "Structure_0000", "attempts": attempt, "output": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
