#ifndef PHASE1K29_INNER_TRACE_H
#define PHASE1K29_INNER_TRACE_H

#include "fvMesh.H"
#include "incompressibleMomentumTransportModels.H"
#include "surfaceFields.H"
#include "volFields.H"

#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>

namespace phase1k29diag
{
inline void mix(std::uint64_t& h, const void* data, const std::size_t n)
{
    const auto* bytes = static_cast<const unsigned char*>(data);
    for (std::size_t i = 0; i < n; ++i)
    {
        h ^= bytes[i];
        h *= UINT64_C(1099511628211);
    }
}

template<class Value>
inline void mixValue(std::uint64_t& h, const Value& value)
{
    mix(h, &value, sizeof(Value));
}

inline std::string hex(const std::uint64_t value)
{
    std::ostringstream out;
    out << std::hex << std::setfill('0') << std::setw(16) << value;
    return out.str();
}

template<class Field>
inline std::uint64_t hashField(const Field& field)
{
    std::uint64_t h = UINT64_C(14695981039346656037);
    const auto& internal = field.primitiveField();
    const std::uint64_t n = internal.size();
    mix(h, &n, sizeof(n));
    forAll(internal, i) mixValue(h, internal[i]);
    return h;
}

template<class Field>
inline Foam::scalar l2Field(const Field& field)
{
    Foam::scalar sum = 0;
    forAll(field.primitiveField(), i) sum += Foam::magSqr(field.primitiveField()[i]);
    return Foam::sqrt(sum);
}

template<class Field>
inline Foam::scalar linfField(const Field& field)
{
    Foam::scalar result = 0;
    forAll(field.primitiveField(), i) result = Foam::max(result, Foam::mag(field.primitiveField()[i]));
    return result;
}

inline void append(const char* variable, const std::string& line)
{
    const char* path = std::getenv(variable);
    if (path == nullptr || *path == '\0')
    {
        throw std::runtime_error(std::string("required Phase 1K.29 trace path is unset: ") + variable);
    }
    std::ofstream out(path, std::ios::out | std::ios::app);
    if (!out) throw std::runtime_error(std::string("cannot open Phase 1K.29 trace: ") + path);
    out << line << '\n';
    out.flush();
    if (!out) throw std::runtime_error(std::string("cannot write Phase 1K.29 trace: ") + path);
}

inline Foam::scalar rho(const Foam::fvMesh& mesh)
{
    const Foam::dictionary& dict =
        mesh.lookupObject<Foam::IOdictionary>("preciceDict").subOrEmptyDict("FSI");
    const Foam::dimensionedScalar value(dict.lookup("rho"));
    return value.value();
}

inline void writeOuter(
    const Foam::fvMesh& mesh,
    const Foam::volScalarField& p,
    const Foam::volVectorField& U,
    const Foam::volScalarField& k,
    const Foam::volScalarField& omega,
    const Foam::volScalarField& nut,
    const Foam::surfaceScalarField& phi,
    const Foam::incompressible::momentumTransportModel& turbulence,
    const Foam::label solveId,
    const Foam::label outer)
{
    const Foam::label patchID = mesh.boundaryMesh().findPatchID("cylinder");
    if (patchID < 0) throw std::runtime_error("Phase 1K.29 cylinder patch not found");
    const Foam::vectorField surface(mesh.boundary()[patchID].Sf());
    const auto& pb = p.boundaryField()[patchID];
    Foam::tmp<Foam::volSymmTensorField> tDev(turbulence.devSigma());
    const auto& dev = tDev().boundaryField()[patchID];
    const Foam::scalar density = rho(mesh);
    Foam::vector pressure(Foam::vector::zero), viscous(Foam::vector::zero), total(Foam::vector::zero);
    std::uint64_t hp = UINT64_C(14695981039346656037);
    std::uint64_t hv = UINT64_C(14695981039346656037);
    std::uint64_t ht = UINT64_C(14695981039346656037);
    forAll(surface, i)
    {
        const Foam::vector pf = surface[i] * pb[i] * density;
        const Foam::vector vf = surface[i] & dev[i];
        const Foam::vector tf = pf + vf;
        pressure += pf; viscous += vf; total += tf;
        mixValue(hp, pf); mixValue(hv, vf); mixValue(ht, tf);
    }
    std::ostringstream out;
    out << std::setprecision(17)
        << "{\"solve_id\":" << solveId
        << ",\"outer\":" << outer
        << ",\"time_s\":" << mesh.time().value()
        << ",\"time_index\":" << mesh.time().timeIndex()
        << ",\"patch\":\"cylinder\",\"face_count\":" << surface.size()
        << ",\"pressure_integrated_xyz\":[" << pressure.x() << ',' << pressure.y() << ',' << pressure.z() << ']'
        << ",\"viscous_integrated_xyz\":[" << viscous.x() << ',' << viscous.y() << ',' << viscous.z() << ']'
        << ",\"raw_integrated_xyz\":[" << total.x() << ',' << total.y() << ',' << total.z() << ']'
        << ",\"pressure_array_hash\":\"" << hex(hp)
        << "\",\"viscous_array_hash\":\"" << hex(hv)
        << "\",\"raw_array_hash\":\"" << hex(ht) << '\"'
        << ",\"field_stats\":{";
    out << "\"U\":{\"hash\":\"" << hex(hashField(U)) << "\",\"l2\":" << l2Field(U) << ",\"linf\":" << linfField(U) << "},";
    out << "\"p\":{\"hash\":\"" << hex(hashField(p)) << "\",\"l2\":" << l2Field(p) << ",\"linf\":" << linfField(p) << "},";
    out << "\"k\":{\"hash\":\"" << hex(hashField(k)) << "\",\"l2\":" << l2Field(k) << ",\"linf\":" << linfField(k) << "},";
    out << "\"omega\":{\"hash\":\"" << hex(hashField(omega)) << "\",\"l2\":" << l2Field(omega) << ",\"linf\":" << linfField(omega) << "},";
    out << "\"nut\":{\"hash\":\"" << hex(hashField(nut)) << "\",\"l2\":" << l2Field(nut) << ",\"linf\":" << linfField(nut) << "},";
    out << "\"phi\":{\"hash\":\"" << hex(hashField(phi)) << "\",\"l2\":" << l2Field(phi) << ",\"linf\":" << linfField(phi) << "}}}";
    append("PHASE1K29_OUTER_FORCE_TRACE", out.str());
}
}

#endif
