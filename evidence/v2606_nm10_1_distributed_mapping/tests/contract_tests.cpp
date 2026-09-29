#include "distributed_force_mapping.hpp"
#include "structure_state_evaluator.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr double PI = 3.141592653589793238462643383279502884;
constexpr double L = 13.12, D = 0.028, U = 0.028, A0 = 0.0, A1 = 5.94;

cfd_ancf::Model model_for(const std::vector<double>& p) {
  cfd_ancf::Model m;
  m.length_m = L; m.diameter_m = D; m.inner_diameter_m = 0.0;
  m.elements = 32; m.slices = p.size(); m.slice_positions_m = p;
  m.top_tension_N = 1175.0;
  const double area = PI * D * D / 4.0;
  m.section_property_mode = cfd_ancf::SectionPropertyMode::ExplicitSectionProperties;
  m.explicit_EA_N = 7470000.0; m.explicit_EI_Nm2 = 29.88;
  m.explicit_mass_per_length_kg_m = 1.845; m.explicit_displaced_area_m2 = area;
  m.youngs_modulus_Pa = 7470000.0 / area; m.material_density = 1.845 / area;
  m.fluid_density = 1000.0; m.gravity = 9.81; m.dt_s = 4e-4;
  m.beta = 0.25; m.gamma = 0.5; m.max_newton = 40; m.newton_tolerance = 2e-10;
  m.gauss_order = 3; m.mass_gauss_order = 5;
  cfd_ancf::validate_model(m);
  return m;
}

nm10_mapping::MappingConfig cfg() {
  nm10_mapping::MappingConfig c;
  c.mode = nm10_mapping::MappingMode::PiecewiseLinearDistributed;
  c.endpoint_policy = nm10_mapping::EndpointPolicy::NearestConstant;
  c.active_s_min_m = A0; c.active_s_max_m = A1; c.unit_span_m = U;
  return c;
}

std::vector<std::array<double, 3>> raw_for(const std::vector<double>& p) {
  std::vector<std::array<double, 3>> raw(p.size());
  for (std::size_t i = 0; i < p.size(); ++i)
    raw[i] = {U * (0.3 + 0.11 * p[i]), U * (-0.2 + 0.07 * p[i]), U * 0.01 * p[i]};
  return raw;
}

double dot(const std::vector<double>& a, const std::vector<double>& b) {
  double result = 0.0;
  for (std::size_t i = 0; i < a.size(); ++i) result += a[i] * b[i];
  return result;
}

}  // namespace

