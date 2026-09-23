# Phase 1C — Implicit Coupling Repair Design

## Status and scope

```text
phase = 1C design only
production source modified = NO
coupling behavior modified = NO
OpenFOAM runtime = NOT RUN
preCICE runtime = NOT RUN
HH06 runtime = NOT RUN
```

This design uses the accepted findings in
`docs/PHASE1B_IMPLICIT_COUPLING_TRACE_REPORT.md`: physical ANCF state is
restored after rollback, but the current participant loop writes the previous
`committed_motion` again and discards the ANCF trial from the next coupling
write. The worker's physical/transport identity repair is separately
qualified. Nothing here changes the current implementation or its validation
status.

## State ownership

| State owner | Contents | Lifetime | Rollback rule |
|---|---|---|---|
| A. `CommittedPhysicalState` | accepted `q`, `qdot`, `qddot`; committed interface displacement `D_n`; committed physical window/step and time | Across accepted windows | Never replaced by a rejected coupling trial |
| A. `PhysicalWindowCheckpoint` | deep copy of A at the start of one physical window, including the physical step state needed to replay that window | One physical window; reused for every retry | Restore A exactly on each retry; clear only after accepted commit |
| B. `CouplingIterationState` | physical window context; coupling iteration index; incoming force iterate; tentative ANCF result; absolute `D_trial`; latest force returned by preCICE; previous-iteration values for residuals/trace | One window's implicit iterations | Do not put it in the physical checkpoint. Preserve the latest exchanged force and iteration history across a retry; discard/recompute tentative ANCF state |
| C. `TransportSessionState` | `sequence`, `request_id`, `transaction_id`, and per-attempt identity | Worker session | Never snapshot, restore, reuse, or decrement on physical rollback |

The physical window context is immutable through retries:

```text
global_step, bridge_step, integer_tick, target_time_s, dt_s
```

It advances exactly once after an accepted commit. Each worker attempt gets
fresh transport IDs while retaining this same physical tuple. `D_trial` is an
absolute interface displacement obtained from the ANCF trial state relative
to the frozen reference; it is not an increment to add to `D_n`.

The current backend checkpoint already has the right basic ownership boundary:
its snapshot contains physical `q/qdot/qddot`, committed advance count, and
pending state, but not transport counters. The coordinator keeps its window
checkpoint alive across rollback and clears it on commit. The design keeps
that boundary; coupling iteration values must not be added to the physical
checkpoint merely to make them survive rollback.

## Repair strategies

| Strategy | Physical correctness | preCICE implicit compatibility | Checkpoint / ANCF interaction | Stale-state risk | Complexity |
|---|---|---|---|---|---|
| A. Preserve the post-solve trial and write it on the next retry, leaving the current call order intact | Keeps the ANCF trial displacement available while restoring physical `q/qdot/qddot`; does not by itself ensure that the accepted physical trial is the one preCICE evaluated | Improves the observed `D_n, D_n, ...` feedback, but the current loop calls `advance()` before computing the current ANCF trial. preCICE therefore evaluates the displacement written on the preceding loop pass; a final `D_trial` can be committed without having been included in the advance that accepted the window | Requires trial interface motion to live outside the restored physical checkpoint. ANCF still re-solves from the physical checkpoint on retry | Medium/high: easy to accidentally treat an unaccepted trial as committed; convergence decision remains one output behind | Low |
| B. Add explicit coupling-iteration state separate from the physical checkpoint, without changing call order | Correctly separates physical rollback from interface-iteration history, but state separation alone cannot repair a write/advance/solve ordering mismatch | Necessary ownership model, but insufficient by itself: with the present ordering, preCICE still evaluates `D_written` before the newly solved trial is written | Physical checkpoint restores only ANCF state. Force iterate, last trial output, residual history, and transport IDs stay in their separate owners | Medium if the participant still chooses the wrong displacement variable to write; low once paired with Strategy C | Medium |
| C. Use B and align the participant loop to read → solve → write trial → advance → handle checkpoint request | Each structural trial is solved from the start-of-window physical state using the current force iterate. The exact trial written is the trial represented by the ANCF state that will either be rolled back or committed | Matches the documented implicit participant lifecycle: the participant computes and writes its output before `advance()`, where exchange, mapping/acceleration, and convergence checks occur | On retry, restore ANCF state to the same physical checkpoint but retain the latest force input and preCICE iteration history. On acceptance, commit the still-pending ANCF trial | Low if state ownership and time-window identity are asserted; remaining risks are incorrect force seeding/time labeling or confusing raw written motion with preCICE-accelerated data | Highest; requires an offline fixed-point test and then a bounded real preCICE mini-qualification |

