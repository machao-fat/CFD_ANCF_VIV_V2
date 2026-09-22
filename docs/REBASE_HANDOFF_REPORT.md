# PROJECT REBASE / CLEAN REPOSITORY HANDOFF

## Date and scope

This handoff was performed on 2026-09-23. The old Windows repository was treated as
legacy/forensic history. No old branch was merged, rebased, cleaned, force-pushed or
modified. The new repository was created from an empty directory in the WSL Linux
filesystem:

```text
/home/machao/projects/CFD_ANCF_VIV_V2
```

## Frozen source lineages

| purpose | source |
|---|---|
| ANCF + SHM1 capability | `machao-fat/CFD_ANCF_VIV`, branch `feature/ancf-spanwise-hydro-matrix-v1`, commit `355640e11925b9feddd1a52bb3d93596e5ee8251` |
| HH06 coupling development/history | `machao-fat/CFD_ANCF_VIV`, branch `validation/g1-terminal-diagnostic-serialization-repair-v1`, commit `ea7909748da5d6be399abedaa405a0df549360d5` |
| actual HH06 case snapshot | `/home/machao/OpenFOAM/coupling/singal_slice/slice0000` |
| fixed-cylinder parent snapshot | `/home/machao/OpenFOAM/CFD_turbulent` |

No “latest filename” selection was used.

## Migrated content

- `src/ancf/`: the authoritative C++ persistent ANCF worker/kernel/protocol source
  extracted from the 355640e1 capability baseline;
- `src/ancf_matlab/`: MATLAB reference implementation;
- `src/coupling/`: checkpoint, mapping, coordinator, preCICE and HH06 wrapper layers;
- `src/openfoam_adapter/`: OpenFOAM motion source snapshot, explicitly marked
  unqualified for production;
- `cases/cfd_fixed_cylinder_re7622/`: `0/`, `constant/`, `system/` only;
- `cases/hh06_single_slice/`: `30/`, `constant/`, `system/`, contracts and frozen
  setup manifests;
- `evidence/ancf_validation/`: MATLAB/C++ and ANCF baseline artifacts;
- `evidence/legacy_qualification/`: HH06 reports and historical qualification evidence;
- `tests/`, `scripts/`, and the permanent project contracts under `docs/`.

## Deliberately excluded

No OpenFOAM processor directories, post-processing data, logs, profiling output,
preCICE sockets, core dumps, worker/adapter binaries, build outputs, caches or runtime
checkpoint directories were copied. The 30 s restart fields are the only retained
runtime state because they are part of the frozen HH06 case snapshot.

## Migration-only adaptations

The ANCF capability source expected the physics-ownership helper beside the historical
`cpp_worker_persistent_ipc_v1` directory. In V2 it lives in `src/cpp_physics_ownership_v1`
and two include paths were changed to `../ancf/ancf_kernel.hpp`; no numerical source
implementation was changed. The CMake migration disables only an unused-function
warning for optional physics-ownership helper targets.

## Offline checks performed

- WSL environment recorded in `docs/SOFTWARE_BASELINE.md`;
- Python source compilation: PASS;
- CMake configure: PASS;
- CMake build of ANCF worker and self-test targets: PASS;
- ANCF kernel, SHM1 matrix/model/state, dense solver and physics-ownership self-tests:
  PASS;
- `ctest`: no tests were registered in the extracted historical CMake project;
- pytest: not installed in the WSL environment, so no pytest claim is made.

These are offline checks only. No OpenFOAM, preCICE initialize/handshake, ANCF physical
time advance, or FSI run was started.

## Current handoff gate

The V2 repository is a clean source/evidence handoff, not a production-FSI release.
The HH06 25-window qualification remains `DO_NOT_PASS` with
`LATE_WINDOW_ALE_FLOW_TURBULENCE_RUNAWAY`. The worker lineage repair remains
`PASS_ISOLATED_ONLY` and must be source/binary re-qualified before deployment.

## Remote status

`gh` was not installed/authenticated in WSL during handoff. The local repository and
commits are therefore authoritative until a GitHub private remote is created by an
authenticated user. No credentials were guessed or stored.
