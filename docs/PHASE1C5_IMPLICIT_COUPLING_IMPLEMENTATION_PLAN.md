# Phase 1C.5 — Implicit Coupling Repair Implementation Plan

## Status and boundary

```text
phase = 1C.5 implementation plan only
approved design = Strategy C + Strategy B state separation
production source modified in this phase = NO
OpenFOAM runtime = NOT RUN
preCICE runtime = NOT RUN
HH06 runtime = NOT RUN
```

The source map below is for the accepted Phase 1B instrumented worktree at
`7c38f61aeb27e56ae5916cc2b5e6f2bc17aa047b`. The Phase 1B participant
instrumentation and its uncommitted evidence remain untouched. Current
worktree also contains those Phase 1B changes and the accepted Phase 1C design;
this plan adds no source change.

## 1. Current code mapping

### Structure participant

| Operation | Current location | Current behavior |
|---|---|---|
| Construct worker, preCICE fleet, and coordinator | `src/coupling/hh06_structure_0000/structure_0000_participant.py:529-531` | Creates the persistent ANCF backend, `PreciceStructureFleetBackend`, and `GenericStructuralCoordinator`. |
| Initial displacement and participant initialization | `structure_0000_participant.py:536-550` | Evaluates q0 relative to the reference, then calls `fleet.initialize(initial_motion_by_slice=...)`. No initial Force is supplied here. |
| Window / iteration loop | `structure_0000_participant.py:558-581` | At each attempt, obtains checkpoint request, writes `committed_motion`, advances preCICE, reads Force, solves ANCF, scatters trial motion, then rolls back or commits. This is the stale-motion path established in the Phase 1B report. |
| Checkpoint request / creation | `structure_0000_participant.py:564-566` | Calls `requires_writing_checkpoint()` and creates one coordinator checkpoint when requested. |
| Motion write | `structure_0000_participant.py:561-567` | Builds the write vector from the previous accepted `committed_motion`, before the ANCF trial exists. |
| preCICE advance and Force read | `structure_0000_participant.py:568-571` | Calls `fleet.advance(dt)` and only then reads and converts Force. `ForceSample.iteration` is the physical window number (`accepted + 1`), not the coupling-iteration index. Preserve that physical identity. |
| ANCF solve and trial scatter | `structure_0000_participant.py:572-575` | Submits the Force sample, calls the coordinator's global solve, scatters absolute motion, and retains it locally as `trial_motion`. |
| Rollback / commit | `structure_0000_participant.py:576-581` | Checks `requires_reading_checkpoint()` after `advance`; rollback discards the physical trial, while acceptance commits the coordinator and updates `committed_motion`. |
| Trace | `structure_0000_participant.py:584-646` | Records written, trial, committed motion, force, residuals, IDs, physical identity, and checkpoint/commit decisions separately. Keep these distinctions; update event timing to match the new order. |

### `GenericStructuralCoordinator`

| Operation | Current location | Current behavior and plan |
|---|---|---|
| Force gather and request construction | `src/coupling/arbitrary_n_live_orchestration_v1/coordinator.py:387-425` | Validates one Force sample per slice and constructs one physical-window `WorkerRequest`. Retain; the participant submits the newly read Force on every attempt. |
| ANCF advance | `coordinator.py:427-435` | Runs the backend once for a complete gather and records a pending tentative physical advance. Retain. |
| Trial displacement scatter | `coordinator.py:437-451` | Evaluates the pending ANCF state and returns absolute displacement relative to the configured reference. Retain and write this exact result before preCICE `advance()`. |
| Commit | `coordinator.py:453-464` | Commits the pending backend trial, increments the accepted physical step, clears gather and checkpoint. Retain; call only after preCICE no longer requests a checkpoint. |
| Checkpoint | `coordinator.py:465-478` | Snapshots the backend physical state and coordinator physical-window metadata. Retain; do not add coupling trial/residual history or transport generators to it. |
| Rollback | `coordinator.py:480-503` | Restores backend physical state and committed step; clears gather, pending request/motion and current force metadata, but keeps the same checkpoint active. This matches the required physical rollback. |

No coordinator behavior change is currently required. Its existing API already
supports the target sequence: submit Force → advance ANCF → scatter trial →
then either rollback the physical trial or commit it. Keeping iteration history
in the participant avoids changing generic checkpoint semantics.

### preCICE backend

