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
ALE/flow/turbulence runaway. The current launcher exposes only the separately
authorized Phase 1I profile: exactly 25 windows with the frozen IQN-ILS settings,
after a clean-tree identity preflight. This authorization is not HH06 validation
or production readiness.
