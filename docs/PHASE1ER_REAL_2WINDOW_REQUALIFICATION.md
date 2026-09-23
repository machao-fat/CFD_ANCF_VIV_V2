# Phase 1E-R — Real 2-Window Strategy C Requalification

**Primary classification: `REAL_IMPLICIT_FORCE_ITERATION_CONTRACT_PASS`**

The one authorized real run completed exactly two physical windows. The repaired
Structure backend consumed the Force returned by the immediately preceding
advance on every same-window retry. Force inputs and ANCF interface trials
changed on every attempt; the written interface displacement exactly equaled
the current ANCF trial in all 33 attempts. This qualifies the real implicit
Force-iteration contract for this bounded run only. It does not validate HH06,
establish long-run stability, or show that the historical 25-window runaway is
fixed.

## Run identity and bounds

- Logical run ID: `run-20260923T101509Z-02d9a1f1`
- Launcher output directory: `evidence/phase1e_bounded_2window/run-20260923T101509Z-pid124039/`
- Branch / HEAD: `repair/worker-lineage-implicit-contract-v1` / `02d9a1f180082e83bcc9f7acdcb090502262b2d1`
- Bounds: `max_windows=2`, `dt=0.0002 s`, `max_iterations=20`
- Preflight before launch: `PASS_PREFLIGHT_ONLY`, exit 0. One `--run-bounded`
  command was issued; no second runtime attempt was made.
- Post-run preflight: `PASS_PREFLIGHT_ONLY`, exit 0; it rechecked the restart,
  identities, socket availability, and the exact two-window authorization.
- Launcher runtime result: `BOUNDED_RUNTIME_COMPLETED`; Fluid and Structure exit
  codes were both 0. Trace contains windows 1 and 2 only; no third window.

The prior Phase 1E failure directory was not overwritten. Its trace,
`runtime_identity.json`, and `qualification_summary.json` hashes remain
`2d96f0d2…f96b74`, `9960579…0991f`, and `b5d4a416…21e12`, respectively.

## Runtime and restart identities

| Component | Observed identity |
|---|---|
| Worker source | `src/ancf/ancf_worker_main.cpp`, SHA256 `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e` |
| Worker binary | `/home/machao/projects/CFD_ANCF_VIV_V2/build/phase1d6_worker/cfd_ancf_ancf_kernel_worker`, SHA256 `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`, Build ID `f1e2a4d34ca5c4fe8bb3ccfbf6d695a34b88c512` |
| Fluid adapter | `/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so`, SHA256 `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572`, Build ID `e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b`; exact path was present in Fluid PID 124433 `/proc/124433/maps` |
| preCICE | Runtime `3.4.1`, `/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1`, SHA256 `b20729622d2dbbafdea3d6ead0480ec66be98cb947db3500cc3c27ed4e3039c7`; loaded in Fluid and Structure |
| Python Structure | `/usr/bin/python3.10`, Python `3.10.12`, pyprecice metadata `3.4.0`; exact qualified module/extension identity revalidated by both preflights |
| OpenFOAM | OpenFOAM 10, build `10-c4cf895ad8fa`; `/opt/openfoam10/platforms/linux64GccDPInt32Opt/bin/pimpleFoam` |

`ADAPTER_RUNTIME_BINARY_PINNED=YES`; `ADAPTER_SOURCE_PROVENANCE_RESOLVED=NO`.
The source-to-binary provenance limitation remains unchanged. The run used the
accepted Phase 1E.6 worktree changes: backend SHA256
`e5f37644e1b31391aed48c47473e336733e0c492191b166ed6354b2a3eb07cf6`, participant
SHA256 `da578e517948c8facfdd3cfe22c01fb0df29c19a6fa48a11ecf646705c1f8cca`, and
test SHA256 `e74d9c9641ccb5062e485bafa2546c1ddd7ba0513ba12fbd9a4e0f1825c44fa6`.
These changes were uncommitted at HEAD before and after the run; no source or
configuration file was edited during this qualification.

