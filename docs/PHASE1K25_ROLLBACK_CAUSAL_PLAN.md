# Phase 1K.25 — Rollback Causal Plan

Status: plan and controlled experimental design. Production source/configuration and the qualified historical adapter remain untouched.

## Objective and baseline

Phase 1K.24 established a same-process replay mismatch while two independent fresh-process replays were identical. The baseline values are:

```text
D* = (1.0633832164606064e-07, 9.530777190012017e-08) m
F1 = (0.0900359042326746, 0.056385514259487284) N
F2 = (0.1615021722747258, -0.021510905978815276) N
||F2-F1|| = 0.1057131957411209 N
```

The first candidate will change only field-history topology. No IQN, relaxation, timestep, solver, turbulence, mesh, RBF, or convergence setting will change.

## Causal groups

| Group | Exact observed/possible state | Owner / creation point | Current checkpoint status | Reconstructible/removable? | Expected impact |
|---|---|---|---|---|---|
| 1. Field time history | `U_0/U_0_0`, `k_0/k_0_0`, `omega_0/omega_0_0`, `Uf_0/Uf_0_0`; `oldTime()` topology and values | `GeometricField::oldTime()` in OpenFOAM; solver field registry | Current fields are discovered and copied; history is copied only if it already exists when checkpoint copies are made. Missing topology is not restored to absence. | Safely canonicalizable by `oldTime()` on existing fields; direct deletion is not selected because it is not a normal public lifecycle operation | Changes transient derivative/history inputs and objectRegistry topology used by the next solve |
| 2. ALE flux history | `meshPhi`, `meshPhi_0`, relation to `phi` | `fvMesh::movePoints()` demand-driven mesh-motion path | Mesh surface fields are checkpointed if present; no equivalent pre-motion `meshPhi` exists at the baseline S0 | Reconstructible only through legal mesh lifecycle; not removed in Group 1 | Changes geometric flux and ALE conservation terms |
| 3. `fvMesh` lifecycle | `moving`, `changing`, `V`, `V0`, `V00`, old points and geometry caches | `fvMesh::movePoints()` / `polyMesh::movePoints()` | points and old points are stored; source explicitly leaves V0/V00 setup incomplete; flags/private caches are not serialized | Must use legal mesh API or canonicalized scratch process; no private-flag hack | Changes geometry/volume history and mesh operators |
| 4. Turbulence runtime | turbulence model object and cached coefficients/state beyond `k/omega/nut` | RAS model construction and `correct()` in `pimpleFoam` | No object serialization; field proxies are checkpointed | Not directly removable/restorable through current adapter | Can change turbulence correction and Force even when fields match |
| 5. Ancillary registry | `yPlus`, forces function object state, other mutable registry objects | function-object list and objectRegistry during solver execution | Generic registered fields may be copied; arbitrary object state is not | Reconstructible by disabling/isolating diagnostic objects only, not yet tested | Can alter diagnostics or hidden field lifecycle; likely secondary to Group 1–3 |
| 6. RBF/motion caches | cached interpolation matrices/control-point state | RBF motion solver object | Not checkpointed by adapter; diagnostic RBF logs only | Not directly hashable; must be tested only if Groups 1–3 fail | Can change mesh displacement response |

## Exact current adapter path

In the experimental K20 source, `setupCheckpointing()` enumerates registered OpenFOAM geometric fields with `lookupClass<...>().sortedToc()`. `writeCheckpoint()` copies current fields and existing old-time levels. `readCheckpoint()` restores current values and only the old-time levels that exist on the live field and copy. It restores point displacement through the explicit K20 snapshot, then calls the diagnostic S1 hook.

`storeMeshPoints()` stores points and old points. Mesh flux/volume checkpoint setup is conditional on `mesh_.moving()`; `V0/V00` support is explicitly marked TODO in the source. `reloadMeshPoints()` uses the legal `fvMesh::move()` and `movePoints(meshPoints_)` path, which can create or update mesh lifecycle state.

## Candidate order

### Candidate G1 — field-history canonicalization only

Use a separately named diagnostic adapter. Before the first checkpoint, require the existing `U`, `k`, `omega`, and `Uf` fields and call the standard OpenFOAM `oldTime()` API twice for each. This creates `_0` and `_0_0` objects with values equal to the frozen current state. The operation is labelled `CANONICALIZED_INITIAL_STATE`, not exact restoration to the original fresh-process topology.

The candidate must record the topology and full hashes at S0 and S1. It must run:

1. canonicalized fresh A and B with one accepted branch;
2. one same-process retry replay with the same `D*`;
3. if same-process difference is below the coupling limit, a third same-process replay sample before stopping.

The fresh A/B values from K24 cannot be used as the candidate baseline because the topology and execution path have changed.

### Candidate G2 — ALE flux/history only

Run only if G1 is insufficient. Recreate the original K24 topology and change only the legal `meshPhi`/ALE-history handling. No G1 canonicalization may remain. The experiment must document whether it is restore, reconstruct, or canonicalize.

### Candidate G3 — `fvMesh` lifecycle only

Run only if G1 and G2 are insufficient. Use only public OpenFOAM APIs or an isolated reconstruction. Direct mutation of private `moving/changing` flags is forbidden.

### Groups G4–G6

Run only if G1–G3 do not restore repeatability. These groups require separate observability or object reconstruction; no serialization of the whole runtime will be attempted by default.

## Qualification gates per candidate

Every candidate must preserve the same frozen 30.0 s restart, `D*`, runtime identities, independent socket directories, and one physical window. It must produce:

- S0/S1 field and topology hashes;
- `F_A`, `F_B`, `||F_B-F_A||` for candidate fresh controls;
- `F1`, `F2` and, if required, `F3` for same-process replay;
- absolute/relative differences and ratio to `1e-3 N`;
- process cleanup and exact experimental binary identity.

A candidate is sufficient only if S0/S1 equality for the targeted group is restored, the same-process Force difference is below the coupling tolerance, and a third replay does not show accidental equality. Once that gate passes, stop; do not repair additional groups.

If Group 1 only lowers the mismatch but leaves it above tolerance, classify it as `GROUP1_CAUSALLY_CONTRIBUTES_BUT_NOT_SUFFICIENT`, discard it for the next isolated candidate, and do not stack Group 2 on top. If it does not materially change the result, classify it as `GROUP1_NOT_SUPPORTED_AS_DOMINANT_CAUSE`.

## Stop conditions

Stop immediately on a successful minimal candidate, a source/API safety blocker, any identity mismatch, any process failure, or any evidence that the candidate changes more than its declared state group. CFD inner-convergence A/B, IQN requalification, multi-window runs, and parameter tuning remain forbidden until same-process Fluid repeatability is re-established.
