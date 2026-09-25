#!/usr/bin/env python3
"""Isolate ancillary function-object state for Phase 1K.25."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

from phase1k24_fluid_state_replay import (  # noqa: E402
    ADAPTER,
    copy_case,
    launch,
    patch_case,
    record_identity,
    validate,
)
import phase1k24_fluid_state_replay as base_runner  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
BASE_ADAPTER = ADAPTER


def remove_function_object(text: str, name: str) -> str:
    pattern = rf"\n    {re.escape(name)}\s*\{{.*?\n    \}}\n"
    updated, count = re.subn(pattern, "\n", text, count=1, flags=re.DOTALL)
    if count != 1:
        raise SystemExit(f"missing function object {name}")
    return updated


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in ("same-process", "fresh-a", "fresh-b"):
        raise SystemExit("usage: phase1k25_run_group5.py MODE RUN_DIR")
    mode = sys.argv[1]
    run = Path(sys.argv[2]).expanduser().resolve()
    base_runner.ADAPTER = BASE_ADAPTER
    max_iterations, min_iterations = (4, 2) if mode == "same-process" else (1, 1)
    case = copy_case(run)
    patch_case(case, run, max_iterations, min_iterations)
    control = (case / "system/controlDict").read_text(encoding="utf-8")
    for name in ("cylinderForces", "cylinderForceCoeffs", "yPlus"):
        control = remove_function_object(control, name)
    (case / "system/controlDict").write_text(control, encoding="utf-8")
    identity = record_identity(
        run, case, "group5-ancillary-function-object-isolation-" + mode,
        max_iterations, min_iterations,
    )
    identity.update({
        "candidate": "GROUP5_ANCILLARY_FUNCTION_OBJECT_ISOLATION",
        "candidate_adapter_sha256": base_runner.sha(BASE_ADAPTER),
        "removed_scratch_function_objects": ["cylinderForces", "cylinderForceCoeffs", "yPlus"],
        "production_configuration_modified": False,
    })
    (run / "runtime_identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    validate(run, case)
    (run / "preflight_status.json").write_text(
        json.dumps({"status": "PASS_PREFLIGHT_ONLY", "candidate": identity}, indent=2) + "\n",
        encoding="utf-8",
    )
    cleanup = launch(run, case)
    if cleanup["stop_reason"] is not None or not all(code == 0 for code in cleanup["exit_codes"].values()):
        raise SystemExit("GROUP5 runtime failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
