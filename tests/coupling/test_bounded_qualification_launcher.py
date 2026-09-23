from __future__ import annotations

from pathlib import Path
import os
import shutil
import sys
import tempfile
import unittest
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
        run_dir = REPO_ROOT / "evidence" / "phase1f_bounded_5window" / "<UNIQUE_RUN_ID>"
        plan = launcher.construct_commands(CASE_DIR, WORKER, 5, fluid_exe, run_dir)

        self.assertEqual(
            list(plan.fluid_command),
            [fluid_exe, "-case", str(CASE_DIR.resolve())],
        )
        structure = list(plan.structure_command)
        self.assertEqual(structure[:2], [str(Path(sys.executable).resolve()), str(launcher.PARTICIPANT.resolve())])
        self.assertEqual(structure[2:8], ["--case", str(CASE_DIR.resolve()), "--run", "--worker", str(WORKER.resolve()), "--max-windows"])
        self.assertEqual(structure[8], "5")
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
        }
        with patch.dict(os.environ, env, clear=False):
            plan, report = launcher.preflight(CASE_DIR, str(WORKER), 5)
        self.assertEqual(report["status"], "PASS_PREFLIGHT_ONLY")
        self.assertFalse(report["runtime_started"])
        self.assertTrue(report["checks"]["F0_provenance_and_restart_hashes"])
        self.assertTrue(report["checks"]["python_precice_binding_runtime_qualified"])
        self.assertEqual(report["max_windows"], 5)
        self.assertEqual(report["precice"]["max_time_windows"], 5)
        self.assertEqual(report["max_iterations"], 20)
        self.assertEqual(plan.socket_directory, Path(report["precice"]["socket_directory"]["path"]))

    def test_wrong_cap_is_rejected(self) -> None:
        for wrong_cap in (2, 6, 25):
            with self.subTest(wrong_cap=wrong_cap):
                with self.assertRaisesRegex(launcher.LaunchContractError, "exactly --max-windows 5"):
                    launcher.construct_commands(CASE_DIR, WORKER, wrong_cap, "/usr/bin/pimpleFoam", Path("/tmp/unused"))
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
        root = {"execution_authorization": {"mode": "BOUNDED_COUPLING_QUALIFICATION", "max_windows": 5}}
        bundle = type("Bundle", (), {"case_id": "ANCF_SINGLE_SLICE_HIGHRE_0P2S_PREP_V1", "root": root})()
        self.assertEqual(participant._bounded_window_limit(bundle, 5), 5)
        for requested in (None, 2, 6, 25):
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
