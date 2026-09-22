# CFD--preCICE--ANCF coupling contract

## Force unit chain

OpenFOAM integrates the cylinder wall over its numerical 2-D extrusion:

```text
F_raw [N]
  -> f_section = F_raw / Lz_CFD,  Lz_CFD = 0.028 m [N/m]
  -> F_strip = f_section * DeltaL, DeltaL = 1.98 m [N]
```

Therefore the current single-slice contract is:

```text
F_strip = F_raw / 0.028 * 1.98
conversion factor = 70.71428571428571
```

This scaling is applied exactly once. The archived force-unit-chain audit reported
zero closure error. A late 150 kN applied strip force in the failed bounded run is
not evidence of an extra `0.028` or `1.98` factor.

## Single-slice geometry

The representative section is `s=2.97 m` and represents its own structural interval
of length `1.98 m` (for the qualification, `[1.98,3.96] m`). It is not the whole
`0--5.94 m` exposed-flow region.

The preCICE data contract is:

```text
Fluid_0000 provides Force on Fluid-Mesh
Structure_0000 receives Force on Structure-Mesh (one point)
Structure_0000 provides Displacement on Structure-Mesh (one point)
Fluid_0000 receives Displacement on Fluid-Mesh
```

CFD wall faces are integrated before mapping. They are never paired directly with ANCF
nodes.

## Distributed multi-slice target

The formal future mode is `PiecewiseLinearDistributed` / `SLD1`:

- slice values are sectional line forces `[N/m]`;
- linear interpolation is used between adjacent slice centers;
- nearest-constant extension is used from the active-region ends to the nearest slice;
- generalized loads are assembled by element-level quadrature:
  `Q = integral H(s)^T f(s) ds`.

The old `sum H(si)^T Fi` point-lumped mode remains a legacy verification mode only.

For the planned three-slice smoke:

```text
active flow region: 0--5.94 m
DeltaL: 1.98 m
centers: s1=0.99 m, s2=2.97 m, s3=4.95 m
```

## Motion semantics

Structure displacement is absolute section displacement, not an increment and not a
previous-displacement accumulator:

```text
r(s,t) - r_ref(s) -> Structure-Mesh Displacement
```

The section displacement at `s=2.97 m` is sent to the one-point structure mesh and
then mapped to OpenFOAM `pointDisplacement`/`cellDisplacement` and ALE motion.
