# Phase 1I–1K.22 off-Git raw evidence archive

The complete, previously untracked raw runtime directories were copied **without deleting or changing the originals** into this local archive before selective Git publication:

- Archive: `/home/machao/projects/CFD_ANCF_VIV_V2_offgit_evidence_7CAhfz/phase1i_to_phase1k22_raw.tar`
- Size: `18,802,472,960` bytes
- SHA-256: `dd74ed84e7b2e4f53624987835ba02775b7cab1f3c4757199cf618df2a22a7a9`
- Relative archive root: repository root; members retain `evidence/...` paths.
- Archive entries: `7,890` (files and directories).
- Verification: `tar --compare -f <archive>` returned exit code 0 against the preserved original directories; `sha256sum` returned the digest above.
- Git baseline at archiving: branch `repair/worker-lineage-implicit-contract-v1`, HEAD `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`.

The archive contains the complete local Phase 1I failure record and Phase 1K.5, 1K.9, 1K.10, 1K.11, 1K.13B, 1K.14, 1K.16B, 1K.17, 1K.18, 1K.18.6, 1K.18.7A/B, 1K.20, 1K.21 and 1K.22 evidence trees, including large mesh/restart cases, raw logs, and S0–S5 JSON snapshots. Original directories remain in the workspace. The archive is **local only** and is not uploaded by `git push`.

Git tracks the associated reports, reproducible source snapshots, selected scripts/configuration, small machine-readable qualification summaries and traces. The `.gitignore` rules prevent accidental addition of the complete raw trees; selected evidence files are explicitly staged. A fresh clone needs access to the external archive to re-audit full-field snapshots or raw CFD states. This path is machine-local, so the archive must be transferred separately if another machine needs complete evidence.

To verify the copy later, run `sha256sum` on the exact archive path above and compare it with the recorded digest. To inspect without extracting, use `tar -tf <archive>`; extraction is not necessary for routine Git review.
