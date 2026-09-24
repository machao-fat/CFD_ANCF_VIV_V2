# Phase 1K.15 — Fluid Displacement read-time contract audit

## Decision and boundary

**Classification: `DISPLACEMENT_READ_TIME_BUG_IDENTIFIED`.** The exact SHA-pinned Fluid adapter unconditionally passes `relativeReadTime=0.0` to its Displacement `Participant::readData` call after `advance()` while coupling continues. That is the current physical-window **start** sample, not the just-exchanged endpoint sample at `dt=0.0002 s` needed by the next implicit retry. This explains the all-zero first-window Fluid receive buffers measured in Phase 1K.14, despite nonzero Structure trial writes. The same unconditional zero is appropriate for a **completed, nonfinal** window's next-window start, but the adapter makes no retry/accepted distinction before this read. At the final window of the existing one-window diagnostic, it makes no post-advance read because coupling has ended.

This audit used only the installed preCICE 3.4.1 header, read-only disassembly/symbols of the qualified adapter, the existing Phase 1K.14 debugger log and Structure trace, and the earlier version-matched Phase 1E.5 read-time qualification. **No new debugger session, adapter modification/rebuild, FSI run, or parameter/configuration change was performed.** The previous failed Phase 1K.11 result and Phase 1K.13/1K.14 evidence remain unchanged.

## Binary identity and exact call chain

- Branch/HEAD at audit: `repair/worker-lineage-implicit-contract-v1` / `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`.
- Qualified adapter: `/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so`; SHA256 rechecked as `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572`. Its exact source-to-binary provenance is still unresolved. The conclusions below are specific to this binary, not to an assumed matching source snapshot.
- Phase 1K.14 external observer, **not rerun here**: `evidence/phase1k14_adapter_read/observe_after_read.gdb`, SHA256 `bc7ee3b33760be0146982701cd3bc740bebbfb989f9ace7d3cafbb02632042af`. It verified the loaded adapter path/SHA and logged the receive buffer immediately after each `Participant::readData` return. No new debugger script was created for Phase 1K.15.

Read-only `objdump -Cd` of that exact adapter establishes the argument path (ELF offsets; not portable to another build):

1. `preciceAdapter::Adapter::execute()` at `0xe7a80–0xe7a83` writes coupling data and calls `Adapter::advance()`.
2. At `0xe7a88–0xe7a92` it tests `isCouplingOngoing()`. If true, `0xe7af3` executes `pxor %xmm0,%xmm0`, making the double argument **exactly `0.0`**, and `0xe7af7` calls `Adapter::readCouplingData(double)`. There is no conditional retry offset on that call path.
3. Only **after** this read, `0xe7aff–0xe7b04` queries `requiresReadingCheckpoint()`; if true, `0xe7b08–0xe7b0b` invokes `readCheckpoint()`. Thus the adapter selects zero before it knows/branches on retry. When `isCouplingOngoing()` is false, the branch bypasses this read (as seen at the final window of Phase 1K.14).
4. `Adapter::readCouplingData(double)` at `0xd5765` preserves `%xmm0` in `%r14` and at `0xd577c–0xd5781` passes the identical bits in `%xmm0` to `Interface::readCouplingData(double)`; there is no offset calculation.
5. `Interface::readCouplingData(double)` at `0x5e369` saves that argument and at `0x5e41c–0x5e422` reloads it into `%xmm0` immediately before `precice::Participant::readData(...)`. That function then hands the receive buffer to the configured data reader. No later branch changes the read-time argument.

On x86-64 System V, the double parameter is carried in `%xmm0`; the two intermediate methods save/restore it unchanged. This is a static proof of the argument value for every invocation through the observed `execute()` path, **not** a claim that GDB logged `%xmm0` separately on each attempt. The Phase 1K.14 runtime breakpoint confirmed that the exact binary and this receive path were actually exercised and that each returned Displacement buffer contained 400 zero scalars.

