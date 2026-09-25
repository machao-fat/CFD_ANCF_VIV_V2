# Roadmap and current gate

The project must proceed in this order and must not skip a layer:

1. **ANCF-0:** MATLAB versus C++ authoritative numerical cross-validation.
2. **ANCF-1:** static equilibrium.
3. **ANCF-2:** modal and free-vibration tests.
4. **CFD-1:** fixed-cylinder Re=7622 baseline.
5. **CFD-2:** prescribed/forced oscillating-cylinder contract.
6. **Mapping:** force scaling and absolute displacement semantics.
7. **FSI-1:** HH06 single-slice ANCF qualification and retry/read-path repair. The
   Strategy C lifecycle passed bounded real 2-window and 5-window runs. The old
   mesh failed in the historical 25-window region; the new RBF run is
   `REVIEW_REQUIRED`.
8. **FSI-2:** 3-slice low-order smoke, pending closure of the single-slice RBF and
   adapter path.
9. **FSI-3:** slice-number sensitivity (1, 3, 5, ...), pending FSI-2.
10. **Benchmark:** HH06 quantitative trend comparison.
11. **Method extension:** finite-span/thick 3-D strip.

## Qualification state closure

Phase 1K.11 is the new-mesh/RBF 25-window stress result. It completed the bounded
run, but its saved accepted mesh points stayed at release coordinates while
rejected-trial force and pressure spikes were observed. Its status is
`REVIEW_REQUIRED`.

Phase 1K.20 is a one-retry nonzero point-displacement checkpoint result.
Phase 1K.21 is a two-window experimental adapter lifecycle result. Phase 1K.22 is
a five-window experimental adapter lifecycle result. K21 and K22 reached the
20-iteration limit; K22 did not converge within the cap. These results are not
production-adapter qualification.

The repair branch is not ready to merge into `main`. The merge gate requires:

1. resolve the K11 Structure-displacement to Fluid-adapter to RBF-to-mesh path;
2. decide whether the experimental adapter can be promoted through a source and
   binary review;
3. establish an accepted convergence policy beyond repeated iteration-cap
   acceptance;
4. update the production contracts only after those reviews pass.

Until then, keep the branch as the reviewable repair and evidence branch. Do not
start three-slice work or production-duration HH06 FSI from this state.
