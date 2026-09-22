# Frozen roadmap

The project must proceed in this order and must not skip a layer:

1. **ANCF-0:** MATLAB versus C++ authoritative numerical cross-validation.
2. **ANCF-1:** static equilibrium.
3. **ANCF-2:** modal and free-vibration tests.
4. **CFD-1:** fixed-cylinder Re=7622 baseline.
5. **CFD-2:** prescribed/forced oscillating-cylinder contract.
6. **Mapping:** force scaling and absolute displacement semantics.
7. **FSI-1:** HH06 single-slice ANCF qualification and retry/read-path repair.
8. **FSI-2:** 3-slice low-order smoke.
9. **FSI-3:** slice-number sensitivity (1, 3, 5, ...).
10. **Benchmark:** HH06 quantitative trend comparison.
11. **Method extension:** finite-span/thick 3-D strip.

The next authorized engineering task is not “add more slices”. It is a targeted audit
of the trial displacement writeback and implicit iteration semantics, followed by an
isolated requalification with source/binary identity frozen.
