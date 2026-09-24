# Phase 1K.18.6 — `pointDisplacement` Mutation Localization

**Captured-run classification:** `NO_POINT_FIELD_MISMATCH` at the checkpoint-restore boundary (`S0 == S1`).

**Additional observed stages:** `DISPLACEMENT_READ_MUTATION` at S2 and `RBF_BOUNDARY_MUTATION` at S4.
**Historical Phase 1K.18 window-2 nonzero-checkpoint discrepancy:** not reproduced; its cause remains unresolved.

## Scope and identities

Exactly one physical coupling window was run, with one retry (two attempts maximum). The purpose was only point-field mutation localization. No ANCF/CFD parameters, production source/configuration, qualified library, mesh, or frozen restart was changed. The only launch adjustment was in the isolated diagnostic runner: Fluid was started with its cwd set to the scratch case and the runner printed and checked `pwd` immediately before OpenFOAM startup.

- Repository / branch / HEAD: `/home/machao/projects/CFD_ANCF_VIV_V2` / `repair/worker-lineage-implicit-contract-v1` / `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`
- Runtime evidence: `evidence/phase1k18_6_point_mutation/run-20260924T141228Z-c2245ff/`
- Restart: exact mapped new-mesh candidate at global time 30.0 s
- Experimental adapter SHA256: `cab6f4bffcc71ea24f296ece6c67ec9f1c6011e7139b39f2af62d2145422f71e`
- Experimental RBF SHA256: `3defd4b158f48062d6222911a449a2b1995f1b0fc0ca00e9453c19a6b6f6dd28`
- Qualified adapter and RBF binaries were not replaced.
- `pwd` evidence: `/home/machao/projects/CFD_ANCF_VIV_V2/evidence/phase1k18_6_point_mutation/run-20260924T141228Z-c2245ff/case`
- Scratch XML and dictionaries are unchanged from the prior isolated attempt; their hashes are recorded below. The existing XML socket path was reused only after checking it was empty and no participants were active. It now contains an empty `precice-run` subdirectory and no files.
- Bounds: `dt=0.0002 s`, one physical window ending at 30.0002 s, two implicit attempts maximum. Attempt 2 was `ACCEPTED_AT_ITERATION_LIMIT`, not convergence.

Preflight passed. Fluid and Structure both exited 0; the runner observed exactly two Structure trace rows and one rollback, with no third attempt. No Fluid, Structure, or worker process remained afterward. The frozen source restart and scratch `30/` fields/mesh still match the provenance hashes; no `30.0002` time directory was written.

## S0–S5 snapshot hashes and norms

Every JSON snapshot contains the full `pointDisplacement` internal array and all patch entries, `cellDisplacement`, and the mesh point coordinates. The hashes below are SHA256 of canonical JSON for the named complete field/subarray (`sort_keys=true`, compact separators, finite values required). Snapshot files are under `diagnostics/` in the runtime evidence directory.

