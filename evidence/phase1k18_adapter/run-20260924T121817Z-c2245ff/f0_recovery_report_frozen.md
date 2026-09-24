# Phase 1K.10 — new-mesh 30.0 s restart transition

Classification: **REVIEW_REQUIRED**. Mapping, new-mesh force evaluation, the TPS-RBF zero-motion contract, and the single 100-step fixed-cylinder OpenFOAM run passed their direct checks. However, the first post-mapping fluid step has a substantial pressure/force transient whose cause and implication for the first FSI window have not been established. This report does **not** authorize a five-window FSI run or promote the case to a validated release condition.

## Scope and protected state

HEAD: `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`, branch `repair/worker-lineage-implicit-contract-v1`. The authoritative `cases/hh06_single_slice/30` and `constant/polyMesh` were neither run nor overwritten; their SHA256 checks in `source_sha256.txt` still pass. The production `constant/dynamicMeshDict` had been half-migrated to RBF before this phase. Its exact Phase 1K.9 form was preserved as `evidence/phase1k9_verified_rbf/run-20260924T081544Z-c2245ff/production_rbf_dynamicMeshDict.phase1k9` (SHA256 `0ffeeac3d86ccfce4f6468371c188d50f70342b77ea0e8bff61b0e6f36519f78`), and the production file was restored to HEAD's old-mesh Laplacian configuration (SHA256 `56158d50b619174c67a343d2660c87c4c0c5e1370e2fde44a4a4c6f07c5ccdc5`). No production physics, coupling, source, or contract file was changed. No commit was created.

All new cases and logs are under [run-20260924T085251Z-c2245ff](../evidence/phase1k10_new_mesh_restart/run-20260924T085251Z-c2245ff/). `mapped_candidate_30/` is the preserved, unadvanced new-mesh release candidate. `fluid_only_100/` is the sole advanced 100-step copy; its 30.02 s endpoint must **not** replace the 30.0 s candidate. `force_eval/` is the separate force post-processing copy. `restart_and_numerics_sha256.txt` shows byte equality of the original and copied `30/uniform/time`, turbulence/viscosity properties, `fvSchemes`, and `fvSolution`; the scratch `controlDict` intentionally differs to remove preCICE and bound the run. No preCICE, Structure participant, ANCF worker, or FSI run was started.

## Mesh and provenance

The Phase 1K.9 port is solids4foam v2.4, commit `1341312f951caf4d8fcc69499c6ce1a588826156`. The installed `libRBFMeshMotionSolver.so` SHA256 is `b27b347c4ba3026a495517ae7ae237ceb5cd8408ac0db9af6a58ccd83647a20c`; ELF Build ID `f5ba43436c00f75dd314136806e0a00c632d0d58`. Source GEO SHA256 `9a19a3b7b593bdf7bbd39409ec8b5fa4958135eac714b24421dfeb0222d9a5d2`; MSH2 SHA256 `c467ec6cb763864608c84acabef3a2160d48171005291035cae5cf2ddd08fab4`. The port was not rebuilt. OpenFOAM was Foundation 10, build `10-c4cf895ad8fa`.

| Property | Old authoritative mesh | New candidate mesh |
|---|---:|---:|
| Hex cells | 46,826 | 46,826 |
| x bounds, m | -0.28 to 0.56 | -0.28 to 0.56 |
| y bounds, m | -0.42 to 0.42 | -0.35 to 0.35 |
| z bounds, m | 0 to 0.028 | 0 to 0.028 |
| Cylinder faces | 200 | 200 |
| Minimum cell volume, m³ | 7.687364982e-10 | 7.687364831e-10 |
| Maximum non-orthogonality, degrees | 44.00486412 | 43.84604554 |
| Maximum skewness | 0.8545162319 | 0.8969795547 |
| `checkMesh -allTopology -allGeometry` | Mesh OK | Mesh OK before mapping and after 100 steps |

