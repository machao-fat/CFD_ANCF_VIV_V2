#include "Displacement.H"
#include "Utilities.H"
#include <iomanip>
#include <sstream>

using namespace Foam;

namespace
{
std::string preciseScalar(const Foam::scalar value)
{
    std::ostringstream stream;
    stream << std::setprecision(17) << value;
    return stream.str();
}

// The face-centre preCICE reader needs an auxiliary volume field even though
// the RBF motion solver itself consumes only pointDisplacement.  Construct it
// before this Displacement reader and the adapter checkpoint are configured.
volVectorField* lookupOrCreateCellDisplacement(
    const fvMesh& mesh, const std::string& requestedName)
{
    const word name(requestedName);
    if (!mesh.foundObject<volVectorField>(name))
    {
        wordList patchTypes(mesh.boundary().size(), "fixedValue");
        forAll(mesh.boundary(), patchI)
        {
            const word& type = mesh.boundary()[patchI].type();
            if (type == "empty" || type == "symmetryPlane")
            {
                patchTypes[patchI] = type;
            }
        }

        volVectorField* field = new volVectorField(
            IOobject(name, mesh.time().timeName(), mesh,
                     IOobject::NO_READ, IOobject::AUTO_WRITE),
            mesh, dimensionedVector("zero", dimLength, Zero), patchTypes);
        mesh.objectRegistry::store(field);
        adapterInfo("PHASE1K17_FIELD_CREATED name=" + requestedName
                    + " time=" + preciseScalar(mesh.time().value())
                    + " cells=" + std::to_string(mesh.nCells()), "info");
    }

    volVectorField& field =
        const_cast<volVectorField&>(mesh.lookupObject<volVectorField>(name));
    if (field.dimensions() != dimLength ||
        field.boundaryField().size() != mesh.boundary().size())
    {
        FatalErrorInFunction << "Invalid cellDisplacement staging field "
                             << name << exit(FatalError);
    }
    forAll(mesh.boundary(), patchI)
    {
        if (field.boundaryField()[patchI].size() != mesh.boundary()[patchI].size())
        {
            FatalErrorInFunction << "cellDisplacement patch-size mismatch "
                                 << mesh.boundary()[patchI].name()
                                 << exit(FatalError);
        }
    }
    adapterInfo("PHASE1K17_FIELD_READY name=" + requestedName
                + " registered=" + std::to_string(mesh.foundObject<volVectorField>(name)),
                "info");
    return &field;
}
}

preciceAdapter::FSI::Displacement::Displacement(
    const Foam::fvMesh& mesh,
    const std::string namePointDisplacement,
    const std::string nameCellDisplacement)
: pointDisplacement_(
    namePointDisplacement == "unused"
        ? nullptr
        : const_cast<pointVectorField*>(
            &mesh.lookupObject<pointVectorField>(namePointDisplacement))),
  cellDisplacement_(
      lookupOrCreateCellDisplacement(mesh, nameCellDisplacement)),
  mesh_(mesh)
{
    dataType_ = vector;
}

// We cannot do this step in the constructor by design of the adapter since the information of the CouplingDataUser is
// defined later. Hence, we call this method after the CouplingDaaUser has been configured
void preciceAdapter::FSI::Displacement::initialize()
{
    // Initialize appropriate objects for each interface patch, namely the volField and the interpolation object
    // this is only necessary for face based FSI
    if (this->locationType_ == LocationType::faceCenters)
    {
        for (unsigned int j = 0; j < patchIDs_.size(); ++j)
        {
            const unsigned int patchID = patchIDs_.at(j);
            interpolationObjects_.emplace_back(new primitivePatchInterpolation(mesh_.boundaryMesh()[patchID]));
        }
    }
}


