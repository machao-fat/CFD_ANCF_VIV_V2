# Phase 1K.19 — `pointDisplacement` Checkpoint Restore Repair Design

**Status: DESIGN ONLY — no implementation or runtime qualification.**

## Scope and established defect

This design concerns the separately named **experimental** Fluid adapter used in Phase 1K.18.7B. It does not authorize replacing the historically qualified adapter. No build, OpenFOAM/preCICE/FSI run, or numerical/configuration change belongs to this phase. The source and observed failure are documented in `docs/PHASE1K18_8_POINTDISPLACEMENT_BOUNDARY_RESTORE_AUDIT.md`; the nonzero S0→S1 difference is confined to 400 cylinder `pointDisplacement` boundary entries, while its internal field, `cellDisplacement`, mesh points, and ANCF state match.

The current adapter uses whole-field `operator==` on **both** checkpoint save and restore (`evidence/phase1k18_6_point_mutation/run-20260924T141228Z-c2245ff/adapter-source/Adapter.C:1437–1450`, `:1267–1281`). In installed Foundation OpenFOAM 10, `GeometricField::operator==` delegates patch handling through `GeometricBoundaryField::operator==`; the `valuePointPatchField::operator==(const pointPatchField&)` overload writes `this->patchInternalField()` into the destination boundary array, not the source patch's stored values. Thus changing only the restore call is insufficient if the checkpoint copy was already corrupted at save.

## State and invariant

At physical-window checkpoint S0, keep separate snapshots of:

1. `pointDisplacement` primitive/internal vector field, **every** boundary patch's values and type, and the patch state needed for subsequent evaluation;
2. any existing `pointDisplacement` old-time levels that the adapter intends to roll back;
3. `cellDisplacement` staging field and its old-time levels, mesh points/mesh flux, CFD fields, physical time, and the Structure/ANCF physical state (their current owners remain unchanged).

The minimum acceptance invariant is **full-value identity**:

```text
S1 = immediately after Fluid rollback restoration,
     before the next preCICE readData(dt)

pointDisplacement(S1).internal       == pointDisplacement(S0).internal
pointDisplacement(S1).boundary[p]    == pointDisplacement(S0).boundary[p]
pointDisplacement(S1).patchType[p]   == pointDisplacement(S0).patchType[p]
for every patch p, including cylinder
cellDisplacement(S1)                 == cellDisplacement(S0)
meshPoints(S1)                       == meshPoints(S0)
```

`==` here means exact stored scalar-array identity/checksum under the same mesh and decomposition, not equality of only maximum norm. Mesh identity, patch ordering, patch sizes, and field dimensions must be checked before applying a snapshot; mismatch is a fail-closed error, not an interpolation opportunity. An internal value at a boundary point is *not* a substitute for the cylinder `fixedValue` patch's stored value. If additional patch-state flags affect later evaluation, they require explicit qualification even when array identity passes.

After S1, the normal retry reads the new absolute displacement at `relativeReadTime=dt`, updates adapter-owned `cellDisplacement`, interpolates to the cylinder `pointDisplacement` boundary, and lets the unchanged RBF solver call `correctBoundaryConditions()` and solve. A later accepted boundary still reads at offset `0`. The rejected trial must not become the next window's committed state. None of these coupling-order, RBF, or Structure semantics is changed by this design.

## Options

| Option | Save/restore design | `fixedValue` and RBF compatibility | Rollback and accepted/retry lifecycle | Risk/complexity |
|---|---|---|---|---|
| **A. Explicit complete point-field snapshot** | At **each** checkpoint save, copy live `pointDisplacement` internal array and each patch's actual stored values, patch type/size, and any relevant accessible patch state into an adapter-owned snapshot. On rollback, restore internal and patch arrays explicitly, **after** mesh-point restoration and **before** S1 or new `readData(dt)`. Avoid the current whole-field `operator==` for this point field on both save and restore. Include old-time levels if present. | Directly preserves the cylinder `fixedValue` value array that RBF reads. RBF's later `correctBoundaryConditions()` may propagate those values to internal patch points as usual; it must not be called between final restore and S1. Unchanged RBF input contract. | Strongest route to full S0==S1 and to a clean subsequent retry. Commit leaves accepted `pointDisplacement` in the live field; the next checkpoint captures that new value. No prior-window displacement is replayed. | More code and patch-type handling. Must validate exact patch types and OpenFOAM accessors; `pointPatchField::updated_` is private and cannot be assumed copied by a raw-array restore. Qualify subsequent `correctBoundaryConditions()` behavior; fail closed for unsupported stateful patch types. |
| **B. Restore internal field, then explicitly restore cylinder patch** | Retain current whole-field copy path, but at save separately capture the **live** cylinder boundary values; at restore, assign those saved values directly to the cylinder patch *after* the whole-field operation. This must bypass the fixed-value patch's disabled ordinary `operator=(Field)` and avoid its `operator==(const pointPatchField&)` fallback (the existing reader uses a `vectorField` reference for direct patch-value writes). | Satisfies the observed cylinder patch value requirement and keeps the RBF input interface. Does not change RBF settings. | May fix the measured S0→S1 cylinder difference for the current single patch. It cannot establish full-field identity if another patch differs, and it does not repair the save-side copy's boundary state or hidden patch state. Requires a full S0/S1 check and fail-closed handling of any remaining mismatch. | Smallest narrow change, but fragile/partial. It risks masking the general point-patch checkpoint gap. Not sufficient as a standalone *general* point-field rollback contract. |
| **C. OpenFOAM field/patch reconstruction or `reset()`** | Explore reconstructing/cloning a complete `pointVectorField` checkpoint and restoring with an OpenFOAM operation that demonstrably retains patch values and state. `GeometricField::reset()` delegates boundary handling to `GeometricBoundaryField::reset()` and patch `reset()`; this is an investigation candidate, not an approved drop-in replacement. | Could retain patch polymorphism if proven, but replacing registered field objects may invalidate references held by adapter reader and RBF solver. `valuePointPatchField::reset()` copies its value array; this alone does not prove private update flags, registry identity, old-time state, or mesh references are preserved. | Requires proof of same S0/S1 invariant and correct retry/accepted behavior. Avoid any operation that changes object identity or mesh ownership during rollback. | Potentially broad OpenFOAM lifecycle impact; higher uncertainty than explicit current-field restoration. Do not use merely because the API name sounds complete. |

