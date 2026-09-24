# Phase 1K.6 — RBF Motion Solver Provenance Audit

## Result

**Classification: `RBF_SOURCE_REQUIRED`.**

The environment contains a specific OpenFOAM-10-compatible candidate library,
and static inspection recovers its runtime selection name and part of its
dictionary contract. However, the authoritative RBF source/build provenance,
kernel, control-point construction, far-field constraints, and support-radius
meaning are unavailable. The binary therefore is not sufficiently specified
to qualify its mesh-deformation behavior or to claim that it implements the
Duanmu concept. No RBF `dynamicMeshDict` was written and no OpenFOAM solver,
mesh-motion, or FSI run was performed.

## Scope and repository state

This audit inspected only the current V2 repository and the local OpenFOAM 10
installation/user library directories. The old repository was not accessed.
Existing Phase 1J/1K.5 untracked reports and evidence were left untouched.

| Item | Value |
|---|---|
| Git branch / HEAD | `repair/worker-lineage-implicit-contract-v1` / `c2245ff396ff42dfa5e80fee6555a9ede93e3b04` |
| OpenFOAM runtime identity | `OpenFOAM-10`, installation `/opt/openfoam10` |
| Existing HH06 `dynamicMeshDict` SHA256 | `56158d50b619174c67a343d2660c87c4c0c5e1370e2fde44a4a4c6f07c5ccdc5` |
| Existing HH06 motion method | `displacementLaplacian` |
| Tracked-file modifications at audit start | None |
| Pre-existing untracked work | Phase 1J/1K.5 reports and evidence; preserved |

## Candidate library identity

| Property | Read-only finding |
|---|---|
| Absolute path | `/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libRBFMotionSolver.so` |
| SHA256 | `e783ae0aa3765dee2a7f11f24d3a041b9d9b028795c4c703e48aca3a508cf188` |
| File type | ELF 64-bit LSB x86-64 shared object, dynamically linked; ELF symbol table present |
| ELF Build ID | `d12bef3602874632c74204341110e7f8008e5dc7` |
| Embedded compiler comment | GCC 11.4.0 (`Ubuntu 11.4.0-1ubuntu1~22.04.3`) |
| RBF class symbols | `Foam::rbfMotionSolver`, including constructor, `solve`, `curPoints`, `buildControls`, and `updateDisplacement` |
| Embedded compilation-unit string | `rbfMotionSolver.C` |
| Embedded OpenFOAM paths | Includes generated paths under `/opt/openfoam10/src/.../lnInclude` |
| Debug/source data | No `.debug_*` sections or RBF source/header found; the embedded compilation-unit name is not source provenance |

The ELF `DT_NEEDED` entries include `libdynamicMesh.so`,
`libfvMotionSolvers.so`, `libfvMeshMovers.so`, `libfiniteVolume.so`,
`libmeshTools.so`, `libOpenFOAM.so`, `libPstream.so`, and the standard C/C++
runtime libraries. With the OpenFOAM 10 environment sourced, the OpenFOAM
dependencies resolve under
`/opt/openfoam10/platforms/linux64GccDPInt32Opt/lib` (including the
OpenMPI-specific `libPstream.so`). This is ABI/dependency evidence, not proof
of the library's source revision or build recipe.

No project/source commit, source hash, build manifest, or reproducible build
recipe was found for this library. Thus:

```text
RBF_BINARY_IDENTITY_KNOWN = YES
RBF_SOURCE_TO_BINARY_PROVENANCE_RESOLVED = NO
```

## Verified OpenFOAM-10 runtime selection/configuration layers

The current OpenFOAM 10 API uses the `fvMeshMover` selection path here, not a
classic `dynamicFvMesh <type>` entry in this case's `dynamicMeshDict`:

1. `fvMeshMover::New` reads `dynamicMeshDict/mover/type` and opens the outer
   `mover/libs` list. The implementation is in
   `/opt/openfoam10/src/finiteVolume/fvMesh/fvMeshMovers/fvMeshMover/fvMeshMoverNew.C:50-63`.
2. The selected outer mover is
   `Foam::fvMeshMovers::motionSolver`, runtime type `motionSolver`; its
   registration and construction are visible in
   `/opt/openfoam10/src/fvMeshMovers/motionSolver/fvMeshMoversMotionSolver.C:32-48`.
   The class declares `TypeName("motionSolver")` in
   `/opt/openfoam10/src/fvMeshMovers/motionSolver/fvMeshMoversMotionSolver.H:53-71`.
3. That mover calls `Foam::motionSolver::New` using the `mover` subdictionary.
   OpenFOAM source then reads `motionSolver`, opens `motionSolverLibs`, and
   looks up the resulting name in the motion-solver dictionary constructor
   table: `/opt/openfoam10/src/dynamicMesh/motionSolvers/motionSolver/motionSolver.C:65-103`.
4. Static inspection of the candidate ELF's global initializer shows the
   string `rbfDisplacement` is used to initialize `Foam::rbfMotionSolver`'s
   `typeName`, then passed to
   `Foam::motionSolver::adddictionaryConstructorToTable<Foam::rbfMotionSolver>`.
   Therefore the verified distinction is:

   | Layer | Runtime name |
   |---|---|
   | Outer `fvMeshMover` | `motionSolver` |
   | Inner C++ class | `Foam::rbfMotionSolver` |
   | Inner `motionSolver` selection key | `rbfDisplacement` |
   | Separate `dynamicFvMesh` type in this dictionary path | Not specified/used; the `mover` selection is used instead |

