# HH06 Case 1 physics contract

This is the frozen contract used by the current HH06 qualification. It is not a
license to tune parameters to a reference curve.

| quantity | value |
|---|---:|
| riser length `L` | 13.12 m |
| cylinder diameter `D` | 0.028 m |
| current speed `U` | 0.31 m/s |
| water density `rho` | 1000 kg/m^3 |
| kinematic viscosity `nu` | 1.1388087116e-6 m^2/s |
| Reynolds number | approximately 7622 |
| benchmark top tension | 1175 N |
| static equilibrium reaction tension | approximately 1188.28 N |
| structural line mass | 1.845 kg/m |
| hydrodynamic added mass | 0.616 kg/m |
| full wet transverse line mass | 2.461 kg/m |
| ANCF elements / nodes / DOF | 32 / 33 / 198 |
| coupling point | `s=2.97 m` |
| tributary length | `DeltaL=1.98 m` |
| coupling time step | 0.0002 s |
| fluid restart | approximately 30 s fixed-cylinder field |

## Wet structural region

The current-exposed region is `0--5.94 m`. The upper region is still submerged in
water, not air. Therefore the current SHM1 added-mass region is full length
`0--13.12 m`; `5.94 m` is an exposed-flow boundary, not a wet-mass boundary.

## SHM1 contract

```text
region: [0.0, 13.12] m
added_mass_per_length_kg_m: [0.616, 0.616, 0.0]
linear_damping_per_length_Ns_m2: [0.0, 0.0, 0.0]
Rayleigh alpha = 0
Rayleigh beta  = 0
```

`1175 N` is the HH06 benchmark input. `1188.28 N` is the P1 static-equilibrium
reaction diagnostic. They must never be silently substituted for one another.

The authoritative initial structural state is the P1 `REF_NE32` static equilibrium
`q0`, with zero initial velocity. The 30 s value belongs to the fluid restart only;
there is no fabricated 30 s ANCF checkpoint in this repository.
