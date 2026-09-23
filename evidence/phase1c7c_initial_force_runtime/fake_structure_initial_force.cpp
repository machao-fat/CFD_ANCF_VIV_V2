#include <precice/Participant.hpp>

#include <array>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>

int main(int argc, char **argv)
{
  if (argc != 2) {
    std::cerr << "usage: fake_structure_initial_force <precice-config.xml>\n";
    return 2;
  }

  constexpr double release_time_s = 30.0;
  constexpr double expected_dt_s = 0.0002;
  constexpr double expected_fx_N = 0.0655270406544;
  constexpr double expected_fy_N = 0.05872987413554;
  constexpr double absolute_tolerance_N = 1.0e-8;

  precice::Participant participant("Structure_0000", argv[1], 0, 1);
  const std::array<double, 2> coordinates{0.0, 0.0};
  const auto vertex = participant.setMeshVertex(
      "Structure-Mesh", {coordinates.data(), coordinates.size()});
  const std::array<precice::VertexID, 1> vertex_ids{vertex};
  const std::array<double, 2> initial_displacement{0.0, 0.0};

  const bool requires_initial_data = participant.requiresInitialData();
  std::cout << std::setprecision(17)
            << "FAKE_STRUCTURE requiresInitialData="
            << (requires_initial_data ? "true" : "false") << '\n';
  std::cout.flush();
  if (requires_initial_data) {
    participant.writeData(
        "Structure-Mesh", "Displacement",
        {vertex_ids.data(), vertex_ids.size()},
        {initial_displacement.data(), initial_displacement.size()});
    std::cout << "FAKE_STRUCTURE initial Displacement written before initialize\n";
    std::cout.flush();
  }

  participant.initialize();
  const double max_dt_s = participant.getMaxTimeStepSize();
  std::array<double, 2> received_force_N{NAN, NAN};
  participant.readData(
      "Structure-Mesh", "Force", {vertex_ids.data(), vertex_ids.size()},
      0.0, {received_force_N.data(), received_force_N.size()});

  const bool finite_force =
      std::isfinite(received_force_N[0]) && std::isfinite(received_force_N[1]);
  const bool time_step_matches = std::abs(max_dt_s - expected_dt_s) <= 1.0e-14;
  const bool force_matches =
      finite_force &&
      std::abs(received_force_N[0] - expected_fx_N) <= absolute_tolerance_N &&
      std::abs(received_force_N[1] - expected_fy_N) <= absolute_tolerance_N;

  std::cout << std::setprecision(17)
            << "INITIAL_FORCE_RECEIVED"
            << " physical_time_s=" << release_time_s
            << " relativeReadTime_s=0"
            << " max_dt_s=" << max_dt_s
            << " Fx_N=" << received_force_N[0]
            << " Fy_N=" << received_force_N[1]
            << " Fz_N=not_transmitted_mesh_dimensions_2"
            << " abs_tolerance_N=" << absolute_tolerance_N
            << " time_step_matches=" << (time_step_matches ? "true" : "false")
            << " force_matches=" << (force_matches ? "true" : "false")
            << '\n';
  std::cout.flush();

  const int result = (requires_initial_data && time_step_matches && force_matches) ? 0 : 3;
  std::_Exit(result);
}
