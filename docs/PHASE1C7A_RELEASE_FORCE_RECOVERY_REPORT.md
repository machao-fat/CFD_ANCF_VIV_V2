# Phase 1C.7A — Exact 30.0 s HH06 Release Force Recovery

**Classification:** `RELEASE_FORCE_RECOVERED_REPRODUCIBLY`  
**F0_PHYSICAL_VALUE_RESOLVED:** `YES`  
**FLUID_INITIALIZATION_PATH_RESOLVED:** `NO`  
**Branch / HEAD:** `repair/worker-lineage-implicit-contract-v1` / `51b598e5f8d16c6cb69625bb25ca0f07011a0931`

## Scope and source identity

The force was evaluated from the current V2 restart only:

```text
cases/hh06_single_slice/30/
contract case_id: ANCF_SINGLE_SLICE_HIGHRE_0P2S_PREP_V1
30/uniform/time: value=30, name="30", index=150000,
                 deltaT=0.0002, deltaT0=0.0002
```

The pre-execution Git worktree was clean. Before execution, SHA256 was recorded for every file in `30/`, every file in `constant/polyMesh/`, and the relevant force/model configuration (`system/controlDict`, `constant/physicalProperties`, `constant/momentumTransport`, `constant/dynamicMeshDict`, `system/fvSchemes`, `system/fvSolution`, and `system/preciceDict`). All those hashes were recomputed after both runs and matched exactly. The complete hash inventory is in [provenance.json](../evidence/phase1c7a_release_force/provenance.json).

The restart has kinematic-pressure field `p` (dimensions `[0 2 -2 0 0 0 0]`), `U`, and the configured RAS `kOmegaSST` fields. The evaluated force is the dimensional `forces` function-object result on patch `cylinder`, using the existing source-case settings `rho rhoInf`, `rhoInf 1000`, `CofR (0 0 0)` and the OpenFOAM v10 default `pRef=0`. No forceCoeffs reconstruction, average, interpolation, alternate case, or additional scaling was used. Axes are global x=streamwise/drag, y=transverse/lift, z=spanwise.

## Method and safety boundary

Runtime was OpenFOAM-10, package `20230119`, build `10-c4cf895ad8fa`. Version-correct `-postProcess` behavior was verified from the installed source: `pimpleFoam.C` includes `postProcess.H` before the solver setup and time loop; in `postProcess.H`, selected existing times are processed and the branch returns from `main`. The later `pimple.run(runTime)`, `mesh.update()`, and `mesh.move()` are in the solver path after that return. The installed header labels the option “Execute functionObjects only.”

Two independent clean scratch copies were made outside the repository. In each scratch copy only, `controlDict` retained the source `cylinderForces` block and removed `cylinderForceCoeffs`, `yPlus`, and `preciceAdapter`; the retained force-object block was unchanged. The scratch configuration is preserved as `evidence/phase1c7a_release_force/controlDict_postprocess_scratch`.

Executed successfully (both return code 0):

```bash
source /opt/openfoam10/etc/bashrc
pimpleFoam -postProcess -case /tmp/phase1c7a_release_force.AH2Uqd/replay1 -time 30

source /opt/openfoam10/etc/bashrc
pimpleFoam -postProcess -case /tmp/phase1c7a_release_force.AH2Uqd/replay2 -time 30
```

Each run log says `Time = 30s`, loads the RAS `kOmegaSST` model and executes only `forces cylinderForces`. Each scratch copy contains only the original `30` time directory plus `constant`, `system`, and the newly written `postProcessing`; no time greater than 30 was generated. No solver time loop or mesh motion occurred. The Fluid preCICE adapter was removed from the scratch function-object list, and no preCICE or Structure participant was started. The authoritative case was not used as a run directory and its recorded field, mesh, and configuration hashes remained unchanged.

The earlier command probes were also scratch-only: generic `postProcess -func cylinderForces` could not find a standalone function-object configuration, and generic `postProcess` could not load the solver fields/model (`U`, `p`). Neither produced the reported force. The reported result comes only from the two successful `pimpleFoam -postProcess` replays above.

