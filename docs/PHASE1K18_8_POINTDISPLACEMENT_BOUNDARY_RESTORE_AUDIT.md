# Phase 1K.18.8 — `pointDisplacement` Boundary Restore Source Audit

**Classification: `POINTFIELD_RESTORE_IMPLEMENTATION_GAP`**

## Boundary and evidence

This is a read-only source audit of the separately identified experimental Phase 1K.17/1K.18 diagnostic adapter, not of the historically qualified Fluid adapter. No runtime, build, configuration change, or new numerical experiment was performed. Repository HEAD during this audit: `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`. The source examined is `evidence/phase1k18_6_point_mutation/run-20260924T141228Z-c2245ff/adapter-source/Adapter.C` and `FSI/Displacement.C`, together with the installed Foundation OpenFOAM-10 source under `/opt/openfoam10/src/`.

The existing Phase 1K.18.7B S0/S1 snapshots are observational evidence: at the nonzero accepted checkpoint, 400 cylinder `pointDisplacement` boundary entries differ immediately after rollback (maximum vector difference `1.0513391307158744e-6 m`), while its internal field, the complete `cellDisplacement` field, mesh points, and ANCF `q/qdot/qddot` match. See `docs/PHASE1K18_7B_NONZERO_CHECKPOINT_LOCALIZATION.md` and `evidence/phase1k18_7b_nonzero_rollback/run-20260924T161017Z-c2245ff-bridge-session1/field_stage_metrics.json`. This audit explains the observed *source-level mechanism*; it does not claim a repaired or retested rollback.

## Exact checkpoint and rollback order

| Order | Source | Operation |
|---|---|---|
| 1 | `Adapter.C:323–440`, `:985–1021` | Construct the FSI interface/reader before checkpoint discovery. `setupCheckpointing()` enumerates registered volume fields, then point fields, including `pointVectorField`. |
| 2 | `Adapter.C:1076–1083`, `:1112–1119` | Register `volVectorField` and `pointVectorField` pointers and allocate full-field copies. `cellDisplacement` is adapter-owned; `pointDisplacement` is a mesh-registry point field looked up by the adapter reader (`FSI/Displacement.C:70–85`). |
| 3 | `Adapter.C:1374–1452` | `writeCheckpoint()` saves time, mesh points/mesh fields, volume fields, then point fields. **It updates each field copy using whole-field `operator==`, including the point-vector copy** (`:1437–1450`). S0 is captured after these copy operations (`:1452–1459`) but snapshots the *live* field, not the saved copy. |
| 4 | `Adapter.C:492–521`, `:1163–1184` | On a retry, `execute()` queries retry state and calls `readCheckpoint()`. That restores runtime time, then mesh points/mesh checkpoint fields (`reloadMeshPoints()`, `:872–899`). Mesh movement may invoke OpenFOAM mesh callbacks before point-field restore. |
| 5 | `Adapter.C:1190–1282` | Restore volume fields, then point fields. The live `pointVectorField` is assigned from its copy with whole-field `operator==` (`:1267–1281`), including conditional old-time levels. No explicit patch-value copy follows. |
| 6 | `Adapter.C:1352–1363`, `:549–566` | S1 is captured immediately after the field-restore loops. Only later does the retry call `readCouplingData(dt)` and capture S2. Thus the new preCICE displacement read cannot cause the S0→S1 difference. |

## The boundary-value overwrite

The relevant OpenFOAM-10 call chain is:

```text
Adapter::readCheckpoint(): live pointVectorField == saved pointVectorField
  -> GeometricField::operator==(tmp<GeometricField>)
       ref() = source internal field
       boundaryFieldRef() == source.boundaryField()
  -> GeometricBoundaryField::operator==(GeometricBoundaryField)
       destinationPatch == sourcePatch  [base pointPatchField reference]
  -> valuePointPatchField::operator==(const pointPatchField&)
       Field::operator=(this->patchInternalField())
```

Source locations: `/opt/openfoam10/src/OpenFOAM/fields/GeometricFields/GeometricField/GeometricField.C:1591–1607`; `/opt/openfoam10/src/OpenFOAM/fields/GeometricFields/GeometricField/GeometricBoundaryField.C:745–755`; `/opt/openfoam10/src/OpenFOAM/fields/pointPatchFields/basic/value/valuePointPatchField.C:249–256`. The `fixedValuePointPatchField` derives from `valuePointPatchField`; its own header disables ordinary assignment from a raw `Field`/value but does not override this `operator==` path (`.../basic/fixedValue/fixedValuePointPatchField.H:124–129`).

