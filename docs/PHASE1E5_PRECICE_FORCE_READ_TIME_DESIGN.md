# Phase 1E.5 — preCICE Force Read-Time Contract Audit

## Scope and frozen Phase 1E evidence

This audit resolves only the Structure-side read-time contract for Force during
implicit retries. It made no production source, HH06 XML, OpenFOAM, or ANCF
changes, and ran no HH06/OpenFOAM/ANCF runtime.

The reviewed Phase 1E run is preserved at:

`evidence/phase1e_bounded_2window/run-20260923T065444Z-02d9a1f1/`

The attempt trace SHA256 is
`2d96f0d2f6fb0cc73290203a379b14336bc25b24951d13598f1d983208f96b74`;
the Phase 1E report SHA256 is
`d4386cfb801acdfe1b5cf7fc8a9812d2ad798ffb442fca62b3a1b70bbd52dc4e`.
That run showed `D_written_to_precice == D_trial_interface` for every attempt,
while Structure's ANCF Force input stayed unchanged during retries. preCICE's
reported coupling residuals changed. The failure was accepted as
`FAIL_REAL_IMPLICIT_CONTRACT`; this audit does not revise that classification.

The current tracked versions of `precice_backend.py`,
`structure_0000_participant.py`, and `precice-config.xml` remain unchanged.
Their SHA256 values during this audit are respectively:

- `precice_backend.py`: `c2cdcef8c77135de71307ae5c9ad74c468c4c67a78f8442bb6329f94921f3aa6`
- `structure_0000_participant.py`: `34baa21a7f286ce64af7afa23f4d59f426706cdfd32f26ad98ef56b12c62c6ed`
- `precice-config.xml`: `7f64a99f7bd7ab82f0ac2fb912bf6b89e83843e0cbbb526b5a8e2ac690cb5c55`

## Current call path

In `src/coupling/arbitrary_n_live_orchestration_v1/precice_backend.py`,
`PreciceStructureFleetBackend.read_force()` at lines 98–102 calls
`participant.read_data(..., 0.0)` unconditionally.

In `src/coupling/hh06_structure_0000/structure_0000_participant.py`:

1. Immediately after `fleet.initialize()`, line 738 reads the initialized Force
   at relative time zero and checks it against the contracted physical release
   F0. This is the correct initialization check and should remain explicit.
2. For every attempt, the participant submits the current force to ANCF, solves,
   writes the trial displacement, and calls `fleet.advance(dt)` (approximately
   lines 790–823).
3. Immediately after `advance()`, it currently calls `fleet.read_force()` at
   relative time zero, then asks `requires_reading_checkpoint()` (lines
   824–825). On a retry, that read selects the window-start sample, not the
   endpoint Force produced by the just-completed implicit iteration.
4. If accepted, relative time zero refers to the now-current next-window start
   and yields the accepted Force for the next physical window. This explains why
   the existing read path can transfer Force across accepted windows while
   remaining stale within retries.

## Installed preCICE 3.4.1 API evidence

The version-matched installed interface is
`/usr/include/precice/Participant.hpp` (SHA256
`d7c677fd9bb035483bcb6a45dc04b91cb500989470913c38c357557d76cf2bdd`). Its
`readData()` documentation at lines 846–849 defines the relative read time from
the beginning of the current solver timestep: `0` is the timestep start and
`dt` is its end. The implicit-coupling documentation at lines 337–362 places
checkpoint handling around each `advance()` and requires restoring solver
state when `requiresReadingCheckpoint()` is true. The API documentation also
states that written data is exchanged by `advance()` and that, absent custom
initial data, coupling data defaults to zero (lines 783–785).

This establishes the API meaning of the offsets. The scratch participants below
establish which sample carries the prior implicit iterate in the actual
installed 3.4.1 runtime and HH06-like exchange settings.

## Scratch two-participant test

The reproducible harness is
`evidence/phase1e5_precice_force_read_timing/run_scratch_read_timing.py`.
Its final passing run is
`evidence/phase1e5_precice_force_read_timing/run-20260923T074627Z-pid112440/`;
machine-readable results are in `result.json` (SHA256
`b8095d5765bce468fd1b1b94101eb01b6ddeae2248e1ca771b9d886f1110297e`). Both
configurations passed `precice-config-validate`; both participants exited 0 in
both runs. The runtime logs identify preCICE 3.4.1. The test used
`/usr/bin/python3.10`, pyprecice metadata 3.4.0, one fake mesh vertex, one
physical window, and four implicit attempts (three requested rollbacks, then
acceptance). It used the same relevant HH06 configuration:

- `waveform-degree="0"` for Force and Displacement;
- `substeps="false"` for both exchanges;
- initial Force supplied before `initialize()`;
- one timestep per window, with window size equal to `dt`.

Fluid initialized `F0=(10,-10)` and wrote a different Force before each
advance: `F1=(101,-203)`, `F2=(102,-206)`, `F3=(103,-209)`, and
`F4=(104,-212)`. Structure wrote a distinct trial displacement on each attempt.
The harness recorded both offsets before the next solve and immediately after
each `advance()`.

| Structure Force read | Values supplied to the four fake solves | Result |
|---|---|---|
| `relativeReadTime=0` | `F0, F0, F0, F0` | retry reads remain stale |
| `relativeReadTime=dt` | `F0, F1, F2, F3` | each retry consumes the preceding advance's Force |

