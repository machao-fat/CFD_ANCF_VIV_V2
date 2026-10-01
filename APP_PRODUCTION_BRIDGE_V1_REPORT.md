# VIV_APP_PRODUCTION_BASELINE_BRIDGE_V1

Classification: **VIV_APP_V2606_N5_PRODUCTION_BRIDGE_READY**

- Branch: `app/production-baseline-bridge-v1`.
- Base: `333cbb8f0defce230c5d881bcb008779ba00b972`.
- Workspace: `D:\CFD_Work\APP` (`/mnt/d/CFD_Work/APP`).
- Authoritative baseline: NM12 fresh frozen30 N5 x 4-rank distributed-mapping diagnostic100, classification **V2606_NM12_N5_4RANK_DISTRIBUTED_MAPPING_DIAGNOSTIC100_PASS**.
- Detailed read-only audit: `app/resources/V2606_N5_PRODUCTION_BASELINE_AUDIT.md`; explicit answers A–L, identities, launch arguments, initial-state and I/O contracts.
- NM13/NM13.1 available reports classify configuration/data readiness and say REAL_LONG_RUN_STARTED=NO; they are not treated as completed long-run evidence. NM12 is the successful qualification authority.

## Delivered capability

New evidence-gated `v2606-n5-implicit-production-v1` profile coexists with original explicit offline profile. Import verifies actual NM12 PASS gates/exit codes, enrolled hashes and recorded Structure/adapter/software/mapping identities. Production naming is Fluid-S1…Fluid-S5 and Structure, with per-slice Force-Si/Displacement-Si and Fluid-Mesh-Si/Solid-Si. N5 positions, structural physics, initial state, dt and four ranks/slice are locked because the qualified binary compiles these values; it does not consume arbitrary-N manifest input.

GUI supports production profile selection, three flows, endTime, integer timeStep writeInterval, purgeWrite, Generate/Static Validate/Production Preflight and Open Folder. Physics values are visible and locked. File work and environment preflight run in QThread. No RUN/STOP/restart/monitor/results pages were added.

Generator copies only system/constant and the explicitly selected frozen30 serial time, extracts the original P1_REF_NE32 CASE/Q record unchanged, and references the immutable external NM12 Structure executable. Native physics, source, adapter and force conversion are untouched. Structure config/compiled model JSON are observational launch/provenance witnesses, explicitly not physics inputs to the executable. Fraw/.028 remains exactly once in the existing distributed mapper.

XML comes from the actual NM12 implicit multi/IQN-ILS template. Standard parser namespaces preserve lexical preCICE names. Semantic comparison allows only window horizon/socket relocation; convergence, mappings, exchanges and acceleration retain identity. Native precice-config-validate also PASS.

Precise field edits update U/inlet/value and apply the established production movingWallVelocity preparation to the serial U cylinder boundary. Internal fields and old-time files stay inherited. forceCoeffs magUInf follows U_i; zero-flow coefficients are disabled through OpenFOAM's enabled flag to avoid undefined normalization, with native integrated forces/FSI retained. Observer output paths become case-local; their libraries remain pinned external dependencies.

Launch manifest contains real Structure argv, state/config/cwd/logs, v2606 environment, all five MPI commands, disjoint CPU layout, expected six participants and startup order. It generates commands only. External solver/libraries are not copied or rebuilt.

## Real generated example and readiness boundary

Example: `D:\CFD_Work\APP\workspace\cases\production_N5_bridge_dryrun` (~78.6 MiB), Uniform U=.31, N5, 4 ranks each, 100 windows, fluid endTime=30.04, timeStep/20 purge2.

- STATIC_VALIDATION = **PASS**.
- PRODUCTION_PREFLIGHT = **PASS**.
- PRODUCTION_LAUNCH_READY = **YES**.
- REAL_FSI_STARTED = **NO**.
- OpenFOAM/preCICE/Structure/MPI simulations executed = **NONE**.
- decomposePar/reconstructPar/checkMesh executed = **NONE**.

