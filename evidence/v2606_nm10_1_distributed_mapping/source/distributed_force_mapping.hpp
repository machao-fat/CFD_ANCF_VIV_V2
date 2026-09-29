#pragma once

#include "ancf_kernel.hpp"

#include <array>
#include <cstddef>
#include <string>
#include <vector>

// Coupling-side force mapping.  The ANCF kernel remains the sole owner of
// shape-function evaluation and consistent H^T f integration; this wrapper
// owns only the explicit Fluid-unit conversion and mapping-mode contract.
namespace nm10_mapping {

enum class MappingMode {
  LegacyPointLumped,
  PiecewiseLinearDistributed,
};

enum class EndpointPolicy {
  NearestConstant,
};

struct IntegratedSliceForceN {
  std::array<double, 3> value{};
};

struct SectionalLineForceNpm {
  std::array<double, 3> value{};
};

struct SliceContract {
  std::string stable_id;
  double s_ref_m = 0.0;
  std::array<double, 3> raw_force_N{};
};

struct MappingConfig {
  MappingMode mode = MappingMode::LegacyPointLumped;
  EndpointPolicy endpoint_policy = EndpointPolicy::NearestConstant;
  double active_s_min_m = 0.0;
  double active_s_max_m = 0.0;
  double unit_span_m = 0.028;
  double legacy_tributary_length_m = 1.98;
};

// Lightweight manifest contract.  It is deliberately data-only so future
// N=5/N=10/N=20 cases change only the manifest, never the mapper source.
struct MappingManifest {
  MappingConfig config;
  std::vector<SliceContract> slices;
};

struct MappingResult {
  std::vector<double> generalized_force;
  std::vector<std::array<double, 3>> line_force_Npm;
  // Populated only for LegacyPointLumped.  Distributed mode intentionally has
  // no tributary multiplier and therefore does not manufacture strip forces.
  std::vector<std::array<double, 3>> legacy_strip_force_N;
};

std::vector<std::array<double, 3>> raw_force_to_line_force(
    const std::vector<std::array<double, 3>>& raw_force_N, double unit_span_m);

std::vector<SectionalLineForceNpm> raw_force_to_sectional_line_force(
    const std::vector<IntegratedSliceForceN>& raw_force_N, double unit_span_m);

void validate_manifest(const cfd_ancf::Model& model, const MappingManifest& manifest);

MappingResult assemble(const cfd_ancf::Model& model, const MappingManifest& manifest);

MappingResult assemble(const cfd_ancf::Model& model,
                       const std::vector<double>& sample_positions_m,
                       const std::vector<std::array<double, 3>>& raw_force_N,
                       const MappingConfig& config);

std::array<double, 3> reconstructed_integral(
    const std::vector<double>& sample_positions_m,
    const std::vector<std::array<double, 3>>& line_force_Npm,
    double active_s_min_m, double active_s_max_m,
    EndpointPolicy endpoint_policy);

std::array<double, 3> reconstructed_force_at(
    double s_m, const std::vector<double>& sample_positions_m,
    const std::vector<std::array<double, 3>>& line_force_Npm,
    double active_s_min_m, double active_s_max_m,
    EndpointPolicy endpoint_policy);

}  // namespace nm10_mapping
