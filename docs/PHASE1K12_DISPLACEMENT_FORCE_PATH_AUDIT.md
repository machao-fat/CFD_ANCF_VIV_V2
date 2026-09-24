# Phase 1K.12 — Fluid displacement and Force path forensic audit

## Decision and boundary

**Classification: `REVIEW_REQUIRED`.** The large discrepancy between direct OpenFOAM Force and the Force received by Structure is **explained**, to numerical precision, by the configured preCICE IQN-ILS initial relaxation (`0.2`). It is not evidence of a Force unit or conservative-mapping defect. In contrast, the displacement-to-RBF path cannot be classified A or B from the saved accepted-time snapshots alone: nonzero `cellDisplacement` follows Structure output, yet `pointDisplacement` and accepted mesh coordinates are zero/unchanged. The rejected-iteration point field, RBF boundary input and mesh coordinates were not serialized. The evidence rules out “Structure displacement never reaches Fluid” as an explanation for the *accepted* `cellDisplacement`, but does not prove how the mesh moved within rejected trials.

This is read-only reduction of the existing Phase 1K.11 run, `evidence/phase1k11_25window_rbf_fsi/run-20260924T095422Z-c2245ff/` (Git HEAD `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`). No Fluid, Structure, worker or post-processing runtime was started; no production files/configuration, numerical parameters or historical evidence were changed. The earlier Phase 1K.11 `REVIEW_REQUIRED` decision remains valid. No new run is authorized by this audit.

## A. Displacement path: selected rejected attempts

The 124-line `structure_trace.jsonl` proves `D_trial_interface_m == D_written_to_precice_m` for every attempt and records `trial_displacement_written_to_precice` before `precice_advance_completed`. For each selected first attempt below, Fluid stdout then records `Mapping "Displacement" ... from "Structure-Mesh" to "Fluid-Mesh"` for the corresponding coupling time. That log confirms the preCICE mapping event, **not** the mapped numerical vector or the adapter's actual read/application. `system/preciceDict` configures cylinder `readData (Displacement)`; `constant/dynamicMeshDict` configures the RBF solver and labels `pointDisplacement` as its input. Configuration comments are not substituted for a runtime value trace.

| Window, rejected iteration | Target global time (s) | Structure `D_trial = D_written` x/y (m) | preCICE event | Fluid-side numeric read / RBF moving-boundary input / trial mesh points | Attempt mesh Co max |
| --- | ---: | --- | --- | --- | ---: |
| 1, 1 | 30.0002 | `(1.063383216e-7, 9.530777190e-8)` | Displacement mapped at `t=0.0002` | **Not recorded** | 0 |
| 15, 1 | 30.0030 | `(4.237982378e-5, 3.222662287e-5)` | Displacement mapped at `t=0.0030` | **Not recorded** | 0.774308 |
| 25, 1 | 30.0050 | `(8.703838876e-5, 7.204406200e-5)` | Displacement mapped at `t=0.0050` | **Not recorded** | 1.730620 |

The nonzero attempt mesh Co in windows 15 and 25 is an ALE-motion *indicator*, but it is not an independently saved mesh-coordinate trajectory or a proof that the cylinder point boundary followed the communicated displacement. Phase 1K.11 saved one set of OpenFOAM fields/points per accepted time, not one per rejected attempt. In particular, the `pointDisplacement` and `polyMesh/points` under `30.003` and `30.005` must **not** be assigned to the first rejected attempts at those times.

## B. Accepted-state fields, mesh and write timing

Read-only comparison of all 25 accepted-window time directories with the accepted Structure trace gives:

- `cellDisplacement.boundaryField.cylinder.value`: nonzero and equal to the *current* window's accepted x/y Structure displacement, within the saved ASCII precision, for windows **1–24**. At the final time `30.005`, it equals **window 24's** accepted value, not window 25's. Examples: `30.0002` has `(3.267467624e-7, 7.424288e-8)` (window 1); `30.003` has `(4.238030220e-5, 3.222672085e-5)` (window 15); `30.005` has `(8.227848877e-5, 6.782485035e-5)` (window 24), while window 25 accepted `(8.703844767e-5, 7.204416474e-5)`.
- `pointDisplacement.boundaryField.cylinder.value` is `uniform (0 0 0)` in **all 25** accepted-time files. Its internal field is also uniform zero at the final time.
- Binary coordinates in every accepted `polyMesh/points` are **exactly** the release `constant/polyMesh/points` coordinates (headers differ by time/location). Selected accepted-window `checkMesh` runs passed, but this does not establish the rejected-trial point trajectories. The saved final `meshPhi` internal field and cylinder boundary are uniform zero.
- `system/controlDict` says `writeControl adjustableRunTime`, `writeInterval 0.01`; nevertheless, the Fluid log explicitly records `The coupling timestep completed. Writing the updated results.` at every completed preCICE window. The 25 numeric time directories therefore reflect completed-window writes, not every retry. The final window also logs this completion message before preCICE finalization, yet the saved `cellDisplacement` still contains window 24's value. Its precise update/write ordering is **unresolved** from these logs.

