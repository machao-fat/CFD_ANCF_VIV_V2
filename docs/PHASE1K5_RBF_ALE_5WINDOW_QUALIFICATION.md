# Phase 1K.5 — RBF ALE Mesh Replacement Qualification

## Result

**Classification: `REVIEW_REQUIRED` — static mesh passed; RBF motion and the 5-window FSI qualification were not run.**

The supplied 6D O-grid mesh was generated and passes OpenFOAM 10 `checkMesh` after applying the existing single-slice patch-type contract in an isolated scratch case. The `cylinder` patch is present with 200 faces, matching the current Fluid/preCICE interface.

The installed `libRBFMotionSolver.so` is a candidate binary, but its source-to-binary lineage, RBF kernel, control-point selection, fixed far-field behavior, and support-radius semantics cannot be established from the current V2 repository or local OpenFOAM installation. Configuring numeric values without those semantics would be speculative. Therefore no candidate RBF `dynamicMeshDict` was invented, no mesh-motion test was performed, and no Fluid, preCICE, Structure, ANCF, or worker runtime was started. This is a qualification gate, **not** an observed RBF failure and not a mesh-quality failure.

The supplied `.geo` file is treated as a geometry asset. Comments embedded in it are recorded as source annotations and checked against generated mesh output; they do not override the user's task/scope instructions.

## Input and mesh generation

Input path supplied by the user: `D:/CFD/CFD_ANCF_VIV_reentry_runtime/OpenFOAM_cylinder-main/1/12.5d.geo`.

The file contents identify it as the intended 6D O-grid / RBF-motion geometry, despite its shorter filename. SHA256 is `9a19a3b7b593bdf7bbd39409ec8b5fa4958135eac714b24421dfeb0222d9a5d2`. No other content from the directory containing that file was inspected.

| Item | Result |
|---|---|
| Gmsh | 4.8.4 |
| OpenFOAM | OpenFOAM-10, build `10-c4cf895ad8fa` |
| Gmsh command | `gmsh -3 -format msh2 -o hh06_single_slice_og6d_rbf_y12p5d.msh hh06_single_slice_og6d_rbf_y12p5d.geo` |
| Gmsh output | 94,500 nodes; 146,870 elements reported by Gmsh |
| Gmsh mesh SHA256 | `c467ec6cb763864608c84acabef3a2160d48171005291035cae5cf2ddd08fab4` |
| OpenFOAM volume mesh | 46,826 cells, all hexahedra; 94,498 points; 187,727 faces, 93,229 internal faces |
| Physical patch names | `front`, `back`, `cylinder`, `inlet`, `upper`, `lower`, `outlet` |
| `cylinder` interface | 200 faces; name matches the current preCICE Fluid interface |

The generated Gmsh mesh initially imports each boundary as a generic `patch`. On that first scratch check, OpenFOAM treated the nominally two-dimensional mesh as three-dimensional and failed the cell-determinant check. Applying the current case's patch classifications in scratch only—`front/back=empty`, `cylinder=wall`, `upper/lower=symmetryPlane`, inlet/outlet=`patch`—produced a clean full check. Patch names, face counts, and `startFace` ranges matched the existing case boundary manifest. The authoritative case boundary and mesh were not changed.

### Static quality

| Metric | Existing 3D O-grid baseline mesh | New 6D O-grid / y=±12.5D mesh |
|---|---:|---:|
| Cells | 46,826 | 46,826 |
| Max aspect ratio | 25.8685 | 6.38283 |
| Minimum cell volume (m³) | 7.687364982e-10 | 7.687364831e-10 |
| Max non-orthogonality | 44.0049° | 43.8460° |
| Average non-orthogonality | 8.71972° | 7.81653° |
| Max skewness | 0.854516 | 0.896980 |
| Cell determinant check | PASS | PASS |
| Full `checkMesh -allTopology -allGeometry` | `Mesh OK` | `Mesh OK` |

The new mesh preserves the smallest edge length at approximately `6.2294e-5 m`, consistent with the supplied geometry's stated first-wall-cell target. The candidate also changes the outer vertical domain from baseline `y=±0.42 m` (`±15D`) to `y=±0.35 m` (`±12.5D`), as well as enlarging the O-grid radius from the 3D baseline to 6D. Thus any later flow change would compare a combined geometry change and cannot be attributed solely to the motion algorithm or O-grid radius.

The five mesh-file hashes recorded in the Phase 1F runtime identity match the current authoritative baseline mesh. Its static check was repeated on a scratch copy for a like-for-like comparison; no outputs were written into the authoritative case.

## RBF implementation audit

No RBF motion-solver source, header, documentation, or example dictionary was found in the current V2 source tree or `/home/machao/OpenFOAM/machao-10`. The environment does contain:

| Identity | Value |
|---|---|
| Library | `/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libRBFMotionSolver.so` |
| SHA256 | `e783ae0aa3765dee2a7f11f24d3a041b9d9b028795c4c703e48aca3a508cf188` |
| ELF Build ID | `d12bef3602874632c74204341110e7f8008e5dc7` |
| Embedded compiler comment | GCC 11.4.0 |
| Exported class | `Foam::rbfMotionSolver` |
| OpenFOAM ABI dependencies | Resolve to `/opt/openfoam10` Foundation OpenFOAM-10 libraries when that environment is sourced |
| Source-to-binary provenance | UNRESOLVED |

Read-only binary inspection exposed the literals `rbfDisplacement`, `movingPatch`, `controlStride`, and `supportRadius`, plus errors requiring positive `controlStride` and positive `supportRadius`. It also contains an error for a missing `movingPatch`. These literals establish that some inputs exist; they do **not** establish the kernel formula, whether the solver uses compact support, which points become fixed controls, how `controlStride` samples controls, or the support-radius units/meaning. The binary has no installed source/debug information from which to confirm those details.

| Required design item | Audit result |
|---|---|
| Motion-solver class name | `rbfMotionSolver` is exported |
| RBF kernel | UNRESOLVED |
| Near-field control-point definition | UNRESOLVED; only the `movingPatch`/`controlStride` input names are visible |
| Far-field fixed-point definition | UNRESOLVED |
| Deformation/support radius | `supportRadius` must be positive; value, units, and physical interpretation are unresolved |
| Current dynamic-mesh configuration | Remains `displacementLaplacian`; SHA256 `56158d50b6198b6b129e384302dfe1737b50cb9d7f40b08c9252ed6b52f83bf2` |
| RBF configuration or movement test | Not created or run |

Without authoritative semantics, it is not possible to prove that the near-cylinder boundary-layer mesh is preserved while displacement transfers outward or that the required far-field points remain fixed. Consequently the non-FSI imposed-motion gate and five-window qualification were both withheld.

## Comparison with prior runtime evidence

| Metric | Phase 1F Laplacian, 5 windows | Phase 1I Laplacian failure region | New candidate |
|---|---:|---:|---:|
| Static min volume | 7.687364982e-10 m³ | Not a single static value; saved snapshots reached -1.1983e-10 m³ | 7.687364831e-10 m³ |
| Fluid Co max | 0.420761851 | 21.4545 | Not measured; no flow run |
| Mesh Co max | Unavailable | 21.3015 | Not measured; no motion/flow run |
| Mesh velocity max | Unavailable | Unavailable | Not measured; no motion test |
| Max `|U|` | Unavailable | 33.1658 m/s sampled before failure | Not measured |
| `omega` max | Unavailable | 4.57795e11 sampled | Not measured |
| Coupled windows | 5 completed, all with the previous Laplacian mesh motion | 20 accepted; Fluid SIGFPE in window 21 | 0 |

Static mesh quality alone does not demonstrate ALE improvement. No dynamic mesh, force, turbulence, IQN, or coupling comparison exists for the RBF candidate. In particular, the previous Phase 1I failure mechanism has **not** been shown to improve or recur under RBF.

## Frozen runtime identity and repository boundary

| Component | Current identity |
|---|---|
| Branch / HEAD | `repair/worker-lineage-implicit-contract-v1` / `c2245ff396ff42dfa5e80fee6555a9ede93e3b04` |
| Worker source SHA256 | `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e` |
| Worker binary SHA256 | `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596` |
| Fluid adapter SHA256 | `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572` |
| preCICE | Runtime 3.4.1; Python metadata 3.4.0; production XML SHA256 `71643ae8042f44e2a661d37ab68b680ae4650bf7118c8d08879cbe441f657211` |
| Python | `/usr/bin/python3.10`, Python 3.10.12 |
| 30.0 s restart | Current field hashes are recorded in the machine-readable runtime identity; no solver was run, and the restart was not modified |

No worker was started. No OpenFOAM solver or preCICE participant was initialized. No ANCF solve occurred. No production case, `dynamicMeshDict`, preCICE XML, solver setting, or physical parameter was changed. The RBF library was inspected but not loaded into a solver process.

The worktree was already untracked before Phase 1K.5 (`docs/PHASE1J_ALE_FLUID_FAILURE_AUDIT.md` and `evidence/phase1i_25window_iqn/`). Phase 1K.5 adds only this report and `evidence/phase1k5_rbf_ale/`; no commit was made.

## Gate to resume

To continue with the approved staged approach, the RBF motion implementation needs an authoritative source/build identity or a version-matched implementation document/example that resolves the exact kernel and control/fixed-point/radius semantics. Once that evidence is available, the next permitted action is a scratch, non-FSI prescribed-displacement test on this mesh. Only if that gate passes should a fresh 30.0 s scratch case be configured and the one authorized five-window run considered.

**Stop reached:** no 25-window run, no parameter tuning, no change to IQN/coupling/worker/ANCF/CFD settings, and no three-slice work.