Immediately after `advance()` on attempts requiring rollback, reading at zero
still returned `F0`, while reading at `dt` returned the Force from that same
completed implicit attempt (`F1`, `F2`, then `F3`). After the final accepted
advance, reading at zero returned accepted `F4`; `dt` was no longer a valid
sample because the active window had ended. This is why the read-time choice
must be conditional on the checkpoint request rather than unconditionally set
to `dt`.

The final scratch classification is `PASS_READ_TIME_CONTRACT`. An exploratory
probe that tried to read at `dt` after the accepted final advance received
preCICE's expected “cannot sample data outside of current time window” error;
the final harness avoids that invalid read and records the accepted branch
separately. An earlier scratch-only configuration also used an invalid
near-zero convergence threshold and was rejected by the config validator;
the final test uses a valid `1e-12` synthetic threshold. Neither exploratory
issue changed the production configuration.

## Exact retry contract and event timeline

Let `F0` be the initialized release Force. On attempt `k`, Structure consumes
`F_(k-1)`, computes `D_trial_k`, and writes it before `advance()`. Fluid's
exchange then produces `F_k` for the active window. If
`requiresReadingCheckpoint()` is true, the next structural solve must use
`F_k`, i.e. the endpoint Force of the just-completed implicit iteration. It is
both “the Force returned by the previous advance” and “the Force at the end of
the current implicit iteration.” It is not the Force at the physical window
start.

Recommended future production ordering (design only; not implemented here):

```text
after initialize:
    F0 = read Force at relativeReadTime=0
    validate F0 provenance/value

for each trial:
    checkpoint physical state if requested
    solve ANCF using current Force iterate
    write exact D_trial
    advance(dt)
    retry = requiresReadingCheckpoint()

    if retry:
        F_next = read Force at relativeReadTime=dt
        rollback physical ANCF state
        preserve F_next and coupling-iteration history
    else:
        F_accepted = read Force at relativeReadTime=0
        commit physical ANCF state
        use F_accepted as the next physical window's starting Force
```

The preCICE checkpoint query must precede the conditional Force read so the
participant selects the endpoint sample only while retrying. The initialized
physical F0 remains sourced at global CFD time 30.0 s; it is not relabelled as
a Force measured at the trial target time.

## Waveform and substeps conclusion

For the current HH06 profile, the window size and Structure `dt` are both
`0.0002 s`; there is one solver step per physical coupling window, and both
Force and Displacement exchanges specify `substeps="false"`. The exact scratch
configuration reproduces the distinction between start and endpoint samples.
Therefore reading at `dt` on a retry is sufficient to consume the preceding
implicit iterate. No waveform-degree, substeps, mapping, relaxation, or other
XML change is indicated by this audit.

This conclusion is bounded to the current one-step-per-window profile. A future
subcycled participant or changed exchange/substeps profile would need its own
time-sample contract test; `dt` always means the endpoint of the current solver
timestep, not automatically the endpoint of an arbitrary longer coupling
window.

## Recommended production change and regressions

No implementation is authorized in this audit. If separately approved, the
narrow change should affect:

- `src/coupling/arbitrary_n_live_orchestration_v1/precice_backend.py`: make
  relative read time explicit in `read_force()` rather than hardcoding zero.
- `src/coupling/hh06_structure_0000/structure_0000_participant.py`: retain the
  initialization F0 read at zero; after each advance query the retry flag
  first; read at `dt` for a retry and at zero for acceptance; preserve existing
  physical rollback, iteration state, trace, and transport behavior.
- Coupling tests/evidence only; no XML change is currently justified.

Required offline regressions before any later real coupling authorization:

1. Preserve the passing two-participant read-time probe: zero returns the
   window-start Force on retries; `dt` returns `F1`, then `F2`, etc.
2. Verify the post-advance retry branch reads `dt`, while the accepted branch
   reads zero and does not sample `dt` outside the ended window.
3. Verify initial post-initialize F0 still matches the frozen release-force
   provenance and is used for the first trial.
4. Verify a two-window fake run passes the accepted prior-window Force into the
   next window and never resets to release F0 or leaks a rejected trial.
5. Re-run physical checkpoint/rollback, worker transport monotonicity, and
   existing Strategy C fixed-point and accepted-output-equality regressions.
6. Assert trace Force source/offset and actual vector separately; timestamps or
   convergence residuals alone are not proof of which Force was consumed.

No real HH06 rerun is authorized by this design report.

## Audit state

- preCICE API offset semantics: **CONFIRMED** by installed 3.4.1 header.
- retry endpoint Force behavior: **CONFIRMED** by final two-participant
  scratch runtime test.
- current retry stale-read mechanism: **CONFIRMED** by combining that runtime
  result with the unchanged backend's hardcoded zero offset and the Phase 1E
  attempt trace.
- recommended retry offset: **`relativeReadTime=dt_s`**.
- accepted-window next-start offset: **`relativeReadTime=0.0`**.
- production changes: **NONE**.
- current Git HEAD: `02d9a1f180082e83bcc9f7acdcb090502262b2d1`.
- tracked worktree: clean; untracked Phase 1E report/evidence and this audit's
  scratch harness/results are preserved for review. Nothing was committed.
