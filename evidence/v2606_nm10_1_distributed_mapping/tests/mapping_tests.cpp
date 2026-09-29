#include "distributed_force_mapping.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <exception>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr double PI = 3.141592653589793238462643383279502884;
constexpr double LENGTH = 13.12;
constexpr double DIAMETER = 0.028;
constexpr std::size_t ELEMENTS = 32;
constexpr double UNIT_SPAN = 0.028;
constexpr double ACTIVE_MIN = 0.0;
constexpr double ACTIVE_MAX = 5.94;

cfd_ancf::Model test_model(const std::vector<double>& positions) {
  cfd_ancf::Model model;
  model.length_m = LENGTH;
  model.diameter_m = DIAMETER;
  model.inner_diameter_m = 0.0;
  model.elements = ELEMENTS;
  model.slices = positions.size();
  model.slice_positions_m = positions;
  model.top_tension_N = 1175.0;
  const double area = PI * DIAMETER * DIAMETER / 4.0;
  model.youngs_modulus_Pa = 7470000.0 / area;
  model.material_density = 1.845 / area;
  model.section_property_mode = cfd_ancf::SectionPropertyMode::ExplicitSectionProperties;
  model.explicit_EA_N = 7470000.0;
  model.explicit_EI_Nm2 = 29.88;
  model.explicit_mass_per_length_kg_m = 1.845;
  model.explicit_displaced_area_m2 = area;
  model.fluid_density = 1000.0;
  model.gravity = 9.81;
  model.dt_s = 4e-4;
  model.beta = 0.25;
  model.gamma = 0.5;
  model.max_newton = 40;
  model.newton_tolerance = 2e-10;
  model.gauss_order = 3;
  model.mass_gauss_order = 5;
  model.damping_alpha = 0.0;
  model.damping_beta = 0.0;
  cfd_ancf::validate_model(model);
  return model;
}

double max_abs(const std::vector<double>& a, const std::vector<double>& b) {
  if (a.size() != b.size()) throw std::runtime_error("vector size mismatch");
  double result = 0.0;
  for (std::size_t i = 0; i < a.size(); ++i)
    result = std::max(result, std::abs(a[i] - b[i]));
  return result;
}

std::vector<double> direct_reference(const cfd_ancf::Model& model,
                                     const std::vector<double>& positions,
                                     const std::vector<std::array<double, 3>>& line,
                                     int order) {
  static constexpr std::array<double, 8> xi8 = {
      -0.9602898564975363, -0.7966664774136267, -0.5255324099163290,
      -0.1834346424956498,  0.1834346424956498,  0.5255324099163290,
       0.7966664774136267,  0.9602898564975363};
  static constexpr std::array<double, 8> w8 = {
      0.1012285362903763, 0.2223810344533745, 0.3137066458778873,
      0.3626837833783620, 0.3626837833783620, 0.3137066458778873,
      0.2223810344533745, 0.1012285362903763};
  static constexpr std::array<double, 5> xi5 = {
      -0.9061798459386640, -0.5384693101056831, 0.0,
       0.5384693101056831,  0.9061798459386640};
  static constexpr std::array<double, 5> w5 = {
      0.2369268850561891, 0.4786286704993665, 0.5688888888888889,
      0.4786286704993665, 0.2369268850561891};
  static constexpr std::array<double, 3> xi3 = {
      -0.7745966692414834, 0.0, 0.7745966692414834};
  static constexpr std::array<double, 3> w3 = {
      0.5555555555555556, 0.8888888888888889, 0.5555555555555556};
  auto f_at = [&](double s) {
    if (s <= positions.front()) return line.front();
    if (s >= positions.back()) return line.back();
    std::size_t upper = 1;
    while (s > positions[upper]) ++upper;
    const double alpha = (s - positions[upper - 1]) /
                         (positions[upper] - positions[upper - 1]);
    std::array<double, 3> f{};
    for (std::size_t c = 0; c < 3; ++c)
      f[c] = (1.0 - alpha) * line[upper - 1][c] + alpha * line[upper][c];
    return f;
  };
  std::vector<double> breaks{ACTIVE_MIN, ACTIVE_MAX};
  const double Le = model.length_m / static_cast<double>(model.elements);
  for (std::size_t e = 1; e < model.elements; ++e) {
    const double s = Le * static_cast<double>(e);
    if (s > ACTIVE_MIN && s < ACTIVE_MAX) breaks.push_back(s);
  }
  for (double s : positions) if (s > ACTIVE_MIN && s < ACTIVE_MAX) breaks.push_back(s);
  std::sort(breaks.begin(), breaks.end());
  breaks.erase(std::unique(breaks.begin(), breaks.end()), breaks.end());
  std::vector<double> q(model.ndof(), 0.0);
  for (std::size_t k = 0; k + 1 < breaks.size(); ++k) {
    const double left = breaks[k], right = breaks[k + 1];
    const std::size_t n = order == 3 ? 3 : order == 5 ? 5 : 8;
    for (std::size_t g = 0; g < n; ++g) {
      const double x = order == 3 ? xi3[g] : order == 5 ? xi5[g] : xi8[g];
      const double weight = order == 3 ? w3[g] : order == 5 ? w5[g] : w8[g];
      const double s = 0.5 * (left + right) + 0.5 * (right - left) * x;
      cfd_ancf::Model point = model;
      point.slices = 1;
      point.slice_positions_m = {s};
      const cfd_ancf::Matrix H = cfd_ancf::mapping_H3(point);
      const auto f = f_at(s);
      const double factor = 0.5 * (right - left) * weight;
      for (std::size_t j = 0; j < model.ndof(); ++j)
        for (std::size_t c = 0; c < 3; ++c) q[j] += factor * H(c, j) * f[c];
    }
  }
  return q;
}

