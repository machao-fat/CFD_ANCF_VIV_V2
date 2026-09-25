#!/usr/bin/env python3
"""Phase 1K.30 production-prefix plus same-time-step continuation diagnostic."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
K29_RUN = ROOT / "evidence/phase1k29_cfd_inner_convergence/run-20260925T214500Z-9747b00"
K29_CASE = K29_RUN / "A/case"
K29_SOURCE = K29_RUN / "solver-source"
K28_RUN = ROOT / "evidence/phase1k28_old_native_reference/run-20260925T113000Z-fc0f94d-b1-g2b"
ADAPTER = K28_RUN / "adapter-build/libpreciceAdapterPhase1K28OldNativeB1G2Diag.so"
RUN_ID = "run-20260925T153500Z-a8be630-buildfix1"
RUN = ROOT / "evidence/phase1k30_production_prefix_continuation" / RUN_ID
DSTAR = [1.0633832164606064e-07, 9.530777190012017e-08]
EXPECTED_HEAD = "a8be63024b2e8568f65476ca38a93080e6c9450a"
EXPECTED_ADAPTER_SHA = "0edcfae77d51d8a57a354a1b745c77f6c15108bf532be0d4893394e80a2d785d"
EXPECTED_PRECICE_SHA = "b20729622d2dbbafdea3d6ead0480ec66be98cb947db3500cc3c27ed4e3039c7"


def fail(message: str) -> None:
    raise SystemExit("PHASE1K30_BLOCKED: " + message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(command: list[str], cwd: Path = ROOT, timeout: int = 120) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    require(result.returncode == 0, f"command failed: {' '.join(command)}\n{result.stderr}")
    return result.stdout.strip()


def copy_case(target: Path, label: str) -> None:
    require(not target.exists(), f"refusing to overwrite {target}")
    shutil.copytree(K29_CASE, target)
    xml = target / "precice-config.xml"
    text = xml.read_text()
    text = re.sub(r'exchange-directory="[^"]+"', f'exchange-directory="{RUN / label / "precice-sockets"}"', text, count=1)
    xml.write_text(text)
    control = target / "system/controlDict"
    control_text = control.read_text()
    require(str(ADAPTER) in control_text, "case does not use the frozen B1/G2 adapter")
    contract = json.loads((target / "contract.json").read_text())
    contract["execution_authorization"]["max_windows"] = 1
    contract["coupling"]["max_iterations"] = 4
    contract["coupling"]["accepted_window_limit"] = 1
    contract["coupling"]["duration_s"] = 0.0002
    (target / "contract.json").write_text(json.dumps(contract, indent=2) + "\n")


def build_solver() -> Path:
    source = RUN / "solver-source"
    require(not source.exists(), f"refusing to overwrite {source}")
    shutil.copytree(K29_SOURCE, source)
    shutil.copy2(ROOT / "scripts/phase1k30_continuation_trace.H", source / "phase1k30_continuation_trace.H")
    shutil.copy2(ROOT / "scripts/phase1k30_continuation_pEqn.H", source / "phase1k30_continuation_pEqn.H")
    main = source / "pimpleFoam.C"
    text = main.read_text()
    marker = '#include "phase1k29_inner_trace.H"'
    require(marker in text, "K29 solver marker missing")
    text = text.replace(marker, marker + '\n#include "phase1k30_continuation_trace.H"')
    outer_marker = 'phase1k29diag::writeOuter(mesh, p, U, turbulence->k(), turbulence->omega(), turbulence->nut(), phi, *turbulence, phase1k26SolveId, phase1k26Outer);'
    require(text.count(outer_marker) == 1, "K29 outer trace insertion point not unique")
    text = text.replace(
        outer_marker,
        outer_marker + '\n            phase1k30diag::force(mesh, p, U, turbulence->k(), turbulence->omega(), turbulence->nut(), phi, *turbulence, phase1k26SolveId, phase1k26Outer, "production_prefix");'
    )
    end_marker = '        phase1k26diag::write(mesh, "S11_before_runTime_write", phase1k26SolveId);'
    require(text.count(end_marker) == 1, "K29 end marker not unique")
    continuation = r'''
        phase1k30diag::snapshot(mesh, U, p, turbulence->k(), turbulence->omega(), turbulence->nut(), phi, "production_prefix");
        for (Foam::label phase1k30Cycle = 1; phase1k30Cycle <= 3; ++phase1k30Cycle)
        {
            // Keep the same physical time, mesh and displacement. This flag is
            // reasserted because pimpleControl clears it during normal loops.
            mesh.data::remove("finalIteration");
            mesh.data::add("finalIteration", true);
            fvModels.correct();
            #include "UEqn.H"
            #include "phase1k30_continuation_pEqn.H"
            viscosity->correct();
            turbulence->correct();
            phase1k30diag::force(mesh, p, U, turbulence->k(), turbulence->omega(), turbulence->nut(), phi, *turbulence, phase1k26SolveId, phase1k30Cycle, "continuation");
            if (phase1k30Cycle == 3)
            {
                phase1k30diag::snapshot(mesh, U, p, turbulence->k(), turbulence->omega(), turbulence->nut(), phi, "strict");
            }
        }
'''
    text = text.replace(end_marker, continuation + "\n" + end_marker)
    main.write_text(text)
    make = source / "Make/files"
    make_text = make.read_text()
    require("pimpleFoamPhase1K29Diag" in make_text, "unexpected K29 Make/files")
    make.write_text(make_text.replace("pimpleFoamPhase1K29Diag", "pimpleFoamPhase1K30Diag"))
    log = RUN / "solver-build.log"
    command = "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; cd \"$1\"; wmake"
    result = subprocess.run(["/bin/bash", "-c", command, "k30-build", str(source)], capture_output=True, text=True, timeout=900)
    log.write_text(result.stdout + result.stderr)
    require(result.returncode == 0, f"solver build failed; see {log}")
    solver = Path("/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/bin/pimpleFoamPhase1K30Diag")
    require(solver.is_file(), f"missing solver {solver}")
    return solver


def loaded_libraries(pid: int) -> set[str]:
    maps = Path(f"/proc/{pid}/maps")
    if not maps.is_file():
        return set()
    return {
        line.split()[-1].removesuffix(" (deleted)")
        for line in maps.read_text(errors="replace").splitlines()
        if line.split() and any(x in line for x in ("libpreciceAdapter", "libprecice.so"))
    }


def launch(label: str, solver: Path) -> dict:
    root = RUN / label
    case = root / "case"
    for name in ("diagnostics", "rbf_diagnostics", "stages", "fields", "fields/production_prefix", "fields/strict", "precice-sockets"):
        (root / name).mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "PYTHONUNBUFFERED": "1",
        "PHASE1K24_DIAG_DIR": str(root / "diagnostics"),
        "PHASE1K18_DIAG_DIR": str(root / "rbf_diagnostics"),
        "PHASE1K26_STAGE_DIR": str(root / "stages"),
        "PHASE1K27_DIRECT_FORCE_TRACE": str(root / "direct_force_trace.jsonl"),
        "PHASE1K27_ADAPTER_PREWRITE_TRACE": str(root / "adapter_prewrite_force.jsonl"),
        "PHASE1K27_FLUID_INPUT_TRACE": str(root / "fluid_input_trace.jsonl"),
        "PHASE1K29_OUTER_FORCE_TRACE": str(root / "outer_iteration_force_trace.jsonl"),
        "PHASE1K30_FORCE_TRACE": str(root / "continuation_force_trace.jsonl"),
        "PHASE1K30_FIELD_SNAPSHOT_DIR": str(root / "fields"),
    })
    fluid = ["/bin/bash", "-c", "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; cd \"$1\"; exec \"$2\" -case .", "k30-fluid", str(case), str(solver)]
    structure = ["/usr/bin/python3.10", str(RUN / "fixed_structure.py"), str(case / "precice-config.xml"), str(root / "fixed_structure_result.json"), str(DSTAR[0]), str(DSTAR[1])]
    processes = {}
    handles = []
    observed = {"fluid": set(), "structure": set()}
    reason = None
    started = time.monotonic()
    try:
        for role, command in (("fluid", fluid), ("structure", structure)):
            out = (root / f"{role}.stdout").open("x")
            err = (root / f"{role}.stderr").open("x")
            handles.extend((out, err))
            processes[role] = subprocess.Popen(command, cwd=case, env=env, stdout=out, stderr=err, start_new_session=True)
        deadline = started + 900
        while any(p.poll() is None for p in processes.values()):
            for role, process in processes.items():
                observed[role].update(loaded_libraries(process.pid))
            failed = [role for role, process in processes.items() if process.poll() not in (None, 0)]
            if failed:
                reason = "participant exited nonzero: " + ",".join(failed)
                break
            if time.monotonic() > deadline:
                reason = "900-second hard timeout"
                break
            time.sleep(0.2)
    finally:
        if reason:
            for process in processes.values():
                if process.poll() is None:
                    process.terminate()
        for process in processes.values():
            process.wait(timeout=30)
        for handle in handles:
            handle.close()
    cleanup = {
        "fluid_command": fluid,
        "structure_command": structure,
        "pids": {role: process.pid for role, process in processes.items()},
        "exit_codes": {role: process.returncode for role, process in processes.items()},
        "loaded_libraries_by_role": {role: sorted(values) for role, values in observed.items()},
        "stop_reason": reason,
        "wall_duration_s": time.monotonic() - started,
        "working_directory": str(case),
        "worker_process": "NOT_STARTED; fixed-displacement diagnostic participant",
        "socket_entries_after_shutdown": sorted(p.name for p in (root / "precice-sockets").iterdir()),
    }
    (root / "process_cleanup.json").write_text(json.dumps(cleanup, indent=2) + "\n")
    require(reason is None and cleanup["exit_codes"] == {"fluid": 0, "structure": 0}, f"{label} runtime failed: {cleanup}")
    require(any(ADAPTER.name in x for x in cleanup["loaded_libraries_by_role"]["fluid"]), f"{label} adapter not loaded")
    return cleanup


def write_identity(solver: Path) -> None:
    restart = json.loads((K29_RUN / "restart_identity.json").read_text())
    identity = {
        "schema": "phase1k30_runtime_identity_v1",
        "git_head": run_cmd(["git", "rev-parse", "HEAD"]),
        "git_branch": run_cmd(["git", "branch", "--show-current"]),
        "openfoam": "Foundation OpenFOAM 10",
        "precice": "3.4.1",
        "precice_sha256": sha(Path("/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1")),
        "adapter_sha256": sha(ADAPTER),
        "adapter_build_id": run_cmd(["readelf", "-n", str(ADAPTER)]).split("Build ID:", 1)[1].splitlines()[0].strip(),
        "diagnostic_solver": str(solver),
        "diagnostic_solver_sha256": sha(solver),
        "d_star_m": DSTAR,
        "d_star_sha256": hashlib.sha256(json.dumps(DSTAR, separators=(",", ":")).encode()).hexdigest(),
        "dt_s": 0.0002,
        "one_physical_window": True,
        "attempt_ceiling": 4,
        "restart_identity": restart,
    }
    (RUN / "runtime_identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    (RUN / "restart_identity.json").write_text(json.dumps(restart, indent=2) + "\n")


def preflight() -> None:
    require(run_cmd(["git", "rev-parse", "HEAD"]) == EXPECTED_HEAD, "K30 must start at frozen K29 HEAD")
    require(sha(ADAPTER) == EXPECTED_ADAPTER_SHA, "B1/G2 adapter SHA mismatch")
    require(sha(Path("/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1")) == EXPECTED_PRECICE_SHA, "preCICE SHA mismatch")
    require(K29_CASE.is_dir() and K29_SOURCE.is_dir() and (K29_RUN / "fixed_structure.py").is_file(), "provenance source missing")
    require(not RUN.exists(), f"refusing to overwrite existing run {RUN}")
    RUN.mkdir(parents=True)
    shutil.copy2(K29_RUN / "fixed_structure.py", RUN / "fixed_structure.py")
    solver = build_solver()
    write_identity(solver)
    for label in ("R1", "R2"):
        (RUN / label).mkdir()
        copy_case(RUN / label / "case", label)
        (RUN / label / "configuration.json").write_text(json.dumps({
            "label": label,
            "prefix_outer_count": 3,
            "continuation_cycles": 3,
            "nCorrectors": 2,
            "nNonOrthogonalCorrectors": 0,
            "momentumPredictor": True,
            "adapter_sha256": sha(ADAPTER),
            "case_fvSolution_sha256": sha(RUN / label / "case/system/fvSolution"),
            "case_fvSchemes_sha256": sha(RUN / label / "case/system/fvSchemes"),
        }, indent=2) + "\n")
    (RUN / "preflight_status.json").write_text(json.dumps({
        "status": "PASS_PREFLIGHT_ONLY",
        "runtime_started": False,
        "physical_windows": 0,
        "prefix_outer_count": 3,
        "continuation_cycles": 3,
        "continuation_writes_to_precice": False,
    }, indent=2) + "\n")


def main() -> int:
    require(len(os.sys.argv) == 2 and os.sys.argv[1] in {"preflight", "run"}, "usage: preflight|run")
    if os.sys.argv[1] == "preflight":
        preflight()
        return 0
    require((RUN / "preflight_status.json").is_file(), "preflight has not passed")
    status = json.loads((RUN / "preflight_status.json").read_text())
    require(status["status"] == "PASS_PREFLIGHT_ONLY" and not status["runtime_started"], "invalid preflight status")
    solver = Path(json.loads((RUN / "runtime_identity.json").read_text())["diagnostic_solver"])
    cleanup = {label: launch(label, solver) for label in ("R1", "R2")}
    (RUN / "process_cleanup.json").write_text(json.dumps(cleanup, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
