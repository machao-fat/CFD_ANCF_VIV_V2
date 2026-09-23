import json, sys
import precice

config = sys.argv[1]
dt = 0.1
p = precice.Participant("Fluid", config, 0, 1)
ids = p.set_mesh_vertices("Fluid-Mesh", [[0.5, 0.5]])
if not p.requires_initial_data():
    raise RuntimeError("Fluid expected initial Force data")
p.write_data("Fluid-Mesh", "Force", ids, [[10.0, -10.0]])
init_dt = p.initialize()
if init_dt is not None:
    dt = float(init_dt)
records = []
attempt = 0
while p.is_coupling_ongoing():
    save = bool(p.requires_writing_checkpoint())
    attempt += 1
    force = [100.0 + attempt, -200.0 - 3.0 * attempt]
    p.write_data("Fluid-Mesh", "Force", ids, [force])
    p.advance(dt)
    retry = bool(p.requires_reading_checkpoint())
    records.append({"attempt": attempt, "force_written_before_advance": force,
                    "checkpoint_requested": save, "rollback_requested": retry})
p.finalize()
print(json.dumps({"role": "Fluid", "records": records}, sort_keys=True))
