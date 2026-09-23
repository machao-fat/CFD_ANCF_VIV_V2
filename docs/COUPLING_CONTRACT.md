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

## Implicit physical-window iteration lifecycle

The Structure participant owns three distinct kinds of state:

- **Committed physical state:** ANCF `q/qdot/qddot` and accepted absolute
  `committed_motion`. The coordinator checkpoints this once at the beginning of
  a physical window and restores it on each rejected coupling iteration.
- **Coupling-iteration state:** current Force iterate, previous/current ANCF trial
  displacement, residual history, and iteration diagnostics. It survives physical
  rollback but is not part of the ANCF checkpoint.
- **Transport-session state:** sequence, request ID, and transaction ID. These are
  owned by the persistent worker and remain unique and monotonic across rollback.

For each attempt, the participant consumes the current Force iterate, solves ANCF
from the physical window checkpoint, scatters absolute `D_trial`, writes that exact
trial displacement to preCICE, and then calls `advance(dt)`. It reads the resulting
Force iterate after `advance`. If preCICE requests a retry, only the physical ANCF
state is restored; Force and iteration history survive. If the window is accepted,
the ANCF trial corresponding to the displacement written before the accepted
`advance` becomes committed motion.

The first Force iterate is the frozen raw, patch-integrated OpenFOAM release Force
from global time `30.0 s`, not a zero numerical seed. The first structural trial
targets global time `30.0002 s`. The production XML requests `Force` initial data;
the exact adapter binary tested for this path is pinned by the HH06 launcher.

This lifecycle currently has deterministic offline qualification only. It has not
yet been exercised in a real preCICE/OpenFOAM coupling run, so it does not establish
HH06 stability or resolve the historical late-window ALE/flow/turbulence runaway.

## Readiness and bounded launch authorization

Scientific maturity remains `READY_FOR_DRY_RUN`; that value is not promoted by
the launch repair. A separate `execution_authorization` permits only the
`BOUNDED_COUPLING_QUALIFICATION` profile with exactly two physical windows.
Both linked structure/interface contracts retain their default-deny launch
fields and carry an explicit matching two-window override; the fail-closed
launcher validates all three records before it constructs commands.

The bounded profile is pinned to `dt=0.0002 s`, preCICE
`max-time-windows=2`, and `max-iterations=20`. Its authorization is not a
production/validation claim. Phase 1D.6 performed static preflight and an
isolated Python/preCICE binding runtime check only; no HH06 participant, worker,
OpenFOAM solver, or real FSI run was started.
