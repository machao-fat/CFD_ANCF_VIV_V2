#ifndef PHASE1K20_POINT_DISPLACEMENT_CHECKPOINT_H
#define PHASE1K20_POINT_DISPLACEMENT_CHECKPOINT_H

#include "pointFields.H"
#include "valuePointPatchField.H"
#include "error.H"
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <vector>

// Experimental HH06 point-field checkpoint. Never use GeometricField::operator==
// to save or restore a fixedValue point patch: on Foundation-10 it substitutes
// patchInternalField() for the stored patch value array.
namespace phase1k20
{
class PointDisplacementCheckpoint
{
    struct Patch
    {
        Foam::word name;
        Foam::word type;
        bool storedValues;
        Foam::vectorField values;
    };

    Foam::vectorField internal_;
    std::vector<Patch> patches_;
    std::uint64_t checksum_ = 0;
    bool captured_ = false;

    static void mix(std::uint64_t& hash, const void* data, std::size_t size)
    {
        const unsigned char* bytes = static_cast<const unsigned char*>(data);
        for (std::size_t i = 0; i < size; ++i)
        {
            hash ^= bytes[i];
            hash *= UINT64_C(1099511628211);
        }
    }

    static void mixWord(std::uint64_t& hash, const Foam::word& word)
    {
        const std::uint64_t size = word.size();
        mix(hash, &size, sizeof(size));
        mix(hash, word.c_str(), word.size());
    }

    static void mixValues(std::uint64_t& hash, const Foam::vectorField& values)
    {
        const std::uint64_t size = values.size();
        mix(hash, &size, sizeof(size));
        forAll(values, i)
        {
            for (Foam::direction d = 0; d < 3; ++d)
            {
                const Foam::scalar value = values[i][d];
                mix(hash, &value, sizeof(value));
            }
        }
    }

    static Foam::vectorField patchValues(const Foam::pointPatchField<Foam::vector>& patch)
    {
        if (Foam::isA<Foam::valuePointPatchField<Foam::vector>>(patch))
        {
            return Foam::refCast<const Foam::valuePointPatchField<Foam::vector>>(patch);
        }
        const Foam::tmp<Foam::Field<Foam::vector>> derived = patch.patchInternalField();
        return derived();
    }

    static std::uint64_t stateChecksum(const Foam::pointVectorField& field)
    {
        std::uint64_t hash = UINT64_C(14695981039346656037);
        mixWord(hash, field.name());
        mixValues(hash, field.primitiveField());
        forAll(field.boundaryField(), patchI)
        {
            const auto& patch = field.boundaryField()[patchI];
            mixWord(hash, patch.patch().name());
            mixWord(hash, patch.type());
            const bool stored = Foam::isA<Foam::valuePointPatchField<Foam::vector>>(patch);
            mix(hash, &stored, sizeof(stored));
            mixValues(hash, patchValues(patch));
        }
        return hash;
    }

public:
    void capture(const Foam::pointVectorField& field)
    {
        if (field.name() != "pointDisplacement" || field.nOldTimes() != 0)
        {
            throw std::runtime_error("Phase1K20 only supports pointDisplacement with no oldTime levels");
        }
        internal_ = field.primitiveField();
        patches_.clear();
        forAll(field.boundaryField(), patchI)
        {
            const auto& source = field.boundaryField()[patchI];
            const bool stored = Foam::isA<Foam::valuePointPatchField<Foam::vector>>(source);
            const Foam::word type = source.type();
            if (!(type == "fixedValue" || type == "empty" || type == "symmetryPlane"))
            {
                throw std::runtime_error("Phase1K20 unsupported pointDisplacement patch type");
            }
            if ((type == "fixedValue") != stored)
            {
                throw std::runtime_error("Phase1K20 fixedValue patch storage mismatch");
            }
            patches_.push_back({source.patch().name(), type, stored, patchValues(source)});
        }
        checksum_ = stateChecksum(field);
        captured_ = true;
        if (!matches(field)) throw std::runtime_error("Phase1K20 checkpoint save verification failed");
    }

    bool matches(const Foam::pointVectorField& field) const
    {
        if (!captured_ || field.name() != "pointDisplacement" ||
            field.primitiveField().size() != internal_.size() ||
            static_cast<std::size_t>(field.boundaryField().size()) != patches_.size()) return false;
        forAll(internal_, i)
        {
            for (Foam::direction d = 0; d < 3; ++d)
                if (std::memcmp(&internal_[i][d], &field.primitiveField()[i][d],
                                sizeof(Foam::scalar)) != 0) return false;
        }
        forAll(field.boundaryField(), patchI)
        {
            const auto& patch = field.boundaryField()[patchI];
            const auto& saved = patches_.at(patchI);
            if (patch.patch().name() != saved.name || patch.type() != saved.type ||
                Foam::isA<Foam::valuePointPatchField<Foam::vector>>(patch) != saved.storedValues)
                return false;
            const Foam::vectorField now = patchValues(patch);
            if (now.size() != saved.values.size()) return false;
            forAll(now, i)
            {
                for (Foam::direction d = 0; d < 3; ++d)
                    if (std::memcmp(&now[i][d], &saved.values[i][d],
                                    sizeof(Foam::scalar)) != 0) return false;
            }
        }
        return stateChecksum(field) == checksum_;
    }

    void restore(Foam::pointVectorField& field) const
    {
        if (!captured_ || field.name() != "pointDisplacement" ||
            field.nOldTimes() != 0 || field.primitiveField().size() != internal_.size() ||
            static_cast<std::size_t>(field.boundaryField().size()) != patches_.size())
        {
            throw std::runtime_error("Phase1K20 incompatible pointDisplacement checkpoint");
        }
        forAll(field.boundaryField(), patchI)
        {
            const auto& patch = field.boundaryField()[patchI];
            const auto& saved = patches_.at(patchI);
            if (patch.patch().name() != saved.name || patch.type() != saved.type ||
                patch.size() != saved.values.size() ||
                Foam::isA<Foam::valuePointPatchField<Foam::vector>>(patch) != saved.storedValues)
                throw std::runtime_error("Phase1K20 point patch topology/type mismatch");
        }
        field.primitiveFieldRef() = internal_;
        forAll(field.boundaryField(), patchI)
        {
            const auto& saved = patches_.at(patchI);
            if (!saved.storedValues) continue; // derived empty/symmetry values follow internal field
            auto& patch = field.boundaryFieldRef()[patchI];
            Foam::vectorField& raw = Foam::refCast<Foam::vectorField>(patch);
            raw = saved.values; // bypass fixedValuePointPatchField::operator=(Field)
        }
        if (!matches(field)) throw std::runtime_error("Phase1K20 restore checksum mismatch");
    }

    std::string checksumHex() const
    {
        std::ostringstream out;
        out << std::hex << std::setfill('0') << std::setw(16) << checksum_;
        return out.str();
    }
};
}

#endif
