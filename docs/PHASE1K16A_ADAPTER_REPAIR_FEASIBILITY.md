# Phase 1K.16A — Fluid adapter read-time repair feasibility audit

**Classification: `ADAPTER_SOURCE_UNRESOLVED`.** A public OpenFOAM-preCICE adapter source candidate and a historical isolated repair are available, but neither is proven to be the source of the currently qualified Fluid adapter. A separately named, source-pinned experimental OpenFOAM-10 build is a feasible *future qualification path*, not an authorized replacement or a verified patch to the qualified binary. No build or runtime was performed in this phase.

## Scope and frozen identities

Audit HEAD: `c2245ff396ff42dfa5e80fee6555a9ede93e3b04` on `repair/worker-lineage-implicit-contract-v1`. The existing tracked worktree had no modifications; pre-existing untracked phase reports/evidence were left untouched.

| Artifact | Identity / finding |
| --- | --- |
| Qualified Fluid adapter | `/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so` |
| SHA256, rechecked | `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572` |
| ELF Build ID, rechecked | `e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b` |
| Runtime version context | Foundation OpenFOAM 10, preCICE 3.4.1; exact loaded binary was established by earlier runtime evidence, not reloaded here. |
| Existing bug evidence | `docs/PHASE1K15_FLUID_DISPLACEMENT_READ_TIME_AUDIT.md` and `evidence/phase1k14_adapter_read/`; no repeat measurement. |

The old Phase 1K.11 result and Phase 1K.14/1K.15 evidence remain historical evidence. This audit does not change their classifications.

## Source and build provenance

The candidate's Git remote is [`precice/openfoam-org-adapter`](https://github.com/precice/openfoam-org-adapter), a Foundation-oriented fork of [`precice/openfoam-adapter`](https://github.com/precice/openfoam-adapter). A local checkout exists at `/mnt/d/研二文件/开题准备/CFD_ANCF_VIV/runtime/openfoam_adapter_v131_rollback_observability_source`, HEAD `3d45c38c5091331906bd32517b400d8cb0786bb1` (v1.3.0 version/changelog commit, 2024-02-09). **Its working tree is dirty across many files**, so the observations below use `git show HEAD:<file>` rather than assuming worktree files represent that commit. The committed `LICENSE` is GPL-3.0.

The committed `Allwmake` uses `wmake libso`, checks the OpenFOAM environment and preCICE via `pkg-config`, and supports `ADAPTER_TARGET_DIR` (default `FOAM_USER_LIBBIN`) and `ADAPTER_PREP_FLAGS`. `Make/files` names `libpreciceAdapterFunctionObject`; `Make/options` links Foundation OpenFOAM and `libprecice`. Its committed `docs/openfoam-support.md` lists Foundation OpenFOAM 10 via a version-specific branch and calls Foundation support secondary/experimental. This establishes a **documented porting route**, not that this particular local HEAD builds cleanly with the installed Foundation-10 headers. The earlier V2 Phase 1C.7B audit records a `faceTriangulation.H` incompatibility from an attempted candidate rebuild. No compiler/build check was repeated here.

The candidate source is **not matched** to the qualified `26ad…` binary by an embedded commit, build manifest, build log, reproducible output hash, or debug-source record. More importantly, its committed `Adapter.C::execute()` calls `advance()`, checkpoint actions, then `adjustSolverTimeStepAndReadData()` for the fixed-step path; that helper calls `readCouplingData(runTime_.deltaT().value())`. This differs materially from the qualified binary's statically verified `advance() → readCouplingData(0.0) → requiresReadingCheckpoint()` call order. The candidate must not be labeled the exact source of the qualified binary, and its helper cannot be edited on the assumption that it implements the measured zero-offset bug.

