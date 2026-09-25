# Phase 1K.29 — CFD inner-convergence adequacy diagnostic

## Result

Classification: **`INNER_AB_NOT_CONTROLLED`**.

This phase does not establish either `CURRENT_INNER_SOLVE_ADEQUATE` or
`CURRENT_INNER_SOLVE_NOT_ADEQUATE`. The controlled-comparison gate failed
before a valid inner-only final-force difference could be interpreted.

The first two corresponding PIMPLE outer iterations of A and B were exactly
equal. The first difference appears at outer 3:

* raw Force difference: `1.2499134022650403e-4 N`;
* pressure contribution difference: `1.2499169130773745e-4 N`;
* viscous contribution difference: `4.059333055795571e-10 N`.

The reason is execution-path control, not an observed solver failure. A has
three outer correctors, so its outer 3 is a final outer iteration and uses the
`pFinal`/final equation entries. B has six outer correctors, so its outer 3 is
not final and uses the non-final entries. Therefore A outer 3 and B outer 3
are not equivalent observations under the current OpenFOAM lifecycle.

The apparent difference between A's final raw Force and B's final raw Force is
`6.627370781791863e-3 N` (pressure `6.6294438211206095e-3 N`, viscous
`2.082786423634808e-6 N`; ratio to `1e-3 N`: `6.627370781791862`). These
numbers are reported for transparency only and are **not** accepted as the
K29 `delta_F_inner`, because the A/B first-three-outer trajectory gate failed.

## Frozen configurations and scope

* A: `nOuterCorrectors=3`, `nCorrectors=2`,
  `nNonOrthogonalCorrectors=0`, `momentumPredictor=yes`.
* B: `nOuterCorrectors=6`; all other `fvSolution` entries are unchanged.
* Old authoritative mesh and native 30.0 s fields; no `mapFields`.
* Native `displacementLaplacian`; no RBF.
* `dt=0.0002 s`, fixed `D*=(1.0633832164606064e-7,
  9.530777190012017e-8) m`.
* B1/G2 experimental adapter SHA256:
  `0edcfae77d51d8a57a354a1b745c77f6c15108bf532be0d4893394e80a2d785d`.
* Isolated diagnostic solver SHA256:
  `ada59d50d7c317926bb3f2b4e0fb02c2491362db268c9a2864b023e44dcd834f`.
* OpenFOAM Foundation 10, preCICE 3.4.1.

All three runs used one physical window and a four-attempt diagnostic ceiling.
Fluid and Structure exited with code 0. The fixed Structure participant was
used only for the coupling lifecycle; its received Force is not an inner
convergence metric.

## Repeatability control

B1 and B2 were independent fresh-process runs from independent copies of the
same restart. Every recorded outer Force row (24/24) matched exactly,
including raw Force hashes. Their final direct raw Force was:

`(-0.045560265665227306, -0.039629577615541055) N`

with difference norm exactly `0 N`. Their Fluid input attempts 3/4 also have
the same full displacement hash
`d32bcccbaeeca2e6685266c70dc358dfd0ba7a76ec226990fa27cc741b1fb339`.
Their final adapter preWrite payload hashes were also identical, with
preWrite L2 difference `0`.

Thus B repeatability passed, but it does not repair the A/B control failure.

## Force and payload observations

For A attempt 4, direct raw Force and adapter preWrite sum were
`(-0.04060569387559982, -0.03522795724790643) N`.

For B attempt 4, both were
`(-0.045560265665227306, -0.039629577615541055) N`.

The corresponding adapter preWrite full-buffer L2 difference is
`6.916855557507504e-4`; this is the consequence of the uncontrolled A/B
solver-path comparison, not a Structure-received Force measurement.

Structure read values remain downstream context only. A attempt 4 received
`(-0.04060569387559982, -0.03522795724790643) N`; B attempt 4 received
`(-0.045560265665227306, -0.039629577615541055) N`, both at relative read
offset `0 s`.

## Adequacy and authorization gates

`CURRENT_INNER_SOLVE_ADEQUATE_FOR_TESTED_STATE`: **UNRESOLVED**.

The K29 result authorizes no inner-solver repair or parameter sweep. A future
diagnostic must first make A/B final/non-final linear-solver lifecycle
equivalent, or use a control design that does not compare A's final outer to
B's non-final outer. That redesign is outside K29.

CFD inner-convergence adequacy is therefore not established for downstream
qualification. IQN retest remains **NO**. No production `fvSolution`, adapter,
mesh, physics, timestep, turbulence setting, relaxation, or coupling
tolerance was changed.

## Evidence

The complete bounded run is archived under
`evidence/phase1k29_cfd_inner_convergence/run-20260925T214500Z-9747b00/`.
The root evidence includes runtime/restart identities, A/B configurations,
outer Force traces, residual traces, field-difference status, Force comparison,
B repeatability, participant cleanup, and qualification summary. Full field
L2/Linf differences are marked `NOT_OBSERVABLE_FROM_RECORDED_HASH_AND_STATS`
because the isolated instrumentation recorded hashes and norms, but did not
serialize complete field arrays.
