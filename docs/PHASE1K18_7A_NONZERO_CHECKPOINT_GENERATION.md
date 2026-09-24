# Phase 1K.18.7A — Nonzero Checkpoint Generation

**Classification: `NONZERO_ACCEPTED_STATE_GENERATED`**

One accepted physical window was generated from the frozen mapped 30.0 s restart. The accepted state is nonzero and preserved as a byte-hash-pinned CFD + ANCF snapshot for the later rollback-localization run. No second physical window was started.

## Runtime boundary and identity

- Run: `evidence/phase1k18_7a_nonzero_checkpoint/run-20260924T144540Z-c2245ff/`
- Repository: branch `repair/worker-lineage-implicit-contract-v1`, HEAD `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`; tracked source/configuration diff remained empty.
- Start state: Phase 1K.10 `mapped_candidate_30`, global time 30.0 s. Frozen source fields and mesh hashes still match after the run.
- Runtime: OpenFOAM 10, preCICE 3.4.1, `/usr/bin/python3.10` 3.10.12, `pyprecice` metadata 3.4.0.
- Worker SHA256: `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`.
- Phase 1K.17 experimental adapter SHA256: `1bc5cf6a1ea481082b01b903d317313be01212413c8bf2718481fa43c485c495`.
- Phase 1K.13 diagnostic RBF SHA256: `4a739721bfaa4734151e79bca285545d6934b2f5a9450080a5e833542a4c84ee`.
- Frozen coupling settings: `dt=0.0002 s`, IQN-ILS profile unchanged, `max-iterations=20`, `min-iterations=2`. The isolated scratch XML was hard-capped to one physical window. Scratch-only output cadence was changed to write the accepted endpoint; no solver or physical parameter was changed.

The first preflight invocation stopped before either participant started because the runner checked only stdout for `foamVersion`, while this installation emitted `OpenFOAM-10` on stderr. The check was corrected and the same untouched scratch passed preflight before runtime. No CFD/FSI state was advanced by that preflight-only stop.

## Window result

- Exactly one physical window completed, target global time 30.0002 s.
- 20 coupling attempts; 19 physical rollbacks; no window 2.
- The window was `ACCEPTED_AT_ITERATION_LIMIT`, **not** convergence-qualified.
- Structure accepted interface displacement: `Dx=-1.4162483789100853e-6 m`, `Dy=-1.235580527301291e-7 m`.
- The Structure trace contains only window 1; `D_written == D_trial` for every attempt; transport sequence remained monotonic.
- Fluid and Structure exit codes were both 0. No solver, participant, or worker process remained after shutdown.

The Fluid/RBF log records nonzero displacement delivery during the window. On the final recorded RBF call at 30.0002 s, the cylinder `cellDisplacement` and `pointDisplacement` boundary maximum norms were approximately `5.806997656e-7 m`, and the RBF candidate mesh displacement maximum was `5.828084446e-7 m`. Across the attempt sequence, maxima were `9.512021597e-7 m`, `9.512021597e-7 m`, and `9.546562338e-7 m`, respectively. These Fluid values reflect the IQN-exchanged displacement, not the unrelaxed Structure trial value.

## Preserved accepted state

The complete accepted CFD snapshot is retained at `case/30.0002/`; the full case also retains the exact starting `case/30/` and the mesh/configuration needed to interpret both times. Required restart data are present: `U`, `p`, `k`, `omega`, `nut`, `pointDisplacement`, adapter-owned `cellDisplacement`, `uniform/time`, and time-local `polyMesh/points`. Additional written fields are included in the manifest.

Key SHA256 values for the accepted endpoint:

| Accepted state item | SHA256 |
|---|---|
| `pointDisplacement` | `f140b18ad38ac964f42e0518ea6a653dc9eb8e0eccfbe5bb5f9fdb19d72af781` |
| `cellDisplacement` | `3773e27364938115926c32804dd16a411e8bf28848e5e32d211c25dd54e99028` |
| `polyMesh/points` | `be63c59879b2ece39de4d0e5e584b719dcc331e2fa02c189772af74b13b5abb9` |
| `U` | `3e20739e7bfcdb6f34cbb14cee5d159bd4e7124862ef86c82c0e524f4a26e11b` |
| `p` | `1eb7499e8138a4ea94b5975d767baa8c81e4b10b9b41cf86db39bb3a4d97e97a` |
| `k` | `709f0f78266ecec6375fcdaca19c7b6e919df9af8387828abf824ef1d731d75d` |
| `omega` | `330cfc5c140fff4788edbf6c25c0e0f6b431970fdf771a966fb6256a2a4478d4` |
| `nut` | `75083b57c0f1582719bc8f4c87e742e6047a0cb88ce45be65f26d6cc203f0314` |
| `uniform/time` | `ffbabc93a614f04985addef0652c2a3d8cf49eb484b9c5317c381162e55c19fc` |

The accepted ANCF state is in `ancf_accepted_state.json`: complete 198-entry `q`, `qdot`, and `qddot` arrays and hashes, plus the physical checkpoint metadata and complete checkpoint backend state. The checkpoint is `hh06-window-1`, SHA256 `5901032d3f4f01250ffe79346f1979ca5b8161bcefa59607975c2fd7c049a0b5`. Accepted-minus-checkpoint `q` norm is `1.7787281326045922e-5`; accepted `qdot` and `qddot` norms are `0.17787281326045917` and `1778.7281326045932`. The coordinator checkpoint is cleared after accepted commit, as expected.

The saved endpoint tree was hashed twice immediately after shutdown and the manifests matched. This establishes byte-level integrity and reproducible identification of the preserved state; no second physical replay was performed, consistent with the one-window-only scope.

## Evidence index and stop

- [Runtime identity](../evidence/phase1k18_7a_nonzero_checkpoint/run-20260924T144540Z-c2245ff/runtime_identity.json)
- [Qualification summary](../evidence/phase1k18_7a_nonzero_checkpoint/run-20260924T144540Z-c2245ff/qualification_summary.json)
- [Accepted CFD file/hash manifest](../evidence/phase1k18_7a_nonzero_checkpoint/run-20260924T144540Z-c2245ff/accepted_cfd_state_manifest.json)
- [Accepted ANCF state and checkpoint](../evidence/phase1k18_7a_nonzero_checkpoint/run-20260924T144540Z-c2245ff/ancf_accepted_state.json)
- [Structure attempt trace](../evidence/phase1k18_7a_nonzero_checkpoint/run-20260924T144540Z-c2245ff/structure_trace.jsonl)
- [Process cleanup](../evidence/phase1k18_7a_nonzero_checkpoint/run-20260924T144540Z-c2245ff/process_cleanup.json)

No production source or authoritative restart was changed. No second window, five-window run, or 25-window run was started. This accepted state is a preparation artifact, not a convergence, stability, or HH06 validation result.
