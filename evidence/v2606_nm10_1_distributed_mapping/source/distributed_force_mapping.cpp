#include "distributed_force_mapping.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <unordered_set>
#include <stdexcept>

namespace nm10_mapping {
namespace {

void validate_common(const cfd_ancf::Model& model,
                     const std::vector<double>& positions,
                     const std::vector<std::array<double, 3>>& raw,
                     const MappingConfig& config) {
  if (positions.size() != raw.size() || positions.empty())
    throw std::invalid_argument("force mapping sample dimensions are invalid");
  if (!std::isfinite(config.unit_span_m) || config.unit_span_m <= 0.0)
    throw std::invalid_argument("force mapping unit span is invalid");
  if (!std::isfinite(config.active_s_min_m) || !std::isfinite(config.active_s_max_m) ||
      config.active_s_min_m < 0.0 || config.active_s_max_m > model.length_m ||
      config.active_s_min_m >= config.active_s_max_m)
    throw std::invalid_argument("force mapping active region is invalid");
  for (std::size_t i = 0; i < positions.size(); ++i) {
    if (!std::isfinite(positions[i]) || positions[i] < config.active_s_min_m ||
        positions[i] > config.active_s_max_m ||
        (i > 0 && positions[i] <= positions[i - 1]))
      throw std::invalid_argument("force mapping sample positions are not strictly ordered");
    for (double value : raw[i])
      if (!std::isfinite(value)) throw std::invalid_argument("raw Fluid force is nonfinite");
  }
  if (config.endpoint_policy != EndpointPolicy::NearestConstant)
    throw std::invalid_argument("unknown force mapping endpoint policy");
}

}  // namespace

std::vector<std::array<double, 3>> raw_force_to_line_force(
    const std::vector<std::array<double, 3>>& raw_force_N, double unit_span_m) {
  if (!std::isfinite(unit_span_m) || unit_span_m <= 0.0)
    throw std::invalid_argument("unit span must be finite and positive");
  std::vector<std::array<double, 3>> line(raw_force_N.size());
  for (std::size_t i = 0; i < raw_force_N.size(); ++i) {
    for (std::size_t component = 0; component < 3; ++component) {
      if (!std::isfinite(raw_force_N[i][component]))
        throw std::invalid_argument("raw Fluid force is nonfinite");
      line[i][component] = raw_force_N[i][component] / unit_span_m;
    }
  }
  return line;
}

std::vector<SectionalLineForceNpm> raw_force_to_sectional_line_force(
    const std::vector<IntegratedSliceForceN>& raw_force_N, double unit_span_m) {
  std::vector<SectionalLineForceNpm> result(raw_force_N.size());
  if (!std::isfinite(unit_span_m) || unit_span_m <= 0.0)
    throw std::invalid_argument("unit span must be finite and positive");
  for (std::size_t i = 0; i < raw_force_N.size(); ++i)
    for (std::size_t c = 0; c < 3; ++c) {
      if (!std::isfinite(raw_force_N[i].value[c]))
        throw std::invalid_argument("raw integrated force is nonfinite");
      result[i].value[c] = raw_force_N[i].value[c] / unit_span_m;
    }
  return result;
}

void validate_manifest(const cfd_ancf::Model& model, const MappingManifest& manifest) {
  if (manifest.slices.empty())
    throw std::invalid_argument("mapping manifest has no slices");
  if (manifest.config.mode == MappingMode::PiecewiseLinearDistributed &&
      manifest.slices.size() < 2)
    throw std::invalid_argument("distributed manifest requires N >= 2");
  if (manifest.config.mode == MappingMode::LegacyPointLumped &&
      manifest.config.legacy_tributary_length_m <= 0.0)
    throw std::invalid_argument("legacy slice length must be positive");
  std::unordered_set<std::string> ids;
  std::vector<double> positions;
  std::vector<std::array<double, 3>> raw;
  positions.reserve(manifest.slices.size());
  raw.reserve(manifest.slices.size());
  for (const auto& slice : manifest.slices) {
    if (slice.stable_id.empty() || !ids.insert(slice.stable_id).second)
      throw std::invalid_argument("mapping manifest stable IDs are not unique");
    positions.push_back(slice.s_ref_m);
    raw.push_back(slice.raw_force_N);
  }
  validate_common(model, positions, raw, manifest.config);
}

MappingResult assemble(const cfd_ancf::Model& model, const MappingManifest& manifest) {
  validate_manifest(model, manifest);
  std::vector<double> positions;
  std::vector<std::array<double, 3>> raw;
  positions.reserve(manifest.slices.size());
  raw.reserve(manifest.slices.size());
  for (const auto& slice : manifest.slices) {
    positions.push_back(slice.s_ref_m);
    raw.push_back(slice.raw_force_N);
  }
  return assemble(model, positions, raw, manifest.config);
}

std::array<double, 3> reconstructed_integral(
    const std::vector<double>& positions,
    const std::vector<std::array<double, 3>>& line,
    double active_s_min_m, double active_s_max_m, EndpointPolicy endpoint_policy) {
  if (positions.size() != line.size() || positions.size() < 2 ||
      !std::isfinite(active_s_min_m) || !std::isfinite(active_s_max_m) ||
      active_s_min_m >= active_s_max_m || endpoint_policy != EndpointPolicy::NearestConstant)
    throw std::invalid_argument("distributed force integral contract is invalid");
  for (std::size_t i = 0; i < positions.size(); ++i) {
    if (!std::isfinite(positions[i]) || positions[i] < active_s_min_m ||
        positions[i] > active_s_max_m || (i > 0 && positions[i] <= positions[i - 1]))
      throw std::invalid_argument("distributed force integral samples are invalid");
    for (double value : line[i])
      if (!std::isfinite(value)) throw std::invalid_argument("distributed force is nonfinite");
  }
  std::array<double, 3> result{};
  const auto add = [&result](const std::array<double, 3>& value, double weight) {
    for (std::size_t component = 0; component < 3; ++component)
      result[component] += value[component] * weight;
  };
  add(line.front(), positions.front() - active_s_min_m);
  for (std::size_t i = 0; i + 1 < positions.size(); ++i) {
    const double width = positions[i + 1] - positions[i];
    for (std::size_t component = 0; component < 3; ++component)
      result[component] += 0.5 * width * (line[i][component] + line[i + 1][component]);
  }
  add(line.back(), active_s_max_m - positions.back());
  return result;
}

std::array<double, 3> reconstructed_force_at(
    double s_m, const std::vector<double>& positions,
    const std::vector<std::array<double, 3>>& line,
    double active_s_min_m, double active_s_max_m, EndpointPolicy endpoint_policy) {
  if (positions.size() != line.size() || positions.size() < 2 ||
      endpoint_policy != EndpointPolicy::NearestConstant ||
      !std::isfinite(s_m) || !std::isfinite(active_s_min_m) ||
      !std::isfinite(active_s_max_m) || active_s_min_m >= active_s_max_m)
    throw std::invalid_argument("distributed force evaluation contract is invalid");
  for (std::size_t i = 0; i < positions.size(); ++i) {
    if (!std::isfinite(positions[i]) || positions[i] < active_s_min_m ||
        positions[i] > active_s_max_m || (i > 0 && positions[i] <= positions[i - 1]))
      throw std::invalid_argument("distributed force evaluation samples are invalid");
  }
  std::array<double, 3> zero{};
  if (s_m < active_s_min_m || s_m > active_s_max_m) return zero;
  if (s_m <= positions.front()) return line.front();
  if (s_m >= positions.back()) return line.back();
  std::size_t upper = 1;
  while (upper < positions.size() && s_m > positions[upper]) ++upper;
  const double alpha = (s_m - positions[upper - 1]) /
                       (positions[upper] - positions[upper - 1]);
  std::array<double, 3> result{};
  for (std::size_t c = 0; c < 3; ++c)
    result[c] = line[upper - 1][c] + alpha * (line[upper][c] - line[upper - 1][c]);
  return result;
}

MappingResult assemble(const cfd_ancf::Model& model,
                       const std::vector<double>& sample_positions_m,
                       const std::vector<std::array<double, 3>>& raw_force_N,
                       const MappingConfig& config) {
  validate_common(model, sample_positions_m, raw_force_N, config);
  MappingResult result;
  result.line_force_Npm = raw_force_to_line_force(raw_force_N, config.unit_span_m);
  switch (config.mode) {
    case MappingMode::LegacyPointLumped: {
      if (sample_positions_m.size() != model.slices ||
          model.slice_positions_m.size() != model.slices)
        throw std::invalid_argument("legacy point mapping requires model slice positions");
      std::vector<double> strip_force(3 * model.slices, 0.0);
      result.legacy_strip_force_N.resize(raw_force_N.size());
      for (std::size_t i = 0; i < raw_force_N.size(); ++i) {
        if (model.slice_positions_m[i] != sample_positions_m[i])
          throw std::invalid_argument("legacy sample/model slice positions differ");
        for (std::size_t component = 0; component < 3; ++component) {
          result.legacy_strip_force_N[i][component] =
              result.line_force_Npm[i][component] * config.legacy_tributary_length_m;
          strip_force[3 * i + component] = result.legacy_strip_force_N[i][component];
        }
      }
      result.generalized_force = cfd_ancf::external_force(model, strip_force);
      break;
    }
    case MappingMode::PiecewiseLinearDistributed: {
      if (sample_positions_m.size() < 2)
        throw std::invalid_argument("distributed mapping requires at least two samples");
      cfd_ancf::SpanwiseLoadInput input;
      input.mode = cfd_ancf::SpanwiseLoadReconstruction::PiecewiseLinearDistributed;
      input.endpoint_policy = cfd_ancf::SpanwiseEndpointPolicy::NearestConstant;
      input.active_region = {config.active_s_min_m, config.active_s_max_m};
      input.samples.resize(sample_positions_m.size());
      for (std::size_t i = 0; i < sample_positions_m.size(); ++i) {
        input.samples[i].s_m = sample_positions_m[i];
        input.samples[i].line_force_Npm = result.line_force_Npm[i];
      }
      // Coupling-side consistent integration.  H(s) is obtained exclusively
      // through the frozen public mapping API; no shape polynomial is copied.
      static constexpr std::array<double, 3> xi = {
          -0.7745966692414834, 0.0, 0.7745966692414834};
      static constexpr std::array<double, 3> weights = {
          0.5555555555555556, 0.8888888888888889, 0.5555555555555556};
      result.generalized_force.assign(model.ndof(), 0.0);
      std::vector<double> breakpoints{config.active_s_min_m, config.active_s_max_m};
      const double element_length = model.length_m / static_cast<double>(model.elements);
      for (std::size_t e = 1; e < model.elements; ++e) {
        const double s = element_length * static_cast<double>(e);
        if (s > config.active_s_min_m && s < config.active_s_max_m)
          breakpoints.push_back(s);
      }
      for (double s : sample_positions_m)
        if (s > config.active_s_min_m && s < config.active_s_max_m)
          breakpoints.push_back(s);
      std::sort(breakpoints.begin(), breakpoints.end());
      breakpoints.erase(std::unique(breakpoints.begin(), breakpoints.end()), breakpoints.end());
      for (std::size_t interval = 0; interval + 1 < breakpoints.size(); ++interval) {
        const double left = breakpoints[interval], right = breakpoints[interval + 1];
        for (std::size_t g = 0; g < xi.size(); ++g) {
          const double s = 0.5 * (left + right) + 0.5 * (right - left) * xi[g];
          cfd_ancf::Model point_model = model;
          point_model.slices = 1;
          point_model.slice_positions_m = {s};
          const cfd_ancf::Matrix H = cfd_ancf::mapping_H3(point_model);
          const auto force = reconstructed_force_at(
              s, sample_positions_m, result.line_force_Npm,
              config.active_s_min_m, config.active_s_max_m, config.endpoint_policy);
          const double factor = 0.5 * (right - left) * weights[g];
          for (std::size_t dof = 0; dof < model.ndof(); ++dof)
            for (std::size_t component = 0; component < 3; ++component)
              result.generalized_force[dof] += factor * H(component, dof) * force[component];
        }
      }
      if (!std::all_of(result.generalized_force.begin(), result.generalized_force.end(),
                       [](double value) { return std::isfinite(value); }))
        throw std::runtime_error("distributed generalized force contains NaN/Inf");
      break;
    }
    default:
      throw std::invalid_argument("unknown force mapping mode");
  }
  return result;
}

}  // namespace nm10_mapping