**The decisive operation is `valuePointPatchField::operator==(const pointPatchField&)`: it copies the destination's `patchInternalField()` into the destination boundary-value array, rather than copying the saved source patch-value array.** Since the whole-field operator first assigns the internal field, the cylinder boundary is replaced by values sampled from the restored internal field. At a nonzero moving boundary, these can differ from the separately stored `fixedValue` boundary values. This is an implementation gap in exact point-field checkpoint semantics; it is not evidence that preCICE sent the wrong displacement or that the RBF kernel modified S1.

The same whole-field `operator==` is used when updating the **checkpoint copy** at save time (`Adapter.C:1437–1450`). Therefore the saved copy's point-patch boundary may already be changed by this operator even though the S0 snapshot of the *live* field remains unchanged. At restore, the live field's boundary is explicitly recomputed from its internal values by the same operator. The existing S0/S1 snapshots bracket the operation but do not expose the saved copy's exact patch values between those two calls; no such values are fabricated here.

## Boundary condition and comparison with `cellDisplacement`

- The observed cylinder `pointDisplacement` patch is `fixedValue` (Phase 1K.18.7B snapshot). Its patch `value` array is distinct state from the geometric point field's primitive/internal array. OpenFOAM `valuePointPatchField::updateCoeffs()` and `evaluate()` set *internal* patch-point values from the boundary values (`valuePointPatchField.C:159–185`); they do not justify replacing the stored boundary values with `patchInternalField()` during rollback. `correctBoundaryConditions()` calls boundary evaluation (`GeometricField.C:1228–1233`).
- The RBF solver calls `pointDisplacement_.correctBoundaryConditions()` later in its solve (`third_party/solids4foam_rbf/of10/RBFMeshMotionSolver.C:305`). Existing S2→S3/S3→S4 snapshots independently show later field changes. This call occurs **after S1** in the captured retry and cannot be the first S0→S1 mutation.
- The adapter reader later updates the `cellDisplacement` cylinder face boundary from received coupling data, then interpolates face values onto the `pointDisplacement` cylinder patch (`FSI/Displacement.C:158–207`). This occurs at the later `readCouplingData(dt)`, after S1.
- For volume fields, `fvPatchField::operator==(const fvPatchField&)` copies the source patch field values (`/opt/openfoam10/src/finiteVolume/fields/fvPatchFields/fvPatchField/fvPatchField.C:423–430`). The point-field `valuePointPatchField` overload instead uses `this->patchInternalField()`. This source distinction is consistent with `cellDisplacement` matching exactly while only the point boundary differs. It does not imply all other patch types or old-time states have been qualified.

## Restore contract and limits

For an **exact** physical rollback of this HH06 RBF interface, the checkpoint must retain and restore both the point field's internal values and its cylinder `fixedValue` boundary-value array; merely restoring mesh coordinates, the cell staging field, or the point internal array is insufficient. Patch type/coefficients and any boundary-condition bookkeeping that affects subsequent evaluation must remain compatible with the saved state. The current source allocates full-field copies at registration, but its subsequent `operator==` save/restore path does **not** demonstrably preserve the point patch values; the installed OpenFOAM-10 implementation shows why. This report does not prescribe or implement a replacement assignment sequence or assert that all patch-state flags/old-time levels are already correct.

**Conclusion:** The earliest source-identified mutation of the *live* cylinder point boundary during S0→S1 is the point-vector restore line in `Adapter::readCheckpoint()`, through OpenFOAM's `valuePointPatchField::operator==(const pointPatchField&)`. The save-side use of the same operator is an additional copy-integrity concern. Mesh callbacks during earlier `reloadMeshPoints()` were not separately snapshotted, but no explicit `correctBoundaryConditions()` appears between the point-field restore and S1, and the restore operator itself has the exact boundary-overwrite behavior consistent with the measured boundary-only mismatch. An instrumented post-fix regression—not this read-only audit—would be required to qualify exact nonzero checkpoint restoration.
