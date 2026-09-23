# Phase 1C.7B — Fluid Initial Force Initialization Capability Audit

**Classification:** `ADAPTER_SOURCE_UNRESOLVED`
**Branch / HEAD:** `repair/worker-lineage-implicit-contract-v1` / `51b598e5f8d16c6cb69625bb25ca0f07011a0931`
**Scope:** read-only audit of the OpenFOAM 10 / preCICE 3.4.1 Fluid adapter configuration, installed adapter binary, installed API, and available source provenance. No solver, preCICE, or HH06 runtime was started. No XML, adapter, source, or physical configuration was modified.

## Decision summary

The installed adapter binary contains a pre-initialize `requiresInitialData()` branch which calls its generic coupling-data writer before `Participant::initialize()`. The available v1.3.0 source candidate implements the corresponding Force writer by calculating pressure and viscous face forces from the OpenFOAM fields. OpenFOAM startup ordering makes the 30.0 s `p`, `U`, turbulence model, mesh, and patch geometry available before the adapter's initial-data hook would be called.

However, the source/build identity of the installed binary cannot be proven. The source candidate is not tied to this binary by a build manifest or reproducible build; migrated evidence also records that the candidate source could not be rebuilt against the current environment because of `faceTriangulation.H` incompatibility. Thus the binary-level generic hook and source-level Force calculation are evidence of capability, not proof that this exact configured Fluid runtime calculates and supplies the intended Force. The current XML does not request initial Force data in any case.

The required classification is therefore **`ADAPTER_SOURCE_UNRESOLVED`**. This does **not** establish that an adapter code change is required. The evidence suggests a Force-exchange `initialize="yes"` configuration may use an existing generic hook, but that configuration-only route cannot be certified until the exact source-to-binary lineage is resolved and the initial Force values are verified.

## 1. Frozen Phase 1C.7A evidence

F0 was frozen from the accepted Phase 1C.7A artifacts; this audit did not recalculate or alter it.

| Frozen item | SHA256 |
|---|---|
| `docs/PHASE1C7A_RELEASE_FORCE_RECOVERY_REPORT.md` | `6737908b9b29f4ff8550ba4353ff88ad90ad5cfc1355a57a885d655f7d3d7b3b` |
| `evidence/phase1c7a_release_force/provenance.json` | `1df1d2ca0876372874b1e6ac0eca2296e2f3ab8f8900e0b3903b53f2566e72d2` |
| `evidence/phase1c7a_release_force/release_force_result.json` | `6b272f695ebefe28daa176723483f611c42f8d25dbae8d83de928f3790811b8a` |
| `force_time30_run1.dat` and `force_time30_run2.dat` | `bafd3b57b2d0f236ef726a321f08562de92f288e2f43e00494529030c728cfdb` (both identical) |

The restart identity remains `cases/hh06_single_slice/30/`, case ID `ANCF_SINGLE_SLICE_HIGHRE_0P2S_PREP_V1`, global time 30.0 s, time index 150000, and `deltaT=0.0002 s`. The recorded `30/uniform/time` SHA256 is `44e3c62df2f2506cf283b85886f8ade0a6d34d1949c89091add862047ab27109`. Selected field hashes from the frozen result are `p=c33098b9634bf39ed09b184f5314aca388cce63063d9cc6c064b280167a78e05`, `U=a71a708e7bc12280ce60d0ad141c826ccd39e2100a0e98322cd0a7f53de3668a`, `k=eab8f52cc20f5a3aa6832cb6471df18a8119804827d532d72f44930377f37d3e`, `omega=cda71b08942c289ef7ae5b73aeb0e8390c5f5c2606706632d9d69d2b31d60c58`, and `nut=52a9ecad93f73cf84856eea748fa81884797b90d5628121a255b2e557704ef21`.

Frozen raw release force:

```text
Fx0_raw =  0.0655270406544 N
Fy0_raw =  0.05872987413554 N
Fz0_raw = -2.44420351566e-21 N
```

These are the exact patch-integrated force results from the Phase 1C.7A `forces(cylinder)` replays. The preCICE adapter's Force writer, as seen in the candidate source, writes per-face vector data; this audit did not establish that its mapped/integrated startup values numerically reproduce the frozen totals. That equality remains a separate provenance/unit regression requirement.

