# Phase 1H.7 — Five-window IQN-ILS controlled comparison

**Primary classification: `IQN_IMPROVES_SINGLE_SLICE_EFFICIENCY`**

In this one paired, five-window experiment on the current single-slice interface, IQN-ILS reduced coupling attempts from 93 to 23, removed all four baseline iteration-cap acceptances, and reduced measured preflight-to-exit elapsed time from 96.905 s to 24.649 s. This is evidence of an efficiency improvement for this interface and this run pair only. It is not evidence of HH06 validation, long-run stability, or behavior of a multi-slice interface.

## Scope and controlled setup

Exactly two independent five-window runs were performed, baseline first and IQN-ILS second. Each started from a fresh scratch copy of `cases/hh06_single_slice/30/` at global time 30.0 s. Neither run continued from the other. The source restart fields, mesh and relevant runtime configuration hashes matched between runs and were rechecked unchanged after execution.

Both runs used `dt = 0.0002 s`, `max_iterations = 20`, and `max_windows = 5`, with the same physics, ANCF settings, convergence criteria and initial Force. The only XML behavior difference was the acceleration block; both scratch configurations used the same run-specific exchange/socket path. The production case XML and restart were not changed by these runs.

| Variant | Acceleration | Source XML SHA-256 | Scratch XML SHA-256 |
|---|---|---|---|
| Baseline | Constant relaxation, `0.2` | `e4987ec7d768517feefe312a9ddcbd391ff052981aa84bae6934b555e97d1f71` | `2cc3e3e0e7fa420a8f56973e100ed9ba7f45ad36a5f966ff99e482e1307bd05d` |
| IQN-ILS | initial relaxation `0.2` (`enforce=true`); `max-used-iterations=1`; `time-windows-reused=1`; residual-sum preconditioner; QR3 filter (`limit=1e-2`); reduced time grid | `cd943e0cfa04d7937d6a421305a032a642ae5a80d7e842b6a1651ec11517bff9` | `e31ca2fc59a1f91644b8dc367ee976fff9a5df3baf51f7cfd20da59c98aa981a` |

The run preparation manifest records that, after the common scratch socket-path adjustment, only the acceleration block differed. Both preflights returned `PASS_PREFLIGHT_ONLY`.

## Runtime identities and release-force check

Both runs used branch `repair/worker-lineage-implicit-contract-v1`, HEAD `02d9a1f180082e83bcc9f7acdcb090502262b2d1`, and the same identities:

| Component | Qualified runtime identity |
|---|---|
| Worker source | `src/ancf/ancf_worker_main.cpp`, SHA-256 `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e` |
| Worker binary | `/home/machao/projects/CFD_ANCF_VIV_V2/build/phase1d6_worker/cfd_ancf_ancf_kernel_worker`, SHA-256 `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596` |
| Fluid adapter | `/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so`, SHA-256 `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572`, Build ID `e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b` |
| preCICE | Runtime 3.4.1; loaded library `/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1`, SHA-256 `b20729622d2dbbafdea3d6ead0480ec66be98cb947db3500cc3c27ed4e3039c7` |
| OpenFOAM | Version 10; `/opt/openfoam10/platforms/linux64GccDPInt32Opt/bin/pimpleFoam` |
| Structure Python binding | `/usr/bin/python3.10`, Python 3.10.12; pyprecice metadata 3.4.0; the loaded preCICE runtime was 3.4.1 |

The adapter source provenance remains unresolved; the runtime binary was SHA-pinned and matched the qualified identity in both runs. Both participant processes exited with code 0, and the worker was absent after shutdown.

Frozen physical release Force was `F0_raw = (0.0655270406544, 0.05872987413554, -2.44420351566e-21) N`, sourced at global time 30.0 s. Both traces show first Structure input `(0.06552704065480554, 0.058729874135090385, 0.0) N`; x/y differences from the frozen values are approximately `4.06e-13 N` and `4.50e-13 N`, within the qualified `<5e-13 N` tolerance. The first target window was 30.0002 s. Force conversion and scaling were unchanged.

## Primary A/B results

| Metric | Baseline | IQN-ILS |
|---|---:|---:|
| Iterations by window | 13, 20, 20, 20, 20 | 3, 5, 5, 5, 5 |
| Windows converged before cap | 1/5 | 5/5 |
| Accepted at iteration limit | 4/5 | 0/5 |
| Total coupling attempts | 93 | 23 |
| Rollbacks | 88 | 18 |
| Fluid/preCICE advance calls | 93 | 23 |
| Monotonic elapsed time, preflight start to both participants exit | 96.905 s | 24.649 s |
| Mean elapsed time per attempt | 1.0420 s | 1.0717 s |
| ANCF Newton iterations | 279 total; 3 per attempt | 69 total; 3 per attempt |

