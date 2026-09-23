# Phase 1C.6 — HH06 Initial Force / Release Contract Audit

**Classification:** `RELEASE_FORCE_VALUE_UNRESOLVED`
**Secondary status:** `FLUID_INITIALIZATION_PATH_UNRESOLVED`
**Audit branch / HEAD:** `repair/worker-lineage-implicit-contract-v1` / `ba48b409e96d35e0da742c94cc9b6561c0782b7a`
**Scope:** current V2 repository, migrated evidence, installed preCICE 3.4.1 headers, and read-only identification of the local OpenFOAM adapter library. No old repository was accessed. No production source/configuration was modified; no OpenFOAM, preCICE, or HH06 runtime was started.

## 0. Freeze checkpoint

The Phase 1B fake deterministic test passed before the audit (`python3 -m unittest discover -s tests/coupling -v`, 1 test). The completed work was frozen in separate commits:

- `d4abec8` — `test: instrument implicit coupling iteration lifecycle`
- `ba48b40` — `docs: design corrected implicit coupling lifecycle`

The worktree was clean after those commits and before this report was added. No Phase 1C.6 audit change is included in either commit.

## Decision summary

For the first structural solve at release, the physical meaning of `F^(0)` is the instantaneous hydrodynamic traction integrated over the cylinder wall in the **exact fixed-cylinder CFD field at global time 30.0 s**. It is not automatically zero merely because preCICE has a zero default. A zero value may be used as an explicitly labelled numerical fixed-point seed in an offline test, but it is not the HH06 physical release load.

The V2 repository contains the `30/` restart fields and the force conversion contract, but no force record tied to those fields at exactly 30.0 s. Therefore no defensible numeric `Fx0_total_N`, `Fy0_total_N`, or `Fz0_total_N` can be reported. The currently documented nonzero force belongs to the first *advanced* physical window at 30.0002 s / implicit iteration 2 and is not a release-force substitute.

**Recommendation:** prefer Policy A (physical release force) for the HH06 production contract, but do not implement or claim it resolved yet. It needs both (1) a reproducible instantaneous Force value from the exact 30 s restart state and (2) source-level confirmation that the Fluid adapter can write that Force as preCICE initial data. Both gates remain open. Policy B is not accepted as the production release contract.

## 1. Current case and Force contract

| Item | Current V2 evidence |
|---|---|
| HH06 restart identity | `cases/hh06_single_slice/30/`; `30/uniform/time` says value `30`, index `150000`, `deltaT=0.0002`. `PRE_RUN_AUDIT.md` identifies this as the 30 s fixed-cylinder Fluid restart. |
| Structure initial state | `contract.json` uses P1 static `q0`; it explicitly says there is no serialized 30 s FSI structural checkpoint. |
| Physical initial Force fields | `initial_state.Fx0_total_N = null`, `Fy0_total_N = null`; initial-force text says to read the 30 s CFD force if time integration is later authorized. |
| Force patch and output setup | `system/controlDict` configures `cylinderForces`, type `forces`, patch `cylinder`, pressure plus viscous integration, `rhoInf=1000`, `CofR=(0 0 0)`, `writeControl timeStep`, `writeInterval 5`. It separately configures `cylinderForceCoeffs`, which is nondimensional (`dragDir=(1 0 0)`, `liftDir=(0 1 0)`, `magUInf=0.31`, `lRef=0.028`, `Aref=0.000784`). |
| Fluid preCICE interface | `system/preciceDict`: participant `Fluid_0000`, FSI module, `nameForce Force`, 200 cylinder face-centre vertices, `writeData (Force)`, `readData (Displacement)`. |
| Structure preCICE interface | `precice-config.xml`: `Structure_0000` reads `Force`; `Fluid_0000` writes `Force`; the structure mesh has one 2-D coupling point. The configured exchange has no `initialize="yes"` on Force. |
| Spatial force conversion | Frozen rule: `F_strip = (F_raw / Lz) * DeltaL`, exactly once; `Lz=0.028 m`, `DeltaL=1.98 m`. |
| Launch contract | `launch.sh` requires `.initial_state.Fx0_total_N` and `.initial_state.Fy0_total_N` to have JSON number type. They are currently null. The script also requires status `READY`; the contract is `READY_FOR_DRY_RUN`. |

