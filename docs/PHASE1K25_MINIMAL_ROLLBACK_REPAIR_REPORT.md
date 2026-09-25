# Phase 1K.25 — Minimal Fluid Rollback-State Repair and Causal Qualification

Status: completed as an isolated diagnostic study. No production adapter, case,
mesh, RBF configuration, coupling configuration, or physical parameter was
modified.

## Final classification

`ROLLBACK_REPEATABILITY_NOT_RESTORED`

The tested candidates did not restore same-process Fluid replay repeatability.
The fresh-process controls remained deterministic for every tested topology.
Consequently CFD inner-convergence A/B and IQN requalification remain closed.

## Frozen baseline

- branch: `diagnostic/phase1k25-minimal-rollback-repair-v1`
- HEAD: `d3890deb0e609cc7e38e3f38ff6203787f889c07`
- restart: frozen new-mesh state at global time `30.0 s`
- displacement: `D* = (1.0633832164606064e-07, 9.530777190012017e-08) m`
- Force absolute coupling limit: `1e-3 N`
- worker SHA256: `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`
- diagnostic RBF SHA256: `508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11`

The qualified historical adapter was not used. Every candidate used a
separately identified experimental adapter.

## Causal candidate results

| Candidate | Isolated state group | Same-process `F1` (N) | Same-process `F2` (N) | `||F2-F1||` (N) | Fresh A/B difference | Result |
|---|---|---:|---:|---:|---:|---|
| G1 | field old-time/history canonicalization | `(0.09266996754766044, 0.056130040689796094)` | `(0.14069864208624935, -0.008447088563692154)` | `0.08047955765631062` | `0` | contributes, insufficient |
| G2 | `meshPhi`/ALE flux value canonicalization only | `(0.0900359042326746, 0.056385514259487284)` | `(0.1615021722747258, -0.021510905978815276)` | `0.1057131957411209` | `0` | no measurable dominant effect |
| G3 | legal zero-motion `fvMesh` lifecycle canonicalization | `(0.0900359042326746, 0.056385514259487284)` | `(0.1615021722747258, -0.021510905978815276)` | `0.1057131957411209` | `0` | not sufficient |
| G5 | scratch-only removal of `forces/forceCoeffs/yPlus` function objects | `(0.0900359042326746, 0.056385514259487284)` | `(0.1615021722747258, -0.021510905978815276)` | `0.1057131957411209` | `0` | no measurable dominant effect |

The G1 result is `80.47955765631062` times the coupling limit. Its history
topology was equalized at the checkpoint/retry comparison, but the replay
difference remained far above tolerance. This is causal contribution evidence,
not a sufficient repair.

For G1 the next recorded same-process Force was
`F3=(0.10290444955509812,-0.04243815561050917) N`; because `F2-F1` already
failed the repeatability gate, no candidate was eligible for an acceptance
decision based on a third replay.

## State observations

The baseline K24 mismatch remains observable in the current adapter path:

- current field values and geometry restore;
- field-history objects are lazily materialized by the solver lifecycle;
- ALE/fvMesh lifecycle objects are not restored to the original fresh topology;
- `yPlus` and other ancillary registry objects can appear after the first solve;
- RBF and other runtime object state is not serialized by the adapter.

G1 materialized `U`, `k`, `omega`, and `Uf` old-time levels before the initial
checkpoint. At S0/S1 those targeted history objects matched, but `meshPhi` and
`yPlus` still appeared in the post-rollback registry and the Force replay was
not repeatable.

G2 zeroed the available `meshPhi` current/old-time values after rollback. It
did not remove the topology or restore the `fvMesh` lifecycle, and it produced
the K24 baseline Force sequence exactly.

G3 entered the legal OpenFOAM moving-mesh lifecycle with zero displacement
before the first checkpoint. Its initial diagnostic attempt was blocked by a
snapshot assumption that `V0/V00` always exist; that diagnostic-only snapshot
was made presence-safe and the candidate was rerun. The corrected G3 run
completed cleanly, but produced the same Force sequence as K24. This is not a
production fix and does not justify private-flag manipulation or direct
`V0/V00` fabrication.

G5 removed the three scratch-only ancillary function objects that appear in the
K24 case (`cylinderForces`, `cylinderForceCoeffs`, and `yPlus`). The same-process
Force difference remained exactly `0.1057131957411209 N`, while fresh-process A/B
remained identical. This does not support ancillary function-object state as the
dominant cause.

Group 4 turbulence-model internals and Group 6 RBF/motion-solver caches were not
assigned an unverified runtime mutation. They are not currently exposed through
a safe adapter checkpoint API and remain `NOT_MEASURED`, not implicitly
exonerated.

## Fresh-process controls

Each tested candidate had an independent fresh A/B control from the same frozen
restart and the same `D*`:

- G1: `FA=FB=(0.201241674978421,0.045730706857473415) N`, difference `0 N`;
- G2: `FA=FB=(0.18807135840349185,0.04700807470592938) N`, difference `0 N`;
- G3: `FA=FB=(0.18807135840349185,0.04700807470592938) N`, difference `0 N`.

These values are candidate-topology controls and must not be compared directly
with the original K24 fresh-process value as though they were the same runtime
branch.

## Required decisions

1. Which group has causal support? **Group 1 has causal contribution support**;
   Groups 2 and 3 were not sufficient and showed no measurable dominant effect
   in their isolated candidates.
2. Minimal sufficient repair found? **NO**.
3. Repaired same-process replay? **Not restored**; the smallest observed G1
   difference is `0.08047955765631062 N`.
4. Fresh-process determinism? **YES for the tested candidate topologies**.
5. CFD inner-convergence A/B allowed? **NO**. Same-process Fluid operator
   repeatability is still not established.
6. IQN re-test allowed? **NO**. This phase does not authorize acceleration
   qualification.

## Evidence

The complete machine-readable evidence is under:

`evidence/phase1k25_minimal_rollback_repair/`

The candidate summaries are in:

- `run-20260925T080000Z-d3890de-G1/candidate-G1/`
- `run-20260925T080000Z-d3890de-G2/candidate-G2/`
- `run-20260925T080000Z-d3890de-G3/candidate-G3/`

The aggregate files are `qualification_summary.json` and
`force_comparison.json`. The original K24 evidence remains unchanged.

No 5-window, 25-window, second physical-window, IQN, relaxation, PIMPLE,
inner-convergence, or production-adapter experiment was run in Phase 1K.25.