Readiness means complete **serial input + validated manual preparation/launch commands**. No processor* is copied. After human review the user must first execute the five generated decomposition commands in `MANUAL_LAUNCH.md`, then launch Structure and the five Fluids manually. No automatic launch or smoke was performed. This is fresh frozen30 release, not a restart. No new physical accuracy or long-duration convergence is claimed.

Preflight verifies v2606 environment, preCICE3.4.1, adapter and external binary/library hashes, linker dependencies, real six-participant implicit XML, meshes/fields, fixed positions/model witnesses, MPI sum20, disjoint available CPU0–20, writable output and disk warning. Every gate must pass before ready=true; failed revalidation clears prior readiness. APP generation and preflight identities are separately recorded.

## Tests and repository hygiene

Smoke: **18 PASS, 3.45 s**, including flow profiles, structural locks, literal P1 selection, implicit XML whitelist/tamper rejection, native launch argv, exact binary boundary edits, zero-flow diagnostic guard and fail-closed preflight. Full acceptance: **60 PASS, 380.90 s**; recorded in `app/resources/production-bridge-full-tests.txt`. Original N1/N3/N5 and byte-identical baseline acceptance all PASS, with no tests deleted.

Actual qualified GUI integration: **PASS**; production preflight through QThread PASS, 1280 event-loop timer beats during checking. Screenshot `app/resources/production-bridge-gui-preview.png`; details `production-bridge-gui-acceptance.json`. Existing N1/N3/N5 offline generation and baseline byte-identity acceptance tests remain in the full suite. Production baseline before/after selected key hashes and bounded selected field/mesh identities match; no historical runtime scan.

The first environment probe timed out because OpenFOAM setup consumed inherited shell arguments. Fixed in existing APP code and the same generated example; regression confirms zero setup args and literal command argv. A first full run had a GUI failure when an accidentally concurrent pytest cleaned shared basetemp; it was not recorded as acceptance PASS. Session locking and serial rerun correct this. Repair details remain in `app/resources/TEST_REPAIR_LOG.md`.

Generated synthetic cases are removed from Git tracking with local files retained. All `workspace/cases/*` are ignored except `.gitignore`; minimal synthetic fixtures moved to `app/tests/fixtures/`. No real production baseline, mesh, binary or runtime is newly tracked. No production source/kernel/adapter/coupling mathematics, completed runtime, main or diagnostic branch is modified. No main merge or PR.

## Limits and APP command

N3/arbitrary-N production, changed positions/ranks/physical parameters, changed dt, cross-process restart, monitoring, postprocessing and packaging are not supported. External NM12 solver/adapter/observer libraries and original source configuration are required for identity/preflight; the profile is currently enrolled for this WSL host. Long-run I/O/physics must be reviewed by the user. The original generic explicit structural-launch gap remains visible in its own offline profile.

```bash
cd /mnt/d/CFD_Work/APP/app
.venv/bin/python -m viv_app
```

After delivery STOP; wait for human review. No real N5 smoke, RUN button, monitoring, restart, postprocessing or arbitrary-N phase begins.

## Documentation provenance clarification (VIV_APP_N5_GENERATED_CASE_REAL_SMOKE_V1)

NM13/NM13.1 readiness records themselves do not prove a completed run and remain historically unchanged; later NM14-series evidence documents postprocessing of a subsequently completed long run.

Read-only corroboration: `evidence/v2606_nm14_n5_long10s_postprocessing/comparison/final_classification.json` = `V2606_NM14_N5_LONG10S_POSTPROCESS_PASS_WITH_LIMITATIONS`, numerical_long10s_health=PASS; subsequent `v2606_nm14_2_modal_cl_correction` documents corrections to this completed-run postprocessing. Their cfd_or_precice_executed=false / real_simulation_started=false flags describe the postprocessing tasks, not absence of the previously completed production run. All historical JSON is unchanged. NM12 remains the APP profile qualification authority.
