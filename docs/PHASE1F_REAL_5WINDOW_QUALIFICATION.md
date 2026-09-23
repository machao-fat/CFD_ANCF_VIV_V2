# Phase 1F — Real 5-Window Strategy C Qualification

## Result

**Classification: `PASS_REAL_5WINDOW_STRATEGY_C`**

One bounded real OpenFOAM–preCICE–ANCF run completed exactly five physical windows (`dt = 0.0002 s`, ending at case-local `0.001 s` / global `30.001 s`). This pass means the corrected coupling lifecycle completed the bounded interval without a protocol/runtime failure or an observed ALE/flow runaway in the diagnostics emitted by this run. It does **not** mean every window converged: windows 2–5 were accepted at the configured 20-iteration limit. It does not establish HH06 validation, long-run stability, or removal of the historical 25-window runaway.

No second run was started. No numerical parameter was changed during the runtime. There were no solver, adapter, ANCF-kernel, worker, mesh, turbulence, force-scaling, timestep, damping, or relaxation changes in this qualification.

## Runtime identity and bounds

- Run: `run-20260923T103144Z-pid128756`
- Branch / HEAD: `repair/worker-lineage-implicit-contract-v1` / `02d9a1f180082e83bcc9f7acdcb090502262b2d1`
- Preflight: `PASS_PREFLIGHT_ONLY`
- Authorization: `BOUNDED_COUPLING_QUALIFICATION`, exactly 5 windows
- `dt = 0.0002 s`; preCICE `max-iterations = 20`
- OpenFOAM 10, build `10-c4cf895ad8fa`; executable `/opt/openfoam10/platforms/linux64GccDPInt32Opt/bin/pimpleFoam`
- preCICE runtime 3.4.1, loaded from `/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1`, SHA256 `b20729622d2dbbafdea3d6ead0480ec66be98cb947db3500cc3c27ed4e3039c7`
- Structure runtime `/usr/bin/python3.10`; Python 3.10.12; pyprecice metadata 3.4.0
- Worker source SHA256 `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e`; worker binary SHA256 `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`
- Fluid adapter SHA256 `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572`, Build ID `e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b`. Adapter source provenance remains unresolved; this result is pinned to the qualified runtime binary only.

The exact restart was `cases/hh06_single_slice/30/`, global time 30.0 s, index 150000. Pre-launch hashes for `uniform/time`, `p`, `U`, `k`, `omega`, and `nut` match the hashes after the run; the recorded mesh hashes also match. Thus the authoritative 30.0 s restart inputs were not modified. Full hashes and live runtime identity are in [runtime_identity.json](../evidence/phase1f_bounded_5window/run-20260923T103144Z-pid128756/runtime_identity.json).

## Initial release Force and iteration lifecycle

The first Structure input was `[0.06552704065480554, 0.058729874135090385, 0] N`. Compared with the frozen release Force `[0.0655270406544, 0.05872987413554] N`, the x/y absolute differences were `4.06e-13 N` and `4.50e-13 N`, respectively, within the qualified `5e-13 N` tolerance. The input is sourced from the global 30.0 s restart and used for the first trial targeting 30.0002 s. The z component is zero on the 2-D mapped interface; the source release value was `-2.44420351566e-21 N`.

There were 93 attempt records. For every attempt, `D_written_to_precice == D_trial_interface` exactly. Across retries, the Force input exactly matched the Force returned by the preceding advance; at a new physical window, the next window started from the accepted preceding exchange rather than resetting to F0. Physical identity stayed fixed within each window and advanced once at the next window. Sequence, request ID, and transaction ID were each unique and strictly monotonic over attempts 1–93.

The first five causal Force/trial pairs were:

| Window / iteration | Force input raw `[Fx,Fy]` N | Force returned raw `[Fx,Fy]` N | Trial displacement `[Dx,Dy]` m |
|---|---:|---:|---:|
| 1 / 1 | `[0.06552704, 0.05872987]` | `[0.06530306, 0.05880125]` | `[1.06338e-7, 9.53078e-8]` |
| 1 / 2 | `[0.06530306, 0.05880125]` | `[0.06512387, 0.05885835]` | `[1.05975e-7, 9.54236e-8]` |
| 1 / 3 | `[0.06512387, 0.05885835]` | `[0.06498053, 0.05890403]` | `[1.05684e-7, 9.55163e-8]` |
| 1 / 4 | `[0.06498053, 0.05890403]` | `[0.06486585, 0.05894057]` | `[1.05451e-7, 9.55904e-8]` |
| 1 / 5 | `[0.06486585, 0.05894057]` | `[0.06477410, 0.05896981]` | `[1.05265e-7, 9.56497e-8]` |

## Per-window results

Residual ranges below are attempt-level norms recorded by the Structure participant. An iteration-cap acceptance is explicitly not convergence.