The exact restart remained at directory `30`, time `30.0 s`, index `150000`,
`dt=0.0002 s`. Pre- and post-run preflight passed the frozen restart field,
mesh, and runtime-configuration hashes. In particular, the hashes of
`30/uniform/time`, `p`, `U`, `k`, `omega`, and `nut` matched their frozen values.
Only the numeric time directory `30` remained. Frozen release-force evidence
was unchanged.

## Initial Force and read-time behavior

Expected raw release Force at source time `30.0 s`:
`(0.0655270406544, 0.05872987413554, -2.44420351566e-21) N`.

The first Structure input was
`(0.06552704065480554, 0.058729874135090385, 0.0) N`; x/y absolute errors were
`4.0554e-13 N` and `4.4961e-13 N`, inside the qualified `5e-13 N` tolerance.
The interface reports 2-D, hence Fz is zero there. The physical source time is
30.0 s; the first target window is 30.0002 s. The established conversion was
applied once: the initial applied strip Force was approximately
`(4.63369787485, 4.15304109958) N`.

For the first attempt of each window, the starting/boundary Force was read at
relative offset `0.0`. After an advance requesting a retry, the returned Force
was read at `dt=0.0002 s` and became the next attempt's ANCF input. After an
accepted window, the boundary Force was read at `0.0` and seeded the next
physical window. The trace explicitly records input and returned Force,
offset, source kind, window, and iteration separately.

## Before/after against the Phase 1E failure

The preserved old trace had one Force input and one trial displacement per
window: window 1 used the release Force on all 13 attempts; window 2 used
`(0.06440713207168003, 0.05908675094604829) N` on all 20 attempts. The trial
was constant within each window (`1.0633832e-7, 9.5307772e-8 m` in window 1;
`5.2844941e-7, 4.7584101e-7 m` in window 2).

In this run each Force input and each interface trial was distinct across the
attempts of its window: 13/13 unique Force inputs and trials in window 1, and
20/20 in window 2. For every same-window retry, the next input exactly equaled
the preceding attempt's `returned_force_raw_N`. Window 2's initial input
exactly equaled the Force returned by accepted window 1—not the original F0.

Selected raw Force pairs (N) and interface trial displacement (m):

| Window / attempt | Force input to ANCF `(Fx,Fy)` | Force returned after advance `(Fx,Fy)` | `D_trial=(Dx,Dy)` | Returned read offset |
|---|---|---|---|---:|
| 1 / 1 | `(0.065527040655, 0.058729874135)` | `(0.065303058938, 0.058801249497)` | `(1.0633832e-7, 9.5307772e-8)` | `dt` |
| 1 / 2 | `(0.065303058938, 0.058801249497)` | `(0.065123873565, 0.058858349787)` | `(1.0597484e-7, 9.5423601e-8)` | `dt` |
| 1 / 3 | `(0.065123873565, 0.058858349787)` | `(0.064980525266, 0.058904030019)` | `(1.0568406e-7, 9.5516264e-8)` | `dt` |
| 1 / 13, accepted | `(0.064484091604, 0.059062226558)` | `(0.064407132072, 0.059086750946)` | `(1.0464581e-7, 9.5847119e-8)` | `0` |
| 2 / 1 | `(0.064407132072, 0.059086750946)` | `(0.044033629712, 0.040166204284)` | `(5.2170203e-7, 4.7799117e-7)` | `dt` |
| 2 / 2 | `(0.044033629712, 0.040166204284)` | `(0.048384010010, 0.043965445970)` | `(4.8863959e-7, 4.4728660e-7)` | `dt` |
| 2 / 3 | `(0.048384010010, 0.043965445970)` | `(0.051864314248, 0.047004839319)` | `(4.9569945e-7, 4.5345207e-7)` | `dt` |
| 2 / 20, accepted at cap | `(0.065393683780, 0.058820207445)` | `(0.065785531202, 0.059162412714)` | `(5.2330302e-7, 4.7755861e-7)` | `0` |

`D_written_to_precice == D_trial_interface` exactly in all 33 rows. Trial
displacement changed with the consumed Force iterate (though the window-1
changes are small); no stale committed-motion repetition was observed.

