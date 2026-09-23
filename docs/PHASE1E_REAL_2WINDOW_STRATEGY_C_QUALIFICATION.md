# Phase 1E — Real 2-Window Strategy C Qualification

**Primary classification: `FAIL_REAL_IMPLICIT_CONTRACT`**

This was the single authorized real OpenFOAM–preCICE–ANCF run. Both physical
windows completed and all launched participants exited successfully, but the
Structure participant did not consume the updated Force iterate during retry
attempts. No source or configuration was changed, and no retry run was made.
This is not HH06 validation and provides no long-run stability result.

## Run identity and bounds

- Run ID: `run-20260923T065444Z-02d9a1f1`
- Launcher-generated runtime directory:
  `evidence/phase1e_bounded_2window/run-20260923T065618Z-pid106532/`
- Branch: `repair/worker-lineage-implicit-contract-v1`
- HEAD: `02d9a1f180082e83bcc9f7acdcb090502262b2d1`
- Worktree was clean before the run. Post-run tracked source/configuration diff
  remained empty.
- Final preflight: `PASS_PREFLIGHT_ONLY`; one `--run-bounded --max-windows 2`
  invocation; no second launch.
- Runtime bounds: `dt = 0.0002 s`, preCICE `max-iterations = 20`,
  `max-time-windows = 2`.
- Scientific maturity remains `READY_FOR_DRY_RUN`; execution authorization
  was the separate two-window bounded qualification only.

Runtime identities were rechecked before launch and are preserved in
`evidence/phase1e_bounded_2window/run-20260923T065444Z-02d9a1f1/runtime_identity.json`:

- Worker source SHA256:
  `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e`
- Worker binary SHA256:
  `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`
- Fluid adapter SHA256:
  `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572`
  (Build ID `e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b`). The exact path was
  present in Fluid PID 106933 `/proc/106933/maps`. Adapter source provenance
  remains unresolved.
- OpenFOAM: `OpenFOAM-10`, build `10-c4cf895ad8fa`.
- The version was confirmed using `foamVersion` and `pimpleFoam -help`.
  An earlier `pimpleFoam -version` query is unsupported by this build and
  returned an invalid-option error before a case was supplied; it did not
  advance a solver or enter the coupled runtime. The coupled-run Fluid log
  itself contains no OpenFOAM fatal error.
- preCICE: 3.4.1.
- Structure Python: `/usr/bin/python3.10`, Python 3.10.12, pyprecice metadata
  3.4.0; loaded `/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1`. The loaded
  paths and library hashes are recorded in the runtime identity evidence.

## Restart and physical initial Force

The exact restart was `cases/hh06_single_slice/30/`, global time 30.0 s,
time index 150000, `dt = 0.0002 s`. Final hashes for `30/uniform/time`, `p`,
`U`, `k`, `omega`, `nut`, and the checked `constant/polyMesh` files match the
pre-run values. No numeric CFD time directory other than `30` was written;
the coupled physical window endpoint was 30.0004 s, but the case write
interval did not emit a new time directory.

The first Structure Force input was:

| Component | Expected raw Force (N) | Observed raw Force (N) | Absolute error (N) |
|---|---:|---:|---:|
| Fx | 0.0655270406544 | 0.06552704065480554 | 4.0554e-13 |
| Fy | 0.05872987413554 | 0.058729874135090385 | 4.4961e-13 |
| Fz | -2.44420351566e-21 | 0.0 on the 2-D interface | negligible |

The x/y differences are below the qualified `5e-13 N` tolerance. The first
Force source is correctly identified as global CFD time 30.0 s; the first
structural target is 30.0002 s. The one-time unit chain gives
`(Fx_section, Fy_section) = (2.34025145194, 2.09749550484) N/m` and
`(Fx_strip, Fy_strip) = (4.63369787485, 4.15304109958) N`; no second scaling
was observed.

The OpenFOAM `forces` record at 30.0 s contains pressure
`(0.063811823767, 0.058106728512, -2.753291492e-21) N` and viscous
`(0.0017152168874, 0.00062314562354, 3.0908797634e-22) N`, summing to the
frozen release Force within the output precision. The captured file is
`openfoam_postProcessing/cylinderForces/30/forces.dat` in the run evidence.

