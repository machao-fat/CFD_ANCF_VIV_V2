# APP Prepared Symlink Contract Repair V1

**Classification: VIV_APP_PREPARED_SYMLINK_CONTRACT_REPAIR_PASS**

- Source base: `8b3b6bafd5d042ca1019d6bb23a9961fe5b01bae`; parent: `f66eacd94576b39faa7f08714ebdb3c9dbd1ef0e`.
- Initial branch: `app/run-manager-monitor-v1`; exact HEAD/parent and clean worktree verified before edits.
- Repair branch: `app/prepared-symlink-contract-repair-v1`, created directly from the exact source base.
- Local workspace: `/mnt/d/CFD_Work/APP` (`D:\CFD_Work\APP`).
- Protected main / Run Manager / production bridge refs remain unchanged.

## First causal defect

The original `prepared_identity()` blanket `require(not p.is_symlink(),'Symlink in prepared inputs')` was reproduced read-only against the failed GUI case before any source edit. This is an APP prepared-input contract defect, not an OpenFOAM/preCICE/ANCF/mesh/physics failure. Historical evidence remains unchanged: prior GUI Generate/Static/Preflight passed and five real APP decompose commands exited 0, but fingerprinting failed before coupled launch. This repair phase executed zero real decompositions and zero coupled participants.

## Actual filesystem witnesses

- Failed case: `/mnt/d/CFD_Work/APP/workspace/cases/production_N5_gui_smoke5_v1`.
- Prior successful case: `/mnt/d/CFD_Work/APP/workspace/cases/production_N5_app_smoke5`.
- Exact initial directory: `29.9999999999834372`, read from the existing enrolled profile.
- Both witnesses have five enrolled Fluids and four processors each; all 20 initial-time uniform links in each case use the same relative form.
- Example: `fluid_s0594/processor0/29.9999999999834372/uniform -> ../../29.9999999999834372/uniform`.
- Strict canonical target: the same Fluid serial `29.9999999999834372/uniform`, an ordinary directory.

| Serial uniform entry | Type | Bytes |
| --- | --- | ---: |
| cumulativeContErr | regular file | 1019 |
| time | regular file | 1070 |
| functionObjects | directory | — |
| functionObjects/functionObjectProperties | regular file | 3670 |

Total regular-file content: 5,759 bytes per Fluid. The prior successful case additionally has post-run processor time directories; only its enrolled initial links and small serial metadata were inspected. No historical runtime tree was copied or recursively hashed. Selected configs, reports, metadata hashes and link semantics were rechecked unchanged after the full suite. Read-only host tests also preserve link/file modification timestamps.

## Allowed contract and prepared identity

The small `qualified_uniform_symlink_identity()` helper permits only enrolled Fluid-S1..S5 case names, processor0..3, the enrolled initial directory and leaf uniform. It requires the exact observed relative readlink text, strict resolution, an existing ordinary serial directory, same-Fluid containment and exact target equality. Parent components must be ordinary paths; chained links are refused. Absolute, escaping, cross-Fluid, broken, wrong-time, field/mesh/config and all unexpected links remain fail-closed. Even an equivalent relative spelling with altered raw link text is refused.

Identity records link path, raw readlink, canonical target relative to the Fluid, target type, and full SHA256 plus size for all three metadata files. Each metadata read is capped at 2 MiB; root/nested entries are checked against the exact observed names with immediate refusal of unknown entries. No unbounded metadata recursion is introduced. Ordinary configuration hashing and the existing first/last-4-KiB field/mesh identities remain intact.

Prepare and Run recomputation are equal without changes. The unmodified Run Manager comparison rejects target content drift; invalid link retargets fail the shared contract before any participant launch. Two fake-process lifecycle regressions execute actual RunManager Prepare using only tiny Python commands and verify both forms of drift leave zero participant records and no Run directory.