`cylinderForces` is the dimensional, patch-integrated pressure/viscous output family and is the appropriate standalone OpenFOAM record to associate with a restart state if generated at that exact state. `forceCoeffs` is not itself a dimensional Force and must not be substituted for the adapter's integrated Force. OpenFOAM v10 documents the `forces` function object as integrating pressure and skin-friction contributions and summing the force components; see the [OpenFOAM v10 `forces` source](https://cpp.openfoam.org/v10/forces_8C_source.html).

Coordinate convention in the case is the global Cartesian axes, with x configured as drag/streamwise and y as lift/transverse; the current 2-D preCICE Force vector transfers x/y. No exact release-time `Fz` is archived, so this audit does not assume a measured `Fz=0`.

### Release-force evidence search

The current V2 `cases/` and `evidence/` inventory contains no `postProcessing` force history, `forces` output, forceCoeffs output, or adapter trace bound to `cases/hh06_single_slice/30/` at time 30.0 s. The parent `cases/cfd_fixed_cylinder_re7622/` snapshot includes setup and initial fields only; its README explicitly says runtime times, logs, and post-processing outputs are excluded. The HH06 snapshot likewise excludes runtime logs and post-processing outputs.

The migrated force-unit-chain evidence is useful for units but is **not** F⁽⁰⁾:

| Evidence sample | `Fx_raw`, `Fy_raw`, `Fz_raw` | `f_section = F_raw/0.028` | `F_strip = f_section*1.98` |
|---|---:|---:|---:|
| Physical window 1, implicit iteration 2, global time 30.0002 s | `(0.06440713207168003, 0.05908675094604829, 0) N` | `(2.3002547168457155, 2.1102411052160104, 0) N/m` | `(4.554504339354517, 4.178277388327700, 0) N` |

This sample is reported in `HH06_SINGLE_SLICE_FORCE_UNIT_CHAIN_AUDIT.md/.json` and `artifacts/run_analysis.json`; the audit identifies it as window 1, implicit iteration 2, and `run_analysis.json` places the accepted window at 30.0002 s. It verifies the existing conversion chain for that later sample only. It cannot establish the instantaneous fixed-cylinder load at the 30.0 s restart. No time average or literature-derived reconstruction was used.

## 2. Fluid-side initial-data capability

### Current implementation inventory

- The V2 source has no `preciceAdapterFunctionObject`/OpenFOAM-preCICE adapter implementation. `src/openfoam_adapter/ancfFileMotion.C/.H` implements a file-driven OpenFOAM solid-body motion function; it is not the Fluid preCICE adapter and contains no initial Force API path.
- `preciceDict` declares ordinary FSI Force output, but contains no initial-force value or explicit pre-initialize operation.
- The current installed candidate library is `/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so`, SHA256 `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572`, ELF Build ID `e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b`. No matching adapter source/build manifest was found in this V2 checkout or beside that library. This hash is also recorded in migrated evidence as a production adapter binary identity; the separately archived candidate source hash `710F45...` paired with candidate binary `8C2C0F...`, not with a source-matched build manifest for this local library. This audit did not run OpenFOAM and therefore does not assert that this library was loaded by a process in this phase.
- The current Structure backend has a pre-initialize **Displacement** write path. Its `read_force()` invokes `read_data(..., 0.0)`, while the HH06 participant currently calls it only after its first `advance()`. There is no current pre-first-solve Structure Force read path.

### Explicit answers

