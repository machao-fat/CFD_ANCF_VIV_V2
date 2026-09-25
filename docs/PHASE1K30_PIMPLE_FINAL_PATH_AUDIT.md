# Phase 1K.30 - PIMPLE final-path audit

## Scope and provenance

This is a source-level audit for the isolated Phase 1K.30 diagnostic. The
runtime is Foundation OpenFOAM 10 and the case is the K28 old-native B1/G2
software-reference case. The diagnostic does not modify the production case,
the production adapter, the mesh, the timestep, turbulence parameters,
discretisation schemes, coupling tolerances, relaxation settings, or IQN.

The audited sources are the installed Foundation OpenFOAM 10 sources under
`/opt/openfoam10`, the K29 diagnostic solver source archived under
`evidence/phase1k29_cfd_inner_convergence/run-20260925T214500Z-9747b00/solver-source/`,
and the K29 old-native `fvSolution` scratch copy. The relevant solver source
files are `pimpleFoam.C`, `UEqn.H`, `pEqn.H`, `pimpleLoop.C/H`,
`pimpleControl.C/H`, `pimpleNoLoopControl.C/H`, `pisoControl.C/H`,
`nonOrthogonalSolutionControl.C/H`, `fvMatrixSolve.C`, and
`singleRegionSolutionControl.C`.

## Current K28/K29 solver configuration

The K29 A configuration, which copies the K28 B1/G2 settings, is:

```text
PIMPLE:
  nOuterCorrectors         3
  nCorrectors              2
  nNonOrthogonalCorrectors 0
  momentumPredictor        yes
  turbOnFinalIterOnly      default true (not explicitly present)

solvers:
  p                 GAMG, tolerance 1e-8, relTol 0.1
  pFinal            $p, relTol 0
  (U|k|omega)       smoothSolver, tolerance 1e-7, relTol 0.1
  (U|k|omega)Final  $U, relTol 0
  cellDisplacement  GAMG, tolerance 1e-5, relTol 0
  cellDisplacementFinal $cellDisplacement, relTol 0
```

The relaxation entries are `p=0.3`, `U=0.5`, `k=0.2`, `omega=0.2`, and
`(U|k|omega)Final=1.0`. They are unchanged by K30. No residual-control
dictionary is present.

## Actual execution order

Foundation `pimpleFoam.C` performs the following operations for a transient
time step:

1. `mesh.update()`, then `runTime++`.
2. `while (pimple.loop())` enters the outer corrector. Mesh motion is done on
   the first outer iteration (or on every iteration if
   `moveMeshOuterCorrectors` is enabled).
3. `fvModels.correct()` and `UEqn.H` are executed. With
   `momentumPredictor yes`, the momentum equation is solved.
4. `while (pimple.correct())` executes the PISO pressure-corrector loop;
   `pEqn.H` builds and solves the pressure equation and updates `phi` on its
   final non-orthogonal iteration. With `nCorrectors=2` and zero
   non-orthogonal correctors, this is two pressure solves per outer iteration.
5. `if (pimple.turbCorr())` calls `viscosity->correct()` and
   `turbulence->correct()`.
6. The outer loop repeats; after it exits, `runTime.write()` is called.

The runtime log confirms this order. In the K29 A run, the `omega` and `k`
solves occur only in outer 3, consistent with the default
`turbOnFinalIterOnly=true`.

## Why outer 3 is final in A

`pimpleLoop::read()` reads `nOuterCorrectors` into `nCorrPimple_`.
`pimpleLoop::finalPimpleIter()` returns true when
`corrPimple_ >= nCorrPimple_` (or when a convergence flag requests the final
iteration). For A, outer 3 therefore has `finalPimpleIter() == true`.

`pimpleControl::loop()` calls `updateFinal()` before returning to the solver.
`singleRegionSolutionControl::updateFinal()` adds the mesh data flag
`finalIteration=true` when `isFinal()` is true and removes it otherwise.

The final flag is consumed centrally by OpenFOAM rather than by a special
`pimpleFoam` branch:

* `fvMatrix::solve()` selects `fieldName + "Final"` when the transient mesh
  has `finalIteration=true`.
* `fvMatrix::relax()` selects the `fieldName + "Final"` equation relaxation
  factor when present.
* `GeometricField::relax()` selects the `fieldName + "Final"` field
  relaxation factor when present.
* `pEqn.H` uses the same matrix solve mechanism, so the pressure solve uses
  `pFinal` on a final outer iteration.

Consequently, A outer 3 uses `pFinal` and the final U/k/omega policy, while
K29 B outer 3 in a six-outer run is non-final and uses the ordinary `p` and
`(U|k|omega)` entries. This is the source-level explanation of the K29
`INNER_AB_NOT_CONTROLLED` result.

There are no literal `UFinal`, `kFinal`, or `omegaFinal` equation blocks in
the case. The regex entry `(U|k|omega)Final` supplies those names. The
`pFinal` entry is explicit. `cellDisplacementFinal` applies to the mesh-motion
solve, not to the PIMPLE momentum/pressure path.

## `finalIter` and `finalInnerIter`

The relevant OpenFOAM 10 names are `finalPimpleIter()`,
`finalPisoIter()`, `finalNonOrthogonalIter()`, and `finalInnerIter()`; the
generic `finalIteration` mesh-data flag is the solver-selection bridge. In
this case, `finalInnerIter()` is not used by `pimpleFoam` directly because
`nNonOrthogonalCorrectors=0`; `pEqn.H` uses
`finalNonOrthogonalIter()` to decide when to assign the final pressure flux.
The final outer flag nevertheless changes matrix selection and relaxation
for all transient equations solved while the flag is set.

## Turbulence correction timing

`pimpleControl::turbCorr()` returns
`!turbOnFinalIterOnly() || finalPimpleIter()`. Since the case uses the
default `turbOnFinalIterOnly=true`, `viscosity->correct()` and
`turbulence->correct()` execute only on the final PIMPLE outer iteration in
the observed K29 run. The production prefix must preserve this behavior.

The K30 continuation is deliberately not another call to `pimple.loop()`.
After the production outer loop exits, the pimple loop state has been reset
and its `finalPimpleIter()` is false. The isolated continuation therefore:

* leaves physical time, mesh, displacement, and preCICE state unchanged;
* sets the diagnostic mesh `finalIteration=true` flag so the existing final
  solver and relaxation entries are selected;
* explicitly repeats the UEqn, pressure-corrector loop, and one turbulence
  correction per continuation cycle;
* does not call `pimple.turbCorr()`, because that would be false after the
  normal outer loop reset even though a complete diagnostic turbulence
  correction is required;
* records raw Force and fields only, without executing the adapter write or
  calling `participant.advance()`.

This is a same-time-step post-final continuation, not `nOuterCorrectors=6`
and not a production setting recommendation.

## Force timing

The direct Force diagnostic is evaluated after the pressure-corrector loop and
after `viscosity->correct()`/`turbulence->correct()` at the corresponding
observation point. The K30 production-prefix observation is therefore after
the exact K29 outer-3 final path. Continuation observations use the same raw
Force calculation after each complete diagnostic cycle. Adapter preWrite and
Structure reads remain coupling observations for the production prefix only;
continuation observations are not written to preCICE.

## Audit conclusion

The controlled K30 design is source-consistent: first three outer iterations
are copied from K29 A, including final-path activation on outer 3, and only
then are C1-C3 executed on the unchanged time-step state with final solver
selection. The continuation result remains conditional on the production
prefix equivalence gate and fresh-process repeatability gate.
