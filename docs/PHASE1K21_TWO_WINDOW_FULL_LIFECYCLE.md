# Phase 1K.21 — Experimental adapter two-window full lifecycle

**Classification: `PASS_EXPERIMENTAL_TWO_WINDOW_LIFECYCLE`.** This qualifies the separately identified Phase 1K.20 adapter for two complete implicit physical windows, including rollback from a **nonzero accepted** window-1 state. It is not production-adapter qualification, convergence qualification, or long-run FSI stability evidence.

## Scope and identity

- Repository: `repair/worker-lineage-implicit-contract-v1`, HEAD `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`. No tracked source, production case, XML, physics, mesh, RBF, IQN, or time-step changes were made in this phase.
- Successful scratch run: `evidence/phase1k21_two_window_lifecycle/run-20260924T1700XXZ-c2245ff-g072Su/`. It starts from the frozen Phase 1K.10 mapped new-mesh `30.0 s` state, not an advanced Phase 1K.18/1K.20 endpoint. The scratch XML SHA-256 is `e59208b5d57783bf49b0b8ae5f4b3ce41bb6a95f6e2b02bd7ca5b50c07948666`; it retains the prior IQN/RBF/physical settings and sets only the experiment's two-window bound and unique socket path.
- Experimental adapter actually loaded: `libpreciceAdapterPhase1K20.so`, SHA-256 `225ecab227b8271f01119fe476370e3a0b705ca06e1ca3a7739200266499b165`. Diagnostic RBF actually loaded: `libRBFMeshMotionSolverPhase1K187BStopDiag.so`, SHA-256 `508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11`; its one-retry stop switch was **disabled** for this run. Worker SHA-256: `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`. The historically qualified adapter was not replaced.
- OpenFOAM Foundation 10, preCICE 3.4.1, `dt=0.0002 s`, IQN-ILS and RBF settings unchanged, preCICE minimum/maximum implicit iterations `2/20`, and maximum physical windows `2`. The scratch diagnostic participant SHA-256 is `46a95b2243823d789328b44cdae0338606286cd57b829cf4ddefe2a420f5c4ee`; it differs from the earlier diagnostic copy only by the narrow **two-window fail-closed authorization**.

An initial startup attempt is preserved separately at `evidence/phase1k21_two_window_lifecycle/run-20260924T165427Z-c2245ff-kpPFSL/`. Its copied diagnostic participant still required exactly 25 windows and exited before coupling; Fluid was terminated, with no coupling attempt or advanced time directory. The successful run used a new scratch/evidence directory after correcting only that diagnostic launch guard and the unique socket path. Neither attempt changed the production participant or the qualified adapter.

## Observed lifecycle

| Physical window | Target global time | Attempts | Rollbacks | Acceptance | Checkpoint `pointDisplacement` max norm |
|---|---:|---:|---:|---|---:|
| 1 | 30.0002 s | 20 | 19 | `ACCEPTED_AT_ITERATION_LIMIT` | 0 m |
| 2 | 30.0004 s | 20 | 19 | `ACCEPTED_AT_ITERATION_LIMIT` | `5.828084446022184e-7 m` |

The window-2 S0 checkpoint is demonstrably nonzero. The window-1 accepted interface displacement `(Dx,Dy)=(-1.4162483789100853e-6,-1.235580527301291e-7) m` becomes the window-2 previous committed interface displacement. The accepted window-1 Force handed to window 2 is exactly `[0.3728239529439289, 0.48539420096402064, 0.0] N` in both the window-1 returned and window-2 input trace records. No third window was started; scratch time directories end at `30.0004`.

Every one of the 38 retries has an S1 full-state snapshot paired with its physical window's S0 snapshot. SHA-256 comparison of the **full point internal field**, **all seven point boundary patches** (values and recorded metadata), **full cell internal/boundary field**, and **all mesh point coordinates** matched S0 exactly for all 19 window-1 and 19 window-2 retries. For the nonzero window-2 checkpoint, point internal SHA-256 is `e07ed16096a0c80b159c20e0f0b75d9005446835aa3207d4a5ed7d5ece76711f`, point boundary SHA-256 is `12bce8248063d4d439cb0b9e0881420a668038accfe4db886e023d5a242926c3`, full point SHA-256 is `031d8d85ce6bac90a5a2dafe16462c6e781a0e8b891ff52d91c64fd2a185ef7c`, and mesh-points SHA-256 is `bee2072d6d1f5c2ae6c3eed7cac82fae1f1bac568fff5a36383e9226c3b8893e`. Each is unchanged at every window-2 S1.

ANCF diagnostic records include one S0 and 19 S1 events per window. At all 38 S1 events, live `q`, `qdot`, and `qddot` arrays and their hashes equal the corresponding saved physical checkpoint. The Fluid adapter recorded 38 retry displacement reads at `relativeReadTime=0.0002 s` and one accepted-window handoff read at `0.0 s`. There is no final accepted-boundary read after window 2 because preCICE ends the two-window coupling then. Across all 40 Structure attempts, written interface displacement equals the current ANCF trial; each retry's Force input equals the immediately preceding returned Force. Transport sequence is 1–40, and request/transaction IDs are unique in all 40 records.

The raw Fluid and Structure processes both exited with code 0; observed worker PIDs are no longer present. The `precice-run` directory remains as an empty directory, with no socket file. Both accepted windows reached the **iteration limit**, so this report makes no claim of convergence before the cap or of improved numerical efficiency.

## Evidence and boundary

The successful run directory contains the frozen scratch case, `structure_trace.jsonl`, `ancf_checkpoint_stages.jsonl`, complete S0–S5 field/mesh snapshots under `diagnostics/`, raw Fluid/Structure logs, `process_cleanup.json`, `analyze_lifecycle.py`, and `qualification_summary.json` with a per-retry hash comparison. The failed pre-coupling startup directory is retained rather than overwritten. Evidence and this report remain uncommitted pending review; the tracked Git tree is clean.

**Conclusion:** the Phase 1K.20 experimental adapter satisfies exact nonzero point/cell/mesh and ANCF checkpoint restoration across two complete implicit physical windows, and the `dt` retry / `0` accepted-boundary read-time lifecycle is observed. Do not infer production readiness, converged windows, five/25-window stability, or permission to replace the historically qualified adapter.
