# Project context

## Research object

The project studies vortex-induced vibration of a high-aspect-ratio flexible riser.
The near-term objective is a credible two-dimensional strip-CFD to finite-element
ANCF coupling workflow. The longer-term method extension is a finite-span/thick-strip
3-D hydrodynamic representation after the baseline is closed.

## Scope boundaries

Current scope is deliberately narrow:

- OpenFOAM incompressible CFD;
- preCICE implicit coupling;
- ANCF structural dynamics;
- sectional/strip force mapping;
- HH06 Case 1 contract and response trends.

Do not add AI, platform 6DOF, lazy-wave geometry, or general curved-riser features
before the baseline and slice convergence are complete.

## Scientific interpretation

The present HH06 single slice is a parameterized coupling qualification, not a full
Huera-Huarte Case 1 reproduction. One CFD slice at `s=2.97 m` represents its own
tributary interval; it does not represent the entire exposed riser. Quantitative
benchmark claims require more slices and a slice-number sensitivity study.

## What is already strong

The generic ANCF numerical core has independent MATLAB/C++ evidence, including static,
modal and free-vibration comparisons. The SHM1 regional hydrodynamic matrix protocol
and M1--M4 capability baseline are also documented.

## What is not yet established

The full HH06 Fluid--preCICE--ANCF production loop has not passed the bounded
multi-window criterion. A one-window nonzero-ALE diagnostic passed in isolation, but
the 25-window run later showed a coupled ALE/flow/turbulence runaway. This distinction
must remain visible in every future report.
