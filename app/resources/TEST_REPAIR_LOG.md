# Offline test repairs (2026-09-30)

All fixes stayed in D:\CFD_Work\APP; no production case/solver was used.

1. First pytest basetemp parent did not exist. Created its parent in the same APP
   workspace; conftest now creates it and defaults all tests to that local path.
2. D: WSL DrvFS returned EINVAL for renameat2(RENAME_NOREPLACE). Added Windows
   Directory.Move no-overwrite fallback. Native/generation tests verified it.
3. GUI screenshot showed the embedded MPI spinbox extending over the U_i column.
   Fixed those two column widths and the embedded widget width, with a GUI
   regression assertion; no generation/physics change.
4. First combined GUI regression had a 15 s watchdog, expired during D: copying,
   and test-session teardown destroyed a live QThread. Increased the test-only
   deadline to 60 s and added session cleanup that waits before closing windows.
   The responsiveness assertion still requires event-loop timer ticks during real
   generation. Final results are recorded separately; the initial abort is not PASS.

## Production bridge environment probe and pytest scheduling repair

The initial environment check timed out because OpenFOAM etc/config.sh/setup consumes inherited positional arguments as configuration. The source command passed bashrc as $1 without clearing $@, causing repeated initialization. The APP command builder now saves the executable argv, clears positional arguments before sourcing, then restores the original argv for exec. Only the existing generated production_N5_bridge_dryrun launch manifest/manual instructions were repaired; no new case folder and no production commands were executed. A literal-argument regression test verifies empty configuration args and safe preservation of spaces/shell metacharacters.

The first full-suite run reported 57 PASS / 1 GUI failure. A second pytest was mistakenly started against the same .tests/pytest basetemp, causing concurrent cleanup (smoke also reported an rm_rf error). This result is not acceptance PASS. pytest configuration now owns an exclusive session lock; tests are rerun sequentially in the original APP workspace. Production runtime is untouched.

Final serial rerun: smoke18 PASS in3.45s; full60 PASS in380.90s. Real existing N5 example static/PREFLIGHT PASS and QThread GUI event-loop responsiveness PASS. No solver/decomposition/FSI execution.