## 2. Current configured and resolved adapter binary

`cases/hh06_single_slice/system/controlDict` names `libpreciceAdapterFunctionObject.so`. In the sourced OpenFOAM-10 environment (`FOAM_USER_LIBBIN=/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib`), that soname resolves to:

```text
/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so
SHA256:   26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572
Size:     1,692,328 bytes
ELF:      64-bit LSB shared object, x86-64, dynamically linked, not stripped
Build ID: e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b
Compiler: GCC 11.4.0-1ubuntu1~22.04.3 (.comment section)
```

Its dynamic dependencies include OpenFOAM-10 libraries under `/opt/openfoam10/platforms/linux64GccDPInt32Opt/lib` and `/lib/x86_64-linux-gnu/libprecice.so.3`; the installed package/API version is preCICE 3.4.1. The binary has symbol tables but no `.debug` compilation/source sections. The library directory identifies the OpenFOAM platform configuration, but no exact build invocation or source manifest was found for this binary. The available adapter source uses OpenFOAM `wmake` (`Make/files` and `Make/options`), not CMake; those files do not establish which source tree produced this ELF.

The current `controlDict` resolution is verified, but no Fluid process was running during this audit (`ps -C pimpleFoam` returned no process). Therefore a live `/proc/<pid>/maps` observation was unavailable. The migrated `HH06_FLUID_ROLLBACK_STATE_AUDIT` records the same path, SHA256, and Build ID as the adapter identified in its historical runtime audit; it also explicitly says exact source/build linkage was not proven.

## 3. Available adapter source and lineage gap

There is no OpenFOAM-preCICE Fluid adapter implementation in the current V2 `src/` tree. The V2 `src/openfoam_adapter/ancfFileMotion.C/.H` files are a separate file-driven mesh-motion component.

For the provenance question only, the available external candidate was inspected read-only at:

```text
/mnt/d/研二文件/开题准备/CFD_ANCF_VIV/runtime/openfoam_adapter_v131_rollback_observability_source
Git HEAD: 3d45c38c5091331906bd32517b400d8cb0786bb1
Commit:   Update version and changelogs to v1.3.0
```

The candidate checkout is dirty, including line-ending changes; inspection of the committed Git HEAD (rather than treating that working tree as authoritative) gives these source hashes:

| Candidate committed file | SHA256 |
|---|---|
| `Adapter.C` | `3729eedf52e1be19e4f8047f67a440ea12687559ddf2a767217230fe40d850f6` |
| `Adapter.H` | `8dd5a481362402e9e930b34229d02e8071c0076505f9cb657d620e072c886544` |
| `Interface.C` | `c299015b4a9461802a1b378e78ebbfcb492a6c7f2046c8994c9d0dd9790661eb` |
| `FSI/Force.C` | `15365ed1c0a3366ef11844a7aefee4878ffa7994747e1351438abb16fdb1800e` |
| `FSI/ForceBase.C` | `035a429b3411ca22f70de338ec844113e876dbfcff9c9286952c019d61657ee7` |
| `Make/files` | `0663c20b3592336e8cdac398592c28f2bf37311d12ffa428a8afb4596ebef25f` |
| `Make/options` | `30d5d688be232d423eb898ca035c07f954736cf1199f5fc09ac9615f27ee2221` |

The candidate source shows a pre-initialize hook, but neither its commit nor its file hashes are embedded in the installed ELF or connected to the ELF by a trusted build record. Existing V2 evidence reports that a rebuild from the visible source did not produce a comparable binary because `faceTriangulation.H` was missing/incompatible. A separate isolated adapter binary with SHA256 `8c2c0fda85dc7ed452eb144b03a92ac9bf739e62ee8369baf489b3439cfdf458` is recorded in other qualification evidence; it is **not** the currently resolved `26ad...` library and is not substituted here.

Consequently the evidence chain is incomplete:

```text
candidate source / commit ──X──> installed binary SHA 26ad...
```

The classification remains `ADAPTER_SOURCE_UNRESOLVED`, even though the binary's symbols/disassembly reveal part of its behavior.

