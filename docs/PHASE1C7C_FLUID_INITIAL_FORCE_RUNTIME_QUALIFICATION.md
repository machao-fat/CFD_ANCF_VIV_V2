# Phase 1C.7C — Fluid Initial Force Runtime Qualification

**Classification:** `FLUID_INITIAL_FORCE_CONFIG_ONLY_CONFIRMED`

**Branch / HEAD:** `repair/worker-lineage-implicit-contract-v1` / `51b598e5f8d16c6cb69625bb25ca0f07011a0931`
**Scope:** exact installed OpenFOAM–preCICE adapter binary, scratch-only initial Force exchange, and a fake Structure participant. No Strategy C or production participant change was made.

## Result

For the tested installed adapter binary, the Fluid participant wrote the Force initial data before `Participant::initialize()`. A fake Structure participant then read Force immediately after its own `initialize()` using `relativeReadTime=0.0`. The received x/y values matched the frozen 30.0 s release force within `1e-8 N` in two independent scratch runs. No adapter source change was needed for this SHA-pinned binary; only the scratch XML Force exchange was enabled with `initialize="yes"`.

This qualifies the runtime behavior of the tested binary, **not** its source-to-binary reproducibility. The exact source commit/build recipe for the installed adapter remains unresolved. The result must not be generalized to another adapter binary.

## Frozen release state and identity

The F0 evidence was not recalculated or changed in this phase. The frozen source is `cases/hh06_single_slice/30/`, case ID `ANCF_SINGLE_SLICE_HIGHRE_0P2S_PREP_V1`, global time `30.0 s`, time index `150000`, and `deltaT=0.0002 s`.

```text
F0_raw = (0.0655270406544, 0.05872987413554,
          -2.44420351566e-21) N
```

The frozen result JSON SHA256 is `6b272f695ebefe28daa176723483f611c42f8d25dbae8d83de928f3790811b8a`; the Phase 1C.7A report SHA256 is `6737908b9b29f4ff8550ba4353ff88ad90ad5cfc1355a57a885d655f7d3d7b3b`. The current restart/configuration hashes for `p`, `U`, `k`, `omega`, `nut`, `uniform/time`, mesh `points`/`faces`, `controlDict`, `preciceDict`, and repository `precice-config.xml` match the frozen Phase 1C.7A values. Representative hashes and the frozen result identity are recorded in [qualification_result.json](../evidence/phase1c7c_initial_force_runtime/qualification_result.json).

## Runtime identity

The runtime trace reports OpenFOAM `10-c4cf895ad8fa` (`OpenFOAM-10`) and preCICE `3.4.1`. The adapter reported version `v1.3.0` and was loaded from:

```text
/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so
SHA256:   26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572
Build ID: e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b
```

The expected full adapter SHA matched. `/proc/<pid>/maps`, captured while the Fluid process was paused, confirms that this exact path was loaded. The mapped preCICE library was `/usr/lib/x86_64-linux-gnu/libprecice.so.3.4.1` (SHA256 `b20729622d2dbbafdea3d6ead0480ec66be98cb947db3500cc3c27ed4e3039c7`). The source commit/build invocation matching the adapter binary remains unknown; this audit deliberately does not infer it from the binary name or version string.

## Scratch test and observed call order

Two independent scratch copies used the exact V2 time-30 fields, mesh, `cylinder` patch, and Fluid `preciceDict`. The Fluid command in each run was:

```text
pimpleFoam -postProcess -case <scratch-case> -time 30
```

Only the scratch `precice-config.xml` changed: its Force exchange gained `initialize="yes"`, and its socket directory pointed inside that scratch root. The repository XML, `preciceDict`, contract, adapter source, and authoritative case were not changed. The Fluid process was instrumented and deliberately stopped at entry to `Adapter::execute()`, before the execute body or adapter `advance()` could run.

The captured runtime sequence was:

```text
Adapter::initialize()
  -> Participant::requiresInitialData()
  -> Adapter::writeCouplingData()
  -> FSI::Force::write()
  -> Participant::writeData(Force)
  -> Participant::initialize()
```

The Structure test participant wrote the configured synthetic initial Displacement before its `initialize()`, then immediately called `readData(Force, relativeReadTime=0.0)`. Its one vertex at `(0,0)` matches the actual HH06 structural coupling mesh: the current contract specifies one structure coupling vertex and the production participant constructs exactly `[(0.0, 0.0)]`. The fake did not run ANCF or advance a physical window.

The detailed GDB call trace and runtime maps for both runs, each scratch XML, the fake Structure source/binary, and preCICE Structure profiling output are preserved under [evidence/phase1c7c_initial_force_runtime](../evidence/phase1c7c_initial_force_runtime/).

## Force comparison and time identity

Both independent reads produced the same result:

| Quantity | Run 1 | Run 2 | Frozen release value / check |
|---|---:|---:|---:|
| Fluid field global release time | 30.0 s | 30.0 s | exact restart time |
| preCICE initial coupling time | 0.0 s | 0.0 s | first coupling sample |
| `relativeReadTime` | 0.0 s | 0.0 s | requested initial sample |
| `getMaxTimeStepSize()` | 0.00020000000000000001 s | 0.00020000000000000001 s | expected `deltaT=0.0002 s` |
| received `Fx` | 0.065527040654805538 N | 0.065527040654805538 N | frozen 0.0655270406544 N |
| received `Fy` | 0.058729874135090385 N | 0.058729874135090385 N | frozen 0.05872987413554 N |
| absolute `Fx` difference | 4.05538e-13 N | 4.05538e-13 N | tolerance `1e-8 N` |
| absolute `Fy` difference | 4.49615e-13 N | 4.49615e-13 N | tolerance `1e-8 N` |

The Force exchange is 2-D, so `Fz` is not transmitted. The frozen `Fz=-2.44420351566e-21 N` is negligible relative to the declared comparison tolerance; it was not replaced with a transmitted zero or used to rescale x/y. The received x/y values are the initial mapped Force at the actual one-point Structure mesh, and agree with the dimensional, patch-integrated `forces(cylinder)` release values. No additional force conversion was applied.

## Boundary verification

- Both Fluid startups loaded only the existing time-30 scratch fields; the traces show `Time = 30s` and no later time. No CFD timestep, mesh-motion step, or preCICE `advance()` was executed.
- The adapter was stopped at `Adapter::execute()` entry after initialization; its execute body was not run.
- No ANCF solve, real moving-structure FSI, or long OpenFOAM solve ran.
- The authoritative restart was not a run directory. Relevant authoritative input hashes still match the frozen Phase 1C.7A hashes; the only test configurations with `initialize="yes"` are preserved under the scratch evidence directory.
- No adapter source, repository XML, `preciceDict`, `contract.json`, physical parameter, or force scaling was changed.

## Gate decision

The Fluid initial Force path is **operationally confirmed for the exact adapter SHA above** using a configuration-only scratch change. Policy A (physical release Force as F0) is feasible through this runtime path. The separate source-to-binary provenance concern remains open, so this does not establish a reproducible adapter build or authorize applying the XML change to the production case. No production configuration change is authorized by this report.

**Final classification:** `FLUID_INITIAL_FORCE_CONFIG_ONLY_CONFIRMED`

**Adapter source commit/build lineage:** unresolved

**Production XML/configuration changed:** no
**Strategy C implemented:** no
