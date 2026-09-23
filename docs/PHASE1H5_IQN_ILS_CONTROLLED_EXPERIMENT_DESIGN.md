# Phase 1H.5 — IQN-ILS Controlled Experiment Design

## Outcome

**Classification: `IQN_ILS_EXPERIMENT_READY`.**

The active preCICE IQN-ILS system has **four primary scalar unknowns** for the proposed two-data configuration, not 402. With the two 2D vector fields `Displacement` and `Force` both configured as primary data on the one-vertex `Structure-Mesh`, the safe `max-used-iterations` value is **1**. This is a nonzero, usable least-squares history, although it permits only a rank-one update. The interface is small and constrains the method; it is not too small to justify the controlled experiment.

This classification means the design is ready for separate review and execution authorization. It does not authorize an XML edit or an A/B runtime in this phase.

## Scope and frozen baseline

No XML, source, physics, or runtime changes were made. The previously accepted baseline remains:

- `parallel-implicit`
- constant relaxation `0.2`
- `max-iterations=20`, `min-iterations=2`
- `dt=0.0002 s`, five physical windows for the comparison profile
- unchanged restart at global time 30.0 s and qualified physical `F0`
- unchanged mesh, OpenFOAM, ANCF, force mapping/scaling, and convergence limits

The audited HEAD is `02d9a1f180082e83bcc9f7acdcb090502262b2d1` on `repair/worker-lineage-implicit-contract-v1`. The worktree was already dirty from accepted prior phases; this report preserves that state.

## Exact IQN-ILS scalar dimension in this case

The current HH06 interface contract declares a one-vertex, two-dimensional `Structure-Mesh`, while `Fluid-Mesh` contains 200 cylinder-wall vertices. Both vector fields are written/read on both participant meshes, but both coupling-scheme `<exchange>` entries explicitly specify **`mesh="Structure-Mesh"`**. The force mapping transfers the 200 Fluid-side samples to the one structural coupling point; the displacement mapping transfers that one point to the 200 Fluid-side vertices.

