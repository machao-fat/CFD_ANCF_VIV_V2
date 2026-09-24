# Phase 1K.14 — Fluid adapter displacement read audit

## Decision

**Classification: `PRECICE_DISPLACEMENT_NOT_RECEIVED` at the qualified Fluid adapter's observed `Participant::readData` return.** In one isolated physical window, Structure wrote nonzero trial displacement on each of four coupling attempts. Immediately after the exact qualified Fluid adapter called `precice::Participant::readData` for its configured `Displacement` exchange, the adapter's 200 two-component receive vectors were **all zero** on each of the three retry reads. Those zero values were present *before* `preciceAdapter::FSI::Displacement::read` could assign them to an OpenFOAM field. This extends Phase 1K.13-B's zero RBF-input finding one step upstream.

The classification describes the **observed read result**, not a proven defect in preCICE mapping or transport. The adapter's `relativeReadTime` argument and the exact mapped-value lifecycle were not captured; a stale window-start read is one possible explanation, not an established root cause. The final accepted Structure write has no subsequent Fluid read in this deliberately one-window run. Neither a new adapter binary nor a production fix was made.

## Boundaries and identity

- Branch/HEAD: `repair/worker-lineage-implicit-contract-v1` / `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`.
- Qualified adapter, **unchanged**: `/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so`, SHA256 `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572`, Build ID `e76f7d6491a2f32cf9d6d5712c79b1ce55cd862b`. GDB independently checked the actually loaded absolute path and full SHA at its first adapter breakpoint. Adapter source-to-binary provenance is still unresolved.
- Qualified RBF library, **unchanged**: SHA256 `b27b347c4ba3026a495517ae7ae237ceb5cd8408ac0db9af6a58ccd83647a20c`. This run did **not** use the Phase 1K.13-B experimental RBF library.
- Diagnostic identity: external GDB 12.1 script `evidence/phase1k14_adapter_read/observe_after_read.gdb`, SHA256 `bc7ee3b33760be0146982701cd3bc740bebbfb989f9ace7d3cafbb02632042af`. It is a debugger script, **not** an adapter build. No installed `.so`, production source, mesh, RBF source, or production configuration was modified.
- Scratch run: `evidence/phase1k14_adapter_read/run-20260924T111251Z-c2245ff/`. Its `30/` restart and `constant/polyMesh/` were compared byte-for-byte with the preserved, unadvanced Phase 1K.11 mapped new-mesh source before launch; F0 source-result SHA256 remained `ce2cbf6edcda28ae46bf3d0a10b2a6d75ec8641b8417549818acda9c98369949`.
- The scratch-only XML changed only the exchange-directory and `max-time-windows` to `1`; dt, IQN-ILS, convergence settings, min/max iterations and all physical settings remained unchanged. Installed `precice-config-validate` reported no major issue, and the Structure offline contract audit had no blocking check. As in Phase 1K.13-B, the current Structure CLI's HH06 guard requires `--max-windows 25`; the validated preCICE XML's `max-time-windows=1` was the actual one-window stop. The Fluid log confirms `final time-window: 1, final time: 0.0002` and Structure reports `accepted_windows: 1`. This CLI/XML dual bound is recorded rather than concealed.

## Observation method and validity check

1. Existing Fluid/preCICE logs were checked first. They report `Mapping "Displacement"` after each exchange and a read-data profiling event, but no numerical vector payload. They cannot answer A versus B alone.
2. The exact adapter's exported symbol and read-only disassembly were checked. Within `preciceAdapter::Interface::readCouplingData(double)`, the call to `precice::Participant::readData(...)` is at function offset `+0xd2` (absolute ELF offset `0x5e422`); its next instruction is `+0xd7` (`0x5e427`). Before that call the adapter puts the receive-buffer pointer in callee-saved register `r14` and the scalar count in `r15`. Immediately after return, it passes the **same** buffer from its coupling-data object to the virtual displacement-field reader (`0x5e438` through `0x5e43f`). These addresses are valid only for the recorded adapter SHA, not an arbitrary rebuild.
3. The external GDB script set an entry breakpoint on this qualified adapter method, verified the loaded path and SHA, then placed a second breakpoint at `entry+0xd7`. It read the buffer in the inferior **after `Participant::readData` returned and before the field-reader call**. It printed one `K14_READ_JSON` record per read, with scalar count, first values, finite check, nonzero count and x/y extrema. It did not write to inferior memory or change an adapter instruction. The script itself is separately SHA-pinned; running under a debugger can alter wall-clock timing, so this is diagnostic evidence, not a performance comparison.
4. `system/preciceDict` configures this interface's only read data as `Displacement`, with 200 cylinder face-center vertices in two dimensions. The observed buffer size is 400 doubles, consistent with that contract. No other read-data name is configured for the Fluid interface.

## One-window attempt timeline

| Structure attempt | `D_written_to_precice` x/y (m) | preCICE Fluid-side event | Buffer after Fluid `readData` | Structure outcome |
| ---: | --- | --- | --- | --- |
| 1 | `(1.063383216e-7, 9.530777190e-8)` | `Mapping "Displacement" for t=0.0002`; then Fluid read #1 | 400/400 scalars zero; max vector norm 0 | rollback |
| 2 | `(1.461116944e-7, 9.150330746e-8)` | same-time mapping; then Fluid read #2 | 400/400 scalars zero; max vector norm 0 | rollback |
| 3 | `(3.557155305e-7, 7.149606491e-8)` | same-time mapping; then Fluid read #3 | 400/400 scalars zero; max vector norm 0 | rollback |
| 4 | `(3.267467624e-7, 7.424288000e-8)` | final mapping at completed window | **No subsequent read in this one-window run** | accepted before cap |

The mapping/read ordering is recorded in the combined `fluid_gdb.stdout`; `structure_trace.jsonl` supplies the actual written values and rollback outcomes. The Fluid read records contain 200 2-D vectors each, all finite and all exactly zero, not merely a zero average or a zero first sample. The debugger confirmed it was attached to the exact pinned adapter. The Structure and Fluid both exited cleanly with code 0; the GDB inferior exited normally. A debugger warning about disabling a breakpoint when the shared library unloaded at normal shutdown is not a participant failure. No orphan Fluid, Structure or worker was observed afterward.

## Interpretation and next causal layer

Alternative **A** (“Fluid `readData` receives nonzero displacement but adapter fails to pass it to `pointDisplacement`”) is **not supported for these three observed retry reads**: the buffer was already zero immediately after preCICE returned. Alternative **B** is supported in the narrow observable sense: **the Fluid adapter received a zero buffer from its current `readData` calls despite nonzero Structure writes and mapping events**. This does not prove preCICE failed to transport the nonzero endpoint sample; reading a different relative time may return zero legitimately. Alternative **C** (“observation impossible”) is false for this pinned binary and this run.

The remaining question is the actual `relativeReadTime` passed by the qualified Fluid adapter on retries and whether it requests the window start (`0`) or the just-written endpoint (`dt`). Establishing that contract, and then locating any field-propagation issue if a nonzero read is obtained, requires a **separately authorized** design/observation phase. No adapter edit, second real run, coupling tuning, mesh change or production adoption follows from this audit.

Primary artifacts: `fluid_gdb.stdout` (mapping and numeric read chronology), `fluid_gdb.stderr`, `structure_trace.jsonl`, `structure.stdout`, scratch `precice-config.xml`, external debugger script, and `read_audit_summary.json`. Historical Phase 1K.11 and Phase 1K.13-B evidence was not overwritten. This report and its evidence remain uncommitted pending review.