Migrated historical evidence at `evidence/legacy_qualification/hh06_single_slice_coupling_history_v1/evidence/runtime/hh06_adapter_displacement_read_path_fix_v1/HH06_ADAPTER_DISPLACEMENT_READ_PATH_FIX_REPORT.md` describes an isolated OpenFOAM-10 adapter source and one-window repair. Its reported source `Adapter.C` SHA256 is `710f45fba682442cbec979d6993a24b2c530b0e592b62c18041d429ca4dd6301`; its final binary SHA256 is `8c2c0fda85dc7ed452eb144b03a92ac9bf739e62ee8369baf489b3439cfdf458`. That report documents checkpoint/mesh-state changes in addition to read ordering, and a prior `phiRef()` API failure. It is useful forensic guidance, **not** a source match for `26ad…`, a patch to copy, or a qualified replacement. Only the migrated report/result artifacts, not a complete build source tree, are present in this V2 evidence location.

## Lifecycle comparison and repair options

| State | Current pinned binary (Phase 1K.15) | Required read-time contract |
| --- | --- | --- |
| Post-advance retry | `advance → readData(Displacement, 0.0) → requiresReadingCheckpoint → rollback` | `advance → determine retry → readData(Displacement, dt) → physical rollback/retry`, with field application/checkpoint timing verified against the actual source. |
| Accepted, still-active boundary | Same unconditional zero read before checkpoint decision | `advance → determine accepted boundary → readData(Displacement, 0.0) → commit/next window`. |
| Final completed coupling | No further read in the observed one-window diagnostic | No invalid post-final read. |

For preCICE 3.4.1, `0.0` denotes the current timestep/window start and `dt` its endpoint (installed `/usr/include/precice/Participant.hpp`; see Phase 1K.15). Phase 1K.14 observed 400 zero received displacement scalars during three retries, although Structure wrote nonzero trial displacement. Phase 1K.15 traced the qualified binary's exact zero argument. **This does not yet prove that changing the offset alone will deliver a nonzero RBF boundary field**: interface-field application and physical mesh/checkpoint restoration still need their own qualification.

- **A — source-based experimental adapter:** Feasible as a *new* source-lineage project, but the exact qualified-binary source is unresolved. First select and pin a clean Foundation-10-compatible source commit/branch, document any necessary API port, compare its lifecycle to the binary and the required contract, and design the narrow offset/checkpoint change. Build into an isolated output location under a **distinct library basename** (for example `libpreciceAdapterPhase1K16Diag.so`), never `libpreciceAdapterFunctionObject.so` in the qualified library directory. Record full source-tree and patch hashes, command, compiler, OpenFOAM/preCICE identities, resulting SHA256 and Build ID, and verify the scratch case loads that distinct file. Separate offline/one-window validation would be required before considering any runtime adoption. **No source or build was created here.**
- **B — source unavailable:** The original source-to-binary build lineage for `26ad…` is unavailable in the audited records. If repair of that *exact source lineage* is mandatory, this is a blocker pending a trustworthy source/build manifest or reproducible reconstruction. The public candidate is not a substitute merely because its API and library name match.
- **C — external wrapper/debugger/binary patch:** An ABI-level interceptor or debugger argument rewrite could potentially alter a `readData` argument, but it would need to recognize retry versus acceptance and preserve OpenFOAM checkpoint/field-application ordering. No such mechanism is verified in this environment. Binary patching or replacing the installed soname would break provenance; a generic preCICE wrapper cannot be recommended as the safer production repair. Treat this option as **not established**.

## Decision and next gate

**`ADAPTER_SOURCE_UNRESOLVED`** means source code is available for investigation, but the source of the qualified adapter is not identified. A future authorized phase should choose a clean Foundation-10 source baseline, prove its build and runtime identity separately, then test retry `dt` versus accepted `0` together with mesh rollback/field propagation. Until that evidence exists, retain the qualified `26ad…` library unchanged and do not present the historical `8c2…` binary as its successor.

No adapter/source/configuration was modified, no library was rebuilt or replaced, and no OpenFOAM, preCICE or FSI runtime was started.