## Attempt-level reconstruction from preserved runtime evidence

`case/system/preciceDict` in the Phase 1K.14 scratch case lists `readData (Displacement)` on the `Fluid-Mesh` face-center interface; `case/precice-config.xml` gives a 2-D vector and nearest-neighbor read mapping from `Structure-Mesh` to `Fluid-Mesh`, with `waveform-degree=0`, `substeps=false`. The debugger logged 400 scalar outputs per read, equivalent to **200 two-component vertices**. The preceding Structure writes and preCICE mapping events are ordered in `structure_trace.jsonl` and `fluid_gdb.stdout` under `evidence/phase1k14_adapter_read/run-20260924T111251Z-c2245ff/`.

| Fluid read after Structure attempt | Active window / next attempt | Mesh : data | Vertices | `relativeReadTime` passed by pinned adapter | Structure displacement just written (x, y) m | Read result |
| --- | --- | --- | ---: | ---: | --- | --- |
| 1 | window 1 / attempt 2 | `Fluid-Mesh : Displacement` | 200 | `0.0 s` | `(1.063383216e-7, 9.530777190e-8)` | 400/400 scalars zero |
| 2 | window 1 / attempt 3 | `Fluid-Mesh : Displacement` | 200 | `0.0 s` | `(1.461116944e-7, 9.150330746e-8)` | 400/400 scalars zero |
| 3 | window 1 / attempt 4 | `Fluid-Mesh : Displacement` | 200 | `0.0 s` | `(3.557155305e-7, 7.149606491e-8)` | 400/400 scalars zero |

This window had `dt=0.0002 s`, four Structure attempts and three retries. The final accepted attempt wrote `(3.267467624e-7, 7.424288000e-8) m`; preCICE completed its configured only window and the adapter performed **no fourth read**. Thus no accepted-boundary read value was measured in this run. Static code nevertheless proves that if a nonfinal accepted window leaves coupling ongoing, the same `0.0 s` argument is used. That is the appropriate next-window-start offset, but it is currently also used on retries.

## Version-matched read-time meaning and defect scope

Installed `/usr/include/precice/Participant.hpp` (preCICE 3.4.1), at its `readData` documentation around lines 841–866, defines `relativeReadTime=0` as current timestep/window start and `relativeReadTime=dt` as its endpoint. The existing Phase 1E.5 scratch qualification (`docs/PHASE1E5_PRECICE_FORCE_READ_TIME_DESIGN.md`, backed by `evidence/phase1e5_precice_force_read_timing/`) demonstrated in the same 3.4.1 implicit lifecycle that a retry's zero-offset read returns the stale start iterate, while `dt` returns the preceding advance's endpoint; after an accepted boundary, zero selects the new start and `dt` is not the desired sample. That experiment tested Force explicitly, not Fluid-side Displacement, so its role here is to corroborate the API timing rule, **not** to replace the direct Phase 1K.14 Displacement observation.

The current Fluid read sequence is therefore:

`write Structure D_trial → advance → preCICE maps Displacement endpoint → Fluid readData(Displacement, 0.0) → requiresReadingCheckpoint → rollback/retry`

For the first physical window, the start sample is zero, which matches the three measured zero receive buffers and the Phase 1K.13-B zero RBF boundary input. The required implicit-feedback design would select the just-exchanged endpoint (`dt`) **only on retry**, and the new-window start (`0`) **on an accepted, still-active boundary**. This is a read-time **contract finding**, not an implemented patch; the adapter's checkpoint and read ordering, initial data, and interface-field propagation need their own source/provenance-aware repair design before any code change. In particular, this audit does not prove that switching the offset alone will make `pointDisplacement` nonzero or make the ALE method stable.

**Stop condition reached.** No production or experimental binary was changed, no new FSI was launched, and no parameter was tuned. The next layer, if authorized, is a narrow design for a separately identifiable adapter read-time correction and offline/one-window verification; do not silently replace the pinned adapter or rerun the 25-window case.
