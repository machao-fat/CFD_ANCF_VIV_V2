#!/usr/bin/env python3
"""Single-use, fail-closed runner for the isolated Phase 1K.18.6 probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

RUN = Path(__file__).resolve().parent
REPO = RUN.parents[2]
CASE = RUN / "case"
DIAG = RUN / "diagnostics"
FROZEN = REPO / "evidence/phase1k10_new_mesh_restart/run-20260924T085251Z-c2245ff/mapped_candidate_30"
PARTICIPANT = REPO / "src/coupling/hh06_structure_0000/structure_0000_participant.py"
WORKER = REPO / "build/phase1d6_worker/cfd_ancf_ancf_kernel_worker"
ADAPTER = RUN / "adapter-lib/libpreciceAdapterPhase1K18Diag.so"
RBF = RUN / "rbf-lib/libRBFMeshMotionSolverPhase1K18Diag.so"
ADAPTER_ORIGINAL = Path("/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so")
RBF_ORIGINAL = Path("/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libRBFMeshMotionSolver.so")
TIMEOUT_S = 180
EXPECTED = {
    "head": "c2245ff396ff42dfa5e80fee6555a9ede93e3b04",
    "worker_sha256": "3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596",
    "qualified_adapter_sha256": "26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572",
    "qualified_rbf_sha256": "b27b347c4ba3026a495517ae7ae237ceb5cd8408ac0db9af6a58ccd83647a20c",
    "adapter_sha256": "cab6f4bffcc71ea24f296ece6c67ec9f1c6011e7139b39f2af62d2145422f71e",
    "adapter_build_id": "f17adc69bf9540ce23982d09165628fff2ce8c03",
    "rbf_sha256": "3defd4b158f48062d6222911a449a2b1995f1b0fc0ca00e9453c19a6b6f6dd28",
    "rbf_build_id": "977bf4d3b867b6cb7a3bd7197e8c5433d70013e7",
    "libprecice_sha256": "b20729622d2dbbafdea3d6ead0480ec66be98cb947db3500cc3c27ed4e3039c7",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha(paths: list[Path], base: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(base).as_posix().encode())
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def json_write(path: Path, value: object, exclusive: bool = False) -> None:
    with path.open("x" if exclusive else "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def run_text(command: list[str], env: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {command}\n{result.stdout}")
    return result.stdout.strip()


def git_value(*args: str) -> str:
    return run_text(["git", "-C", str(REPO), *args])


def uniform_time(path: Path) -> float:
    match = re.search(r"^\s*value\s+([-+0-9.eE]+)\s*;",
                      path.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise RuntimeError(f"cannot parse OpenFOAM time value: {path}")
    return float(match.group(1))


def maps_for(pid: int) -> list[str]:
    maps = Path(f"/proc/{pid}/maps")
    if not maps.exists():
        return []
    needles = ("libprecice", "Phase1K18Diag", "cfd_ancf_ancf_kernel_worker")
    return [line.rstrip() for line in maps.read_text(errors="replace").splitlines()
            if any(needle in line for needle in needles)]


def descendants(pid: int) -> list[int]:
    result: list[int] = []
    pending = [pid]
    while pending:
        current = pending.pop()
        child_file = Path(f"/proc/{current}/task/{current}/children")
        if not child_file.exists():
            continue
        try:
            children = [int(part) for part in child_file.read_text().split()]
        except (OSError, ValueError):
            children = []
        result.extend(children)
        pending.extend(children)
    return sorted(set(result))


def numeric_time_dirs() -> list[tuple[float, str]]:
    result = []
    for item in CASE.iterdir():
        if item.is_dir():
            try:
                result.append((float(item.name), item.name))
            except ValueError:
                pass
    return sorted(result)


def preflight() -> dict:
    if not CASE.is_dir() or not FROZEN.is_dir():
        raise RuntimeError("scratch or frozen mapped restart directory is missing")
    if git_value("rev-parse", "HEAD") != EXPECTED["head"]:
        raise RuntimeError("unexpected repository HEAD")
    if git_value("branch", "--show-current") != "repair/worker-lineage-implicit-contract-v1":
        raise RuntimeError("unexpected Git branch")
    for diff_args in (("diff", "--quiet"), ("diff", "--cached", "--quiet")):
        result = subprocess.run(["git", "-C", str(REPO), *diff_args], check=False)
        if result.returncode != 0:
            raise RuntimeError("tracked/index changes exist outside this isolated evidence")
    tracked_source_clean = True
    run_text(["git", "-C", str(REPO), "diff", "--check"])
    run_text(["git", "-C", str(REPO), "diff", "--cached", "--check"])

    for path in (PARTICIPANT, WORKER, ADAPTER, RBF, ADAPTER_ORIGINAL, RBF_ORIGINAL):
        if not path.is_file():
            raise RuntimeError(f"required identity file is missing: {path}")
    if not os.access(WORKER, os.X_OK) or sha256(WORKER) != EXPECTED["worker_sha256"]:
        raise RuntimeError("qualified worker executable/SHA mismatch")
    if sha256(ADAPTER_ORIGINAL) != EXPECTED["qualified_adapter_sha256"]:
        raise RuntimeError("qualified adapter identity changed")
    if sha256(RBF_ORIGINAL) != EXPECTED["qualified_rbf_sha256"]:
        raise RuntimeError("qualified RBF identity changed")
    if sha256(ADAPTER) != EXPECTED["adapter_sha256"]:
        raise RuntimeError("Phase 1K.18.6 experimental adapter SHA mismatch")
    if sha256(RBF) != EXPECTED["rbf_sha256"]:
        raise RuntimeError("Phase 1K.18.6 experimental RBF SHA mismatch")

    contract = json.loads((CASE / "contract.json").read_text(encoding="utf-8"))
    auth = contract["execution_authorization"]
    coupling = contract["coupling"]
    release = contract["initial_state"]["release_force_provenance"]
    if auth["max_windows"] != 25:
        raise RuntimeError("participant contract authorization must retain its required 25-window profile")
    if coupling["max_iterations"] != 2 or coupling["min_iterations"] != 2:
        raise RuntimeError("scratch cap must allow exactly two attempts")
    if coupling["dt_s"] != 0.0002:
        raise RuntimeError("scratch physical timestep mismatch")
    if auth["worker_binary_sha256"] != EXPECTED["worker_sha256"]:
        raise RuntimeError("contract worker identity mismatch")
    if auth["adapter_runtime_sha256"] != EXPECTED["adapter_sha256"]:
        raise RuntimeError("contract experimental adapter identity mismatch")
    f0_path = RUN / "new_f0_qualified_result.json"
    f0 = json.loads(f0_path.read_text(encoding="utf-8"))
    if release["result_json_sha256"] != sha256(f0_path):
        raise RuntimeError("F0 result evidence SHA mismatch")
    if abs(contract["initial_state"]["Fx0_total_N"] - f0["Fx_raw_N"]) > 1e-15:
        raise RuntimeError("scratch contract Fx0 differs from frozen F0")
    if abs(contract["initial_state"]["Fy0_total_N"] - f0["Fy_raw_N"]) > 1e-15:
        raise RuntimeError("scratch contract Fy0 differs from frozen F0")

    provenance = json.loads((RUN / "new_restart_provenance.json").read_text(encoding="utf-8"))
    expected_fields = provenance["restart"]["field_hashes_sha256_before_and_after"]
    expected_mesh = provenance["restart"]["polyMesh_file_hashes_sha256_before_and_after"]
    checked_fields, checked_mesh = {}, {}
    for name, expected_hash in expected_fields.items():
        for root in (CASE, FROZEN):
            path = root / "30" / name
            if not path.is_file() or sha256(path) != expected_hash:
                raise RuntimeError(f"frozen restart field mismatch: {path}")
        checked_fields[name] = expected_hash
    for name, expected_hash in expected_mesh.items():
        for root in (CASE, FROZEN):
            path = root / "constant/polyMesh" / name
            if not path.is_file() or sha256(path) != expected_hash:
                raise RuntimeError(f"mesh identity mismatch: {path}")
        checked_mesh[name] = expected_hash
    if uniform_time(CASE / "30/uniform/time") != 30.0 or uniform_time(FROZEN / "30/uniform/time") != 30.0:
        raise RuntimeError("restart is not exactly at 30.0 s")
    if [name for _, name in numeric_time_dirs()] != ["30"]:
        raise RuntimeError(f"scratch already contains advanced time directories: {numeric_time_dirs()}")
    if (CASE / "30/cellDisplacement").exists():
        raise RuntimeError("restart unexpectedly has cellDisplacement; expected adapter-owned staging field")

    xml_path = CASE / "precice-config.xml"
    xml = xml_path.read_text(encoding="utf-8")
    for token in ('<max-time-windows value="1"/>', '<time-window-size value="0.0002"/>',
                  '<min-iterations value="2"/>', '<max-iterations value="2"/>',
                  'name="Displacement"', 'name="Force"', 'initialize="yes"'):
        if token not in xml:
            raise RuntimeError(f"scratch preCICE XML missing required one-retry contract token: {token}")
    socket_match = re.search(r'exchange-directory="([^"]+)"', xml)
    if not socket_match:
        raise RuntimeError("preCICE XML has no exchange directory")
    socket_dir = Path(socket_match.group(1)).resolve()
    if not socket_dir.is_relative_to(RUN.resolve()):
        raise RuntimeError("preCICE socket path escapes isolated run directory")
    if socket_dir.exists() and any(socket_dir.iterdir()):
        raise RuntimeError("isolated socket directory is not empty")
    dynamic = (CASE / "constant/dynamicMeshDict").read_text(encoding="utf-8")
    control = (CASE / "system/controlDict").read_text(encoding="utf-8")
    if str(RBF) not in dynamic or str(ADAPTER) not in control:
        raise RuntimeError("scratch case does not load both experimental libraries")
    if not re.search(r"^endTime\s+30\.0002\s*;", control, re.MULTILINE):
        raise RuntimeError("OpenFOAM scratch endTime is not 30.0002 s")

    existing_worker_pids = subprocess.run(["pgrep", "-f", str(WORKER)], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False).stdout.split()
    if existing_worker_pids:
        raise RuntimeError(f"qualified worker process already active: {existing_worker_pids}")
    for name in ("launch_started.json", "fluid.stdout", "structure.stdout",
                 "structure_trace.jsonl", "process_cleanup.json"):
        if (RUN / name).exists():
            raise RuntimeError(f"single-use runtime artifact already exists: {RUN / name}")
    if any(DIAG.glob("*.json")):
        raise RuntimeError("diagnostic snapshots already exist")

    foam_version = run_text(["bash", "-c",
        "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; foamVersion"])
    config_validation = run_text(["precice-config-validate", str(xml_path)])
    participant_help = run_text(["/usr/bin/python3.10", str(PARTICIPANT), "--help"])
    if "--max-windows" not in participant_help or "--worker" not in participant_help:
        raise RuntimeError("authoritative Structure participant CLI changed")
    audit_path = RUN / "structure_preflight_audit.json"
    if audit_path.exists():
        json.loads(audit_path.read_text(encoding="utf-8"))
    else:
        run_text(["/usr/bin/python3.10", str(PARTICIPANT), "--case", str(CASE),
                  "--audit-only", "--audit-output", str(audit_path)])
    probe = ("import ctypes,importlib.metadata,json,pathlib,precice,sys;"
             "ctypes.CDLL('libprecice.so.3');"
             "m=pathlib.Path('/proc/self/maps').read_text().splitlines();"
             "libs=sorted({x.split()[-1] for x in m if 'libprecice.so' in x and '/' in x});"
             "exts=sorted(str(x) for x in pathlib.Path(precice.__file__).parent.glob('*.so'));"
             "print(json.dumps({'python':sys.executable,'python_version':sys.version.split()[0],"
             "'metadata':importlib.metadata.version('pyprecice'),'module':precice.__file__,"
             "'extensions':exts,'loaded_libprecice':libs}))")
    binding = json.loads(run_text(["/usr/bin/python3.10", "-c", probe]))
    loaded_libs = [Path(path) for path in binding["loaded_libprecice"]]
    if not loaded_libs or all(sha256(path) != EXPECTED["libprecice_sha256"] for path in loaded_libs):
        raise RuntimeError("Python binding did not load qualified preCICE runtime SHA")
    pimple_path = run_text(["bash", "-c",
        "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; command -v pimpleFoam"])
    warnings = [line for line in config_validation.splitlines()
                if re.search(r"warning|error", line, re.IGNORECASE)]
    adapter_sources = [p for p in (RUN / "adapter-source").rglob("*")
                       if p.is_file() and (p.suffix in {".C", ".H"} or p.name in {"files", "options"})]
    rbf_sources = [p for p in (RUN / "rbf-source").rglob("*")
                   if p.is_file() and (p.suffix in {".C", ".H"} or p.name in {"files", "options"})]
    return {
        "git": {"branch": git_value("branch", "--show-current"),
                "head": git_value("rev-parse", "HEAD"), "tracked_source_clean": tracked_source_clean},
        "restart": {"source_case": str(FROZEN), "scratch_case": str(CASE), "global_time_s": 30.0,
                    "field_sha256": checked_fields, "mesh_sha256": checked_mesh},
        "f0": {"result": str(f0_path), "result_sha256": sha256(f0_path),
               "Fx_raw_N": f0["Fx_raw_N"], "Fy_raw_N": f0["Fy_raw_N"], "Fz_raw_N": f0["Fz_raw_N"]},
        "worker": {"path": str(WORKER), "sha256": sha256(WORKER)},
        "qualified_binaries_unchanged": {"adapter_sha256": sha256(ADAPTER_ORIGINAL),
                                         "rbf_sha256": sha256(RBF_ORIGINAL)},
        "experimental_adapter": {"path": str(ADAPTER), "sha256": sha256(ADAPTER),
                                 "build_id": EXPECTED["adapter_build_id"],
                                 "source_tree_sha256": tree_sha(adapter_sources, RUN / "adapter-source"),
                                 "source_file_count": len(adapter_sources)},
        "experimental_rbf": {"path": str(RBF), "sha256": sha256(RBF),
                             "build_id": EXPECTED["rbf_build_id"],
                             "source_tree_sha256": tree_sha(rbf_sources, RUN / "rbf-source"),
                             "source_file_count": len(rbf_sources)},
        "software": {"openfoam_version": foam_version, "pimpleFoam": pimple_path,
                     "preCICE_config_validation": config_validation,
                     "preCICE_validation_warnings": warnings, "python_precice_binding": binding,
                     "precice_runtime_sha256": EXPECTED["libprecice_sha256"]},
        "scratch_bounds": {"dt_s": 0.0002, "max_windows": 1, "min_iterations": 2,
                           "max_iterations": 2, "controlDict_endTime_s": 30.0002,
                           "socket_directory": str(socket_dir)},
        "diagnostic_scope": "one physical window; two attempts maximum; one retry maximum",
    }


def stop_group(proc: subprocess.Popen, reason: str) -> dict:
    entry = {"pid": proc.pid, "reason": reason, "signal_sent": None, "exit_code": proc.poll()}
    if proc.poll() is None:
        entry["signal_sent"] = "SIGTERM"
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            entry["exit_code"] = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            entry["signal_sent"] = "SIGKILL_after_SIGTERM_timeout"
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            entry["exit_code"] = proc.wait(timeout=5)
    return entry


def execute(identity: dict) -> dict:
    socket_dir = Path(identity["scratch_bounds"]["socket_directory"])
    socket_dir.mkdir(parents=True, exist_ok=True)
    fluid_out, fluid_err = RUN / "fluid.stdout", RUN / "fluid.stderr"
    structure_out, structure_err = RUN / "structure.stdout", RUN / "structure.stderr"
    trace, audit = RUN / "structure_trace.jsonl", RUN / "structure_audit.json"
    output_paths = (fluid_out, fluid_err, structure_out, structure_err, trace, audit,
                    RUN / "runtime_identity.json", RUN / "process_cleanup.json",
                    RUN / "launch_started.json", RUN / "diagnostic_run_summary.json")
    if any(path.exists() for path in output_paths):
        raise RuntimeError("refusing to overwrite prior runtime evidence")
    json_write(RUN / "runtime_identity.json", identity, exclusive=True)
    marker = {"started_unix": time.time(), "run_dir": str(RUN),
              "fluid_command": ["pimpleFoam", "-case", str(CASE)],
              "structure_command": ["/usr/bin/python3.10", str(PARTICIPANT),
                  "--case", str(CASE), "--run", "--worker", str(WORKER),
                  "--max-windows", "25", "--audit-output", str(audit), "--trace-output", str(trace)],
              "hard_bounds": {"max_wall_time_s": TIMEOUT_S, "windows": 1, "attempts": 2}}
    json_write(RUN / "launch_started.json", marker, exclusive=True)
    fluid_script = ("set +u; source /opt/openfoam10/etc/bashrc >/dev/null; set -u; "
                    "export PHASE1K18_DIAG_DIR=\"$2\"; exec pimpleFoam -case \"$1\"")
    fluid_command = ["bash", "-c", fluid_script, "phase1k18-fluid", str(CASE), str(DIAG)]
    structure_command = ["/usr/bin/python3.10", str(PARTICIPANT), "--case", str(CASE),
                         "--run", "--worker", str(WORKER), "--max-windows", "25",
                         "--audit-output", str(audit), "--trace-output", str(trace)]
    fluid_env, structure_env = os.environ.copy(), os.environ.copy()
    fluid_env["LD_LIBRARY_PATH"] = f"{ADAPTER.parent}:{RBF.parent}:" + fluid_env.get("LD_LIBRARY_PATH", "")
    structure_env["PYTHONUNBUFFERED"] = "1"
    processes: dict[str, subprocess.Popen] = {}
    seen_descendants: set[int] = set()
    maps: dict[str, dict[str, list[str]]] = {"Fluid": {}, "Structure": {}}
    cleanup: dict[str, object] = {"started_unix": marker["started_unix"], "processes": {},
        "descendant_pids": [], "loaded_library_maps": maps, "timed_out": False, "hard_stop_reason": None}
    start = time.monotonic()
    with fluid_out.open("xb") as fo, fluid_err.open("xb") as fe, \
         structure_out.open("xb") as so, structure_err.open("xb") as se:
        processes["Fluid"] = subprocess.Popen(fluid_command, stdout=fo, stderr=fe,
                                               env=fluid_env, start_new_session=True)
        processes["Structure"] = subprocess.Popen(structure_command, stdout=so, stderr=se,
                                                   env=structure_env, start_new_session=True)
        cleanup["processes"] = {name: {"pid": proc.pid} for name, proc in processes.items()}
        reason = None
        while any(proc.poll() is None for proc in processes.values()):
            for name, proc in processes.items():
                if proc.poll() is not None and proc.returncode not in (0, None):
                    reason = f"{name} exited nonzero ({proc.returncode})"
                    break
                if proc.poll() is None:
                    children = descendants(proc.pid)
                    seen_descendants.update(children)
                    for pid in [proc.pid, *children]:
                        maps[name][str(pid)] = maps_for(pid)
            if reason:
                break
            if len(list(DIAG.glob("S1_after_rollback_restore_retry_*.json"))) > 1:
                reason = "second retry/rollback snapshot observed"
                break
            if trace.exists() and sum(1 for line in trace.open(encoding="utf-8") if line.strip()) > 2:
                reason = "third Structure attempt observed"
                break
            times = numeric_time_dirs()
            if any(value > 30.0002000001 for value, _ in times):
                reason = f"OpenFOAM advanced past the one-window endpoint: {times}"
                break
            for log_path in (fluid_out, fluid_err, structure_out, structure_err):
                if log_path.exists():
                    tail = log_path.read_bytes()[-65536:].decode(errors="replace")
                    if re.search(r"FOAM FATAL|SIGFPE|Floating point exception|NaN detected|\bNaN\b|\bInf\b",
                                 tail, re.IGNORECASE):
                        reason = f"fatal/non-finite marker in {log_path.name}"
                        break
            if reason:
                break
            if time.monotonic() - start > TIMEOUT_S:
                cleanup["timed_out"] = True
                reason = f"hard wall-time limit {TIMEOUT_S}s exceeded"
                break
            time.sleep(0.15)

        cleanup["hard_stop_reason"] = reason
        for name, proc in processes.items():
            if reason:
                cleanup["processes"][name].update(stop_group(proc, reason))
            else:
                cleanup["processes"][name]["exit_code"] = proc.wait()
                cleanup["processes"][name]["signal_sent"] = None
    cleanup["elapsed_wall_s"] = time.monotonic() - start
    cleanup["descendant_pids"] = sorted(seen_descendants)
    cleanup["finished_unix"] = time.time()
    json_write(RUN / "process_cleanup.json", cleanup, exclusive=True)
    rows = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines() if line.strip()] if trace.exists() else []
    rollback_count = len(list(DIAG.glob("S1_after_rollback_restore_retry_*.json")))
    exits_ok = all(entry.get("exit_code") == 0 for entry in cleanup["processes"].values())
    passed = not reason and exits_ok and len(rows) == 2 and rollback_count == 1
    return {"classification": "ONE_WINDOW_ONE_RETRY_CAPTURED" if passed else "DIAGNOSTIC_RUN_INCOMPLETE",
            "completed_structure_attempts": len(rows), "rollback_snapshots": rollback_count,
            "trace_path": str(trace) if trace.exists() else None,
            "diagnostic_snapshot_count": len(list(DIAG.glob("*.json"))),
            "window_cap": 1, "iteration_cap": 2, "hard_stop_reason": reason,
            "process_exit_codes": {key: value.get("exit_code") for key, value in cleanup["processes"].items()},
            "elapsed_wall_s": cleanup["elapsed_wall_s"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--run", action="store_true", help="consume the one authorized diagnostic run")
    args = parser.parse_args()
    try:
        identity = preflight()
        json_write(RUN / "preflight.json",
                   {"classification": "PASS_PREFLIGHT_ONLY", "recorded_unix": time.time(),
                    "identity": identity})
        print("PASS_PREFLIGHT_ONLY")
        if args.preflight_only:
            return 0
        result = execute(identity)
        json_write(RUN / "diagnostic_run_summary.json", result, exclusive=True)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["classification"] == "ONE_WINDOW_ONE_RETRY_CAPTURED" else 3
    except Exception as error:
        print(f"PRE_RUN_BLOCKED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
