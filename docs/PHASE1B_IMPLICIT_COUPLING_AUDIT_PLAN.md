# Phase 1B — Implicit Coupling Iteration Audit Plan

## Review gate and execution boundary

```text
phase = 1B
purpose = audit implicit coupling iteration lifecycle
production_behavior_modified = NO
diagnostic_instrumentation_added = NO (plan-only step)
OpenFOAM_runtime = NOT_RUN
preCICE_runtime = NOT_RUN
HH06_production_runtime = NOT_RUN
long_run = NOT_RUN
```

This document records the current source-level lifecycle and the diagnostic
instrumentation plan. It does not authorize a coupling-ordering change. The
preCICE 3.4.1 API semantics must be confirmed from the installed interface or
official version-matched documentation before instrumentation is implemented.

## 1. Current authoritative call chain

The live single-slice entry point is:

```text
src/coupling/hh06_structure_0000/structure_0000_participant.py:491
  run(case_dir, worker_path, max_windows)
```

The current owners are:

| responsibility | source owner |
|---|---|
| live Structure participant loop | `structure_0000_participant.py:516–540` |
| preCICE participant and data calls | `arbitrary_n_live_orchestration_v1/precice_backend.py:22–141` |
| force gather and structural trial/commit/rollback | `arbitrary_n_live_orchestration_v1/coordinator.py:339–511` |
| persistent C++ worker transport and ANCF trial advance | `structure_0000_participant.py:331–455` |
| physical checkpoint state | `GenericStructuralCoordinator` plus backend `snapshot/restore` |

## 2. Current lifecycle trace

For a physical window whose index is `accepted + 1`, the current participant
executes the following sequence.

| order | current action | source evidence | current state/data |
|---:|---|---|---|
| 0 | test whether coupling is ongoing | `structure_0000_participant.py:520` → backend `:123–128` | preCICE `is_coupling_ongoing()` |
| 1 | request writing checkpoint | participant `:521` → backend `precice_backend.py:109–114` | preCICE `requires_writing_checkpoint()` |
| 2 | create physical checkpoint | participant `:522`; coordinator `coordinator.py:465–478` | backend `q`, `qdot`, `qddot`, committed count, pending flag; no transport counters |
| 3 | write structural motion | participant `:523`; backend `:93–96` | `committed_motion`, projected to the 2-D preCICE `Displacement` data |
| 4 | advance preCICE | participant `:524`; backend `:104–107` | `Participant.advance(dt)` |
| 5 | read fluid force | participant `:525`; backend `:98–102` | preCICE `read_data(..., relative_read_time=0.0)` |
| 6 | normalize force and build request | participant `:526–528`; coordinator `:387–425` | raw force → sectional/applied force; one gathered `WorkerRequest` |
| 7 | advance ANCF trial state | coordinator `:427–435`; HH06 backend `:402–446` | new worker transport IDs; `q/qdot/qddot` become tentative |
| 8 | scatter ANCF trial motion | coordinator `:437–451` | `scattered`/`_last_motion` contains current trial section motion |
| 9 | query rollback request | participant `:531`; backend `:116–121` | preCICE `requires_reading_checkpoint()` |
| 10a | rollback retry path | participant `:532–533`; coordinator `:480–503` | restore physical state; clear tentative gather/motion; retain checkpoint and transport counters |
| 10b | accepted-window path | participant `:534`; coordinator `:453–463` | backend commit; clear checkpoint; assign `committed_motion = scattered`; increment `accepted` |

The loop writes `committed_motion` before every `advance()` call. The current
source does not write `scattered` between `scatter_motion()` and a retry
`advance()` call.

## 3. Current physical/transport state ownership

### Physical trial and checkpoint state

`GenericStructuralCoordinator.checkpoint()` snapshots the backend state before
the tentative global advance. `PersistentHH06KernelBackend.snapshot()` stores:

```text
q, qdot, qddot, committed_advance_count, pending
```

`rollback()` restores that snapshot, clears the gathered force and trial
motion, resets the pending flag, and keeps the checkpoint alive for repeated
retries. `commit()` is the only path that clears the checkpoint and advances
the committed physical-window count.

### Transport state

`PersistentHH06KernelBackend.advance()` allocates fresh session counters for
`sequence`, `request_id`, and `transaction_id` before constructing each
`KernelStepRequest`. These counters are not in `snapshot()` and are not
restored by `rollback()`.

## 4. Static observation requiring runtime proof

The current source-level data path is:

```text
D_n written to preCICE
  → preCICE advance/read F_1
  → ANCF trial D_1
  → scatter D_1
  → rollback
  → next loop writes committed_motion = D_n again
```

