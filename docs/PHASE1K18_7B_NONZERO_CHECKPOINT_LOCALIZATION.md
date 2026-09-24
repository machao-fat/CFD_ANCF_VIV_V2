# Phase 1K.18.7B — Nonzero Checkpoint Rollback Localization

**Classification: `NONZERO_ROLLBACK_RESTORE_MISMATCH`**

## Result

One retry was captured from the preserved accepted Phase 1K.18.7A state at global time `30.0002 s`. The first mismatch is already present at S1, immediately after Fluid rollback restoration and before retry `readData(dt)`:

- `pointDisplacement`: S0 and S1 differ. The internal field is identical; 400 cylinder boundary entries differ, with maximum vector delta `1.0513391307158744e-6 m`.
- `cellDisplacement`: S0 equals S1 exactly, including internal and boundary data.
- mesh points: S0 equals S1 exactly.
- ANCF: S0 and S1 retain the same `q`, `qdot`, and `qddot`; the live state equals the saved physical checkpoint at both stages.

Thus the nonzero point-field discrepancy is localized to the rollback-restore interval, not to the later retry read or RBF solve. Later stages also mutate the point field, as detailed below; they do not explain the earlier S0→S1 difference.

## Source and runtime identity

- Git branch/HEAD: `repair/worker-lineage-implicit-contract-v1` / `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`.
- Start state: preserved Phase 1K.18.7A endpoint, global time `30.0002 s`; accepted ANCF snapshot SHA-256 `fae2cedc42186475a27ee01e48deced15580d8d3537c4aa32ec02b0d28cc747c`.
- Worker binary SHA-256: `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`.
- Experimental diagnostic adapter SHA-256: `cab6f4bffcc71ea24f296ece6c67ec9f1c6011e7139b39f2af62d2145422f71e`; Build ID `f17adc69bf9540ce23982d09165628fff2ce8c03`.
- Experimental stop-diagnostic RBF SHA-256: `508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11`; Build ID `968461b080423d63f636d6f1afcff0ad346a3c0a`.
- OpenFOAM `10`; preCICE `3.4.1`; Python `3.10.12`, pyprecice metadata `3.4.0`.
- The qualified historical adapter and RBF binaries were not loaded or replaced. Only the isolated evidence case and its diagnostic participant variant were adjusted.

The actual diagnostic run is `evidence/phase1k18_7b_nonzero_rollback/run-20260924T161017Z-c2245ff-bridge-session1/`. Preflight passed. It captured one physical retry and stopped at S5 before another Fluid advance; no new window was accepted. Fluid exited at the deliberate diagnostic stop (86), Structure was stopped as its peer, and no solver or worker process remained. The scratch Fluid case contains a `30.0004` output directory from the in-progress target attempt; it is not an accepted checkpoint and must not be used as a restart.

An earlier startup-only attempt is separately preserved at `run-20260924T153627Z-c2245ff/`. It stopped before ANCF solve because the fresh worker session rejected bridge step 2 as its first request; it produced no rollback evidence. The successful diagnostic run used a run-local bridge-step origin while preserving resumed global time/tick and all production binaries.

## S0–S5 measurements

The complete snapshots retain every point/cell field value and mesh point. `field_stage_metrics.json` contains the full SHA-256 values for each stage and each field's complete/internal/boundary arrays, changed-entry counts, and maximum deltas. The table below summarizes the decisive comparisons; mesh-point checksums are unchanged through S5 because the stop is inside the RBF solve, before the candidate points are assigned to the active mesh.

| Stage | Point-field change from prior stage | Cell-field change from prior stage | Active mesh-point change |
|---|---:|---:|---:|
| S0 checkpoint saved, `30.0002 s` | baseline; cylinder boundary max norm `1.421627962288273e-6 m` | baseline | baseline |
| S1 rollback restored, before read | **400 cylinder boundary entries**, internal 0; max delta `1.0513391307158744e-6 m` | none; exact checksum match | none; exact checksum match |
| S2 after `readData(dt)` | 400 cylinder boundary entries; max delta `7.651864172437014e-7 m` | 200 cylinder face-boundary entries; max delta `4.470363116019137e-7 m` | none |
| S3 before `correctBoundaryConditions()` | no change from S2 | no change from S2 | none |
| S4 after `correctBoundaryConditions()` | 400 internal + 400 boundary entries; max delta `7.651864172437014e-7 m` | no change | none |
| S5 after RBF solve, call 3 | 93,206 internal + 93,206 boundary entries; max delta `7.676456987216975e-7 m` | no change | active mesh unchanged; separate RBF candidate moved 93,206 points, max `7.676686797465788e-7 m` |