Both meshes have patches `front`, `back`, `cylinder`, `inlet`, `outlet`, `upper`, `lower`; `front/back` remain `empty`. The new cylinder patch is a 200-face wall compatible with the existing preCICE interface. Detailed checks are in `checkMesh_old_source.log`, `checkMesh_pre_mapping.log`, and `checkMesh_after_100.log`. The 6D O-grid ring remains an internal interface and is **not** separately pinned by the RBF patch-list API.

## Version-correct field transfer

Installed `/opt/openfoam10/applications/utilities/preProcessing/mapFields/mapFields.C` and `mapFields -help` were inspected before execution. Because the meshes have different y extent, `-consistent` was not used. The actual command used `mapFields -case <mapped_candidate_30> -sourceTime 30 -mapMethod interpolate -noFunctionObjects <mapping_source>`, with explicit identity patch mappings in `system/mapFieldsDict` and `cuttingPatches ()`. OpenFOAM 10's `mapFields` maps only target volume fields also present in the source; the scratch cases exposed exactly `U`, `p`, `k`, `omega`, and `nut`. It reported interpolation of all five and exit code 0 (`mapFields.log`). The map is interpolation across different geometries, **not** cellwise identity or a conservation proof.

`phi` and old mesh-motion fields were not transplanted across different face/point geometry. `pointDisplacement` was constructed as a new-mesh, uniform-zero pointVectorField with the target patch types. `mapFields` temporarily renamed this non-volume field to `.unmapped`; the byte-identical new-mesh template was restored to `pointDisplacement`. The RBF solver did not require old `cellDisplacement`. The required field dimensions and patch definitions were readable, no target 1e99 unmapped-cell sentinel survived the extrema checks, and no NaN/Inf appeared.

| Field statistic | Old 30 s | Mapped new 30 s |
|---|---:|---:|
| max \|U\|, m/s | 0.557968422 | 0.557472136 |
| min/max p, m²/s² | -0.1434163747 / 0.05357864538 | -0.1424346684 / 0.05357864538 |
| min/max k, m²/s² | 2.701992533e-10 / 0.01589701043 | 2.701992533e-10 / 0.01578528817 |
| min/max omega, 1/s | 1.983594574 / 93792.84749 | 1.988436249 / 93792.84749 |
| min/max nut, m²/s | 2.880808728e-15 / 2.803142219e-4 | 2.880808728e-15 / 2.782685419e-4 |

These are OpenFOAM `volFieldValue` results (`source_field_postprocess.log`, `force_time30_postprocess.log`), not a claim that every mapped cell is physically equivalent. The source `30/uniform/time` has value 30, index 150000, and deltaT 0.0002. The new scratch candidate retains that exact restart time. Its 30 s field and mesh hashes remained unchanged after the advanced-copy run (`pre_run_sha256.txt`).

## New-mesh release force at exact 30.0 s

The independent force-only copy was processed using the previously qualified Foundation-10 solver route, `pimpleFoam -postProcess -case <force_eval> -time 30`. The cylinder `forces` object used kinematic `p`, `rho rhoInf`, `rhoInf 1000`, pressure plus viscous force, and no solver advance. Its exact line is in `force_eval/postProcessing/cylinderForces/30/forces.dat` (SHA256 `f29486df3a3a22b874bf04bb5404c1e9c3a95327b7b184add60518002283bb2b`). Components are dimensional patch-integrated newtons.

| Component | Fx, N | Fy, N | Fz, N |
|---|---:|---:|---:|
| Pressure | 0.063811823767 | 0.058106728512 | -2.4124367132e-21 |
| Viscous | 0.0017152169226 | 0.00062314563632 | 3.0935816745e-22 |
| **New raw F0** | **0.0655270406896** | **0.05872987414832** | **-2.10307854575e-21** |
| Section F0 = raw / 0.028, N/m | 2.3402514532 | 2.0974955052971 | -7.51099480625e-20 |
| Strip F0 = section × 1.98, N | 4.633697877336 | 4.1530411004883 | -1.4871769716375e-19 |

