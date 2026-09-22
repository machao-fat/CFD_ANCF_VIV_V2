# Fixed-cylinder Re=7622 parent snapshot

Source snapshot: `/home/machao/OpenFOAM/CFD_turbulent`.

The copied `0/`, `constant/`, and `system/` are the clean fixed-cylinder parent used
to develop the HH06 30 s restart field. Its physical contract is `D=0.028 m`,
`U=0.31 m/s`, `rho=1000 kg/m^3`, `nu=1.1388087116e-6 m^2/s`, giving `Re≈7622`.

Only setup files and the initial field are included. Runtime times, logs, processor
directories and post-processing outputs are intentionally excluded. This snapshot
has not been re-run during the V2 handoff.