S0/S1 decisive SHA-256 values:

| Field | S0 full | S1 full | S0 internal = S1 internal | S0 boundary | S1 boundary |
|---|---|---|---|---|---|
| `pointDisplacement` | `4309ee30bbf66f11ea08b44d1a38ef91eb6df7acccc306abe9f7e79983d6f0aa` | `54862958dd30a46d5b8aedec21a4f40ca67d3c955ef29c5fce6b2cdeb09fe8ec` | `e07ed16096a0c80b159c20e0f0b75d9005446835aa3207d4a5ed7d5ece76711f` | `c5dbaddde643e6e7a509c8ae1e0aa6dd9e48b2aeab1b80519fea28847f4a8cb5` | `57092953a19ee0c21cad2441c06aeb2c1cf639e507caa0bd668041856d3d106f` |
| `cellDisplacement` | `7aa1b0cd6a58c570439b2a511d882504c619b75a1494b5b4cf77abc337c3f5cd` | same as S0 | `51b5a3e6f4d33c17a2b0514b8cd0d56cf68d3c376e726644193c0ce2a386df54` | `6fc43ca8ae59e60bb89a1698e16acfb417d4676a77605bd7916643e2e9933f9f` | same as S0 |
| mesh points | `bee2072d6d1f5c2ae6c3eed7cac82fae1f1bac568fff5a36383e9226c3b8893e` | same as S0 | — | — | — |

ANCF checkpoint identity at both S0 and S1:

- coordinator checkpoint ID: `hh06-window-2`
- coordinator checkpoint SHA-256: `8509acecbf9d10ea65a574dcf980dfdd58c281a2124b0c19af49269f4a7af11d`
- `q`: `c3aea75f15b3da0c28f035b7019dd30454beb927165c756e04099e30d9e4d23b`
- `qdot`: `4a4bcde806faf26bd5ec4df8e0efff09378475459739292d941375e4d69d1ed1`
- `qddot`: `d19b017431234a96df023dfac14f59fb8a5095e55c401c23575dfe5a68f7a17b`
- S0 and S1 live-state hashes equal their checkpoint-state hashes; all three state vectors are identical across restore.

## Localization and limits

The diagnostic adapter source copy at `evidence/phase1k18_6_point_mutation/run-20260924T141228Z-c2245ff/adapter-source/Adapter.C` shows `pointDisplacement` registered among `pointVectorField` checkpoint fields (1112–1118), copied at checkpoint save (1437–1458), and assigned back during restore (1267–1281). It emits S1 after that restore block (1352–1360); retry `readCouplingData(readOffset)` and S2 occur later (557–566). S1 is therefore before the new displacement read. The snapshots establish the observed mutation interval: after the checkpoint snapshot and by completion of the adapter's restore block, before the next displacement read. The exact sub-operation responsible for the fixed-value cylinder boundary values changing is **not** isolated by these snapshots; do not attribute it more narrowly to a particular OpenFOAM assignment operator or boundary-condition routine.

The retry read and later operations are independently visible: S1→S2 changes the incoming boundary displacement; S2→S3 is unchanged; `correctBoundaryConditions()` changes point-field internal/boundary values at S3→S4; RBF computes nonzero candidate point motion at S5. The stop occurs before that candidate is assigned to `mesh.points()`, so this run does not claim a post-assignment mesh update.

The earlier Phase 1K.18.6 zero-state result (`NO_POINT_FIELD_MISMATCH`) remains valid for its zero checkpoint. This nonzero-state result does not overwrite it; it demonstrates that the zero-state case did not exercise the mismatch now observed.

## Evidence files

Under the run directory above:

- `diagnostics/S0_after_checkpoint_save_1.json` through `S5_after_RBF_solve_call_3.json`: complete snapshots (all S0–S5 field arrays and mesh points).
- `field_stage_metrics.json`: full checksums, internal/boundary checksums, changed entries, maximum deltas, and classification.
- `ancf_checkpoint_stages.jsonl`: full q/qdot/qddot and checkpoint state at S0/S1.
- `pre_advance_attempts.jsonl`, `structure_trace.jsonl`: force, motion and attempt records; the second trial is preserved in the pre-advance trace because the deliberate Fluid stop occurs before its preCICE advance returns.
- `runtime_identity.json`, `preflight.json`, `process_cleanup.json`, `fluid.stdout`, `structure.stdout`, `structure.stderr`, `diagnostic_summary.json`.

No production coupling, ANCF, worker, adapter, RBF, mesh, or physics source/configuration was modified. No commit was created.
