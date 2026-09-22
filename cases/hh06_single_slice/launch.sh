#!/usr/bin/env bash
# 单切片高 Re ANCF 0.2 s 启动器。
# 默认只做预检查并失败即停；只有人工完成结构合同后才允许 ALLOW_LAUNCH=1。
set -Eeuo pipefail
CASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTRACT="$CASE/contract.json"
XML="$CASE/precice-config.xml"
PARTICIPANT="${ANCF_PARTICIPANT:-$CASE/ancf_single_slice_participant.py}"
WORKER="${ANCF_WORKER:-$CASE/cfd_ancf_ancf_kernel_worker}"

die(){ echo "PRE_RUN_BLOCKED: $*" >&2; exit 2; }
command -v jq >/dev/null 2>&1 || die "jq is required for contract preflight"
[[ -f "$CONTRACT" && -f "$XML" ]] || die "contract.json or precice-config.xml missing"
[[ "$(jq -r '.status' "$CONTRACT")" == "READY" ]] || die "contract status is not READY; fill the confirmed high-Re ANCF structural contract first"
for key in '.structure.Mx_kg' '.structure.My_kg' '.structure.Kx_N_m' '.structure.Ky_N_m' '.structure.Cx_N_s_m' '.structure.Cy_N_s_m' '.structure.interface_vertex_count' '.initial_state.Fx0_total_N' '.initial_state.Fy0_total_N' '.initial_state.ax0_m_s2' '.initial_state.ay0_m_s2'; do
    jq -e "$key | numbers" "$CONTRACT" >/dev/null || die "missing numeric contract field: $key"
done
[[ -f "$PARTICIPANT" ]] || die "ANCF participant missing: $PARTICIPANT"
[[ -x "$WORKER" ]] || die "ANCF worker missing or not executable: $WORKER"
[[ -d "$CASE/30" ]] || die "restart field 30/ missing"
[[ "${ALLOW_LAUNCH:-0}" == "1" ]] || die "preflight passed; set ALLOW_LAUNCH=1 only after manual review"

mkdir -p "$CASE/precice-sockets"
rm -f "$CASE/participant.stdout" "$CASE/participant.stderr" "$CASE/fluid.stdout" "$CASE/fluid.stderr"

echo "LAUNCHING single-slice ANCF: global 30 -> 30.2 s, dt=0.0002 s"
python3 "$PARTICIPANT" --case "$CASE" --contract "$CONTRACT" >"$CASE/participant.stdout" 2>"$CASE/participant.stderr" &
STRUCT_PID=$!
trap 'kill "$STRUCT_PID" 2>/dev/null || true' EXIT
source /opt/openfoam10/etc/bashrc
pimpleFoam >"$CASE/fluid.stdout" 2>"$CASE/fluid.stderr"
wait "$STRUCT_PID"
trap - EXIT
echo "RUN_COMPLETED_OR_STOPPED: inspect participant.stdout, participant.stderr, fluid.stdout, fluid.stderr"