OpenFOAM-10 source anchors: `GeometricField.C:1591–1607,1235–1250`; `GeometricBoundaryField.C:636–657,745–755`; `valuePointPatchField.C:145–185,239–266`; `fixedValuePointPatchField.H:124–129`; `pointPatchField.H:80–93,329–340`. The `fixedValue` patch's boundary value array is accessible, but `updated_` is private. The adapter's reader writes directly to the point-patch vector field after `readData(dt)` (`FSI/Displacement.C:158–207`), and RBF reads the corrected boundary values (`third_party/solids4foam_rbf/of10/RBFMeshMotionSolver.C:303–325`). These are source semantics, not a claim that any proposed replacement has been compiled or tested.

## Recommended implementation contract for later review

**Prefer A**, scoped to the experimental adapter's `pointDisplacement`, with explicit value snapshots and fail-closed patch/type/mesh checks. It addresses the save-side and restore-side uses of `operator==` together and permits an exact full-field S0/S1 comparison. Implement as an adapter-owned snapshot associated with the existing physical checkpoint; do not create a second independent physical-window clock or touch preCICE transport state. Keep the existing `cellDisplacement` and mesh checkpoint paths unless later tests show a separate defect. Do **not** change the historically qualified library, RBF solver, coupling XML, or physics as part of this design.

An implementation must decide how to handle patch bookkeeping and any existing old-time levels after inspecting the exact compile-time API. For the current HH06 `fixedValue` cylinder, a direct typed value-array copy is plausible; it is **not yet qualified** as preserving every OpenFOAM patch state. The safest implementation gate is: if it cannot preserve the state used by the subsequent `correctBoundaryConditions()` call, stop rather than declare S0/S1-value equality sufficient for all future retries. Option B may be a diagnostic minimal experiment, but not the final design unless full patch/internal and next-step invariants pass. Option C remains contingent on proof that registry references and field identity survive.

Conceptual sequence (not code to paste):

```text
checkpoint requested:
    snapshot live pointDisplacement internal + all patch values/types
    snapshot existing physical state using current owners
    verify snapshot matches the live S0 field, including cylinder boundary

rejected attempt / rollback:
    restore time, mesh state, cell/flow/ANCF physical checkpoint
    restore pointDisplacement internal + patch values (+ qualified old-time state)
    assert S1 == S0 for full point field and companion physical state
    only then readData(dt), update cellDisplacement and point boundary
    RBF correctBoundaryConditions() / solve on the new retry displacement

accepted attempt:
    do not restore rejected state; retain accepted point/mesh/CFD/ANCF state
    readData(0) for next-window starting displacement if coupling continues
    capture a new checkpoint only when requested for the next physical window
```

## Required later qualification (not run here)

1. **Save-copy integrity:** nonzero `fixedValue` cylinder boundary deliberately differs from its point internal values; saved snapshot matches the *live* S0 boundary exactly. This specifically catches the current save-side `operator==` defect.
2. **Nonzero rollback identity:** from a valid accepted nonzero state, capture full internal/boundary/patch-type checksums at S0 and S1; require exact identity for every patch, plus `cellDisplacement`, mesh points, CFD checkpoint, and ANCF physical state. Do not use a zero-release checkpoint as sole proof.
3. **Retry mutation timing:** only *after* S1, read `Displacement(dt)`, verify S2 reflects the new coupling iterate, and verify RBF receives it. `correctBoundaryConditions()` must not silently reintroduce the saved trial's old values.
4. **Accepted next-window handoff:** accepted `readData(0)` and new checkpoint carry the accepted nonzero displacement; a subsequent rejected trial restores that new S0 exactly, not the original 30.0-s release or an earlier rejected trial.
5. **Patch/old-time coverage:** check all current HH06 patch types, patch sizes, dimensions, old-time counts, and any additional patch state; unsupported types or topology changes fail closed. Include a repeated-retry case and compare both field values and subsequent RBF motion.
6. **Identity separation:** the patched adapter must have a separate name, SHA-256, Build ID, and evidence from the historically qualified adapter. No production adoption without a separately reviewed multi-window qualification.

No code was changed and no PASS for checkpoint restoration is claimed by this document.
