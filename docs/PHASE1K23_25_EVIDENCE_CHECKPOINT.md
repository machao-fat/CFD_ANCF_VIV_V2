# Phase 1K.23–1K.25 evidence checkpoint

This index freezes the diagnostic evidence boundary before Phase 1K.26. The
checkpoint commit contains the reports, diagnostic scripts, and curated
machine-readable summaries listed below. Large OpenFOAM scratch cases,
field snapshots, meshes, logs, and experimental build trees remain at their
existing local paths and are intentionally not committed.

## Git checkpoint boundary

- Baseline before checkpoint: `d3890deb0e609cc7e38e3f38ff6203787f889c07`
- Branch before checkpoint: `diagnostic/phase1k25-minimal-rollback-repair-v1`
- New Phase 1K.26 branch is created only after the checkpoint commit is clean.
- The raw evidence directories are ignored by the repository policy added in
  `.gitignore`; this does not delete or modify them.

## Curated tracked content

Reports:

- `docs/PHASE1K23_SINGLE_WINDOW_CONVERGENCE_DIAGNOSTIC_PLAN.md`
- `docs/PHASE1K23_SINGLE_WINDOW_CONVERGENCE_REPORT.md`
- `docs/PHASE1K24_FLUID_OPERATOR_REPEATABILITY_REPORT.md`
- `docs/PHASE1K24_FLUID_STATE_ROLLBACK_AUDIT.md`
- `docs/PHASE1K25_ROLLBACK_CAUSAL_PLAN.md`
- `docs/PHASE1K25_MINIMAL_ROLLBACK_REPAIR_REPORT.md`

Diagnostic scripts:

- `scripts/phase1k23_fixed_displacement_structure.py`
- `scripts/phase1k23_run_repeatability.py`
- `scripts/phase1k23_run_single_window.py`
- `scripts/phase1k24_fluid_state_replay.py`
- `scripts/phase1k25_run_group1.py`
- `scripts/phase1k25_run_group5.py`

Curated evidence summaries:

- `evidence/phase1k23_single_window_convergence/qualification_summary.json`
- `evidence/phase1k24_fluid_state_repeatability/fresh_process_repeatability.json`
- `evidence/phase1k24_fluid_state_repeatability/same_process_repeatability.json`
- `evidence/phase1k24_fluid_state_repeatability/process_cleanup.json`
- all root-level JSON summaries under
  `evidence/phase1k25_minimal_rollback_repair/`
- `evidence/phase1k25_minimal_rollback_repair/repair_attempts/README.md`

## External raw evidence index

The following directories are preserved locally and are not overwritten by
Phase 1K.26:

- `evidence/phase1k23_single_window_convergence/` — approximately 4.1 GB;
  includes the Phase 1K.23 extended single-window traces.
- `evidence/phase1k24_fluid_state_repeatability/` — approximately 452 MB.
- `evidence/phase1k25_minimal_rollback_repair/` — approximately 1.8 GB;
  includes independent G1, G2, G3, and G5 candidate trees.

The exact run IDs, file inventory, sizes, and per-file hashes remain
recoverable from these paths. The raw trees are evidence archives, not source
inputs for a production run. Phase 1K.26 must record the exact source paths
and hashes of the frozen restart/configuration it actually uses.

## Diagnostic status at freeze

- K24 fresh-process A/B: repeatable (`0 N` difference).
- K24 same-process replay: not repeatable (`0.1057131957411209 N`).
- K25 Group 1: causal contribution, not sufficient (`0.08047955765631062 N`).
- K25 Groups 2, 3, and 5: no measurable dominant effect in the isolated
  candidates.
- K25 Groups 4 and 6: not measured.
- CFD inner-convergence A/B and IQN requalification remain blocked until
  same-process Fluid operator repeatability is restored.
