# Phase 1K.18.5 — `pointDisplacement` Checkpoint Lifecycle Audit

**Classification:** `ROLLBACK_ORDER_AUDITED` / `CHECKPOINT_REGISTRATION_UNRESOLVED` / `POINT_FIELD_CAUSE_UNRESOLVED`

## Scope and evidence identity

This is a read-only source-and-existing-evidence audit. No OpenFOAM or FSI runtime was repeated; no adapter or RBF library was rebuilt; no configuration or runtime evidence was changed.

The audited run is `evidence/phase1k18_adapter/run-20260924T121817Z-c2245ff/`, recorded at repository HEAD `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`. It loaded the experimental Phase 1K.17 adapter and Phase 1K.13-B diagnostic RBF library, not the historically qualified adapter/RBF binaries. The source inspected for call-order semantics is the corresponding migrated experimental adapter source at `evidence/phase1k17_adapter/experimental_source/`; RBF call sites were inspected in `evidence/phase1k13b_rbf_diag/build-20260924T105315Z-c2245ff/source/`.

The Phase 1K.18 report states that this run recorded only `cellDisplacement`/`pointDisplacement` maximum norms, mesh rollback delta, and old-time counts. It did **not** preserve full field snapshots, boundary arrays, internal-field values/checksums, or checkpoint-container contents. This audit does not reconstruct or calculate any of those missing data.

## Field ownership and checkpoint registration path

| State | Source-level owner/path | What the source shows |
|---|---|---|
| `cellDisplacement` | Experimental adapter's `FSI::Displacement` reader | `lookupOrCreateCellDisplacement()` finds the named `volVectorField` or constructs a zero-initialized length-dimension field, registers it in the mesh object registry, and returns it (`FSI/Displacement.C:17–67`). The `Displacement` reader binds this field in its constructor (`:70–84`). |
| `pointDisplacement` | OpenFOAM point field consumed by the RBF solver; adapter reader holds a registry lookup | The adapter reader looks up the configured `pointVectorField`; it does not create it (`FSI/Displacement.C:70–80`). During a face-centre displacement read it writes `cellDisplacement` boundary values and interpolates them onto the configured `pointDisplacement` patch (`:158–207`). |
| Mesh state | OpenFOAM dynamic mesh plus adapter checkpoint storage | `storeMeshPoints()` copies current and old mesh points and, for a moving mesh, sets up/stores mesh checkpoint fields (`Adapter.C:822–852`). The rollback path restores saved points and mesh checkpoint fields (`:854–888`). |

The adapter calls `initialize()`, reads initial coupling data at offset zero, then—if preCICE requests a checkpoint—calls `setupCheckpointing()` and `writeCheckpoint()` (`Adapter.C:414–436`). The displacement reader/interface has already been constructed by then (`:323–410`), and its constructor creates/registers the staging `cellDisplacement` field if it was absent (`FSI/Displacement.C:20–66`). The K18 log reports `PHASE1K17_CHECKPOINT_DISCOVERY cell=1 point=1` at startup. This proves both named objects were discoverable in the mesh registry at that point; it does not expose checkpoint-vector membership or copied values.

At source level, `setupCheckpointing()` iterates the mesh registry's sorted registered-field lists, including `volVectorField` and `pointVectorField`, and dispatches each object to `addCheckpointField()` (`Adapter.C:967–1005`). The corresponding add methods retain pointers and allocate field copies (`:1058–1065`, `:1094–1103`). `writeCheckpoint()` copies the current registered volume-vector and point-vector fields into those copies (`:1353–1425`). Thus the source is designed to include the staging field and point field if each appears in the respective registry enumeration. The K18 runtime evidence does not log the actual names or membership of those checkpoint vectors, so actual per-field registration for that run remains unverified.

## Rollback and retry call order

The experimental adapter's `execute()` follows this order (`Adapter.C:485–550`):

1. Write coupling data, then call preCICE `advance()`.
2. Query `requiresReadingCheckpoint()` and time-window completion.
3. On retry, emit the `before_rollback` max-norm trace and call `readCheckpoint()`.
4. `readCheckpoint()` restores runtime time, then calls `reloadMeshPoints()` before restoring registered volume fields and then registered point fields (`:1145–1264`).
5. The point-vector restore uses whole-field assignment from the saved copy; old-time values are restored only when `nOldTimes() >= 1` (`:1249–1264`).
6. Emit the `after_rollback` trace after the field-restore loops (`:1334–1340`).
7. Later in the callback, for a continuing coupling, read displacement data at the selected offset. On retry that is the completed-step endpoint (`:540–550`); the displacement reader writes the staging field and interpolates the point boundary values (`FSI/Displacement.C:158–207`).
8. The next RBF solve calls `pointDisplacement_.correctBoundaryConditions()` before collecting moving control-point values (`RBFMeshMotionSolver.C:303–370`). It then interpolates mesh motion and assigns its interpolated values to the point field's primitive/internal field (`:980–1006`).

