# Phase 1K.13-A — RBF displacement observability feasibility audit

## Decision and scope

**Classification: `EXPERIMENTAL_INSTRUMENTATION_REQUIRED`.** Existing Phase 1K.11 artifacts show the Structure displacement written to preCICE, a Fluid-side mapping/read event, some accepted-window displacement fields, and per-attempt RBF/ALE activity. They do **not** contain the numerical Fluid adapter read, the `pointDisplacement` value entering RBF on a rejected trial, the selected control-point displacement vectors, or the trial mesh-point coordinates. Consequently they cannot establish whether the RBF solver received and applied the Structure displacement on that same rejected attempt. The Phase 1K.12 `REVIEW_REQUIRED` displacement-path conclusion remains unchanged.

This is a read-only audit of the current repository, installed binaries, and preserved `evidence/phase1k11_25window_rbf_fsi/run-20260924T095422Z-c2245ff/`. No participant, solver, post-processing run, build, debugger session, configuration change, or parameter change was made. Git HEAD at audit: `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`; pre-existing untracked reports/evidence/source were left untouched.

## Qualified identity versus a possible diagnostic identity

| Component | Qualified Phase 1K.11 runtime identity | Source/diagnostic boundary |
| --- | --- | --- |
| RBF solver | `/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libRBFMeshMotionSolver.so`; SHA256 `b27b347c4ba3026a495517ae7ae237ceb5cd8408ac0db9af6a58ccd83647a20c`; ELF Build ID `f5ba43436c00f75dd314136806e0a00c632d0d58` | Port source exists at `third_party/solids4foam_rbf/of10/`; its Phase 1K.9 clean-build provenance is recorded in `docs/PHASE1K9_VERIFIED_RBF_SOLVER_INTEGRATION.md`. A newly instrumented build would be **experimental**, with its own path, name, SHA256, Build ID and build manifest. It must not replace or be reported as the qualified binary. |
| Fluid preCICE adapter | `/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so`; SHA256 `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572`; ELF Build ID `e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b` | Exact source-to-binary lineage remains unresolved. No source patch may be represented as an instrumentation build of this qualified adapter without a separate provenance/identity gate. |

Both installed shared objects retain symbol tables but do not contain `.debug_info`. The qualified adapter exports `preciceAdapter::FSI::Displacement::read(double*, unsigned int)`; the RBF library exposes its solver methods. Symbol-level breakpoints might be explored in a separately authorized experiment, but their ability to extract the complete numerical arrays or checkpoint state from optimized binaries is **unverified**. A debugger would also perturb runtime timing. Symbol visibility is not equivalent to existing attempt-level evidence.

## Existing OpenFOAM and ALE observability

| Link or state | Already observable | Missing for a rejected attempt |
| --- | --- | --- |
| Structure output | `structure_trace.jsonl` records each `D_trial_interface_m` and `D_written_to_precice_m` (124 attempts); Phase 1K.12 found equality on every attempt. | Nothing at the Structure write point; subsequent Fluid receipt is a separate question. |
| Fluid field after coupling | Saved time directories contain `cellDisplacement`, `pointDisplacement`, `polyMesh/points`, `meshPhi` and cell volume `V`. Accepted `cellDisplacement` generally follows Structure's accepted displacement. | No separately preserved per-retry field snapshots or before/after-rollback point arrays. The same physical time is reused during implicit attempts; an ordinary time-directory write cannot be assumed to identify a particular attempt. |
| RBF input and result | Fluid stdout says `Selecting motion solver: RBFMeshMotionSolver`, reports coarsening selected counts/errors, and emits `Mesh Courant Number` per solve. Nonzero later-window mesh Co is an indirect motion indicator. | Numerical `pointDisplacement` at the cylinder immediately before `solve()`, `motionCenters`, selected control-point values, interpolated displacement, `curPoints()` coordinates, and per-attempt minimum cell volume. Mesh Co alone cannot prove where the cylinder points moved. |
| Accepted output | Phase 1K.12 found saved `pointDisplacement` cylinder values zero and accepted `polyMesh/points` identical to release points; the Fluid log writes updated results after a completed coupling timestep. | Whether the rejected-trial mesh moved before rollback, and exactly why accepted fields/points are zero or unchanged. Accepted snapshots must not be assigned to earlier rejected attempts. |