| Question | Finding |
|---|---|
| A. Can Fluid compute/read Force from the loaded 30 s fields before its first coupling advance? | The fields are present and OpenFOAM's `forces` object can integrate pressure/viscous traction from a loaded solution in principle. But this case only configures periodic output every five time steps; it contains no startup Force record at 30.0 s. Whether the actual Fluid adapter calculates and exposes the exact startup Force before its first advance is **not demonstrated**. |
| B. Can Fluid write Force before `initialize()`? | The preCICE 3.4.1 Participant API supports custom initial coupling data: after defining the mesh, the writer checks `requiresInitialData()`, calls `writeData()`, then calls `initialize()`. This is a generic API capability, not proof about this OpenFOAM plugin. |
| C. Does the current OpenFOAM adapter expose this path? | **Unresolved.** Its source is not present/matched, and a binary hash alone cannot prove that the Fluid function object computes and writes initial Force before `initialize()`. |
| D. Required XML/configuration form? | The Force exchange must request initialization, e.g. `<exchange data="Force" mesh="Structure-Mesh" from="Fluid_0000" to="Structure_0000" initialize="yes" substeps="false"/>`, consistent with this configuration's exchange mesh. Fluid must provide values on its Force-writing mesh before its `initialize()`. Current XML omits the attribute, so Force uses the default zero initial value. |
| E. Configuration only or adapter source change? | The XML change is necessary but may not be sufficient. If the installed adapter already has a verified pre-initialize Force hook, configuration/runtime initialization could suffice; otherwise adapter source must be extended to calculate the release traction from the loaded fields and call the preCICE initial-data API before initialization. The missing source prevents deciding which case applies. The Structure side must also consume the initialized Force after its `initialize()` and before its first ANCF solve. |

## 3. preCICE 3.4.1 semantics

The installed package is `libprecice3 3.4.1`; `/usr/include/precice/Version.h` defines `PRECICE_VERSION "3.4.1"`. The installed `/usr/include/precice/Participant.hpp` states that `initialize()` receives the first coupling data and that initial values are zero by default. It also states that all data default to zero and custom initial values must be written before `initialize()`, after mesh definition, when `requiresInitialData()` indicates the participant must provide them.