For completeness, a new checkpoint is written when preCICE requests it (`Adapter.C:507–511`); `writeCheckpoint()` stores time and mesh state before copying registered fields (`:1353–1425`). The trace helper itself only calculates cylinder-patch maximum norms and maximum mesh-point delta against saved points (`Adapter.C:13–59`).

This establishes source call order. It does not establish the exact per-entry effects of OpenFOAM field assignment, boundary-condition evaluation, or dynamic-mesh callbacks in the K18 runtime because full arrays and serialized checkpoint contents were not captured.

## Possible `pointDisplacement` mutation points

| Operation | Source-observed role | What can and cannot be concluded |
|---|---|---|
| Checkpoint save/restore | Copies registered `pointVectorField` objects and later assigns the saved copy back (`Adapter.C:1094–1103`, `:1416–1420`, `:1249–1264`). | A source-level restore path exists. Without the runtime checkpoint-vector membership and full before/after values, the K18 evidence cannot prove that every point-field component/patch value was captured and restored identically. |
| Mesh rollback | Calls `move()` and `movePoints(savedPoints)`, then restores mesh checkpoint fields (`Adapter.C:854–888`). | This directly restores mesh point coordinates in the adapter path. K18's zero mesh delta is consistent with that observation, but does not establish `pointDisplacement` identity. |
| `correctBoundaryConditions()` | Called by RBF `solve()` before moving-control extraction (`RBFMeshMotionSolver.C:303–370`). | This is a possible later boundary-field mutation/evaluation point. The adapter's `readCheckpoint()` source does not explicitly call `correctBoundaryConditions()` after restoring point fields. K18 logs do not snapshot the point field immediately before/after this call, so it cannot be identified as the cause. |
| Adapter displacement read/interpolation | Writes received face data into `cellDisplacement` and assigns face-to-point interpolation results to the point patch (`FSI/Displacement.C:158–207`). | This is an explicit point-boundary update after the rollback trace in the retry callback. It can make the field differ from the checkpoint after new coupling data is consumed; the existing max-only log does not distinguish this from a difference already present immediately after restore. |
| RBF solve | Reads corrected moving-patch values as controls, interpolates mesh-point motion, and writes the interpolated field's primitive values (`RBFMeshMotionSolver.C:316–370`, `:980–1006`). | It is a further field/motion update path. The K18 evidence confirms RBF motion occurred generally, but it does not provide full `pointDisplacement` state at this stage for comparison with the checkpoint. |

## What the existing K18 run proves

The K18 report and `fluid.stdout` show that:

- `cellDisplacement` and `pointDisplacement` were discoverable at checkpoint setup; the log does not enumerate checkpoint container contents.
- For window 1, the recorded rollback maximum norms returned to zero and mesh delta was zero.
- For window 2, the checkpoint-written cylinder maxima were `cell=5.8069976555299806e-7 m` and `point=5.8069976555299827e-7 m`. After rollback, the cell maximum matched the recorded checkpoint maximum and the mesh delta was zero, while the point maximum was `5.8280844460221839e-7 m`.
- These are scalar maxima, not full-field identity tests. They cannot show whether the difference is in boundary or internal values, which points/components differ, whether the checkpoint copy itself differed, or when in the sequence any difference arose.
- The trace reported `cell_old_times=0` and `point_old_times=0`. In this run, the source's conditional old-time restore therefore had no old-time levels to restore; this does not establish whether old-time state would be required under another runtime state.

The observed point maximum discrepancy is retained as reported in the K18 evidence; no new checksum or per-entry delta has been computed.

## Audit conclusion

- **Rollback ordering:** audited from the experimental adapter source. Mesh/time restoration precedes registered field restoration; point fields are assigned from copies; the `after_rollback` max-norm trace follows these restore loops; the next displacement read and later RBF boundary correction are subsequent possible mutation points.
- **Checkpoint registration:** unresolved for the actual K18 run. Source enumeration and registry discovery are visible, but runtime logs do not prove that the named point field was present in the checkpoint vector or expose its saved snapshot. The cell staging field has the same runtime-membership evidence limitation.
- **Point-field cause:** unresolved. The K18 max-norm and mesh-delta evidence cannot distinguish incomplete checkpoint registration/restore from a subsequent field update or boundary/RBF-related mutation. No cause A–D is assigned.

Further discrimination requires a separately authorized instrumented runtime that captures full `pointDisplacement` boundary/internal state at checkpoint save, immediately after restore, after adapter displacement read, and around RBF boundary correction/solve. This report does not perform or authorize that runtime.