IQN-ILS reduced attempts and Fluid advances by `75.27%`; measured total elapsed time fell by `74.56%`. Mean elapsed time per attempt was `2.85%` higher with IQN-ILS, so the total-time gain is explained by fewer attempts rather than cheaper individual attempts. The timer used `time.monotonic_ns()`, includes the per-run preflight (about 0.58 s), and ends after both participants exit; scratch-copy preparation is outside that timer.

The first window illustrates that Force iterates were consumed and that the current ANCF trial was the displacement written on each attempt:

| Variant / iteration | Force input to ANCF `(Fx,Fy)` N | Force returned after advance `(Fx,Fy)` N | `D_trial = D_written` `(Dx,Dy)` m |
|---|---|---|---|
| Baseline 1 | `(0.065527040655, 0.058729874135)` | `(0.065303058938, 0.058801249497)` | `(1.0633832e-7, 9.5307772e-8)` |
| Baseline 2 | `(0.065303058938, 0.058801249497)` | `(0.065123873565, 0.058858349787)` | `(1.0597484e-7, 9.5423601e-8)` |
| Baseline 3 | `(0.065123873565, 0.058858349787)` | `(0.064980525266, 0.058904030019)` | `(1.0568406e-7, 9.5516264e-8)` |
| IQN-ILS 1 | `(0.065527040655, 0.058729874135)` | `(0.065303058938, 0.058801249497)` | `(1.0633832e-7, 9.5307772e-8)` |
| IQN-ILS 2 | `(0.065303058938, 0.058801249497)` | `(0.064407132072, 0.059086750946)` | `(1.0597484e-7, 9.5423601e-8)` |
| IQN-ILS 3 | `(0.064407132072, 0.059086750946)` | `(0.064407132072, 0.059086750946)` | `(1.0452092e-7, 9.5886917e-8)` |

Across all attempts, `D_written_to_precice == D_trial_interface` exactly. Transport IDs were monotonic and unique within each run: baseline sequence `1..93`, request IDs `910001..910093`, transaction IDs `1910001..1910093`; IQN-ILS sequence `1..23`, request IDs `910001..910023`, transaction IDs `1910001..1910023`. Both traces cover precisely windows 1–5.

## Convergence and acceleration diagnostics

The preCICE iterations logs report baseline convergence flags `1,0,0,0,0` and IQN-ILS flags `1,1,1,1,1`. Thus the baseline completed its later windows at the configured cap without convergence, while IQN-ILS converged all five before the cap. The conservative classifications in the attempt data are `converged_before_cap` or `ACCEPTED_AT_ITERATION_LIMIT`; cap acceptance is not labelled convergence.

Final-attempt values from the Structure trace are shown below. These are participant-trace residual fields, not the anomalous preCICE per-data log values discussed next.

| Window | Baseline final force residual raw / applied (N) | Baseline final trial-displacement residual (m) | IQN-ILS final force residual raw / applied (N) | IQN-ILS final trial-displacement residual (m) |
|---:|---:|---:|---:|---:|
| 1 | `8.0773e-5 / 5.7118e-3` | `3.2770e-11` | `0 / 0` | `1.5260e-9` |
| 2 | `5.2024e-4 / 3.6788e-2` | `2.1106e-10` | `0 / 0` | `0` |
| 3 | `2.5185e-3 / 1.7809e-1` | `1.0212e-9` | `1.4088e-6 / 9.9619e-5` | `2.8297e-12` |
| 4 | `6.5066e-3 / 4.6011e-1` | `2.6397e-9` | `0 / 0` | `0` |
| 5 | `1.2390e-2 / 8.7613e-1` | `5.0266e-9` | `0 / 0` | `0` |

Full per-attempt Force input/return, read-offset, motion, residual and ANCF histories are preserved in each `structure_trace.jsonl` and summarized by window in each `run_summary.json`.

IQN-ILS `iterations.log` diagnostics were:

| Window | Iterations | Convergence | QN columns | Deleted columns | Dropped columns |
|---:|---:|---:|---:|---:|---:|
| 1 | 3 | 1 | 1 | 0 | 1 |
| 2 | 5 | 1 | 1 | 0 | 5 |
| 3 | 5 | 1 | 1 | 0 | 9 |
| 4 | 5 | 1 | 1 | 0 | 13 |
| 5 | 5 | 1 | 1 | 0 | 17 |

