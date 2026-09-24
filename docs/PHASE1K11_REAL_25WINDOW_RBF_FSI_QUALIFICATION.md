# Phase 1K.11 — real 25-window RBF + IQN FSI stress qualification

## Decision

**REVIEW_REQUIRED.** The sole authorized 25-window run reached global time 30.005 s with both participants exiting normally, practical IQN iteration counts, no NaN/Inf, positive saved cell volumes, and no historical Courant/turbulence/solver crash. The Structure-side implicit contract passed. However, a PASS for the **RBF ALE physical response** is not justified: large *rejected-trial* pressure/force spikes recur and grow through window 25, while every saved accepted-window mesh point coordinate is identical to the release mesh despite nonzero accepted structural interface displacement. These are observations, not yet an established root cause. Do not adopt this mesh/ALE case for production or start another run until the Fluid displacement-to-mesh path is audited.

This is a bounded stress test, not HH06 validation, VIV reproduction, or production readiness. No source, physics, IQN, timestep, convergence, or solver setting was tuned during the run. No rerun was made.

## Run and provenance

- Git branch: `repair/worker-lineage-implicit-contract-v1`; HEAD: `c2245ff396ff42dfa5e80fee6555a9ede93e3b04`. Tracked source/config tree was clean. The complete `git status` was **not** clean because accepted earlier phase reports/evidence and the new run artifacts were untracked. No commits were made.
- Run: `evidence/phase1k11_25window_rbf_fsi/run-20260924T095422Z-c2245ff/`. Preparation and read-only reduction: `evidence/phase1k11_25window_rbf_fsi/staging-20260924T093404Z-c2245ff/`. Scratch case only; the authoritative old-mesh case was not replaced.
- Start: independent copy of the unadvanced Phase 1K.10 `mapped_candidate_30`, **not** `fluid_only_100/30.02`. All `30/` field and mesh hashes were checked against the frozen scratch provenance in `runtime_identity.json`; global restart time 30.0 s. A second independent time-30 force replay reproduced the Phase 1K.10 forces output byte-for-byte (SHA256 `f29486df3a3a22b874bf04bb5404c1e9c3a95327b7b184add60518002283bb2b`).
- New-mesh F0 raw (N): `(0.0655270406896, 0.05872987414832, -2.10307854575e-21)`. First Structure read: `(0.06552704068997028, 0.058729874147876754, 0)`; x/y discrepancies are below `5e-13` N. The interface is 2-D, so the negligible Fz is not exchanged. The single existing conversion is `F_strip = F_raw / 0.028 * 1.98`.
- Runtime: OpenFOAM Foundation 10, preCICE 3.4.1, `/usr/bin/python3.10` with pyprecice metadata 3.4.0. Worker source SHA256 `c6dd29f344a506deb7c1d06d0b408dc1f504ad8d67259b7c2f3b24e16a0b759e`, worker binary SHA256 `3d4a4eaa8c13856a1616e7672866a1ac8bec2c7dda1c194fa2c549ab3f564596`; adapter SHA256 `26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572`; RBF SHA256 `b27b347c4ba3026a495517ae7ae237ceb5cd8408ac0db9af6a58ccd83647a20c` (Build ID `f5ba43436c00f75dd314136806e0a00c632d0d58`). `/proc` confirmed the Fluid loaded this RBF library, pinned adapter and `libprecice.so.3.4.1`. Adapter source-to-binary lineage is still unresolved; the exact binary is pinned.
- Scratch XML SHA256 `5677253184dad62649157b8b29f16ca5f0b2cee714500331b2464380903ced02`: frozen IQN-ILS `initial-relaxation=0.2`, `max-used-iterations=1`, `time-windows-reused=1`, residual-sum, QR3 `1e-2`, reduced-time-grid; `dt=0.0002`, `min-iterations=2`, `max-iterations=20`, `max-time-windows=25`. RBF TPS dictionary SHA256 `0ffeeac3d86ccfce4f6468371c188d50f70342b77ea0e8bff61b0e6f36519f78`.
- One prelaunch `checkMesh -allTopology -allGeometry` passed. Preflight: `PASS_PREFLIGHT_ONLY`. The independent scratch runner enforced identity, exact window bound, Structure trace, Co thresholds and saved-volume positivity. It was validated offline against the preserved Phase 1I bad Co and negative-volume evidence. No production launcher/config was edited.

