# Phase 1H.8 — IQN-ILS History-Length Sensitivity

## Result

**Classification: `IQN_HISTORY_DEGRADES`.** Increasing `max-used-iterations` from 1 to 2 or 3 did not reduce coupling iterations, attempts, CFD advances, or measured wall time in this two-window study. Both larger-history candidates repeatedly emitted preCICE's warning that the least-squares column count exceeded half the primary-unknown count and could become ill-conditioned. The classification reflects that adverse numerical-risk evidence; it does not mean this short run diverged or took materially longer.

No production XML, source, physics, or restart was changed by this study. No 5- or 25-window run was performed.

## Controlled setup and provenance

- Run ID: `run-20260923T123908Z-02d9a1f-pid143932`
- Branch / HEAD: `repair/worker-lineage-implicit-contract-v1` / `02d9a1f180082e83bcc9f7acdcb090502262b2d1`
- Each candidate used a separate fresh scratch copy of restart time `30` (global time `30.0 s`, time index `150000`) with `dt=0.0002 s`; the frozen release-force evidence was unchanged. Restart fields and mesh hashes matched across candidates, and each run records `restart_inputs_unchanged_after_run=true`.
- Each run was bounded by scratch preCICE configuration to exactly two physical windows and by `max-iterations=20`. The existing Structure CLI's fail-closed outer ceiling remained `--max-windows=5`; preCICE's scratch `max-time-windows=2` stopped the coupling at two. No third window was attempted.
- The 30.0 s physical release force observed by each Structure participant was `(0.06552704065480554, 0.058729874135090385, 0) N`, matching the frozen x/y values within the qualified tolerance. Its source remains global time `30.0 s`.
- The only candidate XML setting varied was `max-used-iterations`; the other IQN-ILS settings were `initial-relaxation=0.2`, `enforce=true`, `time-windows-reused=1`, primary data `Displacement` and `Force`, `residual-sum` preconditioner, QR3 filter (`limit=1e-2`), and reduced time grid enabled.

Candidate XML validation used installed preCICE 3.4.1. All three `precice-config-validate` invocations returned 0, reported “No major issues detected,” and emitted no parser warnings.

| Candidate | XML SHA256 | Validation |
|---|---|---|
| `max-used-iterations=1` (reference) | `b5ddf80b6e642f2e6b051442ab83a95a0b1116b1311201f056a36e94709e8d3e` | PASS |
| `max-used-iterations=2` | `eed3cb90c7089c6570ea005c0cb164663e0c9bc0544bb923beccc909af13cc2f` | PASS |
| `max-used-iterations=3` | `7ea091bc4201d845f35e952b7caeb7b341b0911474aa60d48211fc0ad86ad769` | PASS |

The production XML hash was `e4987ec7d768517feefe312a9ddcbd391ff052981aa84bae6934b555e97d1f71` before and after the study. Candidate XML files are confined to the evidence run directories.

## Runtime comparison

All windows converged before the 20-iteration cap. Each candidate completed window 1 in 3 coupling attempts and window 2 in 5 attempts, for 8 total attempts, 6 rollbacks, and 8 CFD advances.

| `max-used-iterations` | Window 1 attempts | Window 2 attempts | Total attempts | Rollbacks | CFD advances | Wall time, including preflight | Mean per attempt | Acceptance |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 3 | 5 | 8 | 6 | 8 | 9.993856860 s | 1.249232108 s | Both converged before cap |
| 2 | 3 | 5 | 8 | 6 | 8 | 10.019043640 s | 1.252380455 s | Both converged before cap |
| 3 | 3 | 5 | 8 | 6 | 8 | 9.998236556 s | 1.249779570 s | Both converged before cap |

Relative to the one-column reference, wall-time deltas were `+0.025186780 s` for 2 columns and `+0.004379696 s` for 3 columns. These are small differences in one short run, not evidence of a meaningful performance regression. There was no iteration or attempt reduction.

## Residual and IQN diagnostics

preCICE's detailed `measureConvergence` messages in each preserved Fluid stdout show the same initial residuals for all candidates. In window 1, the first displacement absolute/relative measures were `1.43e-7 m / 1.00`; by the third attempt they were `6.59e-12 m / 4.65e-5`, satisfying the configured criteria. In window 2, the first measures were `5.65e-7 m / 7.99e-1`; at the fifth attempt the final displacement absolute/relative measure was:

| `max-used-iterations` | Window 2 final displacement measure | Force measure | Window 2 result |
|---:|---|---|---|
| 1 | `5.18e-20 m / 7.30e-14` | `0 / 0` | Converged, attempt 5 |
| 2 | `1.61e-12 m / 2.27e-6` | `0 / 0` | Converged, attempt 5 |
| 3 | `1.22e-12 m / 1.72e-6` | `0 / 0` | Converged, attempt 5 |

The final displacement measures differ slightly but all satisfy the same tolerances; no candidate used fewer iterations. The generated `precice-Fluid_0000-convergence.log` contains all-zero residual columns for every attempt in all three runs. Those columns are therefore not used as the residual evidence here; the detailed per-data convergence measures printed in the raw Fluid stdout agree with the observed preCICE convergence/acceptance status. Both raw forms are retained for audit.

