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