## Coupling execution

Completed windows: **25/25**; no window 26. Iterations per window:

`[4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5]`

There were 124 coupling attempts, 99 rollbacks, 124 CFD advances, 124 ANCF solves and 372 ANCF Newton iterations. No window was accepted at the iteration cap; `iterations.log` convergence flag is 1 for each window. Wall-clock time: **62.8104 s** (2.5124 s/window; 0.5065 s/attempt). Structure and Fluid exit codes: 0/0. Worker disappeared after Structure shutdown; its independent exit code is not exposed. No participant/worker orphan, stale socket file, or held launcher lock remained.

All 124 `D_written_to_precice` vectors equal the corresponding `D_trial_interface` vectors. The first ANCF trial used physical time-30 F0. On every retry, `relativeReadTime=dt` and the ANCF input Force equals the preceding advance's returned Force; at accepted boundaries the next-window input is inherited with read offset zero. Physical identity advances once per window, transport IDs remain strictly increasing, and physical rollback/commit trace checks passed. Maximum trial interface displacement norm (x/y) was `1.1298695976391279e-4 m`; maximum full ANCF trial vector norm including z was `4.313710574513627e-4 m`. Maximum applied strip Force norm *in the Structure attempt trace* was `1539.1716475 N` (a rejected trial, not an accepted release load).

IQN `iterations.log` reports 1 retained column at each accepted window, 0 deleted columns, and a cumulative 98 dropped columns by window 25. Fluid log contains 24 preCICE warnings that a coupling residual is almost zero (one in each of windows 2–25); these did not prevent convergence but must not be silently called warning-free. The generated `convergence.log` per-data zero-column anomaly remains known; primary evidence here is detailed convergence messages, `iterations.log`, and Structure attempt traces.

RBF coarsening selected 20 of 846 candidate points. At the start of window 2, one logged interpolation `max(error)` reached `452.208` and triggered `reselection=true`; the immediate reselection reduced it to `0.012917` against `tol=0.05`. This single pre-reselection diagnostic is preserved rather than interpreted as a mesh-quality result. Later reported errors remained near `0.01349`.

## Fluid, ALE and first-window observations

| Metric, across available attempts | Phase 1I old mesh + Laplacian | Phase 1K.11 new 6D O-grid + TPS RBF |
| --- | ---: | ---: |
| Accepted windows / failure | 20; window 21 Fluid SIGFPE (GAMG) | 25; no crash |
| Attempts / wall clock | 99 / 111.119 s | 124 / 62.810 s |
| Maximum Fluid Co | 21.4545 | 0.389960 |
| Maximum mesh Co | 21.3015 | 1.730620 |
| Maximum reported `|U|` (m/s) | 33.1658 | 0.901710 |
| Maximum omega | `4.57795e11` | `9.38073e4` |
| Largest direct cylinder-force x/y norm, **all trials** (N) | 81.3681 | **109.1891** |
| Minimum saved cell volume (m³) | `-1.19833e-10` | `7.68736e-10` |
| Max non-positive cells in a saved field | 33 | 0 |
| Solver SIGFPE | Yes | No |

The new first-window mapped-field startup transient was visible: post-processing `max(p)` reached `4.5318815932 m²/s²` at the first 30.0002 s trial, and direct cylinder-force norm peaked at `0.20648 N` in window 1, then returned near the initial-force scale on accepted iterations. This is comparable to the Phase 1K.10 fixed-cylinder startup observation; no abort was warranted solely from that first transient.

