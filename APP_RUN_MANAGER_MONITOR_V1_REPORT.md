# VIV APP Run Manager / Monitor V1

Final classification: **VIV_APP_RUN_MANAGER_OFFLINE_READY**.

Branch: `app/run-manager-monitor-v1`. Base: `f66eacd94576b39faa7f08714ebdb3c9dbd1ef0e`, created from the authoritative APP branch. Local worktree: `/mnt/d/CFD_Work/APP` (`D:\CFD_Work\APP`). Tests ran against the implementation working tree before its commit; the exact APP source hashes are in `app/resources/run-manager-offline-acceptance.json`.

**Real CFD started in this task: NO.** Only tiny Python fake participants ran. The prior N5 generator qualification is retained, not repeated. Production kernel/source/binary, adapter, mapping, force scaling, coupling mathematics, meshes, PIMPLE, IQN, turbulence and dt were not modified. No process that existed before this task received a control operation.

## Changes

* `app/viv_app/runner/{state,config,contract,processes,manager}.py`, `run_options.json`, `__init__.py`: explicit states, strict manifest parsing, preparation, background supervision, owned-process control and provenance.
* `app/viv_app/monitor/{models,structure_parser,fluid_parser,run_monitor}.py`, `__init__.py`: structured parser events, accepted-only progress, rolling ETA and bounded histories.
* `app/viv_app/ui/main_window.py`, `run_page.py`, `theme.qss`: Case Setup / Run navigation, Prepare/Run/Abort gates, six participant rows, metrics, three native plots, bounded collapsible Events, errors and full-log access.
* `app/viv_app/generator/{production_validation,production_preflight,validation}.py`: allow this APP branch in provenance; explicit prepared validation accepts exactly four complete processor directories per slice. Default generation checks still refuse copied processors. Existing production semantic/identity gates remain authoritative.
* `app/tests/test_run_manager.py`, `test_ui.py`, `fixtures/fake_participant.py`, `fixtures/run_monitor/`: lifecycle/failure/abort/monitor/GUI tests and tiny qualified-log grammar excerpts. No real baseline mesh/runtime committed.
* `app/pyproject.toml`, `app/README.md`: psutil dependency, packaged run options, current workflow and limitations. Small acceptance JSON, test transcripts and an explicitly offline UI preview are in `app/resources/run-manager-*`.

## State and execution model

Normal path: CREATED → VALIDATED → PREFLIGHT_PASSED → PREPARING → PREPARED → STARTING → HANDSHAKING → RUNNING → COMPLETED. Failures enter FAILED; Abort goes ABORTING → ABORTED, or FAILED if owned-process cleanup fails. Illegal transitions and terminal handle reuse are rejected.

Only `v2606-n5-implicit-production-v1` is executable: fixed N5, four ranks per Fluid, dt=0.0004, qualified positions and CPU masks. Commands/cwd/environment are read from `launch_manifest.json` and checked against existing production validation. The successful smoke harness was read to confirm Structure first, then Fluid-S1…S5 without waiting for an individual participant to connect before starting the next. GUI never assembles solver commands.

Prepare runs static validation and Production Preflight, then five manifest decompose commands in the supervisor thread. It checks five zero exits, four processors per slice, eight required initial fields and five mesh files on each processor, and saves `preparation_result.json`. Run rechecks prepared validation/Preflight and compares manifest/config/source hashes plus bounded processor input identities. Run is enabled only after Prepare PASS. An exclusive case lock prevents concurrent ownership; already executed cases are refused without changing their runtime.

Processes use argv arrays, manifest cwd/environment, independent sessions and disk stdout/stderr. PID birth time authenticates each root/descendant. Startup waits for six actual preCICE handshake markers with a configurable timeout (default 180 s). Six zero exits alone do not imply success: target strict accepted windows, handshake, committed journal clock/order/count and Structure final attempt count must agree. Window deficit fails with FAILED_INCOMPLETE.

Abort sends SIGTERM only to authenticated process groups/descendants created by this manager, waits the configured grace period (10 s), then SIGKILL only to remaining owned processes. GUI close while active uses the same cleanup. No kill-by-name command, global PID enumeration, unrelated CFD control or stale-lock takeover is used. The unrelated dummy process remains alive in the Abort tests. The UI states **ABORTED RUN MAY NOT BE RESTARTABLE**.

## Observation and evidence

