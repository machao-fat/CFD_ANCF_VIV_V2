# Known issues and forbidden shortcuts

## HIGH PRIORITY — production RBF/adapter path remains open

Phase 1B source tracing and a deterministic fake backend confirmed the participant's
old retry behavior: after rollback it restored ANCF physical state and wrote the
previous `committed_motion`, discarding the just-computed trial interface
displacement. This explains the identically zero displacement residual in that
historical participant path (`STALE_COMMITTED_MOTION`).

Phase 1D implemented the participant-side fixed-point lifecycle. Phase 1E-R and
Phase 1F then exercised the repaired Structure/Fluid lifecycle in real bounded
runs with the qualified historical adapter. Phase 1I showed that the old mesh plus
Laplacian ALE still fails in the historical late-window region.

Phase 1K.11 completed 25 windows with the new RBF mesh and no solver crash, but its
accepted mesh points remained at the release coordinates while rejected-trial
pressure and force spikes grew. The displacement-to-mesh path therefore remains a
`REVIEW_REQUIRED` item. The result does not establish that the historical runaway
has been removed.

K20--K22 qualified a separately identified experimental adapter for one retry, two
windows, and five windows. K22 reached the 20-iteration cap in all five windows;
the lifecycle evidence is useful, while convergence efficiency and production
adapter adoption remain unresolved.

Phase 1K.23 then isolated one physical window with a diagnostic ceiling of 40
iterations. It reached 40 attempts with 39 rollbacks and was accepted at the
iteration limit, not converged. The repaired checkpoint path restored point and
cell displacement, mesh points, and the available ANCF state exactly from S0 to
S1. Its original replay Force samples differed by
`0.1057131957411209 N`, but Phase 1K.26 later established that attempts 1 and 2
did not deliver the same displacement to Fluid. Therefore that difference is
not valid same-input Fluid-operator evidence, and K23's repeatability
interpretation is superseded. The 40-attempt non-converged-at-cap result remains
valid. The inner-convergence A/B and repaired-adapter constant-relaxation
baseline were not run. Do not tune IQN until the gated diagnostics are complete.

Phase 1K.24 then instrumented the Fluid state at the checkpoint boundary. The
same-process replay showed that current hashes for `U`, `p`, `phi`, `k`,
`omega`, `nut`, `Uf`, `pointDisplacement`, and `cellDisplacement`, as well as
mesh point coordinates, matched at the captured S0/S1 boundary. However,
`U/k/omega/Uf` old-time layers and related `_0` objects were created after the
first advance, `meshPhi` appeared, `fvMesh` changed from `moving=false,
changing=false` to `moving=true, changing=true`, and volume-history proxies
`V/V0/V00` were only available after motion. The mismatch is therefore
localized to OpenFOAM solver-history/objectRegistry/ALE lifecycle state, while
turbulence-object, function-object, RBF-cache, and other internal `fvMesh`
state remain not directly hashable.

The corresponding S0/S1 inventory mismatch remains a valid observation. The
original same-process Force samples differed by `0.1057131957411209 N`, but
K26 showed that attempts 1 and 2 had different Fluid-read displacement; this
does not establish a same-input replay mismatch or prove the state inventory
caused the Force difference. Two independent fresh-process replays from the
same frozen 30.0 s restart and nominal `D*` returned exactly the same Force
(`||FB-FA|| = 0 N`) on their one-step accepted branch; that control remains
valid for that branch.

## Worker lineage parity repair — source and offline qualified

The authoritative V2 worker source no longer uses sequence parity to classify
same-window retries versus next-window requests. Commit `0383920` classifies
physical identity using `(global_step, bridge_step, integer_tick, time_s,
dt_s)` and preserves independent monotonic transport identities. The current
source-built worker passed the bounded offline 2-window x 5-request test,
including acceptance of sequence 6 as the next physical window and physical
rollback without transport-ID rollback.

The repair is source-traceable and offline-qualified. The bounded HH06 records in
this branch preserve the qualified worker identity, but no separate production
release claim is made for the worker beyond the cited runtime evidence.

## ALE/flow runaway and mesh-path ambiguity

