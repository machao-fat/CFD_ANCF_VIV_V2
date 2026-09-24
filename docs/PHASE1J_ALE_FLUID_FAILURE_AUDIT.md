# Phase 1J — ALE / Fluid Runtime Failure Root-Cause Audit

## Classification

`MULTIPLE_POSSIBLE_FAILURES`

The run shows a coupled late-window degradation involving ALE cell-volume collapse, large force excursions, turbulence-variable excursions, rising Courant numbers and ultimately a Fluid-side floating-point exception in GAMG. The evidence does not isolate one unique initiating cause or prove a single causal chain at attempt-level resolution. The earliest sustained precursor visible in the available record is progressive loss of minimum cell volume; a large force pulse is visible at window 15, followed by a sharp `omega` excursion in a retry. The exact ordering between these signals within that first affected window is not fully resolved.

This report does not identify an implicit-coupling contract failure. Phase 1I's Strategy C checks remain valid: trial displacement was written, physical rollback and transport identity checks passed. No rerun, production-source edit, configuration edit, or parameter change was performed for this audit.

## Frozen run and outcome

Audited run: `evidence/phase1i_25window_iqn/run-20260923T143029Z-c2245ff/`.

| Item | Observed |
|---|---|
| Git HEAD during audit | `c2245ff396ff42dfa5e80fee6555a9ede93e3b04` |
| Run ID | `run-20260923T143029Z-c2245ff` |
| Accepted physical windows | 20 (windows 1–20) |
| First incomplete window | 21; one Structure attempt was traced before the Fluid failed on the retry advance |
| Last accepted global time | 30.0040 s |
| Intended endpoint | 30.0050 s; not reached |
| Coupling attempts in summary | 99 |
| Iteration-limit acceptances | 0 |
| Fluid exit | `-8` (SIGFPE) |
| Structure exit | `-15` (terminated after the Fluid process failed) |
| Worker | no orphan remained after cleanup; an independent worker exit code was not exposed |
| Wall time | 111.12 s |

The run stopped in window 21, not at its authorized endpoint. The Structure EOF/termination is downstream of the Fluid failure, not evidence of an independent structural cause.

Frozen evidence hashes:

| Artifact | SHA256 |
|---|---|
| `qualification_summary.json` | `86d0e2cfac60361c103633a1df5c6e1a689a0ac8f6e97d4f0e896849b1642617` |
| `structure_trace.jsonl` | `20525a6405bb921a040e9eda3446cd1293f2379ae81bfdee7b237da70d9c19eb` |
| `fluid.stdout` | `3430604c326279707a8d4fe08f8fac3df109aa101765f9154781e97790355efa` |
| `fluid.stderr` | `613f6e3ce5666b807fbeb283ffe9d5fb4c18e89f3ec1bcb91e5942b7c64c6d84` |
| `postProcessing/cylinderForces/0/forces.dat` | `ddc9af91d1f54fcd0a248add835ca0e8b57219d5187ed306944fe3e11e92f040` |
| `postProcessing/phase1iTurbulenceMax/0/fieldMinMax.dat` | `3362146595d0bbee7d3450b434b637cd1ff75afff7ad6598f3ea541d2f8d6ce2` |
| `postProcessing/phase1iUMax/0/fieldMinMax.dat` | `85821df0caeebf1d189683eea39eff97cad4a77754bbe6f055c34dbb77b438bb` |

## Failure ordering and windows 15–21

The following table aligns the run's per-advance log markers with physical windows where available. `Structure Force return` is the norm recorded by the Structure-side trace after its first attempt; `raw CFD force` is the dimensional integrated force from OpenFOAM's `forces` output. They are different stages/representations and must not be read as identical values. `min(V)` is from the saved volume field at the physical-time directory, not an attempt-tagged measurement; retries can share/overwrite that directory.

| Window / endpoint | Structure first Force return norm (N) | First endpoint raw CFD force `(Fx,Fy)` N; norm | max Fluid Co | max mesh Co | sampled max `|U|` m/s | sampled max `omega` | saved min cell volume m³ |
|---|---:|---:|---:|---:|---:|---:|---:|
| 15 / 30.0030 s | 8.727 | (-32.640, -29.495); 43.99 | 0.4264 | 0.3958 | 0.5980 | 1.0408e6 | 2.3077e-10 |
| 16 / 30.0032 s | 9.872 | (-36.880, -33.340); 49.72 | 0.4264 | 0.4414 | 0.6159 | 2.0811e6 | 1.6320e-10 |
| 17 / 30.0034 s | 11.052 | (-41.256, -37.300); 55.62 | 0.4262 | 0.4877 | 0.6360 | 6.2601e6 | 9.4096e-11 |
| 18 / 30.0036 s | 12.261 | (-45.738, -41.357); 61.66 | 0.4260 | 1.4872 | 0.7027 | 9.8230e7 | 2.3754e-11 |
| 19 / 30.0038 s | 13.497 | (-50.320, -45.503); 67.84 | 1.5003 | 21.3015 | 0.8204 | 4.57795e11 | **-4.7606e-11; 22 non-positive cells** |
| 20 / 30.0040 s | 14.756 | (-54.984, -49.734); 74.14 | **21.4545** | 14.6236 | **33.1658** | 1.03883e10 | **-1.1983e-10; 33 non-positive cells** |
| 21 / 30.0042 s | 15.988 | (-60.100, -54.852); 81.37 | 14.7092 | 7.9870* | 7.1218* | 1.24245e5* | 7.6874e-10* |