| Snapshot | Time | `pointDisplacement` full SHA256 | Internal SHA256 | Boundary SHA256 | Point norm min–max (m) | `cellDisplacement` SHA256 | Actual mesh-point SHA256 |
|---|---:|---|---|---|---:|---|---|
| S0 checkpoint save | 30.0 | `2bf92ed1ebf949284553b09f36d39e964a157c1da634735fd867a39e499e9979` | `b64109323c6a795d022cb63d525c7d8a846f42fbfb9f915adf67c38bd3c5ae7a` | `ac1aa9533e07992a96ccfebf0965806eaace277149f5e02cc677d8eb0b9bb652` | 0 – 0 | `79614898baade45f97a708bcc28ec2a7f0dddc893bbbd557f49873dcdd2e727a` | `113ebbf907de5d0e4fe47072c4c5d85e96a01db9a4a3124f36e641ecfea279e7` |
| S1 after rollback restore | 30.0 | `2bf92ed1ebf949284553b09f36d39e964a157c1da634735fd867a39e499e9979` | `b64109323c6a795d022cb63d525c7d8a846f42fbfb9f915adf67c38bd3c5ae7a` | `ac1aa9533e07992a96ccfebf0965806eaace277149f5e02cc677d8eb0b9bb652` | 0 – 0 | `79614898baade45f97a708bcc28ec2a7f0dddc893bbbd557f49873dcdd2e727a` | `113ebbf907de5d0e4fe47072c4c5d85e96a01db9a4a3124f36e641ecfea279e7` |
| S2 after retry `readData(dt)` | 30.0 | `73bd50c3b6bd789b813094a81238676ef4017f02ce25635109a98ae747fa3e91` | `b64109323c6a795d022cb63d525c7d8a846f42fbfb9f915adf67c38bd3c5ae7a` | `84f45bd2f0faa345d7f27c398a991117c50eaa847b8cba705154aac00b9bd8c9` | 0 – `2.855969890252094e-8` | `b6649ee8ec83d9482c01405bafc39a4e26e0b77ab4292a6de003d6c87924fd94` | `113ebbf907de5d0e4fe47072c4c5d85e96a01db9a4a3124f36e641ecfea279e7` |
| S3 before RBF boundary correction, call 3 | 30.0002 | `73bd50c3b6bd789b813094a81238676ef4017f02ce25635109a98ae747fa3e91` | `b64109323c6a795d022cb63d525c7d8a846f42fbfb9f915adf67c38bd3c5ae7a` | `84f45bd2f0faa345d7f27c398a991117c50eaa847b8cba705154aac00b9bd8c9` | 0 – `2.855969890252094e-8` | `b6649ee8ec83d9482c01405bafc39a4e26e0b77ab4292a6de003d6c87924fd94` | `113ebbf907de5d0e4fe47072c4c5d85e96a01db9a4a3124f36e641ecfea279e7` |
| S4 after RBF boundary correction, call 3 | 30.0002 | `6f397fc7f45db23f99e868d5e43eb3a7218fd06ba82c5a7f672cbf71577e4e0e` | `b48bb60f15d05df085d54a13dbfc8c3e20273e20a760e175a3e5df648717e16d` | `8f449f6d31c75ea23781cab7d6f52000a3e5546efcf7297a7540c4824e17792f` | 0 – `2.855969890252094e-8` | `b6649ee8ec83d9482c01405bafc39a4e26e0b77ab4292a6de003d6c87924fd94` | `113ebbf907de5d0e4fe47072c4c5d85e96a01db9a4a3124f36e641ecfea279e7` |
| S5 after RBF solve, call 3 | 30.0002 | `67a3eb3494d282e47e2cb1be55297628eea75dd847c6815dfd55f76ed10a9900` | `ee9bdd77c9c4b8757793316eb558f21a615db8e2525dde43fd797daa44a2a633` | `c6f2bbf2bcfdc34b4b1904f17e660f286678a7f19bf4cfede80dde1ea20bbe07` | 0 – `2.8663406949777452e-8` | `b6649ee8ec83d9482c01405bafc39a4e26e0b77ab4292a6de003d6c87924fd94` | `113ebbf907de5d0e4fe47072c4c5d85e96a01db9a4a3124f36e641ecfea279e7` |

The S5 RBF candidate mesh-point array has canonical SHA256 `b922ce4faf4db35fb897a0a9f55015551a6f4206af5df7dc790e067398600667`. Relative to the release mesh-point array, 93,206 of 94,498 candidate points differ; maximum candidate point motion is `2.8663406950560435e-8 m`. The S5 hook is inside the motion solver before its returned candidate has been installed as the current mesh points; therefore the actual `mesh_points` checksum remains the release checksum in S5. The candidate array is separately captured and must not be conflated with the current mesh.

## Mutation localization