## 4. Lifecycle and force availability

### OpenFOAM startup state

Installed OpenFOAM-10 `pimpleFoam.C` creates the time and mesh, includes `createFields.H`, then validates the turbulence model before entering the time loop. In `createFields.H`, `p` and `U` are read from `runTime.timeName()` with `MUST_READ`; the viscosity and incompressible momentum-transport/turbulence model are then constructed. On the first `pimple.run(runTime)`, `Time::run()` starts the function-object list at the start time; `functionObjectList::start()` reads/constructs configured function objects. Therefore the exact 30.0 s solution fields, mesh, and cylinder patch geometry are available when an adapter initial-data hook is configured during startup. This establishes data availability, not that a force calculation was actually executed in this audit.

### Binary and candidate-source call paths

The installed ELF exports `preciceAdapter::Adapter::initialize()`, `writeCouplingData()`, `advance()`, and `execute()`, and imports the preCICE 3.4.1 `Participant::requiresInitialData()`, `initialize()`, and `writeData()` APIs. Disassembly of this exact binary's `Adapter::initialize()` shows:

```text
call Participant::requiresInitialData()
if true: call Adapter::writeCouplingData()
call Participant::initialize()
```

This proves that the installed binary has a generic conditional write-before-initialize path. It does not by itself prove the particular Force writer implementation behind `writeCouplingData()` is the candidate code below.

The candidate committed source maps that generic hook to Force as follows:

| Stage | Candidate source evidence |
|---|---|
| OpenFOAM function-object setup | `preciceAdapterFunctionObject::read()` calls `adapter_.configure()` (`preciceAdapterFunctionObject.C:88`); `Adapter::configure()` defines meshes/interfaces and calls `initialize()` (`Adapter.C:363-365`). |
| Initial-data check | `Adapter::initialize()` calls `requiresInitialData()`, then `writeCouplingData()`, then `initialize()` (`Adapter.C:541-557`). |
| Interface writer | `Interface::writeCouplingData()` invokes each configured writer, then `Participant::writeData()` (`Interface.C:558-580`). |
| Force writer | `FSI::Force::write()` calls `writeToBuffer()` (`FSI/Force.C:39-42`). `ForceBase::writeToBuffer()` reads pressure `p`, density, patch face vectors, and viscous stress derived from the registered turbulence model (`FSI/ForceBase.C:27-55, 133-184`). |
| Normal iteration | `Adapter::execute()` is called after the solver has solved its timestep; it calls `writeCouplingData()` and then `advance()` (`Adapter.C:413-435`). |

For the HH06 incompressible case, the current `preciceDict` declares `rho=1000`, `nu=1.13881e-6`, `nameForce Force`, a `cylinder` patch interface at `faceCenters`, `writeData (Force)`, and `readData (Displacement)`. The candidate writer calculates per-face pressure plus viscous force from those loaded fields. This differs from the separate `cylinderForces` post-processing function object: that object is configured for periodic output (`writeControl timeStep`, `writeInterval 5`), whereas the candidate adapter Force writer computes coupling values directly when called. The adapter calculation was not executed here, and equality against frozen F0 was not measured.

## 5. Current preCICE configuration and 3.4.1 contract

The current Force exchange is:

```xml
<exchange data="Force" mesh="Structure-Mesh" from="Fluid_0000" to="Structure_0000" substeps="false"/>
```

It has **no `initialize="yes"`**. The Displacement exchange is initialized, with Structure as its `from` participant. Thus current configuration requests initial Displacement from Structure, not initial Force from Fluid. The current configuration does not ask Fluid to provide physical `F0` before initialization.

The installed `/usr/include/precice/Participant.hpp` is from preCICE 3.4.1 and states:

- initial coupling values default to zero unless custom initial data is configured;
- after defining meshes, the participant checks `requiresInitialData()` and uses `writeData()` before calling `initialize()`;
- `requiresInitialData()` returns whether that participant must provide initial data to its defined vertices before `initialize()`;
- `initialize()` receives the first coupling data;
- `readData(..., relativeReadTime=0.0, ...)` reads at the beginning of the current timestep.