### Recommendation

Use **Strategy C, implemented with Strategy B's explicit state separation**.
Do not implement Strategy A as a one-line assignment to `committed_motion`.
Under the existing order, such an assignment would make the next force depend
on the preceding trial, but `requiresReadingCheckpoint()` and preCICE's
convergence decision follow an `advance()` that already exchanged the prior
write. If that advance accepts the window, the ANCF trial computed afterward
is not the displacement that Fluid consumed or preCICE evaluated.

With Strategy C, a prior `D_trial(k)` is already written before
`advance(k)` and is part of that coupling iteration. After a retry, the next
ANCF solve starts from the restored physical state and uses the force made
available by the preceding advance; it computes a new `D_trial(k+1)`, which is
then written before `advance(k+1)`. The old trial remains in the local
iteration record and preCICE's own coupling/acceleration history; it is not
mistaken for committed physical motion or replayed as the next structural
output.

For this case, the raw vector passed to preCICE and the vector effectively
consumed by Fluid must remain conceptually distinct. The current XML uses
parallel implicit coupling with constant relaxation; preCICE may transform
coupling data during `advance()`. An offline fake test should isolate the
participant fixed-point contract without acceleration. A later real mini-test
must compare participant writes with preCICE/Fluid-visible values before
making runtime claims.

## Desired lifecycle

Let the accepted physical state at window start be
`S_n = (q_n, qdot_n, qddot_n)`, and let `F^(0)` be the force iterate currently
available to Structure at the beginning of the window. For attempt `k`:

```text
S_trial(k) = ANCF_step(S_n, F^(k-1), dt)
D_trial(k) = absolute_interface_displacement(S_trial(k))
preCICE exchanges D_trial(k) and returns F^(k)
```

If the coupling does not converge, the next solve uses the same `S_n` and the
newly available `F^(k)`. At a converged attempt, preCICE has evaluated the
same `D_trial(k)` produced by the ANCF state that is committed.

### Initial attempt

```text
physical_window = immutable (n+1, target_time, dt, tick, bridge_step)
if requiresWritingCheckpoint():
    checkpoint = copy(CommittedPhysicalState)
    # This checkpoint is retained for every retry in this physical window.

F_input = read current Force iterate available after initialize/window start
sample = convert_force_once(F_input, target_time, window_index)
S_trial = ANCF_step(CommittedPhysicalState, sample, dt)
D_trial = scatter_absolute_interface_displacement(S_trial)

write_motion(D_trial)                 # before advance
advance(dt)                            # exchange/check convergence for D_trial
retry = requiresReadingCheckpoint()    # after advance

if retry:
    rollback physical state to checkpoint
    retain preCICE's newly available Force iterate for attempt 2
    retain D_trial as prior-iteration output/diagnostic, not as committed state
else:
    commit S_trial and D_trial
```

The first force input is the value actually available from preCICE after
initialization/window entry (including configured initial data/defaults). It
must not be fabricated or confused with a force from an unrelated physical
time. In the current HH06 configuration, initial Displacement data is
provided; initial Force seeding and the next-window `relativeReadTime=0`
interpretation must be verified in the offline adapter fake before
implementation.

### Retry attempt

```text
assert physical_window == checkpoint.physical_window
assert physical worker state == checkpoint.(q, qdot, qddot)
assert transport IDs have not been restored

F_input = read latest Force iterate available after the preceding advance
sample = convert_force_once(F_input, same_target_time, same_window_index)
S_trial(k+1) = ANCF_step(checkpoint physical state, sample, same dt)
D_trial(k+1) = scatter_absolute_interface_displacement(S_trial(k+1))

write_motion(D_trial(k+1))             # not D_n and not a stale variable
advance(dt)
retry = requiresReadingCheckpoint()
```

If another retry is requested, restore `q/qdot/qddot` and physical step state
to the same checkpoint again. Keep the same physical time/window identity,
checkpoint, latest force iterate, previous iteration's trial for residuals,
and monotonic transport session. Do not increment the accepted window or
commit `D_trial(k+1)` on this path.

### Accepted commit

```text
assert requiresReadingCheckpoint() == false
coordinator.commit()                    # retain current S_trial
CommittedPhysicalState = S_trial
committed_motion = D_trial               # only here
accepted_window += 1
advance physical time/tick/step exactly once
clear this window's checkpoint and coupling-iteration residual history
```