Phase 1I showed a late feedback chain consistent with large force, large absolute
structural displacement change, high mesh velocity/mesh Co, flow velocity growth
and SST `omega` growth. Phase 1K.11 avoided the same solver crash for 25 windows,
but did not close the displacement-to-RBF-to-mesh path. Do not mask either result
with arbitrary dt, relaxation, SST, fvSchemes or fvSolution changes. The next
technical decision must use direct displacement-path evidence.

## Bounded HH06 runtime and production readiness

Phase 1D.6 closes the bounded launcher contract with a separate
`BOUNDED_COUPLING_QUALIFICATION` authorization for exactly two physical windows.
The maturity/status remains `READY_FOR_DRY_RUN`. Preflight requires the pinned
worker and Fluid adapter, the frozen 30.0 s F0 evidence, Force initial data,
`dt=0.0002`, `max-iterations=20`, Python/preCICE runtime qualification, and a
clear XML-configured socket directory. It does not start either participant.

The later Phase 1E-R and Phase 1F runs established bounded real lifecycle results.
They did not establish production readiness. Phase 1K.11 is a separate RBF/ALE
stress result with `REVIEW_REQUIRED`, and K20--K22 use an experimental adapter.
No result in this branch authorizes production HH06 FSI, 0.2 s production time,
or multi-slice coupling.

## Adapter source lineage remains unresolved

The source-to-binary provenance of the installed Fluid adapter is unresolved. Phase
1C.7C qualified initial Force configuration behavior only for SHA256
`26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572` (Build ID
`e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b`). The HH06 launcher fails closed on a
different adapter binary. The pin is restricted to the bounded qualification
profile; it does not resolve adapter source/build provenance or imply production
readiness.

K20--K22 use a separately named source-preserved experimental adapter with SHA256
`225ecab227b8271f01119fe476370e3a0b705ca06e1ca3a7739200266499b165`. That
experimental identity must not be silently substituted for the historically
qualified adapter.

## Experimental adapter convergence limitation

The experimental adapter preserves the tested point-displacement boundary values,
cell-displacement staging field, mesh state and ANCF state across the K20--K22
rollback checks. K22 still accepted every window at the 20-iteration limit and
reported no convergence within that cap. The adapter therefore has an isolated
lifecycle qualification and no production convergence qualification.

## Phase 1K.25 candidate-force causality is superseded; G2 branch is repeatable

Phase 1K.25's field-history canonicalization and candidate state snapshots
remain valid observations. Its reported Group 1 causal contribution to Force
repeatability is withdrawn: the Force samples used for that comparison did not
have a verified identical Fluid-read displacement. The same limitation applies
to attempts 1/2 in K23/K24; those records remain preserved, but are not valid
same-input Fluid Force comparisons.

Phase 1K.27 then used the K26 G2 branch and verified attempts 3/4 had identical
Fluid-read displacement, time identity, geometry and all 15 S01–S11 solver
stage records. Their direct raw per-face pressure, viscous and total Forces
were bitwise equal; the exact adapter preWrite Force buffers were also equal
(both difference norms `0`). Structure-received Force still differed by
`0.01869480300014619 N`, but its reads were at different relative offsets:
`dt` for retry attempt 3 and `0` for accepted-boundary attempt 4. The
pre-acceleration value was not observed, so the precise downstream
mapping/acceleration/read-sampling cause remains unresolved.

This supports Fluid raw-force and outgoing-payload repeatability only on the
tested G2 branch/pair. It does not establish general rollback completeness or
global operator repeatability. A CFD inner-convergence A/B is now authorized as
the next diagnostic only and has not been run. IQN retest, parameter tuning,
multi-window runs, and production-adapter adoption remain unauthorized.

## Forbidden historical shortcuts

- Do not revive the old Re=100 / D=1 m / 50 m / 604-vertex participant for HH06.
- Do not map CFD faces one-to-one to ANCF nodes.
- Do not treat `1188.28 N` equilibrium reaction as the `1175 N` benchmark input.
- Do not change SHM1 from full length to `0--5.94 m` merely to cure divergence.
- Do not call a diagnostic displacement offset a physical HH06 result.