For windows 3–5, the final raw force residual remained above the configured absolute force convergence limit (`1e-3 N`). Those windows were accepted only because the iteration cap was reached; this report does not classify them as converged.

| Window | Attempts | Acceptance | Force residual raw (N), min–max; final | Trial displacement residual (m), min–max; final | Accepted interface trial `[Dx,Dy]` m |
|---:|---:|---|---:|---:|---:|
| 1 | 13 | `accepted_by_precice_before_iteration_limit` | `2.019e-5–2.351e-4`; `8.077e-5` | `3.277e-11–1.428e-7`; `3.277e-11` | `[1.04646e-7, 9.58471e-8]` |
| 2 | 20 | `ACCEPTED_AT_ITERATION_LIMIT` | `1.301e-4–2.780e-2`; `5.202e-4` | `2.111e-10–5.657e-7`; `2.111e-10` | `[5.23303e-7, 4.77559e-7]` |
| 3 | 20 | `ACCEPTED_AT_ITERATION_LIMIT` | `6.293e-4–1.396e-1`; `2.518e-3` | `1.021e-9–1.128e-6`; `1.021e-9` | `[1.35592e-6, 1.23295e-6]` |
| 4 | 20 | `ACCEPTED_AT_ITERATION_LIMIT` | `1.627e-3–3.612e-1`; `6.507e-3` | `2.640e-9–1.666e-6`; `2.640e-9` | `[2.58398e-6, 2.34298e-6]` |
| 5 | 20 | `ACCEPTED_AT_ITERATION_LIMIT` | `3.097e-3–6.878e-1`; `1.239e-2` | `5.027e-9–2.160e-6`; `5.027e-9` | `[4.17249e-6, 3.77592e-6]` |

Each attempt reported 3 ANCF Newton iterations. The per-window ANCF residuals were finite, ranging from `7.827e-8` to `1.446e-7`. Across all attempts there were 88 rollback retries followed by one accepted attempt in each window. The accepted displacement of each window became the committed reference of the next window.

## Fluid/ALE observations and historical comparison

- OpenFOAM emitted 94 fluid Courant samples. Mean Co ranged from `0.0157955` to `0.0160120`; maximum fluid Co was `0.420761851`.
- No OpenFOAM/preCICE fatal error, NaN/Inf field marker, participant crash, or non-finite trace value was observed. Fluid and Structure stderr files are empty.
- Mesh Courant, maximum mesh velocity, `Umax`, `kmax`, `omega_max`, `nut_max`, minimum cell volume, and mesh-quality extrema were not emitted by the existing runtime diagnostics. They are recorded as unavailable; no extra quality pass or solver/physics change was made.
- The dimensional cylinder force output remains at `cases/hh06_single_slice/postProcessing/cylinderForces/30/forces.dat` (SHA256 `c9d07e97b1323849cb62cfdd1008635fd3567b51f98efcc54f77cb911dd85413`); its final logged global time is 30.001 s. The full OpenFOAM stdout log is preserved in the run directory.
- The previous late-window ALE/flow/turbulence runaway was **not observed within these five windows in the available diagnostics**. This only covers 1 ms of coupled physical time and cannot establish that the old 25-window runaway is eliminated or delayed.

## Shutdown and evidence

Fluid and Structure exited with code 0; the launcher exited with code 0. The worker PID was absent after shutdown and there was no orphan participant/worker. The worker's independent exit code is not exposed by the launcher. The configured socket location had no files or active users after shutdown; an empty `precice-run` directory remained and was not removed. Process details are in [process_cleanup.json](../evidence/phase1f_bounded_5window/run-20260923T103144Z-pid128756/process_cleanup.json).

Run evidence: [structure_trace.jsonl](../evidence/phase1f_bounded_5window/run-20260923T103144Z-pid128756/structure_trace.jsonl), [fluid.stdout](../evidence/phase1f_bounded_5window/run-20260923T103144Z-pid128756/fluid.stdout), [structure.stdout](../evidence/phase1f_bounded_5window/run-20260923T103144Z-pid128756/structure.stdout), [qualification_summary.json](../evidence/phase1f_bounded_5window/run-20260923T103144Z-pid128756/qualification_summary.json), and [runtime_identity.json](../evidence/phase1f_bounded_5window/run-20260923T103144Z-pid128756/runtime_identity.json). The earlier Phase 1E failed trace and Phase 1E-R successful trace remain unchanged; their SHA256 values were rechecked.

The worktree remains uncommitted. HEAD is unchanged. The pre-existing accepted Phase 1E.6 changes and the narrowly scoped five-window launch-profile changes remain in the dirty worktree alongside this report/evidence; no commit was created.

**Stop condition met. No 25-window run, parameter tuning, or three-slice work was started.**
