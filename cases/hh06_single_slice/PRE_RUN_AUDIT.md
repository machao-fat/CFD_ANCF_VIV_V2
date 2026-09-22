# HH06 Case 1 高 Re 单切片 ANCF-FSI 合同预运行审计

状态：`READY_FOR_DRY_RUN`

本轮为合同配置，不是求解运行。没有执行 `launch.sh`，没有启动
OpenFOAM、preCICE 或 ANCF，也没有创建新的数值时间目录。

## 已核对

- 起始场：`30/`，`uniform/time` 为 30 s，`deltaT=0.0002 s`。
- 网格：46,826 hexahedral cells，圆柱边界 200 faces，`checkMesh` 通过。
- 流体合同：D=0.028 m，U=0.31 m/s，rho=1000 kg/m³，nu=1.1388087116e-6 m²/s，Re≈7622。
- 动网格：`displacementLaplacian`，`pointDisplacement` 绑定，圆柱 `movingWallVelocity`。
- 目标耦合：parallel-implicit，窗口/步长 0.0002 s，最多 1000 个接受窗口（0.2 s）。
- ANCF C++ 源码快照已更新为 `feature/ancf-spanwise-hydro-matrix-v1@355640e11925b9feddd1a52bb3d93596e5ee8251`；哈希见 `SOURCE_MANIFEST.md`。
- 已扫描用户指定的 `D:\CFD相关的报告`，该目录当前不存在；未从该路径猜测或重构任何参数。
- 找到并采用的 P1 工件目录：`D:\CFD\CFD_ANCF_VIV_reentry_runtime\HH06_P1_WET_MODAL_STRUCTURAL_GATE`。关键文件为 `source_parameter_contract.json`、`HH06_P1_RESULT.json`、`ancf_static.raw`、`ancf_static_equilibrium.json` 和 `HH06_P1_SHA256_MANIFEST.txt`。
- P1 结构合同：L=13.12 m，D=0.028 m，Ne=32，33 个 ANCF 状态节点，EI=29.88 N·m²，EA=7.47e6 N（P1 标记为 derived core-consistent reference），结构线质量 1.845 kg/m，added mass=[0.616,0.616,0] kg/m，P1 零阻尼。
- 张力语义已分开：HH06 Case 1 benchmark top-tension 输入为 1175 N；P1 静力平衡得到的 equilibrium reaction tension 为 1188.28 N。后者不是 HH06 输入，不能写回 benchmark contract；活动 runtime 输入保持未选择，故状态保持 `READY_FOR_DRY_RUN`。
- P1 `ancf_static.raw` 的 `CASE REF_NE32`/`Q` 记录作为 q0 静态平衡状态来源；不复制或伪造 30 s ANCF checkpoint。
- 单切片空间位置：s=2.97 m，`DeltaL=1.98 m`；力转换冻结为 `F_slice=(F_raw/Lz_CFD)*DeltaL`，其中 CFD 挤出厚度 Lz=0.028 m，只执行一次。
- 接口方向冻结为：`Fluid_0000` provides `Force`；`Structure_0000` receives `Force`、provides `Displacement`；正确管线为“CFD wall integration → strip resultant force → preCICE Force → ANCF generalized load”，不使用 CFD 面到 ANCF 状态顶点的一一对应，也不使用旧 604-vertex participant。
- 已生成/更新 `structure_contract.json`、`mapping_contract.json`、`interface_contract.json`；四个合同均应通过 JSON 语法检查。

## 尚存阻塞与边界

合同层已允许进入 dry-run 阶段，但尚未允许时间积分。P1 截面质量、EA、EI、零阻尼和 `REF_NE32` 静力平衡 q0 已在上述可签名工件中找到并写入合同；没有用旧 Re=100、50 m 或 604-vertex 数值替代。1175 N benchmark 输入与 1188.28 N equilibrium reaction 已明确区分。

此外，已新增 HH06 专用 `Structure_0000` wrapper：
`D:/研二文件/开题准备/CFD_ANCF_VIV/tools/hh06_single_slice_structure_0000_participant_v1/structure_0000_participant.py`。
它只注册一个结构耦合点，复用 `PreciceStructureFleetBackend`、
`GenericStructuralCoordinator` 和 persistent worker，并在 implicit window
前后执行 checkpoint/rollback；不使用旧 604-vertex participant。
离线审计已通过几何、q0、映射、张力分离和 XML parse，但当前 clone 的 Python
wire protocol 未暴露 P1 所需 SHM1 hydrodynamic-region extension。wrapper
因此 fail-closed，不能静默丢弃 added mass；`launch.sh` 仍不会启动求解。