Parsers use actual NM12 `NM9_ATTEMPT` / `NM9_FINAL`, preCICE 3.4.1 relative convergence/handshake grammar, and OpenFOAM v2606 time/Co/mesh Co/continuity/solver residual grammar. ANSI, partial lines and split UTF-8 are handled. Native bootstrap relative residual `inf` with zero normalization and conv=true is preserved; accepted markers require the ten qualified converged residuals. APP adds no force conversion or physics.

Live values: accepted physical/coupled time, accepted/target windows, current coupling iteration, force/displacement residuals, rejection count, cumulative maximum Co/mesh Co and originating slice, elapsed wall time and ETA. Only accepted windows advance progress. ETA is warming up below 20 windows and thereafter uses the latest 50 acceptance timestamps, labelled ESTIMATE. Three QPainter plots retain at most 500 accepted points; Events retains at most 2000 lines. Complete parser events are appended and flushed to disk JSONL.

Resource sampling is every 1 s: own solver CPU/RSS, aggregate system CPU/RAM and free disk. Descendant discovery reads only `/proc/<authenticated-own-PID>/task/*/children`; it does not call psutil's global process enumeration. Summed CPU may exceed 100% across cores; summed RSS includes shared pages.

Actual launches create `runtime/run_<UTC timestamp>_<id>/` with `run_manifest.json`, `participants.json`, `runtime_monitor.jsonl`, `run_result.json`; full stdout/stderr are under `runtime/logs/`. Records include APP/profile/generation/preflight/preparation/launch identities, argv/environment/CPU masks/PIDs/start/end/status/exits, acceptance/rollback/Co/warnings/abort state and first observed failure. Test runtime remains ignored under `workspace/cases/.tests`.

## Offline acceptance

| Check | Result |
| --- | --- |
| State transitions and terminal reuse rejection | PASS |
| Manifest topology/argv/cwd/CPU/profile/dt/startup validation | PASS |
| Prepare checks and changed-input launch refusal | PASS |
| Six fake participant lifecycles and five-window completion | PASS |
| Actual log excerpt replay, partial/malformed/UTF-8 parsing | PASS |
| Accepted-only progress, rolling ETA and bounded history | PASS |
| Own PID-tree CPU/RAM sampling | PASS |
| Abort own processes only; unrelated process unaffected | PASS |
| Slow startup, nonzero/fatal exit and incomplete run fail closed | PASS |
| GUI responsiveness and close-while-running cleanup | PASS |
| Repeated fast file-worker failures and worker cleanup | PASS |

Full regression: **92 passed in 156.22 s**, pytest exit=0; original acceptance tests retained. Fast suite: **34 passed, 58 deselected in 14.94 s**, exit=0. GUI-specific subset: **4 passed in 12.74 s**, exit=0; the new repeated-failure regression also passes in the full suite. Transcripts: `app/resources/run-manager-full-tests.txt`, `run-manager-smoke-tests.txt`, `run-manager-gui-tests.txt`.

A development regression exposed QThread deferred-deletion/fast-failure cleanup. File operations now use a retained Python background thread and GUI-owned signal object, with explicitly queued GUI callbacks and release only after the thread returns. The final full run completed and exited normally. This did not involve a production solver repair or runtime change.

## Limits and stop boundary

Run Manager has **offline acceptance only**, not GUI-driven real N5 smoke qualification. Fake fixtures cannot prove real MPI teardown, startup timing or production execution performance. Production Preflight and immutable external artifacts remain mandatory at actual Prepare/Run time.

V1 requires qualified WSL/Linux; native Windows cannot execute this Linux manifest. Prepare and Run must occur in one GUI session. There is no adoption of old prepared/running cases, stale-lock recovery, retry, restart, continuation or committed-state stop. Forced GUI/host failure preserves already flushed events but is not a managed crash-recovery service. Large input identity checks are bounded samples, not full-file cryptographic proofs. Residuals have stdout precision; rollback count observes qualified rejection markers without requalifying kernel state mathematics. Co plotting reflects logged cumulative maxima available when an acceptance is observed.

No Results, postprocessing, FFT, curvature, modes, riser animation, ParaView, mesh generation, N3/arbitrary-N production, installer/exe or database was added.

Run APP:

```bash
cd /mnt/d/CFD_Work/APP/app
.venv/bin/python -m viv_app
```

**STOP.** No real GUI N5 smoke was started. Await human authorization for the next five-window GUI-driven smoke.
