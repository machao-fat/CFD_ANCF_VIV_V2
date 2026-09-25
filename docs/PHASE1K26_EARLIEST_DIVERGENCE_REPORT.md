# Phase 1K.26 — Earliest Fluid replay divergence

Classification: **EARLIEST_DIVERGENCE_LOCALIZED_CAUSE_UNRESOLVED**.

This is a one-physical-window diagnostic, not a rollback repair or an FSI
convergence qualification. The first confirmed same-*Fluid-input* pair of
attempts diverges in `meshPhi`/`meshPhi_0` **immediately after rollback**, before
the next displacement read or RBF/mesh move. Zeroing only that ALE-flux state
removes the measured solver-stage difference and reduces, but does not remove,
the difference in Force received by Structure. The unaccelerated per-attempt
Fluid Force was **NOT MEASURED**; therefore this evidence cannot claim complete
Fluid-operator repeatability or a sufficient repair.

## Provenance and boundary

- K23–K25 diagnostic checkpoint commit:
  `4182ac91a08b16edd5982a34cd22dbfa050c7fae` on
  `diagnostic/phase1k26-earliest-fluid-replay-divergence-v1`.
- Frozen source: the K22/K23 30.0 s new-mesh restart copied independently into
  four scratch runs. Each child `runtime_identity.json` and
  `restart_identity.json` records field, mesh, XML, and configuration hashes.
- Baseline experimental adapter: `libpreciceAdapterPhase1K24StateDiag.so`,
  SHA256 `3d75ae9fcebba444d8e21fa228fddc394e8748959d3b8ae340732fd21b3abd25`.
  It is **not** the historical qualified production adapter.
- Single selected causal intervention: the previously isolated K25 G2
  `libpreciceAdapterPhase1K25G2Diag.so`, SHA256
  `f9a89b21b0a0fe92f297a0c8bceb67bc5df5f52e5f7a9c35fa17df5b7eb8b754`.
  Its source zeroes `meshPhi` current/old-time values after rollback; it does
  not restore `fvMesh` topology or change solver, mesh, RBF, or physics.
- Diagnostic RBF library SHA256
  `508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11`;
  worker binary SHA256
  `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`.
- Isolated stage-tracing `pimpleFoamPhase1K26Diag` SHA256
  `e895e5f1788146da2205e4c8bb0b959f99f66e426c92dc7233d7ac303fd91e96`,
  ELF Build ID `d90b0192dae597213503399aaeb4f04a375378a1`.
  The solver hooks hash state without changing the governing equations.
- All four runs used the same `D*=(1.0633832164606064e-7,
  9.530777190012017e-8) m`, `dt=0.0002 s`, one physical window,
  `min-iterations=2`, and a **diagnostic-only** four-attempt ceiling. The
  preCICE acceleration and convergence settings were not tuned. Cap acceptance
  is **not** convergence.
- No production adapter/case/configuration, ANCF, IQN settings, RBF parameters,
  turbulence, or solver numerics were modified. No second physical window ran.

Run root:
`evidence/phase1k26_earliest_divergence/run-20260925T-phase1k26-4182ac9/`.
Children are `same_process/`, `fresh_A/`, `fresh_B/`, and
`selected_causal_test_G2/`. Each has Fluid/Structure logs, stage traces,
runtime/restart identity, validation output, and `process_cleanup.json`.
All eight participant processes exited with code 0, with no recorded stop
reason. The Phase 1K.26 raw runtime trees remain ignored under the repository
evidence policy, not deleted.

## Why the K23/K24 F1/F2 comparison is not a same-Fluid-input replay

The fake Structure wrote `D*` on every attempt, but preCICE's initialized
Displacement and acceleration/read lifecycle did **not** deliver the same
value to Fluid on attempts 1 and 2:

| Attempt | Fluid read offset | Adapter received maximum scalar | Cylinder `cellDisplacement` maximum norm |
|---:|---:|---:|---:|
| 1 | `0` initially | `0` | `0` |
| 2 | `dt` on retry | `2.1267664329212128e-8 m` | `2.8559698902520933e-8 m` |
| 3 | `dt` on retry | `1.0633832164606064e-7 m` | `1.4279849451260464e-7 m` |
| 4 | `dt` on retry | `1.0633832164606064e-7 m` | `1.4279849451260464e-7 m` |

The original K24 `F1 != F2` (`0.1057131957411209 N`) therefore cannot **by
itself** establish nonrepeatability of `G(S0,D*)`: the Fluid inputs differ.
This does not invalidate K24's independently observed rollback-state inventory
mismatch. It limits the causal interpretation of its first two Force values
and of K25 candidates judged only against those values.

Attempts **3 and 4** are the valid observed same-Fluid-input comparison in
this one-window trace. Their full `cellDisplacement` and RBF diagnostic
`pointDisplacement` arrays match. The RBF candidate point arrays from motion
calls 5 and 7 also match exactly; the mesh point hashes match. The read branch,
time identity, and physical window match. This pair is a diagnostic test of
replay after successive rollbacks, not a proof that all hidden runtime state
returned to the original fresh-process `S0`.

## Earliest divergence and propagation

The adapter's post-rollback snapshots for retries 2 and 3 (the states feeding
attempts 3 and 4) differ first at **S00**, before retry `readData(dt)`:

| Object group at S00 | Attempts 3 vs 4 |
|---|---|
| `U`, `p`, `k`, `omega`, `nut` current/history inventory | equal in recorded snapshot |
| `phi`, `Uf`, point/cell displacement, mesh points/flags | equal in recorded snapshot |
| `meshPhi` and `meshPhi_0` | **different** |