std::size_t preciceAdapter::FSI::Displacement::write(double* buffer, bool meshConnectivity, const unsigned int dim)
{
    /* TODO: Implement
     * We need two nested for-loops for each patch,
     * the outer for the locations and the inner for the dimensions.
     * See the preCICE writeBlockVectorData() implementation.
     */

    // Copy the displacement field from OpenFOAM to the buffer

    int bufferIndex = 0;
    if (this->locationType_ == LocationType::faceCenters)
    {
        // For every boundary patch of the interface
        for (const label patchID : patchIDs_)
        {
            // Write the displacement to the preCICE buffer
            // For every cell of the patch
            forAll(cellDisplacement_->boundaryField()[patchID], i)
            {
                for (unsigned int d = 0; d < dim; ++d)
                    buffer[bufferIndex++] =
                        cellDisplacement_->boundaryField()[patchID][i][d];
            }
        }
    }
    else if (this->locationType_ == LocationType::faceNodes)
    {
        DEBUG(adapterInfo(
            "Please be aware of issues with using 'locationType faceNodes' "
            "in parallel. \n"
            "See https://github.com/precice/openfoam-adapter/issues/153.",
            "warning"));

        // For every boundary patch of the interface
        for (const label patchID : patchIDs_)
        {
            // Write the displacement to the preCICE buffer
            // For every cell of the patch
            forAll(pointDisplacement_->boundaryField()[patchID], i)
            {
                const labelList& meshPoints =
                    mesh_.boundaryMesh()[patchID].meshPoints();

                for (unsigned int d = 0; d < dim; ++d)
                    buffer[bufferIndex++] =
                        pointDisplacement_->internalField()[meshPoints[i]][d];
            }
        }
    }
    return bufferIndex;
}


// return the displacement to use later in the velocity?
void preciceAdapter::FSI::Displacement::read(double* buffer, const unsigned int dim)
{
    int bufferIndex = 0;
    for (unsigned int j = 0; j < patchIDs_.size(); j++)
    {
        // Get the ID of the current patch
        const unsigned int patchID = patchIDs_.at(j);

        if (this->locationType_ == LocationType::faceCenters)
        {
            // the boundaryCellDisplacement is a vector and ordered according to the iterator j
            // and not according to the patchID
            // First, copy the buffer data into the center based vectorFields on each interface patch
            forAll(cellDisplacement_->boundaryField()[patchID], i)
            {
                for (unsigned int d = 0; d < dim; ++d)
                    cellDisplacement_->boundaryFieldRef()[patchID][i][d] = buffer[bufferIndex++];
            }
            Foam::scalar maxFaceNorm = 0.0;
            forAll(cellDisplacement_->boundaryField()[patchID], faceI)
            {
                maxFaceNorm = Foam::max(
                    maxFaceNorm, mag(cellDisplacement_->boundaryField()[patchID][faceI]));
            }
            adapterInfo("PHASE1K17_CELL_BOUNDARY patch="
                            + mesh_.boundaryMesh()[patchID].name()
                            + " faces="
                            + std::to_string(cellDisplacement_->boundaryField()[patchID].size())
                            + " max_norm=" + preciseScalar(maxFaceNorm), "info");

            if (pointDisplacement_ != nullptr)
            {
                // Get a reference to the displacement on the point patch in order to overwrite it
                vectorField& pointDisplacementFluidPatch(
                    refCast<vectorField>(
                        pointDisplacement_->boundaryFieldRef()[patchID]));

                // Overwrite the node based patch using the interpolation objects and the cell based vector field
                // Afterwards, continue as usual
                pointDisplacementFluidPatch = interpolationObjects_[j]->faceToPointInterpolate(cellDisplacement_->boundaryField()[patchID]);

                Foam::scalar maxPointNorm = 0.0;
                forAll(pointDisplacementFluidPatch, pointI)
                {
                    maxPointNorm = Foam::max(maxPointNorm, mag(pointDisplacementFluidPatch[pointI]));
                }
                adapterInfo("PHASE1K17_POINT_BOUNDARY patch="
                                + mesh_.boundaryMesh()[patchID].name()
                                + " max_norm=" + preciseScalar(maxPointNorm), "info");
            }
        }
        else if (this->locationType_ == LocationType::faceNodes)
        {

            // Get the displacement on the patch
            fixedValuePointPatchVectorField& pointDisplacementFluidPatch(
                refCast<fixedValuePointPatchVectorField>(
                    pointDisplacement_->boundaryFieldRef()[patchID]));

            // Overwrite the nodes on the interface directly
            forAll(pointDisplacement_->boundaryFieldRef()[patchID], i)
            {
                for (unsigned int d = 0; d < dim; ++d)
                    pointDisplacementFluidPatch[i][d] = buffer[bufferIndex++];
            }
        }
    }
}

bool preciceAdapter::FSI::Displacement::isLocationTypeSupported(const bool meshConnectivity) const
{
    return (this->locationType_ == LocationType::faceCenters || this->locationType_ == LocationType::faceNodes);
}

std::string preciceAdapter::FSI::Displacement::getDataName() const
{
    return "Displacement";
}