For preCICE `3.4.1`, the exchange mesh—not the ANCF 198-DOF state and not the unmapped 200-vertex Fluid mesh—sets the `CouplingData` size used by the coupling scheme. The v3.4.1 configuration source creates the exchanged data using the mesh named by the `<exchange>` entry and passes that mesh to the scheme; the parallel scheme returns all its coupling data to the acceleration. The quasi-Newton implementation forms its primary vector by summing the configured primary data sizes, with each field contributing its vertex count × vector dimension × selected time-grid samples. See the v3.4.1 [`CouplingSchemeConfiguration.cpp`](https://github.com/precice/precice/blob/v3.4.1/src/cplscheme/config/CouplingSchemeConfiguration.cpp#L255-L277) and [exchange setup](https://github.com/precice/precice/blob/v3.4.1/src/cplscheme/config/CouplingSchemeConfiguration.cpp#L965-L991), [`ParallelCouplingScheme.cpp`](https://github.com/precice/precice/blob/v3.4.1/src/cplscheme/ParallelCouplingScheme.cpp#L105-L110), and [`BaseQNAcceleration.cpp`](https://github.com/precice/precice/blob/v3.4.1/src/acceleration/BaseQNAcceleration.cpp#L776-L855).

With the proposed IQN-ILS primary data list containing both exchanged vectors, and the current one-endpoint-per-window setup (`waveform-degree=0`, `substeps=false`, reduced time grid), the count is:

| Primary coupling data | Exchange mesh | Vertices | Components/vertex | Time samples | Scalar unknowns |
|---|---|---:|---:|---:|---:|
| `Displacement` | `Structure-Mesh` | 1 | 2 | 1 | 2 |
| `Force` | `Structure-Mesh` | 1 | 2 | 1 | 2 |
| **Total primary IQN-ILS vector** |  |  |  |  | **4** |

This distinction matters: if only one vector were listed as primary, the primary system would have only two rows. preCICE's v3.4.1 implementation warns when `2 × least-squares columns >= primary interface unknowns`; the exact check is in [`BaseQNAcceleration.cpp`](https://github.com/precice/precice/blob/v3.4.1/src/acceleration/BaseQNAcceleration.cpp#L243-L322). For four primary unknowns, one column satisfies `2×1 < 4`; two columns reach the warning threshold. The constructor also requires a positive maximum column count ([v3.4.1 source](https://github.com/precice/precice/blob/v3.4.1/src/acceleration/BaseQNAcceleration.cpp#L31-L70)). Therefore:

- safe tested range for this configuration: **`max-used-iterations=1` only**;
- `0` is invalid;
- `2` or more is not a parser-level rejection, but reaches the implementation's ill-conditioning warning and is outside the recommended safe range;
- defaults such as `100` must not be used here.

`max-used-iterations` limits the number of retained least-squares columns, not the ANCF degrees of freedom or physical windows. Listing **both** primary vectors is required to obtain the four-row system used in this dimension audit.

## Proposed single IQN-ILS candidate

The candidate changes only the acceleration block. It does not change the coupling scheme, iteration cap, convergence criteria, or any physical/numerical model setting.

| IQN-ILS setting | Proposed value | Reason |
|---|---|---|
| Primary data | `Displacement` and `Force`, both on `Structure-Mesh` | Includes both parallel-coupling directions; produces the four-scalar primary vector and exposes both variables to the quasi-Newton fit. |
| Initial relaxation | `0.2`, `enforce="true"` | Matches the baseline's first fixed-point relaxation factor, including the first attempt of each physical window. The measured comparison then tests the IQN update after that matched seed. |
| `max-used-iterations` | `1` | Maximum safe column count under the v3.4.1 `2×columns < 4 primary unknowns` conditioning criterion. |
| `time-windows-reused` | `1` | Allows data from at most the immediately preceding physical window; avoids carrying a long history through the strongly changing early-window response. The one-column cap remains in force. |
| Preconditioner | `residual-sum`, explicitly specified | Available in the installed 3.4.1 schema and its documented default for QN; scales the disparate Force and Displacement residual blocks without adding a manually guessed unit factor. |
| Filter | `QR3`, limit `1e-2` | Explicit rank/conditioning filter for the short, low-dimensional history; the official guide gives `1e-2` as a starting value for QR2/QR3. |
| Reduced time grid | `true` | Uses the current window endpoint, consistent with one exchanged sample per window and the four-scalar count above. |
| Bound handling | Leave at 3.4.1 default (`ignore`) | The current coupling data have no configured bounds, so bound-handling options do not affect this comparison. |

The installed package is `libprecice3 3.4.1`; its local `/usr/bin/precice-config-doc md` confirms the IQN-ILS schema, positive column count, defaults (initial relaxation `0.1`, maximum columns `100`, reused windows `10`), and residual-sum preconditioner default. The proposed explicit values deliberately override defaults where needed for fairness or the four-DOF interface. The current official [acceleration guide](https://precice.org/configuration-acceleration) documents the low-interface-DOF column heuristic and filtering guidance. The comparison XML must still be checked with the installed 3.4.1 parser before any coupled runtime; this phase did not create or validate a candidate XML file.

## Fair five-window A/B protocol

The historical Phase 1F run is the baseline for iteration/residual histories, but it did not preserve a measured wall-clock duration. A fair comparison therefore needs **two fresh five-window runs**: a baseline replay and the IQN-ILS candidate.

1. Make independent scratch copies from the exact 30.0 s restart and mesh for each run. Verify restart field and mesh hashes, restart time, and the unchanged qualified `F0`; never start one run from the other run's advanced fields.
2. Use the same qualified OpenFOAM, adapter, preCICE 3.4.1, Python binding, worker, participant source, and launch environment in both runs. Start fresh preCICE sessions and use isolated logs, sockets, and output directories.
3. Keep exactly five physical windows, `dt=0.0002 s`, `min-iterations=2`, `max-iterations=20`, identical convergence measures, Force mapping/scaling, mesh, CFD/ANCF settings, and all other physics fixed.
4. Baseline uses constant relaxation `0.2`. Candidate uses only the IQN-ILS block above. Freeze both complete XML hashes before starting either run. No mid-run tuning, retries with altered values, or extension beyond five windows.
5. Measure and report per window:
   - number of coupling attempts and convergence-before-cap versus `ACCEPTED_AT_ITERATION_LIMIT`;
   - every preCICE Force and Displacement residual, with the same absolute/relative pass logic;
   - participant ANCF `D_trial` residual separately from the preCICE Displacement residual;
   - Force input/returned residual history;
   - ANCF solve count, Newton iterations per solve and total Newton iterations, nonlinear residuals;
   - wall-clock using one fixed start/stop definition from launcher start through participant exit.
6. Capture IQN-specific iteration columns (used/deleted/dropped columns and acceleration log if enabled), candidate XML and runtime identities. Report raw per-window results, not only averages. Treat any cap acceptance as cap acceptance, never as convergence.

If per-solve ANCF elapsed time is desired in addition to Newton work, the current Phase 1F trace does not provide it. Add the same passive timing instrumentation to both runs before the paired experiment, or mark per-solve time unavailable; do not compare instrumented candidate time with an uninstrumented baseline.

## Justification and boundary

The Phase 1F baseline showed slow monotonic convergence and four of five windows accepted at the 20-iteration cap. The low-dimensional audit resolves the concern that IQN-ILS history is wholly unusable: both primary vector fields create four scalar unknowns, allowing one safe history column. That is sufficient to justify one controlled experiment, while limiting expectations: this candidate can use only a rank-one least-squares direction and may not improve both Force and Displacement simultaneously.

**Final classification: `IQN_ILS_EXPERIMENT_READY`.** The A/B experiment is justified once its candidate XML is reviewed and the runtime is separately authorized. No 25-window qualification, XML edit, acceleration change, or real runtime is authorized by this design report.

No source/configuration files were changed in Phase 1H.5. The existing worktree changes remain untouched; current HEAD is `02d9a1f180082e83bcc9f7acdcb090502262b2d1`.