| Operation | Current location | Current behavior and plan |
|---|---|---|
| Initial data | `src/coupling/arbitrary_n_live_orchestration_v1/precice_backend.py:44-91` | Defines the Structure mesh; if preCICE requests initial data, writes only the supplied initial Displacement before `initialize()`. It has no Force-initialization input. |
| Write motion | `precice_backend.py:93-96` | Passes the supplied vector directly to `Participant.write_data()`. Retain. |
| Read Force | `precice_backend.py:98-102` | Calls `read_data(..., relativeReadTime=0.0)`. Retain only after confirming the input is valid at the target call site and physical time. |
| Advance | `precice_backend.py:104-107` | Pass-through to `Participant.advance(dt)`. Retain. |
| Checkpoint actions | `precice_backend.py:109-121` | Pass-through for `requires_writing_checkpoint()` and `requires_reading_checkpoint()`. Retain their pre-/post-advance positions in the participant loop. |

The source-level call sites and lifecycle agree with the accepted Phase 1B
trace report. The coordinator and backend remain behaviorally unchanged in the
base implementation plan. Any Force-seed transport extension is conditional on
resolving the gate in section 4; Force initial data, if needed, must originate
from the Fluid side, not be fabricated by the Structure backend.

## 2. Proposed state ownership

`CommittedPhysicalState` is the authoritative accepted state, not an extra
copy of worker memory. Preserve its current distributed storage to avoid two
sources of truth:

| Named state | Contents | Authoritative existing owner | Retry behavior |
|---|---|---|---|
| `CommittedPhysicalState` | `q`, `qdot`, `qddot`; `committed_motion`; accepted window/step/time | `PersistentHH06KernelBackend.q/qdot/qddot` and `committed_advance_count`; `GenericStructuralCoordinator.committed_step`; participant `committed_motion` and `accepted` count. Target time is currently derived as `(accepted + 1) * dt`; it is not a separate stored backend field. | Never overwrite with a rejected trial. The coordinator checkpoint restores the physical ANCF portion. |
| `CouplingIterationState` | window index and immutable physical identity; coupling iteration index; Force sample used by the current solve and latest Force iterate; current `D_trial`; prior trial/force values for residuals; trace/event data | New participant-loop state in `structure_0000_participant.py`, outside the coordinator/backend physical checkpoint | Survives retries as iteration history. The trial ANCF physical state is rolled back; the saved trial vector is diagnostic/residual history only and is not replayed as the next write. Reset after window acceptance. |
| `TransportSessionState` | `sequence`, `request_id`, `transaction_id` and generators | Existing `PersistentHH06KernelBackend` counters at `structure_0000_participant.py:327-349,402-421`; C++ worker validates transport IDs | Never checkpointed or rolled back. Each ANCF attempt consumes fresh monotonic identities. |

The intended implementation is one explicit `CouplingIterationState` object per
active physical window, or an equivalent tightly scoped set of fields. It must
not be put in `CouplingCheckpoint`, and it must not duplicate the authoritative
q vectors. The accepted physical state remains the logical aggregate described
above.

## 3. Proposed call-order migration

### Before

```text
if requires_writing_checkpoint():
    coordinator.checkpoint(window_id)

write_motion(committed_motion)
advance(dt)
force = read_force(relativeReadTime=0)
submit_force(force, physical_window_identity)
result = coordinator.advance_if_complete()  # ANCF trial
D_trial = coordinator.scatter_motion()

if requires_reading_checkpoint():
    coordinator.rollback()                 # restores q/qdot/qddot; clears trial
else:
    coordinator.commit()
    committed_motion = D_trial
```

### After — every attempt, including retries

```text
if requires_writing_checkpoint():
    coordinator.checkpoint(window_id)       # once, before this window's solve

F_input = read_force_for_current_window(relativeReadTime=0)
iteration_state.record_force_input(F_input)
submit_force(F_input, physical_window_identity)
result = coordinator.advance_if_complete()  # solve trial from current physical state
D_trial = coordinator.scatter_motion()     # absolute displacement
iteration_state.record_trial(D_trial, result)

write_motion(D_trial)                       # this trial precedes this advance
advance(dt)
rollback = requires_reading_checkpoint()
iteration_state.record_attempt(rollback)

if rollback:
    coordinator.rollback()                  # physical state only
    iteration_state.advance_iteration()      # retain force/trial residual history
    # Next loop reads the newly available Force iterate from preCICE.
else:
    coordinator.commit()                    # commits the still-pending ANCF trial
    committed_motion = D_trial
    accepted_window += 1
    iteration_state.close_window()
```

