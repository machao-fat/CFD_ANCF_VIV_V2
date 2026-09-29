# OpenFOAM.com v2606 moving-wall source audit

Runtime/source root: `/usr/lib/openfoam/openfoam2606`.

Relevant implementation:

- `src/finiteVolume/fields/fvPatchFields/derived/movingWallVelocity/movingWallVelocityFvPatchVectorField.cxx`
- function `Foam::movingWallVelocityFvPatchVectorField::Uwall()`
- function `Foam::movingWallVelocityFvPatchVectorField::updateCoeffs()`

The v2606 implementation obtains `const pointField& oldPoints = mesh.oldPoints()`, computes old face centres from those points, and forms

`Up = (current faceCentre - old faceCentre) / mesh.time().deltaTValue()`.

It then obtains `phip` from `p.patchField<surfaceScalarField>(fvc::meshPhi(U))`, computes `Un = phip/(magSf + VSMALL)`, and returns

`Uwall = Up + n*(Un - (n & Up))`.

`updateCoeffs()` assigns this field when `mesh.moving()` is true. Thus the production BC uses current face centres, `oldPoints`, the mesh-motion flux returned by `fvc::meshPhi(U)`, face normals and face area magnitudes. It is not a fixed zero velocity after mesh motion.

The diagnostic solver additionally records `fvMesh::phi()`, the public v2606 mesh-motion flux accessor (`src/finiteVolume/fvMesh/fvMeshGeometry.C`, `Foam::fvMesh::phi()`), without creating or modifying a new history object.

The diagnostic solver is a copied source tree under `diagnostics/nm8_3_2_pimpleFoam`; the installed production `pimpleFoam` and official adapter were not changed.