After a non-rollback commit, `committed_motion` is assigned `D_1`, so the next
physical window starts with that accepted motion. After a rollback, the
assignment at participant line 534 is skipped. Therefore the source path
currently predicts that a trial motion can change while the next retry's
written motion remains the prior committed motion.

This is a source-level observation and the leading audit hypothesis. It is not
yet a proven preCICE root cause because the installed preCICE 3.4.1 lifecycle
semantics and an instrumented runtime trace have not been checked.

The current code also does not retain one record per retry: `records` at line
535 are appended only after an accepted window. Coupling force and
displacement residuals are not currently emitted by the participant. The
worker result contains ANCF Newton diagnostics, but those are not coupling
residuals.

## 5. Diagnostic instrumentation plan — no behavior change

Instrumentation, when separately authorized, should be additive and disabled
unless an explicit trace path is configured. It must not reorder calls, alter
checkpoint contents, alter transport counters, or change the rollback/commit
branches.

### Planned instrumentation points

1. `structure_0000_participant.py` around lines 521–535:
   capture checkpoint request/result, the exact motion passed to
   `write_motion()`, the force returned by `read_force()`, the trial motion
   returned by `scatter_motion()`, the rollback decision, and commit result.

2. `PersistentHH06KernelBackend.advance()` around lines 409–446:
   expose diagnostic-only transport IDs, physical request identity, ANCF
   Newton iterations/residual, and trial `q/qdot/qddot` state hashes in the
   returned diagnostic mapping. The wire request and response remain
   unchanged.

3. `PreciceStructureFleetBackend` around lines 93–121, only if needed to
   capture API-return timing/status:
   record successful `write_data`, `read_data`, `advance`, and checkpoint
   requirement queries without wrapping or reordering the calls.

`GenericStructuralCoordinator` should not be behaviorally changed. The
participant can record its calls before and after the existing coordinator
methods; coordinator changes would be considered only if a required state is
otherwise inaccessible.

### Planned trace record

Emit one JSON record for every physical-window attempt, including retries:

```text
run_id
case_id
window_index
iteration_index
sequence
physical_time_s
dt_s

Fx_raw_N, Fy_raw_N
Fx_section_Npm, Fy_section_Npm
Fx_applied_N, Fy_applied_N

Dx_written_to_precice_m, Dy_written_to_precice_m
Dx_trial_from_ancf_m, Dy_trial_from_ancf_m
written_motion_vector
trial_motion_vector

force_residual_raw_N
force_residual_applied_N
displacement_residual_trial_m
written_motion_delta_m

requires_writing_checkpoint
requires_reading_checkpoint
rollback_requested
time_window_complete_or_accepted
commit_status

ancf_newton_iterations
ancf_residual
q_state_hash
qdot_state_hash
qddot_state_hash
```

The first attempt in a physical window has null residuals. Subsequent local
diagnostic residuals must be defined from the immediately preceding attempt
in the same physical window:

```text
force_residual = norm(F_k - F_(k-1))
displacement_residual_trial = norm(D_trial_k - D_trial_(k-1))
written_motion_delta = norm(D_written_k - D_written_(k-1))
```

The trace must preserve both `D_written` and `D_trial`; a single motion hash is
insufficient to establish whether a trial became visible to Fluid.

## 6. Diagnostic acceptance checks

The first diagnostic run should use a deterministic/fake backend with two
physical windows and at most five attempts per window. Its force response must
depend on the displacement written for that attempt, so stale versus trial
feedback is distinguishable.

The trace is informative only if all of the following are visible:

1. retry attempts retain the same physical window/time identity;
2. sequence and transport IDs advance for every attempt;
3. `D_trial_k` is captured after ANCF advance and before rollback/commit;
4. after a rollback, `D_written_(k+1)` is explicitly compared with
   `D_trial_k`;
5. force and trial-displacement residuals are computed over attempts in the
   same physical window;
6. physical checkpoint restoration and transport-counter persistence remain
   observable;
7. every retry record is retained, including records preceding rollback.

The current source prediction is:

```text
D_trial_1 != D_written_1
rollback = true
D_written_2 == D_written_1 == D_n
```

That prediction must be tested, not promoted to a confirmed root cause from
source inspection alone.

## 7. Explicit non-goals for this audit step

- no coupling-ordering fix;
- no change to `committed_motion` semantics;
- no change to preCICE API calls;
- no dt, relaxation, damping, turbulence, mesh, force, or HH06 parameter changes;
- no OpenFOAM run;
- no real HH06 run;
- no 2-window/5-window preCICE qualification yet;
- no 25-window qualification;
- no three-slice work.

## Stop condition

```text
PLAN_CREATED = YES
DIAGNOSTIC_CODE = NOT_ADDED
PRODUCTION_BEHAVIOR_CHANGE = NONE
WAITING_FOR_REVIEW = YES
```

This step stops after the plan. No instrumentation or runtime is started.
