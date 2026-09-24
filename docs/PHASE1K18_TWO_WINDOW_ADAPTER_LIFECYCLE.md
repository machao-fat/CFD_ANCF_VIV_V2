# Phase 1K.18 — Two-window adapter lifecycle qualification

**Classification: `REVIEW_REQUIRED`.** One bounded run completed exactly two physical windows with the Phase 1K.17 experimental adapter and diagnostic RBF library. The displacement read-time lifecycle, accepted-window handoff, trial-to-RBF-to-mesh path, and cell/mesh rollback observations behaved as intended. A repeatable `pointDisplacement` checkpoint/rollback diagnostic mismatch remains unresolved, so the strict no-field-mismatch acceptance criterion is not claimed as passed.

This is an experimental adapter lifecycle qualification only. It does not qualify convergence, efficiency, long-run stability, the historical qualified adapter, or HH06 physics.

## Run identity and bounds

- Run: `run-20260924T121817Z-c2245ff`
- Repository HEAD: `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`, branch `repair/worker-lineage-implicit-contract-v1`.
- Scratch restart: fresh copy of the unadvanced Phase 1K.10 `mapped_candidate_30`, `global time = 30.0 s`, `dt = 0.0002 s`.
- preCICE XML SHA256: `464170069c7b589ef8c1b1fd977c6282e2e4afbb944881e7e252980d1cb6a6d6`; hard bound `max-time-windows=2`, `max-iterations=20`, `min-iterations=2`. Installed preCICE 3.4.1 validation passed. The frozen IQN-ILS block was unchanged.
- Structure's existing CLI/contract still reports its pre-authorized 25-window ceiling; this scratch XML's preCICE cap was 2 and both participants stopped at that cap. Trace and logs contain no third window.
- OpenFOAM Foundation 10; Python `/usr/bin/python3.10` 3.10.12, `pyprecice` metadata 3.4.0, loaded `libprecice` runtime 3.4.1.
- Experimental adapter `libpreciceAdapterPhase1K17.so`: SHA256 `1bc5cf6a1ea481082b01b903d317313be01212413c8bf2718481fa43c485c495`, Build ID `ef890a9afffa253f4aceb051c4c3fed89e64cffe`. The historical qualified adapter SHA `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572` was checked, not substituted; process-map sampling observed the experimental adapter path.
- Diagnostic RBF `libRBFMeshMotionSolverPhase1K13Diag.so`: SHA256 `4a739721bfaa4734151e79bca285545d6934b2f5a9450080a5e833542a4c84ee`, Build ID `3bb45499c0bd8ce75b20cec055f920b6f35f4f41`.
- Worker source/binary SHA256: `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e` / `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`.
- New-mesh F0 evidence remained the Phase 1K.10 result: raw `(0.0655270406896, 0.05872987414832, -2.10307854575e-21) N`; the first Structure Force input was `(0.06552704068997028, 0.058729874147876754, 0) N`.

Machine-readable identity and result are in [runtime_identity.json](../evidence/phase1k18_adapter/run-20260924T121817Z-c2245ff/runtime_identity.json) and [qualification_summary.json](../evidence/phase1k18_adapter/run-20260924T121817Z-c2245ff/qualification_summary.json).

## Lifecycle observations

The trace contains 40 attempts: 20 in each window, with 19 rollback retries per window. Both windows were accepted at the iteration limit (`ACCEPTED_AT_ITERATION_LIMIT`), not by convergence. No convergence-efficiency conclusion is drawn.

| Check | Observation |
|---|---|
| Window targets | 30.0002 s and 30.0004 s; only windows 1 and 2 appear |
| Transport | Sequence 1–40; request IDs 910001–910040; transaction IDs 1910001–1910040; unique and monotonic in the Structure trace |
| Structure motion | `D_written == D_trial` exactly in all 40 records |
| Fluid displacement reads | 38 endpoint retry reads at `dt=0.0002`; one accepted-boundary read at offset 0; plus startup initial-data read at offset 0 |
| Window-1 accepted handoff | Offset-0 read returned max component `1.4162483789100853e-6 m`, equal to the magnitude of the accepted Structure x displacement; the next physical solve's RBF boundary input was `(-1.4162483789100853e-6, -1.235580527301291e-7) m` |
| Window-2 start | Its committed Structure motion equals window 1's accepted motion; its first Force input exactly equals window 1's accepted Force return |
| Displacement path | Nonzero received vectors populated `cellDisplacement` and `pointDisplacement`; 78 diagnostic RBF solve calls showed 200 moving controls, 646 fixed controls, 20 selected controls, and nonzero mesh movement. Maximum observed mesh-point displacement from `points0` was `4.900887096e-6 m` |
| Startup and errors | Initial zero displacement was observed at release. Both participant exit codes were 0; Fluid and Structure stderr were empty; OpenFOAM reached `End`; no solver fatal/SIGFPE or protocol failure was observed |

The full per-attempt Structure record is [structure_trace.jsonl](../evidence/phase1k18_adapter/run-20260924T121817Z-c2245ff/structure_trace.jsonl). Fluid read, field, checkpoint, and RBF details are in [fluid.stdout](../evidence/phase1k18_adapter/run-20260924T121817Z-c2245ff/fluid.stdout); participant exit and library observations are in [process_cleanup.json](../evidence/phase1k18_adapter/run-20260924T121817Z-c2245ff/process_cleanup.json).

## Rollback qualification gap

Window 1 rollback restored the zero release displacement fields and mesh (`mesh_delta_from_checkpoint=0`). In window 2, the checkpoint recorded:

- `cellDisplacement` cylinder maximum norm: `5.8069976555299806e-7 m`
- `pointDisplacement` cylinder maximum norm: `5.8069976555299827e-7 m`

After each rejected window-2 trial, rollback reported:

- `cellDisplacement` cylinder maximum norm: `5.8069976555299806e-7 m` (matches the checkpoint diagnostic)
- `pointDisplacement` cylinder maximum norm: `5.8280844460221839e-7 m` (differs by `2.1086790492201146e-9 m`)
- maximum mesh-point delta from checkpoint: `0 m`

The point-field diagnostic is only a maximum norm, not a full-field checksum. Existing evidence cannot determine whether this small but nonzero difference is a boundary re-evaluation/interpolation effect or a checkpoint restoration defect. Therefore full point-field rollback identity and the strict “no field mismatch” criterion remain unresolved. No tolerance was invented to waive it.

## Conclusion and stop

The two-window run confirms the accepted-boundary `readData(0)` handoff and retry `readData(dt)` behavior in the experimental Fluid adapter, and confirms that nonzero Structure displacement reaches RBF mesh motion. It does **not** justify a full Phase 1K.18 PASS while point-field rollback identity remains unresolved. Both windows hit the 20-iteration cap; this is reported, not treated as convergence or as an adapter lifecycle failure.

No production adapter, RBF library, mesh, coupling XML, physics parameter, or authoritative restart was changed. No retry or further runtime was started. The source-controlled diff remains empty; the worktree contains the existing untracked phase artifacts plus this report and Phase 1K.18 evidence. Stop here pending review of the point-field checkpoint diagnostic.
