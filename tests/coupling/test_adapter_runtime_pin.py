"""Offline test for the launch-time SHA pin of the qualified Fluid adapter."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "cases" / "hh06_single_slice" / "preflight_adapter_sha.sh"
OPENFOAM_BASHRC = Path("/opt/openfoam10/etc/bashrc")
EXPECTED_SHA256 = "26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572"
QUALIFIED_LIBRARY = Path(
    "/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/"
    "libpreciceAdapterFunctionObject.so"
)


class AdapterRuntimePinTests(unittest.TestCase):
    def test_exact_qualified_adapter_passes_and_bad_binary_fails_closed(self) -> None:
        self.assertTrue(OPENFOAM_BASHRC.is_file(), "OpenFOAM-10 environment required for this host qualification test")
        self.assertTrue(QUALIFIED_LIBRARY.is_file(), "SHA-pinned adapter binary is not installed at its qualified path")

        env = os.environ.copy()
        env.pop("ANCF_PRECICE_ADAPTER_LIBRARY", None)
        good = subprocess.run(
            ["bash", "-c", 'source "$1" >/dev/null; bash "$2"', "adapter-pin-test", str(OPENFOAM_BASHRC), str(GUARD)],
            env=env, text=True, capture_output=True, check=False,
        )
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertIn("ADAPTER_RUNTIME_BINARY_PINNED=YES", good.stdout)
        self.assertIn("ADAPTER_SOURCE_PROVENANCE_RESOLVED=NO", good.stdout)
        self.assertIn(f"ADAPTER_RUNTIME_SHA256={EXPECTED_SHA256}", good.stdout)
        self.assertIn(str(QUALIFIED_LIBRARY), good.stdout)

        launcher = (REPO_ROOT / "cases" / "hh06_single_slice" / "launch.sh").read_text(encoding="utf-8")
        guard_position = launcher.index('bash "$CASE_DIR/preflight_adapter_sha.sh"')
        helper_position = launcher.rindex('exec python3 "$CASE_DIR/bounded_qualification.py"')
        helper = (REPO_ROOT / "cases" / "hh06_single_slice" / "bounded_qualification.py").read_text(encoding="utf-8")
        adapter_check_position = helper.index("adapter = _verify_adapter(auth)")
        socket_check_position = helper.index("socket = _check_socket_directory(", adapter_check_position)
        run_start_position = helper.index("def run_bounded(")
        self.assertLess(guard_position, helper_position)
        self.assertLess(adapter_check_position, socket_check_position)
        self.assertLess(socket_check_position, run_start_position)

        with tempfile.TemporaryDirectory(prefix="bad-adapter-sha-") as temp_dir:
            fake = Path(temp_dir) / "libpreciceAdapterFunctionObject.so"
            fake.write_bytes(b"deliberately-not-the-qualified-adapter")
            bad_env = env.copy()
            bad_env["ANCF_PRECICE_ADAPTER_LIBRARY"] = str(fake)
            bad = subprocess.run(
                ["bash", str(GUARD)], env=bad_env, text=True,
                capture_output=True, check=False,
            )
        self.assertEqual(bad.returncode, 2, bad.stdout + bad.stderr)
        self.assertIn("adapter SHA mismatch", bad.stderr)
        self.assertNotIn("ADAPTER_RUNTIME_BINARY_PINNED=YES", bad.stdout)


if __name__ == "__main__":
    unittest.main()
