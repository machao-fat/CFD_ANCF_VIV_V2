# HH06 P1 artifact scan and contract audit

状态：`READY_FOR_DRY_RUN`

本文件仅记录离线资料扫描与合同更新；没有执行 `launch.sh`，没有启动
OpenFOAM、preCICE 或 ANCF，也没有创建新的时间目录。

## 搜索路径

- 用户指定目录：`D:\CFD相关的报告` —— 当前不存在，因此没有从该路径猜测参数。
- 实际找到的 P1 工件：
  `D:\CFD\CFD_ANCF_VIV_reentry_runtime\HH06_P1_WET_MODAL_STRUCTURAL_GATE`

## 已确认并写入合同的 P1 工件

来源文件：

- `source_parameter_contract.json`
- `HH06_P1_RESULT.json`
- `ancf_static.raw`
- `ancf_static_equilibrium.json`
- `HH06_P1_SHA256_MANIFEST.txt`

选用 `ancf_static.raw` 中的 `CASE REF_NE32`：

- `L=13.12 m`，`D=0.028 m`，`Ne=32`，33 个 ANCF 状态节点；
- `EI=29.88 N m^2`；
- `EA=7.47e6 N`，P1 标记为 derived core-consistent reference；
- 结构线质量 `1.845 kg/m`；added mass `[0.616, 0.616, 0] kg/m`；
- P1 湿横向线质量 `2.461 kg/m`；
- Rayleigh `alpha=0`、`beta=0`；水动力线性阻尼 `[0,0,0]`；
- `q0` 来源为 `CASE REF_NE32` 的 `Q` 记录，静力求解器为 PotentialBacktrackingNewton。

## 未采用或仍需人工确认

- HH06 Case 1 benchmark top-tension 输入为 `1175 N`。P1 工件中的 `1188.28 N`
  是静力平衡后的 equilibrium reaction tension，不是 HH06 benchmark 输入，不能写回
  benchmark contract。两者已作为独立字段保存，活动 runtime 输入保持 `null`，直到
  participant 合同明确选择 benchmark 输入。
- 当前目录仍没有兼容 `Fluid_0000/Structure_0000`、200 个 CFD 面中心和单点
  `Structure-Mesh` 的 HH06 participant 入口。
- 不存在可合法伪造的 30 s ANCF checkpoint；30 s 仅是 Fluid restart 场。
- 初始加速度不是 q0 或 dry-run 合同字段，不能以 `a0=0` 代替静力平衡状态。

## 接口合同

唯一允许的力路径为：

`CFD wall integration -> strip resultant force -> preCICE Force -> ANCF generalized load`。

禁止 CFD face index 与 ANCF state vertex 一一对应，也禁止旧 604-vertex participant。

## 现有代码入口审计

本地仓库 `D:/CFD/CFD_ANCF_VIV_source` 已完成只读检索；GitHub remote
为 `https://github.com/machao-fat/CFD_ANCF_VIV.git`。未发现同时满足
`Structure_0000`、HH06 `Structure-Mesh` 单耦合点、200 个 CFD 面中心、33 个
ANCF 状态节点/198 DOF 的现成 wrapper。

仓库中存在 `Structure_0000` 名称的桥接/SDOF 文件，但均不满足 HH06 ANCF
合同：`run_bridge.py`/`run_bridge_v2.py` 是 40 顶点规定运动且明确
`contains_ancf=false`；`run_fixed_zero_bridge.py` 是固定/零运动 fixture；
Shiels continuation participant 是旧 Re=100 SDOF。

已定位但不兼容的入口：

1. `tools/precice_ancf_adapter_v1/ancf_structure_participant_v1.py`：participant 名为 `Structure`，固定 604 顶点，属于 fixture。
2. `tools/precice_ancf_adapter_v1/ancf_cpp_worker_single_slice_participant_v1.py`：participant 名为 `Structure`，力输入固定 604 顶点，属于通用 worker qualification。
3. `tools/precice_ancf_adapter_v1/ancf_generic_participant_v1.py`：只有注入式 generic orchestration，没有 live preCICE participant entrypoint。
4. `tools/three_slice_force_contract_smoke_v1/structure_participant.py`：三切片 smoke 入口，拓扑和接口均不同。

当前目录的 `ancf_worker_main.cpp`/`cfd_ancf_ancf_kernel_worker` 仅是 ANCF 数值核的持久
IPC worker；`initialize/advance/checkpoint` 属于 worker 协议，并不提供
`precice.Participant("Structure_0000", ...)`。

因此 `Structure_0000` 入口状态为 `MISSING_COMPATIBLE_ENTRYPOINT`。不能把 SDOF
脚本或旧 604-vertex 代码冒充 HH06 ANCF 结构端；本轮没有修改源码。

## 当前结论

XML 和四个合同 JSON 可解析；唯一数值目录仍为 `30/`。可以在兼容 participant
入口补齐后进入只读 preCICE handshake dry-run；当前仍不得执行 handshake、求解或
时间积分。
