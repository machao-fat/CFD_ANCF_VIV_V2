#!/usr/bin/env bash
set -Eeuo pipefail

readonly EXPECTED_ADAPTER_SHA256="26ad8529822f96ca8ddfb3370f85257b0d19b56958538d6073cf8af897aac572"
readonly ADAPTER_NAME="libpreciceAdapterFunctionObject.so"

die() {
    echo "PRE_RUN_BLOCKED: $*" >&2
    exit 2
}

declare -a candidates=()
declare -A seen=()
add_candidate() {
    local raw="$1" resolved
    [[ -n "$raw" && -f "$raw" ]] || return 0
    resolved="$(realpath -e -- "$raw")" || die "cannot resolve adapter library path: $raw"
    if [[ -z "${seen[$resolved]+x}" ]]; then
        seen[$resolved]=1
        candidates+=("$resolved")
    fi
}

if [[ -n "${ANCF_PRECICE_ADAPTER_LIBRARY:-}" ]]; then
    add_candidate "$ANCF_PRECICE_ADAPTER_LIBRARY"
    [[ ${#candidates[@]} -eq 1 ]] || die "explicit adapter library does not exist: $ANCF_PRECICE_ADAPTER_LIBRARY"
    export LD_LIBRARY_PATH="$(dirname "${candidates[0]}")${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

[[ -n "${FOAM_USER_LIBBIN:-}" ]] && add_candidate "$FOAM_USER_LIBBIN/$ADAPTER_NAME"
IFS=: read -r -a ld_dirs <<< "${LD_LIBRARY_PATH:-}"
for directory in "${ld_dirs[@]}"; do
    [[ -n "$directory" ]] && add_candidate "$directory/$ADAPTER_NAME"
done
[[ -n "${FOAM_LIBBIN:-}" ]] && add_candidate "$FOAM_LIBBIN/$ADAPTER_NAME"
if command -v ldconfig >/dev/null 2>&1; then
    while IFS= read -r path; do
        add_candidate "$path"
    done < <(ldconfig -p 2>/dev/null | awk -v name="$ADAPTER_NAME" '$1 == name {print $NF}')
fi

[[ ${#candidates[@]} -gt 0 ]] || die "cannot resolve $ADAPTER_NAME from the active OpenFOAM library paths"

resolved_adapter="${candidates[0]}"
for candidate in "${candidates[@]}"; do
    actual_sha="$(sha256sum -- "$candidate" | awk '{print $1}')"
    [[ "$actual_sha" == "$EXPECTED_ADAPTER_SHA256" ]] || die "adapter SHA mismatch: path=$candidate sha256=$actual_sha expected=$EXPECTED_ADAPTER_SHA256"
done

echo "ADAPTER_RUNTIME_BINARY_PINNED=YES"
echo "ADAPTER_SOURCE_PROVENANCE_RESOLVED=NO"
echo "ADAPTER_RUNTIME_PATH=$resolved_adapter"
echo "ADAPTER_RUNTIME_SHA256=$EXPECTED_ADAPTER_SHA256"
