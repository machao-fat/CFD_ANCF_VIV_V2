# VIV Studio

CFD–ANCF 柔性立管涡激振动仿真平台。当前界面以简体中文为主，采用浅色卡片布局，提供“算例设置”和“运行监控”两页。“结果分析”标明尚未开放，不能触发工作。

这是现有 Case Generator / Run Manager 的显示层升级。Python package、profile ID、manifest 字段以及生产执行合同保持原名。当前实现仍在 WSL/Linux 中运行，文件位于 `D:\CFD_Work\APP`，GUI 使用 WSLg；没有 Windows 前端协议、Windows Python 安装或 exe 打包。

## 启动

使用现有 WSL 环境：

```bash
cd /mnt/d/CFD_Work/APP/app
.venv/bin/python -m viv_app
```

需要重建 APP 自身 Python 环境时：

```bash
cd /mnt/d/CFD_Work/APP/app
python3 -m venv .venv
PIP_CACHE_DIR=/mnt/d/CFD_Work/APP/.cache/pip .venv/bin/python -m pip install -e '.[test]'
```

使用 PySide6 原生组件和 QPainter，没有新增 UI framework、绘图库、图标包或字体文件。中文优先使用已有 Noto Sans CJK SC / Microsoft YaHei UI / Microsoft YaHei 字体。WSL 缺少中文字体时，可在当前 Qt 进程注册 Windows 已有的 `msyh.ttc`；不复制、安装或分发该字体。

## 当前资格状态

N5 Case Generator 的手动执行合同已通过历史五窗真实 smoke。Run Manager 已通过离线资格测试；历史 GUI 真实尝试在 Prepare 的 symlink identity 阶段失败，尚未启动耦合参与端。该缺陷已在上一阶段离线修复。

**本轮 UI 改造仅做离线测试和模拟截图，没有执行真实 decomposePar、CFD、preCICE、ANCF 或 MPI simulation。新界面与修复后的完整真实执行资格，留待单独授权的 GUI N5 smoke V2。**

## 算例设置

1. 选择“V2606 N5 Production”，或选择支持合同的自定义离线基准。基准审计在后台进行，始终只读。
2. 设置算例名称；“基准与输出目录”展开显示精确路径。默认输出 `workspace/cases/<CASE_NAME>`，输出必须留在 APP 的 cases 根目录内。
3. 选择均匀流、线性剪切流或阶梯流。模式按钮调用现有 FlowProfile；Slice 表同步展示实际位置、s/L、U 和 MPI。
4. 生产锁定参数显示为只读摘要。D/L/EA/EI/线质量/预张力/单元数不接线为可编辑参数；generic offline 仅保留已有 Rayleigh α 编辑能力。
5. “生成算例”在后台复制必要配置和所选初态、发布新目录，自动完成静态检查。已有目标或 staging 拒绝覆盖，失败证据留在原 staging 内。
6. “静态检查”和“运行前检查”复用现有 validator / Production Preflight。没有通过运行检查的案例不能直接开始计算。

生产 profile 的内部 ID 为 `v2606-n5-implicit-production-v1`；外部 NM12 evidence、Structure binary、adapter 和 observer libraries 必须存在且身份一致，作为 EXTERNAL_SOLVER_DEPENDENCY 使用。APP 不复制或修改这些求解器。

仅支持 production **N5 → N5**：参与端为 Structure 和 Fluid-S1…Fluid-S5；位置固定 0.594/1.782/2.970/4.158/5.346 m；每片四 MPI ranks，CPU 分别 0–3/4–7/8–11/12–15/16–19，Structure CPU20；deltaT=0.0004 s、P1_REF_NE32 和精确 frozen30 初态锁定。结构参数来自已登记 baseline，界面不会套用示意值。

允许编辑已有合同暴露的 endTime、writeInterval、purgeWrite 和流速。endTime 是流体绝对时间，与精确初态之差必须构成整数个 coupling windows。不会改 mesh、PIMPLE、IQN-ILS、mapping、force scaling 或 turbulence。

原 `arbitrary-n-live-explicit-v1` profile 继续仅支持离线生成 N1/N3/N5 等案例，不提供生产 Run；N1 需独立 legacy baseline，SLD1 的 N≥2 要求保持原样。精确 inlet dictionary path、binary internal U、old-time 数据、结构初态和 native XML 合同均沿用既有实现。未知合同 FAIL CLOSED。

## 准备与运行监控

这些功能保留现有 Run Manager 行为；本阶段不执行它们的真实生产命令。

