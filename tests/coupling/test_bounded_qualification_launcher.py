from __future__ import annotations

from pathlib import Path
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
CASE_DIR = REPO_ROOT / "cases" / "hh06_single_slice"
WORKER = REPO_ROOT / "build" / "phase1d6_worker" / "cfd_ancf_ancf_kernel_worker"
ADAPTER = Path(
    "/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/"
    "libpreciceAdapterFunctionObject.so"
)
sys.path.insert(0, str(CASE_DIR))
sys.path.insert(0, str(REPO_ROOT / "src"))
import bounded_qualification as launcher  # noqa: E402
from coupling.hh06_structure_0000 import structure_0000_participant as participant  # noqa: E402


class BoundedQualificationLauncherTests(unittest.TestCase):
    def test_command_construction_matches_current_cli_and_paths_without_execution(self) -> None:
        fluid_exe = shutil.which("pimpleFoam") or "/opt/openfoam10/platforms/linux64GccDPInt32Opt/bin/pimpleFoam"
        run_dir = REPO_ROOT / "evidence" / "phase1i_25window_iqn" / "<UNIQUE_RUN_ID>"
        plan = launcher.construct_commands(CASE_DIR, WORKER, 25, fluid_exe, run_dir)

        self.assertEqual(
            list(plan.fluid_command),
            [fluid_exe, "-case", str(CASE_DIR.resolve())],
        )
        structure = list(plan.structure_command)
        self.assertEqual(structure[:2], [str(Path(sys.executable).resolve()), str(launcher.PARTICIPANT.resolve())])
        self.assertEqual(structure[2:8], ["--case", str(CASE_DIR.resolve()), "--run", "--worker", str(WORKER.resolve()), "--max-windows"])
        self.assertEqual(structure[8], "25")
        self.assertIn("--trace-output", structure)
        self.assertNotIn("--contract", structure)
        self.assertEqual(plan.socket_directory, Path(
            "/home/machao/OpenFOAM/coupling/singal_slice/slice0000/precice-sockets"
        ).resolve())
        self.assertTrue(all(str(run_dir) in log for log in plan.log_paths.values()))

    def test_full_preflight_passes_without_starting_runtime(self) -> None:
        env = {
            "ANCF_ADAPTER_RUNTIME_PATH": str(ADAPTER),
            "ANCF_ADAPTER_RUNTIME_SHA256": launcher.EXPECTED_ADAPTER_SHA256,
            "PATH": "/opt/openfoam10/platforms/linux64GccDPInt32Opt/bin:" + os.environ.get("PATH", ""),
            "WM_PROJECT_VERSION": "10",
            "WM_PROJECT": "OpenFOAM",
            "WM_PROJECT_DIR": "/opt/openfoam10",
            "FOAM_APPBIN": "/opt/openfoam10/platforms/linux64GccDPInt32Opt/bin",
        }
        git_identity = {"branch": "repair/worker-lineage-implicit-contract-v1",
                        "head": "test-head", "worktree_clean": True, "status_porcelain": ""}
        with patch.dict(os.environ, env, clear=False), patch.object(launcher, "_git_identity", return_value=git_identity):
            plan, report = launcher.preflight(CASE_DIR, str(WORKER), 25)
        self.assertEqual(report["status"], "PASS_PREFLIGHT_ONLY")
        self.assertFalse(report["runtime_started"])
        self.assertTrue(report["checks"]["F0_provenance_and_restart_hashes"])
        self.assertTrue(report["checks"]["python_precice_binding_runtime_qualified"])
        self.assertEqual(report["max_windows"], 25)
        self.assertEqual(report["precice"]["max_time_windows"], 25)
        self.assertEqual(report["precice"]["acceleration"]["type"], "IQN-ILS")
        self.assertEqual(report["precice"]["acceleration"]["max_used_iterations"], 1)
        self.assertTrue(report["checks"]["frozen_iqn_ils_profile"])
        self.assertEqual(report["max_iterations"], 20)
        self.assertEqual(plan.socket_directory, Path(report["precice"]["socket_directory"]["path"]))
        self.assertEqual(report["openfoam"]["version"], "OpenFOAM-10")
        self.assertTrue(report["checks"]["OpenFOAM_10_environment_and_solver_path"])

    def test_openfoam_identity_uses_sourced_environment_not_shell_function_path(self) -> None:
        executable = "/opt/openfoam10/platforms/linux64GccDPInt32Opt/bin/pimpleFoam"
        env = {
            "WM_PROJECT_VERSION": "10",
            "WM_PROJECT": "OpenFOAM",
            "WM_PROJECT_DIR": "/opt/openfoam10",
            "FOAM_APPBIN": "/opt/openfoam10/platforms/linux64GccDPInt32Opt/bin",
        }
        with patch.dict(os.environ, env, clear=False):
            identity = launcher._verify_openfoam_identity(executable)
        self.assertEqual(identity["version"], "OpenFOAM-10")
        with patch.dict(os.environ, {**env, "WM_PROJECT_VERSION": "11"}, clear=False):
            with self.assertRaisesRegex(launcher.LaunchContractError, "WM_PROJECT_VERSION=10"):
                launcher._verify_openfoam_identity(executable)

    def test_wrong_cap_is_rejected(self) -> None:
        git_identity = {"branch": "repair/worker-lineage-implicit-contract-v1",
                        "head": "test-head", "worktree_clean": True, "status_porcelain": ""}
        for wrong_cap in (2, 5, 26):
            with self.subTest(wrong_cap=wrong_cap):
                with self.assertRaisesRegex(launcher.LaunchContractError, "exactly --max-windows 25"):
                    launcher.construct_commands(CASE_DIR, WORKER, wrong_cap, "/usr/bin/pimpleFoam", Path("/tmp/unused"))
                with patch.object(launcher, "_git_identity", return_value=git_identity):
                    with self.assertRaisesRegex(launcher.LaunchContractError, "explicit --max-windows"):
                        launcher.preflight(CASE_DIR, str(WORKER), wrong_cap)

    def test_wrong_worker_binary_is_rejected(self) -> None:
        with self.assertRaisesRegex(launcher.LaunchContractError, "worker binary SHA mismatch"):
            launcher._verify_worker("/bin/true", launcher.load_json_strict(CASE_DIR / "contract.json")["execution_authorization"])

    def test_adapter_guard_result_must_match_pinned_identity(self) -> None:
        contract_auth = launcher.load_json_strict(CASE_DIR / "contract.json")["execution_authorization"]
        env = {
            "ANCF_ADAPTER_RUNTIME_PATH": str(ADAPTER),
            "ANCF_ADAPTER_RUNTIME_SHA256": "0" * 64,
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaisesRegex(launcher.LaunchContractError, "guard result differs"):
                launcher._verify_adapter(contract_auth)

    def test_participant_run_path_requires_exact_bounded_authorization(self) -> None:
        root = {"execution_authorization": {"mode": "BOUNDED_COUPLING_QUALIFICATION", "max_windows": 25}}
        bundle = type("Bundle", (), {"case_id": "ANCF_SINGLE_SLICE_HIGHRE_0P2S_PREP_V1", "root": root})()
        self.assertEqual(participant._bounded_window_limit(bundle, 25), 25)
        for requested in (None, 2, 5, 26):
            with self.subTest(requested=requested):
                with self.assertRaises( participant.HH06ContractError):
                    participant._bounded_window_limit(bundle, requested)

    def test_duplicate_json_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phase1d6-json-contract-") as temp_dir:
            path = Path(temp_dir) / "duplicate.json"
            path.write_text('{"max_windows":5,"max_windows":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(launcher.LaunchContractError, "duplicate JSON key"):
                launcher.load_json_strict(path)

    def test_linked_contracts_keep_default_deny_and_only_allow_exact_override(self) -> None:
        structure = launcher.load_json_strict(CASE_DIR / "structure_contract.json")
        interface = launcher.load_json_strict(CASE_DIR / "interface_contract.json")
        launcher._validate_linked_launch_boundaries(structure, interface)

        interface["launch_boundary"]["bounded_qualification_override"]["max_windows"] = 2
        with self.assertRaisesRegex(launcher.LaunchContractError, "bounded override is inconsistent"):
            launcher._validate_linked_launch_boundaries(structure, interface)

    def test_frozen_iqn_ils_profile_is_exact_and_rejects_history_change(self) -> None:
        root = ET.parse(CASE_DIR / "precice-config.xml").getroot()
        implicit = next(item for item in root.iter() if launcher._local(item.tag) == "parallel-implicit")
        profile = launcher._validate_iqn_ils_profile(implicit)
        self.assertEqual(profile["primary_scalar_dimension"], 4)
        self.assertEqual(profile["max_used_iterations"], 1)
        used = next(item for item in implicit.iter() if launcher._local(item.tag) == "max-used-iterations")
        used.attrib["value"] = "2"
        with self.assertRaisesRegex(launcher.LaunchContractError, "must remain 1"):
            launcher._validate_iqn_ils_profile(implicit)

    def test_iteration_bounds_are_exact_and_fail_closed(self) -> None:
        root = ET.parse(CASE_DIR / "precice-config.xml").getroot()
        implicit = next(item for item in root.iter() if launcher._local(item.tag) == "parallel-implicit")
        self.assertEqual(launcher._validate_iteration_bounds(implicit),
                         {"min_iterations": 2, "max_iterations": 20})
        min_node = next(item for item in implicit if launcher._local(item.tag) == "min-iterations")
        min_node.attrib["value"] = "1"
        with self.assertRaisesRegex(launcher.LaunchContractError, "min-iterations must remain 2"):
            launcher._validate_iteration_bounds(implicit)
        min_node.attrib["value"] = "2"
        max_node = next(item for item in implicit if launcher._local(item.tag) == "max-iterations")
        max_node.attrib["value"] = "21"
        with self.assertRaisesRegex(launcher.LaunchContractError, "max-iterations must remain 20"):
            launcher._validate_iteration_bounds(implicit)

    def test_orphan_worker_identity_is_checked_by_executable(self) -> None:
        expected = Path(sys.executable).resolve()
        with patch.object(launcher.os, "readlink", return_value=str(expected)):
            self.assertTrue(launcher._worker_process_matches(12345, expected))
        with patch.object(launcher.os, "readlink", side_effect=FileNotFoundError):
            self.assertFalse(launcher._worker_process_matches(12345, expected))

    def test_live_attempt_monitor_requires_retry_force_feedback_and_one_step_identity(self) -> None:
        state = {"accepted_windows": set()}

        def attempt(window: int, iteration: int, sequence: int, force_input: list[float],
                    force_returned: list[float], force_read: list[float], *, accepted: bool) -> dict:
            return {
                "window_index": window,
                "iteration_index": iteration,
                "transport_ids": {"sequence": sequence, "request_id": sequence + 100,
                                  "transaction_id": sequence + 200},
                "physical_identity": {"global_step": window, "bridge_step": window,
                                      "integer_tick": window * 200000, "time_s": window * 0.0002,
                                      "dt_s": 0.0002},
                "dt_s": 0.0002,
                "force_input_vector_raw_N": force_input,
                "force_input_read_offset_s": 0.0 if iteration == 1 else 0.0002,
                "returned_force_raw_N": force_returned,
                "force_read_vector_raw_N": force_read,
                "force_read_offset_s": 0.0 if accepted else 0.0002,
                "D_trial_interface_m": [sequence * 1e-6, sequence * 2e-6],
                "D_written_to_precice_m": [sequence * 1e-6, sequence * 2e-6],
                "D_previous_committed_m": [0.0, 0.0, 0.0] if window == 1 else [2e-6, 4e-6, 0.0],
                "commit_status": "committed" if accepted else "rolled_back",
                "rollback_request": not accepted,
            }

        f0 = [launcher.EXPECTED_F0[0], launcher.EXPECTED_F0[1], 0.0]
        f1 = [0.0654, 0.0588, 0.0]
        f2 = [0.0653, 0.0589, 0.0]
        f3 = [0.0652, 0.0590, 0.0]
        launcher._monitor_attempt(attempt(1, 1, 1, f0, f1, f1, accepted=False), state)
        launcher._monitor_attempt(attempt(1, 2, 2, f1, f2, f2, accepted=True), state)
        launcher._monitor_attempt(attempt(2, 1, 3, f2, f3, f3, accepted=False), state)
        self.assertEqual(state["accepted_windows"], {1})

    def test_live_attempt_monitor_fails_closed_on_stale_written_motion(self) -> None:
        record = {
            "window_index": 1, "iteration_index": 1,
            "transport_ids": {"sequence": 1, "request_id": 101, "transaction_id": 201},
            "physical_identity": {"global_step": 1, "bridge_step": 1, "integer_tick": 200000,
                                  "time_s": 0.0002, "dt_s": 0.0002},
            "dt_s": 0.0002,
            "force_input_vector_raw_N": [launcher.EXPECTED_F0[0], launcher.EXPECTED_F0[1], 0.0],
            "D_trial_interface_m": [1e-6, 2e-6], "D_written_to_precice_m": [0.0, 0.0],
            "commit_status": "rolled_back", "rollback_request": True,
        }
        with self.assertRaisesRegex(launcher.LaunchContractError, "D_written != D_trial_interface"):
            launcher._monitor_attempt(record, {"accepted_windows": set()})

    def test_scratch_case_preserves_restart_and_uses_isolated_runtime_overlay(self) -> None:
        contract = launcher.load_json_strict(CASE_DIR / "contract.json")
        restart = launcher._verify_restart(CASE_DIR, contract, contract["initial_state"])
        authoritative_hashes = {
            path: launcher.sha256(CASE_DIR / path)
            for path in ("system/controlDict", "system/fvSolution", "precice-config.xml", "30/uniform/time")
        }
        foam_bin = "/opt/openfoam10/platforms/linux64GccDPInt32Opt/bin"
        env_path = foam_bin + os.pathsep + os.environ.get("PATH", "")
        with tempfile.TemporaryDirectory(prefix="phase1i-scratch-test-", dir=REPO_ROOT / "evidence") as temp_dir:
            run_dir = Path(temp_dir)
            with patch.dict(os.environ, {"PATH": env_path}, clear=False):
                runtime_case, record = launcher._prepare_runtime_case(CASE_DIR, run_dir, restart)
            self.assertNotEqual(runtime_case.resolve(), CASE_DIR.resolve())
            self.assertEqual(record["runtime_numeric_time_directories_before_start"], ["30"])
            self.assertEqual(record["restart_field_hashes_verified"], restart["field_hashes_verified"])
            self.assertEqual(record["iqn_ils_profile"]["type"], "IQN-ILS")
            self.assertFalse(record["passive_diagnostic_overlays"]["controlDict"]["physics_changed"])
            self.assertTrue((run_dir / "diagnostic_overlay.diff").is_file())
            self.assertEqual(record["precice_socket_directory"], str((run_dir / "precice-sockets").resolve()))
        self.assertEqual(authoritative_hashes, {
            path: launcher.sha256(CASE_DIR / path) for path in authoritative_hashes
        })

    def test_active_process_using_configured_socket_is_detected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phase1d6-socket-users-") as temp_dir:
            root = Path(temp_dir)
            proc_root = root / "proc"
            proc = proc_root / "1234567"
            proc.mkdir(parents=True)
            case_dir = root / "case"
            case_dir.mkdir()
            socket_path = root / "shared-sockets"
            socket_path.mkdir()
            config_path = case_dir / "precice-config.xml"
            config_path.write_text("<precice-configuration />\n", encoding="utf-8")
            (proc / "cmdline").write_bytes(f"unrelated\0{socket_path}\0".encode())
            (proc / "comm").write_text("unrelated\n", encoding="utf-8")
            (proc / "cwd").symlink_to(case_dir, target_is_directory=True)
            (proc / "fd").mkdir()

            users = launcher._active_socket_users(socket_path, config_path, case_dir, proc_root=proc_root)
            self.assertEqual(len(users), 1)
            self.assertIn("pid=1234567", users[0])


if __name__ == "__main__":
    unittest.main()
