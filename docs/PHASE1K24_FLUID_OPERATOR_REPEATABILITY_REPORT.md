# Phase 1K.24 — Fluid Operator Repeatability Report

> **Later evidence qualification (Phase 1K.26/K.27):** The S0/S1 object and
> history inventory below remains valid. The original same-process `F1`/`F2`
> samples were from attempts 1 and 2, which K26 later showed had different
> Fluid-read displacements. Their Force difference therefore does not establish
> same-input Fluid-operator non-repeatability or prove that the inventory
> mismatch caused that Force difference. The fresh-process result remains valid
> for its distinct one-step accepted branch. See
> [Phase 1K.27](PHASE1K27_DIRECT_FLUID_FORCE_REPEATABILITY_REPORT.md).

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

## 2. Same-process S0/S1 state observation and Force samples

The same-process run used one physical window, four attempts, and three
rollback requests. The harness held nominal Structure displacement `D*`, but
K26 later established that the first two Fluid reads differed. The first two
retry-endpoint Force values were:

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

This is a concrete, high-impact mismatch in the OpenFOAM solver/ALE state
boundary. It supports the statement that the observed registry/history topology
changed across the checkpoint boundary. Because the Fluid inputs to the first
two Force samples differed, this inventory does not establish that the state
mismatch caused their Force difference. It does not identify which newly
created histories or internal runtime caches affect a controlled identical-
input replay.

## 3. Fresh-process control replay

Two independent scratch cases were launched from independent copies of the same frozen 30.0 s restart, with independent preCICE socket directories and the same `D*`, adapter, RBF, OpenFOAM and preCICE identities. Both processes exited cleanly.

| replay | Force returned after the one-step accepted branch (N) |
|---|---:|
| fresh A | `(0.18807135840349185, 0.04700807470592938)` |
| fresh B | `(0.18807135840349185, 0.04700807470592938)` |

`||F_B-F_A|| = 0 N`, relative difference `0`. The fresh-process control is repeatable at the tested one-step accepted branch. It does not erase the same-process S0/S1 mismatch; it argues against a generic fresh-process nondeterminism explanation.

The fresh A/B branch used `max_iterations=1` and `min_iterations=1` solely to obtain a single independent process-level replay. Its Force sample is not substituted for the same-process retry-endpoint samples, because the read branch/offset is different.

## 4. Answers to the required questions

1. **Does the S0/S1 mismatch causally support the original `F1 != F2` Force difference?** **UNRESOLVED / NOT ESTABLISHED.** The inventory mismatch is observed, but K26 showed the paired Fluid-read displacement values differed; the Force comparison is not an identical-input causal test.

2. **Which states differ?** The observed differences are `U/k/omega/Uf` old-time allocation and hashes, new `U_0/k_0/omega_0/Uf_0` objects, new `meshPhi/meshPhi_0`, `yPlus`, `fvMesh moving/changing` flags, and volume-history proxies `V/V0/V00`. Current primary-field hashes, pointDisplacement, cellDisplacement, and mesh point coordinates were equal. Turbulence-object internals, function-object mutable state, RBF caches, and other fvMesh caches remain not directly hashable.

3. **Are fresh-process A/B replays repeatable?** **YES for the tested one-step accepted branch.** `F_A`, `F_B`, and the exact difference are reported above.

4. **Can the original Force difference be attributed to CFD inner convergence?** **NOT_YET_TESTABLE from K24.** K24 did not isolate a same-Fluid-input replay; its inner-convergence A/B remains unmeasured.

5. **Was CFD inner-convergence A/B allowed at the end of K24?** **NO.** K27 later authorizes it as the next diagnostic only, after matching Fluid inputs and repeatable raw Force/payload were observed on the tested G2 branch. It was not run in K24 or K27.

## 5. Final evidence status

- Same-process Fluid operator repeatability: **NOT ESTABLISHED**.
- Fresh-process replay repeatability: **PASS_DIAGNOSTIC_ONLY**.
- Rollback mismatch localization: **PASS_DIAGNOSTIC_ONLY**.
- CFD inner-convergence A/B: **NOT_MEASURED**.
- IQN/acceleration conclusions: remain unauthorized.
- Process cleanup: all successful diagnostic runs exited with Fluid and Structure code `0`; no orphan participant remained.

Evidence is preserved under `evidence/phase1k24_fluid_state_repeatability/run-20260925T074500Z-d3890de/`, including raw Fluid/Structure logs, S0/S1 snapshots, fresh-process A/B directories, runtime identities, and machine-readable comparisons.