The saved `cellDisplacement` establishes that accepted Structure displacement reached a Fluid-side displacement field; thus alternative C (“never reaches Fluid”) is contradicted for that field. The simultaneous zero saved `pointDisplacement` and stationary accepted mesh point coordinates establish an **accepted-output field/path mismatch**, not its mechanism. The data do not distinguish (A) a correctly moved but rolled-back/re-written trial mesh from (B) an adapter-to-RBF point-field application failure. The RBF input value and mesh point coordinates during rejected attempts were not captured. **Displacement classification: D — unresolved.** No claim that RBF ALE was physically qualified follows.

## C. Force channels reconciled by attempt and time

There are 125 ordered lines in `case/postProcessing/cylinderForces/30/forces.dat`: the time-30 release record plus **one for each of the 124 Structure attempts**. The 124 Fluid `Time = ...` blocks and 124 Structure trace records have the same order and target times. For the first attempt of each physical window, let `F_direct` be the dimensional pressure-plus-viscous `cylinderForces` vector, and `F_prev` the preceding accepted Force (F0 in window 1). The **observed** Structure return satisfies

`F_Structure_received = 0.8 F_prev + 0.2 F_direct`

for x/y in **all 25 window-first attempts**; largest x/y vector error is `1.27e-10 N` using printed force-history precision. This is the configured IQN initial-relaxation `0.2` acting on the exchanged Force iterate. The preCICE XML gives a **conservative nearest-neighbor** mapping of Fluid Force from 200 cylinder-face coupling points to one Structure point and applies IQN-ILS to both primary data. Its `measureConvergence` log for window 25's first attempt reports a Force difference of about `1.09e2 N`, consistent with the **unrelaxed** direct-force jump; the Structure endpoint read is the relaxed value.

| Window, iteration | `F_direct` x/y from OpenFOAM (N) | `F_prev` x/y (N) | `0.8 F_prev + 0.2 F_direct` x/y (N) | Structure endpoint read x/y (N) |
| --- | --- | --- | --- | --- |
| 1, 1 | `(0.1880713584, 0.0470080747)` | `(0.06552704069, 0.05872987415)` | `(0.09003590423, 0.05638551426)` | `(0.09003590423, 0.05638551426)` |
| 15, 1 | `(-37.35058125, -27.94335526)` | `(0.06561766129, 0.05989327031)` | `(-7.417622121, -5.540756436)` | `(-7.417622121, -5.540756436)` |
| 25, 1 | `(-84.212097857, -69.502386186)` | `(0.06625052641, 0.06064032758)` | `(-16.789419150, -13.851964975)` | `(-16.789419150, -13.851964975)` |

For accepted time directories, the saved OpenFOAM `Force` field contains 200 cylinder-face vectors. Their component-wise sum equals the accepted `Structure` returned Force **exactly to the JSON float values in all 25 windows** and agrees with the last direct `forces.dat` record at each time to output precision. Thus the following are separately supported:

1. OpenFOAM's direct integrated Force and the saved per-face adapter `Force` field agree at accepted outputs.
2. Conservative preCICE mapping and Structure read preserve that accepted Force sum.
3. The very large rejected-first-attempt discrepancy is introduced by **preCICE IQN relaxation**, not by the one-time raw-to-section-to-strip conversion, and not by a demonstrated adapter mapping defect.

The per-face `Force` field was not saved separately for rejected attempts, so the exact adapter outgoing face-vector sum **at those attempts** remains unobserved. The all-25 relaxation identity, ordered direct-force records and preCICE convergence messages strongly locate the observed difference at acceleration; they do not supply a missing raw per-face trial snapshot. Structure's next retry uses the just-returned (relaxed) Force, as required by the established implicit contract.

## Classification by requested alternatives

| Question | Finding |
| --- | --- |
| Rejected-trial RBF motion: A or B? | **D: unresolved**. No rejected-trial point field, RBF boundary input or mesh-coordinate snapshot. Mesh Co is suggestive but insufficient. |
| Structure displacement never reaches Fluid (C)? | **No** for accepted output: `cellDisplacement` matches accepted Structure x/y in windows 1–24. Numeric rejected-trial adapter read is not logged. |
| Why saved accepted points return to release? | Associated `pointDisplacement` remains zero and output occurs at completed-window writes. The upstream cause of the zero point field and exact rollback/write ordering are not proven by this evidence. |
| Direct versus Structure Force discrepancy: A/B/C/D? | **Identified at preCICE IQN acceleration**; 0.2/0.8 relation holds across all 25 first attempts. Accepted per-face Force sum validates the conservative output/read channel. |

**Final `REVIEW_REQUIRED`** is chosen instead of `FORCE_CHANNEL_MISMATCH_IDENTIFIED` because the audit's central displacement/RBF question remains open. It is not classified `ADAPTER_DISPLACEMENT_PATH_FAILURE` without the missing rejected-attempt adapter/point/mesh values, and the Force mismatch is not counted as a second defect. A subsequent phase, if authorized, should first design passive attempt-level capture at `adapter read → pointDisplacement boundary → RBF input → mesh points`, including checkpoint rollback and final-window write timing; it must not tune or rerun this 25-window qualification automatically.
