# Phase 1K.29 — CFD inner-convergence diagnostic plan

## Frozen scope

This diagnostic starts from K28 commit `9747b00884e9a0f7f74160520c17353e2d1f7518`
on branch `diagnostic/phase1k29-cfd-inner-convergence-v1`. It uses only the
old-native 30.0 s restart, the experimental B1/G2 `meshPhi` canonicalization
adapter, the native `displacementLaplacian` motion path, and one physical
coupling window. It does not modify the production case, adapter, mesh,
physics, timestep, schemes, turbulence parameters, coupling tolerances,
relaxation, IQN, or ANCF worker.

## Question and controlled comparison

The primary observable is the direct raw OpenFOAM cylinder Force and the
adapter's unaccelerated preCICE Force payload. Structure-received Force is
recorded only as downstream context and is not an inner-convergence metric.

* A is an exact copy of the K28 B1/G2 `fvSolution`: `nOuterCorrectors=3`,
  `nCorrectors=2`, `nNonOrthogonalCorrectors=0`, `momentumPredictor=yes`.
* B changes only `nOuterCorrectors` from 3 to 6 in a scratch case. All other
  dictionary bytes and all restart bytes must remain equal to A.
* A and B use the same fixed displacement
  `D*=(1.0633832164606064e-7, 9.530777190012017e-8) m` and one-window,
  four-attempt diagnostic ceiling.
* B is run twice from independent copies of the same restart to test fresh
  process repeatability before interpreting A/B sensitivity.

## Measurements

The isolated solver binary records direct pressure, viscous, and total Force
after every PIMPLE outer corrector, plus a stable per-face-array hash. It also
records field hash/norm statistics for `U`, `p`, `k`, `omega`, `nut`, and
`phi`. Final A/B field snapshots are serialized only for the selected final
solve and are compared offline for L2 and Linf differences. Solver residuals
and continuity errors are parsed from the unchanged OpenFOAM diagnostic log
and aligned by solve/outer identity.

## Decision gates

1. The first three common outer Force records for A and B must be trajectory
   equivalent for every aligned Fluid solve; otherwise the result is
   `INNER_AB_NOT_CONTROLLED`.
2. B1 and B2 final raw Force must be repeatable; otherwise the result is
   `INNER_CONVERGENCE_DIAGNOSTIC_NOT_REPEATABLE`.
3. For a controlled comparison,
   `delta_F_inner=||F_B(final)-F_A(outer=3)||` is reported for total,
   pressure, and viscous Force, with its ratio to `1e-3 N`.
4. `CURRENT_INNER_SOLVE_ADEQUATE_FOR_TESTED_STATE` is supported only when
   the sensitivity is well below `1e-3 N` and the B Force tail is still
   contracting. This is not a production recommendation or a convergence
   qualification.

## Stop conditions

After A, B, B1/B2 repeatability, and the report/evidence are complete, stop.
No solver repair, parameter sweep, IQN retest, relaxation tuning, additional
physical window, or multi-window run is authorized by this phase.