## Recovered force at exactly 30.0 s

Both independent `postProcessing/cylinderForces/30/forces.dat` files are byte-identical, SHA256 `bafd3b57b2d0f236ef726a321f08562de92f288e2f43e00494529030c728cfdb`. The exact force record is line 4 of each output. It stores pressure and viscous vectors separately; the total below is their component-wise sum plus the reported zero porous contribution. The machine-readable value and source-field hashes are in [release_force_result.json](../evidence/phase1c7a_release_force/release_force_result.json).

| Contribution | Fx (N) | Fy (N) | Fz (N) |
|---|---:|---:|---:|
| Pressure | 0.063811823767 | 0.058106728512 | -2.7532914920e-21 |
| Viscous | 0.0017152168874 | 0.00062314562354 | 3.0908797634e-22 |
| Porous | 0 | 0 | 0 |
| **Raw release force** | **0.0655270406544** | **0.05872987413554** | **-2.44420351566e-21** |

Thus the exact recovered physical release value is:

```text
F0_raw = (0.0655270406544, 0.05872987413554, -2.44420351566e-21) N
```

The OpenFOAM record itself reports pressure and viscous separately, not an independent total vector. Summing pressure + viscous + porous gives the listed total, with zero component-wise closure error at the printed record precision. The tiny nonzero z value is retained from the measured output rather than replaced by an assumed zero.

Applying only the already-qualified unit chain (`Lz=0.028 m`, `DeltaL=1.98 m`):

| Quantity | Fx | Fy | Fz |
|---|---:|---:|---:|
| Section force `F_raw / Lz` (N/m) | 2.340251451942857 | 2.0974955048407145 | -8.729298270214285e-20 |
| Strip resultant `F_section * DeltaL` (N) | 4.633697874846857 | 4.153041099584614 | -1.7284010575024286e-19 |

This is reporting only. `contract.json`, `precice-config.xml`, `preciceDict`, and the adapter were not modified; the value has not been installed into the HH06 launch contract. Conversion provenance remains `F_strip=(F_raw/0.028)*1.98`, once, as specified by `docs/COUPLING_CONTRACT.md`.

## Reproducibility and comparison sample

The two clean scratch replays returned identical `forces.dat` bytes and identical raw component values. Both stdout logs, both output data files, the scratch control dictionary, hashes, and the machine-readable force result are preserved under `evidence/phase1c7a_release_force/`.

For context only, the migrated qualification evidence associates `(Fx,Fy)=(0.06440713207168003, 0.05908675094604829) N` with the later `30.0002 s` first advanced coupling sample. Relative to the exact 30.0 s release force, that sample changes by `(-0.0011199085827199723, +0.00035687681050829145) N` (approximately `-1.709%` in x and `+0.608%` in y); both components remain positive. The values are similar in magnitude and retain sign across this first `0.0002 s` transition. This single difference does not establish convergence, stability, or a physical response conclusion, and the 30.0002 s sample was not used to calculate `F0`.

Comparison sources: `evidence/legacy_qualification/hh06_single_slice_coupling_history_v1/evidence/runtime/hh06_bounded_multiwindow_ale_qualification_v1/HH06_SINGLE_SLICE_FORCE_UNIT_CHAIN_AUDIT.md` and `artifacts/run_analysis.json`.

## Gate result and remaining boundary

The numeric release-force provenance gate is resolved: `F0_PHYSICAL_VALUE_RESOLVED = YES`. The recommended initial-force policy remains **Policy A — use this physical release force**, not zero as a physical load. However, the separate Fluid initialization gate remains open: `FLUID_INITIALIZATION_PATH_RESOLVED = NO`. This phase did not establish that the current Fluid adapter can supply this force as preCICE initial data before `initialize()`, and it made no preCICE runtime or adapter change.

Final classification: **`RELEASE_FORCE_RECOVERED_REPRODUCIBLY`**.

No CFD timestep was advanced; the authoritative restart remained hash-identical. No real preCICE/FSI run was performed.