The first `read_force` is the configured/available `F^(0)`; it is addressed
explicitly in section 4. The Force sample's physical time and `iteration`
metadata remain the window target time and physical window identity. The
separate `CouplingIterationState.iteration_index` labels retries. Do not feed
the coupling iteration counter into worker physical identity.

`requires_writing_checkpoint()` stays before the trial solve; the decision to
rollback or commit stays after `advance()`. An accepted-at-iteration-limit
window is not to be reported as converged unless the actual preCICE/fake
criterion says it converged.

## 4. Initial Force seed (`F^(0)`) — finding and implementation gate

The current sources establish the following:

1. The current participant does **not** read an explicit `F^(0)` before its
   first ANCF solve. It writes initial Displacement at initialization, then its
   current loop advances preCICE before reading Force (`structure_0000_participant.py:536-550,567-575`).
2. The Structure backend checks `requires_initial_data()` and writes only
   Displacement before `initialize()` (`precice_backend.py:72-87`). It never
   supplies an initial Force value. Its later Force read is at
   `relativeReadTime=0.0` (`precice_backend.py:98-102`).
3. HH06 `precice-config.xml:27-28` marks Displacement `initialize="yes"`, but
   does not mark Force for initialization. The Fluid adapter config declares
   Force as `writeData` (`system/preciceDict:22,32-33`).
4. The current fake `_FakeFleet` cannot model an input seed: `read_force()` is
   only called after `advance()`, requires a just-written displacement, and
   computes Force as `1 + 10*D_written_y` (`tests/coupling/test_implicit_iteration_trace.py:164-187`).
   That fake characterizes the old order; it is not evidence for pre-advance
   Force availability.
5. The HH06 contract says the initial force is outside the q0 dry-run contract,
   but if time integration is authorized the 30 s CFD force should be read at
   release. Its `Fx0_total_N` and `Fy0_total_N` are null
   (`cases/hh06_single_slice/contract.json:39-53,166-172`); the case launch
   guard requires numeric initial-force fields (`cases/hh06_single_slice/launch.sh:15-16`).

