#pragma once

#include "ancf_kernel.hpp"

#include <array>
#include <vector>

namespace nm10_mapping {

struct EvaluatedStructureState {
  std::array<double, 3> r_m{};
  std::array<double, 3> displacement_m{};
  std::array<double, 3> velocity_m_s{};
  std::array<double, 3> acceleration_m_s2{};
};

// Read-only evaluator using the frozen kernel's mapping_H3(s) path.  The
// coupling contract writes only displacement; velocity and acceleration are
// diagnostic outputs and never enter preCICE writes or convergence measures.
EvaluatedStructureState evaluateStructureState(
    const cfd_ancf::Model& model, double s_m,
    const std::vector<double>& q,
    const std::vector<double>& q_reference,
    const std::vector<double>& qdot,
    const std::vector<double>& qddot);

}  // namespace nm10_mapping
