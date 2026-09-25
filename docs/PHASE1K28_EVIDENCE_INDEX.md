# Phase 1K.28 evidence index

The complete B0/B1 runtime trees are local evidence archives and are excluded
from Git by the repository evidence policy. They were not deleted or replaced.
The two failed/complete B1 preflight identities are also retained locally; the
failed `run-20260925T113000Z-fc0f94d-b1-g2` contains only the double-`.so`
preflight failure and was never used for runtime conclusions.

## Completed runs

| Run | Role | Runtime result | Physical windows | Participants |
|---|---|---|---:|---|
| `run-20260925T113000Z-fc0f94d-b0` | `OLD_NATIVE_BASELINE_DIAG` | 4 attempts, accepted at iteration limit, not converged | 1 | Fluid/Structure exit 0 |
| `run-20260925T113000Z-fc0f94d-b1-g2b` | `OLD_NATIVE_G2_DIAG` | 4 attempts, accepted at iteration limit, not converged | 1 | Fluid/Structure exit 0 |

Both completed runs loaded the intended separately named adapter and did not
load `libRBFMeshMotionSolver`. Both used the old native
`displacementLaplacian` path and the fixed diagnostic Structure participant.

## Curated artifact hashes

SHA256 values below bind the machine-readable conclusions to the local archive.

| Artifact | B0 SHA256 | B1 SHA256 |
|---|---|---|
| `runtime_identity.json` | `43e22af4a7988d96e91c7192e1b91bdabca3bdaced160551d8a3950e5630a122` | `97431c5ea4d7292022c872b71c2dfb3a7acaebde171f97eb838b19bda316c44` |
| `restart_identity.json` | `0b38f2607279f2bc5812c073b06db930e79498696f87480d4f269def13a7b62c` | `7e0b9bfb817ec71b9ebc7bf0ac47b659f8acdbc8201fc44a865755879d9b7712` |
| `process_cleanup.json` | `f38842d86c2f7749f93db7eacef0840d2f07f1283a9acc034f52b27ce41a7087` | `9cae297f14616a84bca38d3bf8efffff6cc1f6b1dba0f5ab256f6e8fe2517d62` |
| `attempt_alignment.json` | `84ab08b7de54fe72c0e7000ccc82aeaa33b95a7ca20c8573f58f1a20663a5a79` | `a9ae0405dfdc254df0febec7c5e7dad913f273370bb99fa3d3aa1f3c2e88bd81` |
| `force_comparison.json` | `1fcc6f2dd0000c03cfea3c28e62e30105eb0560667d0f2aa08fc2a2a8909c594` | `2b04db8ca274d34b4d2ebcae472ca068080c15b72259a4cd6c738122e40a4aa6` |
| `stage_pair_comparison.json` | `06191d5d3c6eb7999d6ef411fd549655f09265bae5e76e786a78452e13e882fb` | `514f5b44e660d8f8be81b523cbe6fccc92f72721120c61dbdc948c1b1d23f244` |
| `qualification_summary.json` | `5e864ace6de83cce4a3c50c458a56f300b814dfdc02b893889c343acd3ac6bdb` | `5666ac6ce99afb9cce9168a9595340d9b2326b91d30ac71f3e8359955881f556` |
| `source_diff.patch` | `74b783bac8a906a4e926fb8f0fbce252c462c2ebb100b583bcb46fa610ba623b` | `48cf1bc357eec64d885c6f100ff967420b973e4d6526118a45569391f62afb1e` |

The primary displacement pair hash is
`d32bcccbaeeca2e6685266c70dc358dfd0ba7a76ec226990fa27cc741b1fb339`.
The B0 adapter binary SHA256 is
`9dd8fcf861e6dc1d96b6dece84b840fcbe30a1bf317b19293e3b9ec2a73a4579`.
The B1 adapter binary SHA256 is
`0edcfae77d51d8a57a354a1b745c77f6c15108bf532be0d4893394e80a2d785d`.

See the formal interpretation in
`PHASE1K28_OLD_NATIVE_SOFTWARE_REFERENCE_REPORT.md` and the Phase A contract
in `PHASE1K28_OLD_NATIVE_BASELINE_AUDIT.md`.
