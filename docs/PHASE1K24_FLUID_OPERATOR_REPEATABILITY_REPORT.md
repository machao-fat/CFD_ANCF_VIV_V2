# Phase 1K.24 — Fluid Operator Repeatability Report

Primary classification: **`FLUID_ROLLBACK_STATE_MISMATCH_LOCALIZED`**

This is a diagnostic-only result. No IQN, relaxation, timestep, turbulence, mesh, RBF, ANCF, or production configuration change was made. No second physical window, 5-window run, 25-window run, or repair experiment was performed.

## 1. Test identity

- Branch: `diagnostic/phase1k24-fluid-state-replay-v1`
- HEAD: `d3890deb0e609cc7e38e3f38ff6203787f889c07`
- Frozen restart: exact new-mesh state at global time `30.0 s`
- `D* = (1.0633832164606064e-07, 9.530777190012017e-08) m`
- OpenFOAM: Foundation 10, build `10-c4cf895ad8fa`
- preCICE runtime: `3.4.1`
- Python: `/usr/bin/python3.10`; pyprecice metadata `3.4.0`
- Worker binary SHA256: `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`
- RBF diagnostic library SHA256: `508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11`
- Experimental diagnostic adapter SHA256: `3d75ae9fcebba444d8e21fa228fddc394e8748959d3b8ae340732fd21b3abd25`
- Experimental adapter Build ID: `91e011c76e613a1a6b272f522afc4cf5b9cfccc7`
- Qualified historical adapter: not used

## 2. Same-process S0/S1 replay

The same-process run used one physical window, four attempts, three rollback requests, and the exact fixed displacement `D*`. The first two retry-endpoint Force values were:

| sample | Force input/endpoint (N) |
|---|---:|
| `F1` | `(0.0900359042326746, 0.056385514259487284)` |
| `F2` | `(0.1615021722747258, -0.021510905978815276)` |

`||F2-F1|| = 0.1057131957411209 N`, relative difference `0.9950919530038619`, versus the `1e-3 N` coupling force limit.

The S0/S1 comparison was performed before the second Fluid solve:

- current hashes of `U`, `p`, `phi`, `k`, `omega`, `nut`, `Uf`, `pointDisplacement`, and `cellDisplacement` were equal in the captured snapshot;
- mesh point hash was equal (`4d777bcb263e9eff`);
- `pointDisplacement`, `cellDisplacement`, and mesh point coordinates therefore did not explain the difference at this observation point;
- `U`, `k`, `omega`, and `Uf` acquired old-time/old-old-time layers at S1 that were absent at S0;
- S1 contained newly registered/created `U_0`, `k_0`, `omega_0`, `Uf_0`, `meshPhi`, `meshPhi_0`, and `yPlus` objects;
- `fvMesh` state changed from `moving=false, changing=false` at S0 to `moving=true, changing=true` at S1, while the point coordinates remained equal;
- `V/V0/V00` were unavailable at S0 because the mesh was not yet marked moving and were hashable proxies at S1.

This is a concrete, high-impact mismatch in the OpenFOAM solver/ALE state boundary. It supports the statement that the same-process replay did not restart from an identical Fluid state. It does not yet identify which of the newly created histories or internal runtime caches is sufficient by itself to explain the full Force difference.

## 3. Fresh-process control replay

Two independent scratch cases were launched from independent copies of the same frozen 30.0 s restart, with independent preCICE socket directories and the same `D*`, adapter, RBF, OpenFOAM and preCICE identities. Both processes exited cleanly.

| replay | Force returned after the one-step accepted branch (N) |
|---|---:|
| fresh A | `(0.18807135840349185, 0.04700807470592938)` |
| fresh B | `(0.18807135840349185, 0.04700807470592938)` |

`||F_B-F_A|| = 0 N`, relative difference `0`. The fresh-process control is repeatable at the tested one-step accepted branch. It does not erase the same-process S0/S1 mismatch; it argues against a generic fresh-process nondeterminism explanation.

The fresh A/B branch used `max_iterations=1` and `min_iterations=1` solely to obtain a single independent process-level replay. Its Force sample is not substituted for the same-process retry-endpoint samples, because the read branch/offset is different.

## 4. Answers to the required questions

1. **Is `F1 != F2` supported by a same-process rollback state mismatch?** **SUPPORTED.** The S0/S1 snapshot shows field-history/objectRegistry/ALE lifecycle differences before the second solve.

2. **Which states differ?** The observed differences are `U/k/omega/Uf` old-time allocation and hashes, new `U_0/k_0/omega_0/Uf_0` objects, new `meshPhi/meshPhi_0`, `yPlus`, `fvMesh moving/changing` flags, and volume-history proxies `V/V0/V00`. Current primary-field hashes, pointDisplacement, cellDisplacement, and mesh point coordinates were equal. Turbulence-object internals, function-object mutable state, RBF caches, and other fvMesh caches remain not directly hashable.

3. **Are fresh-process A/B replays repeatable?** **YES for the tested one-step accepted branch.** `F_A`, `F_B`, and the exact difference are reported above.

4. **Can the current failure still be attributed to CFD inner convergence?** **NOT_YET_TESTABLE.** The rollback-state equality gate fails first. The Phase 1K.23 inner-convergence A/B remains unmeasured and must not be reopened yet.

5. **Is the next phase allowed to begin CFD inner-convergence A/B?** **NO.** The next gate is to localize and minimally repair/validate the proven Fluid rollback-state mismatch, one state group at a time. No repair was attempted in Phase 1K.24.

## 5. Final evidence status

- Same-process Fluid operator repeatability: **NOT ESTABLISHED**.
- Fresh-process replay repeatability: **PASS_DIAGNOSTIC_ONLY**.
- Rollback mismatch localization: **PASS_DIAGNOSTIC_ONLY**.
- CFD inner-convergence A/B: **NOT_MEASURED**.
- IQN/acceleration conclusions: remain unauthorized.
- Process cleanup: all successful diagnostic runs exited with Fluid and Structure code `0`; no orphan participant remained.

Evidence is preserved under `evidence/phase1k24_fluid_state_repeatability/run-20260925T074500Z-d3890de/`, including raw Fluid/Structure logs, S0/S1 snapshots, fresh-process A/B directories, runtime identities, and machine-readable comparisons.