`*` Window 21 values are incomplete: they describe data emitted for the first attempt or its saved timestamp directory. The second retry failed before its diagnostic writers completed; the positive saved volume at 30.0042 s therefore does not demonstrate mesh recovery.

Across windows 15–20, each window used five coupling attempts and was accepted before the iteration cap. Window 21 had one traced attempt followed by the failing Fluid retry. The Structure force-return sequence within each window is informative: the first returned force grows from 8.727 N at window 15 to 14.756 N at window 20; subsequent retry returns in those windows generally fall back near 0.089–0.378 N. Thus the attempt-level response is strongly non-monotone even while the first returned load grows with window index.

### What appears first?

1. **Gradual ALE geometry deterioration is the earliest sustained precursor in the available record.** The minimum saved cell volume declines from `7.6874e-10 m³` at 30.0002 s to `2.3754e-11 m³` by 30.0036 s. At 30.0038 s the saved field contains 22 non-positive volumes. This progression precedes the terminal SIGFPE and the largest reported Fluid Co.
2. **A force excursion is already present at window 15.** The first endpoint raw force norm is about 43.99 N while Fluid Co and mesh Co remain below 0.43. This is a large load response before the later Co explosion, but does not alone prove force initiated the mesh degradation.
3. **Turbulence extrema escalate during the retry sequence.** `omega` is already sampled at about `1.04e6` within window 15 (the first sample at that endpoint is about `9.38e4`); it grows to `4.58e11` at window 19. `k_max` stays near `0.0157` and `nut_max` remains near `2.806e-4`, so the available extrema point specifically to `omega` rather than a comparable `k`/`nut` maximum blow-up. Negative `omega` minima also occur in stdout.
4. **Large Courant and velocity excursions follow.** Mesh Co reaches 21.30 at window 19; Fluid Co reaches 21.45 and sampled `|U|` reaches 33.17 m/s at window 20. The maxima are not all available at identical per-attempt timestamps, so this ordering is window-level rather than a fully resolved causal sequence.
5. **The Fluid process terminates in window 21 during GAMG.** This is the final failure, not the earliest anomaly.

Overall, the degradation is gradual over many windows, with a sharp escalation in windows 18–20 and terminal solver failure in window 21. Existing output cannot establish whether the initial force pulse, worsening mesh geometry, or turbulence response is the unique initiating mechanism.

## ALE and mesh-motion audit

The scratch runtime uses the case's `motionSolver` with `displacementLaplacian` and `quadratic inverseDistance` diffusivity around patch `cylinder`, as configured in `cases/hh06_single_slice/constant/dynamicMeshDict`.

- Fluid Courant and mesh Courant numbers are printed per participant advance and are usable for attempt-level ordering.
- The run's passive `writeCellVolumes` output makes minimum volume and the count of non-positive volumes recoverable from saved binary `V` fields at physical timestamps. Those snapshots are not attempt-tagged; retries at the same timestamp do not provide an unambiguous per-retry geometry history.
- No attempt-level maximum vector mesh velocity was emitted. `meshPhi` is a face scalar flux and `Uf` is a surface vector field; neither was treated as a substitute for cell/point mesh-velocity magnitude.
- No corresponding per-attempt maximum non-orthogonality or skewness metric was emitted. No live `checkMesh` quality pass was run as part of this read-only audit.

The scratch diagnostic overlay added passive outputs for force, `|U|`, turbulence extrema, and cell volumes; it enabled mesh-Courant reporting. Its recorded diff did not change solver tolerances/schemes, dynamic-mesh parameters, coupling settings, or physical parameters. The authoritative case and source/configuration were not edited during this audit.

For a future separately authorized diagnostic run, the remaining useful passive observables are an attempt-tagged minimum-volume/non-positive-cell count, maximum vector mesh velocity, and geometric quality extrema. They are recommendations only, not changes made here.

## Turbulence field findings

- `k_max` remains approximately `0.01576` down to `0.01568` over the audited late windows. The log reports negative minima beginning at small magnitude, reaching approximately `-8.74e-7` at window 20 and `-6.85e-7` in the first window-21 output.
- `nut_max` remains near `2.8059e-4` to `2.8066e-4`; the available output does not show a comparable maximum excursion. `nut_min` is unavailable in this run's passive output.
- `omega` is the first clearly extreme turbulence maximum in the late-window sample series: approximately `1.04e6` in a window-15 retry, `9.82e7` by window 18, `4.58e11` at window 19, then `1.04e10` in a window-20 retry. This is not monotone at every sample, and saved extrema do not isolate the first cell or exact retry that generated the maximum.
- `bounding omega` reports negative minima as well as very large positive maxima (e.g. window 20 retry: min about `-3.00e4`, max about `1.04e10`). No turbulence-model change or field repair was attempted.

