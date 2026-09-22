# HH06 Case 1 single-slice case snapshot

Source runtime: `/home/machao/OpenFOAM/coupling/singal_slice/slice0000`.

Included:

- the `30/` fixed-cylinder restart fields;
- `constant/` and `system/` setup;
- HH06 structure, mapping and interface contracts;
- `precice-config.xml`, `launch.sh`, and source/pre-run manifests as historical setup.

Excluded:

- logs and profiling output;
- preCICE sockets;
- worker/adapter binaries;
- post-processing and later runtime directories.

The case is a frozen configuration snapshot, not a claim of production readiness.
The historical 25-window qualification remains `DO_NOT_PASS` because of late-window
ALE/flow/turbulence runaway. The copied `launch.sh` must not be executed until the
known retry/displacement-writeback defect and source/binary lineage are re-qualified.
