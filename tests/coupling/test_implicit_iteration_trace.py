"""Deterministic characterization of the HH06 implicit retry data path.

This test replaces both external endpoints with fakes and exercises the real
Structure participant loop and GenericStructuralCoordinator. It never imports
or initializes a preCICE participant, OpenFOAM, or the C++ worker.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from coupling.arbitrary_n_live_orchestration_v1.manifest import (
    OrchestrationSlice,
    SliceManifest,
)
from coupling.hh06_structure_0000 import structure_0000_participant as participant


def _sha(values: list[float]) -> str:
    return hashlib.sha256(struct.pack("<" + "d" * len(values), *values)).hexdigest()


def _manifest() -> SliceManifest:
    item = OrchestrationSlice(
        slice_id="slice_0000",
        ordinal=0,
        s_ref_m=2.0,
        slice_length_m=1.0,
        unit_span_m=1.0,
        fluid_participant="Fluid_0000",
        structure_participant="Structure_0000",
        structure_mesh="Structure-Mesh",
        fluid_mesh="Fluid-Mesh",
        force_data="Force",
        motion_data="Displacement",
        openfoam_case_id="fake-implicit-case",
        force_slot=0,
        motion_slot=0,
    )
    return SliceManifest(
        schema_version="arbitrary-n-live-coupling-v1",
        case_id="fake-implicit-case",
        reference_length_m=4.0,
        active_start_m=1.5,
        active_end_m=2.5,
        reconstruction_mode="LegacyPointLumped",
        endpoint_policy="NearestConstant",
        structure_participant="Structure_0000",
        slices=(item,),
    )


class _FakeWorker:
    instances: list["_FakeWorker"] = []

    def __init__(self, bundle, manifest, worker_path) -> None:
        self.bundle = bundle
        self.manifest = manifest
        self.worker_path = worker_path
        self.model = SimpleNamespace(ndof=3)
        self.q = [0.0, 0.0, 0.0]
        self.qdot = [0.0, 0.0, 0.0]
        self.qddot = [0.0, 0.0, 0.0]
        self.committed_advance_count = 0
        self.pending = False
        self.sequence = 0
        self.request_id = 500
        self.transaction_id = 900
        self.input_states: list[tuple[list[float], list[float], list[float]]] = []
        self.started = False
        self.closed = False
        type(self).instances.append(self)

    def start(self) -> None:
        self.started = True

    def snapshot(self):
        return {
            "q": list(self.q),
            "qdot": list(self.qdot),
            "qddot": list(self.qddot),
            "committed": self.committed_advance_count,
            "pending": self.pending,
        }

    def restore(self, snapshot) -> None:
        self.q = list(snapshot["q"])
        self.qdot = list(snapshot["qdot"])
        self.qddot = list(snapshot["qddot"])
        self.committed_advance_count = int(snapshot["committed"])
        self.pending = bool(snapshot["pending"])

    def advance(self, request):
        self.input_states.append((list(self.q), list(self.qdot), list(self.qddot)))
        fy = float(request.slice_force_N[1])
        self.q[1] += 0.1 * fy
        self.qdot[1] = fy
        self.qddot[1] = 2.0 * fy
        self.pending = True
        self.sequence += 1
        self.request_id += 1
        self.transaction_id += 1
        step = self.committed_advance_count + 1
        tick = int(round(request.time_s * 1_000_000))
        return {
            "iterations": 2,
            "residual": 1.0e-12,
            "q_sha256": _sha(self.q),
            "qdot_sha256": _sha(self.qdot),
            "qddot_sha256": _sha(self.qddot),
            "sequence": self.sequence,
            "request_id": self.request_id,
            "transaction_id": self.transaction_id,
            "physical_identity": {
                "global_step": step,
                "bridge_step": step,
                "integer_tick": tick,
                "time_s": request.time_s,
                "dt_s": self.bundle.dt_s,
            },
        }

    def commit(self) -> None:
        if not self.pending:
            raise AssertionError("fake worker commit without trial")
        self.committed_advance_count += 1
        self.pending = False

    def evaluate_position(self, s_ref_m: float):
        return (self.q[0], self.q[1], float(s_ref_m))

    def close(self):
        self.closed = True
        return {"closed": True}


class _FakeFleet:
    instances: list["_FakeFleet"] = []

    def __init__(self, manifest, config_file, vertices_by_slice) -> None:
        self.manifest = manifest
        self.config_file = config_file
        self.vertices_by_slice = vertices_by_slice
        self.advance_calls = 0
        self._checkpoint_needed = True
        self._written: tuple[float, float] | None = None
        self.written_history: list[tuple[float, float]] = []
        self.initial_motion = None
        self.finalized = False
        type(self).instances.append(self)

    def initialize(self, initial_motion_by_slice=None) -> None:
        self.initial_motion = initial_motion_by_slice

    def is_coupling_ongoing(self) -> bool:
        return self.advance_calls < 10

    def requires_writing_checkpoint(self) -> bool:
        return self.advance_calls in (0, 5)

    def write_motion(self, slice_id, values) -> None:
        self._written = (float(values[0][0]), float(values[0][1]))
        self.written_history.append(self._written)

    def advance(self, dt_s: float) -> None:
        if self._written is None or dt_s <= 0.0:
            raise AssertionError("fake fleet advance requires written motion and positive dt")
        self.advance_calls += 1

    def read_force(self, slice_id):
        if self._written is None:
            raise AssertionError("fake force requested before displacement was written")
        # Fluid force is an explicit function of the exact displacement written.
        fy = 1.0 + 10.0 * self._written[1]
        return [(0.0, fy, 0.0)]

    def requires_reading_checkpoint(self) -> bool:
        attempt_in_window = (self.advance_calls - 1) % 5 + 1
        return attempt_in_window < 5

    def finalize(self) -> None:
        self.finalized = True


class ImplicitIterationTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeWorker.instances.clear()
        _FakeFleet.instances.clear()

    def test_trace_distinguishes_stale_motion_from_trial_feedback(self) -> None:
        manifest = _manifest()
        bundle = SimpleNamespace(
            root={"coupling": {"accepted_window_limit": 2}},
            case_id="fake-implicit-case",
            structure={"geometry": {"length_m": 4.0}},
            config_file=Path("fake-precice-config.xml"),
            dt_s=0.1,
            unit_span_m=1.0,
            slice_length_m=1.0,
            slice_center_m=2.0,
        )
        with tempfile.TemporaryDirectory(prefix="implicit-trace-test-") as temp_dir:
            trace_path = Path(temp_dir) / "attempts.jsonl"
            with (
                patch.object(participant, "load_contract_bundle", return_value=bundle),
                patch.object(participant, "audit_contract", return_value={"status": "PASS"}),
                patch.object(participant, "build_manifest", return_value=manifest),
                patch.object(participant, "PersistentHH06KernelBackend", _FakeWorker),
                patch.object(participant, "PreciceStructureFleetBackend", _FakeFleet),
            ):
                result = participant.run("unused-case", "unused-worker", trace_output=trace_path)

            trace = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(result["accepted_windows"], 2)
        self.assertEqual(len(trace), 10)
        self.assertEqual(
            [(row["window_index"], row["iteration_index"]) for row in trace],
            [(1, index) for index in range(1, 6)] + [(2, index) for index in range(1, 6)],
        )
        self.assertEqual([row["sequence"] for row in trace], list(range(1, 11)))
        self.assertEqual([row["request_id"] for row in trace], list(range(501, 511)))
        self.assertEqual([row["transaction_id"] for row in trace], list(range(901, 911)))
        self.assertEqual([row["commit_status"] for row in trace], ["rolled_back"] * 4 + ["committed"] + ["rolled_back"] * 4 + ["committed"])
        self.assertEqual([row["rollback_request"] for row in trace], [True] * 4 + [False] + [True] * 4 + [False])
        self.assertEqual([row["checkpoint_request"] for row in trace], [True] + [False] * 4 + [True] + [False] * 4)

        first, retry, window1_accept, next_window = trace[0], trace[1], trace[4], trace[5]
        self.assertEqual(len({json.dumps(row["physical_identity"], sort_keys=True) for row in trace[:5]}), 1)
        self.assertEqual(len({json.dumps(row["physical_identity"], sort_keys=True) for row in trace[5:]}), 1)
        self.assertEqual(first["physical_identity"]["global_step"], 1)
        self.assertEqual(first["physical_identity"]["bridge_step"], 1)
        self.assertEqual(trace[5]["physical_identity"]["global_step"], 2)
        self.assertEqual(trace[5]["physical_identity"]["bridge_step"], 2)
        self.assertEqual(trace[5]["physical_identity"]["integer_tick"] - first["physical_identity"]["integer_tick"], 100_000)
        self.assertAlmostEqual(first["physical_time_s"], 0.1)
        self.assertAlmostEqual(retry["physical_time_s"], 0.1)
        self.assertAlmostEqual(next_window["physical_time_s"], 0.2)
        self.assertTrue(all(math.isclose(row["dt_s"], 0.1) for row in trace))
        self.assertEqual(first["force_residual_raw_N"], None)
        self.assertAlmostEqual(retry["force_residual_raw_N"], 0.0)
        self.assertAlmostEqual(retry["trial_displacement_residual_m"], 0.0)
        self.assertAlmostEqual(retry["written_motion_delta_m"], 0.0)
        self.assertAlmostEqual(window1_accept["Fy_raw_N"], 1.0)
        self.assertAlmostEqual(next_window["Fy_raw_N"], 2.0)

        committed_xy = tuple(first["D_previous_committed_m"][:2])
        trial_xy = tuple(first["D_trial_from_ancf_m"][:2])
        retry_written_xy = tuple(retry["D_written_to_precice_m"])
        stale_path = all(math.isclose(a, b) for a, b in zip(retry_written_xy, committed_xy))
        trial_feedback_path = all(math.isclose(a, b) for a, b in zip(retry_written_xy, trial_xy))
        self.assertNotEqual(stale_path, trial_feedback_path, "fixture must make stale and feedback paths distinguishable")
        self.assertTrue(
            stale_path,
            "current Structure loop should be explicitly classified as stale committed-motion feedback",
        )

        # F_y = 1 + 10 D_written_y; D_trial_y = D_checkpoint_y + 0.1 F_y.
        self.assertFalse(trial_feedback_path)
        self.assertAlmostEqual(retry["Fy_raw_N"], 1.0)
        self.assertNotAlmostEqual(retry["Fy_raw_N"], 1.0 + 10.0 * trial_xy[1])

        # Rollback restores all physical state vectors, while transport IDs advance.
        worker = _FakeWorker.instances[0]
        self.assertEqual(len(worker.input_states), 10)
        for restored_state in worker.input_states[1:5]:
            self.assertEqual(restored_state, ([0.0, 0.0, 0.0],) * 3)
        expected_window2_checkpoint = (
            [0.0, window1_accept["D_trial_from_ancf_m"][1], 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 2.0, 0.0],
        )
        for restored_state in worker.input_states[5:10]:
            self.assertEqual(restored_state, expected_window2_checkpoint)
        self.assertTrue(all(row["q_state_hash"] == trace[0]["q_state_hash"] for row in trace[:5]))
        self.assertTrue(all(row["qdot_state_hash"] and row["qddot_state_hash"] for row in trace))
        self.assertTrue(_FakeFleet.instances[0].finalized)
        self.assertTrue(worker.closed)


if __name__ == "__main__":
    unittest.main()
