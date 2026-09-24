# Phase 1K.22 — Five-window experimental adapter qualification

**Lifecycle classification: `PASS_EXPERIMENTAL_FIVE_WINDOW_LIFECYCLE`.** **Convergence observation: `NOT_CONVERGED_WITHIN_20_ITERATIONS` in every window.** This is an experimental five-window adapter/rollback result, not production-adapter qualification, converged FSI, long-run stability, or HH06 validation.

## Frozen run and identities

- One real run: `evidence/phase1k22_five_window_experimental/run-20260924T170918Z-c2245ff-r6j6GB/`. Branch `repair/worker-lineage-implicit-contract-v1`; Git HEAD `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`. Tracked/index worktree changes were absent before and after. No production source or case file was changed; only this isolated scratch case and evidence were created.
- Start: a fresh copy of the frozen Phase 1K.10 mapped new-mesh `30.0 s` fields. Preflight compared restart-field and mesh hashes to that frozen source and returned `PASS_PREFLIGHT_ONLY`. Scratch XML SHA-256: `5fbeaa4e5e67701266648014decdb8ca5eb44bea08e437810f065573b4516b23`.
- Experimental adapter **actually loaded**: `libpreciceAdapterPhase1K20.so`, SHA-256 `225ecab227b8271f01119fe476370e3a0b705ca06e1ca3a7739200266499b165`. Diagnostic RBF library actually loaded: `libRBFMeshMotionSolverPhase1K187BStopDiag.so`, SHA-256 `508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11`; its deliberate one-retry stop was disabled. Worker SHA-256: `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`. The historically qualified adapter was **not** loaded or replaced.
- Foundation OpenFOAM 10, preCICE 3.4.1; mesh, RBF settings, IQN-ILS settings, ANCF, Fluid physics, and `dt=0.0002 s` were retained from Phase 1K.21. Scratch XML, Structure authorization, and Fluid end-time were bounded to **five** physical windows, ending at global time `30.001 s`; no sixth window exists in the trace or case time directories.

## Per-window result

The residual columns below are **participant diagnostic** residuals on the final attempt, not substitutes for preCICE's convergence decision. Full 20-entry residual histories and ANCF Newton/residual histories for every window are in `qualification_summary.json` and `structure_trace.jsonl`.

| Window | Attempts / rollbacks | Acceptance | preCICE convergence flag | Final raw Force residual (N) | Final trial-D residual (m) | QN columns / logged dropped columns | Profile-derived wall interval (s) |
|---:|---:|---|---:|---:|---:|---:|---:|
| 1 | 20 / 19 | `ACCEPTED_AT_ITERATION_LIMIT` | 0 | 1.366262948 | 6.193694713e-7 | 1 / 18 | 44.676440 |
| 2 | 20 / 19 | `ACCEPTED_AT_ITERATION_LIMIT` | 0 | 0.002725907 | 1.517056202e-9 | 1 / 37 | 52.178734 |
| 3 | 20 / 19 | `ACCEPTED_AT_ITERATION_LIMIT` | 0 | 0.002957177 | 8.841848421e-9 | 1 / 56 | 54.187636 |
| 4 | 20 / 19 | `ACCEPTED_AT_ITERATION_LIMIT` | 0 | 0.014260922 | 1.152754452e-8 | 1 / 75 | 53.922585 |
| 5 | 20 / 19 | `ACCEPTED_AT_ITERATION_LIMIT` | 0 | 0.134364711 | 8.585008859e-8 | 1 / 94 | 52.893395 |

The IQN `DroppedQNColumns` figures are the values as written in preCICE's per-window iterations log; their 18, 37, 56, 75, 94 progression appears cumulative. Deleted columns were 0 in all five rows. The Force and trial-displacement residual histories are non-monotonic; window-1 final raw Force residual increased to 1.366 N. There is no evidence that any of these five windows converged to configured preCICE tolerances. No acceleration or other parameter was tuned.

Total launch-to-clean-exit **monotonic** wall time was `258.875052 s`. Per-window intervals above come from the relative-microsecond `advance` event timestamps in the Structure preCICE profiling file: window 1 starts at its first advance; later intervals begin at the preceding accepted advance endpoint. They sum to about `257.859 s`, leaving approximately one second of startup/shutdown outside those intervals. The system's Unix wall clock advanced about `23.647 s` more than the monotonic clock during this run; therefore the human-readable `HH:MM:SS` log timestamps are **not** used for the quantitative per-window timings.

## Checkpoint, exchange, and cleanup verification

- All **95** retries have S0/S1 snapshots. For each, the complete `pointDisplacement` internal field and all boundary patches, complete `cellDisplacement` internal/boundary field, and mesh point coordinates have matching SHA-256 digests before checkpoint and immediately after restore. This includes four windows whose S0 `pointDisplacement` is nonzero; window-5 S0 max norm is `5.169892841326847e-6 m`.
- ANCF logged one S0 and 19 S1 records per window. At every S1, the live `q`, `qdot`, and `qddot` arrays and hashes match that window's saved physical checkpoint.
- Fluid adapter logged **95** retry reads at `relativeReadTime=0.0002 s` and **4** accepted-boundary reads at `0.0 s`. The fifth accepted window ends coupling and therefore has no subsequent boundary read. Across all 100 attempts, `D_written_to_precice == D_trial_interface`; each retry Force input equals the preceding returned Force, and accepted Force handoff matches at all four physical-window boundaries.
- Transport sequence was 1–100, strictly increasing. Both Fluid and Structure exited with status 0. The observed worker PIDs were absent after shutdown; the socket run directory contained no remaining socket file. The maximum Fluid Courant number emitted in the log was `0.3966036913`. No OpenFOAM/preCICE fatal error or SIGFPE occurred. The adapter emitted its existing `runTimeModifiable` warning; no `deltaT` was changed.

## Evidence and limits

Machine-readable per-retry hash comparisons, residual histories, IQN rows, wall timings, and classification: `qualification_summary.json`. Supporting artifacts in the unique run directory include `diagnostics/S0...S5...json`, `ancf_checkpoint_stages.jsonl`, `structure_trace.jsonl`, Fluid/Structure stdout and stderr, `case/precice-Fluid_0000-iterations.log`, `case/precice-profiling/Structure_0000-0-1.txt`, `launch_started.json`, `process_cleanup.json`, scratch XML/contract, and the single-use runner/analyzer. The full diagnostic snapshots occupy about 12 GB and are preserved without overwriting Phase 1K.21 evidence. This report and evidence remain uncommitted pending review.

**Conclusion:** the experimental Phase 1K.20 adapter preserves the tested point/cell/mesh and ANCF rollback invariant across five complete implicit windows, including nonzero committed states and accepted-window read handoffs. The same run shows a clear **convergence-efficiency problem**: all five windows exhausted the 20-iteration cap. It does not authorize a 25-window run, production adapter replacement, or long-duration stability claims.