The current case `system/controlDict` sets normal field-writing controls and diagnostic function objects for forces and flow extrema, not an adapter-read or RBF-entry vector trace. Installed OpenFOAM-10 has a `writeObjects` function object (`/opt/openfoam10/src/functionObjects/utilities/writeObjects/writeObjects.H`), but ordinary scheduled object writes do not provide a verified hook immediately after each adapter read and before/after each RBF solve. Adding such a function object would also change a runtime configuration, outside this audit. OpenFOAM debug switches do not close the gap: `RBFMeshMotionSolver.C:30` registers a debug switch, yet the needed vector values have no corresponding runtime debug print; `RBFCoarsening.C:26-27` uses a hard-coded `debug = 0`. Existing coarsening messages print counts/errors, not control-point displacement vectors.

## Existing preCICE observability

The preserved Fluid stdout logs `Mapping "Displacement" ... from "Structure-Mesh" to "Fluid-Mesh"` for coupling attempts. `precice-profiling/Fluid_0000-0-1.txt` names `map.nn.mapData.FromStructure-MeshToFluid-Mesh` and `readData.Fluid-Mesh_Displacement` events with timing information. Structure profiling names `writeData.Structure-Mesh_Displacement`. These support an exchange/event chronology, **not** a numeric assertion that the adapter received a particular `(Dx,Dy)` or assigned it to `pointDisplacement`. The installed preCICE `Participant::readData` API returns values into a caller-provided buffer; the preserved timing/profiling records do not serialize that buffer. Convergence and mapping logs likewise do not expose the RBF boundary condition.

## RBF source availability and a separately identifiable future instrument

The OpenFOAM-10 port in `third_party/solids4foam_rbf/of10/RBFMeshMotionSolver.C` provides exact prospective observation points:

1. In `solve()`, after `pointDisplacement_.correctBoundaryConditions()` (`:305`), capture cylinder boundary values and, after `motionCenters` is populated (`:306-322`), capture the moving control-point input.
2. At the control-value assembly (`:804-829`), capture selected moving/fixed indices and value norms; existing coarsening output alone is insufficient.
3. After interpolation (`:849-866`) and assignment to `newPoints` / the point field (`:895-899`), capture norms and representative cylinder/far-field point displacements. `curPoints()` (`:291-299`) constructs actual points from `points0() + newPoints`; observing `newPoints` without the final mesh update would still be incomplete.
4. Pair each numeric record with physical window, coupling attempt, preCICE event, and before/after-rollback phase. A solver-only print lacking attempt identity could be misjoined to the wrong retry.

The source `Make/files` currently outputs `$(FOAM_USER_LIBBIN)/libRBFMeshMotionSolver`. A future authorized diagnostic could copy the port into an isolated tree and build a **separately named** `libRBFMeshMotionSolverPhase1K13Diag.so` into an isolated output directory, with its own hash/Build ID and explicit experimental run manifest. This is a feasibility proposal, **not a build or qualification performed here**. Loading both registrations together, or silently replacing the pinned library, is not acceptable; class registration/loading and diagnostic overhead would require independent review. If numerical adapter-read capture is needed, first evaluate an external observation method against the exact pinned adapter; do not presume the unmatched candidate adapter source is authoritative or overwrite the pinned binary.

## Gate for a subsequent experiment

Existing artifacts are **insufficient**, but observability is not blocked because the exact RBF port source and instrumentable call sites are present. A separately approved experiment must define an attempt-correlated record at each interface—Structure write, adapter numeric read, point-field boundary, RBF control values, mesh points before/after update and rollback—and preserve qualified-versus-experimental binary identity in its report. This audit does not authorize that experiment, an FSI rerun, a production adoption decision, or any parameter change.
