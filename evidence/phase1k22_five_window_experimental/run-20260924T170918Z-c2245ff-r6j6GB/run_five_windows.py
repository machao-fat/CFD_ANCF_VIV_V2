#!/usr/bin/python3.10
"""Single-use Phase 1K.22 five-window experimental checkpoint runner."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[2]
ADAPTER = ROOT / "evidence/phase1k20_point_checkpoint/run-20260924T164027Z-c2245ff-Gu2Hg5/build/libpreciceAdapterPhase1K20.so"
ADAPTER_SHA = "225ecab227b8271f01119fe476370e3a0b705ca06e1ca3a7739200266499b165"
QUALIFIED = Path("/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so")
QUALIFIED_SHA = "26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572"
WORKER = ROOT / "build/phase1d6_worker/cfd_ancf_ancf_kernel_worker"
WORKER_SHA = "3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596"
RBF = ROOT / "evidence/phase1k20_point_checkpoint/run-20260924T164027Z-c2245ff-Gu2Hg5/build/libRBFMeshMotionSolverPhase1K187BStopDiag.so"
RBF_SHA = "508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11"
PARTICIPANT = RUN / "participant_trace.py"
FROZEN = ROOT / "evidence/phase1k10_new_mesh_restart/run-20260924T085251Z-c2245ff/mapped_candidate_30"
REFERENCE_XML = ROOT / "evidence/phase1k18_7a_nonzero_checkpoint/run-20260924T144540Z-c2245ff/case/precice-config.xml"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    preflight_only = len(sys.argv) == 3 and sys.argv[1] == "--preflight-only"
    run_argument = sys.argv[2] if preflight_only else sys.argv[1]
    run = Path(run_argument).resolve()
    if run != RUN.resolve():
        raise SystemExit("run directory differs from the single authorized Phase 1K.22 attempt")
    case = run / "case"
    marker = run / "launch_started.json"
    if marker.exists():
        raise SystemExit("five-window run already launched; refusing a second attempt")
    if not case.is_dir():
        raise SystemExit("scratch case missing")
    for relative in ("30/uniform/time", "30/U", "30/p", "30/k", "30/omega",
                     "30/nut", "30/pointDisplacement", "constant/polyMesh/points",
                     "constant/polyMesh/faces", "constant/polyMesh/owner",
                     "constant/polyMesh/neighbour", "constant/polyMesh/boundary"):
        if sha(case / relative) != sha(FROZEN / relative):
            raise SystemExit(f"restart/mesh hash mismatch: {relative}")
    if any(child.is_dir() and child.name not in ("30", "constant", "system")
           and child.name.replace(".", "", 1).isdigit() for child in case.iterdir()):
        raise SystemExit("scratch case already has an advanced time directory")
    for path, expected in ((ADAPTER, ADAPTER_SHA), (QUALIFIED, QUALIFIED_SHA),
                           (WORKER, WORKER_SHA), (RBF, RBF_SHA)):
        if sha(path) != expected:
            raise SystemExit(f"identity mismatch: {path}")
    xml = (case / "precice-config.xml").read_text()
    tree = ET.fromstring(xml)
    caps = tree.findall(".//max-time-windows")
    if len(caps) != 1 or caps[0].get("value") != "5":
        raise SystemExit("preCICE physical-window bound is not exactly five")
    windows = tree.findall(".//time-window-size")
    max_iters = tree.findall(".//max-iterations")
    min_iters = tree.findall(".//min-iterations")
    if len(windows) != 1 or windows[0].get("value") != "0.0002":
        raise SystemExit("coupling dt/window size changed")
    if len(max_iters) != 1 or max_iters[0].get("value") != "20":
        raise SystemExit("implicit iteration cap changed")
    if len(min_iters) != 1 or min_iters[0].get("value") != "2":
        raise SystemExit("minimum iteration count changed")
    socket_dir = run / "precice-sockets"
    expected_tree = ET.fromstring(REFERENCE_XML.read_text())
    expected_socket = expected_tree.findall(".//{http://www.precice.org/schemas/m2n}sockets")
    current_socket = tree.findall(".//{http://www.precice.org/schemas/m2n}sockets")
    if len(expected_socket) != 1 or len(current_socket) != 1:
        raise SystemExit("preCICE socket node missing or repeated")
    if current_socket[0].get("exchange-directory") != str(socket_dir):
        raise SystemExit("scratch socket path does not match this run")
    current_socket[0].set("exchange-directory", expected_socket[0].get("exchange-directory"))
    caps[0].set("value", "1")
    if ET.tostring(tree) != ET.tostring(expected_tree):
        raise SystemExit("scratch XML differs from frozen IQN coupling config beyond window/socket edits")
    if socket_dir.is_symlink() or (socket_dir.exists() and any(socket_dir.iterdir())):
        raise SystemExit("socket directory is symlinked or contains stale state")
    if str(ADAPTER) not in (case / "system/controlDict").read_text():
        raise SystemExit("scratch controlDict does not name experimental adapter")
    if str(RBF) not in (case / "constant/dynamicMeshDict").read_text():
        raise SystemExit("scratch dynamicMeshDict does not name diagnostic RBF")
    if json.loads((case / "contract.json").read_text())["execution_authorization"]["adapter_runtime_sha256"] != ADAPTER_SHA:
        raise SystemExit("scratch adapter contract SHA mismatch")
    if json.loads((case / "contract.json").read_text())["execution_authorization"]["max_windows"] != 5:
        raise SystemExit("scratch execution authorization is not exactly five windows")
    if not (run / "diagnostics").is_dir() or any((run / "diagnostics").iterdir()):
        raise SystemExit("diagnostic directory is not an empty fresh directory")
    if not PARTICIPANT.is_file():
        raise SystemExit("diagnostic Structure participant missing")
    audit = subprocess.run(["/usr/bin/python3.10", str(PARTICIPANT), "--case", str(case), "--audit-only"],
                           cwd=case, capture_output=True, text=True, timeout=30)
    if audit.returncode or '"status": "PASS"' not in audit.stdout:
        raise SystemExit("diagnostic Structure participant audit failed: " + audit.stdout[-2000:])
    limit_check = subprocess.run(
        ["/usr/bin/python3.10", "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); import participant_trace as p; "
         "bundle=p.load_contract_bundle(sys.argv[2]); "
         "assert p._bounded_window_limit(bundle, 5) == 5",
         str(run), str(case)], cwd=case, capture_output=True, text=True, timeout=30)
    if limit_check.returncode:
        raise SystemExit("diagnostic Structure runtime five-window guard failed: " + limit_check.stderr[-2000:])
    validator = subprocess.run(["precice-config-validate", str(case / "precice-config.xml")],
                               capture_output=True, text=True, timeout=30)
    if validator.returncode:
        raise SystemExit("XML validation failed: " + validator.stderr)
    if preflight_only:
        print(json.dumps({"result": "PASS_PREFLIGHT_ONLY",
                          "physical_window_cap": 5,
                          "dt_s": 0.0002,
                          "max_iterations": 20,
                          "xml_sha256": sha(case / "precice-config.xml"),
                          "adapter_sha256": ADAPTER_SHA,
                          "worker_sha256": WORKER_SHA,
                          "rbf_sha256": RBF_SHA}, indent=2))
        return
    socket_dir.mkdir(exist_ok=True)
    marker.write_text(json.dumps({"timestamp_unix": time.time(), "case": str(case),
                                  "adapter_sha256": ADAPTER_SHA,
                                  "physical_window_cap_xml": 5,
                                  "xml_sha256": sha(case / "precice-config.xml"),
                                  "worker_sha256": WORKER_SHA,
                                  "rbf_sha256": RBF_SHA}) + "\n")

    fluid_command = ["/bin/bash", "-c", "set +u; source /opt/openfoam10/etc/bashrc >/dev/null; "
                     "cd \"$1\" || exit 91; test \"$(pwd -P)\" = \"$(realpath \"$1\")\" || exit 92; "
                     "printf 'PHASE1K22_FLUID_PWD=%s\\n' \"$(pwd -P)\"; exec pimpleFoam -case .",
                     "phase1k22-fluid", str(case)]
    structure_command = ["/usr/bin/python3.10", str(PARTICIPANT), "--case", str(case),
                         "--run", "--worker", str(WORKER), "--max-windows", "5",
                         "--trace-output", str(run / "structure_trace.jsonl"),
                         "--audit-output", str(run / "structure_audit_live.json")]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PHASE1K18_DIAG_DIR"] = str(run / "diagnostics")
    env["PHASE1K18_7B_ANCF_TRACE"] = str(run / "ancf_checkpoint_stages.jsonl")
    env["PHASE1K18_7B_PRE_ADVANCE_TRACE"] = str(run / "pre_advance_attempts.jsonl")
    env.pop("PHASE1K18_7B_STOP_AFTER_RETRY_S5", None)
    processes = {}
    handles = []
    wall_start_unix_s = time.time()
    wall_start_monotonic_s = time.monotonic()
    for role, command in (("fluid", fluid_command), ("structure", structure_command)):
        out = (run / f"{role}.stdout").open("x")
        err = (run / f"{role}.stderr").open("x")
        handles.extend((out, err))
        processes[role] = subprocess.Popen(command, cwd=case, env=env, stdout=out, stderr=err,
                                           start_new_session=True)
    paths_seen = set()
    worker_pids = set()
    timed_out = False
    stop_reason = None
    deadline = time.monotonic() + 600
    try:
        while any(p.poll() is None for p in processes.values()):
            fluid_pid = processes["fluid"].pid
            maps = Path(f"/proc/{fluid_pid}/maps")
            if maps.exists():
                for line in maps.read_text().splitlines():
                    if "libpreciceAdapter" in line or "libRBFMeshMotionSolver" in line:
                        paths_seen.add(line.split()[-1])
            structure_pid = processes["structure"].pid
            children = Path(f"/proc/{structure_pid}/task/{structure_pid}/children")
            if children.exists():
                worker_pids.update(children.read_text().split())
            if time.monotonic() > deadline:
                timed_out = True
                stop_reason = "600-second hard timeout"
                break
            failed = [role for role, p in processes.items() if p.poll() not in (None, 0)]
            if failed:
                stop_reason = "participant exited nonzero: " + ",".join(failed)
                break
            time.sleep(0.1)
        if stop_reason:
            for p in processes.values():
                if p.poll() is None:
                    p.terminate()
            time.sleep(2)
            for p in processes.values():
                if p.poll() is None:
                    p.kill()
    finally:
        for p in processes.values():
            p.wait(timeout=10)
        for handle in handles:
            handle.close()
    result = {"fluid_command": fluid_command, "structure_command": structure_command,
              "fluid_pid": processes["fluid"].pid,
              "structure_pid": processes["structure"].pid,
              "observed_worker_pids": sorted(worker_pids),
              "loaded_libraries_observed": sorted(paths_seen),
              "exit_codes": {role: p.returncode for role, p in processes.items()},
              "timed_out": timed_out, "stop_reason": stop_reason,
              "wall_start_unix_s": wall_start_unix_s,
              "wall_end_unix_s": time.time(),
              "wall_duration_s": time.monotonic() - wall_start_monotonic_s}
    (run / "process_cleanup.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if any(p.returncode != 0 for p in processes.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
