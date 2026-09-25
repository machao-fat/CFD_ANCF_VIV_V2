# Validation ledger

Permanent claims require a report/result, a source lineage, and a reproducible test
or artifact. A historical PASS does not authorize a production FSI run by itself.

| area | status | evidence / interpretation |
|---|---|---|
| ANCF static | PASS | baseline credibility and MATLAB/C++ evidence |
| ANCF modal | PASS | six-frequency comparison, MAC=1 |
| ANCF free vibration | PASS | 50 s NRMSE about 3.44e-12, phase drift about 1.37e-12 |
| MATLAB/C++ cross-validation | PASS | `evidence/ancf_validation/ANCF_MATLAB_CPP_CROSS_VALIDATION_V1.md` |
| SHM1 M1--M4 capability | PASS | authoritative commit `355640e1...` and archived worker reports |
| worker lifecycle | PASS | M3/M4 evidence |
| cold restart | PASS | M4 evidence |
| physical checkpoint rollback | PASS | q/qdot/qddot recovery evidence; nonzero point-displacement restoration is separately qualified only for the experimental adapter in K20--K22 |
| transport ID monotonicity | PASS_OFFLINE_WORKER_PARITY_REPAIR | authoritative-source CMake worker: 2 windows x 5 requests, sequence 1--10; duplicate request/transaction guards and physical-only rollback pass; no HH06 runtime deployment claim |
| force unit chain | PASS | `HH06_SINGLE_SLICE_FORCE_UNIT_CHAIN_AUDIT` |
| physical release Force F0 | RESOLVED | exact 30.0 s restart Force is hash-bound in `contract.json`; pre-initialize Fluid initial-data path qualified for the exact SHA-pinned adapter only |
| absolute displacement semantics | PASS | no double accumulation in audit |
| nonzero ALE one-window isolation | PASS_ISOLATED_ONLY | diagnostic-only isolated adapter path; this does not qualify the production adapter |
| preCICE one-window handshake | PASS | historical qualification report |
| historical implicit multi-iteration qualification | NOT PASS | old 5-iteration trace had zero displacement residual; confirmed cause in the old participant path was stale committed motion |
| offline implicit feedback lifecycle | PASS_OFFLINE_STRATEGY_C | deterministic `F=1+2D`, `D_trial=0.1+0.2F` converges by tolerances; physical rollback, F0 units, worker transport, and cap honesty regressions pass |
| bounded coupling launch contract | PASS_BOUNDED_QUALIFICATION_READINESS | exact 2-window/20-iteration launcher preflight and isolated Python/preCICE runtime ABI qualification pass; no HH06 participant or solver was started |
| real preCICE implicit qualification | PASS_BOUNDED_REAL | Phase 1E-R two-window and Phase 1F five-window Strategy C lifecycle passed with the qualified historical adapter; convergence efficiency and long-run stability remain separate claims |
| worker transition parity | PASS_OFFLINE_ONLY | current authoritative source and clean build pass the 2-window x 5-request sequence-6 regression; not deployed/runtime-qualified in the HH06 slice |
| HH06 25-window old-mesh bounded FSI | FAIL_ALE_OR_FLUID_RUNTIME | Phase 1I: old mesh plus Laplacian ALE failed in the historical late-window region |
| HH06 25-window new-mesh RBF FSI | REVIEW_REQUIRED | Phase 1K.11 completed 25 windows without a solver crash, but accepted mesh points remained at release coordinates while rejected-trial force/pressure spikes and the displacement-to-mesh path remained unresolved |
| K20 experimental point-displacement checkpoint | PASS_EXPERIMENTAL_NONZERO_POINT_CHECKPOINT_ONE_RETRY | exact nonzero S0-to-S1 restoration for one retry with `libpreciceAdapterPhase1K20.so` |
| K21 experimental adapter lifecycle | PASS_EXPERIMENTAL_TWO_WINDOW_LIFECYCLE | two complete windows with nonzero rollback checks; both accepted at the 20-iteration limit |
| K22 experimental adapter lifecycle | PASS_EXPERIMENTAL_FIVE_WINDOW_LIFECYCLE | five complete windows with rollback/read-handoff checks; all five accepted at the 20-iteration limit and were not converged within the cap |
| experimental adapter source/build | QUALIFIED_ISOLATED | source snapshot and SHA-pinned experimental binary are preserved under `third_party/`; the historically qualified adapter source lineage remains unresolved |
| HH06 production 50-window / 0.2 s | NOT DONE / NOT AUTHORIZED | no claim made |
| 3-slice FSI in this baseline | NOT DONE | planned only |
| slice convergence | NOT DONE | planned only |
| full HH06 quantitative reproduction | NOT DONE | single slice is only a coupling qualification |

## Phase 1K qualification levels

| Level | Meaning |
|---|---|
| `REVIEW_REQUIRED` | The bounded run produced useful evidence, but a required runtime path or physical interpretation remains unresolved. |
| `PASS_EXPERIMENTAL_*` | A separately identified experimental implementation passed the named bounded lifecycle. The result does not transfer qualification to the production adapter. |
| `PASS_BOUNDED_REAL` | The real single-slice coupling lifecycle passed the named bounded run. It does not imply convergence efficiency, long-run stability, or HH06 validation. |
| `QUALIFIED` | Reserved for a source-traceable implementation with the required regression and runtime evidence; K20--K22 do not meet this level for production use. |

## Numerical facts from the failed bounded run

The 25-window run accepted 25 windows and executed 25 real rollbacks, but reached
approximately `Co_max=184.662`, `meshCo_max=58.752`, `meshVelocity_max=18.117 m/s`,
`max|U|=392.274 m/s`, `omega_max=925093`, and `max applied strip force=149994.84 N`.
Geometry remained positive before the bounded stop, but the run is not numerically
healthy and is not a physical benchmark result.
