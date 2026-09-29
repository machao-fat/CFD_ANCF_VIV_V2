# NM4 coupling configuration reference

Read-only local tutorial reference:
`${LINUX_HOME}/software/precice-tutorials-v2606-smoke/perpendicular-flap/precice-config.xml`, lines 47–64.
It uses parallel-implicit, separate relative convergence measures on
`Displacement` and `Force` (each `5e-3`), a 50-iteration ceiling, and IQN-ILS.
The NM4-B configuration preserves the two-measure schema and chooses a
stricter HH06 diagnostic threshold of `1e-3` per data set, a bounded
20-iteration ceiling, one 4e-4 s window per CFD/ANCF step, and 20 windows.
IQN-ILS and all other acceleration are intentionally omitted at NM4-B.
Nearest-neighbor one-point mapping is inherited from the working NM2
official-adapter topology; no RBF mapping is used.

preCICE's max-iteration stop may *advance* a window even when convergence
measures remain false. An advanced window is not counted as qualified
accepted unless both measures actually meet their limits and the
`precice-Solid-iterations.log` convergence flag equals one.

The only NM4-B Fluid solver-control addition relative to NM4-A is
`PIMPLE.checkMeshCourantNo true`, which makes pimpleFoam report the
mesh Courant diagnostic without changing the solution equations.
