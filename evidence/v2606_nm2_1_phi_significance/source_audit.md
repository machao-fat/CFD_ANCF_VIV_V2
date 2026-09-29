# NM2.1 local-source significance audit

No CFD process was run. The original NM2 classification file was not edited.

## Provenance and scope

The original NM2 evidence was actually written under
`${LINUX_HOME}/projects/CFD_ANCF_VIV_V2/evidence/v2606_nm2_official_adapter_rollback`.
It was copied intact to
`${LINUX_HOME}/projects/CFD_ANCF_VIV_V2_of2606/evidence/v2606_nm2_official_adapter_rollback`;
`diff -qr` found no differences. This is location case B, not a report-link typo.
The requested `_of2606` directory is not a Git checkout (`git rev-parse --show-toplevel`
reports “not a git repository”), so its identity is the absolute path and the
byte-matched evidence copy, not a Git worktree root. The old evidence remains.

## Field geometry and measured symmetry constraint

The actual mesh `R1/case/constant/polyMesh/boundary` lines 47–59 declares
`upper` and `lower` as `symmetryPlane`, 189 faces each. The `front` and `back`
patches are `empty` and therefore have zero stored field elements despite
46826 geometric faces each. The observer source `observer_source/nm2Observer.C`
serializes internal elements then boundary elements in patch order, each as
binary64 after a uint64 count. The offline analyzer separates those segments
using the mesh boundary dictionary and reconstructs area normals using the
central-triangle decomposition in local OpenFOAM source
`src/OpenFOAM/meshes/meshShapes/face/face.C`, `face::areaNormal`, lines 576–614.

For both R1 and R2, attempt 3/4 points are byte-exact; topology files are
unchanged; reconstructed `Sf` is byte-exact on all 378 symmetry faces. On all
378 faces in both attempts, observed symmetry boundary `U·n` and `U·Sf` are
exactly 0 in the reconstruction. The maximum `|phi|` over all symmetry faces
is 9.525073347779722e-17 m3/s, and its maximum ratio to the specified local
characteristic flux is 5.967749299273966e-13. For the 84 differing faces
only, maximum `|phi3|` is 2.2184998214043221e-23 m3/s, maximum `|phi4|` is
2.2184998214034743e-23 m3/s, and maximum `|delta|` is
9.525074031516734e-36 m3/s; maximum `|delta|/phi_char` is
1.1928640048239356e-31. These ratios describe scale; they do not change
the original bitwise exactness gate. All 84 differences per run are in upper
(41) or lower (43). The full 84-row per-run list is `phi_diff_faces.csv`.

The 84 attempt-3 values are all IEEE-754 *normal* doubles. Of the attempt-4
values, 61 are normal and 23 are `+0`; all 84 nonzero differences are normal.
They are not subnormal. The face-index and binary delta pattern repeats
exactly in R1 and R2, so this is an attempt-role-dependent deterministic
difference, not fresh-process nondeterminism. See `ieee754_phi_diff.json`.

## OpenFOAM.com v2606 installed source

- `src/finiteVolume/cfdTools/incompressible/createPhi.H`, lines 26–49,
  creates registered `surfaceScalarField phi` from `fvc::flux(U)` when no field
  is read; `src/finiteVolume/finiteVolume/fvc/fvcFlux.C`, lines 33–43, computes
  it by `Sf` dot-interpolation of `U`. This is a derived surface flux, but it
  is also a registered, checkpointed field with history, not an untracked
  diagnostic.
- `applications/solvers/incompressible/pimpleFoam/pimpleFoam.C`, lines
  146–162, recomputes/corrects `phi` after mesh change and makes it relative
  to mesh motion. `pEqn.H`, lines 1–69, forms `phiHbyA`, corrects pressure,
  assigns `phi = phiHbyA - pEqn.flux()`, and makes it relative again.
  `src/finiteVolume/cfdTools/general/CorrectPhi/CorrectPhi.C`, lines 95–116,
  also corrects `phi` by pressure flux. Thus rollback restores a stored
  `phi`, after which a repeated solver attempt can recompute it.
- `src/finiteVolume/fields/fvPatchFields/constraint/symmetryPlane/
  symmetryPlaneFvPatchField.txx`, lines 167–188, projects vector boundary
  values onto the symmetry plane and extrapolates scalar boundary values.
  The actual sampled boundary velocities satisfy `U·n = 0` exactly.
- `src/finiteVolume/fields/fvsPatchFields/constraint/symmetryPlane/
  symmetryPlaneFvsPatchField.txx`, lines 44–60 and 100–105, validates the
  symmetry patch and writes its stored value; it has no hard-zero operation
  for the surface flux. Accordingly, nonzero numerical `phi` residues can
  remain on the theoretical zero-flux symmetry boundary.
- **Important qualification:** those residues are *not structurally skipped*.
  `src/finiteVolume/finiteVolume/convectionSchemes/gaussConvectionScheme/
  gaussConvectionScheme.C`, lines 101–108, multiplies the patch flux into
  boundary matrix coefficients. For scalar symmetry fields,
  `src/finiteVolume/fields/fvPatchFields/basic/transform/
  transformFvPatchField.txx`, lines 84–116, has internal coefficient 1 and
  boundary coefficient from the extrapolated value. `pimpleFoam/UEqn.H`,
  lines 5–8, calls `fvm::div(phi,U)`; the frozen `fvSchemes` selects
  `div(phi,k)` and `div(phi,omega)`, whose kOmegaSST equations use
  `fvm::div(alphaRhoPhi,omega_)` and `fvm::div(alphaRhoPhi,k_)` in
  `src/TurbulenceModels/turbulenceModels/Base/kOmegaSST/kOmegaSSTBase.C`,
  lines 569–604. Therefore the residual can enter discrete coefficients;
  it is not justified to say the solver ignores it. In these measured
  attempts, all stored U/p/k/omega/nut internal and boundary segments and
  raw forces remain byte-exact despite the residual.

## Official adapter v1.4.0 source

The local checkout `${LINUX_HOME}/software/openfoam-adapter-v1.4.0` is tag
`v1.4.0` at commit `0801887b958f3101389cb719838dc8fc864d5369`.
`Adapter.C::setupCheckpointing`, lines 912–944, includes registered
`surfaceScalarField` objects, thus CFD `phi`; lines 1173–1186 and 1353–1357
read/write those copies and old times. Independently,
`Adapter.C::setupMeshCheckpointing`, lines 879–886, adds `mesh_.phi()`
(mesh motion flux) to a separate checkpoint list, read/written at lines
1397–1430. `Adapter.C::reloadMeshPoints`, lines 857–877, restores points,
oldPoints, mesh flux, and volumes. The NM2 observer attempted a read-only
lookup for `meshPhi` but did not capture a `meshPhi.bin`, so its numeric
bitwise equality is **not claimed** here. The source establishes the
checkpoint path, while the measured exactness claim covers only explicitly
captured state and forces.

## Interpretation

The theoretical physical normal flux is zero at upper/lower. The observed
boundary velocity and reconstructed flux are exactly zero, while stored
`phi` differs only by tiny normal-double residues on some of those faces.
Internal `phi`, all other boundary `phi`, mesh geometry, solved field segments,
and three raw force vectors are bitwise equal. This supports a narrow
**boundary roundoff only** finding for the measured one-window runs; it does
not retroactively pass NM2's full-state bitwise gate or establish that
symmetry `phi` has no algebraic participation in future solves.
