#include "structure_state_evaluator.hpp"

#include <cmath>
#include <stdexcept>

namespace nm10_mapping {

EvaluatedStructureState evaluateStructureState(
    const cfd_ancf::Model& model, double s_m,
    const std::vector<double>& q,
    const std::vector<double>& q_reference,
    const std::vector<double>& qdot,
    const std::vector<double>& qddot) {
  if (!std::isfinite(s_m) || s_m < 0.0 || s_m > model.length_m ||
      q.size() != model.ndof() || q_reference.size() != model.ndof() ||
      qdot.size() != model.ndof() || qddot.size() != model.ndof())
    throw std::invalid_argument("structure state evaluation dimensions/position invalid");
  cfd_ancf::Model point_model = model;
  point_model.slices = 1;
  point_model.slice_positions_m = {s_m};
  const cfd_ancf::Matrix H = cfd_ancf::mapping_H3(point_model);
  EvaluatedStructureState result;
  for (std::size_t dof = 0; dof < model.ndof(); ++dof) {
    for (std::size_t c = 0; c < 3; ++c) {
      result.r_m[c] += H(c, dof) * q[dof];
      result.displacement_m[c] += H(c, dof) * (q[dof] - q_reference[dof]);
      result.velocity_m_s[c] += H(c, dof) * qdot[dof];
      result.acceleration_m_s2[c] += H(c, dof) * qddot[dof];
    }
  }
  return result;
}

}  // namespace nm10_mapping
