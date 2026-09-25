# Phase 1K.26 evidence index

Phase 1K.26 is frozen from checkpoint commit
`4182ac91a08b16edd5982a34cd22dbfa050c7fae` on
`diagnostic/phase1k26-earliest-fluid-replay-divergence-v1`.

## Runtime archive

- Run ID: `run-20260925T-phase1k26-4182ac9`
- Local evidence path:
  `evidence/phase1k26_earliest_divergence/run-20260925T-phase1k26-4182ac9/`
- Inventory at freeze: 641 files, 1,338,116,161 bytes before the SHA manifest.
- Runtime trees, meshes, stage snapshots, and logs remain in the local evidence
  archive and are intentionally not committed. They were preserved in place.
- `sha256_manifest.txt` lists each file path and SHA256. The manifest itself is
  indexed here by SHA256.
- Four child runs are present: `same_process`, `fresh_A`, `fresh_B`, and
  `selected_causal_test_G2`. Each contains its runtime/restart identity and
  process cleanup record.

## Curated tracked summaries

| Artifact | SHA256 |
|---|---|
| `earliest_divergence.json` | `f6f936fba77e7db9c3bd928ee7a7a7b272e9d15184906e93d5228033ee8239f2` |
| `force_comparison.json` | `074495304bcb39d9c5b0902a4c7b50b92002d4178ba63af035408723d189eb82` |
| `qualification_summary.json` | `325ce7899361082c0490653a017a6907b3a8a1858676994454851dd08096fe50` |
| `runtime_environment_verified.json` | `9b3d7a57a3b523c939e476f41ad7a9993b08fbc2c3f5c61f8eba27c0c1d86e4d` |
| `stage_diff.json` | `80045c2f6bcc9e1b2a128806c85c71de42c86e4c67be31f55308e24ecf4a8023` |
| `sha256_manifest.txt` | `192511ab14a9cd120ee561c21f60bace2f1171afbb7da774c797992cd774ab66` |

The complete interpretation is in
`docs/PHASE1K26_EARLIEST_DIVERGENCE_REPORT.md`. The raw archive is a diagnostic
record, not a production restart or run authorization.