## Attempts, rollback, residuals, and acceptance

| Window | Attempts | Rollbacks | Physical identity | Result |
|---|---:|---:|---|---|
| 1 | 13 | 12 | `(step=1, bridge=1, tick=200000, t=0.0002, dt=0.0002)` | `accepted_by_precice_before_iteration_limit` |
| 2 | 20 | 19 | `(step=2, bridge=2, tick=400000, t=0.0004, dt=0.0002)` | `ACCEPTED_AT_ITERATION_LIMIT` |

Each window created one physical checkpoint. Each retry row records
`rollback_request=true` and `commit_status=rolled_back`; the accepted row
commits. Physical identity stayed fixed through retries and advanced exactly
once between windows. Window 2's `D_previous_committed` equals the accepted
window-1 trial. Sequence IDs were `1..33`, request IDs `910001..910033`, and
transaction IDs `1910001..1910033`; all were unique and strictly monotonic.
The coordinator rollback call is recorded for every rejected trial. The live
trace records trial-state hashes but does not emit a separate post-rollback
q/qdot/qddot snapshot; exact restore remains covered by the accepted offline
checkpoint regression rather than being independently hash-compared after
each real rollback.

Force residual here is the Structure trace's raw norm of returned Force minus
the Force used by that attempt; trial displacement residual is the norm against
the previous trial (or the committed interface displacement on attempt 1).
Both now carry nonzero iteration information:

| Window | Raw Force residual range (N) | Trial-displacement residual range (m) | ANCF Newton / residual |
|---|---:|---:|---|
| 1 | `2.0193e-5 .. 2.3508e-4` | `3.2770e-11 .. 1.4280e-7` | 3 iterations; `7.82694e-8` each attempt |
| 2 | `1.3006e-4 .. 2.7804e-2` | `2.1106e-10 .. 5.6566e-7` | 3 iterations; `9.32297e-8` each attempt |

Window 1 was accepted before the cap at attempt 13. Window 2 was accepted
exactly at the 20-iteration limit and is deliberately **not** called converged.
At its final logged preCICE check, displacement's absolute residual was
`1.11e-8` against `1.00e-8` and its relative residual was `1.57e-2` against
`1.00e-5`; the runtime proceeded because the configured iteration cap was
reached. No iteration-cap tuning was made.

## Fluid diagnostics and cleanup

OpenFOAM emitted 34 fluid Courant samples: mean ranged
`0.01601185442..0.01601199855`; maximum fluid Co was `0.4182184878`. The case
did not emit mesh Co, max mesh velocity, max `|U|`, max `k`, max `omega`, max
`nut`, or minimum cell volume. No extra quality pass or solver/configuration
change was made; minimum volume was not independently verified. The existing
adapter `runTimeModifiable` warning appeared; neither participant log contains
a fatal error, NaN/Inf, or solver failure.

Observed PIDs: launcher 124039, Structure 124432, Fluid 124433, worker 124434.
Fluid and Structure exited 0; the launcher exited 0. The worker PID was absent
after Structure shutdown, but an independent worker exit code is not exposed by
the launcher. Post-run process/socket preflight found no active participants,
no stale socket files, and no stale socket user; the socket tree retained only
an empty `precice-run` directory. No orphan runtime process remained.

## Evidence and interpretation boundary

Raw attempt trace SHA256:
`33266a748588efc115d14121645cc67f660afc734243d214c00042a1dc3fe14c`.
The raw `structure_trace.jsonl`, `structure_audit.json`, `launch_summary.json`,
and Fluid/Structure stdout/stderr are preserved in the launcher output
directory above. Companion `runtime_identity.json`,
`qualification_summary.json`, `fluid_metrics.json`,
`process_cleanup.json`, and `proc_maps_observation.txt` are in that same
directory.

The result confirms that the stale retry Force-read mechanism observed in
Phase 1E is absent in this real two-window run. It does not address whether the
historical 25-window ALE/flow/turbulence runaway is eliminated, delayed, or
unchanged. No 5-window or 25-window run, parameter tuning, or three-slice work
was started. Stop here pending review and separate authorization.