For Force, the participant responsible for supplying initialized data is the source participant `Fluid_0000`, if the Force exchange is configured for initialization. The receiving Structure participant can consume the initial Force only after its own `initialize()` has completed; the first-window read at relative time zero is the appropriate initial sample. This generic API contract does not prove the current OpenFOAM adapter's source-to-binary Force path.

Configuration implication: the Force exchange must request initialization (the expected schema form is `initialize="yes"`). The current adapter binary's generic pre-init hook suggests that this may be configuration-only for Fluid, but exact source/build matching is required before asserting that no adapter source change is needed. Structure must separately read the initialized Force after preCICE initialization and before its first ANCF trial; the adapter audit does not implement or qualify that Structure-side consumer.

## 6. Explicit answers

| Question | Finding |
|---|---|
| A. Can Fluid compute/read Force from the exact 30 s fields before its first coupling advance? | The fields, model, mesh, and patch geometry are loaded before the startup function-object configuration point. The candidate source calculates Force directly from them, and the installed binary has a generic pre-initialize writer hook. But source-to-binary matching is absent and no Force calculation was executed. **Potentially supported; not confirmed for the exact installed adapter.** |
| B. Does the Fluid adapter call `requiresInitialData()` and have a Force initial-data path? | **Binary:** yes, `requiresInitialData()` and a conditional generic `writeCouplingData()` before `initialize()` are confirmed by symbol/disassembly. **Candidate source:** its writer list includes Force and calculates values. **Exact binary Force-writer implementation:** unresolved. Current XML does not trigger initial Force writing. |
| C. Can it compute cylinder force before `initialize()`? | OpenFOAM state is available, and the candidate Force writer's pressure/viscous calculation can be called in that phase. Whether the installed binary contains that exact calculation and its numerical match to Phase 1C.7A's integrated `forces(cylinder)` result are **not proven**. |
| D. Does it currently only write Force after a CFD timestep? | Under the current XML there is no initial Force exchange. The candidate normal `execute()` path is invoked after a solver timestep has been solved and writes Force **before** that callback's `advance()`. No current-config initial Force write is requested. The exact runtime callback was not exercised in this audit. |
| Is XML `initialize="yes"` sufficient? | It is necessary to request initial Force. The installed binary has a compatible generic hook, so config-only is plausible, but cannot be certified without the matching source/build or an authorized targeted qualification. |
| Does this prove Strategy C can use the numeric F0 immediately? | No. It proves neither exact adapter force values nor the Structure participant's pre-first-solve read/application of F0. |

## 7. Minimal resolution work (not performed)

1. Resolve the installed binary's exact source and build invocation, or produce a clean, identified adapter build and designate it as the intended runtime binary.
2. In a separately authorized offline/targeted adapter test, enable initial Force exchange and observe that Fluid's initial writer runs between `requiresInitialData()` and `initialize()` using the time-30 loaded state.
3. Verify the per-face Force values and conservative mapping reproduce the frozen integrated release force, preserving pressure reference, density, axes, and the existing one-time force-unit chain.
4. Separately verify Structure reads that initial Force after `initialize()` and before the first ANCF solve. Only then can the Fluid initialization gate and end-to-end F0 contract be marked resolved.

No XML or adapter changes, build, OpenFOAM execution, preCICE initialization, or HH06/FSI runtime were performed in this audit.

## 8. Final status

- **Classification:** `ADAPTER_SOURCE_UNRESOLVED`
- **F0 numeric provenance:** resolved and frozen by Phase 1C.7A; unchanged here.
- **Generic preCICE initial-data API:** confirmed from installed preCICE 3.4.1 headers.
- **Installed binary generic pre-initialize hook:** confirmed by ELF symbols and disassembly.
- **Exact installed binary's Force writer source/build lineage:** unresolved.
- **Current Force exchange initialization:** not enabled.
- **Adapter source/configuration/physical parameter changes:** none.
- **Current V2 HEAD:** `51b598e5f8d16c6cb69625bb25ca0f07011a0931`.
- **Working-tree expectation:** prior Phase 1C.7A report/evidence remain untracked; this report is the only new audit artifact.