Thus `omega` is the most conspicuous turbulence-field anomaly, but the logs do not prove that it precedes ALE deterioration: cell-volume decline is already present earlier, and the available turbulence extrema are not consistently attempt-aligned with the volume snapshots.

## GAMG / SIGFPE stage

`fluid.stderr` records `Foam::sigFpe::sigHandler`, followed by `Foam::GAMGSolver::scale`, `GAMGSolver::Vcycle`, `GAMGSolver::solve`, and `fvMatrix<double>::solveSegregated` in `pimpleFoam`.

The last stdout block is window 21, retry attempt 2, at `Time = 30.0042 s`, PIMPLE iteration 1. `cellDisplacementx/y`, `pcorr`, and `Ux/Uy` report completed solves immediately before termination. In this PIMPLE sequence, the next expected segregated solve is `p`, whose configured solver is GAMG. Therefore the pressure solve is the likely failing stage, but the crash stack does not print the matrix/equation name and cannot prove it. No earlier explicit GAMG singular-matrix warning is present in the inspected terminal block. **Exact failed equation: unresolved; likely `p`.**

The preCICE near-zero residual warnings are not the Fluid fatal error. Structure termination/EOF follows the Fluid SIGFPE.

## Comparison to migrated historical runaway

Comparison uses only the current repository's migrated historical report at `evidence/legacy_qualification/hh06_single_slice_coupling_history_v1/evidence/runtime/hh06_bounded_multiwindow_ale_qualification_v1/HH06_BOUNDED_MULTIWINDOW_ALE_QUALIFICATION_REPORT.md`; no old repository was accessed. Its cited per-iteration CSV is not present in the migrated evidence, so detailed attempt-level matching is unavailable.

| Indicator | Historical bounded run | Phase 1I IQN-ILS run |
|---|---:|---:|
| Accepted windows | 25/25, through 30.0050 s | 20; failed in window 21 |
| Fluid Co max | 184.6621 | 21.4545 observed before failure |
| Mesh Co max | 58.7520 | 21.3015 observed before failure |
| Mesh velocity max | 18.1173 m/s | unavailable |
| `|U|` max | 392.2742 m/s | 33.1658 m/s sampled before failure; terminal attempt incomplete |
| `omega_max` | 925,092.97 | 4.57795e11 sampled at window 19 |
| Minimum cell volume | 7.6874e-10 m³, positive | -1.1983e-10 m³ in saved window-20 timestamp field |
| Solver FPE | none during bounded run | SIGFPE in GAMG during window 21 |

The current run exhibits the **same broad ALE/flow/turbulence runaway class** (increasing load/mesh indicators, extreme flow/turbulence values), but its observed failure is earlier and more severe in `omega` and saved cell volumes, and it ends in a GAMG SIGFPE. The evidence is insufficient to assert the same exact initiating mechanism as the historical run. It is also insufficient to claim that the historical mechanism was eliminated or merely shifted.

## Direct answers

1. **Final/failed windows and processes:** 20 accepted; window 21 failed on retry. Fluid `-8`; Structure `-15`; no orphan worker remained, but its individual exit code was not recorded.
2. **First observable failure mechanism:** sustained ALE volume contraction is the earliest clear trend; a large force pulse is visible at window 15, `omega` escalates in retry samples, followed by severe mesh/Fluid Co and velocity excursions. Attempt-level data do not uniquely order or causally connect these signals.
3. **Gradual or sudden:** gradual deterioration across windows, with sharp escalation in windows 18–20 and solver failure in window 21.
4. **ALE metrics:** Fluid Co and mesh Co are attempt-aligned; mesh velocity and quality extrema are unavailable. Timestamp-level cell volumes are recoverable, including non-positive values, but cannot identify the exact retry geometry.
5. **First turbulence variable to diverge:** `omega` is the strongest extreme; exact causal precedence against mesh deterioration is unresolved. `k_max` and `nut_max` do not show comparable growth in available output.
6. **GAMG equation:** likely pressure `p` after successful mesh, `pcorr`, and velocity solves; exact matrix name is absent from the crash stack and remains unresolved.
7. **Historical comparison:** same broad runaway class, not proven to be the same root mechanism.
8. **Root cause:** not uniquely isolated; retain `MULTIPLE_POSSIBLE_FAILURES` and do not tune parameters based on this audit alone.

## Repository boundary

Only this audit document is added by Phase 1J. The Phase 1I runtime evidence remains untouched. No source, runtime configuration, physical parameter, or case file was changed; no solver, OpenFOAM, preCICE, Structure, or worker process was launched for this audit.
