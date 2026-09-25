#!/usr/bin/env python3
"""Run the single authorized Phase 1K.28 old-native B1 G2 diagnostic.

B1 is identical to the bounded B0 old-native run except that the isolated
K27 force-instrumented source retains the already-defined G2 meshPhi
canonicalization.  It creates a new scratch and a separately named library;
it never modifies the authoritative case or a production adapter.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import phase1k28_run_old_native_b0 as b0


RUN_ID = "run-20260925T113000Z-fc0f94d-b1-g2"
RUN = b0.ROOT / "evidence/phase1k28_old_native_reference" / RUN_ID
ADAPTER_NAME = "libpreciceAdapterPhase1K28OldNativeB1G2Diag.so"


def build_adapter() -> tuple[Path, Path]:
    b0.require(b0.K27_SOURCE.is_dir(), f"K27 G2 source missing: {b0.K27_SOURCE}")
    source = RUN / "adapter-source"
    shutil.copytree(
        b0.K27_SOURCE, source,
        ignore=shutil.ignore_patterns(".git", "lnInclude", "linux64GccDPInt32Opt"),
    )
    make_files = source / "Make/files"
    baseline = make_files.read_text(encoding="utf-8")
    updated = baseline.replace("libpreciceAdapterPhase1K27ForceDiag", ADAPTER_NAME)
    b0.require(updated != baseline, "B1 library identity rename did not apply")
    make_files.write_text(updated, encoding="utf-8")

    patch = "".join(difflib.unified_diff(
        baseline.splitlines(keepends=True), updated.splitlines(keepends=True),
        fromfile="a/Make/files", tofile="b/Make/files",
    ))
    patch_path = RUN / "source_diff.patch"
    patch_path.write_text(patch, encoding="utf-8")

    build = RUN / "adapter-build"
    build.mkdir()
    command = (
        "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; "
        "export ADAPTER_TARGET_DIR=\"$1\"; cd \"$2\"; wmake libso ."
    )
    result = subprocess.run(
        ["/bin/bash", "-c", command, "phase1k28-b1-build", str(build), str(source)],
        capture_output=True, text=True, timeout=900,
    )
    (build / "build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    b0.require(result.returncode == 0, f"B1 adapter build failed; see {build / 'build.log'}")
    adapter = build / ADAPTER_NAME
    b0.require(adapter.is_file(), f"B1 adapter binary missing: {adapter}")
    return adapter, patch_path


def record_b1_identity(case: Path, adapter: Path, patch_path: Path) -> None:
    b0.record_identity(case, adapter, patch_path)
    identity_path = RUN / "runtime_identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity.update({
        "schema": "phase1k28_old_native_b1_g2_runtime_identity_v1",
        "run_id": RUN_ID,
        "g2_meshphi_canonicalization": True,
        "candidate": "OLD_NATIVE_G2_DIAG",
        "b0_baseline_run_id": "run-20260925T113000Z-fc0f94d-b0",
        "adapter_sha256": b0.sha(adapter),
        "adapter_path": str(adapter),
        "source_diff_description": "K27 G2 source retained; only library identity renamed for B1",
    })
    identity_path.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    restart = json.loads((RUN / "restart_identity.json").read_text(encoding="utf-8"))
    restart.update({"candidate": "OLD_NATIVE_G2_DIAG", "g2_meshphi_canonicalization": True})
    (RUN / "restart_identity.json").write_text(json.dumps(restart, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"preflight", "run"}:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} preflight|run")
    mode = sys.argv[1]
    b0.require(b0.RUN.exists(), "B0 evidence must exist before B1")
    b0.require((b0.RUN / "process_cleanup.json").is_file(), "B0 cleanup evidence missing")
    # Reuse B0's bounded helpers, but redirect every RUN-relative artifact to
    # the independent B1 evidence tree before any case or process operation.
    b0.RUN = RUN
    b0.require(not RUN.exists(), f"refusing to overwrite existing B1 run: {RUN}") if mode == "preflight" else None
    if mode == "preflight":
        RUN.mkdir(parents=True)
        case = RUN / "prepared/case"
        case.parent.mkdir(parents=True, exist_ok=True)
        adapter, patch_path = build_adapter()
        b0.copy_old_case(case)
        b0.prepare_case(case, adapter)
        record_b1_identity(case, adapter, patch_path)
        shutil.copy2(b0.SOURCE_CASE / "README.md", RUN / "old_native_case_readme.md")
        b0.validate(case)
        (RUN / "preflight_status.json").write_text(json.dumps({
            "status": "PASS_PREFLIGHT_ONLY", "b0": False, "b1": True,
            "g2": True, "runtime_started": False, "physical_windows": 0,
        }, indent=2) + "\n", encoding="utf-8")
        return 0

    b0.require(RUN.is_dir(), f"B1 preflight run directory missing: {RUN}")
    status = json.loads((RUN / "preflight_status.json").read_text(encoding="utf-8"))
    b0.require(status == {
        "status": "PASS_PREFLIGHT_ONLY", "b0": False, "b1": True,
        "g2": True, "runtime_started": False, "physical_windows": 0,
    }, "B1 preflight gate mismatch")
    case = RUN / "prepared/case"
    adapter = RUN / f"adapter-build/{ADAPTER_NAME}"
    b0.require(case.is_dir() and adapter.is_file(), "B1 case or adapter missing")
    b0.require(not (RUN / "process_cleanup.json").exists(), "refusing to overwrite B1 runtime evidence")
    b0.validate(case)
    cleanup = b0.launch(case)
    b0.require(cleanup["stop_reason"] is None, f"B1 runtime stopped: {cleanup['stop_reason']}")
    b0.require(cleanup["exit_codes"] == {"fluid": 0, "structure": 0},
               f"B1 participant exit codes: {cleanup['exit_codes']}")
    b0.require(any(ADAPTER_NAME in x for x in cleanup["loaded_libraries_by_role"]["fluid"]),
               "B1 adapter was not loaded")
    b0.require(not any("libRBFMeshMotionSolver" in x
                       for x in cleanup["loaded_libraries_by_role"]["fluid"]),
               "RBF library unexpectedly loaded")
    case_logs = {
        "precice_iterations.log": "precice-Fluid_0000-iterations.log",
        "precice_convergence.log": "precice-Fluid_0000-convergence.log",
    }
    for target, source in case_logs.items():
        path = case / source
        b0.require(path.is_file(), f"missing B1 runtime log: {path}")
        shutil.copy2(path, RUN / target)
    result = json.loads((RUN / "fixed_structure_result.json").read_text(encoding="utf-8"))
    attempts = [row for row in result.get("records", []) if row.get("stage") == "attempt"]
    b0.require(len(attempts) == 4, f"expected four B1 attempts, got {len(attempts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
