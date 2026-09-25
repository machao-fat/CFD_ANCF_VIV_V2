# Phase 1K.25 — Minimal Fluid Rollback-State Repair and Causal Qualification

> **Later evidence qualification (Phase 1K.26/K.27):** Candidate state and
> history-topology observations below remain preserved. The table's Force
> differences came from attempts without verified matching Fluid-read
> displacement, so the stated Group 1 causal contribution to same-input Force
> replay is not established. Do not interpret the original `F1`/`F2` values as
> a controlled same-Fluid-input comparison. See
> [Phase 1K.27](PHASE1K27_DIRECT_FLUID_FORCE_REPEATABILITY_REPORT.md).

Status: completed as an isolated diagnostic study. No production adapter, case,
mesh, RBF configuration, coupling configuration, or physical parameter was
modified.

## Final classification

Current evidence-qualified interpretation: `FORCE_REPEATABILITY_UNRESOLVED_AFTER_INPUT_ALIGNMENT_AUDIT`.

Historical K25 classification: `ROLLBACK_REPEATABILITY_NOT_RESTORED`.
K26/K27 later showed that K25's attempts 1/2 were not a same-Fluid-input pair,
so the Force evidence cannot establish either restored or unrestored
same-process operator repeatability. The fresh-process controls remain
deterministic for the tested one-step accepted branches and topologies.

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

## Candidate state and historical Force observations

The `F1`/`F2` entries below are preserved historical values. Fluid-read
displacement equality was not verified for these paired samples; the reported
Force deltas therefore cannot be used to infer causal effects of the state
group interventions on same-input Fluid Force repeatability.

| Candidate | Isolated state group | Recorded `F1` (N) | Recorded `F2` (N) | `||F2-F1||` (N) | Fresh A/B difference | Historical interpretation (causality unverified) |
|---|---|---:|---:|---:|---:|---|
| G1 | field old-time/history canonicalization | `(0.09266996754766044, 0.056130040689796094)` | `(0.14069864208624935, -0.008447088563692154)` | `0.08047955765631062` | `0` | old label: contributes; matching Fluid input unverified |
| G2 | `meshPhi`/ALE flux value canonicalization only | `(0.0900359042326746, 0.056385514259487284)` | `(0.1615021722747258, -0.021510905978815276)` | `0.1057131957411209` | `0` | old label: no dominant effect; force causality unverified |
| G3 | legal zero-motion `fvMesh` lifecycle canonicalization | `(0.0900359042326746, 0.056385514259487284)` | `(0.1615021722747258, -0.021510905978815276)` | `0.1057131957411209` | `0` | old label: not sufficient; force causality unverified |
| G5 | scratch-only removal of `forces/forceCoeffs/yPlus` function objects | `(0.0900359042326746, 0.056385514259487284)` | `(0.1615021722747258, -0.021510905978815276)` | `0.1057131957411209` | `0` | old label: no dominant effect; force causality unverified |

The G1 history topology was equalized at the checkpoint/retry comparison. Its
recorded Force-sample difference was `80.47955765631062` times the coupling
limit, but without matching Fluid-read displacement this is not evidence of a
causal Force contribution or of failed same-input repeatability.

For G1 the next recorded same-process Force was
`F3=(0.10290444955509812,-0.04243815561050917) N`; the read displacement for
this sample was not shown to form a same-input replay with `F1`/`F2`, so these
samples do not establish a repeatability-gate result.

## State observations

The baseline K24 mismatch remains observable in the current adapter path:

- current field values and geometry restore;
- field-history objects are lazily materialized by the solver lifecycle;
- ALE/fvMesh lifecycle objects are not restored to the original fresh topology;
- `yPlus` and other ancillary registry objects can appear after the first solve;
- RBF and other runtime object state is not serialized by the adapter.

G1 materialized `U`, `k`, `omega`, and `Uf` old-time levels before the initial
checkpoint. At S0/S1 those targeted history objects matched, but `meshPhi` and
`yPlus` still appeared in the post-rollback registry. The recorded Force
samples differed, but their same-input repeatability was not established.

G2 zeroed the available `meshPhi` current/old-time values after rollback. It
did not remove the topology or restore the `fvMesh` lifecycle, and it produced
the K24 recorded Force sequence exactly. K27 later established a valid G2
same-input attempt pair with equal raw Force and adapter payload; the K25
Structure-read difference was not itself a same-offset comparison.

G3 entered the legal OpenFOAM moving-mesh lifecycle with zero displacement
before the first checkpoint. Its initial diagnostic attempt was blocked by a
snapshot assumption that `V0/V00` always exist; that diagnostic-only snapshot
was made presence-safe and the candidate was rerun. The corrected G3 run
completed cleanly, but produced the same recorded Force sequence as K24. This
does not determine its effect on same-input raw Force and is not a production
fix; it does not justify private-flag manipulation or direct `V0/V00`
fabrication.

G5 removed the three scratch-only ancillary function objects that appear in the
K24 case (`cylinderForces`, `cylinderForceCoeffs`, and `yPlus`). The same-process
recorded Force-sample difference remained `0.1057131957411209 N`, while
fresh-process A/B remained identical. The input mismatch means this does not
support or refute ancillary function-object state as a cause of identical-input
Force variation.

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

1. Which group has causal support for Force repeatability? **UNRESOLVED**;
   Group 1 topology was canonicalized, but its Force comparison did not verify
   equal Fluid inputs. G2/G3/G5 Force-causal effects are also unresolved.
2. Minimal sufficient repair for same-input replay? **NOT ESTABLISHED**.
3. Same-process repeatability after candidate changes? **NOT MEASURED with a
   verified identical Fluid input**; the quoted deltas are not a valid gate.
4. Fresh-process determinism? **YES for the tested candidate topologies and
   their recorded branch**.
5. At the end of K25, CFD inner-convergence A/B was **not authorized**. K27
   later authorizes it as the next diagnostic only; it has not been run.
6. IQN re-test allowed? **NO**. Acceleration qualification remains closed.

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
