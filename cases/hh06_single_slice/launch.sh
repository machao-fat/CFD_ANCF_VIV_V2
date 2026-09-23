#!/usr/bin/env bash
# Fail-closed launcher for the explicitly bounded HH06 25-window IQN qualification profile.
set -Eeuo pipefail

SCRIPT_PATH="$(realpath -e -- "${BASH_SOURCE[0]}")"
CASE_DIR="$(cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd -P)"
REPO_ROOT="$(cd -- "$CASE_DIR/../.." && pwd -P)"
readonly EXPECTED_ADAPTER_PATH="/home/machao/OpenFOAM/machao-10/platforms/linux64GccDPInt32Opt/lib/libpreciceAdapterFunctionObject.so"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    exec python3 "$CASE_DIR/bounded_qualification.py" --help
fi

die() {
    echo "PRE_RUN_BLOCKED: $*" >&2
    exit 2
}

[[ -f "$CASE_DIR/contract.json" && -f "$CASE_DIR/precice-config.xml" ]] || die "case contract or preCICE XML missing"
[[ -f "$REPO_ROOT/src/coupling/hh06_structure_0000/structure_0000_participant.py" ]] || die "authoritative Structure participant missing"

OPENFOAM_BASHRC="${OPENFOAM_BASHRC:-/opt/openfoam10/etc/bashrc}"
[[ -r "$OPENFOAM_BASHRC" ]] || die "OpenFOAM environment file missing: $OPENFOAM_BASHRC"
# shellcheck disable=SC1090
set +e
set +u
set +o pipefail
source "$OPENFOAM_BASHRC" >/dev/null
FOAM_SOURCE_STATUS=$?
set -Eeuo pipefail
[[ "$FOAM_SOURCE_STATUS" -eq 0 ]] || die "OpenFOAM environment setup failed: $OPENFOAM_BASHRC"
command -v pimpleFoam >/dev/null 2>&1 || die "pimpleFoam is unavailable after sourcing $OPENFOAM_BASHRC"

export ANCF_PRECICE_ADAPTER_LIBRARY="${ANCF_PRECICE_ADAPTER_LIBRARY:-$EXPECTED_ADAPTER_PATH}"
ADAPTER_GUARD_OUTPUT="$(bash "$CASE_DIR/preflight_adapter_sha.sh")" || die "adapter SHA preflight failed"
printf '%s\n' "$ADAPTER_GUARD_OUTPUT"
export ANCF_ADAPTER_RUNTIME_PATH="$(sed -n 's/^ADAPTER_RUNTIME_PATH=//p' <<<"$ADAPTER_GUARD_OUTPUT" | tail -n 1)"
export ANCF_ADAPTER_RUNTIME_SHA256="$(sed -n 's/^ADAPTER_RUNTIME_SHA256=//p' <<<"$ADAPTER_GUARD_OUTPUT" | tail -n 1)"
[[ -n "$ANCF_ADAPTER_RUNTIME_PATH" && -n "$ANCF_ADAPTER_RUNTIME_SHA256" ]] || die "adapter guard did not report a resolved identity"
# Keep the SHA-verified adapter directory first in the environment inherited by
# pimpleFoam; command substitution does not propagate exports from the guard.
export LD_LIBRARY_PATH="$(dirname -- "$ANCF_ADAPTER_RUNTIME_PATH")${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

exec python3 "$CASE_DIR/bounded_qualification.py" --case "$CASE_DIR" "$@"
