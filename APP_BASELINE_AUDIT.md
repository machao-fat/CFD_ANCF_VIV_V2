# VIV_APP_CASE_GENERATOR_MVP_V1 baseline audit

Audit date: 2026-09-30 (Asia/Shanghai). Base: `origin/main`
`a1c4988b23d4a61edbb4c00e6d53926add51d795`.
Worktree: `D:\CFD_Work\APP` (`/mnt/d/CFD_Work/APP`).

## Evidence read before implementation

Read `cases/`, `scripts/`, `src/coupling/`, and all requested contract/context,
provenance, ledger, issues and roadmap documents. There is no N1/N3/N5 complete
production case generator in this main revision. Existing reusable primitives:

* `src/coupling/arbitrary_n_live_orchestration_v1/manifest.py`:
  `build_slice_manifest`, `SliceManifest`, `OrchestrationSlice`; ordered positions,
  active interval, representative lengths, unit spans, force/motion slots.
* `.../topology.py`: `generate_precice_xml`, `inspect_precice_xml`,
  `generate_openfoam_launch_plan`. XML is **parallel-explicit**, with per-slice
  meshes, conservative Force mapping and consistent Displacement mapping.
* `.../coordinator.py`: existing force representation and SLD1 semantics.
  Distributed forces are sectional N/m; legacy forces are integrated N.
* `src/ancf/kernel_protocol.py`: `KernelModel`, SHM1/DMP1/SLD1 model validation.
  Elements imply nodes = elements + 1 and DOFs = 6 * nodes.

## Blocking distinction

`cases/hh06_single_slice/precice-config.xml` is **parallel-implicit**, waveform
degree 0, initial Displacement exchange, relaxation 0.2, convergence/retry settings.
It cannot be substituted with the generic explicit helper. Its socket path is an
old absolute runtime path. `structure_0000_participant.py` fixes one slice, 32
elements and P1 initial-state artifacts outside this repository; its kernel backend
rejects SLD1/multi-slice requests. `launch.sh` also references absent executables
and a historical OpenFOAM environment. The ledger does not qualify full HH06 FSI.

Therefore this baseline is rejected with
`GENERATION_BLOCKED_BY_UNKNOWN_CONTRACT`: implicit arbitrary-N structure/launcher
contract and portable P1 initial state are not established in main. No runtime
branch is copied into APP, no implicit-to-explicit conversion is authorized, and
no static PASS represents a production FSI qualification.

## V1 supported import boundary

V1 uses an explicit, versioned `app_baseline.json` descriptor for a baseline
already using the repository's **generic explicit** contract. It points to one
fluid template, a native KernelModel JSON, the native slice manifest, and a
serialized structural initial state. All are local to baseline. XML must match
the existing helper structurally (socket location may differ). This is an APP
import adapter, not a new solver/physics contract. Unknown/missing fields fail
closed. Bundled tiny fixtures are SYNTHETIC_OFFLINE_ONLY and are not validated
CFD baselines. The APP preserves that evidence status in generated manifests.

## Safe writable fields

* Case identity; N=1..32 subject to inherited reconstruction mode (SLD1 requires
  N>=2); ordered positions within inherited active interval, including endpoints
  because the native generic manifest explicitly permits them.
* Uniform centers and explicit positions through the native manifest builder.
  Legacy representative lengths are inherited and legacy V1 is limited to N=1;
  distributed uniform centers use the native builder's interval/N rule. Custom
  distributed positions retain that rule; lengths do not rescale sectional loads.
* Fixed-value uniform inlet vector at an explicitly declared U dictionary path,
  along an explicitly declared direction. Preserve developed internal fields.
  Unsupported boundary types, directives, compressed fields or ambiguous paths
  produce `UNSUPPORTED_BASELINE_FLOW_CONFIGURATION`.
* controlDict root deltaT/endTime/writeInterval, explicit selected startTime,
  and numberOfSubdomains (scotch only). Coupling max-time = endTime - fluid start;
  time-window-size = deltaT only when that relation is verified in baseline.
* Native KernelModel slices/positions/SLD1 active interval; Rayleigh alpha [1/s]
  only. Never change beta or the SHM1 regions.

## Inherit byte-for-byte or semantically unchanged

Mesh, fluid internal initial fields, all other initial fields (including phi,
Uf, meshPhi, displacement and old-time files when present), selected time's mesh,
constant, fvSchemes, fvSolution, turbulence, PIMPLE, RBF, solver application,
adapter FSI/interface settings, quadrature, boundary conditions, initial structural
q/qdot/qddot, SHM1, force units/scaling, endpoint policy and reconstruction mode.
Absolute operational paths/directives in inherited configuration are rejected.
Initial time directories are copied only when explicitly selected; no fabricated
restart fields. Runtime directories/logs/scripts/binaries are not imported.

## V1 forbidden structural edits

D, L, EA, EI, line mass, pretension and element count have native model fields,
but modifying them while inheriting a mesh and equilibrium q is not safe.
They appear as baseline values marked NOT YET WIRED / locked. Changes fail closed.
No mesh scaling, q remeshing, static equilibrium solve, or automatic SHM1 resizing.
Rayleigh alpha is explicitly identified; no ambiguous scalar damping ratio.

## Manual-launch limitation

The existing generic launch-plan helper describes fluid launches only. Main has
no certified arbitrary-N native KernelModel JSON CLI/production launcher. V1
generates native configuration and a launch manifest with this structural runner
gap clearly marked. It does not invent a launcher. A generated synthetic case can
pass configuration checks but is NOT READY FOR PRODUCTION LAUNCH. Real HH06 import
remains blocked until its unique production contract is supplied and audited.
