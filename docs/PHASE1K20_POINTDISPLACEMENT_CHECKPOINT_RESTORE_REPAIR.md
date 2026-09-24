# Phase 1K.20 — Experimental `pointDisplacement` Checkpoint Restore Repair

**Classification: `PASS_EXPERIMENTAL_NONZERO_POINT_CHECKPOINT_ONE_RETRY`**

This is an experimental adapter result only. It qualifies exact nonzero `pointDisplacement` S0→S1 restoration for **one** implicit retry from the preserved Phase 1K.18.7A accepted state. It does not qualify later accepted-window handoff, multi-window convergence, or long-run RBF/FSI stability. No production case, qualified adapter, IQN/RBF parameters, mesh, ANCF model, worker, or time step was changed.

## Identity and implementation

- Repository branch/HEAD: `repair/worker-lineage-implicit-contract-v1` / `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`; tracked/index diff remained empty.
- Run/evidence: `evidence/phase1k20_point_checkpoint/run-20260924T164027Z-c2245ff-Gu2Hg5/`.
- Experimental source basis: separate diagnostic adapter source preserved at `evidence/phase1k18_6_point_mutation/run-20260924T141228Z-c2245ff/adapter-source/`, derived from official `precice/openfoam-adapter` `OpenFOAM10` commit `d53753b1c927b2413b02299c9da15725b3e772f0` through the earlier experimental Phase 1K.16–1K.18 patches. This is **not** asserted to be the source of the historically qualified adapter.
- Exact new experimental source: `adapter-source/Adapter.C`, `Adapter.H`, new `PointDisplacementCheckpoint.H`, and `Make/files` within the run directory. Source-tree SHA-256 `7c3406da03f96431bb89d04863adb7e6e1e20beb9b9b2ea52b8979f4329c3701` (lexically sorted `sha256sum` records for `.C`, `.H`, `Make/files`, `Make/options`, excluding `lnInclude` and compiled objects). Patch-identity digest `92dbd6632a96254f755fee2fd59307f7b199519c40e8987a63f5e932cfa03b5e` (concatenated `git diff --no-index` for the three changed original files plus SHA-256 line for the new header, then SHA-256). The new header itself is SHA-256 `65599761c93cb586dedeac77b4315710eaddd2387a3cf9388deb0b051af92a0b`.
- New library: `build/libpreciceAdapterPhase1K20.so`, SHA-256 `225ecab227b8271f01119fe476370e3a0b705ca06e1ca3a7739200266499b165`, ELF Build ID `d1a7fca8f75aea43f9b3b8d7904e57a6ac90c627`. Build: `source /opt/openfoam10/etc/bashrc; ADAPTER_TARGET_DIR=<run>/build; wclean .; wmake libso .`, then `wmake libso .` after a warning-only type-size cleanup. Compiler `g++ 11.4.0`, OpenFOAM Foundation 10, preCICE runtime 3.4.1. `wmake` reported a dependency-scanner warning about `clockValue.H`, but linking completed with exit code 0.
- The historically qualified adapter `/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so` remained SHA-256 `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572` and was not loaded. The reused, separately named diagnostic RBF binary remained SHA-256 `508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11`.

The repair handles the **save and restore** sides: at each physical checkpoint, the experimental adapter takes an explicit snapshot of the live `pointDisplacement` primitive/internal values and each patch's name, type, and values. For `fixedValue`, it saves the *stored patch-value array* rather than using `patchInternalField()`. At rollback it restores internal values, then directly restores stored-value patches, checks exact component equality and an in-process 64-bit FNV checksum, and only then allows the retry `readData(dt)`. `empty`/`symmetryPlane` patches have derived values rather than stored writable values; their values are captured and verified after internal restoration. A patch type, size, or supported-state mismatch fails closed. The old whole-field `operator==` remains for other point-vector fields but is bypassed for the named HH06 `pointDisplacement` on both save and restore.

The implementation intentionally does **not** disable the normal displacement reader or RBF `correctBoundaryConditions()`. `pointPatchField::updated_` is private in installed OpenFOAM-10 and is not independently snapshotted. This one-retry PASS proves exact measured field values at S1 and subsequent diagnostic path, not general patch-bookkeeping identity. The experimental helper fails closed if `pointDisplacement` has old-time levels (`nOldTimes()!=0`); the observed case had none. That limitation must be resolved or separately qualified before broader use.