## ANCF participant 源码审计（只读）

审计范围：本地 Git clone `D:/CFD/CFD_ANCF_VIV_source`（remote 为
`https://github.com/machao-fat/CFD_ANCF_VIV.git`，当前 HEAD
`8443209c4db39572f5099bec5d66a093eec7cdc3`），并检索
`participant`、`precice`、`initialize`、`advance`、`writeData/write_data`、
`readData/read_data`、`checkpoint`。

结论：仓库中新增了 HH06 兼容的 ANCF `Structure_0000` adapter；旧 fixture 仍不作为入口。

- `tools/precice_ancf_adapter_v1/ancf_structure_participant_v1.py`：离线/阶段 fixture，调用 participant 名 `Structure`，固定 604 个圆周顶点。
- `tools/precice_ancf_adapter_v1/ancf_cpp_worker_single_slice_participant_v1.py`：通用单切片 worker fixture，仍调用 `Structure` 且要求 604 个力顶点。
- `tools/precice_ancf_adapter_v1/ancf_generic_participant_v1.py`：注入式 generic orchestration class，没有实际 `Structure_0000` preCICE 入口。
- `tools/three_slice_force_contract_smoke_v1/structure_participant.py`：三切片 smoke participant，不符合本 HH06 单点 `Structure-Mesh`/33 节点/198 DOF 合同。
- `tools/cfd_current_dynamic_nonzero_bridge_v1/run_bridge.py`、`run_bridge_v2.py`：规定/桥接运动 fixture，40 个圆周顶点，并明确 `contains_ancf=false`。
- `tools/cfd_current_fixed_zero_bridge_v1/run_fixed_zero_bridge.py`：固定/零运动 bridge fixture，40 个圆周顶点，不是 ANCF。
- `tools/shiels_s5_k988_single_slice_free_fsi_long_development_v1/sdof_precice_continuation_participant.py`：`Structure_0000` SDOF 入口，使用旧 Re=100 SDOF 参数，不是 HH06 ANCF。
- 当前目录的 `ancf_worker_main.cpp`/`cfd_ancf_ancf_kernel_worker` 是 ANCF 数值核的持久 IPC worker；其 `initialize/advance/checkpoint` 是 worker 协议，不包含 `precice.Participant` 或 `Structure_0000` wrapper。
- 其他检索到的 `Structure_0000` 脚本属于 SDOF 或旧桥接 fixture，不是 HH06 ANCF wrapper，不能替代。

因此当前 blocker 已从“缺少入口”收敛为“Python wire protocol 与目标 worker 的 SHM1 能力尚未对齐”，不是张力数值冲突；本轮未改 kernel/worker、未执行 handshake。

## 高 Re 崩溃风险记录

历史同类高 Re 动网格 RAS 运行曾在 omega 发散后出现 Co 突增和 GAMG FPE；本轮不擅自修改 `fvSchemes`、`fvSolution`、RAS 模型或时间步来掩盖该风险。首次 0.2 s 只能在结构合同闭合后进行。

## 明确边界

`contract.json` 是合同身份和预检查输入，不是结构求解器；`precice-config.xml` 只定义耦合拓扑和时间；`launch.sh` 只负责预检查和启动。

## 可执行范围

- 可以：离线 JSON/XML 语法检查；在提供兼容 participant 后执行 preCICE participant-handshake dry-run。
- 当前不能：实际执行 handshake（SHM1 wire capability 未对齐）；OpenFOAM solve；ANCF time integration；读取或伪造 30 s FSI 结构 checkpoint。

## 初始状态与加速度边界

- `q0` 定义为 P1 `REF_NE32` 静力平衡，不是零质量状态。
- `v0=0`。
- 初始加速度不是 dry-run 合同字段，也不要求写入或猜测；不得用 `a0=0` 替代静力平衡定义。
- 30 s 仅为 Fluid restart 场；本轮没有 30 s 结构 checkpoint。

当前边界：`NO_OPENFOAM_RUN`、`NO_PRECICE_RUN`、`NO_ANCF_RUN`、`NO_NEW_TIME_DIRECTORY`。
