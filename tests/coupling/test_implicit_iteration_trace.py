"""Offline fixed-point and rollback qualification for the HH06 participant."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from coupling.arbitrary_n_live_orchestration_v1.coordinator import ForceSample  # noqa: E402
from coupling.arbitrary_n_live_orchestration_v1.manifest import (  # noqa: E402
    OrchestrationSlice,
    SliceManifest,
)
from coupling.arbitrary_n_live_orchestration_v1.precice_backend import (  # noqa: E402
    PreciceStructureFleetBackend,
)
from coupling.hh06_structure_0000 import structure_0000_participant as participant  # noqa: E402

_EVENT_ORDER: list[tuple] = []


def _sha(values: list[float]) -> str:
    return hashlib.sha256(struct.pack("<" + "d" * len(values), *values)).hexdigest()


def _manifest(*, unit_span_m=1.0, slice_length_m=1.0) -> SliceManifest:
    item = OrchestrationSlice(
        slice_id="slice_0000", ordinal=0, s_ref_m=2.0, slice_length_m=slice_length_m,
        unit_span_m=unit_span_m, fluid_participant="Fluid_0000",
        structure_participant="Structure_0000", structure_mesh="Structure-Mesh",
        fluid_mesh="Fluid-Mesh", force_data="Force", motion_data="Displacement",
        openfoam_case_id="fake-implicit-case", force_slot=0, motion_slot=0,
    )
    return SliceManifest(
        schema_version="arbitrary-n-live-coupling-v1", case_id="fake-implicit-case",
        reference_length_m=4.0, active_start_m=1.5, active_end_m=2.5,
        reconstruction_mode="LegacyPointLumped", endpoint_policy="NearestConstant",
        structure_participant="Structure_0000", slices=(item,),
    )


class _FakeWorker:
    instances: list["_FakeWorker"] = []
    events: list[tuple] = []

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
        self.request_id = 910000
        self.transaction_id = 1910000
        self.input_states: list[dict] = []
        self.force_input_history: list[tuple[float, ...]] = []
        self.started = False
        self.closed = False
        type(self).instances.append(self)

    def start(self) -> None:
        self.started = True

    def snapshot(self):
        return {
            "q": list(self.q), "qdot": list(self.qdot), "qddot": list(self.qddot),
            "committed": self.committed_advance_count, "pending": self.pending,
        }

    def restore(self, snapshot) -> None:
        self.q = list(snapshot["q"])
        self.qdot = list(snapshot["qdot"])
        self.qddot = list(snapshot["qddot"])
        self.committed_advance_count = int(snapshot["committed"])
        self.pending = bool(snapshot["pending"])

    def advance(self, request):
        if self.pending:
            raise AssertionError("fake backend received a second pending physical trial")
        self.sequence += 1
        self.request_id += 1
        self.transaction_id += 1
        state_before = (list(self.q), list(self.qdot), list(self.qddot))
        fy = float(request.slice_force_N[1])
        self.force_input_history.append(tuple(float(value) for value in request.slice_force_N))
        # D_trial = g(F) = 0.1 + 0.2 F, relative to this window's committed q.
        self.q[1] += 0.1 + 0.2 * fy
        self.qdot[1] = fy
        self.qddot[1] = 2.0 * fy
        self.pending = True
        type(self).events.append(("solve", self.sequence))
        _EVENT_ORDER.append(("solve", self.sequence))
        step = self.committed_advance_count + 1
        tick = int(round(request.time_s * 1_000_000_000))
        self.input_states.append({
            "before": state_before,
            "sequence": self.sequence,
            "request_id": self.request_id,
            "transaction_id": self.transaction_id,
            "physical_step": step,
            "time_s": request.time_s,
        })
        return {
            "iterations": 3, "residual": 1.0e-12,
            "q_sha256": _sha(self.q), "qdot_sha256": _sha(self.qdot),
            "qddot_sha256": _sha(self.qddot),
            "sequence": self.sequence, "request_id": self.request_id,
            "transaction_id": self.transaction_id,
            "physical_identity": {
                "global_step": step, "bridge_step": step,
                "integer_tick": tick, "time_s": request.time_s,
                "dt_s": self.bundle.dt_s,
            },
        }

    def commit(self) -> None:
        if not self.pending:
            raise AssertionError("fake worker commit without a physical trial")
        self.committed_advance_count += 1
        self.pending = False

    def evaluate_position(self, s_ref_m: float):
        return (self.q[0], self.q[1], float(s_ref_m))

    def close(self):
        self.closed = True
        return {"closed": True}


class _FakeFleet:
    instances: list["_FakeFleet"] = []
    events: list[tuple] = []

    def __init__(self, manifest, config_file, vertices_by_slice, *, windows, max_iterations,
                 force_seed=(0.0, 1.0, 0.0), mode="fixed_point",
                 displacement_tolerance=1.0e-8, force_tolerance=1.0e-7,
                 dt_s=0.0002) -> None:
        self.manifest = manifest
        self.config_file = config_file
        self.vertices_by_slice = vertices_by_slice
        self.windows = windows
        self.max_iterations = max_iterations
        self.force_seed = tuple(force_seed)
        self.mode = mode
        self.displacement_tolerance = displacement_tolerance
        self.force_tolerance = force_tolerance
        self.dt_s = float(dt_s)
        self.completed_windows = 0
        self.iteration_in_window = 0
        self.advance_calls = 0
        self.checkpoint_queries = 0
        self.written: tuple[float, float] | None = None
        self.previous_written = (0.0, 0.0)
        self.previous_force = tuple(force_seed)
        self.current_force = tuple(force_seed)
        self.window_start_force = tuple(force_seed)
        self.last_rollback_request: bool | None = None
        self.last_advance_window_index: int | None = None
        self.last_advance_iteration_index: int | None = None
        self.initialized = False
        self.initial_motion = None
        self.finalized = False
        self.write_history: list[tuple[float, float]] = []
        self.read_history: list[dict] = []
        type(self).instances.append(self)

    def initialize(self, initial_motion_by_slice=None) -> None:
        self.initial_motion = initial_motion_by_slice
        self.initialized = True
        type(self).events.append(("initialize",))
        _EVENT_ORDER.append(("initialize",))

    def is_coupling_ongoing(self) -> bool:
        return self.completed_windows < self.windows

    def requires_writing_checkpoint(self) -> bool:
        # Some API paths can request the already-active window checkpoint
        # again on retries. The Structure participant must keep one snapshot.
        self.checkpoint_queries += 1
        return True

    def write_motion(self, slice_id, values) -> None:
        self.written = (float(values[0][0]), float(values[0][1]))
        self.write_history.append(self.written)
        type(self).events.append(("write", self.advance_calls + 1, self.written))
        _EVENT_ORDER.append(("write", self.advance_calls + 1, self.written))

    def advance(self, dt_s: float) -> None:
        if self.written is None or dt_s <= 0.0:
            raise AssertionError("fake preCICE advance requires the current trial displacement")
        self.advance_calls += 1
        self.last_advance_window_index = self.completed_windows + 1
        self.iteration_in_window += 1
        self.last_advance_iteration_index = self.iteration_in_window
        self.last_rollback_request = None
        type(self).events.append(("precice_advance", self.advance_calls, self.written))
        _EVENT_ORDER.append(("precice_advance", self.advance_calls, self.written))
        if self.mode == "fixed_point":
            # F = f(D_written) = 1 + 2 D_y.
            self.current_force = (0.0, 1.0 + 2.0 * self.written[1], 0.0)
        elif self.mode == "non_convergent":
            # Deliberately moving force iterate: only the configured cap ends it.
            self.current_force = (0.0, self.current_force[1] + 1.0, 0.0)
        elif self.mode == "two_window_transition":
            # Window 1 accepts F1=(0,2,0); window 2 must start from that value,
            # not the original release seed F0=(0,1,0).
            self.current_force = (0.0, 2.0 if self.completed_windows == 0 else 3.0, 0.0)
        else:
            raise AssertionError(f"unknown fake flow mode {self.mode}")

    def read_force(self, slice_id, *, relative_read_time_s):
        kind = "initial" if self.advance_calls == 0 else "post_advance"
        offset = float(relative_read_time_s)
        if self.advance_calls == 0:
            if offset != 0.0:
                raise AssertionError("initialized release Force must be read at relative time zero")
            values = self.current_force
            source_kind = "initial_force"
        elif self.last_rollback_request is True:
            if offset == 0.0:
                # preCICE start-of-window sample: reproduce the stale retry path.
                values = self.window_start_force
                source_kind = "window_start_force"
            elif math.isclose(offset, self.dt_s, rel_tol=0.0, abs_tol=1.0e-15):
                values = self.current_force
                source_kind = "retry_endpoint_force"
            else:
                raise AssertionError(f"unexpected retry read offset {offset}")
        elif self.last_rollback_request is False:
            if offset != 0.0:
                raise AssertionError("accepted window must not read the ended endpoint at dt")
            values = self.current_force
            source_kind = "accepted_window_boundary_force"
        else:
            raise AssertionError("post-advance Force read preceded checkpoint decision")
        record = {
            "kind": kind, "source_kind": source_kind,
            "relative_read_time_s": offset, "force_raw_N": list(values),
            "window_index": self.last_advance_window_index or 1,
            "iteration_index": self.last_advance_iteration_index or 0,
            "source_global_time_s": 30.0 + (self.last_advance_window_index or 0) * self.dt_s,
        }
        self.read_history.append(record)
        type(self).events.append(("read_force", kind, tuple(values)))
        _EVENT_ORDER.append(("read_force", kind, tuple(values)))
        _EVENT_ORDER.append(("force_read_offset", kind, offset))
        return [values]

    def requires_reading_checkpoint(self) -> bool:
        d_residual = abs(self.written[1] - self.previous_written[1])
        f_residual = abs(self.current_force[1] - self.previous_force[1])
        retry = self.iteration_in_window < 2 or (
            d_residual > self.displacement_tolerance or f_residual > self.force_tolerance
        )
        if self.mode == "non_convergent" or self.iteration_in_window >= self.max_iterations:
            retry = self.iteration_in_window < self.max_iterations

        self.previous_written = self.written
        self.previous_force = self.current_force
        type(self).events.append(("checkpoint_decision", self.iteration_in_window, retry))
        if not retry:
            self.completed_windows += 1
            self.iteration_in_window = 0
            self.window_start_force = self.current_force
        self.last_rollback_request = retry
        return retry

    def finalize(self) -> None:
        self.finalized = True


def _fake_bundle(config_file: Path, *, windows: int, max_iterations: int,
                 force_seed: tuple[float, float, float], source_kind: str,
                 unit_span_m: float, slice_length_m: float) -> SimpleNamespace:
    manifest = _manifest()
    root = {
        "case_id": "fake-implicit-case",
        "initial_state": {
            "openfoam_global_time_s": 30.0,
            "Fx0_total_N": force_seed[0],
            "Fy0_total_N": force_seed[1],
            "release_force_provenance": {
                "source_kind": source_kind,
                "initial_data_comparison_tolerance_N": 1.0e-13,
            },
        },
        "coupling": {"accepted_window_limit": windows, "max_iterations": max_iterations},
    }
    return SimpleNamespace(
        root=root, case_id="fake-implicit-case",
        structure={"geometry": {"length_m": 4.0}},
        config_file=config_file, dt_s=0.0002, unit_span_m=unit_span_m,
        slice_length_m=slice_length_m, slice_center_m=2.0,
    )


def _write_fake_precice_xml(path: Path, max_iterations: int) -> None:
    path.write_text(
        "<precice-configuration><max-iterations value=\"%d\"/></precice-configuration>\n" % max_iterations,
        encoding="utf-8",
    )


def _save_machine_trace(filename: str, trace: list[dict]) -> None:
    evidence_root = os.environ.get("PHASE1D_EVIDENCE_DIR")
    if not evidence_root:
        return
    path = Path(evidence_root)
    path.mkdir(parents=True, exist_ok=True)
    with (path / filename).open("w", encoding="utf-8") as stream:
        for row in trace:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def _run_fake(*, windows: int, max_iterations: int, mode="fixed_point",
              force_seed=(0.0, 1.0, 0.0), source_kind="SYNTHETIC_OFFLINE_TEST_SEED",
              unit_span_m=1.0, slice_length_m=1.0):
    _FakeWorker.instances.clear()
    _FakeFleet.instances.clear()
    _FakeWorker.events.clear()
    _FakeFleet.events.clear()
    _EVENT_ORDER.clear()
    with tempfile.TemporaryDirectory(prefix="strategy-c-offline-") as temp_dir:
        config_path = Path(temp_dir) / "precice-config.xml"
        trace_path = Path(temp_dir) / "attempts.jsonl"
        _write_fake_precice_xml(config_path, max_iterations)
        bundle = _fake_bundle(
            config_path, windows=windows, max_iterations=max_iterations,
            force_seed=tuple(force_seed), source_kind=source_kind,
            unit_span_m=unit_span_m, slice_length_m=slice_length_m,
        )
        manifest = _manifest(unit_span_m=unit_span_m, slice_length_m=slice_length_m)
        fake_fleet_factory = lambda m, c, v: _FakeFleet(
            m, c, v, windows=windows, max_iterations=max_iterations, mode=mode,
            force_seed=tuple(force_seed), dt_s=bundle.dt_s,
        )
        with (
            patch.object(participant, "load_contract_bundle", return_value=bundle),
            patch.object(participant, "audit_contract", return_value={"status": "PASS"}),
            patch.object(participant, "build_manifest", return_value=manifest),
            patch.object(participant, "PersistentHH06KernelBackend", _FakeWorker),
            patch.object(participant, "PreciceStructureFleetBackend", side_effect=fake_fleet_factory),
        ):
            result = participant.run("unused-case", "unused-worker", trace_output=trace_path)
        trace = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    return result, trace, _FakeWorker.instances[0], _FakeFleet.instances[0]


class ImplicitIterationTraceTests(unittest.TestCase):
    def test_backend_requires_and_forwards_explicit_force_read_offset(self) -> None:
        class ParticipantSpy:
            def __init__(self) -> None:
                self.read_data_arguments = None

            def set_mesh_vertices(self, mesh_name, vertices):
                return [17]

            def initialize(self):
                return None

            def read_data(self, mesh_name, data_name, vertex_ids, relative_read_time_s):
                self.read_data_arguments = (mesh_name, data_name, vertex_ids, relative_read_time_s)
                return [[1.25, -0.5]]

            def finalize(self):
                return None

        with tempfile.TemporaryDirectory(prefix="precice-read-offset-api-") as temp_dir:
            config_path = Path(temp_dir) / "precice-config.xml"
            _write_fake_precice_xml(config_path, 4)
            spy = ParticipantSpy()
            backend = PreciceStructureFleetBackend(
                _manifest(), config_path, {"slice_0000": [[0.0, 0.0]]},
                participant_factory=lambda *_args: spy,
            )
            backend.initialize()
            values = backend.read_force("slice_0000", relative_read_time_s=0.0002)
            self.assertEqual(values, [[1.25, -0.5]])
            self.assertEqual(spy.read_data_arguments, ("Structure-Mesh", "Force", [17], 0.0002))
            with self.assertRaises(TypeError):
                backend.read_force("slice_0000")
            backend.finalize()

    def test_fixed_point_feedback_converges_with_trial_written_before_advance(self) -> None:
        result, trace, worker, fleet = _run_fake(windows=2, max_iterations=25)
        _save_machine_trace("implicit_fixed_point_trace.jsonl", trace)
        self.assertEqual(result["accepted_windows"], 2)
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(trace[0]["force_source_kind"], "SYNTHETIC_OFFLINE_TEST_SEED")

        first_window = [row for row in trace if row["window_index"] == 1]
        self.assertGreaterEqual(len(first_window), 3)
        for row, expected in zip(first_window[:3], (0.3, 0.42, 0.468)):
            self.assertAlmostEqual(row["D_trial_from_ancf_m"][1], expected, places=14)
            self.assertAlmostEqual(row["D_written_to_precice_m"][1], expected, places=14)
            self.assertEqual(row["D_trial_interface_m"], row["D_written_to_precice_m"])
        self.assertAlmostEqual(first_window[0]["Fy_raw_N"], 1.0)
        self.assertAlmostEqual(first_window[0]["Fy_returned_raw_N"], 1.6)
        self.assertAlmostEqual(first_window[1]["Fy_raw_N"], 1.6)
        self.assertAlmostEqual(first_window[1]["Fy_returned_raw_N"], 1.84)
        self.assertAlmostEqual(first_window[2]["Fy_raw_N"], 1.84)
        self.assertAlmostEqual(first_window[2]["Fy_returned_raw_N"], 1.936)

        d_residuals = [row["trial_displacement_residual_m"] for row in first_window[:5]]
        f_residuals = [row["force_residual_raw_N"] for row in first_window[:5]]
        for previous, current in zip(d_residuals, d_residuals[1:]):
            self.assertAlmostEqual(current / previous, 0.4, places=10)
        for previous, current in zip(f_residuals, f_residuals[1:]):
            self.assertAlmostEqual(current / previous, 0.4, places=10)
        self.assertEqual(first_window[-1]["convergence_status"], "accepted_by_precice_before_iteration_limit")
        self.assertLess(first_window[-1]["iteration_index"], 25)

        # Every trial is sent as-is before its associated fluid advance.
        self.assertEqual(_EVENT_ORDER[0], ("initialize",))
        self.assertEqual(_EVENT_ORDER[1][0:2], ("read_force", "initial"))
        self.assertEqual(len(fleet.write_history), len(trace))
        for attempt_index, row in enumerate(trace, start=1):
            write_event = next(event for event in _FakeFleet.events if event[0] == "write" and event[1] == attempt_index)
            advance_event = next(event for event in _FakeFleet.events if event[0] == "precice_advance" and event[1] == attempt_index)
            self.assertEqual(write_event[2], tuple(row["D_trial_interface_m"]))
            self.assertLess(_EVENT_ORDER.index(write_event), _EVENT_ORDER.index(advance_event))
        for solve_index in range(1, len(trace) + 1):
            solve_event = next(event for event in _FakeWorker.events if event == ("solve", solve_index))
            write_event = next(event for event in _FakeFleet.events if event[0] == "write" and event[1] == solve_index)
            self.assertLess(_EVENT_ORDER.index(solve_event), _EVENT_ORDER.index(write_event))

        # The accepted structural state, trial, and written coupling value agree.
        last = first_window[-1]
        accepted = result["records"][0]
        self.assertEqual(accepted["motion_m"][:2], last["D_trial_interface_m"])
        self.assertEqual(accepted["written_motion_m"], last["D_written_to_precice_m"])
        self.assertEqual(accepted["motion_m"][:2], accepted["written_motion_m"])

        # Retry restores q/qdot/qddot exactly; transport identity never rolls back.
        self.assertEqual([row["sequence"] for row in trace], list(range(1, len(trace) + 1)))
        self.assertEqual(len({row["request_id"] for row in trace}), len(trace))
        self.assertEqual(len({row["transaction_id"] for row in trace}), len(trace))
        for window_index in (1, 2):
            rows = [row for row in trace if row["window_index"] == window_index]
            identity_tuples = {json.dumps(row["physical_identity"], sort_keys=True) for row in rows}
            self.assertEqual(len(identity_tuples), 1)
            attempts = [state for state in worker.input_states if state["physical_step"] == window_index]
            self.assertGreater(len(attempts), 1)
            checkpoint_state = attempts[0]["before"]
            self.assertTrue(all(state["before"] == checkpoint_state for state in attempts))
        win1_last = first_window[-1]
        win2_first = next(row for row in trace if row["window_index"] == 2)
        self.assertEqual(win2_first["force_input_raw_N"], win1_last["returned_force_raw_N"])
        self.assertEqual(win1_last["force_read_time_s"], 0.0)
        self.assertEqual(win2_first["force_input_read_offset_s"], 0.0)
        self.assertAlmostEqual(win2_first["force_source_global_time_s"], 30.0002)
        self.assertAlmostEqual(win2_first["window_target_global_time_s"], 30.0004)
        self.assertEqual(win2_first["force_source_kind"], "PRECEDING_ACCEPTED_PRECICE_EXCHANGE")
        self.assertEqual(fleet.completed_windows, 2)
        self.assertTrue(fleet.finalized)
        self.assertTrue(worker.closed)

    def test_retry_uses_endpoint_force_and_acceptance_uses_zero_offset(self) -> None:
        result, trace, _worker, fleet = _run_fake(windows=2, max_iterations=25)
        self.assertEqual(result["accepted_windows"], 2)
        self.assertEqual(len(trace), len(fleet.read_history) - 1)
        self.assertEqual(fleet.read_history[0]["kind"], "initial")
        self.assertEqual(fleet.read_history[0]["relative_read_time_s"], 0.0)

        for row, read in zip(trace, fleet.read_history[1:]):
            expected_read_offset = 0.0002 if row["rollback_request"] else 0.0
            self.assertEqual(row["force_read_time_s"], expected_read_offset)
            self.assertEqual(read["relative_read_time_s"], expected_read_offset)
            self.assertEqual(read["force_raw_N"], row["returned_force_raw_N"])
            self.assertEqual(read["window_index"], row["force_read_window_index"])
            self.assertEqual(read["iteration_index"], row["force_read_iteration_index"])
            self.assertEqual(row["force_source_vector_raw_N"], row["returned_force_raw_N"])
            expected_source_kind = (
                "CURRENT_WINDOW_ENDPOINT_RETRY_ITERATE"
                if row["rollback_request"] else "ACCEPTED_WINDOW_BOUNDARY_FORCE"
            )
            self.assertEqual(row["force_read_source_kind"], expected_source_kind)
            self.assertEqual(row["force_read_source_global_time_s"], row["returned_force_source_global_time_s"])
            self.assertEqual(row["force_read_vector_raw_N"], row["returned_force_raw_N"])
            self.assertEqual(row["force_input_vector_raw_N"], row["force_input_raw_N"])

        for window_index in (1, 2):
            rows = [row for row in trace if row["window_index"] == window_index]
            self.assertTrue(rows)
            self.assertEqual(rows[0]["force_input_read_offset_s"], 0.0)
            for retry_row, next_row in zip(rows, rows[1:]):
                self.assertTrue(retry_row["rollback_request"])
                self.assertEqual(retry_row["force_read_time_s"], 0.0002)
                self.assertEqual(next_row["force_input_raw_N"], retry_row["returned_force_raw_N"])
                self.assertEqual(next_row["force_input_read_offset_s"], 0.0002)
            self.assertFalse(rows[-1]["rollback_request"])
            self.assertEqual(rows[-1]["force_read_time_s"], 0.0)

        win1_accepted = next(row for row in trace if row["window_index"] == 1 and not row["rollback_request"])
        win2_first = next(row for row in trace if row["window_index"] == 2)
        self.assertEqual(win2_first["force_input_raw_N"], win1_accepted["returned_force_raw_N"])
        self.assertNotEqual(win2_first["force_input_raw_N"], [0.0, 1.0, 0.0])

    def test_two_window_transition_uses_accepted_f1_not_original_f0(self) -> None:
        result, trace, _worker, _fleet = _run_fake(
            windows=2, max_iterations=2, mode="two_window_transition",
        )
        _save_machine_trace("force_window_transition_trace.jsonl", trace)
        self.assertEqual(result["accepted_windows"], 2)
        window1 = [row for row in trace if row["window_index"] == 1]
        window2 = [row for row in trace if row["window_index"] == 2]
        self.assertEqual(len(window1), 2)
        self.assertEqual(len(window2), 2)
        self.assertEqual(window1[0]["force_input_raw_N"], [0.0, 1.0, 0.0])
        self.assertEqual(window1[0]["returned_force_raw_N"], [0.0, 2.0, 0.0])
        self.assertTrue(window1[0]["rollback_request"])
        self.assertEqual(window1[1]["force_input_raw_N"], [0.0, 2.0, 0.0])
        self.assertFalse(window1[1]["rollback_request"])
        self.assertEqual(window2[0]["force_input_raw_N"], [0.0, 2.0, 0.0])
        self.assertNotEqual(window2[0]["force_input_raw_N"], [0.0, 1.0, 0.0])
        self.assertEqual(window2[0]["force_input_read_offset_s"], 0.0)

    def test_iteration_cap_is_reported_honestly(self) -> None:
        result, trace, _worker, _fleet = _run_fake(
            windows=1, max_iterations=3, mode="non_convergent",
        )
        _save_machine_trace("iteration_cap_trace.jsonl", trace)
        self.assertEqual(result["accepted_windows"], 1)
        self.assertEqual(len(trace), 3)
        self.assertEqual(trace[-1]["convergence_status"], "ACCEPTED_AT_ITERATION_LIMIT")
        self.assertTrue(all(row["rollback_request"] for row in trace[:-1]))
        self.assertFalse(trace[-1]["rollback_request"])

    def test_physical_f0_is_read_before_first_solve_and_scaled_once(self) -> None:
        raw_f0 = (0.0655270406544, 0.05872987413554, 0.0)
        result, trace, worker, _fleet = _run_fake(
            windows=1, max_iterations=1, mode="non_convergent",
            force_seed=raw_f0, source_kind="HH06_PHYSICAL_RELEASE_FORCE",
            unit_span_m=0.028, slice_length_m=1.98,
        )
        _save_machine_trace("physical_f0_seed_trace.jsonl", trace)
        self.assertEqual(result["accepted_windows"], 1)
        self.assertEqual(trace[0]["force_source_kind"], "HH06_PHYSICAL_RELEASE_FORCE")
        self.assertEqual(trace[0]["force_input_raw_N"], list(raw_f0))
        self.assertEqual(trace[0]["force_input_read_offset_s"], 0.0)
        self.assertEqual(_FakeFleet.instances[0].read_history[0]["force_raw_N"], list(raw_f0))
        self.assertAlmostEqual(trace[0]["force_source_global_time_s"], 30.0)
        self.assertAlmostEqual(trace[0]["window_target_global_time_s"], 30.0002)
        expected_strip = (
            raw_f0[0] / 0.028 * 1.98,
            raw_f0[1] / 0.028 * 1.98,
            0.0,
        )
        for actual, expected in zip(worker.force_input_history[0], expected_strip):
            self.assertAlmostEqual(actual, expected, places=14)
        self.assertLess(_EVENT_ORDER.index(("read_force", "initial", raw_f0)), _EVENT_ORDER.index(("solve", 1)))
        self.assertEqual(trace[0]["convergence_status"], "ACCEPTED_AT_ITERATION_LIMIT")

    def test_frozen_physical_f0_provenance_and_single_force_conversion(self) -> None:
        case = REPO_ROOT / "cases" / "hh06_single_slice"
        bundle = participant.load_contract_bundle(case)
        frozen = participant._load_release_force_contract(bundle)
        self.assertEqual(
            frozen["force_raw_N"],
            (0.0655270406544, 0.05872987413554, -2.44420351566e-21),
        )
        self.assertEqual(frozen["source_global_time_s"], 30.0)
        self.assertEqual(
            frozen["result_json_sha256"],
            "6b272f695ebefe28daa176723483f611c42f8d25dbae8d83de928f3790811b8a",
        )
        sample = ForceSample.from_openfoam_integrated(
            participant.build_manifest(bundle), "slice_0000", iteration=1,
            time_s=bundle.dt_s, force_N=frozen["force_raw_N"],
            unit_span_m=bundle.unit_span_m,
        )
        self.assertAlmostEqual(sample.values[0], 4.633697874846857, places=14)
        self.assertAlmostEqual(sample.values[1], 4.153041099584614, places=14)
        self.assertEqual(sample.openfoam_force_N, frozen["force_raw_N"])
        audit = participant.audit_contract(bundle)
        self.assertTrue(audit["checks"]["physical_release_force_provenance"])
        self.assertTrue(audit["checks"]["force_initial_data_exchange"])


if __name__ == "__main__":
    unittest.main()
