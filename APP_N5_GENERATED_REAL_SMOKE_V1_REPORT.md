# APP N5 generated real smoke V1

Final classification: **VIV_APP_N5_GENERATED_CASE_REAL_SMOKE_PASS**.

Executed APP commit: `15810855ca6b28c0dfcd1386cbb3fe24bdfe822c`; branch `app/production-baseline-bridge-v1`. APP source hashes match that commit. Production kernel, adapter, mapping, coupling mathematics and solver numerics were not modified.

Production profile: `v2606-n5-implicit-production-v1`; SHA256 `d00847f915e32862a86367bf770e4b28b77f045bfed379982476f42e6f01a3be`. Qualified Structure SHA256 `a97c82657fb99ba838c3966e5bd0bc2bd943af9741278662ddaf0109fc08df33`; adapter SHA256 `51bf2889e5aab6867d17b78764faacecb2f467102f925332467b8b188b1cbed9`. Actual runtime: OpenFOAM v2606 / preCICE 3.4.1. P1 selected state SHA256 `eecbb21d25a4b68097cd9d1fd1d042dbbcb12752d911669f103ad9cbddb4e083`; XML SHA256 `c6c29dd97fbf45fb8a922405510556c4f31a656432b17da41d410f7670ab226d`.

Generated case: `/mnt/d/CFD_Work/APP/workspace/cases/production_N5_app_smoke5` (`D:\CFD_Work\APP\workspace\cases\production_N5_app_smoke5`). Per user instruction, this task's previous interrupted case was overwritten in the same directory after verifying it was unused. This was regenerated fresh from selected frozen30 directory `29.9999999999834372`, with no continuation. The previous 2/5-window attempt evidence remains preserved and contributes nothing to this PASS.

Pre-run Static Validation / Production Preflight: **PASS / PASS**, saved as `pre_run_static_validation.json` and `pre_run_production_preflight.json`. Manual document and manifest audit parsed all 11 command blocks: 5 decompose, 1 Structure, 5 Fluid MPI. Five decompositions all exit **0**, each has 4 processors and complete selected initial fields. Six handshakes and six natural exit codes: **Structure=0; Fluid-S1=0; Fluid-S2=0; Fluid-S3=0; Fluid-S4=0; Fluid-S5=0**.

N5 positions `[0.594, 1.782, 2.970, 4.158, 5.346]` m; uniform U=0.31 m/s; MPI `[4,4,4,4,4]`. CPU sets: Fluid-S1 0–3; S2 4–7; S3 8–11; S4 12–15; S5 16–19; Structure 20. No pre-existing process received a control operation. Observed new pimpleFoam masks and loaded adapter identity agree with the generated contract.

**5/5 strict accepted windows**, dt=0.0004 s; duration=0.002 s. Exact requested Fluid final time `30.0019999999834372` (native float `30.001999999983436`); actual final fields follow OpenFOAM's 18-digit directory formatting. Qualified Structure clock starts at 30.0 s, differing from Fluid initial time by 1.65628e-11 s. Startup through final observed natural exit took **46.03 s**; no long-run stability or physical validation is asserted.

| Window | Structure physical time [s] | Iterations | Max force relative residual | Max displacement relative residual |
| --- | --- | --- | --- | --- |
| 1 | 30.0004 | 7 | 0.000554167168 | 0.000303406192 |
| 2 | 30.0008 | 7 | 0.00134039915 | 4.8889255e-07 |
| 3 | 30.0012 | 6 | 0.00488552382 | 1.98531196e-05 |
| 4 | 30.0016 | 5 | 0.00447313533 | 1.05298304e-06 |
| 5 | 30.0020 | 7 | 0.00380319998 | 1.34009663e-06 |

Each accepted window satisfied all 10 qualified relative convergence measures, limit 0.005. **Forced acceptance=0**. Attempts=32; rejected attempts / rollback transitions=27 / 27. All rejected transitions restore q/v payload hashes and elapsed clock; each attempt performs one global ANCF advance and contains five finite raw force inputs and displacement candidates. 160 state-payload hash checks pass. Whole-State qddot restoration is supported by unchanged qualified binary/source, not independently requalified from unlogged qddot values.

Mapping identity: **PASS**, `PiecewiseLinearDistributed / NearestConstant`, active region `[0,5.94]` m. Exactly-once `Fraw / 0.028` conversion error maximum **0**; APP performs no second conversion. Fluid force observer attempt counts match; all active wall input streams evolve. IQN exchanges relaxed values, so candidate-to-input bitwise equality is not asserted. All 73 bounded baseline key files remain unchanged; XML comparison permits only approved socket path and five-window horizon changes. NM12 semantic comparison passes; trajectory bitwise equality is neither required nor claimed.

Fluid health: **PASS**. Maximum Co **0.8822924897**, maximum mesh Co **0.007899289252**; no FATAL/FPE/NaN/Inf/negative-volume markers, final required binary fields finite on all 20 ranks. Final accepted-state parallel checkMesh: all five exit **0**, all five **Mesh OK**.

Nonfatal warnings: v2606 announces allowSystemOperations and automatically raises timePrecision 12→18 for the exact initial directory; preCICE issues **7 IQN-ILS column-count conditioning warnings**. All five windows strictly converge; these warnings are retained without changes to IQN settings. Bootstrap relative displacement residuals are `inf` on the first zero-displacement comparison; accepted residuals and physical state/fields are finite. No fatal anomaly occurred in this completed attempt.

Evidence: `/mnt/d/CFD_Work/APP/workspace/evidence/viv_app_n5_generated_smoke_v1/attempt_02_parallel` with generation/preflight/decomposition/logs/coupling/fluid_health/comparison and `final_classification.json`. Task-level latest classification: `/mnt/d/CFD_Work/APP/workspace/evidence/viv_app_n5_generated_smoke_v1/final_classification.json`. Prior interruption reports/classification/raw logs remain under the parent evidence directory. Git saves this report and `app/resources/n5-generated-real-smoke-v1-summary.json`; processor directories, meshes, raw logs and state payloads remain ignored.

**STOP** after this five-window test. No GUI RUN button, serial/N3/arbitrary-N run, solver repair, extended run, restart, monitoring or postprocessing development was performed.