Across all trials: `p_min=-91.2586`, `p_max=84.5489 m²/s²`; `k_min=2.65285e-10`, `k_max=0.0157853`; `omega_min=1.98844`, `omega_max=93807.3`; `nut_min=2.82841e-15`, `nut_max=2.78344e-4`; `|U|_max=0.901710 m/s`. Selected accepted-window `checkMesh` at 1, 5, 10, 15, 20, 25 returned `Mesh OK`, max non-orthogonality `43.8460°`, max skewness `0.896980`, and minimum volume `7.68736e-10 m³`. No NaN/Inf or non-positive volume was found. The direct OpenFOAM force-history maximum was at a **rejected window-25 trial**: `Fx=-84.212097857469 N`, `Fy=-69.502386186349 N`, x/y norm `109.189097950081 N`. It is not the accepted Force or F0.

**Critical unresolved observations:**

1. The first returned Force iterate grows from `0.106 N` in window 1 to `21.766 N` in window 25, then the accepted returned Force is only `0.08988 N` at window 25. At the first window-25 trial, the direct `cylinderForces` output reaches `109.189 N`; the mapped Force read by Structure is about `21.766 N`. The two force channels differ markedly for these large rejected trials; this difference has not been reconciled. The repeated large first-attempt transients are not an accepted-state blow-up, but they preclude a simple claim that the stress mechanism disappeared.
2. Every accepted-window saved mesh `points` binary has coordinates **exactly equal** to the release `constant/polyMesh/points` (only file headers/locations change), whereas every accepted Structure trace has a nonzero x/y trial displacement. The saved `pointDisplacement` cylinder boundary at 30.005 s is also uniform zero. Mesh Co nevertheless reaches 1.73 in rejected attempts. The current evidence does not establish whether the RBF motion was correctly applied during attempts and then reset by the lifecycle, or whether there is a Fluid-side displacement application defect. Per-attempt mesh velocity maximum is unavailable; the accepted-window point-difference estimate is zero and must **not** be mislabeled as the runtime maximum.

The historical failure region was traversed without the old non-positive-volume/SIGFPE chain. This demonstrates bounded runtime survival, **not** that the RBF mesh correctly follows the accepted structural displacement or that it causally fixes long-run instability. Mesh geometry, ALE method and mapped release field changed together, so the historical comparison is not a single-variable RBF experiment.

The live force-growth guard watched consecutive Structure-returned Force iterates, not the independent OpenFOAM `forces.dat` channel. The recurring first-iterate spikes rose across windows rather than meeting its two-consecutive-`>3×` trigger. Thus completion is **not** evidence that the large direct-force channel was live-qualified against an absolute limit; this observability gap is part of the review decision. No retrospective tuning or second run was performed.

## Evidence and stop condition

Machine-readable artifacts in the unique run directory include `runtime_identity.json`, `qualification_summary.json` (runtime completion only), `qualification_assessment.json` (scientific classification), `structure_trace.jsonl`, `structure_audit.json`, `fluid_metrics.json`, `rbf_metrics.json`, `iqn_metrics.json`, `coupling_contract_metrics.json`, `mesh_identity.json`, `restart_identity.json`, `new_f0.json`, `historical_comparison.json`, `wall_clock_timing.json`, `process_cleanup.json`, both participant logs, preCICE iterations/convergence logs, direct cylinder force history under `case/postProcessing`, and selected checkMesh logs. The reduction script is in the separate staging directory and does not mutate the runtime case.

**Next action:** a read-only, attempt-level forensic audit of the Fluid adapter's Displacement → pointDisplacement → RBF mesh-coordinate lifecycle and the direct-force versus preCICE Force discrepancy. Do not tune, rerun, use 30.02 s, adopt the new case as production, or proceed to long-duration/multislice FSI on this evidence alone.
