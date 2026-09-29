# NM8.2 local v2606 moving-wall reference

- Installation: OpenFOAM.com `v2606`, `/usr/lib/openfoam/openfoam2606`; `pimpleFoam` resolves inside that installation. The installed distribution does not provide a `foamVersion` executable, so `WM_PROJECT_VERSION` and the solver path are the local identity checks.
- Definition and syntax: `/usr/lib/openfoam/openfoam2606/src/finiteVolume/fields/fvPatchFields/derived/movingWallVelocity/movingWallVelocityFvPatchVectorField.H`, class description and Usage. Selected cylinder/U entry:

  ```foam
  cylinder
  {
      type movingWallVelocity;
      value uniform (0 0 0);
  }
  ```

- Implementation: adjacent `movingWallVelocityFvPatchVectorField.cxx`, `Uwall()` computes old/current face-centre motion per timestep and adjusts the normal component using `fvc::meshPhi(U)`. `updateCoeffs()` applies this only if `mesh.moving()`. This is why no simple pointwise `U = (D_n-D_{n-1})/dt` bitwise test is imposed.
- Incompressible moving-mesh flux/pressure path: `/usr/lib/openfoam/openfoam2606/applications/solvers/incompressible/pimpleFoam/pEqn.H` invokes `constrainPressure`, corrects `phi`, corrects `Uf` for moving mesh, then makes `phi` relative. `constrainPressure.C` updates pressure gradient only for an `updateableSnGrad` patch; this does not establish an obligatory pressure-BC change for the present case.
- Installed official v2606 templates: `/usr/lib/openfoam/openfoam2606/etc/templates/inflowOutflowRotating/0/U` uses movingWallVelocity, while corresponding `0/p` uses zeroGradient on wall. The local official preCICE tutorial `${LINUX_HOME}/software/precice-tutorials-v2606-smoke/perpendicular-flap/fluid-openfoam/0/U` also uses movingWallVelocity; its `0/p` uses zeroGradient on flap. Official adapter v1.4.0 documentation `${LINUX_HOME}/software/openfoam-adapter-v1.4.0/docs/config.md` gives the same U/pointDisplacement/dynamicMeshDict combination.

No additional companion BC is required by these local references. This finding does not imply pressure fluxes are exact; it limits the NM8.2 intervention to cylinder/U type as specified.
