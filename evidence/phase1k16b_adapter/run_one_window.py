#!/usr/bin/python3.10
"""Single-use experimental one-window launch; only scratch inputs are accepted."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "evidence/phase1k16b_adapter/lib/libpreciceAdapterPhase1K16.so"
ADAPTER_SHA = "3a655c3348f7ec682f25c5092bedf2df6e0f9ab79492b6207d6ceb90a66555ee"
QUALIFIED = Path("/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so")
QUALIFIED_SHA = "26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572"
WORKER = ROOT / "build/phase1d6_worker/cfd_ancf_ancf_kernel_worker"
WORKER_SHA = "3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596"
RBF = ROOT / "evidence/phase1k13b_rbf_diag/build-20260924T105315Z-c2245ff/lib/libRBFMeshMotionSolverPhase1K13Diag.so"
RBF_SHA = "4a739721bfaa4734151e79bca285545d6934b2f5a9450080a5e833542a4c84ee"
PARTICIPANT = ROOT / "src/coupling/hh06_structure_0000/structure_0000_participant.py"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    run = Path(sys.argv[1]).resolve()
    case = run / "case"
    marker = run / "launch_started.json"
    if marker.exists():
        raise SystemExit("one-window run already launched; refusing second attempt")
    if not case.is_dir():
        raise SystemExit("scratch case missing")
    for path, expected in ((ADAPTER, ADAPTER_SHA), (QUALIFIED, QUALIFIED_SHA),
                           (WORKER, WORKER_SHA), (RBF, RBF_SHA)):
        if sha(path) != expected:
            raise SystemExit(f"identity mismatch: {path}")
    xml = (case / "precice-config.xml").read_text()
    tree = ET.fromstring(xml)
    caps = tree.findall(".//max-time-windows")
    if len(caps) != 1 or caps[0].get("value") != "1":
        raise SystemExit("preCICE physical-window bound is not exactly one")
    if str(ADAPTER) not in (case / "system/controlDict").read_text():
        raise SystemExit("scratch controlDict does not name experimental adapter")
    if str(RBF) not in (case / "constant/dynamicMeshDict").read_text():
        raise SystemExit("scratch dynamicMeshDict does not name diagnostic RBF")
    validator = subprocess.run(["precice-config-validate", str(case / "precice-config.xml")],
                               capture_output=True, text=True, timeout=30)
    if validator.returncode:
        raise SystemExit("XML validation failed: " + validator.stderr)
    marker.write_text(json.dumps({"timestamp_unix": time.time(), "case": str(case),
                                  "adapter_sha256": ADAPTER_SHA}) + "\n")

    fluid_command = ["/bin/bash", "-lc", "source /opt/openfoam10/etc/bashrc && exec pimpleFoam -case \"$1\"",
                     "phase1k16b-fluid", str(case)]
    structure_command = ["/usr/bin/python3.10", str(PARTICIPANT), "--case", str(case),
                         "--run", "--worker", str(WORKER), "--max-windows", "25",
                         "--trace-output", str(run / "structure_trace.jsonl"),
                         "--audit-output", str(run / "structure_audit_live.json")]
    processes = {}
    handles = []
    for role, command in (("fluid", fluid_command), ("structure", structure_command)):
        out = (run / f"{role}.stdout").open("w")
        err = (run / f"{role}.stderr").open("w")
        handles.extend((out, err))
        processes[role] = subprocess.Popen(command, cwd=case, stdout=out, stderr=err,
                                           start_new_session=True)
    paths_seen = set()
    worker_pids = set()
    timed_out = False
    stop_reason = None
    deadline = time.monotonic() + 180
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
                stop_reason = "180-second hard timeout"
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
              "timed_out": timed_out, "stop_reason": stop_reason}
    (run / "process_cleanup.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if any(p.returncode != 0 for p in processes.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
