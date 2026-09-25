# Phase 1K.26 — OpenFOAM execution-stage map

Status: source-audited map used by the Phase 1K.26 diagnostic runtime. Actual
stage coverage and results are recorded in
`PHASE1K26_EARLIEST_DIVERGENCE_REPORT.md`.

## Source identities inspected

| Component | Source | Relevant locations |
|---|---|---|
| Foundation OpenFOAM 10 `pimpleFoam` | `/opt/openfoam10/applications/solvers/incompressible/pimpleFoam/` | `pimpleFoam.C`, `UEqn.H`, `pEqn.H`, `createFields.H` |
| Foundation dynamic mesh | `/opt/openfoam10/src/finiteVolume/fvMesh/` and `/opt/openfoam10/src/fvMeshMovers/` | `fvMesh::move()`, `fvMesh::movePoints()`, `fvMeshMovers::motionSolver::update()` |
| Experimental adapter source used by K24/K25 diagnostics | `evidence/phase1k24_fluid_state_repeatability/run-20260925T074500Z-d3890de/adapter-source/` | `Adapter.C`, `Phase1K24StateSnapshot.H` |
| RBF motion source | `third_party/solids4foam_rbf/of10/` | `RBFMeshMotionSolver.C` |

## Verified per-attempt order

The adapter function object runs after the OpenFOAM solver has completed its
current time-step equations. In `Adapter::execute()` the adapter writes
coupling data, calls `preCICE::advance()`, queries the retry/window state, and
on retry restores its checkpoint. It then reads the next displacement at the
retry endpoint offset before the next solver time loop. The K24 source places
the existing S0/S1/S2 snapshots at checkpoint save, post-restore, and after
retry `readData(dt)`, respectively.

The solver then enters the next `pimpleFoam` time loop. `runTime++` occurs
before the PIMPLE corrector loop. On the first PIMPLE iteration `mesh.move()`
calls the configured mesh mover; the Foundation motion-solver mover obtains
`motionPtr_->newPoints()` and calls `fvMesh::movePoints()`. The latter sets
`moving_`, may create/update `meshPhi`, stores old volumes when the time index
advances, moves the polyMesh, updates geometric data, and invokes mesh-object
and function-object move callbacks.

## Diagnostic stage definitions

The names below are the observable stages for an isolated diagnostic solver.
Where an object cannot be read without changing solver behavior, the trace
must contain `NOT_OBSERVABLE_AT_STAGE` rather than an inferred value.

| Stage | Exact location / event | Primary observations |
|---|---|---|
| `S00` | Adapter checkpoint restore has returned; before the retry `readData(dt)` or before the next solver attempt | current fields, histories, point/cell displacement, mesh topology flags, time identity |
| `S01` | After adapter displacement read has populated the RBF-facing field; immediately before the next `mesh.move()` | displacement field and cylinder boundary values; current mesh points |
| `S02` | Inside the motion-solver path after `RBFMeshMotionSolver::solve()` has read `pointDisplacement` and produced its candidate `newPoints()`, before `fvMesh::movePoints()` | RBF input, candidate point displacement, control-point/cache proxy |
| `S03` | After `fvMesh::movePoints()` returns from the mesh mover | mesh points, volumes, `moving/changing`, point/cell displacement |
| `S04` | After mesh-motion flux/geometric updates and before the first momentum equation | `meshPhi`, `phi`, `Uf`, volume/history objects, mesh quality proxies |
| `S05` | Immediately before `UEqn.H` in the first PIMPLE iteration | all solver inputs and history topology |
| `S06` | After the momentum predictor/`UEqn` solve and constraints | `U`, matrix/solver result proxies, `phi` |
| `S07` | After the pressure-correction loop in `pEqn.H` | `p`, `phi`, `U`, `Uf`, continuity state |
| `S08` | After `viscosity->correct()` and `turbulence->correct()` | `k`, `omega`, `nut`, turbulence-model observable fields |
| `S09` | End of a later PIMPLE outer iteration before the next `UEqn.H` | same field set and iteration index |
| `S10` | End of the final PIMPLE outer iteration | same field set and final inner-loop identity |
| `S11` | Immediately before the adapter's post-solve force writer | force-object inputs and current fields |
| `S12` | Adapter force write / preCICE exchange endpoint | pressure/viscous/total force and preCICE payload if observable |

The isolated diagnostic `pimpleFoam` emitted `S01`, `S04`, `S05`, `S06`,
`S07`, `S08`, and `S11`; the existing experimental adapter emitted the
post-rollback `S00` proxy, and the separately identified RBF diagnostic build
emitted before/after correction and RBF-solve snapshots. There is **no**
per-attempt direct-force or unaccelerated outgoing-Force `S12` trace in this
phase. `S03` is covered only by the post-`mesh.move()` solver hook, not by a
separate intra-`fvMesh::movePoints()` record. These coverage limits must not
be filled by inference from preCICE-received Force.

## Important source-level qualification

`RBFMeshMotionSolver::solve()` is not called by `fvMeshMovers::motionSolver::update()`.
The motion-solver mover calls `motionPtr_->newPoints()`, and the RBF
implementation computes its displacement in the `newPoints()` path. Therefore
the diagnostic hook must not label a generic `mesh.move()` entry as “after RBF
solve”; it must either instrument the RBF `newPoints()` call path or mark the
RBF-internal output unavailable.

Likewise, a function-object snapshot taken from `Adapter::execute()` cannot be
treated as a momentum-, pressure-, or turbulence-stage snapshot: it occurs
after the solver equations. Those stage labels require an isolated diagnostic
`pimpleFoam` build or equivalent source-level hooks.

## Replay comparison contract

For same-process replay #1/#2 and branch-equivalent fresh-process controls,
each stage record must carry:

- solver attempt/time identity and process ID;
- hashes and extrema for geometry, ALE fields, primary fields, turbulence
  fields, and available history levels;
- RBF input/output and cache proxy, or an explicit unavailable marker;
- force components and provenance branch.

The earliest divergence is the first corresponding stage at which a hash,
topology flag, or numeric comparison differs. A final Force difference alone
does not identify the stage. Fresh-process A/B is only an oracle when the
execution branch, read offset, physical time, and displacement input match the
same-process replay branch.
