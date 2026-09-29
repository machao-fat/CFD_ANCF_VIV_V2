# Boundary-condition correction and historical evidence scope

The frozen fixed-cylinder 30 s release and historical NM5/NM7/NM8/NM8.1 coupled cases used `cylinder/U = fixedValue (0 0 0)`. The fixed30 release remains unmodified and remains the initial flow state. In NM8.2 independent FSI scratch cases, the actual six decomposed 30 s restart U files use `movingWallVelocity`; the numerical field payload is unchanged at preparation.

Historical coupled evidence remains evidence for software architecture, rollback, IQN mechanics, ANCF lifecycle, and diagnostic history. It is **not** production-Fluid-physics qualification for the corrected moving-wall boundary. NM8.2 A/B/C provide separate evidence for that operator. Old fixedValue trajectories are diagnostic comparisons only; disagreement with them is expected to be possible and is not a failure criterion.
