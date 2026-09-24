# Experimental OpenFOAM adapter and RBF source snapshots

These are **source-only** snapshots for the Phase 1K experiments, not replacements for the historically qualified Fluid adapter or permission to run production FSI.

| Tree | Provenance | Purpose |
|---|---|---|
| `solids4foam_rbf/upstream` | solids4foam v2.4, commit `1341312f951caf4d8fcc69499c6ce1a588826156` | Upstream RBF source |
| `solids4foam_rbf/of10` | Foundation OpenFOAM-10 port documented in `docs/PHASE1K9_VERIFIED_RBF_SOLVER_INTEGRATION.md` | Phase 1K.9 RBF source |
| `solids4foam_rbf_diag_phase1k18` | Source-only copy of the diagnostic RBF tree used by Phase 1K.20–1K.22, originally under `evidence/phase1k20_point_checkpoint/run-20260924T164027Z-c2245ff-Gu2Hg5/rbf-source/` | Full S0–S5 field/mesh snapshots; **experimental** |
| `precice_adapter_phase1k20` | Source-only copy of the Phase 1K.20 adapter tree, originally under `evidence/phase1k20_point_checkpoint/run-20260924T164027Z-c2245ff-Gu2Hg5/adapter-source/`; source basis is `precice/openfoam-adapter` OpenFOAM10 commit `d53753b1c927b2413b02299c9da15725b3e772f0` plus documented Phase 1K patches | Explicit point-patch checkpoint restore; **experimental** |

The copies exclude nested Git metadata, compiled objects, generated `lnInclude`, and shared libraries. Their own `LICENSE` files are retained. Build and test details are in the Phase 1K.9 and Phase 1K.20 reports. The tested experimental adapter binary SHA-256 was `225ecab227b8271f01119fe476370e3a0b705ca06e1ca3a7739200266499b165`; the diagnostic RBF binary SHA-256 was `508f474654f728503e62e4f7a2c88934800dc73f947353839c52106604a2ca11`. Those binaries are **not** committed.

The historically qualified adapter SHA-256 `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572` has unresolved source-to-binary provenance and must not be conflated with the experimental source above.
