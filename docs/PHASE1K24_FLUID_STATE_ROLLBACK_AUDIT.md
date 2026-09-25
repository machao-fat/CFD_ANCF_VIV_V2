# Phase 1K.24 — Fluid State Rollback Audit

Status: diagnostic-only forensic audit. No production case, qualified adapter, mesh, RBF configuration, or solver parameters were modified.

## Scope and identity

The audit started from the frozen 30.0 s new-mesh restart used by Phase 1K.22/K23. The diagnostic branch is `diagnostic/phase1k24-fluid-state-replay-v1` at `d3890deb0e609cc7e38e3f38ff6203787f889c07`. The separately built adapter was `libpreciceAdapterPhase1K24StateDiag.so`, SHA256 `3d75ae9fcebba444d8e21fa228fddc394e8748959d3b8ae340732fd21b3abd25`, Build ID `91e011c76e613a1a6b272f522afc4cf5b9cfccc7`. The qualified historical adapter was not loaded.

The source-level audit used the Phase 1K.20 experimental adapter source and the installed Foundation OpenFOAM 10 source/runtime. The adapter checkpoint implementation restores registered current fields and up to two `oldTime()` levels that exist in its checkpoint registry; it stores mesh points and old mesh points, and has the explicit Phase 1K.20 point-displacement snapshot. It does not make the whole OpenFOAM runtime state automatically transactional.

## Actual checkpoint path

The relevant lifecycle is:

1. `writeCheckpoint()` stores time and mesh points, copies registered volume/surface/point fields, and captures the explicit `pointDisplacement` snapshot.
2. Fluid advances through the OpenFOAM solver and mesh-motion path.
3. On retry, `readCheckpoint()` restores time, mesh points, registered field current values and available old-time copies, then restores the explicit point-displacement snapshot.
4. The adapter then reads retry displacement at `relativeReadTime=dt` and the solver proceeds with the next attempt.

OpenFOAM `pimpleFoam` creates and mutates solver fields, turbulence objects, mesh geometry, mesh fluxes and time-history objects during the solve. `fvMesh::movePoints()` can create or update mesh-volume and mesh-flux history when the time index advances. The adapter checkpoint is therefore not equivalent to a complete snapshot of every mutable OpenFOAM object unless each object is explicitly registered and restored.

## Rollback inventory

| Object / field | Exists in tested case? | Mutates during attempt? | Currently checkpointed by adapter? | Currently restored? | Hashable / observable? | Risk if incomplete |
|---|---:|---:|---:|---:|---:|---|
| `U` current | yes | yes | yes, registered volume field | yes | yes | next velocity solve starts from a different state |
| `p` current | yes | yes | yes | yes | yes | pressure/force map changes |
| `phi` current | yes | yes | yes, registered surface field | yes | yes | flux balance changes |
| `k`, `omega`, `nut` current | yes | yes | yes for registered fields | yes for current values | yes | turbulence state changes |
| `U.oldTime()` and older levels | created after first advance | yes | only if already present in registry/copy set | only for levels represented by the checkpoint | yes | transient history differs after retry |
| `k.oldTime()` / `omega.oldTime()` | created after first advance | yes | only if already present | observed after rollback, absent at S0 | yes | turbulence time history differs |
| `Uf` current/history | yes | yes | registered surface-vector field | current restored; history appears after rollback | yes | face-velocity history differs |
| `cellDisplacement` | yes, adapter-owned | yes | registered volume-vector field | yes | yes | ALE staging mismatch |
| `pointDisplacement` | yes | yes | yes, explicit Phase 1K.20 snapshot | yes | yes | RBF input mismatch; K20 repair addresses field values |
| mesh points / old mesh points | yes | yes | yes | yes | yes | geometry mismatch |
| `meshPhi` / mesh-flux history | absent at S0, created after motion | yes | not present at initial checkpoint; no complete pre-motion state | not equivalent to S0 | yes when present | ALE flux map differs |
| `V`, `V0`, `V00` | mesh volume history | yes/created by motion lifecycle | active source comments leave V0/V00 setup incomplete | not equivalent to S0 | proxy hashes only | geometric conservation/history differs |
| `Time` value/index | yes | yes | yes | yes | yes | wrong physical retry identity |
| `deltaT` | yes | solver-controlled | time contract retained; full solver ownership not independently snapshotted | not independently proven | scalar observable | different advance length |
| turbulence model object | yes | yes | not directly serialized as an object | not directly restored | not directly hashable | hidden model state can alter force |
| function-object mutable state | yes (`forces`, adapter, etc.) | yes | not generically serialized | not directly restored | not directly hashable | force output or adapter behavior can differ |
| RBF cached state | yes | yes/implementation-dependent | not directly serialized | not directly restored | not directly hashable; binary/log proxies only | mesh motion operator may differ |
| `fvMesh` internal caches | yes | yes | not fully serialized | not fully proven | only movement/volume proxies | ALE operator can differ |

## Read-only conclusion before runtime

The adapter contract proves restoration of the physical fields and geometry that K20 explicitly covered, but not complete OpenFOAM solver-owned history/runtime state. In particular, the source path does not establish a complete pre-motion snapshot for `V/V0/V00`, mesh flux history, field old-time allocation state, turbulence-object state, function-object state, or RBF/fvMesh caches.

This leaves the Phase 1K.23 same-process Force replay difference unresolved before instrumentation. It is not scientifically valid to label that difference as CFD inner-convergence error without first testing S0/S1 state equality.

## Evidence

The Phase 1K.24 run root is `evidence/phase1k24_fluid_state_repeatability/run-20260925T074500Z-d3890de/`. The runtime snapshot inventory, source-level checkpoint paths, and subsequent S0/S1 state hashes are recorded there. No repair attempt or parameter study was performed.
