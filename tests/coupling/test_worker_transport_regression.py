"""Current-source C++ worker transport/rollback regression (offline only)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys_path = REPO_ROOT / "src"

import sys
sys.path.insert(0, str(sys_path))

from coupling.arbitrary_n_live_orchestration_v1.coordinator import (  # noqa: E402
    ForceSample,
    GenericStructuralCoordinator,
    WorkerRequest,
)
from coupling.hh06_structure_0000 import structure_0000_participant as participant  # noqa: E402


class CurrentWorkerTransportRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.build_temp = None
        supplied_worker = os.environ.get("CFD_ANCF_TEST_WORKER")
        if supplied_worker:
            cls.worker_path = Path(supplied_worker).expanduser().resolve()
            cls.build_dir = cls.worker_path.parent
            cls.build_mode = "supplied_current_source_cmake_build"
        else:
            cls.build_temp = tempfile.TemporaryDirectory(prefix="phase1d-worker-build-")
            cls.build_dir = Path(cls.build_temp.name) / "build"
            configure = subprocess.run(
                ["cmake", "-S", str(REPO_ROOT / "src" / "ancf"), "-B", str(cls.build_dir), "-DCMAKE_BUILD_TYPE=Release"],
                text=True, capture_output=True, check=False,
            )
            if configure.returncode != 0:
                raise RuntimeError("worker CMake configure failed:\n" + configure.stdout + configure.stderr)
            build = subprocess.run(
                ["cmake", "--build", str(cls.build_dir), "--target", "cfd_ancf_ancf_kernel_worker", "-j2"],
                text=True, capture_output=True, check=False,
            )
            if build.returncode != 0:
                raise RuntimeError("worker build failed:\n" + build.stdout + build.stderr)
            cls.worker_path = cls.build_dir / "cfd_ancf_ancf_kernel_worker"
            cls.build_mode = "built_by_regression_test_from_current_source"
        if not cls.worker_path.is_file():
            raise RuntimeError("CMake completed without producing the authoritative worker target")
        cache_path = cls.build_dir / "CMakeCache.txt"
        cache = cache_path.read_text(encoding="utf-8", errors="replace") if cache_path.is_file() else ""
        cls.cmake_cache = {
            key: next((line.split("=", 1)[1] for line in cache.splitlines() if line.startswith(key + ":")), None)
            for key in ("CMAKE_BUILD_TYPE", "CMAKE_CXX_COMPILER")
        }
        cls.evidence = {
            "test": "phase1d_current_source_worker_transport_regression_v1",
            "git_head_before_phase1d": subprocess.check_output(
                ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True,
            ).strip(),
            "worker_source": str(REPO_ROOT / "src" / "ancf" / "ancf_worker_main.cpp"),
            "worker_source_sha256": hashlib.sha256(
                (REPO_ROOT / "src" / "ancf" / "ancf_worker_main.cpp").read_bytes()
            ).hexdigest(),
            "worker_binary": str(cls.worker_path),
            "worker_binary_sha256": hashlib.sha256(cls.worker_path.read_bytes()).hexdigest(),
            "build_mode": cls.build_mode,
            "cmake_cache": cls.cmake_cache,
            "cmake_version": subprocess.check_output(["cmake", "--version"], text=True).splitlines()[0],
            "compiler_version": subprocess.check_output(["c++", "--version"], text=True).splitlines()[0],
            "two_window_five_attempt_regression": {"status": "NOT_RUN"},
            "duplicate_request_id_guard": {"status": "NOT_RUN"},
            "duplicate_transaction_id_guard": {"status": "NOT_RUN"},
        }

    @classmethod
    def tearDownClass(cls) -> None:
        evidence_root = os.environ.get("PHASE1D_EVIDENCE_DIR")
        if evidence_root:
            path = Path(evidence_root)
            path.mkdir(parents=True, exist_ok=True)
            (path / "worker_transport_qualification.json").write_text(
                json.dumps(cls.evidence, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        if cls.build_temp is not None:
            cls.build_temp.cleanup()

    def setUp(self) -> None:
        self.case_dir = REPO_ROOT / "cases" / "hh06_single_slice"
        self.bundle = participant.load_contract_bundle(self.case_dir)
        self.manifest = participant.build_manifest(self.bundle)
        self.item = self.manifest.slices[0]

    def _request(self, window: int) -> WorkerRequest:
        return WorkerRequest(
            case_id=self.manifest.case_id,
            iteration=window,
            time_s=window * self.bundle.dt_s,
            slice_ids=self.manifest.slice_ids,
            slice_positions_m=tuple(item.s_ref_m for item in self.manifest.slices),
            reconstruction_mode=self.manifest.reconstruction_mode,
            active_start_m=self.manifest.active_start_m,
            active_end_m=self.manifest.active_end_m,
            spanwise_line_force_Npm=(),
            slice_force_N=(0.0, 0.0, 0.0),
            sld1=False,
        )

    @staticmethod
    def _close_worker(backend) -> None:
        backend.close()
        process = backend.process
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()

    def test_two_windows_five_attempts_each_preserve_physical_and_transport_state(self) -> None:
        backend = participant.PersistentHH06KernelBackend(self.bundle, self.manifest, self.worker_path)
        coordinator = GenericStructuralCoordinator(
            self.manifest, backend,
            reference_positions_by_slice={self.item.slice_id: (0.0, 0.0, self.item.s_ref_m)},
        )
        records = []
        try:
            backend.start()
            for window in (1, 2):
                coordinator.checkpoint(f"phase1d-worker-window-{window}")
                physical_checkpoint = backend.snapshot()
                for attempt in range(1, 6):
                    sample = ForceSample.from_openfoam_integrated(
                        self.manifest, self.item.slice_id, iteration=window,
                        time_s=window * self.bundle.dt_s, force_N=(0.0, 0.0, 0.0),
                        unit_span_m=self.bundle.unit_span_m,
                    )
                    coordinator.submit_force(sample)
                    result = coordinator.advance_if_complete()
                    coordinator.scatter_motion()
                    records.append(result)
                    if attempt < 5:
                        coordinator.rollback()
                        restored = backend.snapshot()
                        for key in ("q", "qdot", "qddot", "committed"):
                            self.assertEqual(restored[key], physical_checkpoint[key], f"rollback did not restore {key}")
                        self.assertFalse(restored["pending"])
                    else:
                        coordinator.commit()

            self.assertEqual([row["sequence"] for row in records], list(range(1, 11)))
            self.assertEqual([row["request_id"] for row in records], sorted({row["request_id"] for row in records}))
            self.assertEqual([row["transaction_id"] for row in records], sorted({row["transaction_id"] for row in records}))
            self.assertEqual(len({row["request_id"] for row in records}), 10)
            self.assertEqual(len({row["transaction_id"] for row in records}), 10)
            self.assertEqual(len({row["sequence"] for row in records}), 10)

            first_window = records[:5]
            second_window = records[5:]
            for group in (first_window, second_window):
                physical_ids = {tuple(sorted(row["physical_identity"].items())) for row in group}
                self.assertEqual(len(physical_ids), 1)
            self.assertEqual(first_window[-1]["sequence"], 5)
            self.assertEqual(second_window[0]["sequence"], 6)
            self.assertEqual(second_window[0]["physical_identity"]["global_step"], 2)
            self.assertEqual(second_window[0]["physical_identity"]["bridge_step"], 2)
            self.assertEqual(
                second_window[0]["physical_identity"]["integer_tick"] - first_window[0]["physical_identity"]["integer_tick"],
                int(round(self.bundle.dt_s * 1.0e9)),
            )
            self.assertAlmostEqual(
                second_window[0]["physical_identity"]["time_s"] - first_window[0]["physical_identity"]["time_s"],
                self.bundle.dt_s,
                places=15,
            )
            self.assertTrue(all(row["physical_identity"]["dt_s"] == self.bundle.dt_s for row in records))
            self.__class__.evidence["two_window_five_attempt_regression"] = {
                "status": "PASS",
                "sequences": [row["sequence"] for row in records],
                "request_ids": [row["request_id"] for row in records],
                "transaction_ids": [row["transaction_id"] for row in records],
                "physical_identity_by_window": [
                    first_window[0]["physical_identity"], second_window[0]["physical_identity"],
                ],
                "q_qdot_qddot_restored_exactly_on_each_rollback": True,
                "transport_ids_excluded_from_physical_restore": True,
            }
        finally:
            self._close_worker(backend)

    def _assert_worker_rejects_duplicate(self, duplicate_kind: str) -> None:
        backend = participant.PersistentHH06KernelBackend(self.bundle, self.manifest, self.worker_path)
        try:
            backend.start()
            initial = backend.snapshot()
            first = backend.advance(self._request(1))
            backend.restore(initial)
            if duplicate_kind == "request_id":
                backend._transport_request_id_counter = first["request_id"] - 1
            elif duplicate_kind == "transaction_id":
                backend._transport_transaction_id_counter = first["transaction_id"] - 1
            else:
                raise AssertionError(duplicate_kind)
            with self.assertRaisesRegex(participant.HH06ContractError, "response header missing at sequence 2"):
                backend.advance(self._request(1))
            self.assertEqual(backend.process.wait(timeout=5), 18)
            self.__class__.evidence[f"duplicate_{duplicate_kind}_guard"] = {
                "status": "PASS",
                "worker_exit_code": 18,
                "duplicate_identity": duplicate_kind,
                "next_sequence": 2,
            }
        finally:
            self._close_worker(backend)

    def test_worker_rejects_duplicate_request_id(self) -> None:
        self._assert_worker_rejects_duplicate("request_id")

    def test_worker_rejects_duplicate_transaction_id(self) -> None:
        self._assert_worker_rejects_duplicate("transaction_id")


if __name__ == "__main__":
    unittest.main()
