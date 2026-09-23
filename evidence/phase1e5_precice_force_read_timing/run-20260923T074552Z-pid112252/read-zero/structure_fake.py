import json, sys
import precice

config, read_offset_arg = sys.argv[1], sys.argv[2]
dt = 0.1
read_offset = 0.0 if read_offset_arg == "zero" else dt
p = precice.Participant("Structure", config, 0, 1)
ids = p.set_mesh_vertices("Structure-Mesh", [[0.5, 0.5]])
if not p.requires_initial_data():
    raise RuntimeError("Structure expected initial Displacement data")
p.write_data("Structure-Mesh", "Displacement", ids, [[0.0, 0.0]])
init_dt = p.initialize()
if init_dt is not None:
    dt = float(init_dt)
if read_offset_arg == "dt":
    read_offset = dt
records = []
committed = [0.0, 0.0]
saved = committed[:]
attempt = 0
while p.is_coupling_ongoing():
    checkpoint = bool(p.requires_writing_checkpoint())
    if checkpoint:
        saved = committed[:]
    force_at_start = p.read_data("Structure-Mesh", "Force", ids, 0.0).tolist()
    force_at_end = p.read_data("Structure-Mesh", "Force", ids, dt).tolist()
    selected = force_at_start if read_offset_arg == "zero" else force_at_end
    attempt += 1
    trial = [float(attempt), -float(attempt)]
    p.write_data("Structure-Mesh", "Displacement", ids, [trial])
    p.advance(dt)
    rollback = bool(p.requires_reading_checkpoint())
    force_immediately_after_advance_at_start = p.read_data("Structure-Mesh", "Force", ids, 0.0).tolist()
    force_immediately_after_advance_at_end = (
        p.read_data("Structure-Mesh", "Force", ids, dt).tolist() if rollback else None)
    if rollback:
        committed = saved[:]
    else:
        committed = trial[:]
    records.append({"attempt": attempt, "read_offset_s": read_offset,
                    "force_at_relative_0": force_at_start,
                    "force_at_relative_dt": force_at_end,
                    "force_after_advance_relative_0": force_immediately_after_advance_at_start,
                    "force_after_advance_relative_dt": force_immediately_after_advance_at_end,
                    "force_selected_for_fake_solve": selected,
                    "trial_displacement_written": trial,
                    "checkpoint_requested": checkpoint,
                    "rollback_requested": rollback,
                    "committed_fake_state_after_advance": committed[:]})
p.finalize()
print(json.dumps({"role": "Structure", "read_mode": read_offset_arg,
                  "records": records}, sort_keys=True))