For completeness, the detailed Fluid log history is listed below as `absolute / relative` per attempt. Displacement absolute values are in metres; Force absolute values are in newtons. Relative values are dimensionless.

| History limit | Window | Displacement `abs/rel` sequence | Force `abs/rel` sequence |
|---:|---:|---|---|
| 1 | 1 | `1.43e-7/1.00, 1.14e-7/8.00e-1, 6.59e-12/4.65e-5` | `1.18e-3/1.34e-2, 9.40e-4/1.08e-2, 0/0` |
| 2 | 1 | same as limit 1 | same as limit 1 |
| 3 | 1 | same as limit 1 | same as limit 1 |
| 1 | 2 | `5.65e-7/7.99e-1, 4.07e-7/6.15e-1, 1.19e-9/1.77e-3, 1.37e-8/1.93e-2, 5.18e-20/7.30e-14` | `1.39e-1/2.70, 2.89e-2/3.26e-1, 2.41e-2/2.72e-1, 0/0, 0/0` |
| 2 | 2 | `5.65e-7/7.99e-1, 4.07e-7/6.15e-1, 3.55e-9/5.31e-3, 2.21e-11/3.27e-5, 1.61e-12/2.27e-6` | `1.39e-1/2.70, 2.89e-2/3.26e-1, 2.48e-2/2.80e-1, 2.05e-2/2.31e-1, 0/0` |
| 3 | 2 | `5.65e-7/7.99e-1, 4.07e-7/6.15e-1, 3.11e-9/4.65e-3, 6.19e-13/9.15e-7, 1.22e-12/1.72e-6` | `1.39e-1/2.70, 2.89e-2/3.26e-1, 2.46e-2/2.78e-1, 2.04e-2/2.30e-1, 0/0` |

The interface's IQN primary vector has four scalar entries (2 displacement + 2 force). Runtime `iterations.log` and normalized raw-log warning audit report:

| History limit | Window 1: QN / deleted / dropped columns | Window 2: QN / deleted / dropped columns | IQN primary-unknown ill-conditioning warnings |
|---:|---:|---:|---:|
| 1 | `1 / 0 / 1` | `1 / 0 / 5` | 0 |
| 2 | `2 / 0 / 0` | `2 / 0 / 4` | 4 |
| 3 | `2 / 0 / 0` | `3 / 1 / 2` | 4 |

Each warning for limits 2 and 3 says the least-squares column count exceeded half the number of primary unknowns and that the system could become bad or ill-conditioned; it suggests limiting `max-used-iterations`. For limit 3, one column was deleted in window 2. The initial warning scan did not recognize these lines because of ANSI escape codes; the final counts above come from the preserved ANSI-normalized audit of the raw Fluid logs. The one-column run emitted a separate near-zero-coupling-residual warning at its end; that warning is preserved and is not counted as the column/conditioning warning.

## Runtime identity and integrity

The three runs used the same identities:

- Worker source SHA256: `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e`
- Worker binary SHA256: `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`
- Fluid adapter SHA256: `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572`; Build ID `e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b`
- preCICE runtime: 3.4.1; loaded library `/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1`, SHA256 `b20729622d2dbbafdea3d6ead0480ec66be98cb947db3500cc3c27ed4e3039c7`
- Python: `/usr/bin/python3.10`, version 3.10.12; pyprecice metadata 3.4.0, with the qualified preCICE 3.4.1 library loaded
- OpenFOAM: 10

All three preflights passed. Structure and Fluid exited with code 0 for every candidate; the worker was absent after shutdown; no fatal/error lines were recorded; and all restart-input hashes remained unchanged.

## Interpretation and evidence

For this four-scalar, single-slice interface, increasing retained history from 1 to 2 or 3 provided **no measured efficiency benefit** over the two tested physical windows. Limits 2 and 3 added repeated preCICE ill-conditioning warnings, with one QR3 deletion at limit 3. The evidence favors retaining the established one-column setting for this interface unless a separately reviewed experiment provides a reason to change it. This result is limited to this single-slice, two-window sensitivity study; it does not establish behavior for a multi-slice interface or long runs.

Curated machine-readable records, candidate XML, validation output, preflight/runtime identities, Structure traces/audits, Fluid and Structure logs, preCICE iteration/convergence logs, warning audits, cleanup records, and qualification summaries are under:

`evidence/phase1h8_iqn_history/run-20260923T123908Z-02d9a1f-pid143932/`. The six complete scratch case trees (three executed candidate copies and three superseded preparation-only copies) remain in the external archive at `/home/machao/projects/CFD_ANCF_VIV_V2_phase1h_scratch_archive/phase1h8_iqn_history/`. Their file-level SHA256 records are indexed in [archive_index.json](../evidence/phase1h_external_archive/archive_index.json); the superseded preparation-only directory remains explicitly marked `PREPARATION_SUPERSEDED_NO_RUNTIME`.

The directory `run-20260923T123746Z-02d9a1f-pid143216/` is preserved as `PREPARATION_SUPERSEDED_NO_RUNTIME`; it was never executed and is not part of the comparison.

The run used source HEAD `02d9a1f180082e83bcc9f7acdcb090502262b2d1`. The H8 runner was subsequently committed in `e24197d`; this report and curated evidence are being preserved in the Phase 1H evidence commit. The full scratch trees were archived without modifying their contents.
