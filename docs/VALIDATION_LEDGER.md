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
| physical checkpoint rollback | PASS | q/qdot/qddot recovery evidence |
| transport ID monotonicity | PASS_OFFLINE_WORKER_PARITY_REPAIR | authoritative-source CMake worker: 2 windows x 5 requests, sequence 1--10; duplicate request/transaction guards and physical-only rollback pass; no HH06 runtime deployment claim |
| force unit chain | PASS | `HH06_SINGLE_SLICE_FORCE_UNIT_CHAIN_AUDIT` |
| physical release Force F0 | RESOLVED | exact 30.0 s restart Force is hash-bound in `contract.json`; pre-initialize Fluid initial-data path qualified for the exact SHA-pinned adapter only |
| absolute displacement semantics | PASS | no double accumulation in audit |
| nonzero ALE one-window isolation | PASS | diagnostic-only isolated adapter path |
| preCICE one-window handshake | PASS | historical qualification report |
| historical implicit multi-iteration qualification | NOT PASS | old 5-iteration trace had zero displacement residual; confirmed cause in the old participant path was stale committed motion |
| offline implicit feedback lifecycle | PASS_OFFLINE_STRATEGY_C | deterministic `F=1+2D`, `D_trial=0.1+0.2F` converges by tolerances; physical rollback, F0 units, worker transport, and cap honesty regressions pass |
| bounded coupling launch contract | PASS_BOUNDED_QUALIFICATION_READINESS | exact 2-window/20-iteration launcher preflight and isolated Python/preCICE runtime ABI qualification pass; no HH06 participant or solver was started |
| real preCICE implicit qualification | NOT RUN | no real preCICE/OpenFOAM runtime was authorized in Phase 1D |
| worker transition parity | PASS_OFFLINE_ONLY | current authoritative source and clean build pass the 2-window x 5-request sequence-6 regression; not deployed/runtime-qualified in the HH06 slice |
| HH06 25-window bounded FSI | NOT PASS | late ALE/flow/turbulence runaway |
| HH06 production 50-window / 0.2 s | NOT DONE / NOT AUTHORIZED | no claim made |
| 3-slice FSI in this baseline | NOT DONE | planned only |
| slice convergence | NOT DONE | planned only |
| full HH06 quantitative reproduction | NOT DONE | single slice is only a coupling qualification |

## Numerical facts from the failed bounded run

The 25-window run accepted 25 windows and executed 25 real rollbacks, but reached
approximately `Co_max=184.662`, `meshCo_max=58.752`, `meshVelocity_max=18.117 m/s`,
`max|U|=392.274 m/s`, `omega_max=925093`, and `max applied strip force=149994.84 N`.
Geometry remained positive before the bounded stop, but the run is not numerically
healthy and is not a physical benchmark result.