1. **S0 → S1, checkpoint restore:** complete `pointDisplacement` SHA, internal SHA, and boundary SHA are identical. All 190,696 serialized point vectors compare exactly (`changed=0`, maximum vector delta `0`). `cellDisplacement` (47,672 vectors) and mesh coordinates (94,498 points) also compare exactly. This run shows no point-field restore mismatch for this checkpoint.
2. **S1 → S2, adapter retry read:** the internal point array remains identical. Exactly 400 `cylinder` point-boundary vectors change; maximum norm is `2.855969890252094e-8 m`. Exactly 200 cylinder `cellDisplacement` face vectors change. Other point patches and mesh points are unchanged. Fluid log records `readData` offset `0.000200`, 400 scalars, and a nonzero value. This is the first post-rollback field change and is the expected application of the retry displacement, not a failed restore.
3. **S2 → S3 call 3:** point, cell, and mesh arrays are identical; RBF enters with the adapter-read interface state.
4. **S3 → S4 call 3, `correctBoundaryConditions()`:** 400 internal point vectors change, with maximum delta `2.855969890252094e-8 m`; the fixed-value cylinder patch itself is unchanged. The serialized `front`/`back` point-patch entries each show 200 changed values because those entries are patch-internal views for the `empty` patches. Cell displacement and mesh coordinates are unchanged. Thus a field mutation occurs at the RBF boundary-correction stage, where the interface values are reflected into the point field's internal representation.
5. **S4 → S5 call 3, RBF interpolation:** 93,206 internal point vectors change; maximum vector delta is `2.8662548878465792e-8 m`. The cylinder fixed-value control boundary remains unchanged; the RBF-produced candidate mesh is nonzero as reported above. This demonstrates that the retry displacement reaches the RBF solver and produces a nonzero candidate deformation.

RBF calls 1 and 2 (the first attempt and rollback-time mesh restoration) remained all-zero point states; their S3/S4/S5 point hashes equal S0/S1. Call 3 is the retry solve and is the nonzero path summarized above.

## Interpretation boundary

For the captured window, the requested rollback comparison is `NO_POINT_FIELD_MISMATCH`: S1 exactly matches S0. The first later change is at S2 (`DISPLACEMENT_READ_MUTATION`), followed by point-field updates at S4 (`RBF_BOUNDARY_MUTATION`) and RBF interpolation at S5. These are post-restore lifecycle changes, not evidence of a restore defect.

This was the first physical window from the 30.0 s release with zero committed structural displacement. The earlier Phase 1K.18 anomaly occurred in window 2 with a nonzero checkpoint. Therefore this one-window test does **not** reproduce or explain that historical nonzero-state discrepancy, nor does it prove behavior for nonzero checkpoint fields or old-time levels. That historical root cause remains unresolved pending equivalent S0–S5 evidence from a nonzero committed state.

## Runtime and preserved evidence

- Successful run: `evidence/phase1k18_6_point_mutation/run-20260924T141228Z-c2245ff/`
- `preflight.json`: `PASS_PREFLIGHT_ONLY`
- `diagnostic_run_summary.json`: `ONE_WINDOW_ONE_RETRY_CAPTURED`; 2 attempts, 1 rollback, 12 snapshots, no hard-stop reason
- `structure_trace.jsonl`: attempt 1 rolled back; attempt 2 committed with `ACCEPTED_AT_ITERATION_LIMIT`; `D_written == D_trial` on both attempts
- `process_cleanup.json`: Fluid exit 0, Structure exit 0; no lingering runtime processes
- `fluid.stdout`: verified case `pwd`, OpenFOAM/preCICE startup, all S0–S5 stage markers and adapter read offset
- `diagnostics/`: full field snapshots listed above
- Experimental libraries loaded by the runtime are the SHA-pinned Phase 1K.18 diagnostic builds listed above; qualified binaries remain unchanged.
- XML SHA256: `d8a29141cb752ab1cfe74fa647d21b9e07d4f90e40358d1ef00a55afade433f1`
- `preciceDict` SHA256: `5d018d744d1f76280fad2b1cc788e5dd32b331fe2bd0d9aa7900260cf4c7f229`
- `controlDict` SHA256: `89480b690b5d4e8a13e44795cf556e1dc90e508f0642b20f30937779cb861bea`
- `dynamicMeshDict` SHA256: `262a8742c8bae0c861f0ee8768ac970dd8067949e23aaa3bff41e9b3747f2a2d`
- Successful-run scratch runner SHA256: `02f13222b4cea0c46cc66425a0c23a3d61174e1eaf46f4b5a8fced3b3a53e492` (`run_one_window_one_retry.py`); it contains only launch cwd/socket-guard diagnostics in addition to the existing one-window cap.
- The initial cwd-failure and monitor false-positive runs remain preserved in their separate run directories; they are not used for mutation conclusions.

## Git boundary

No commit was created. No tracked source or production configuration was changed. The report and runtime evidence are untracked. `git diff --check` passed; repository HEAD remains `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`.
