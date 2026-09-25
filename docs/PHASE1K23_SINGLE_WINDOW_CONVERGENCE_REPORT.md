# Phase 1K.23 — Single-Window Implicit Convergence Mechanism Diagnostic

## Result

Primary classification: `FLUID_OPERATOR_NOT_REPEATABLE_OR_INNER_UNCONVERGED`

Gate qualifier: `FLUID_OPERATOR_REPEATABILITY_NOT_ESTABLISHED`

This is a diagnostic result, not a convergence pass. One physical coupling
window was run from the frozen 30.0 s new-mesh restart. No second window, 5-
window run, 25-window run, parameter sweep, or production configuration change
was performed.

## Frozen identity

| Item | Value |
|---|---|
| Branch | `diagnostic/phase1k23-single-window-convergence-v1` |
| HEAD | `d3890deb0e609cc7e38e3f38ff6203787f889c07` |
| Restart | 30.0 s new-mesh K22 restart, scratch copy only |
| OpenFOAM | Foundation OpenFOAM 10 |
| preCICE runtime | 3.4.1 |
| Python | `/usr/bin/python3.10`; pyprecice metadata 3.4.0 |
| Experimental adapter | `libpreciceAdapterPhase1K20.so`, SHA256 `225ecab227b8271f01119fe476370e3a0b705ca06e1ca3a7739200266499b165` |
| Diagnostic RBF | `libRBFMeshMotionSolverPhase1K187BStopDiag.so`, SHA256 `508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11` |
| Worker source | `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e` |
| Worker binary | `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596` |

Full runtime and restart identities are preserved in [runtime_identity.json](../evidence/phase1k23_single_window_convergence/run-20260925T055605Z-d3890de-e/runtime_identity.json).

## Single-window extended diagnostic

The diagnostic ceiling was 40 iterations. The window executed 40 attempts,
with 39 rollbacks and one acceptance at the iteration limit. preCICE reported
`Convergence 0`; the result is therefore `ACCEPTED_AT_ITERATION_LIMIT`, not
`CONVERGED`.

| Quantity | Result |
|---|---:|
| Physical windows | 1 |
| Attempts | 40 |
| Rollbacks | 39 |
| ANCF Newton iterations/attempt | 3 |
| ANCF nonlinear residual | `7.826941494926132e-08` |
| First raw Force residual | `0.02462073141564219 N` |
| Maximum raw Force residual | `12.667404453953939 N` |
| Final returned raw Force residual | `24.09700299734948 N` |
| Final trial displacement residual | `2.0556864839679076e-05 m` |
| `D_written == D_trial` | PASS for all 40 attempts |
| Transport sequence | 1--40, monotonic |

The force residual history is not a stable decreasing contraction: its ratio
range was approximately `0.2024` to `3.9433`, with median ratio about `1.3865`.
The trial displacement residual likewise increased to the final value. This
observation alone does not distinguish an intrinsically noncontractive map from
a non-repeatable Fluid operator, because the repeatability gate below failed.

Representative Force/trial pairs from the trace:

| k | Force input `(Fx,Fy)` N | returned Force `(Fx,Fy)` N | `D_trial` `(Dx,Dy)` m |
|---:|---|---|---|
| 1 | `(0.06552704, 0.05872987)` | `(0.09003590, 0.05638551)` | `(1.0634e-7, 9.5308e-8)` |
| 2 | `(0.09003590, 0.05638551)` | `(0.17083377, 0.00255426)` | `(1.4611e-7, 9.1503e-8)` |
| 3 | `(0.17083377, 0.00255426)` | `(0.10712246,-0.00311548)` | `(2.7723e-7,4.1451e-9)` |
| 40 | `(-3.07747226,-5.99688964)` | `(-27.04526286,-3.50478867)` | `(-4.9942e-6,-9.7318e-6)` |

