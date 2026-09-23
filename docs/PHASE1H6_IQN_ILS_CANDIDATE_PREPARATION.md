# Phase 1H.6 — IQN-ILS Candidate Configuration Preparation

## Result

**Candidate prepared and accepted by the installed preCICE 3.4.1 configuration validator.** No coupling participant was initialized and no runtime was run. The production configuration, source, contract, physics, and restart were not changed in this phase.

## Candidate and frozen baseline

- Qualified baseline: `cases/hh06_single_slice/precice-config.xml`
- Isolated candidate: `evidence/phase1h6_iqn_ils_candidate/precice-config.xml`
- Baseline SHA256: `e4987ec7d768517feefe312a9ddcbd391ff052981aa84bae6934b555e97d1f71`
- Candidate SHA256: `cd943e0cfa04d7937d6a421305a032a642ae5a80d7e842b6a1651ec11517bff9`

The XML diff replaces only the acceleration element. The parallel-implicit scheme, five-window profile, `dt=0.0002 s`, `min-iterations=2`, `max-iterations=20`, convergence measures, meshes, exchanges, initial-data flags, mappings, and socket configuration are unchanged. The baseline's acceleration explanatory comment is retained.

Candidate acceleration block:

```xml
<acceleration:IQN-ILS reduced-time-grid="true">
  <initial-relaxation value="0.2" enforce="true"/>
  <max-used-iterations value="1"/>
  <time-windows-reused value="1"/>
  <data name="Displacement" mesh="Structure-Mesh"/>
  <data name="Force" mesh="Structure-Mesh"/>
  <filter type="QR3" limit="1e-2"/>
  <preconditioner type="residual-sum"/>
</acceleration:IQN-ILS>
```

`filter limit="1e-2"` follows the reviewed Phase 1H.5 candidate design; no other acceleration option or coupling setting was added.

## Installed 3.4.1 validation

Runtime identity was queried with `precice-version`, which reported preCICE `3.4.1`. The installed `/usr/bin/precice-config-doc dtd` describes the `parallel-implicit` IQN-ILS element and accepts the candidate's child-element ordering and attributes, including `reduced-time-grid`, `initial-relaxation/enforce`, `max-used-iterations`, `time-windows-reused`, `filter`, and `preconditioner`.

Exact validator commands and results:

| Command | Exit | Output |
|---|---:|---|
| `precice-config-validate evidence/phase1h6_iqn_ils_candidate/precice-config.xml` | 0 | `No major issues detected`; no parser warning emitted |
| `precice-config-validate cases/hh06_single_slice/precice-config.xml` | 0 | `No major issues detected`; no parser warning emitted |

The validator reports syntax/basic-setup checks; this is configuration validation only, not evidence that IQN-ILS converges or improves the physical coupling. No Fluid/Structure participant, OpenFOAM solver, preCICE coupling runtime, or ANCF worker was started.

## Interface and primary-vector dimensions

The current HH06 interface contract defines a one-vertex `Structure-Mesh` with two spatial dimensions; `Fluid-Mesh` has 200 vertices. Both exchanged fields in the coupling scheme use `Structure-Mesh`. Each vector field therefore contributes one vertex × two components × one reduced-time-grid sample:

| IQN-ILS primary data | Exchange mesh | Scalar count |
|---|---|---:|
| `Displacement` | one-vertex, 2D `Structure-Mesh` | 2 |
| `Force` | one-vertex, 2D `Structure-Mesh` | 2 |
| **Primary IQN-ILS vector** |  | **4** |

This is the preCICE coupling-data dimension, not the 198 structural ANCF degrees of freedom or the 200 Fluid mesh vertices. The exchange meshes and vector dimensions are confirmed by the candidate XML and `cases/hh06_single_slice/contract.json` / `interface_contract.json`.

## `max-used-iterations` choice

The selected value is **1**, giving the small four-scalar primary system at most one retained least-squares column. In the preCICE v3.4.1 quasi-Newton implementation, the dimensional warning condition is reached when `2 × columns >= primary-vector rows`; one column gives `2 < 4`, while two columns reach the warning threshold. Thus one is the conservative nonzero history size for this interface. It limits this candidate to a rank-one update and does not establish likely convergence speed. The implementation criterion is documented in the version-matched [preCICE v3.4.1 `BaseQNAcceleration.cpp`](https://github.com/precice/precice/blob/v3.4.1/src/acceleration/BaseQNAcceleration.cpp#L243-L322); the exchanged-mesh dimension follows the [v3.4.1 coupling configuration](https://github.com/precice/precice/blob/v3.4.1/src/cplscheme/config/CouplingSchemeConfiguration.cpp#L255-L277) and the reviewed Phase 1H.5 audit.

## Boundary and repository state

Only these Phase 1H.6 artifacts were added:

- `evidence/phase1h6_iqn_ils_candidate/precice-config.xml`
- `docs/PHASE1H6_IQN_ILS_CANDIDATE_PREPARATION.md`

The production XML hash remained `e4987ec7d768517feefe312a9ddcbd391ff052981aa84bae6934b555e97d1f71` after candidate preparation. The worktree already contained unrelated, previously accepted Phase 1E–1H changes; they were left untouched. Current HEAD at preparation was `02d9a1f180082e83bcc9f7acdcb090502262b2d1` on `repair/worker-lineage-implicit-contract-v1`.

This artifact only prepares the candidate for review. It does not authorize modifying the production XML or starting an A/B runtime.