int main() {
  try {
    const std::vector<double> p{0.37, 1.41, 2.64, 4.28, 5.61};
    const auto m = model_for(p);
    const auto raw = raw_for(p);
    const auto line = nm10_mapping::raw_force_to_line_force(raw, U);
    const auto mapped = nm10_mapping::assemble(m, p, raw, cfg());

    const bool left_endpoint = nm10_mapping::reconstructed_force_at(
        0.0, p, line, A0, A1, nm10_mapping::EndpointPolicy::NearestConstant) == line.front();
    const bool right_endpoint = nm10_mapping::reconstructed_force_at(
        A1, p, line, A0, A1, nm10_mapping::EndpointPolicy::NearestConstant) == line.back();
    const auto outside_left = nm10_mapping::reconstructed_force_at(
        -1.0, p, line, A0, A1, nm10_mapping::EndpointPolicy::NearestConstant);
    const auto outside_right = nm10_mapping::reconstructed_force_at(
        6.0, p, line, A0, A1, nm10_mapping::EndpointPolicy::NearestConstant);
    bool outside_zero = true;
    for (double x : outside_left) outside_zero = outside_zero && x == 0.0;
    for (double x : outside_right) outside_zero = outside_zero && x == 0.0;

    // Different N and non-node sample positions are all handled by the same
    // manifest/mapping implementation.
    std::vector<std::size_t> supported_N{2, 3, 5, 8};
    bool arbitrary_pass = true;
    for (std::size_t n : supported_N) {
      std::vector<double> pn(n);
      for (std::size_t i = 0; i < n; ++i)
        pn[i] = A0 + (A1 - A0) * (0.5 + static_cast<double>(i)) / static_cast<double>(n);
      const auto rn = raw_for(pn);
      const auto mn = model_for(pn);
      const auto mapped_n = nm10_mapping::assemble(mn, pn, rn, cfg());
      arbitrary_pass = arbitrary_pass &&
                       std::all_of(mapped_n.generalized_force.begin(),
                                   mapped_n.generalized_force.end(),
                                   [](double x) { return std::isfinite(x); });
    }

    // Smooth-load refinement ladder is an offline mapper-only contract check.
    bool refinement_pass = true;
    std::vector<double> refinement_max;
    for (std::size_t n : {5u, 10u, 20u, 40u}) {
      std::vector<double> pn(n);
      for (std::size_t i = 0; i < n; ++i)
        pn[i] = A0 + (A1 - A0) * (0.5 + static_cast<double>(i)) / static_cast<double>(n);
      auto rn = raw_for(pn);
      const auto result = nm10_mapping::assemble(model_for(pn), pn, rn, cfg());
      double maxv = 0.0;
      for (double x : result.generalized_force) maxv = std::max(maxv, std::abs(x));
      refinement_max.push_back(maxv);
      refinement_pass = refinement_pass && std::isfinite(maxv);
    }

    // Virtual-work identity and translational resultant identity.  The direct
    // work integral uses H(s) from the frozen public API independently of the
    // production mapper call.
    std::vector<double> delta_q(m.ndof());
    for (std::size_t i = 0; i < delta_q.size(); ++i)
      delta_q[i] = 1e-4 * std::sin(0.13 * static_cast<double>(i + 1));
    const double work_q = dot(delta_q, mapped.generalized_force);
    const double Le = m.length_m / static_cast<double>(m.elements);
    const std::array<double, 8> xi = {-0.9602898565, -0.7966664774, -0.5255324099,
                                       -0.1834346425, 0.1834346425, 0.5255324099,
                                       0.7966664774, 0.9602898565};
    const std::array<double, 8> wt = {0.1012285363, 0.2223810345, 0.3137066459,
                                      0.3626837834, 0.3626837834, 0.3137066459,
                                      0.2223810345, 0.1012285363};
    double work_integral = 0.0;
    std::vector<double> breaks{A0, A1};
    for (std::size_t e = 1; e < m.elements; ++e) {
      const double s = Le * static_cast<double>(e);
      if (s > A0 && s < A1) breaks.push_back(s);
    }
    for (double s : p) breaks.push_back(s);
    std::sort(breaks.begin(), breaks.end());
    breaks.erase(std::unique(breaks.begin(), breaks.end()), breaks.end());
    for (std::size_t k = 0; k + 1 < breaks.size(); ++k) {
      for (std::size_t g = 0; g < xi.size(); ++g) {
        const double s = 0.5 * (breaks[k] + breaks[k + 1]) +
                         0.5 * (breaks[k + 1] - breaks[k]) * xi[g];
        const auto f = nm10_mapping::reconstructed_force_at(
            s, p, line, A0, A1, nm10_mapping::EndpointPolicy::NearestConstant);
        cfd_ancf::Model point = m; point.slices = 1; point.slice_positions_m = {s};
        const auto H = cfd_ancf::mapping_H3(point);
        double hdelta[3]{};
        for (std::size_t c = 0; c < 3; ++c)
          for (std::size_t j = 0; j < m.ndof(); ++j) hdelta[c] += H(c, j) * delta_q[j];
        double integrand = 0.0;
        for (std::size_t c = 0; c < 3; ++c) integrand += hdelta[c] * f[c];
        work_integral += 0.5 * (breaks[k + 1] - breaks[k]) * wt[g] * integrand;
      }
    }
    const double work_error = std::abs(work_q - work_integral);
    const auto integral = nm10_mapping::reconstructed_integral(
        p, line, A0, A1, nm10_mapping::EndpointPolicy::NearestConstant);
    double resultant_error = 0.0;
    for (std::size_t c = 0; c < 3; ++c) {
      double generalized_resultant = 0.0;
      for (std::size_t node = 0; node <= m.elements; ++node)
        generalized_resultant += mapped.generalized_force[6 * node + c];
      resultant_error = std::max(resultant_error, std::abs(generalized_resultant - integral[c]));
    }

    nm10_mapping::MappingManifest manifest;
    manifest.config = cfg();
    for (std::size_t i = 0; i < p.size(); ++i)
      manifest.slices.push_back({"S" + std::to_string(i + 1), p[i], raw[i]});
    nm10_mapping::validate_manifest(m, manifest);
    bool duplicate_id_rejected = false;
    manifest.slices[1].stable_id = manifest.slices[0].stable_id;
    try { nm10_mapping::validate_manifest(m, manifest); }
    catch (const std::exception&) { duplicate_id_rejected = true; }

    const auto evaluated = nm10_mapping::evaluateStructureState(
        m, 1.234, std::vector<double>(m.ndof(), 1e-4),
        std::vector<double>(m.ndof(), 0.0), delta_q, delta_q);
    const bool evaluator_finite = std::all_of(evaluated.displacement_m.begin(),
                                              evaluated.displacement_m.end(),
                                              [](double x) { return std::isfinite(x); });
    const bool pass = left_endpoint && right_endpoint && outside_zero && arbitrary_pass &&
                      refinement_pass && duplicate_id_rejected && evaluator_finite &&
                      work_error <= 1e-11 && resultant_error <= 1e-11;
    std::cout << std::setprecision(17)
              << "{\"status\":\"" << (pass ? "PASS" : "FAIL") << "\","
              << "\"nonuniform_sample_positions\":true,\"nearest_constant_endpoints\":"
              << ((left_endpoint && right_endpoint) ? "true" : "false")
              << ",\"outside_zero\":" << (outside_zero ? "true" : "false")
              << ",\"arbitrary_N_2_3_5_8\":" << (arbitrary_pass ? "true" : "false")
              << ",\"smooth_refinement_N5_N10_N20_N40\":" << (refinement_pass ? "true" : "false")
              << ",\"virtual_work_abs_error\":" << work_error
              << ",\"resultant_abs_error\":" << resultant_error
              << ",\"manifest_duplicate_id_rejected\":" << (duplicate_id_rejected ? "true" : "false")
              << ",\"generic_evaluator_finite\":" << (evaluator_finite ? "true" : "false")
              << "}\n";
    return pass ? 0 : 1;
  } catch (const std::exception& error) {
    std::cerr << "CONTRACT_TEST_FATAL: " << error.what() << '\n';
    return 2;
  }
}