No QR3-deleted columns were reported. `precice-accelerationInfo.log` was absent; preCICE 3.4.1 documents that this additional log is only available when enabled in the source. The candidate configured the `residual-sum` preconditioner, but the stock runtime logs did not separately expose its runtime status.

### Residual-log observability limitation

Both runs' `precice-Fluid_0000-convergence.log` files show **exactly zero** for every iteration in both `ResAbsOrRel(Structure-Mesh:Displacement)` and `ResAbsOrRel(Structure-Mesh:Force)`. These values do not agree with the nonzero, changing participant trace residuals above, nor with the different overall convergence flags between the two configurations. preCICE documents the convergence log as containing per-iteration data residuals, while the iterations log records window iteration counts and convergence flags; the IQN column counters are also logged there ([preCICE 3.4.1 output-file documentation](https://precice.org/running-output-files)). Consequently, the zero per-data values are recorded as an observability anomaly and are **not** interpreted as valid evidence that either variable's residual was zero. The overall window outcome is taken from the iterations log and its matching cap/convergence classification; no claim is made here about which individual data measure limited convergence.

The IQN Fluid output also contains three warnings that the coupling residual was “almost zero.” They are preserved verbatim in `iqn_ils/fluid.stdout`; they make the residual-log anomaly especially important and should be investigated before using those per-data residual columns as a quantitative convergence history. Both runs emitted the same non-fatal adapter warning about `runTimeModifiable` when `adjustableTimestep` is disabled; neither run changed `deltaT`. No participant fatal error was observed.

## Fluid observations and run completion

The OpenFOAM logs expose fluid Courant numbers but do not emit mesh Courant number, mesh-velocity maximum, `U`/`k`/`omega`/`nut` extrema, cell-volume minimum, or mesh-quality extrema. No additional diagnostic pass or solver change was introduced for this comparison. Maximum logged fluid Courant numbers were `0.420761851` (baseline) and `0.4207895528` (IQN-ILS). These short-run observations are not a stability qualification.

Both runs completed exactly five physical windows; no sixth window was attempted. Structure and Fluid exited with code 0 in both runs. The worker process was observed during execution and was absent afterward. No participant stderr output was recorded. Each scratch restart-input set remained unchanged after its run. The run-specific preCICE exchange directory has no remaining files/socket entries.

## Conclusion and limits

For this single-slice, five-window A/B pair, IQN-ILS materially improved coupling efficiency: 23 attempts and 0 cap acceptances versus 93 attempts and 4 cap acceptances for constant relaxation 0.2. The effect is consistent across all five windows and is accompanied by real preCICE convergence flags, while the Structure trace confirms the write-current-trial contract throughout.

This was one ordered pair of runs, not a repeated or randomized benchmark. Per-data convergence-log values are anomalous, and IQN emitted near-zero-residual warnings; therefore this result should be reviewed with that observability limitation in mind. It applies only to the current low-dimensional single-slice interface. It does **not** establish HH06 validation, VIV reproduction, long-run stability, elimination of the historical 25-window runaway, or whether IQN-ILS generalizes to a multi-slice interface. No 25-window run, tuning, or three-slice work was started.

## Evidence and repository state

Unique run directory: `evidence/phase1h7_iqn_comparison/run-20260923T120142Z-02d9a1f-pid138712/`. Curated run outputs remain at this path. The two full scratch case trees are preserved in the external archive at `/home/machao/projects/CFD_ANCF_VIV_V2_phase1h_scratch_archive/phase1h7_iqn_comparison/`; the per-file SHA256 manifest is [indexed here](../evidence/phase1h_external_archive/archive_index.json).

Primary artifacts:

- `qualification_summary.json` — direct A/B totals and primary classification.
- `preparation_manifest.json` — restart, force provenance, and configuration hashes.
- `baseline/` and `iqn_ils/` — runtime identities, preflights, process cleanup, participant logs, traces, preCICE iteration/convergence logs, and profiling outputs. The copied `case/` directories containing restart fields and mesh are archived outside Git as recorded in the index above.
- `scripts/phase1h7_iqn_ab.py` — one-shot preparation/execution and evidence validator used for the pair.

The run used source HEAD `02d9a1f180082e83bcc9f7acdcb090502262b2d1`. The Phase 1H.7 runner was subsequently committed in `e24197d`; this report and curated evidence are being preserved in the Phase 1H evidence commit. No run data or conclusion was changed by that source-control step.
