# Phase 1D — Strategy C Implementation and Offline Qualification

**Classification:** `PASS_OFFLINE_STRATEGY_C`
**Branch:** `repair/worker-lineage-implicit-contract-v1`
**HEAD:** `8550e6a4cd7fb62c0f8b49471a704604965a7ff6` (unchanged; Phase 1D changes are uncommitted)
**Runtime boundary:** no real OpenFOAM solve, preCICE participant run, or HH06 FSI was started.

## Result and scope

The approved participant-side Strategy C / Strategy B lifecycle is implemented
and passed the deterministic offline qualification. Each attempt now solves ANCF
from the active physical-window checkpoint, scatters the absolute trial
displacement, writes that exact value to preCICE, advances, and then either
rolls back physical ANCF state or commits the accepted trial. Force and trial
history survive retry in participant-owned `CouplingIterationState`; physical
ANCF state remains owned by `GenericStructuralCoordinator`; transport identity
remains owned by the persistent worker.

The result is an offline coupling-contract PASS only. It does not establish real
preCICE convergence, HH06 stability, VIV reproduction, or removal of the
historical late-window ALE/flow/turbulence runaway.

## Changed files

Production/configuration:

- `src/coupling/hh06_structure_0000/structure_0000_participant.py`
- `cases/hh06_single_slice/contract.json`
- `cases/hh06_single_slice/precice-config.xml`
- `cases/hh06_single_slice/launch.sh`
- `cases/hh06_single_slice/preflight_adapter_sha.sh`

Tests and evidence:

- `tests/coupling/test_implicit_iteration_trace.py`
- `tests/coupling/test_adapter_runtime_pin.py`
- `tests/coupling/test_worker_transport_regression.py`
- `evidence/phase1d_offline_qualification/implicit_fixed_point_trace.jsonl`
- `evidence/phase1d_offline_qualification/iteration_cap_trace.jsonl`
- `evidence/phase1d_offline_qualification/physical_f0_seed_trace.jsonl`
- `evidence/phase1d_offline_qualification/worker_transport_qualification.json`
- `evidence/phase1d_offline_qualification/qualification_summary.json`

Project records:

- `docs/COUPLING_CONTRACT.md`
- `docs/KNOWN_ISSUES.md`
- `docs/VALIDATION_LEDGER.md`
- `docs/PHASE1D_STRATEGY_C_IMPLEMENTATION_REPORT.md`

SHA256 identities for changed source/config/test inputs at qualification:

| file | SHA256 |
|---|---|
| `src/coupling/hh06_structure_0000/structure_0000_participant.py` | `b5c8c30e8634f00fa4a03c05ecf55beecbe5f6ca1ddeda22bd28ee137f41dc8a` |
| `src/ancf/ancf_worker_main.cpp` (unchanged) | `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e` |
| `cases/hh06_single_slice/contract.json` | `80f270e7cf3eeac46e62963d8a6a56b603b91763e47c36a2e9ae17746a6cf87c` |
| `cases/hh06_single_slice/precice-config.xml` | `6b282ec8db4bdfb67a03c23c86f8ecb26835500fe512f2546616f1602db70219` |
| `cases/hh06_single_slice/launch.sh` | `d8ab79614321311c785b36608fb8a814a92f21028b9e9508972cbfbc607f8157` |
| `cases/hh06_single_slice/preflight_adapter_sha.sh` | `8142e6e69b3078b7972d6a7cb5453aa34a8b8c8fc9db9cb9ddf8aa1a4eb78eac` |
| `tests/coupling/test_implicit_iteration_trace.py` | `fa545e43826466f406d78b34e46cbbb92e4175739d9b53fe786874f5754e9a7b` |
| `tests/coupling/test_adapter_runtime_pin.py` | `45bfc6699eccfd5cc135a7fddeb19336b86b0d9dc03f973173fdb5f89ca1eb06` |
| `tests/coupling/test_worker_transport_regression.py` | `607d13f26ae0200404f110fef44b4a0b13f7fe2a31362beb30172956a1bf8069` |

No changes were made to `ancf_worker_main.cpp`, ANCF equations/kernel,
SHM1/DMP1 serialization, `GenericStructuralCoordinator`, the preCICE backend,
the OpenFOAM adapter source, or CFD/structural physical parameters.

## Before and after lifecycle

Previously, the participant wrote `committed_motion`, advanced preCICE, read
Force, solved ANCF, and then rolled back the physical trial. This meant that a
new ANCF trial displacement was discarded before the next retry write.

The current attempt order is:

```text
initialize Structure; read initialized Force F0
for each physical window:
    create one physical ANCF checkpoint
    for each implicit attempt:
        consume the current Force iterate
        solve ANCF from the physical window checkpoint
        scatter absolute D_trial
        write exactly D_trial to preCICE
        advance(dt)
        read the resulting Force iterate
        if preCICE requests a retry:
            restore q/qdot/qddot and physical window identity
            retain Force iterate and coupling-iteration history
        else:
            commit exactly the trial written before this accepted advance
```

`D_previous_committed`, `D_trial_from_ancf`, and
`D_written_to_precice` are distinct in every JSON attempt record. A runtime
assertion checks `D_written_to_precice == D_trial_interface` before the associated
preCICE advance.

`CouplingIterationState` contains the physical window and iteration indices,
current/previous raw Force iterates, source time and source kind, current/previous
trial displacement, committed motion reference, residual history, and event
history. It contains no `q/qdot/qddot`, sequence, request ID, or transaction ID.

The participant explicitly starts the persistent worker with
`CFD_ANCF_ALLOW_IMPLICIT_RETRY=1`, because the current worker intentionally keeps
same-window implicit retries disabled by default. The worker source and its
physical/transport identity implementation are unchanged.

## Physical F0 and force units

The current contract records the raw patch-integrated force from the exact
30.0 s restart, patch `cylinder`, case ID
`ANCF_SINGLE_SLICE_HIGHRE_0P2S_PREP_V1`, time index `150000`:

```text
Fx0_raw =  0.0655270406544 N
Fy0_raw =  0.05872987413554 N
Fz0_raw = -2.44420351566e-21 N (provenance only; no Fz contract field added)
```

Frozen result JSON SHA256:
`6b272f695ebefe28daa176723483f611c42f8d25dbae8d83de928f3790811b8a`.
The recovery report SHA256 is
`6737908b9b29f4ff8550ba4353ff88ad90ad5cfc1355a57a885d655f7d3d7b3b`.
Contract loading verifies both hashes and the case/time/patch identity.

The first Force read after Structure `initialize()` is checked against the
contract within `5e-13 N` in x/y. It is traced with source global time `30.0 s`;
the first structural trial targets `30.0002 s`. Subsequent Force iterates are
tagged with the global time of their preceding preCICE advance. The existing
conversion is unchanged and applied once by `ForceSample`:

```text
F_section = F_raw / 0.028 m
F_strip   = F_section * 1.98 m
```

No release force was fabricated and no extra scaling was added.

The production Force exchange now has `initialize="yes"`. The production
`contract.json` readiness/status fields remain unchanged. The already-qualified
pre-initialize runtime evidence applies only to the adapter SHA below.

## Adapter runtime pin

The launcher sources the OpenFOAM-10 environment and runs the fail-closed
preflight before creating sockets/logs or starting either coupled participant.
The preflight resolves the library path through active OpenFOAM/library search
locations, hashes all matching candidates, and rejects a mismatch.

```text
ADAPTER_RUNTIME_BINARY_PINNED = YES
ADAPTER_SOURCE_PROVENANCE_RESOLVED = NO
qualified path = /home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so
SHA256 = 26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572
Build ID = e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b
```

The exact installed SHA passed the guard; a deliberately incorrect scratch
library failed with exit code 2 before any runtime start. The adapter source/build
lineage remains unresolved. The launcher itself was not used to start a run; its
guard ordering was checked by test and source inspection.

## Deterministic fixed-point qualification

The fake Fluid/Structure map is:

```text
F = 1 + 2 D_written
D_trial = 0.1 + 0.2 F_input
D0 = 0, F0 = 1 (explicit synthetic offline seed)
```

The first window begins:

| attempt | Force input | ANCF trial / Force written back | Force returned by fake Fluid |
|---:|---:|---:|---:|
| 1 | 1.0 | 0.3 | 1.6 |
| 2 | 1.6 | 0.42 | 1.84 |
| 3 | 1.84 | 0.468 | 1.936 |

Both Force and displacement residuals contract geometrically by `0.4`. With
the fake tolerances (`1e-7 N` Force and `1e-8 m` displacement) the first physical
window accepts by tolerance on attempt 20 of a 25-attempt fake cap. The second
window converges in 21 attempts and starts from the preceding accepted Force,
not from F0. Every one of the 41 attempts records identical trial and written
interface displacement. The cap-only non-convergent fixture stops at attempt 3
with the exact status `ACCEPTED_AT_ITERATION_LIMIT`, not `CONVERGED`.