The current HH06 dictionary already uses the same outer `mover { type
motionSolver; ... }` structure. OpenFOAM 10 tutorials such as
`/opt/openfoam10/tutorials/incompressible/pimpleFoam/laminar/movingCone/constant/dynamicMeshDict:17-27`
and `.../RAS/propeller/constant/dynamicMeshDict:17-32` corroborate the outer
schema, but contain no RBF-specific entries.

### Binary-recovered input surface

The ELF constructor's static strings and call sites provide the following
limited contract:

| Input / behavior | Evidence and status |
|---|---|
| `motionSolver rbfDisplacement;` | Runtime name confirmed by the ELF static initializer and registration-table symbols; selection key is not the C++ class name |
| `motionSolverLibs` | OpenFOAM 10 `motionSolver::New` explicitly opens this entry before table lookup; use it to load the candidate plugin |
| `rbfDisplacementCoeffs` | `motionSolver` base forms the coefficient subdictionary name as `type + "Coeffs"` in `/opt/openfoam10/src/dynamicMesh/motionSolvers/motionSolver/motionSolver.C:42-53` |
| `movingPatch` | Binary uses `lookupOrDefault`; default is exactly `cyl` (decoded from the adjacent ELF string bytes). Missing selected patch triggers `movingPatch was not found` |
| `controlStride` | Binary performs a required dictionary-entry lookup and converts to integer; no default found; constructor rejects non-positive values |
| `supportRadius` | Binary performs a required dictionary-entry lookup and converts to scalar; no default found; constructor rejects values not greater than zero |
| `cellDisplacement` | Internal field-name string present in the constructor; it does not establish any RBF algorithm semantics |
| Kernel selector / kernel name | No user-facing kernel selector or kernel identifier was found in strings, static source search, or examples; actual kernel remains unknown (it may be hard-coded) |

Since the HH06 mesh patch is named `cylinder`, relying on this binary's
`movingPatch` default (`cyl`) would not select the intended patch. An explicit
`movingPatch cylinder` would be needed if this implementation is eventually
qualified. No numerical values are assigned here.

The source-derived *shape only* of a future dictionary would therefore be:

```foam
mover
{
    type                motionSolver;
    libs                ("libfvMeshMovers.so" "libfvMotionSolvers.so");
    motionSolverLibs    ("libRBFMotionSolver.so");
    motionSolver        rbfDisplacement;

    rbfDisplacementCoeffs
    {
        movingPatch     cylinder;
        controlStride   <required-positive-integer>;
        supportRadius   <required-positive-scalar>;
    }
}
```

This is a schema sketch, **not a tested or approved configuration**. The
placeholder values are deliberately unresolved. `motionSolverLibs` is the
inner solver-library loader entry; the outer `libs` list belongs to the
`fvMeshMover` selector. Neither this sketch nor the static inspection proves
that constructing the solver will preserve the near-cylinder boundary layer
or hold the intended far field fixed.

## Local source/example search

Search locations were the current V2 `src/` and `cases/`, OpenFOAM 10
`src/`, `tutorials/`, and `etc/`, and `/home/machao/OpenFOAM/machao-10`.

| Location | RBF-specific source/config result |
|---|---|
| Current V2 `src/`, `cases/` | No RBF references or implementation files |
| `/opt/openfoam10/src/` | Generic `motionSolver` selection source exists; no `rbfMotionSolver` implementation source |
| `/opt/openfoam10/tutorials/`, `/opt/openfoam10/etc/` | No RBF-specific example or configuration |
| `/home/machao/OpenFOAM/machao-10` | Candidate `.so` only; no matching RBF source/header/example |
| Local RBF source filename scan | No `*rbf*.C`, `*rbf*.H`, `*rbf*.cpp`, or `*rbf*.hpp` outside the binary |

The generic OpenFOAM sources establish the loader/selection mechanics. They do
not define this custom implementation's RBF kernel or coefficient meanings.

## Duanmu concept comparison

The design concept to preserve is that the near-cylinder boundary-layer mesh
should remain unchanged while deformation is propagated outward through RBF
motion. This remains a requirement for a future qualification, not a finding
about this binary. The available implementation evidence does not identify:

- the radial basis function/kernel or its formula;
- whether `supportRadius` is compact support, a cutoff, or another quantity;
- the units/normalization of `supportRadius`;
- how `controlStride` selects or spaces control points;
- whether far-field points are fixed controls, how they are selected, or what
  boundary condition applies there;
- whether the near-cylinder layer is held rigid or only interpolated with the
  moving patch.

No kernel, support-radius value, or control-point distribution is inferred
from the library name, input names, or thesis concept.

## Qualification boundary and next gate

No `dynamicMeshDict`, source, mesh, physics, or coupling file was modified.
No OpenFOAM solver or mesh-motion executable was run, no preCICE participant
was initialized, and no FSI runtime was started. The existing Laplacian
configuration remains intact.

To close the provenance gate, obtain the authoritative source corresponding
to this exact binary (including source revision and build instructions), or a
version-matched implementation document that specifies the kernel,
control-point/fixed-point construction, and radius semantics. Until then,
configuration can only be sketched; a prescribed-motion test and the later
5-window RBF qualification remain unauthorized by evidence.

**Final classification: `RBF_SOURCE_REQUIRED`.**
