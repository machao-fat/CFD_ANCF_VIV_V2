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
| Phase 1K.23 single-window convergence mechanism | NOT CONVERGED / replay inference superseded | One window, 40-attempt diagnostic: 39 rollbacks and acceptance at the diagnostic limit, not convergence. The originally compared Force samples differed by `0.1057131957411209 N`, but K26 established that attempts 1/2 did not deliver the same displacement to Fluid; that Force difference is not valid same-input operator-repeatability evidence. Inner-convergence A/B and the constant-relaxation baseline were not measured. |
| Phase 1K.24 Fluid rollback-state audit | FLUID_ROLLBACK_STATE_MISMATCH_LOCALIZED (state inventory only) | The observed S0/S1 current-field, old-time/objectRegistry, ALE, `moving/changing`, and volume-history differences remain valid. However, its attempts 1/2 Force comparison was not a same-Fluid-input replay, so it does not establish that the inventory mismatch caused Fluid Force non-repeatability. Fresh-process A/B (`||FB-FA||=0 N`) remains valid for its one-step accepted branch. |
| Phase 1K.25 minimal rollback candidates | FORCE_REPEATABILITY_UNRESOLVED_AFTER_INPUT_ALIGNMENT_AUDIT (historical classification: `ROLLBACK_REPEATABILITY_NOT_RESTORED`) | Group 1 history topology was canonicalized and candidate state snapshots remain valid, but its claimed causal reduction of same-input Force difference is superseded: the Force samples were not based on matching Fluid-read displacement. Isolated G2/G3/G5 observations remain descriptive; they did not establish a force-causal effect. K26/K27 later show G2 same-input attempts 3/4 with identical stages/raw Force/payload, while the Structure read comparison has different offsets. |
| Phase 1K.27 direct Force/payload decomposition | PRECICE_DOWNSTREAM_STATE_EXPLAINS_RECEIVED_FORCE_DIFFERENCE | On the tested K26 G2 branch, attempts 3/4 have identical Fluid-read displacement (400-value hash `d32bccc...b1fb339`), all 15 S01–S11 stages equal, identical raw per-face pressure/viscous/total Force and identical adapter preWrite buffer (hash `093a44...2cf3fc6`). Raw Force difference and payload difference are both `0`; Structure Force differs by `0.01869480300014619 N`, but reads use different offsets (`dt` retry vs `0` accepted boundary). Thus tested-branch raw/operator repeatability is supported and divergence is downstream of adapter write; exact mapping/acceleration/read-sampling sub-cause remains unresolved. CFD inner-convergence A/B is authorized as a next diagnostic only, not performed; IQN retest remains unauthorized. |
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
