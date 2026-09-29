# V2606 NM-series offline evidence archive

This index covers the previously unuploaded NM-series material now curated into this repository. The NM14.1/NM14.2 scripts, corrected reports, modal/Cl results, source audit, and vector figures were already uploaded separately; this addition covers the existing NM2–NM13.1 evidence found in the completed-work evidence tree.

## Scope and preservation rules

- Included: non-empty compact classifications, comparison/analysis results, source and configuration audits, offline postprocessing/reconstruction scripts, and the NM10.1 distributed-mapping helper/tests.
- Excluded: original CFD fields and meshes, direct raw force/structure time histories, per-attempt JSONL, run logs, executables, checkpoint/state binaries, copied frozen ANCF core snapshots, participant launch/run scripts, and large intermediate/retry directories.
- Absolute machine-local roots in copied text/JSON have been replaced with portable placeholders such as `${V2606_PROJECT_ROOT}`, `${LINUX_HOME}`, and `${D_DRIVE_ROOT}`. These reports remain historical evidence; this path normalization does not claim that excluded runtime inputs are present here.
- Empty placeholder files are not treated as results. Where a source phase had only runtime source/configuration and no offline result package, it is identified below rather than represented as a completed report.
- No historical classification is changed by this archival commit.

## Uploaded NM phases

| Phase | Curated evidence |
|---|---|
| NM2.1 | IEEE-754/significance measurements, final classification, source audit |
| NM2 adapter rollback | Attempt-alignment and R1/R2 comparison reports, configuration identity |
| NM3 | Frozen-release manifest, late-window statistics, restart smoke and runtime identity |
| NM4 | Clean-ANCF source/coupling audit, checkpoint and force-conversion evidence, convergence report |
| NM5 | IQN-ILS classifications/statistics, configuration and official-source identities, preCICE reference |
| NM6 | OP1/OP2 field and force convergence comparisons, final classification and common manifest |
| NM7 | 500-window iteration/convergence/mesh summaries, warning summary, release/config identities |
| NM8.1 and the separately named attempt-1 review | Displacement envelope, coupling/mesh summaries, classifications and source manifest where non-empty |
| NM8.2 | Boundary-condition correction report, old-vs-corrected comparison, A/B/C preparation and coupling summaries |
| NM8.3.1–NM8.3.5 | Four-state response, local-gain, pressure-sensitivity, PIMPLE subsolve and minimal-pressure-solver analyses/classifications |
| NM8.3 moving-wall failure | Root-cause, residual/rollback/solver and source-checkpoint audit results |
| NM8.4 / NM8.5 / NM8 endurance-1s | Short100/500-window and 1-second iteration, force, displacement, mesh, pressure, and stability summaries |
| NM9-A / NM9-B / NM9-C0 | Three-slice smoke and short100 audits, accepted-state summaries, spatial-representativeness metrics and classifications |
| NM10 resolution strategy | Point-load localization, generalized-force/power, quadrature, and resolution-ladder offline analyses |
| NM10.1 | Actual V2 reference contract/hash record, closeout matrix, thin distributed mapper/evaluator and permanent tests, replay comparisons |
| NM10.2 / NM10.3 / NM10.4 / NM10.5 | Smoke, entry review, fresh100, and post100 reports/audits; raw attempts and trajectories are not copied |
| NM11 | Four-rank identity, fixed-run comparison, restart and R3 failure/summary evidence; execution scripts and logs are not copied |
| NM12 | N5 diagnostic summaries, cost/projection and gate reports, Q/rollback/health analyses, selected offline analyzers; no CFD output data or runtime logs |
| NM13.1 | Direct-force alignment and merge/audit scripts, force/Huera contracts, postprocessing-readiness and structure-data audit results |
| NM13 configuration | N5 long-run configuration/identity, I/O, logging, restart and launch-preflight contracts; checkpoint histories and runtime data are excluded |

NM9's separate `v2606_nm9_three_slice_multi` source directory contained only participant source and XML configuration in the inspected evidence tree; its run-result evidence is represented by NM9-A/NM9-B. Those implementation/configuration files were not copied into this offline-results archive.

No standalone `v2606_nm1` evidence directory was present in the inspected source evidence tree. This archive therefore starts with the earliest available NM2 artifacts; it does not imply NM1 never existed elsewhere.

## NM14 package

The already-uploaded NM14 package is indexed in [V2606_NM14_OFFLINE_UPLOAD.md](V2606_NM14_OFFLINE_UPLOAD.md). It contains the corrected NM14.1/NM14.2 offline analysis, modal-family and Huera-compatible Cl outputs, reports, source audit, and vector figures. The thesis PDF and all original 10-second CFD/structure data remain excluded.