`check_decomposition()` retains four processors per Fluid, eight required initial fields and five required mesh files, while additionally refusing linked ancestors and inconsistent prepared trees. It and prepared static validation use the same narrow symlink helper. Normal generation validation still forbids all symlinks. Only this named repair branch was added to the existing provenance allowlists; no arbitrary branch bypass was added.

## Offline qualification

| Test | Coverage | Result |
| --- | --- | --- |
| T1 | Twenty valid same-Fluid uniform links; stable Prepare/Run identity | PASS |
| T2 | Absolute link | PASS |
| T3 | Relative escape to an existing external directory | PASS |
| T4 | Another enrolled Fluid target | PASS |
| T5 | Broken link | PASS |
| T6 | Initial U link | PASS |
| T7 | Wrong initial-time location | PASS |
| T8 | polyMesh points link | PASS |
| T9 | system/controlDict link | PASS |
| T10 | Post-Prepare link retarget / altered raw text | PASS |
| T11 | Post-Prepare nested uniform metadata content change | PASS |
| T12 | Ordinary inputs retain bounded identities and required fields/mesh | PASS |
| T13 | Failed real GUI case: twenty links, decomposition/identity/prepared static validation read-only | PASS |
| T14 | Previous successful real case: twenty original initial links read-only | PASS |

Ten additional regressions cover nested target links, unknown/oversized metadata, system/processor parent links, wrong rank/profile/initial/enrollment and broken config links. T13/T14 ran against available host artifacts; neither was skipped.

Commands from `/mnt/d/CFD_Work/APP/app`:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -m smoke
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
```

- Final fast/smoke suite: **58 PASS**, 60 deselected, 201.82 s.
- Focused escape/Run-gate follow-up: **3 PASS**, 54.27 s.
- Full APP regression: **118 PASS**, zero failures/errors/skips, 506.27 s.
- All original 92 tests retained; 26 added. Existing production locks, generator, preflight, state machine, parser, owned-process/Abort and GUI responsiveness checks remain PASS.
- Pytest elapsed times above include harness overhead; JSON also records exact JUnit suite times.
- Local evidence: `/mnt/d/CFD_Work/APP/workspace/evidence/viv_app_prepared_symlink_contract_repair_v1`. Includes original defect reproduction, real witness snapshot, read-only prepared static report, JUnit reports and final safety verification. Runtime/test bulk stays ignored.

## Files changed

- `app/viv_app/runner/prepared_symlinks.py`
- `app/viv_app/runner/contract.py`
- `app/viv_app/generator/production_validation.py`
- `app/viv_app/generator/validation.py`
- `app/tests/fixtures/fake_n5_decomposition.py`
- `app/tests/test_prepared_symlinks.py`
- `APP_PREPARED_SYMLINK_CONTRACT_REPAIR_V1_REPORT.md`
- `app/resources/prepared-symlink-contract-repair-v1-summary.json`

State/process/Abort/monitor implementation, UI/QSS, production profile descriptor, production generator/XML/preflight and protected refs were compared with the frozen base and remain unchanged. No production solver source, binary, adapter, mathematics, scaling, mesh, numerics, dt, positions, MPI topology or CPU masks were changed.

## Limitations and next phase

The whitelist intentionally supports only the observed enrolled metadata tree and initial time. Fresh prepared processors allow only constant and the selected initial directory; completed-case reuse/restart is unsupported. Existing field/mesh sample identities remain bounded and do not claim to detect changes confined outside their sampled ranges. This host uses a 9p APP mount; the fast suite exceeded 30 s, and no acceptance test was removed to hide the timing.

This is offline software repair qualification. A new real GUI smoke was not run, and the historical failed case was not repaired in place, retried or relabeled. UI redesign was not started.

**Authorized next phase: VIV_APP_UI_UX_CN_V1 — offline UI/UX work only, subject to the separate phase instruction. STOP here.**

- REAL_CFD_STARTED = NO
- REAL_DECOMPOSEPAR_STARTED = NO
- PRODUCTION_SOLVER_CHANGED = NO
- HISTORICAL_EVIDENCE_MODIFIED = NO