## Coupling attempts and Strategy C observations

The raw attempt trace contains 33 entries. Its exact copy is
`evidence/phase1e_bounded_2window/run-20260923T065444Z-02d9a1f1/structure_trace.jsonl`
(SHA256 `2d96f0d2f6fb0cc73290203a379b14336bc25b24951d13598f1d983208f96b74`).
Because the participant's raw trace does not include a run ID, a separate
derived `structure_trace_with_run_id.jsonl` adds only `run_id` and the raw
trace hash; the raw trace is retained unchanged.

| Window | Physical identity `(step, bridge, tick, time, dt)` | Attempts | Retries / rollbacks | Acceptance |
|---|---|---:|---:|---|
| 1 | `(1, 1, 200000, 0.0002, 0.0002)` | 13 | 12 | `accepted_by_precice_before_iteration_limit` |
| 2 | `(2, 2, 400000, 0.0004, 0.0002)` | 20 | 19 | `ACCEPTED_AT_ITERATION_LIMIT` |

There was no third physical window. Window 2's preCICE log reports “All
converged” on attempt 20, but the participant conservatively labels acceptance
at the configured cap, not convergence before the cap.

The trial/write equality check passed exactly on every attempt:
`D_written_to_precice_m == D_trial_interface_m` for all 33 records. Physical
rollback/checkpoint evidence is also consistent: each window has one
checkpointed physical state, q/qdot/qddot hashes are invariant across its
retries, and window 2 starts from window 1's accepted displacement. Transport
identities remain independent and monotonic: sequence `1..33`, request ID
`910001..910033`, transaction ID `1910001..1910033`; all are unique and no
third physical identity appears. All trace numeric values are finite.
Every ANCF attempt reports 3 Newton iterations; nonlinear residuals range from
`7.8269414949e-8` to `9.3229683529e-8` in the participant's reported residual
measure. Full per-attempt values and q/qdot/qddot hashes remain in the trace.

However, the Structure-side trial did **not** change during retries within
either window:

- Window 1: all 13 trials were
  `(1.06338321589e-7, 9.53077718794e-8) m`.
- Window 2: all 20 trials were
  `(5.28449407994e-7, 4.75841005172e-7) m`.

Selected raw attempt pairs (Force values are raw integrated N; displacement is
the Structure interface trial in m):

| Window / iteration | Force input to ANCF (Fx, Fy) | Force read after advance (Fx, Fy) | `D_trial` (x, y) |
|---|---|---|---|
| 1 / 1 | `(0.065527040654806, 0.058729874135090)` | `(0.065527040654806, 0.058729874135090)` | `(1.0633832e-7, 9.5307772e-8)` |
| 1 / 2 | `(0.065527040654806, 0.058729874135090)` | `(0.065527040654806, 0.058729874135090)` | `(1.0633832e-7, 9.5307772e-8)` |
| 1 / 3 | `(0.065527040654806, 0.058729874135090)` | `(0.065527040654806, 0.058729874135090)` | `(1.0633832e-7, 9.5307772e-8)` |
| 1 / 13, accepted | `(0.065527040654806, 0.058729874135090)` | `(0.064407132071680, 0.059086750946048)` | `(1.0633832e-7, 9.5307772e-8)` |
| 2 / 1 | `(0.064407132071680, 0.059086750946048)` | `(0.064407132071680, 0.059086750946048)` | `(5.2844941e-7, 4.7584101e-7)` |
| 2 / 2 | `(0.064407132071680, 0.059086750946048)` | `(0.064407132071680, 0.059086750946048)` | `(5.2844941e-7, 4.7584101e-7)` |
| 2 / 20, accepted at cap | `(0.064407132071680, 0.059086750946048)` | `(0.065785618438038, 0.059162358132904)` | `(5.2844941e-7, 4.7584101e-7)` |

The Force passed to ANCF likewise remained constant within each window. Window
1 used the release Force on all 13 solves; window 2 used the prior accepted
window Force `(0.06440713207168003, 0.05908675094604829) N` on all 20 solves.
Only the Force returned after the final accepted attempt changed:

- Window 1 final returned Force:
  `(0.06440713207168003, 0.05908675094604829) N`.