The preCICE v3.4.1 data-initialization documentation says coupling variables
default to zero when custom initial data is not supplied; nonzero initial data
must be written before `initialize()`. The implicit-coupling example uses the
read → solve → write → `advance()` loop, with checkpoint request before the
solve and rollback decision after `advance()` ([data initialization](https://precice.org/couple-your-code-initializing-coupling-data.html),
[implicit coupling](https://precice.org/couple-your-code-implicit-coupling),
[Participant API](https://precice.org/doxygen/main/classprecice_1_1Participant.html)).
These semantics are also recorded in the accepted Phase 1B report, which
checked the installed preCICE 3.4.1 headers.

**Conclusion:** with the current XML, the first Force iterate available to a
read-before-solve implementation is preCICE's default zero, not a measured
30 s CFD force. Treating it as a *fixed-point starting iterate* is different
from declaring it the physical initial load, but the HH06 contract currently
requires the actual release force for authorized time integration. No source
artifact in this case currently supplies that numeric Force value. Resolve
this mismatch before implementing the first-attempt path; do not silently
reinterpret zero as the physical release force.

The Structure backend cannot provide an incoming Fluid Force as preCICE initial
data. If the decision is to seed with the actual release Force, the Fluid-side
initial-data path and the `<exchange data="Force" ... initialize="yes"/>`
configuration must be audited and separately authorized. If the explicit
decision is instead to use preCICE's zero as a solver iterate only, record that
policy in the coupling contract and test that the accepted fixed point is
independent of the seed within the configured tolerances. The offline fake
test must inject its seed explicitly; its test seed is not evidence of the real
HH06 value.

The case's `relativeReadTime=0.0` behavior at the beginning of later physical
windows must also be asserted by a fake adapter contract: it must deliver the
Force iterate belonging to the current window/retry, not a stale force from a
different physical window. This is an offline assertion, not authorization for
a real preCICE run.

## 5. Rollback semantics

| Category | Exact behavior after a retry request |
|---|---|
| Restored | Backend `q`, `qdot`, `qddot`, pending physical trial/committed physical count; coordinator committed step and physical window checkpoint. The same physical tuple and `dt` remain active. |
| Preserved | Current window's Force iterate as preCICE input for the next attempt; coupling iteration index; prior Force/trial values needed for residuals and trace; the same active physical checkpoint; transport counters and their monotonic sequence. |
| Discarded as physical state | Rejected ANCF trial q/qdot/qddot. Its displacement value remains only as prior-iteration data for residual/trace calculation; do not commit or blindly resend it. |
| Next output | Solve from the restored physical checkpoint using the latest Force iterate, scatter a new absolute `D_trial(k+1)`, and write it before the next `advance()`. |

`coordinator.rollback()` already implements the physical restore and clears
pending/gather state while retaining the checkpoint. `CouplingIterationState`
must live outside it. Transport ID behavior remains owned by the backend and
must not be added to the checkpoint.

## 6. Required regression tests before implementation is qualified

1. **Fake Fluid fixed-point convergence.** Extend
   `tests/coupling/test_implicit_iteration_trace.py` with an event-logged fake
   that seeds an explicit `F^(0)`, returns the current force input before the
   Structure solve, and computes the next force in fake `advance()` from the
   just-written `D_trial`. Use the approved deterministic map
   `F=1+2D`, `D_trial=0.1+0.2F`, with explicit fake seed
   `D^(0)=0`, `F^(0)=1`. Assert write-before-advance for each attempt, both
   force and displacement residual sequences, expected fixed point, and
   tolerance-driven acceptance (not acceptance merely because a cap was
   reached). Keep the seed labeled as a fake-test seed.
2. **Physical rollback regression.** Run all cases in
   `tests/checkpoint/test_checkpoint_lifecycle.py`: exact q/qdot/qddot restore,
   repeated rollback using the same checkpoint, and commit preserving the
   accepted trial while clearing the checkpoint only at acceptance.
3. **Transport identity regression.** Run the Phase 1A.5 offline lineage
   qualification script under
   `evidence/legacy_qualification/hh06_single_slice_coupling_history_v1/evidence/runtime/hh06_worker_lineage_transition_fix_audit_v1/lineage_transition_protocol_test.py`
   and retain the current checkpoint test's monotonic ID assertions. Verify
   physical identity does not change within a window, all transport IDs remain
   unique/monotonic, and rollback does not restore them.
4. **No cross-window contamination.** In the coupling fake, force several
   retries in window 1, accept it, then run window 2. Assert window 2 starts
   from only window 1's accepted physical q/qdot/qddot and `committed_motion`;
   discarded trials and prior residual/iteration history do not leak. Assert
   the window identity advances once and transport IDs continue monotonically.
5. **Accepted output equals written trial.** On a non-retry attempt, assert
   that the ANCF trial scattered for that attempt is exactly the vector passed
   to `write_motion()` before the `advance()` that accepted the window, and
   that this physical trial is the one committed. This compares the raw
   participant write; it does not claim equality with preCICE-relaxed/Fluid-
   visible data under the configured constant relaxation.

## 7. Planned file-level changes and gates

| File | Planned implementation change | Gate / constraint |
|---|---|---|
| `src/coupling/hh06_structure_0000/structure_0000_participant.py` | Add participant-level `CouplingIterationState`; reorder the attempt loop to read Force, solve/scatter, write that trial, advance, then inspect rollback/commit; preserve separate trace vectors and update their event timing. | Do not alter force conversion, ANCF equations, worker request physical identity, checkpoint format, or accepted-window time advancement. Block first-attempt implementation until the `F^(0)` policy is resolved. |
| `src/coupling/arbitrary_n_live_orchestration_v1/coordinator.py` | No behavior change planned. Existing submit/advance/scatter/rollback/commit lifecycle already fits the migration and preserves physical rollback. | Modify only if offline tests expose a concrete missing coordinator contract; do not put coupling history or transport counters in `CouplingCheckpoint`. |
| `src/coupling/arbitrary_n_live_orchestration_v1/precice_backend.py` | No ordering change planned; retain pass-through read/write/advance/checkpoint methods and initial Displacement handling. | Any actual-Force initialization requires Fluid-side support/configuration and separate scope authorization; Structure must not fabricate incoming Force. |
| `tests/coupling/test_implicit_iteration_trace.py` | Replace/extend old-order characterization with event-logged stale-vs-correct fixed-point lifecycle, explicit initial seed, and two-window isolation tests. | Fake only; no preCICE or OpenFOAM runtime. |
| `tests/checkpoint/test_checkpoint_lifecycle.py` and Phase 1A.5 evidence script | Regression execution only unless a test contract is found missing. | No changes to physical checkpoint or transport ID semantics. |

Implementation order, if separately authorized: first settle/document `F^(0)`;
then add or update deterministic fakes; implement only the participant ordering
and state separation; run all offline tests above; inspect trace; stop before
real preCICE qualification unless separately authorized. No runtime action is
authorized by this plan.