The old-mesh raw F0 was `(0.0655270406544, 0.05872987413554, -2.44420351566e-21)` N. New minus old in x/y is `(3.52e-11, 1.278e-11)` N. This proximity is an observation, not permission to reuse the old F0 or to skip new-mesh provenance. `contract.json` was not changed.

## Exactly one fixed-cylinder fluid-only test

The separate `fluid_only_100/` scratch case retained the Phase 1K.9 RBF parameters: TPS; moving `(cylinder)`; fixed `(inlet outlet upper lower)`; static `()`; coarsening enabled with tol 0.05, minPoints 20, maxPoints 200, livePointSelection yes, tolLivePointSelection 0.05. It used the same OpenFOAM `fvSchemes`, `fvSolution`, kOmegaSST model and physical properties; the only active function objects were passive `forces` and field extrema. No preCICE function object or dictionary was configured. The solver log confirms loading `RBFMeshMotionSolver` and TPS. `pimpleFoam` completed exactly 100 time steps, 30.0002 through 30.02 s, exit code 0; wall-clock 43.65 s.

| Diagnostic over run | Observation |
|---|---:|
| Max Fluid Co | 0.4026192225 |
| Max mesh Co | Not emitted; do not substitute a measured value |
| Max \|U\|, m/s | 0.58088911801 |
| Min/max p, m²/s² | -0.55437406818 / 4.5318815932 |
| Min/max k, m²/s² | 2.6533853859e-10 / 0.015785288172 |
| Min/max omega, 1/s | 1.9884362493 / 93792.851139 |
| Min/max nut, m²/s | 2.828984676e-15 / 2.7989782751e-4 |
| Minimum cell volume, m³ | 7.687364831e-10 |
| Max raw cylinder force norm, N | 0.19385715086 at 30.0002 s |
| NaN/Inf, turbulence bounding, fatal solver warning | None found |

The final 30.02 s point file differs bytewise because OpenFOAM rewrote its header/format, but direct decoding of all 94,498 vector coordinates found **max absolute coordinate change = 0.0 m**, with no changed coordinate component. Both initial and final `pointDisplacement` are uniform zero. Final `checkMesh` passed with positive volumes, unchanged quality metrics, and no topology errors. Mesh Co and intermediate point-velocity maxima were not directly emitted; the exact final coordinate identity is the supported zero-motion observation.

### Startup-transient review gate

At 30.0002 s, max `p` jumped from the mapped state's 0.05357864538 to 4.5318815932 m²/s². Raw `Fx` jumped from the measured new F0 `0.0655270406896` to `0.188071358405` N (2.87013×); total force norm peaked at `0.19385715086` N. At 30.0004 s `Fx` had already fallen to approximately `0.0728168874` N. The solver then continued to 30.02 s with Co < 0.403, bounded U/k/omega/nut, no SIGFPE, and final `Fx = 0.068230402639` N. This is **not** a sustained multi-order-of-magnitude force explosion or an RBF mesh-motion failure. Nevertheless, it is a substantial first-step transient relative to the intended physical release state, and its exact mechanism has not been demonstrated. Reconstructed surface flux `phi` after cross-mesh volume-field mapping is a plausible contributor, **not a confirmed cause**.

Accordingly, Phase 1K.10 passes the specific mapping readability, 30 s force recovery, 100-step fluid runtime, and stationary-RBF checks, but the scientific readiness gate for an immediate new-mesh five-window FSI test remains **REVIEW_REQUIRED**. The next action is a read-only review of that first-step pressure/flux adjustment and its first-window coupling consequences. No dt, turbulence, mesh, RBF, IQN, or ANCF parameter was tuned, and no further run was started.

Machine-readable records: `source_mesh_identity.json`, `target_mesh_identity.json`, `field_mapping_manifest.json`, `new_release_force.json`, `fluid_only_runtime_identity.json`, `fluid_only_metrics.json`, `process_cleanup.json`, and `qualification_summary.json` in the run directory. The original Phase 1I/1J/1K.5/1K.6/1K.7/1K.9 evidence remains present and untouched.
