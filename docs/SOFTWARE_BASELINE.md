# Software baseline

Recorded from the WSL environment during repository handoff on 2026-09-23.

| component | recorded value |
|---|---|
| OS | Ubuntu 22.04 on WSL2 |
| Linux kernel | Microsoft WSL2 6.18.33.2 |
| Git | 2.34.1 |
| Python | 3.10.12 |
| CMake | 3.22.1 |
| GCC | 11.4.0 |
| G++ | 11.4.0 |
| Open MPI | 4.1.2 |
| OpenFOAM | 10 |
| preCICE | 3.4.1 (historical qualification environment) |
| MATLAB reference | R2021b |
| GitHub CLI | not installed in this WSL environment at handoff |

The OpenFOAM and preCICE entries are inherited from the archived qualification
reports; they were not re-run during this handoff. The handoff itself executed no
CFD, preCICE, or ANCF physical time advancement.