The separate physical-F0 fake path verifies that the first ANCF solve consumes
the raw F0 read after initialization, converts it once to the strip resultant,
and distinguishes source time `30.0 s` from target time `30.0002 s`. It uses the
frozen HH06 F0 numbers as data in a fake backend; it is not a real preCICE run.

Machine traces are in `evidence/phase1d_offline_qualification/`.

## Rollback, transport, and ANCF/SHM1 regressions

The offline Structure fake and current-source C++ worker tests verify:

- rejected trial `q/qdot/qddot` restores exactly to the physical checkpoint;
- the same physical identity is used for all retries in a window;
- next-window physical step/time/tick advance exactly once with unchanged `dt`;
- C++ worker requests have sequence `1..10` across two windows with five
  attempts each; sequence 6 is accepted as window 2, not a retry of window 1;
- request IDs and transaction IDs are monotonic/unique and not rolled back;
- the actual worker rejects a duplicate request ID and duplicate transaction ID
  with protocol exit code 18;
- accepted ANCF output corresponds to the trial displacement written before
  the accepted advance;
- the existing three checkpoint lifecycle tests pass.

The C++ build and binary identity are:

```text
CMake: cmake version 3.22.1
Configuration: Release
Compiler: c++ (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0
Target: cfd_ancf_ancf_kernel_worker
Worker source SHA256: c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e
Worker binary SHA256: 3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596
Build directory: /tmp/phase1d-cmake-071hBo
```

The following six current-source C++ selftest targets built and passed:

- `cfd_ancf_ancf_kernel_selftest`
- `cfd_ancf_spanwise_hydrodynamic_matrix_selftest`
- `cfd_ancf_spanwise_hydrodynamic_model_selftest`
- `cfd_ancf_spanwise_hydrodynamic_state_selftest`
- `cfd_ancf_dense_solver_selftest`
- `cfd_ancf_physics_ownership_selftest`

The repository-wide Python `tests/ancf` suite was also attempted. It remains
blocked by the same pre-existing incomplete V2 checkout: 15 tests were reported,
16 errors arose from missing modules and result artifacts (including
`coupling.stage303_interface_mapping_repair_v1`,
`coupling.openfoam_quality_contract_v3`,
`coupling.moment_mapping_audit_v1`, and absent `results/...` JSON files), and one
test was skipped. No missing module/artifact was added or modified in this phase.
This does not invalidate the targeted participant/worker tests or the six passing
ANCF/SHM1 C++ selftests, but a suite-wide Python PASS is not claimed.

## Configuration and boundaries

The existing configuration mismatch remains visible and unchanged:

```text
contract.json coupling.max_iterations = 8
precice-config.xml max-iterations    = 20
```

The participant reports the actual XML cap and marks acceptance at the cap
conservatively. Neither cap, relaxation, convergence tolerance, timestep,
turbulence, mesh, damping, force scaling, nor physical parameters were adjusted.

Not run: real OpenFOAM, real preCICE, HH06 moving-structure runtime, 2-window
real qualification, 5-window qualification, 25-window qualification, or long
production FSI. No three-slice work was started.

## Static/source verification and Git state

- `git diff --check`: PASS.
- Python compilation and shell syntax checks: PASS.
- HH06 participant `--audit-only`: PASS; reports the `8` vs `20` iteration-cap
  mismatch without changing either value.
- No sequence-parity branch or `lineage_mode` was reintroduced; the existing
  worker source was not modified.
- `committed_motion` is written after accepted commit only; retry attempts write
  `D_trial` and preserve `committed_motion`.
- No changes in `GenericStructuralCoordinator`, the preCICE backend, or any
  OpenFOAM adapter source.
- Git HEAD remains `8550e6a4cd7fb62c0f8b49471a704604965a7ff6`; no Phase 1D commit
  was created.
- Final worktree is intentionally dirty with the Phase 1D implementation,
  documentation, tests, and evidence pending review.

Tracked diff summary at report creation: 8 tracked files changed, 787 insertions,
285 deletions. Newly created guard, tests, traces, evidence summary, and this
report are untracked and therefore are not included in `git diff --stat`.

## Phase 1D disposition

**`PASS_OFFLINE_STRATEGY_C`**. The deterministic fixed-point behavior,
participant write/advance order, F0 contract, rollback separation, transport
identity, cap honesty, adapter SHA guard, and targeted ANCF/SHM1 C++ regressions
pass offline. Stop here for review. Do not start real coupling or long FSI from
this result alone.