The version-matched [preCICE 3.4.1 Participant API documentation](https://precice.org/doxygen/main/classprecice_1_1Participant.html) specifies that `readData(..., relativeReadTime=0.0, ...)` samples data at the beginning of the current time step; `relativeReadTime=dt` samples its end. `readData` is an initialized-participant operation. Consequently, when Fluid has supplied mapped, nonzero Force initial data before `initialize()`, Structure can read the received initial Force after its own `initialize()` and before its first `advance()`. With the first window starting at 30.0 s, this value is the candidate F⁽⁰⁾ for the first ANCF solve, provided its provenance and units are correct.

The [preCICE data initialization guide](https://precice.org/couple-your-code-initializing-coupling-data.html) documents the `requiresInitialData()` → `writeData()` → `initialize()` sequence and the `initialize="yes"` exchange attribute. The [implicit coupling guide](https://precice.org/couple-your-code-implicit-coupling.html) places exchange and convergence handling in `advance()` and requires participants to act on checkpoint requests. The [waveform / relative-read-time guide](https://precice.org/couple-your-code-waveform.html) defines sampling relative to the current step. These semantics establish the generic contract, but do not establish the behavior of the unpaired local OpenFOAM adapter binary.

For later implicit iterations, `advance()` is the exchange boundary; after it returns, Structure's next read must consume the Force iterate delivered for the same active physical window. The existing backend's `relativeReadTime=0.0` means “window/step start,” not “latest” by itself. The HH06 Force is configured with `waveform-degree="0"` and `substeps="false"`; an offline fake-backend test must verify that each post-advance read returns the correct new iteration Force and does not leak a previous window's value.

## 4. Policy evaluation

### Policy A — physical release Force

This is the recommended HH06 contract. It represents the hydrodynamic load already present in the exact 30.0 s fixed-cylinder CFD restart. It is compatible with the generic preCICE initialization API, but is not implementable/qualifiable yet because the numeric release Force and current Fluid adapter initialization path are both unverified. Once established, preCICE must carry the raw integrated Force in N and the existing Structure conversion must apply `F_strip=(F_raw/0.028)*1.98` exactly once.

### Policy B — zero fixed-point seed

Zero could be treated as an arbitrary numerical initial iterate only if the implicit first window demonstrably converges by its configured tolerance and the accepted solution is insensitive to reasonable alternate seeds. It is not the physical traction on the already-developed 30 s restart field. The migrated first-window qualification reports decreasing force residuals but zero displacement residuals and acceptance at the iteration cap rather than convergence; this does not demonstrate seed independence. Therefore Policy B is not accepted for the HH06 production release contract and must not be described as the physical release load. A synthetic seed remains valid for offline tests only when explicitly labelled as test data.

## 5. Offline tests required before any real FSI

These are a plan, not tests executed in this audit.

1. **Initial-data adapter fake:** use a deterministic fake Fluid participant that requires initial data; assert the expected Force vector is written after mesh definition and before Fluid `initialize()`, then assert Structure reads the same value after initialization and before its first ANCF solve.
2. **Force provenance and units:** bind the expected raw x/y/(z) value to the restart case identity, exact global time `30.0`, force patch `cylinder`, coordinate convention, source path/hash, and raw integrated N units. Assert the Structure input equals the qualified `/0.028 * 1.98` conversion exactly once. Do not seed this test from the 30.0002 s qualification sample.
3. **First-window identity:** assert F⁽⁰⁾ is tagged to the 30.0 s initial physical window, consumed once as the first trial input, and cannot be reused from another case, time, or prior window.
4. **Later-window read contract:** after each fake `advance()`, have the fake Fluid deliver a distinct Force iterate; assert `read_data(relativeReadTime=0.0)` returns that active window/iteration value, and assert rollback does not substitute a previous physical window's Force.
5. **Seed isolation:** label any fake zero or synthetic Force as `offline_test_seed`; assert it is never loaded from or written into `contract.json` as HH06 `Fx0_total_N`/`Fy0_total_N`.

## 6. Required scope to resolve the gate later

No implementation was performed here. After separate authorization, resolution requires:

1. Obtain or generate a reproducible raw integrated Force record from the exact `cases/hh06_single_slice/30/` fields at global time 30.0 s, preserving case/restart identity, patch, axes, units, and hash. If generation requires executing OpenFOAM post-processing, authorize that separately; it was not done in this phase.
2. Recover and pin the source/build provenance corresponding to the local Fluid adapter binary, then establish whether it can produce and write initial Force before preCICE initialization. If it cannot, make the smallest adapter-side change needed for that path.
3. If Policy A is implemented, add `initialize="yes"` to the Force exchange and implement the Fluid initial-data write. Extend the Structure path to read F⁽⁰⁾ after `initialize()` and before its first ANCF solve, using the existing force conversion unchanged.
4. Run the five offline tests above, including the fake test that separates the real release-force contract from a synthetic fixed-point seed.

This audit does not authorize Strategy C implementation, participant-order changes, adapter/XML/contract changes, or any OpenFOAM/preCICE/HH06 run.

## 7. Final answers

1. **Physical meaning of F⁽⁰⁾:** instantaneous integrated cylinder-wall traction in the exact 30.0 s fixed-cylinder restart state.
2. **Does exact 30 s Force evidence exist in V2?** No.
3. **Exact provenance/value?** Not available; no numeric release Force can be asserted.
4. **`Fx_raw/Fy_raw`:** unresolved at 30.0 s. The archived `(0.0644071321, 0.0590867509, 0) N` is a 30.0002 s later coupling sample, not F⁽⁰⁾.
5. **Sectional/strip values:** no release values can be calculated. The only valid rule remains `F_raw/0.028`, then `*1.98`, once; the later-sample values above are not release values.
6. **Can current Fluid supply Force before `initialize()`?** The preCICE 3.4.1 API allows it; current OpenFOAM adapter support is unresolved.
7. **Required integration:** Force exchange `initialize="yes"`, Fluid-side initial Force write before `initialize()`, and a Structure-side post-initialize/pre-solve read; adapter source change is conditional on the missing source audit.
8. **Is Policy A feasible?** Generic preCICE semantics support it; current HH06 path is not yet proven feasible end-to-end.
9. **Is Policy B acceptable?** No, not for the production physical-release contract; only as a clearly synthetic offline seed.
10. **Recommended policy:** Policy A, pending exact force provenance and adapter-path verification.
11. **Gate resolved?** No — `RELEASE_FORCE_VALUE_UNRESOLVED` (with Fluid initialization path also unresolved).