- Window 2 final returned Force:
  `(0.06578561843803757, 0.05916235813290415) N`.

Thus neither changed returned Force was used by another ANCF retry in its own
window. The first attempt's returned Force was exactly the initial Force. The
Structure trace's own force residual was zero on the non-accepted retries,
and trial-displacement residual was zero after the first attempt. In contrast,
preCICE's logged iteration residuals changed:

- Window 1: displacement `1.43e-7 -> 9.81e-9 m`; Force
  `1.18e-3 -> 8.08e-5 N`.
- Window 2: displacement `5.68e-7 -> 8.19e-9 m`; Force
  `2.50e-3 -> 5.24e-4 N`.

The trace also advances `force_source_global_time_s` on a retry even when the
numeric Force is unchanged (for example, window 1 attempt 2 labels the
unchanged 30.0 s F0 as 30.0002 s). That timestamp is not valid evidence that a
new Force iterate was consumed.

### Finding and responsible layer

The old “write committed motion on every retry” pattern was **not** observed:
the participant passed its current ANCF trial to `write_data()` each time.
Nevertheless, the full implicit fixed-point contract failed because the
Structure solve did not consume the changing Force iterate visible in
preCICE's convergence process. This run therefore demonstrates that
`D_written == D_trial` alone is insufficient to establish a functioning
implicit iteration.

The responsible code path is the Structure-side preCICE backend:
`src/coupling/arbitrary_n_live_orchestration_v1/precice_backend.py:98-102`
hardcodes `relativeReadTime = 0.0` in `read_force()`. The installed preCICE
3.4.1 API header `/usr/include/precice/Participant.hpp:846-849` states that
relative time zero reads the beginning of the current time step and `dt`
reads its end. During retry, preCICE reports changing, nonzero Force
convergence residuals while the backend returns the start-of-step sample to
Structure. The logs report residual norms, not the full Force vector; together
with the repeated numeric Structure input, this supports the stale-read
diagnosis. The exact post-advance read-time contract must be
resolved offline before any further real run; no fix is implemented here.

## Fluid/ALE and process observations

The only emitted fluid stability diagnostic was the standard fluid Courant
number: 34 samples, mean range `0.01601185442..0.01601199855`, maximum
`0.4182184878`. The current case did not emit mesh Courant, mesh velocity
maximum, max `|U|`, max `k`, max `omega`, max `nut`, minimum cell volume, or
mesh non-orthogonality/skew. No additional mesh-quality pass was run, so
positive minimum cell volume was **not independently verified**. No FSI power
was captured. The solver logs contain no fatal error, NaN/Inf, or floating
point failure; they do contain the adapter's existing `runTimeModifiable`
warning. These unavailable diagnostics are explicitly recorded in
`fluid_metrics.json` rather than inferred.

Observed PIDs: launcher 106532, Structure 106932, Fluid 106933, worker 106934.
The launcher completed with exit 0; Fluid and Structure both exited 0. The
worker shutdown was requested by Structure and its PID was absent afterward,
but its independent exit code is not exposed by the participant/launcher
summary. Worker stdout is the persistent protocol stream consumed by Structure;
the runtime did not emit a separate worker log. No orphan participant/worker
remained; the configured socket directory had no files/sockets and the launch
lock was released. No forced
termination occurred. Details are in `process_cleanup.json` and the copied
preCICE profiling files.

## Final interpretation and stop

The exact two-window run completed as authorized, but it is **not** a pass for
the corrected real implicit lifecycle. The original stale-committed-motion
write is absent; the current failure is stale endpoint Force consumption on
retry. Do not infer that the historical late-window ALE/flow/turbulence runaway
is fixed or tested by these two windows. No 5-window, 25-window, long-run, or
three-slice work was started.

Required final classification: `FAIL_REAL_IMPLICIT_CONTRACT`.

No production source/configuration, timestep, force scaling, relaxation,
turbulence, mesh, or damping changes were made. Evidence and this report are
uncommitted pending review. The next action should be limited to an offline
preCICE 3.4.1 read-time/Force-iterate contract test and a reviewed Structure
backend design; another real runtime requires separate explicit authorization.
