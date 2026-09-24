# Phase 1K.9 — Verified RBF Solver Integration

## Result

**Solver port build: PASS. Prescribed ALE motion on the new 6D O-grid scratch mesh: PASS. Full production mesh transition: PENDING.**

The source, clean build, installed shared library, and scratch runtime artifact have matching binary hashes. The solver successfully moved the new mesh through a prescribed `0.02D` lateral displacement and back; `checkMesh -allTopology -allGeometry` passed at both moved states. No CFD equations, OpenFOAM flow solver, preCICE participant, ANCF worker, or FSI runtime were run.

This does **not** yet make the authoritative HH06 restart ready to run on the new mesh. The production `30/` fields still belong to the old mesh, and the production `constant/polyMesh` was intentionally not replaced or remapped in this phase. The production `dynamicMeshDict` now selects the new RBF port, so do not launch the coupled case until a separately authorized, provenance-preserving restart-field mapping/mesh-transition step is completed.

## Upstream source and port provenance

| Item | Identity |
|---|---|
| Upstream repository | [solids4foam/solids4foam](https://github.com/solids4foam/solids4foam) |
| Release | `v2.4` |
| Pinned commit | `1341312f951caf4d8fcc69499c6ce1a588826156` |
| Upstream subtree | `src/RBFMeshMotionSolver/` |
| License | GNU GPL v3 or later; full license retained at `third_party/solids4foam_rbf/LICENSE` |
| License SHA256 | `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986` |
| Upstream README SHA256 | `959baffa8e7ffd0beacbac507ba31a15a2c78a3d61c3d9f3522c43b9894ddadc` |
| Exact upstream snapshot check | `diff -qr` against the pinned checkout reported no differences |
| Upstream snapshot manifest SHA256 | `5545b649dc5e71b7d4c383930cfdf9f6690b6caf5e8d2e9cea9eaf6be628dc58` |

The upstream README describes its short transient example as checked with OpenFOAM.com v2312, not OpenFOAM Foundation 10. This integration is therefore an explicit Foundation-10 API port that was compiled and exercised locally; it is not a claim that upstream v2.4 natively supports the Foundation-10 ABI. The upstream README and pinned solver source are linked here: [RBF solver documentation](https://raw.githubusercontent.com/solids4foam/solids4foam/v2.4/src/RBFMeshMotionSolver/README.md), [pinned solver source](https://github.com/solids4foam/solids4foam/blob/1341312f951caf4d8fcc69499c6ce1a588826156/src/RBFMeshMotionSolver/RBFMeshMotionSolver.C), [license](https://github.com/solids4foam/solids4foam/blob/v2.4/LICENSE).

The port source is under `third_party/solids4foam_rbf/of10/`; the unmodified pinned subtree is retained separately under `third_party/solids4foam_rbf/upstream/`. The port preserves the upstream interpolation and kernel implementations while adapting the solver-facing API to Foundation 10: runtime registration through `motionSolver`, `displacementMotionSolver` inheritance, point-patch `pointDisplacement` input, absolute displacement interpolation from `points0`, and Foundation-10 addressing-file APIs. The port's C++ source/header/Make manifest hash is `83129a34b3d9a984f9b1409c5dd10b5732dd9fe20987654ec5651e4ad8592def`.

| Port file | SHA256 |
|---|---|
| `of10/RBFMeshMotionSolver.C` | `14d5a2d2d7a95c83681e6c6fea2dc61a3fefca73fd81d3d18345d7da84bee793` |
| `of10/RBFMeshMotionSolver.H` | `22d41d8d7829c2a4ac7a6f5d6b404da5e549c208710e041f73e4b79a9867239a` |
| `of10/FieldSumOp.H` (pinned upstream helper) | `f19cbf0a1c6c521f32cb31fd5f7a51f15f55600a1fa13b8daf442b07cb2ca343` |
| `of10/Make/options` | `e88122aa5ea94e5359a575b2f924ba560a77803b357a9352314501c94fcbef40` |

## Build and binary identity

| Property | Recorded value |
|---|---|
| OpenFOAM | `OpenFOAM-10`, build `10-c4cf895ad8fa` |
| `WM_OPTIONS` | `linux64GccDPInt32Opt` |
| Compiler | GCC `11.4.0-1ubuntu1~22.04.3` |
| Build system | OpenFOAM `wmake libso`; no CMake used |
| Eigen headers | `libeigen3-dev 3.4.0-2ubuntu2`, extracted to scratch; not installed system-wide |
| Eigen package SHA256 | `04ee3759712a0f003fb186edf83724947826d7a43f3ef8d858cd359ca38a25ef` |
| Clean build command | `source /opt/openfoam10/etc/bashrc`; set `EIGEN3_INCLUDE_DIR` to the extracted Eigen include directory and `FOAM_USER_LIBBIN` to the isolated build output; run `wclean lib && wmake libso` from `third_party/solids4foam_rbf/of10/` |
| Clean build log | `evidence/phase1k9_verified_rbf/run-20260924T081544Z-c2245ff/logs/wmake-clean-build.log` |
| Installed runtime library | `/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libRBFMeshMotionSolver.so` |
| ELF Build ID | `f5ba43436c00f75dd314136806e0a00c632d0d58` |
| Clean build SHA256 | `b27b347c4ba3026a495517ae7ae237ceb5cd8408ac0db9af6a58ccd83647a20c` |
| Installed library SHA256 | `b27b347c4ba3026a495517ae7ae237ceb5cd8408ac0db9af6a58ccd83647a20c` |
| ABI dependency check | `ldd -r` under the sourced Foundation-10 environment: no missing dependencies or unresolved symbols |

The scratch `moveMesh` run loaded `/tmp/solids4foam-rbf-phase1k9.8TGZTs/build-output/libRBFMeshMotionSolver.so`; its SHA256, the clean-build output SHA256, and the installed library SHA256 all match. The binary is installed outside Git and is not committed. The exact Eigen package used for this build and its hash are preserved in the run evidence directory. The unrelated pre-existing `libRBFMotionSolver.so` was not reused, overwritten, or removed.

## HH06 configuration audit

The production file `cases/hh06_single_slice/constant/dynamicMeshDict` now parses as an OpenFOAM dictionary and selects the class successfully in the scratch prescribed-motion test. The same solver configuration is preserved in `evidence/phase1k9_verified_rbf/run-20260924T081544Z-c2245ff/candidate_dynamicMeshDict`.

| Entry | Selected value / meaning |
|---|---|
| Outer mover | `type motionSolver` |
| Solver library | `motionSolverLibs ("libRBFMeshMotionSolver.so")` |
| Port runtime solver | `motionSolver RBFMeshMotionSolver` |
| Moving patch | `cylinder` |
| Static patches | Empty; no extra zero-motion boundary controls requested |
| Fixed patches | `inlet outlet upper lower` |
| Input field | Absolute point-patch values from `pointDisplacement`; `faceCellCenters no` |
| RBF kernel | `TPS`, whose source uses `r² log(r)` for positive Euclidean distance and zero at `r=0` |
| TPS support radius | Not used; the radius parameter is required only by the Wendland kernels |
| Polynomial / CPU / fullCPU | `no / no / no` |
| Coarsening | Enabled; `tol=0.05`, `minPoints=20`, `maxPoints=200`, live selection enabled, `tolLivePointSelection=0.05`, export/two-point/surface correction disabled |

The coarsening values match the upstream `perpendicularFlap` example and are not represented as HH06-optimal values. In the prescribed-motion log the solver selected 20 of 846 controls; the reported relative 2-norm error was `0.0111694`, and maximum point error was `0.0134906`, both below `0.05`.

### O-grid ring treatment

The 6D O-grid perimeter is an internal mesh interface, not a named boundary patch. The upstream `movingPatches`/`staticPatches`/`fixedPatches` interface cannot independently pin that ring. It is therefore **not fixed** by this configuration. No unsupported control-point keyword was invented. The small prescribed test shows acceptable mesh quality for the tested displacement only; it does not prove near-field quality for large or sustained motion. If later qualification requires the ring to be fixed or move rigidly, the solver needs a separately designed and tested internal point-zone control mechanism before that behavior can be claimed.

## Mesh identity and prescribed ALE test

The geometry and generated mesh are the Phase 1K.5 artifacts:

| Item | Identity |
|---|---|
| Geometry | `evidence/phase1k5_rbf_ale/preflight-20260924T1432-c2245ff/hh06_single_slice_og6d_rbf_y12p5d.geo` |
| Gmsh | `4.8.4` |
| Geometry SHA256 | `9a19a3b7b593bdf7bbd39409ec8b5fa4958135eac714b24421dfeb0222d9a5d2` |
| Generated MSH2 SHA256 | `c467ec6cb763864608c84acabef3a2160d48171005291035cae5cf2ddd08fab4` |
| Gmsh reported mesh | 94,500 nodes; 146,870 elements |
| OpenFOAM cells / faces | `46,826` / `187,727` (`93,229` internal faces) |
| Patch names | `front`, `cylinder`, `back`, `inlet`, `upper`, `lower`, `outlet` |
| Cylinder interface | 200 faces; compatible name and face count for the existing preCICE interface |

The test used an isolated copy of the new mesh and a prescribed cylinder displacement from `0` to `0.00056 m` in y and back to `0` (`0.02D` for `D=0.028 m`), at times `30.0002` and `30.0004 s`. The command was OpenFOAM-10 `moveMesh`, not `pimpleFoam`; no flow equations or coupling participants were run. The run log confirms the plugin and TPS were selected, then `checkMesh -allTopology -allGeometry` passed at both moved states.

| State | Max aspect ratio* | Minimum cell volume (m³) | Max non-orthogonality | Max skewness | Result |
|---|---:|---:|---:|---:|---|
| Initial, 30.0 s | 6.382834 | `7.68736483059e-10` | `43.8460°` | `0.896980` | `Mesh OK` |
| Displaced, 30.0002 s | 6.392453 | `7.68303679837e-10` | `43.8629°` | `0.897043` | `Mesh OK` |
| Returned, 30.0004 s | 6.382834 | `7.68736482553e-10` | `43.8460°` | `0.896980` | `Mesh OK` |

\*`checkMesh` reports aspect ratio in the two non-empty geometric directions for this empty-front/back 2D mesh. The `moveMesh` internal geometry check additionally prints a 3D ratio that includes the thin spanwise thickness; those two aspect-ratio figures are not directly comparable. The minimum volume remained positive and returned to the initial value to numerical precision.

Full logs, scratch case, prescribed displacement field, build log, and the Eigen package are under `evidence/phase1k9_verified_rbf/run-20260924T081544Z-c2245ff/`.

## Production restart mesh boundary

The new test mesh was **not** copied over `cases/hh06_single_slice/constant/polyMesh`. It is not the mesh associated with the current 30 s restart:

| Identity check | Current production case | New scratch test mesh |
|---|---|---|
| y extent | `±0.42 m` | `±0.35 m` |
| `points` SHA256 | `41d2d570fb801c4bab9e40cc1c0644150cbaddaa5903e682e9e78b333e3b93bf` | `8cd3213978b1ab7d324f8e41a5669ab4029a2c500f3de986f8f9dca465d53fd3` |
| `faces` SHA256 | `d2a7dfeefed80fc08af488a83e9bf26d9e570c7db22a3392faa918b21a332242` | `55c44296d5e48469ff64d44d1176dd7fe180881d2b581224ba57cf2c6d66a92c` |
| Total volume | `0.01973956178 m³` | `0.01644676385 m³` |

The `30/p`, `30/U`, turbulence fields, and current production mesh were left untouched. Replacing only `polyMesh` would pair fields with a different mesh; remapping those fields is outside this compile/ALE qualification and has not been done. Consequently, the configuration change is not authorization to start HH06 FSI.

## Changed files and boundary

- Modified production configuration: `cases/hh06_single_slice/constant/dynamicMeshDict` only.
- Added third-party source/license/port notes: `third_party/solids4foam_rbf/` (`upstream/` snapshot plus `of10/` Foundation-10 port).
- Added this report and isolated run evidence under `evidence/phase1k9_verified_rbf/`.
- No production mesh, restart field, preCICE XML, worker, ANCF source, OpenFOAM fluid setting, or physical parameter changed.
- No FSI run and no Git commit were made.

**Stop reached.** The solver is built and the small scratch ALE test passes. Production adoption of the 6D mesh remains gated on a separately reviewed mesh/restart-field transition; no 5-, 25-window, or FSI qualification was started.