At solver `S01`, before `mesh.move()`, `meshPhi` hash is
`422b4d116dc898dd` versus `1886d01a8df51f94`; its recorded maximum is
`1.6121653031358853e-8` versus `8.060826515328194e-8`. The old-time hashes
are `50ff2e67a182aca0` versus `21a039f29be94615`. At adapter S00, the
separately registered `meshPhi_0` current hashes are `70d4e303d9aac83b`
versus `6c230b4d99322d01`. All other recorded S01 field hashes, physical
time/index, displacement input, mesh points, and
current volume hash agree. Stage trace records full internal and boundary
values for conventional volume/surface fields; the point-field solver hook
uses a `patchInternalField` proxy. Full point-boundary values are available
separately in the RBF diagnostic JSON.

After `mesh.move()`, stage `S04` first shows `U` and `phi` divergence as well
as the pre-existing `meshPhi` divergence; subsequent momentum/pressure stages
propagate differences into `p`, `Uf`, and finally turbulence fields. That
ordering **does not** support turbulence or RBF cache as the *first* cause.
It does not prove these subsystems have no other defects.

The observed Structure-received (preCICE exchanged/accelerated) Force was:

| Attempt | Fx (N) | Fy (N) |
|---:|---:|---:|
| 3 | `0.10674012020107931` | `-0.03899730797417809` |
| 4 | `0.06173208299132629` | `-0.07937302508219088` |

Its attempt-3/4 difference norm is `0.060464220374208 N`.

## Fresh-process trajectory oracle

Fresh A and Fresh B each started from a distinct scratch copy of the same
frozen 30.0 s state, with independent processes and socket directories. Their
four-attempt received-Force sequences are identical componentwise. All **60**
corresponding solver stage JSON records compare exactly after excluding the
expected PID difference. Thus the full **four-attempt branch-equivalent
trajectory** is reproducible across fresh processes. This does not make
attempts 1 and 2 a same-input pair within either process.

## Selected single-subsystem causal test: G2 ALE flux canonicalization

The only selected intervention was K25's already-built G2 experimental
adapter, run again from a new frozen-restart scratch copy with the same
stage-tracing solver. It zeroes current/old-time `meshPhi` after rollback.
No G4/G6 reconstruction, PIMPLE change, or acceleration change was performed.

For attempts 3 and 4 in the G2 run, the S00 `meshPhi`/`meshPhi_0` snapshot
entries match. Every one of the **15** corresponding solver stage records
matches, including RBF/mesh, momentum, pressure, turbulence, and `S11` just
before the adapter force write. The Structure-received Force remains different:

| G2 attempt | Fx (N) | Fy (N) |
|---:|---:|---:|
| 3 | `0.11051428672025433` | `-0.03561152033583504` |
| 4 | `0.09659825039505082` | `-0.04809509323023877` |

The difference is `0.018694803000146195 N`: approximately **69.1% lower**
than baseline, but still **18.7 times** the `1e-3 N` absolute Force criterion.
This supports a causal contribution from the ALE-flux state to the *received
Force sequence* under this branch. It is **not** a sufficient rollback repair.
The fact that the recorded G2 solver fields match through `S11` while
received Force differs means an unobserved `S12` force-calculation/exchange/
acceleration state remains a live explanation. It would be unsound to label
the residual `0.01869 N` as an unrepeatable *direct OpenFOAM* force: the
per-attempt direct patch-integrated Force and adapter's unaccelerated outgoing
Force were **NOT MEASURED**. preCICE's convergence/iterations logs and
participant stdout are preserved, but preCICE-received Force is not identical
by definition to the raw Fluid operator output under IQN acceleration.

## Required answers and gates

1. **Earliest divergence:** `S00`, after rollback restore and before the next
   `readData(dt)`; confirmed again at solver `S01` before `mesh.move()`.
2. **First objects:** `meshPhi` and `meshPhi_0` surface-scalar ALE history.
   The first solver-stage `meshPhi` hashes and maxima are above.
3. **Region:** `ALE_FLUX` for the first observable state difference. The
   ultimate cause of residual received-Force divergence remains unresolved.
4. **Group 4 turbulence runtime:** `NOT_SUPPORTED` as the earliest stage;
   isolated G4 reconstruction was `NOT_REACHED`.
5. **Group 6 RBF/motion cache:** `NOT_SUPPORTED` by identical same-input RBF
   input and candidate mesh output; isolated G6 reconstruction was
   `NOT_REACHED`.
6. **One-subsystem test reducing `||F4-F3||`:** `YES`, G2 lowered the
   received-Force difference from `0.0604642` to `0.0186948 N`. This is a
   partial causal result, not a repeatability pass.
7. **CFD inner-convergence A/B authorized:** `NO`. The unaccelerated Fluid
   Force operator has not been measured as repeatable on the same branch, and
   the post-rollback ALE state is not correctly restored in the baseline.
8. **IQN retest authorized:** `NO`.

The next *diagnostic* question, requiring separate authorization, is whether
identical `S11` inputs produce identical unaccelerated adapter Force payloads
at `S12`, and which part of the residual difference is preCICE acceleration
history. Do not replace the experimental adapter or infer physical convergence
from the four-attempt cap.

Machine-readable summaries are `stage_diff.json`, `earliest_divergence.json`,
`force_comparison.json`, and `qualification_summary.json` at the run root.
The exact scripts are `scripts/phase1k26_stage_replay.py` and
`scripts/phase1k26_analyze_stages.py`; the isolated solver source and build
identity are retained below the ignored evidence tree. No Phase 1K.26
production change or automatic next-phase run was made.