No rollback is performed after acceptance. If preCICE accepts because its
maximum iteration count was reached, record “accepted at iteration limit,”
not “converged.” The next window starts from the accepted physical state and
motion; it must not inherit rejected ANCF trial state or the old window's
force/residual labels. Transport IDs continue from the same worker session.

### Explicit rollback ownership

| After rollback | Restored | Survives | Value written before next `advance()` under Strategy C |
|---|---|---|---|
| Physical ANCF state | checkpoint `q`, `qdot`, `qddot`, committed physical step/window state | Same physical window target time and `dt`; checkpoint remains active | A newly computed `D_trial(k+1)` from restored physical state and latest Force iterate |
| Coupling iteration | Tentative ANCF solve is no longer the current physical worker state | Latest exchanged Force input; previous `D_trial(k)` as iteration history/diagnostic; preCICE's own coupling/acceleration history | Not `D_n`, and not a blind replay of `D_trial(k)`; the new trial produced in this attempt |
| Transport | Nothing | Session-monotonic sequence, request ID, transaction ID | Fresh identities for the new ANCF request; none are included in the physical checkpoint |

## Required regression tests before implementation is qualified

1. **Deterministic fake-fluid fixed-point convergence.** Drive the actual
   participant lifecycle with `F = f(D_written)` and `D_trial = g(F_input)`.
   Use a contractive deterministic mapping, for example
   `F = 1 + 2D` and `D_trial = 0.1 + 0.2F`, whose fixed point is
   `(D, F) = (0.5 m, 2 N)`. Seed the fake interface consistently with
   `D^(0)=0` and `F^(0)=f(D^(0))=1`; then the first iterates are
   `D_1=0.3`, `F_1=1.6`, `D_2=0.42`, `F_2=1.84`, `D_3=0.468`,
   `F_3=1.936`. Define residuals explicitly as
   `R_D(k)=|D_trial(k)-D_trial(k-1)|` and
   `R_F(k)=|F^(k)-F^(k-1)|`, using the seeded values for `k=1`.
   Both decrease geometrically by the mapping factor `0.4`. Assert that each
   `D_trial(k)` is the value written before that same `advance(k)`, that
   Fluid's force responds to that write, and that the configured convergence
   criterion—not merely the iteration cap—accepts the test window. This
   deterministic seed is only for the fake test; it does not prescribe real
   preCICE initial Force data.
2. **Existing physical rollback regressions.** Run all cases in
   `tests/checkpoint/test_checkpoint_lifecycle.py`: exact `q/qdot/qddot`
   restoration, repeated rollback with one retained checkpoint, and commit
   clearing the checkpoint only after acceptance.
3. **Worker transport identity regression.** Re-run the Phase 1A.5 offline
   worker-lineage qualification (including sequences 1–10 over two physical
   windows, same-window retries, even/odd sequence cases, duplicate guards,
   and rollback). Physical identity must stay constant within retries;
   sequence/request/transaction IDs must be unique, monotonic, and absent from
   the physical snapshot.
4. **No cross-window contamination.** Force several rollbacks in window 1,
   then accept. Start window 2 from only window 1's accepted `q/qdot/qddot`
   and `committed_motion`; assert the discarded window-1 trials do not affect
   window-2 force input, ANCF initial state, displacement, or first residual.
   Assert iteration index/residual history resets per window, physical
   identity advances once, and transport IDs do not reset.
5. **Call-order and accepted-output assertion.** The fake fleet records an
   event log and fails unless every attempt is ordered as
   `read Force → ANCF solve/scatter → write D_trial → advance → checkpoint
   decision → rollback or commit`. On an accepted attempt, assert the
   committed ANCF state generated exactly the trial written in the advance
   that preCICE accepted.
6. **Iteration-cap honesty.** Add a separate fake case that does not meet
   tolerance before the cap. Verify the participant commits only because
   preCICE no longer requests a checkpoint and records the result as
   max-iteration acceptance, not convergence or qualification PASS.

## Implementation gate

This document is a design only. Before a later implementation, review the
initial Force seed and read-time handling against the current preCICE 3.4.1
adapter/API and add the fake tests above. Then implement the participant-side
ordering/state ownership change without changing ANCF physics, worker
protocol, checkpoint format, OpenFOAM parameters, or acceleration settings.
Re-run the existing rollback and transport identity regressions before any
real preCICE mini-qualification. This design does not authorize OpenFOAM,
HH06, 5-window/25-window, or production runs.
