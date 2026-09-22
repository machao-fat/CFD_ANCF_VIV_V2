# Authoritative ANCF source

This directory is extracted from `feature/ancf-spanwise-hydro-matrix-v1` at
`355640e11925b9feddd1a52bb3d93596e5ee8251`. It is the single ANCF/SHM1 capability
source tree for V2.

The C++ kernel does not call preCICE directly. preCICE belongs in the Python/backend
layer; the worker owns ANCF numerical state and the SHM1/DMP1 wire protocol.

The CMake file contains historical self-tests and diagnostics. Build results must be
recorded with source hashes; do not copy or trust a historical binary by filename.