The trace retains separate Force input, returned Force, read offset, trial and
written displacement. Direct per-attempt OpenFOAM `forces` output was
`NOT_MEASURED`; the available `forces.dat` output contains the restart-time
record only and was not substituted for attempt-level data.

## Same-input Fluid repeatability gate

The fixed displacement was taken from the real window-1 trace:

`D* = (1.0633832164606064e-07, 9.530777190012017e-08) m`.

The controlled replay used the same 30.0 s scratch restart, the same
experimental adapter/RBF identities, and the same displacement. The measured
Force difference was:

```text
F1 = ( 0.0900359042326746,  0.056385514259487284) N
F2 = ( 0.1615021722747258, -0.021510905978815276) N
||F2-F1|| = 0.1057131957411209 N
relative difference = 0.9950919530038619
absolute coupling-force limit = 0.001 N
ratio to limit = 105.7131957411209
```

The result is `NOT_PASS`: `FLUID_OPERATOR_REPEATABILITY_NOT_ESTABLISHED`.
The S0-to-S1 checks did pass for point-displacement internal and boundary
fields, cell-displacement internal and boundary fields, mesh points, and the
available ANCF checkpoint state. Thus this evidence does not indicate a
checkpoint restore mismatch as the cause. It also does not yet separate CFD
inner-solve error from another Fluid state/operation that is not restored by
the replay; that distinction remains open.

Machine-readable result: [repeatability_test.json](../evidence/phase1k23_single_window_convergence/repeatability-20260925T060549Z-d3890de-b/repeatability_test.json).

## Gated-off tests

The failed repeatability gate required stopping here:

| Test | Status | Reason |
|---|---|---|
| CFD inner-convergence A/B | `NOT_MEASURED` | Not authorized after repeatability failure |
| Repaired-adapter constant-relaxation 0.2 baseline | `NOT_MEASURED` | Not authorized after repeatability failure |
| Further IQN tuning | NOT RUN | Explicitly forbidden by the phase gate |
| Direct per-attempt OpenFOAM force reconciliation | `NOT_MEASURED` | No attempt-level direct force output in this run |

The artifacts explicitly preserve these statuses in
`inner_convergence_ab.json` and `constant_relaxation_trace.jsonl`.

## Answers to the five required questions

1. A stable fixed point is **UNRESOLVED**. The run did not converge, and the
   same-input Fluid operator repeatability gate failed.
2. The current 20-iteration behavior is best recorded as
   **NOISY_FLUID_OPERATOR** pending the inner-convergence isolation test. The
   observed residual ratios are not sufficient to call it a clean slow
   contraction or a purely noncontractive fixed point.
3. Same `S0 + D*` did **not** produce sufficiently consistent Force in the
   measured replay: `0.1057131957411209 N`, relative `0.9950919530038619`, over
   100 times the `1e-3 N` limit.
4. CFD inner-convergence error versus a stricter diagnostic setting is
   **NOT_MEASURED** because the repeatability gate stopped the phase.
5. The evidence-supported next action is **B: improve/diagnose Fluid inner
   convergence and operator repeatability**. Acceleration tuning is not
   justified yet; checkpoint/state determinism is supported by the exact S0-S1
   checks.

The K22 IQN column/drop counts are preserved as evidence but are **not
interpreted** here. This phase did not perform the required preCICE 3.4.1
source/documentation analysis needed to distinguish max-history behavior,
filter/rank effects, and residual/Jacobian quality.

## Evidence and scope statement

Primary run: [run-20260925T055605Z-d3890de-e](../evidence/phase1k23_single_window_convergence/run-20260925T055605Z-d3890de-e/).

Repeatability run: [repeatability-20260925T060549Z-d3890de-b](../evidence/phase1k23_single_window_convergence/repeatability-20260925T060549Z-d3890de-b/).

Earlier harness-blocked attempts are retained in the same evidence root and
were not overwritten. Production source/configuration, `main`, the qualified
historical adapter, ANCF physics, mesh, RBF settings, and runtime tolerances
were not modified by this phase.
