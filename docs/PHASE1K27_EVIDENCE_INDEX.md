# Phase 1K.27 evidence index

Phase 1K.27 was run from diagnostic branch
`diagnostic/phase1k27-force-pipeline-decomposition-v1` at runtime HEAD
`e0da50c5660ec266c4bee50769ab95f94f0b014a`. The run used one physical
coupling window and stopped at its four-attempt diagnostic ceiling.

## Raw runtime archive

- Run ID: `run-20260925T090832Z-e0da50c`
- Local evidence path:
  `evidence/phase1k27_force_pipeline/run-20260925T090832Z-e0da50c/`
- Inventory at freeze: 328 files, 342451715 bytes
- Complete path-sorted tree SHA256:
  `ac4727a9330939d109f044f9171bf86d4d2989f7f2cb64bc97973c4d41952119`
- Runtime binaries, prepared cases, meshes, stage snapshots, logs, and nested
  source checkout remain in the local archive and are intentionally excluded
  from Git by repository evidence policy.
- The path-sorted tree digest is computed as the SHA256 of the newline-delimited
  `sha256sum` output for every regular file, with paths relative to the run root.

## Curated artifacts

The reports and scripts are tracked. The following runtime artifacts are the
curated machine-readable record; their exact hashes are listed for archive
verification.

| Artifact | SHA256 |
|---|---|
| `runtime_identity.json` | `91abb7a9be3501838df6e2896129e24d8e4e5c1cd662b12e290c06e205c26725` |
| `restart_identity.json` | `8612e16438f37c3c094e57e52793f328a1a1897ad1684e7f75d9455881d88bd5` |
| `qualification_summary.json` | `d475541b31d16dad2457875c7f39c6f8bc90f434d05913fab456163131a0c854` |
| `force_pipeline_map.json` | `6ec4af71da21afb3b7100b03028467c8b1e9226c930994f06a9165fe7db52ca9` |
| `force_stage_diff.json` | `bbb868a628935dcd149faa5aabe5205df199032c06efb7232ebecbfa86cb8e97` |
| `attempt_alignment.json` | `c37131ff3794abaa8e531e656565c368149a7015e06cea4e57ef341345aeec16` |
| `precice_acceleration_audit.json` | `c0a8943f5bab7d7c3055d9e9c82f2a06b0ebc0b9f476abd6bdf89b89cba7c5a7` |
| `process_cleanup.json` | `342fefa1fd7c08a806e2eecfae040eb4d605ee41de97334e60a8c2b9608870d2` |
| `fluid_input_trace.jsonl` | `bfa36487e6aa0607bdf5e02557d67559aafe49a833cd1dd3bb4b2fe530f67708` |
| `direct_force_trace.jsonl` | `7de85583a6146bfb37792bd13fe44b0b3eafb9bf5de0053ed99805491c4b7467` |
| `adapter_prewrite_force.jsonl` | `ef345145b46bb73ab4eafeab413175956cf6403058f59e617dcb4aed120f8be2` |
| `structure_received_force.jsonl` | `fcf2d58fcbd1665c42617010e68451cc1a2acb9d08a7fa31199fdfae397578d5` |
| `solver_stage_trace.jsonl` | `1d425ae54ea23a387cc9909c541da1aa6625c071b653cf6cfa6ee93d9f2caf0b` |
| `precice_iterations.log` | `50df545bb76a3815c1f2a4cef537810254a20bc7a4c3250dfb24c15ceefaa80b` |
| `precice_convergence.log` | `ff9421f89ad7b28c6d4b87d80054ecc7afffd2ee83658053fd68ced18f753031` |

The curated artifacts remain in the local archive for direct inspection. This
index records their provenance without staging the 342 MB raw runtime tree.
The diagnostic result and its scope are described in
`docs/PHASE1K27_DIRECT_FLUID_FORCE_REPEATABILITY_REPORT.md`.
