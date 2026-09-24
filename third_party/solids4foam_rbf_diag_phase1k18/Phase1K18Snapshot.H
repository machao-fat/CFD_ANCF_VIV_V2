#ifndef Phase1K18Snapshot_H
#define Phase1K18Snapshot_H

#include "fvMesh.H"
#include "polyMesh.H"
#include "pointFields.H"
#include "valuePointPatchField.H"
#include "volFields.H"
#include "Pstream.H"
#include "IOstreams.H"
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unistd.h>

namespace phase1k18diag
{
struct NormRange
{
    Foam::scalar minNorm;
    Foam::scalar maxNorm;
    Foam::label count;

    NormRange()
    : minNorm(std::numeric_limits<Foam::scalar>::max()), maxNorm(0), count(0)
    {}

    void add(const Foam::vector& value)
    {
        const Foam::scalar valueNorm = Foam::mag(value);
        minNorm = Foam::min(minNorm, valueNorm);
        maxNorm = Foam::max(maxNorm, valueNorm);
        ++count;
    }

    void emit(std::ostream& out) const
    {
        out << "{\"count\":" << count
            << ",\"min_norm\":" << (count ? minNorm : 0)
            << ",\"max_norm\":" << maxNorm << "}";
    }
};

template<class Values>
void writeValues(std::ostream& out, const Values& values, NormRange& range)
{
    out << '[';
    forAll(values, i)
    {
        if (i) out << ',';
        const Foam::vector& value = values[i];
        out << '[' << value[0] << ',' << value[1] << ',' << value[2] << ']';
        range.add(value);
    }
    out << ']';
}

inline void writeQuoted(std::ostream& out, const std::string& value)
{
    out << '"';
    for (std::string::const_iterator i = value.begin(); i != value.end(); ++i)
    {
        if (*i == '"' || *i == '\\') out << '\\';
        out << *i;
    }
    out << '"';
}

template<class FieldType>
void writeField(std::ostream& out, const Foam::polyMesh& mesh,
                const FieldType& field)
{
    NormRange allRange, internalRange, boundaryRange;
    out << "{\"internal\":";
    writeValues(out, field.primitiveField(), internalRange);
    out << ",\"boundary\":{";
    forAll(field.boundaryField(), patchI)
    {
        if (patchI) out << ',';
        writeQuoted(out, mesh.boundaryMesh()[patchI].name());
        out << ':';
        writeValues(out, field.boundaryField()[patchI], boundaryRange);
    }
    out << "},\"norms\":{\"internal\":";
    internalRange.emit(out);
    out << ",\"boundary\":";
    boundaryRange.emit(out);
    allRange.minNorm = Foam::min(internalRange.minNorm, boundaryRange.minNorm);
    allRange.maxNorm = Foam::max(internalRange.maxNorm, boundaryRange.maxNorm);
    allRange.count = internalRange.count + boundaryRange.count;
    out << ",\"all\":";
    allRange.emit(out);
    out << "}}";
}

inline void writePointField(std::ostream& out, const Foam::polyMesh& mesh,
                            const Foam::pointVectorField& field)
{
    NormRange allRange, internalRange, boundaryRange;
    out << "{\"internal\":";
    writeValues(out, field.primitiveField(), internalRange);
    out << ",\"boundary\":{";
    forAll(field.boundaryField(), patchI)
    {
        if (patchI) out << ',';
        writeQuoted(out, mesh.boundaryMesh()[patchI].name());
        out << ":{\"type\":";
        const Foam::pointPatchField<Foam::vector>& patchField =
            field.boundaryField()[patchI];
        writeQuoted(out, std::string(patchField.type().c_str()));
        out << ",\"value_source\":";
        if (Foam::isA<Foam::valuePointPatchField<Foam::vector>>(patchField))
        {
            writeQuoted(out, "stored_patch_values");
            out << ",\"values\":";
            const Foam::valuePointPatchField<Foam::vector>& valuePatch =
                Foam::refCast<const Foam::valuePointPatchField<Foam::vector>>
                (
                    patchField
                );
            writeValues(out, valuePatch, boundaryRange);
        }
        else
        {
            writeQuoted(out, "patch_internal_field_fallback");
            out << ",\"values\":";
            const Foam::tmp<Foam::Field<Foam::vector>> patchInternal =
                patchField.patchInternalField();
            writeValues(out, patchInternal(), boundaryRange);
        }
        out << '}';
    }
    out << "},\"norms\":{\"internal\":";
    internalRange.emit(out);
    out << ",\"boundary\":";
    boundaryRange.emit(out);
    allRange.minNorm = Foam::min(internalRange.minNorm, boundaryRange.minNorm);
    allRange.maxNorm = Foam::max(internalRange.maxNorm, boundaryRange.maxNorm);
    allRange.count = internalRange.count + boundaryRange.count;
    out << ",\"all\":";
    allRange.emit(out);
    out << "}}";
}

inline void writeMeshPoints(std::ostream& out, const Foam::pointField& points,
                            NormRange& range)
{
    writeValues(out, points, range);
}

inline void writeSnapshot(const Foam::polyMesh& mesh,
                          const Foam::pointVectorField& pointDisplacement,
                          const Foam::volVectorField& cellDisplacement,
                          const std::string& stage,
                          const Foam::pointField* candidateMeshPoints = nullptr)
{
    const char* directory = std::getenv("PHASE1K18_DIAG_DIR");
    if (directory == nullptr || *directory == '\0')
    {
        throw std::runtime_error("PHASE1K18_DIAG_DIR is not set");
    }

    std::ostringstream path;
    path << directory << '/' << stage << ".json";
    Foam::Info << "PHASE1K18_SNAPSHOT stage=" << stage
               << " file=" << path.str()
               << " time=" << mesh.time().value()
               << " rank=" << Foam::Pstream::myProcNo()
               << " pid=" << ::getpid() << Foam::endl;
    std::ofstream out(path.str().c_str(), std::ios::out | std::ios::trunc);
    if (!out) throw std::runtime_error("cannot create point-state snapshot: " + path.str());
    out << std::setprecision(17);
    out << "{\"stage\":";
    writeQuoted(out, stage);
    out << ",\"time_s\":" << mesh.time().value()
        << ",\"time_dir\":";
    writeQuoted(out, mesh.time().timeName());
    out << ",\"mpi_rank\":" << Foam::Pstream::myProcNo()
        << ",\"pid\":" << ::getpid()
        << ",\"pointDisplacement\":";
    writePointField(out, mesh, pointDisplacement);
    out << ",\"cellDisplacement\":";
    writeField(out, mesh, cellDisplacement);
    NormRange meshPointRange;
    out << ",\"mesh_points\":";
    writeMeshPoints(out, mesh.points(), meshPointRange);
    out << ",\"mesh_point_coordinate_norms\":";
    meshPointRange.emit(out);
    if (candidateMeshPoints != nullptr)
    {
        NormRange candidateRange;
        out << ",\"rbf_candidate_mesh_points\":";
        writeMeshPoints(out, *candidateMeshPoints, candidateRange);
        out << ",\"rbf_candidate_coordinate_norms\":";
        candidateRange.emit(out);
    }
    out << "}\n";
    out.close();
    if (!out) throw std::runtime_error("failed writing point-state snapshot: " + path.str());
}
}

#endif
