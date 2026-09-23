# Phase 1B — Implicit Coupling Iteration Trace Report

## Status and boundary

| Item | Result |
|---|---|
| Phase 1B base HEAD | `7c38f61aeb27e56ae5916cc2b5e6f2bc17aa047b` |
| Phase 1A.5 source repair commit | `0383920 fix: replace worker sequence parity with physical identity checks` |
| Phase 1A.5 documentation/evidence commit | `7c38f61 docs: qualify worker lineage transition repair` |
| Instrumentation | Implemented; diagnostic only |
| GenericStructuralCoordinator | Unmodified |
| Coupling call order / checkpoint contents / rollback / commit | Unmodified |
| Deterministic fake-backend test | PASS; 2 windows × 5 attempts/window |
| Real preCICE runtime | NOT RUN |
| OpenFOAM / HH06 runtime | NOT RUN |
| Coupling-ordering fix | NOT implemented |

The current source trace and fake test establish the participant's write path.
They do not establish that this path caused the historical late-window
ALE/flow/turbulence runaway.

## preCICE 3.4.1 semantics checked before instrumentation

The installed header `/usr/include/precice/Version.h` defines
`PRECICE_VERSION` as `3.4.1`. The installed `Participant.hpp` and official
preCICE API/implicit-coupling documentation were checked before editing.

- `writeData()` stages the participant-provided values; `advance()` sends and
  resets written coupling data, exchanges/maps data, and computes implicit
  convergence and acceleration. Therefore preCICE does not automatically
  promote an ANCF state held only in the participant's local memory into the
  next iteration's write buffer. The participant must explicitly write that
  value before the next `advance()`.
- `readData(..., relativeReadTime=0)` reads the exchanged value at the
  beginning of the current time step. `advance(dt)` with the window-sized
  timestep reaches the time-window boundary and performs coupling exchange;
  the existing Structure backend reads its Force after that call with
  `relativeReadTime=0`.
- For implicit coupling, the adapter requests a solver checkpoint before the
  first attempt and checks `requiresReadingCheckpoint()` after `advance()`.
  When a retry is requested, the solver restores the checkpoint before its
  next `advance()`. The documented solver iteration is an input-read → solve →
  output-write → `advance()` cycle; the checkpoint is the solver's own state.
- In this case, `D_written_to_precice` below means the exact value passed by
  Structure to its `write_motion()`/preCICE `writeData()` call. The HH06
  configuration uses parallel implicit coupling with constant relaxation,
  which is applied inside `advance()`. Without a real run, this report does
  not equate that raw API argument with the relaxed displacement actually
  consumed by Fluid.
- The trace's `time_window_complete` is derived from
  `requiresReadingCheckpoint() == false`; no extra preCICE status query was
  added. `convergence_status` deliberately distinguishes retry-requested from
  accepted-at-convergence-or-iteration-limit; it does not claim convergence
  when the iteration limit may have accepted the window.

