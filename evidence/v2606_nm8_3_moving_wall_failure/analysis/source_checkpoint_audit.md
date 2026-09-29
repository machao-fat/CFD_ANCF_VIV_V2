# NM8.3 read-only source audit

Installed OpenFOAM.com v2606 source: `/usr/lib/openfoam/openfoam2606/src/finiteVolume/fields/fvPatchFields/derived/movingWallVelocity/movingWallVelocityFvPatchVectorField.cxx`.

- `Uwall()` (lines 86–118) derives wall velocity from current face centres, `mesh.oldPoints()`, `deltaT`, and the boundary part of `fvc::meshPhi(U)`. It is not a permanently prescribed zero velocity.
- `updateCoeffs()` (lines 121–136) assigns this computed value when `mesh.moving()`.

Official adapter source checkout: `${LINUX_HOME}/software/openfoam-adapter-v1.4.0`, tag `v1.4.0`, commit `0801887b958f3101389cb719838dc8fc864d5369` (read-only verified). No adapter source was changed.

- `Adapter.C:502–514`: after coupling `advance()`, the adapter reads a checkpoint when required, then writes one when required.
- `Adapter.C:809–820`: coupling iteration time and time index are stored and restored.
- `Adapter.C:828–873`: mesh `points` and `oldPoints` are stored; rollback calls `mesh.movePoints()` and restores `oldPoints`.
- `Adapter.C:880–885, 1397–1439`: mesh motion flux (`meshPhi`) is included in the adapter's mesh checkpoint path, including available old times.
- `Adapter.C:888–909, 1444–1480`: available volume histories `V`, `V0`, `V00` are tracked in the mesh checkpoint path.
- `Adapter.C:1126–1168` and following field loops: registered OpenFOAM fields and available old-time fields are restored.
- `docs/extend.md:98–129`: the official adapter documents the checkpointed field and mesh categories and notes that the checkpoint list is formed once after the first solver step.

These are source-level *intended semantics*, not a bitwise observation of the actual pre-solve state in production window 39. The read-only NM8.3 observer executed after each Fluid solve and before the adapter, so it cannot establish that every rejected trial began with identical `oldPoints`, `meshPhi`, `U.oldTime()` or wall-velocity patch state. The independent fixed-input replay supports repeatability with a fresh preCICE history, but does not close that production rollback evidence gap.