* “准备计算”再次检查 production identity，随后由现有 Run Manager 执行 launch_manifest 的五条 decomposePar argv，检查四分区、八初始 fields 和五 mesh 文件，写 preparation_result.json。
* 只有 PREPARED、没有后台工作、且 launch identity 未改变时，“开始计算”可用。进入运行监控页本身不会启动进程。
* Run 复用 manifest 的 argv、cwd、environment、CPU binding 和 startup_order，先 Structure 后五个 Fluid。六方 handshake 后进入 RUNNING。
* 主进度只由 accepted windows 推进，trial/rejected attempt 不推进。ETA 保留 ESTIMATE 语义，20 个 accepted windows 前显示预热中。
* 运行页显示状态、接受窗口、物理时间、已运行时间、迭代、Force/Displacement residual、回滚次数和 Co/Mesh Co。三张 QPainter 图各保留最近最多 500 点。
* Participant 默认展示名称和健康状态；完成后可显示 Exit。高级信息保留 PID、路径和记录；双击参与端可打开完整 stdout 日志。
* 资源采样沿用认证 PID tree，显示 Solver CPU、RSS、系统 CPU/RAM 和磁盘余量。运行事件默认收起，最多 2000 行；完整事件仍写 runtime_monitor.jsonl。
* 失败卡显示第一因果错误，原技术文本不改写；“查看详细信息”保留完整失败对象和 traceback。

“终止计算”是 **Abort**，只终止本管理器创建并验证 birth time 的 process tree。它不是 checkpoint-safe stop，不保证可继续计算。关闭运行中的 GUI 沿用现有清理逻辑；不会控制无关进程。

CREATED → VALIDATED → PREFLIGHT_PASSED → PREPARING → PREPARED → STARTING → HANDSHAKING → RUNNING → COMPLETED 的状态机不变。失败为 FAILED；Abort 为 ABORTING → ABORTED。COMPLETED 必须满足六次 handshake、目标严格接受窗、committed journal / Structure final count 一致和六方自然 exit=0。

每次运行的 run_manifest.json、participants.json、runtime_monitor.jsonl 和 run_result.json 继续写 `case/runtime/run_<...>/`；完整 stdout/stderr 写 `case/runtime/logs/`。Prepare 与 Run 须在同一 GUI 会话，不能接管历史运行、自动 restart 或复用失败进程。

## 离线测试与截图

依次执行，一次只运行一个 pytest 会话：

```bash
cd /mnt/d/CFD_Work/APP
QT_QPA_PLATFORM=offscreen app/.venv/bin/python -m pytest app/tests/test_ui_cn.py
QT_QPA_PLATFORM=offscreen app/.venv/bin/python -m pytest app/tests -m smoke
QT_QPA_PLATFORM=offscreen app/.venv/bin/python -m pytest app/tests
```

测试使用 tiny fixtures、Python fake participants 和 dummy unrelated process，绝不运行真实求解器。测试临时目录固定在 `workspace/cases/.tests`；不要把 basetemp 指向 production case。host integration 只读真实基准和已存在的 decomposition 见证，不存在则 skip。

四张 UI 截图只注入模拟显示数据，标注“离线展示数据”，不点击生成、准备或运行：

```bash
cd /mnt/d/CFD_Work/APP/app
QT_QPA_PLATFORM=offscreen .venv/bin/python examples/capture_ui_cn.py
```

输出 `workspace/evidence/viv_app_ui_ux_cn_v1/screenshots/`，含设置、PREPARED、模拟 RUNNING 和模拟 FAILED 四张图。它们不是生产运行证据。

## 范围与限制

没有 Results、restart、continuation、safe committed stop、FFT/PSD、后处理、曲率/模态、动画、ParaView、N3/arbitrary-N production、网格生成、数据库或安装器。GUI 不会自动开始下一次真实 smoke。

1280×800、1366×768、1440×900 和 1920×1080 通过离线布局/响应检查；小窗口可纵向滚动。字体取决于宿主现有环境；截图使用 offscreen Qt，不等于已经验证所有 Windows DPI/WSLg 组合。

报告见 [UI 阶段报告](../APP_UI_UX_CN_V1_REPORT.md)。生产 baseline 审计见 [V2606 N5 审计](resources/V2606_N5_PRODUCTION_BASELINE_AUDIT.md)，原合同见 [APP baseline 审计](../APP_BASELINE_AUDIT.md)。历史分类和证据保持原样。