Sources: the installed version header and `Participant.hpp`; [preCICE
Participant API](https://precice.org/doxygen/main/classprecice_1_1Participant.html),
[implicit coupling lifecycle](https://precice.org/couple-your-code-implicit-coupling),
and [acceleration semantics](https://precice.org/configuration-acceleration).
The API reference and site snapshot identify the documented release as
preCICE 3.4.1.

## Current Structure participant lifecycle

The audited path in `src/coupling/hh06_structure_0000/structure_0000_participant.py`
remains:

```text
requiresWritingCheckpoint → coordinator.checkpoint (when requested)
→ write committed_motion → preCICE advance → read Force
→ coordinator submits force → ANCF trial advance → scatter trial motion
→ requiresReadingCheckpoint
   ├─ true: coordinator.rollback; retry loop
   └─ false: coordinator.commit; committed_motion = scattered
```

The value written at the top of every attempt is still
`committed_motion`. On a retry, the `scattered` ANCF trial is not assigned to
`committed_motion`; the coordinator restores physical `q/qdot/qddot` and clears
its pending trial. Thus the next participant-loop write uses the previous
accepted displacement. No source change was made to this lifecycle.

The preCICE fleet backend remains a pass-through for the existing
`write_data`, `advance`, `read_data`, and checkpoint requirement calls. The
coordinator's checkpoint/rollback/commit implementation is unchanged.

## Instrumentation added

Changes are confined to:

- `src/coupling/hh06_structure_0000/structure_0000_participant.py`
- `tests/coupling/test_implicit_iteration_trace.py`
- `tests/coupling/__init__.py`
- this report

The Phase 1B plan-only artifact from the preceding step,
`docs/PHASE1B_IMPLICIT_COUPLING_AUDIT_PLAN.md`, was already present and was not
modified by this implementation. The instrumented participant source SHA-256
at this report revision is
`959c7430eca34f77c4b3d7390f722cf44d2ea5a886474614d98314063d7795f9`.

The participant now returns an `attempt_trace` and supports optional
`--trace-output PATH`, writing one JSON object per attempt as JSONL. Existing
trace paths are not overwritten. Each attempt keeps distinct fields for
`D_previous_committed_m`, `D_written_to_precice_m`, and
`D_trial_from_ancf_m`; it also records physical identity, transport IDs, raw,
sectional, and applied force, within-window force/trial-displacement/written
motion residuals, checkpoint/rollback/commit status, ANCF iterations/residual,
and separate `q`, `qdot`, `qddot` hashes.

Residuals compare only against the immediately preceding attempt in the same
physical window. First-attempt residuals are JSON `null`. The trial
displacement residual is measured over the communicated 2-D interface
components; the full 3-D scattered ANCF displacement is retained separately.

The backend's returned diagnostic mapping was extended only to expose the
already allocated transport IDs, physical request tuple, and trial state
hashes. No wire fields, checkpoint contents, worker state, or preCICE API calls
were changed.

## Deterministic fake-backend result

Test:

```text
python3 -m unittest discover -s tests/coupling -v
Ran 1 test — PASS
```

The test drives the actual Structure participant loop and
`GenericStructuralCoordinator` with fake worker/fleet endpoints. It does not
instantiate a preCICE participant or launch the C++ worker/OpenFOAM. Its
deterministic relationship is:

```text
Fluid:     Fy = 1 + 10 * D_written_y
Structure: D_trial_y = D_checkpoint_y + 0.1 * Fy
```

The fake fleet requests rollback for attempts 1–4 in each window and accepts
attempt 5. It uses two physical windows, five attempts each. The observed
interface path is:

| Physical window | Iterations | Sequences | `D_previous_committed_y` | `D_written_y` | `Fy_raw` | `D_trial_y` | Outcome |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 1–4 | 1–4 | 0.0 m | 0.0 m | 1.0 N | 0.1 m | rollback each attempt |
| 1 | 5 | 5 | 0.0 m | 0.0 m | 1.0 N | 0.1 m | committed |
| 2 | 1–4 | 6–9 | 0.1 m | 0.1 m | 2.0 N | 0.3 m | rollback each attempt |
| 2 | 5 | 10 | 0.1 m | 0.1 m | 2.0 N | 0.3 m | committed |

Within a physical window, `global_step`, `bridge_step`, `integer_tick`,
`time_s`, and `dt_s` remain fixed. Between windows, physical step/time/tick
advance once with unchanged `dt_s`. Transport `sequence`, `request_id`, and
`transaction_id` remain monotonic across all ten attempts (`1..10`, `501..510`,
and `901..910`).

At window 1 iteration 1, the trial changes from the committed interface value
(`0.0 → 0.1 m`). After rollback, iteration 2 writes `0.0 m`, not the prior
`0.1 m` ANCF trial. The fake Fluid therefore returns `1.0 N` again; if the trial
had been written, this fixture would return `2.0 N`. The within-window force,
trial displacement, and written-motion residuals after the first attempt are
zero for this repeated stale input/output sequence.

The fake worker also verifies that each rollback restores physical `q`,
`qdot`, and `qddot` to the window checkpoint while transport IDs continue
advancing. The accepted `0.1 m` state from window 1 becomes the committed input
for window 2.

Observed classification for the current participant loop:
`STALE_COMMITTED_MOTION`.

## Required findings

1. **After rollback, what is written on the next retry?** The previous
   committed displacement `D_n`.
2. **A or B?** **A — previous committed displacement**, not the prior ANCF
   trial displacement.
3. **Does that match preCICE 3.4.1 semantics?** preCICE's checkpoint and
   data-buffer semantics do not automatically carry a local ANCF trial into
   the next write. The literal restore-and-write-old-value behavior is
   compatible with those API mechanics, but it does **not** implement the
   intended fixed-point feedback `D_trial(k) → D_written(k+1)`. The documented
   implicit loop expects the participant to compute and write its iteration
   output before the next `advance()`. This is not evidence of a preCICE
   internal violation.
4. **Responsible layer if the intended contract is trial feedback:** the
   Structure participant loop's choice to write `committed_motion` after a
   rollback. The coordinator correctly restores physical checkpoint state;
   the backend delegates the existing preCICE calls. This audit does not
   identify checkpoint corruption or a preCICE adapter substitution.
5. **Does this explain the previous runaway?** `NOT_CONFIRMED`. The fake test
   confirms stale displacement feedback in this source loop and demonstrates
   how it can produce zero residuals for this deterministic relation. It does
   not establish that this was the cause of the historical HH06/ALE/flow/
   turbulence runaway. No instrumented real preCICE or OpenFOAM trace was run.

## Validation and stop condition

- Fake deterministic trace test: **PASS**.
- `git diff --check`: **PASS** after final source/test/report edits.
- ANCF/SHM1 full regressions: **NOT RUN in this instrumentation step**.
- Real 2-window preCICE / OpenFOAM / HH06: **NOT RUN**.
- 5-window or 25-window qualification: **NOT RUN**.
- No coupling fix or parameter adjustment is claimed.

Stop here. Phase 1B behavior changes and all real FSI qualification remain
unauthorized by this instrumentation result.
