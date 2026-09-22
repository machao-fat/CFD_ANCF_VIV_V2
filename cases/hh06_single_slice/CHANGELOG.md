# 配置变更日志

## PREP-V1

- 将 `controlDict` 目标终点冻结为 30.2 s；保留 `latestTime`、`deltaT=2e-4 s` 和每 0.01 s 的完整场写出策略。
- 将 `precice-config.xml` 从旧 Ur=4.5 续算 socket/60 s 合同改为本目录本地 socket、0.2 s、0.0002 s 耦合窗口。
- 保留 `system/preciceDict` 的 `pointDisplacement`、`cellDisplacement`、Force 和 Fluid_0000 绑定。
- 仅更新高 Re 物理注释；未擅自改变物性、RAS、网格、fvSchemes 或 fvSolution。
- 添加 `contract.json`、`PRE_RUN_AUDIT.md` 和 fail-closed `launch.sh`。
- 由于高 Re 单切片 ANCF 结构合同尚未确认，脚本当前拒绝启动。
- 根据用户提供的远程分支信息，复制了 `355640e11925b9feddd1a52bb3d93596e5ee8251` 的 C++ ANCF kernel 源码快照；未把不匹配的旧 participant 冒充为生产入口。

## HH06-CONTRACT-V1

- 新增 `structure_contract.json`：冻结 HH06 P1 单切片几何、Ne=32、初始张力 1175 N、湿结构静力初始状态定义和接口边界；未填入未经 P1 工件确认的质量、EA、EI 或阻尼数值。
- 新增 `mapping_contract.json`：冻结 s=2.97 m、DeltaL=1.98 m 以及 `F_slice=(F_raw/0.028)*1.98` 的单次单位转换；禁止 CFD 面索引与 ANCF 状态顶点一一对应。
- `contract.json` 状态改为 `READY_FOR_DRY_RUN`，加入结构、映射和 Fluid_0000/Structure_0000 接口合同；保持 D/U/Re/deltaT/30 s CFD 起点不变。
- `PRE_RUN_AUDIT.md` 更新为 dry-run 范围说明。实际 participant 缺失和 P1 截面/静力工件缺失仍是时间积分前阻塞；未启动任何求解。