nm10_mapping::MappingConfig distributed_config() {
  nm10_mapping::MappingConfig config;
  config.mode = nm10_mapping::MappingMode::PiecewiseLinearDistributed;
  config.endpoint_policy = nm10_mapping::EndpointPolicy::NearestConstant;
  config.active_s_min_m = ACTIVE_MIN;
  config.active_s_max_m = ACTIVE_MAX;
  config.unit_span_m = UNIT_SPAN;
  return config;
}

}  // namespace

int main() {
  try {
    const std::vector<double> p3{0.99, 2.97, 4.95};
    const std::vector<std::array<double, 3>> raw3{
        {{0.05, 0.01, 0.0}}, {{0.06, -0.02, 0.0}}, {{0.04, 0.03, 0.0}}};
    const auto model3 = test_model(p3);
    const auto config = distributed_config();
    const auto m3 = nm10_mapping::assemble(model3, p3, raw3, config);
    const auto line3 = nm10_mapping::raw_force_to_line_force(raw3, UNIT_SPAN);
    const auto q3_reference = direct_reference(model3, p3, line3, 8);
    const double q3_error = max_abs(m3.generalized_force, q3_reference);
    cfd_ancf::SpanwiseLoadInput core_input;
    core_input.mode = cfd_ancf::SpanwiseLoadReconstruction::PiecewiseLinearDistributed;
    core_input.endpoint_policy = cfd_ancf::SpanwiseEndpointPolicy::NearestConstant;
    core_input.active_region = {ACTIVE_MIN, ACTIVE_MAX};
    for (std::size_t i = 0; i < p3.size(); ++i)
      core_input.samples.push_back({p3[i], line3[i]});
    const double helper_vs_frozen_core = max_abs(
        m3.generalized_force, cfd_ancf::external_force(model3, core_input));
    const double q3_vs_q5 = max_abs(q3_reference, direct_reference(model3, p3, line3, 5));
    const double q3_vs_q8 = max_abs(q3_reference, direct_reference(model3, p3, line3, 8));
    const auto integral3 = nm10_mapping::reconstructed_integral(
        p3, line3, ACTIVE_MIN, ACTIVE_MAX, nm10_mapping::EndpointPolicy::NearestConstant);
    std::array<double, 3> expected3{};
    for (std::size_t i = 0; i < 3; ++i)
      for (std::size_t c = 0; c < 3; ++c) expected3[c] += 1.98 * line3[i][c];
    double conservation_error = 0.0;
    for (std::size_t c = 0; c < 3; ++c)
      conservation_error = std::max(conservation_error, std::abs(integral3[c] - expected3[c]));

    // Exact analytical linear field samples for Test B.
    const std::vector<std::array<double, 3>> linear3{
        {{UNIT_SPAN * (0.7 + 0.2 * p3[0]), UNIT_SPAN * (-0.4 + 0.03 * p3[0]), 0.0}},
        {{UNIT_SPAN * (0.7 + 0.2 * p3[1]), UNIT_SPAN * (-0.4 + 0.03 * p3[1]), 0.0}},
        {{UNIT_SPAN * (0.7 + 0.2 * p3[2]), UNIT_SPAN * (-0.4 + 0.03 * p3[2]), 0.0}}};
    const auto linear_result = nm10_mapping::assemble(model3, p3, linear3, config);
    const auto linear_ref = direct_reference(model3, p3,
                                             nm10_mapping::raw_force_to_line_force(linear3, UNIT_SPAN), 8);
    const double linear_error = max_abs(linear_result.generalized_force, linear_ref);

    // N=2/N=3/N=5 deterministic V2 cross-checks.
    const std::vector<std::vector<double>> cases{
        {1.98, 3.96}, {0.99, 2.97, 4.95},
        {0.594, 1.782, 2.970, 4.158, 5.346}};
    double cross_max = 0.0;
    std::vector<double> cross_errors;
    for (const auto& positions : cases) {
      std::vector<std::array<double, 3>> raw(positions.size());
      for (std::size_t i = 0; i < positions.size(); ++i)
        raw[i] = {0.012 + 0.004 * static_cast<double>(i),
                  -0.008 + 0.003 * static_cast<double>(i),
                  0.001 * static_cast<double>(i)};
      const auto model = test_model(positions);
      const auto mapped = nm10_mapping::assemble(model, positions, raw, config);
      const auto line = nm10_mapping::raw_force_to_line_force(raw, UNIT_SPAN);
      const double error = max_abs(mapped.generalized_force,
                                   direct_reference(model, positions, line, 8));
      cross_errors.push_back(error);
      cross_max = std::max(cross_max, error);
    }

    // Invalid input closure checks.
    bool unsorted_rejected = false, duplicate_rejected = false,
         nonfinite_rejected = false, outside_rejected = false;
    try { nm10_mapping::assemble(model3, {2.97, 0.99, 4.95}, raw3, config); }
    catch (const std::exception&) { unsorted_rejected = true; }
    try { nm10_mapping::assemble(model3, {0.99, 2.97, 2.97}, raw3, config); }
    catch (const std::exception&) { duplicate_rejected = true; }
    auto nonfinite = raw3; nonfinite[1][0] = std::numeric_limits<double>::quiet_NaN();
    try { nm10_mapping::assemble(model3, p3, nonfinite, config); }
    catch (const std::exception&) { nonfinite_rejected = true; }
    try { nm10_mapping::assemble(model3, {0.99, 6.10, 6.20}, raw3, config); }
    catch (const std::exception&) { outside_rejected = true; }

    nm10_mapping::MappingConfig legacy_config = config;
    legacy_config.mode = nm10_mapping::MappingMode::LegacyPointLumped;
    legacy_config.legacy_tributary_length_m = 1.98;
    const auto legacy = nm10_mapping::assemble(model3, p3, raw3, legacy_config);
    std::vector<double> direct_legacy(legacy.generalized_force.size(), 0.0);
    const auto H = cfd_ancf::mapping_H3(model3);
    for (std::size_t j = 0; j < model3.ndof(); ++j)
      for (std::size_t i = 0; i < p3.size(); ++i)
        for (std::size_t c = 0; c < 3; ++c)
          direct_legacy[j] += H(3 * i + c, j) * raw3[i][c] / UNIT_SPAN * 1.98;
    const double legacy_error = max_abs(legacy.generalized_force, direct_legacy);
    const bool pass = q3_error <= 1e-12 && linear_error <= 1e-12 &&
                      cross_max <= 1e-12 && conservation_error <= 1e-12 &&
                      helper_vs_frozen_core <= 1e-12 && legacy_error <= 1e-12 && unsorted_rejected && duplicate_rejected &&
                      nonfinite_rejected && outside_rejected;
    std::cout << std::setprecision(17)
              << "{\"status\":\"" << (pass ? "PASS" : "FAIL") << "\","
              << "\"constant_force_q_error\":" << q3_error << ','
              << "\"helper_vs_frozen_core_max_abs_error\":" << helper_vs_frozen_core << ','
              << "\"gauss3_vs_gauss5_max_abs_difference\":" << q3_vs_q5 << ','
              << "\"gauss3_vs_gauss8_max_abs_difference\":" << q3_vs_q8 << ','
              << "\"linear_force_q_error\":" << linear_error << ','
              << "\"conservation_max_abs_error\":" << conservation_error << ','
              << "\"v2_crosscheck_errors_n2_n3_n5\":["
              << cross_errors[0] << ',' << cross_errors[1] << ',' << cross_errors[2] << "],"
              << "\"v2_crosscheck_max_abs_error\":" << cross_max << ','
              << "\"legacy_regression_max_abs_error\":" << legacy_error << ','
              << "\"invalid_inputs\":{\"unsorted\":" << (unsorted_rejected ? "true" : "false")
              << ",\"duplicate\":" << (duplicate_rejected ? "true" : "false")
              << ",\"nonfinite\":" << (nonfinite_rejected ? "true" : "false")
              << ",\"outside\":" << (outside_rejected ? "true" : "false") << "},"
              << "\"mapping_mode\":\"PiecewiseLinearDistributed\","
              << "\"endpoint_policy\":\"NearestConstant\"}\n";
    return pass ? 0 : 1;
  } catch (const std::exception& error) {
    std::cerr << "MAPPING_TEST_FATAL: " << error.what() << '\n';
    return 2;
  }
}