## Field-level test

`field_test/pointCheckpointTest.C` was built as an isolated OpenFOAM utility and run against a scratch case. It created a nonzero `pointDisplacement` whose cylinder `fixedValue` values differed deliberately from the point internal field, captured a snapshot, zeroed both components, confirmed the mutated field did **not** match, restored it, then confirmed full exact equality. Output: `PHASE1K20_FIELD_TEST_PASS`, checksum `337d40b6d8391b27`, cylinder points `400`; exit code 0. The test did not advance time or start preCICE/ANCF.

## One-retry runtime

The runtime case is a fresh copy of the preserved Phase 1K.18.7A accepted `30.0002 s` CFD state, including its mesh and fields. The accepted ANCF state and manifest were copied unchanged. Only scratch launch paths and the one-retry preCICE cap were adjusted; source templates copied from Phase 1K.18.7B are retained under `source_templates/` and are **not** the active case configuration. An initial *preflight-only* call found missing frozen F0 report/result files in the new scratch directory; those original, hash-pinned files were copied into the new evidence directory. The next preflight was `PASS_PREFLIGHT_ONLY`; no runtime was started by the failed preflight.

The only real attempt used the executed copy `run_nonzero_rollback.py --run`, launched Fluid with the scratch case as `cwd`, and stopped at the first retry's S5 stage. The runtime `/proc` maps show the new Phase 1K.20 adapter, the diagnostic RBF library, and system `libprecice.so.3.4.1`. This reused diagnostic harness deliberately stops before a second Fluid advance or acceptance of another physical window.

| Check | Result |
|---|---|
| Adapter save/restore log checksum | Both `f65fd3238852d45d` |
| `pointDisplacement` full S0/S1 SHA-256 | Both `4309ee30bbf66f11ea08b44d1a38ef91eb6df7acccc306abe9f7e79983d6f0aa` |
| Point internal and boundary SHA-256 | Both equal across S0/S1; 0 changed entries, 0 maximum delta |
| `cellDisplacement` full S0/S1 | Equal; 0 changed entries |
| Mesh points S0/S1 | Equal; 0 changed points |
| ANCF `q/qdot/qddot` S0/S1 | Equal to the saved physical checkpoint at both stages |
| Retry read offset | `0.0002 s` (`dt`), logged **after** S1 |
| S1→S2 new displacement | 400 cylinder point-boundary and 200 cylinder cell-boundary entries changed |
| RBF diagnostic S5 | 93,206 candidate points moved, maximum candidate delta `7.676686797465788e-7 m`; active mesh assignment after S5 was not tested |

The inherited diagnostic summarizer labels later S1→S2/RBF changes as `DISPLACEMENT_READ_OR_RBF_STAGE_MUTATION`. That is **expected post-restore behavior**, not a rollback failure: its own `rollback` object reports all three field/mesh S0==S1 checks as `true`. The Phase 1K.20 result is classified using that exact rollback object plus ANCF identity and the controlled-stop record; no historical failure evidence was overwritten.

Fluid exited with diagnostic code 86 at the deliberate S5 stop. Structure was terminated as its peer (signal 15). `process_cleanup.json` reports no remaining solver/worker process. One physical retry was observed; no second new window was accepted.

## Evidence and boundary

Machine-readable result: `qualification_summary.json`; full snapshots: `diagnostics/S0...json` through `S5...json`; comparisons: `field_stage_metrics.json`; ANCF physical state: `ancf_checkpoint_stages.jsonl`; launch/identity: `preflight.json`, `runtime_identity.json`, `process_cleanup.json`; raw logs: `fluid.stdout`, `fluid.stderr`, `structure.stdout`, `structure.stderr`. All are under the unique run directory above. This evidence remains uncommitted pending review.

**Next gate is separate review.** This run proves the nonzero S0→S1 value-restoration invariant for the experimental adapter at one retry only. It does not authorize replacing the qualified adapter, running five/25 windows, or claiming long-run stability.
