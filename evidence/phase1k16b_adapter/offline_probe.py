#!/usr/bin/python3.10
"""Two fake preCICE participants; no OpenFOAM, ANCF, or HH06 runtime.

This verifies the preCICE read-time contract used by the experimental adapter.
It does not itself load the OpenFOAM adapter library.
"""

import json
import subprocess
import sys
from pathlib import Path

import precice


DT = 0.1


def structure(config):
    p = precice.Participant("Structure", str(config), 0, 1)
    vertices = p.set_mesh_vertices("Structure-Mesh", [[0.5, 0.5]])
    assert p.requires_initial_data()
    p.write_data("Structure-Mesh", "Displacement", vertices, [[0.0, 0.0]])
    p.initialize()
    attempts = 0
    while p.is_coupling_ongoing():
        p.requires_writing_checkpoint()
        attempts += 1
        value = attempts * 0.1
        p.write_data("Structure-Mesh", "Displacement", vertices, [[value, -value]])
        p.advance(DT)
        p.requires_reading_checkpoint()
    p.finalize()
    print("PROBE_JSON " + json.dumps({"role": "Structure", "attempts": attempts}), flush=True)


def fluid(config):
    p = precice.Participant("Fluid", str(config), 0, 1)
    vertices = p.set_mesh_vertices("Fluid-Mesh", [[0.5, 0.5]])
    assert p.requires_initial_data()
    p.write_data("Fluid-Mesh", "Force", vertices, [[1.0, 0.0]])
    p.initialize()
    initial = p.read_data("Fluid-Mesh", "Displacement", vertices, 0.0).tolist()[0]
    records = []
    attempt = 0
    while p.is_coupling_ongoing():
        p.requires_writing_checkpoint()
        attempt += 1
        p.write_data("Fluid-Mesh", "Force", vertices, [[1.0 + attempt, 0.0]])
        p.advance(DT)
        retry = bool(p.requires_reading_checkpoint())
        start = p.read_data("Fluid-Mesh", "Displacement", vertices, 0.0).tolist()[0]
        endpoint = (
            p.read_data("Fluid-Mesh", "Displacement", vertices, DT).tolist()[0]
            if retry else None
        )
        records.append({"attempt": attempt, "retry": retry, "start": start,
                        "endpoint": endpoint, "selected_offset": DT if retry else 0.0,
                        "selected": endpoint if retry else start})
    p.finalize()
    print("PROBE_JSON " + json.dumps({"role": "Fluid", "initial": initial,
                                      "records": records}), flush=True)


def config_text(socket_dir):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<precice-configuration xmlns:data="http://www.precice.org/schemas/data"
 xmlns:m2n="http://www.precice.org/schemas/m2n"
 xmlns:coupling-scheme="http://www.precice.org/schemas/coupling-scheme"
 xmlns:mapping="http://www.precice.org/schemas/mapping">
 <data:vector name="Displacement" waveform-degree="0"/>
 <data:vector name="Force" waveform-degree="0"/>
 <mesh name="Structure-Mesh" dimensions="2"><use-data name="Displacement"/><use-data name="Force"/></mesh>
 <mesh name="Fluid-Mesh" dimensions="2"><use-data name="Displacement"/><use-data name="Force"/></mesh>
 <m2n:sockets acceptor="Structure" connector="Fluid" exchange-directory="{socket_dir}"/>
 <participant name="Structure"><provide-mesh name="Structure-Mesh"/>
  <write-data name="Displacement" mesh="Structure-Mesh"/><read-data name="Force" mesh="Structure-Mesh"/></participant>
 <participant name="Fluid"><receive-mesh name="Structure-Mesh" from="Structure"/><provide-mesh name="Fluid-Mesh"/>
  <mapping:nearest-neighbor direction="read" from="Structure-Mesh" to="Fluid-Mesh" constraint="consistent"/>
  <mapping:nearest-neighbor direction="write" from="Fluid-Mesh" to="Structure-Mesh" constraint="conservative"/>
  <write-data name="Force" mesh="Fluid-Mesh"/><read-data name="Displacement" mesh="Fluid-Mesh"/></participant>
 <coupling-scheme:parallel-implicit><participants first="Structure" second="Fluid"/>
  <max-time-windows value="2"/><time-window-size value="0.1"/>
  <min-iterations value="2"/><max-iterations value="3"/>
  <absolute-convergence-measure data="Displacement" mesh="Structure-Mesh" limit="1e-12"/>
  <exchange data="Displacement" mesh="Structure-Mesh" from="Structure" to="Fluid" initialize="yes" substeps="false"/>
  <exchange data="Force" mesh="Structure-Mesh" from="Fluid" to="Structure" initialize="yes" substeps="false"/>
 </coupling-scheme:parallel-implicit>
</precice-configuration>
'''


def main():
    scratch = Path(sys.argv[1]).resolve()
    if scratch.exists():
        raise SystemExit(f"scratch already exists: {scratch}")
    scratch.mkdir(parents=True)
    sockets = scratch / "sockets"
    sockets.mkdir()
    config = scratch / "precice-config.xml"
    config.write_text(config_text(sockets), encoding="utf-8")
    validation = subprocess.run(["precice-config-validate", str(config)],
                                capture_output=True, text=True, timeout=30)
    (scratch / "validation.log").write_text(validation.stdout + validation.stderr)
    if validation.returncode:
        raise SystemExit(f"config validation failed: {validation.returncode}")
    processes = {}
    for role in ("Structure", "Fluid"):
        processes[role] = subprocess.Popen([sys.executable, __file__, role, str(config)],
                                          cwd=scratch, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True,
                                          start_new_session=True)
    observations = {}
    for role, process in processes.items():
        try:
            stdout, stderr = process.communicate(timeout=45)
        except subprocess.TimeoutExpired:
            for other in processes.values():
                if other.poll() is None:
                    other.kill()
            raise
        (scratch / f"{role.lower()}.stdout").write_text(stdout)
        (scratch / f"{role.lower()}.stderr").write_text(stderr)
        if process.returncode:
            raise SystemExit(f"{role} exited {process.returncode}: {stderr[-2000:]}")
        observations[role] = json.loads(next(line.split("PROBE_JSON ", 1)[1]
                                           for line in stdout.splitlines()
                                           if line.startswith("PROBE_JSON ")))
    records = observations["Fluid"]["records"]
    assert observations["Fluid"]["initial"] == [0.0, 0.0]
    assert observations["Structure"]["attempts"] == len(records)
    assert len(records) >= 4, records
    assert any(row["retry"] and row["endpoint"] != row["start"] for row in records)
    assert any(not row["retry"] and row["selected_offset"] == 0.0 for row in records)
    assert all((row["selected"] == row["endpoint"] if row["retry"]
                else row["selected"] == row["start"]) for row in records)
    (scratch / "result.json").write_text(json.dumps(observations, indent=2) + "\n")
    print(json.dumps({"result": "PASS", "attempts": len(records), "fluid": records}, indent=2))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in ("Structure", "Fluid"):
        globals()[sys.argv[1].lower()](Path(sys.argv[2]))
    else:
        main()
