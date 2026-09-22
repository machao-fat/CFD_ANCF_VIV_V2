cmake_minimum_required(VERSION 3.20)
project(CFD_ANCF_VIV_V2 LANGUAGES CXX)

include(CTest)
enable_testing()

# The authoritative worker and offline self-tests live here. This does not run
# OpenFOAM, preCICE, or any physical FSI simulation.
add_subdirectory(src/ancf)
