#include "argList.H"
#include "Time.H"
#include "fvMesh.H"
#include "pointMesh.H"
#include "pointFields.H"
#include "volFields.H"
#include "primitivePatchInterpolation.H"
#include "FSI/Displacement.H"

#include <cmath>
#include <vector>

int main(int argc, char** argv)
{
    #include "setRootCase.H"
    #include "createTime.H"
    #include "createMesh.H"

    const Foam::pointVectorField& pointDisplacement =
        mesh.lookupObject<Foam::pointVectorField>("pointDisplacement");
    const Foam::label patch = mesh.boundaryMesh().findPatchID("cylinder");
    if (patch < 0 || mesh.foundObject<Foam::volVectorField>("cellDisplacement"))
    {
        FatalErrorInFunction << "invalid initial field state"
                                  << Foam::exit(Foam::FatalError);
    }

    preciceAdapter::FSI::Displacement reader(
        mesh, "pointDisplacement", "cellDisplacement");
    reader.setPatchIDs({patch});
    reader.setLocationsType(preciceAdapter::LocationType::faceCenters);
    reader.initialize();

    const Foam::volVectorField& cell =
        mesh.lookupObject<Foam::volVectorField>("cellDisplacement");
    if (cell.dimensions() != Foam::dimLength ||
        cell.boundaryField()[patch].size() != 200 ||
        pointDisplacement.boundaryField()[patch].size() != 400)
    {
        FatalErrorInFunction << "field geometry/dimensions mismatch"
                                  << Foam::exit(Foam::FatalError);
    }
    forAll(cell.primitiveField(), i)
    {
        if (Foam::mag(cell.primitiveField()[i]) != 0)
        {
            FatalErrorInFunction << "nonzero staging field"
                                      << Foam::exit(Foam::FatalError);
        }
    }

    const Foam::label faces = cell.boundaryField()[patch].size();
    std::vector<double> uniform(2 * faces);
    for (Foam::label i = 0; i < faces; ++i)
    {
        uniform[2 * i] = 0.001;
        uniform[2 * i + 1] = -0.002;
    }
    reader.read(uniform.data(), 2);
    forAll(cell.boundaryField()[patch], i)
    {
        if (Foam::mag(cell.boundaryField()[patch][i]
            - Foam::vector(0.001, -0.002, 0)) > 1e-13)
        {
            FatalErrorInFunction << "uniform face transfer mismatch"
                                      << Foam::exit(Foam::FatalError);
        }
    }
    const Foam::vectorField& pointPatch = Foam::refCast<const Foam::vectorField>(
        pointDisplacement.boundaryField()[patch]);
    forAll(pointPatch, i)
    {
        if (Foam::mag(pointPatch[i]
            - Foam::vector(0.001, -0.002, 0)) > 1e-13)
        {
            FatalErrorInFunction << "uniform point transfer mismatch at " << i
                                 << " got=" << pointPatch[i]
                                      << Foam::exit(Foam::FatalError);
        }
    }

    std::vector<double> patterned(2 * faces);
    for (Foam::label i = 0; i < faces; ++i)
    {
        patterned[2 * i] = 1e-4 * (i + 1);
        patterned[2 * i + 1] = -2e-4 * (i + 1);
    }
    reader.read(patterned.data(), 2);
    Foam::primitivePatchInterpolation interpolation(mesh.boundaryMesh()[patch]);
    const Foam::vectorField expected = interpolation.faceToPointInterpolate(
        cell.boundaryField()[patch]);
    forAll(expected, i)
    {
        if (Foam::mag(pointPatch[i]
            - expected[i]) > 1e-13)
        {
            FatalErrorInFunction << "nonuniform point transfer mismatch at " << i
                                 << " got=" << pointPatch[i]
                                 << " expected=" << expected[i]
                                      << Foam::exit(Foam::FatalError);
        }
    }
    Foam::Info << "PHASE1K17_FIELD_TEST_PASS faces=" << faces
               << " points=" << expected.size() << Foam::endl;
    return 0;
}
