# VIV APP — Setup / Run Manager V1

当前分支提供最小 **Case Setup / Run** 两页。Case Generator 的 N5 执行合同已经通过真实五窗 smoke；**Run Manager 本轮只做 offline acceptance，尚未通过 GUI-driven real smoke**。本轮没有启动真实 CFD。

Run Manager 仅支持 `v2606-n5-implicit-production-v1`，原 generic explicit profile 仍仅离线生成。执行环境为已资格化的本机 WSL/Linux + OpenFOAM v2606 / preCICE 3.4.1；Windows native 可用于 offline Builder，不能直接运行该 Linux manifest。

## 安装和运行

所有 APP 文件、环境和测试输出都留在 `D:\CFD_Work\APP`。
以下在 Windows PowerShell / 已安装 Python 3.10+ 环境下使用：

```powershell
cd D:\CFD_Work\APP\app
python -m venv .venv-win
$env:PIP_CACHE_DIR = "D:\CFD_Work\APP\.cache\pip-win"
.\.venv-win\Scripts\python -m pip install -e ".[test]"
.\.venv-win\Scripts\python -m viv_app
```

本轮已在 WSL Python 3.10 环境安装并测试 PySide6 6.11.2：

```bash
cd /mnt/d/CFD_Work/APP/app
.venv/bin/python -m viv_app
```

重新安装 WSL 环境时：

```bash
cd /mnt/d/CFD_Work/APP/app
python3 -m venv .venv
PIP_CACHE_DIR=/mnt/d/CFD_Work/APP/.cache/pip .venv/bin/python -m pip install -e '.[test]'
```

PySide6 的依赖轮子包含 Qt；无需安装大型 UI framework。
参阅 [Qt 安装说明](https://doc.qt.io/qtforpython-6/gettingstarted.html) 和
[Qt 线程示例](https://doc.qt.io/qtforpython-6/examples/example_widgets_thread_signals.html)。

## 原 offline profile 操作

1. Browse Baseline 选择包含 `app_baseline.json` 的 baseline **根目录**。
2. 设置 Case Name、N、Uniform / Custom positions、流型和 MPI ranks。
3. 如使用 developed field，明确选择 Initial State Time；endTime 为流体绝对时间。
4. Generate Case。后台线程负责审计、复制和验证，GUI 显示进度与 first failure。
5. PASS 后可 Validate Generated Case 或 Open Case Folder。

默认输出为 `workspace/cases/<CASE_NAME>`；Output Root 必须仍在 APP 的
`workspace/cases` 中。已有目录拒绝，绝不覆盖。失败 staging 固定为
`workspace/cases/.<CASE_NAME>.staging` 并保留失败证据；再次生成会拒绝已有
staging，不在另一目录自动重跑，不提供 overwrite/regenerate。

Linux 使用 renameat2 不覆盖发布；D: 的 WSL DrvFS 使用已存在的 Windows
PowerShell / `.NET Directory.Move` 同盘原子移动（不覆盖）。缺少该 interop
时会失败保留 staging，不退化成危险的覆盖操作。Windows native Python
使用 Windows directory rename。本轮没有安装或改变系统环境。

## 原 explicit baseline 合同与复用

详见根目录 `APP_BASELINE_AUDIT.md`。APP 从当前 worktree 的 `src/` 导入既有
`SliceManifest`、`build_slice_manifest`、`generate_precice_xml`、XML inspector、
launch-plan helper 和 `KernelModel.validate`。不复制或改写 production kernel。
应用需要留在该 worktree 中；V1 不是独立打包产品。

支持的显式导入 profile：`arbitrary-n-live-explicit-v1`。描述文件完整示例见：
`tests/fixtures/synthetic_distributed/app_baseline.json`。它声明：

* local fluid template、native slice manifest、native KernelModel JSON、明确的
  serialized q/qdot/qddot；所有引用都必须在 baseline 内，禁止 symlinks。
* fixedValue / uniform inlet 的精确 patch 路径和单位方向，保留内部流场。
* required initial fields、明确的初始 time、Ns/positions/active interval。
* 已验证的 naming profile 和 time-window == deltaT 关系。
* `SYNTHETIC_OFFLINE_ONLY` 或用户声明的 `USER_VERIFIED_BASELINE` evidence status。
  APP 保存声明，不替用户证明 physical qualification。

这份 descriptor 是 APP 的导入适配层。真实 baseline 的语义必须先被审计确认，
不能只添加一个标签就认为结构入口/force scaling 已通过验证。

仅接受与 native explicit XML helper 在结构上完全相同的 XML；允许安全重定位
旧 socket path，不接受 implicit/retry/convergence settings 的隐式改变。
仓库 `cases/hh06_single_slice` 不满足该合同，会明确 FAIL CLOSED：它是
implicit XML + 固定单切片/P1 artifact 入口，当前 main 没有唯一的 arbitrary-N
production structure launcher。本轮没有修改它以迎合 APP。

## 当前能力

* N=1..32、native uniform centers / custom ordered positions；端点依据 native
  active interval 校验。SLD1 requires N>=2；N1 用独立 legacy baseline，绝不自动
  切换 load reconstruction。V1 legacy 限 N1，继承代表长度。
* Uniform、Linear Shear、Step Current：按真实 s/L 计算 inlet U_i。Step 定义为
  `s/L <= transition` 使用 U_active。GUI 实时显示位置、速度和 MPI 总数。
* baseline mesh 按 slice 独立复制；仅复制 system、constant、选定 time 和结构
  初始状态，不复制 processor*/postProcessing/logs/其他时间目录。
* binary U 的 internal payload 原样保留，仅编辑独立 ASCII boundary dictionary。
  其他选定字段、old-time 数据及 time mesh 原样继承，不生成或重算 phi/Uf 等。
* root controlDict deltaT/endTime/writeInterval、MPI scotch ranks；不改 nested
  function-object writeInterval、fvSchemes、fvSolution 或 turbulence。
* native SPX1/SLD1/SHM1 配置检查与 slice 同步；只允许 Rayleigh alpha [1/s] 编辑。
* 原子 staging 发布、provenance、离线静态报告、重验证/篡改检查、后台 worker。

D、L、EA、EI、线质量、预张力、单元数显示 baseline 值并标记 NOT YET WIRED。
这些量虽有 native model 字段，但更改还需要一致的 CFD mesh 或静力平衡态。
本轮不解静力、不缩放网格、不重新采样 q。节点数从单元数推导。

## 原 offline profile 的不支持项和限制

原 generic explicit profile 没有 Run/Abort/Restart 或实时监控。全 APP 不提供 FFT/PSD/曲率、Results、网格生成、安装器、exe 打包或数据库。原 generic explicit profile 不提供多切片结构 CLI runner；其 launch manifest 中 structure
command 为 null，production_launch_ready=false。

未知 profile、字典 include/code/substitution、未知 inlet 类型、compressed U、
非 scotch decomposition、adaptive time step、forceCoeffs 独立 magUInf 合同、
不明结构初始状态均失败关闭。不同 slice mesh/extrusion 不推断。V1 所有 slice
必须 Enabled；取消勾选时给出明确错误，需减少 N 来移除切片。

关键配置 hash 限 2 MiB；大型内部 U 只记录长度及两端各 4 KiB sample identity，
不会对历史 runtime 全目录做 SHA256。baseline 前后全文件字节不变的证明只用于
小型 synthetic fixtures。真实生成另外校验所选关键配置的前后身份。

## 测试和示例

```bash
cd /mnt/d/CFD_Work/APP/app
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests
```

测试不启动求解器；temporary fixtures 全部写入 APP/workspace/cases/.tests。
不要把 `--basetemp` 指向已有 production case。N1/N3/N5、所有 flow profiles、
custom/uniform positions、目录拒绝、binary field/old-time 保留、XML/配置篡改、
staging 失败保留、baseline immutability 和 GUI event-loop 响应均有 offline tests。

可选择 bundled synthetic baseline 体验 GUI，但 **不要运行 synthetic CFD**。
生成示例：`../workspace/cases/synthetic_N5_step`。
原 offline generated cases 有 simulation_spec.yaml、generation_manifest.json、
slice_manifest.json、launch_manifest.json、Structure_0000 配置和
`generation_validation.json`。初始字段/mesh 来自 baseline，APP 不创造新物理状态。

## 已完成的 V2606 N5 production baseline bridge V1（历史范围）

在 GUI 的 **Import Profile** 选择 `v2606 N5 implicit production (NM12)`。程序只读审计已登记的本机 NM12 N5 short100 PASS lineage；外部 evidence/binary/library 不存在或身份漂移时拒绝生成。原 `arbitrary-n-live-explicit-v1` offline profile 继续存在。

本版 production 只支持 **N5 → N5**。实际 participant 是 `Fluid-S1`…`Fluid-S5` 和 `Structure`。可修改 case name、APP 内 output root、流体绝对 endTime、timeStep writeInterval、purgeWrite 和三种 flow profile 算出的每片 inlet U_i。L=13.12 m，五个位置固定为 0.594/1.782/2.970/4.158/5.346 m；N、结构物理参数、dt=0.0004、初态、每片四 MPI ranks 均锁定，因为成功的 Structure executable 把这些值编译在代码中。endTime 与初态时间之差必须是整数个 coupling windows。流速变化仅修改当前 U/inlet/value，保留 developed internal field 和 old-time 文件；零流速关闭无定义的 forceCoeffs 归一化诊断，native forces/FSI 保留。

**Generate Case** 写真实生产配置和初态，自动 Static Validation。然后点击 **Production Preflight**：验证 OpenFOAM v2606、preCICE 3.4.1、XML、外部库/二进制身份、共享库依赖和 20+1 CPU layout。只有全部检查通过，`production_launch_ready=true`。所有复制、验证和环境探测在后台 worker 执行。

重要的就绪范围：输出是 **串行 mesh + selected frozen30 fields + 手动准备/启动命令**。APP 不复制 processor*，也不运行 decomposePar。必须经人工审议后，先执行生成目录 `MANUAL_LAUNCH.md` 的五个分区命令，再在独立终端启动 Structure 和五个 Fluid。此文件仅列出命令；本轮没有执行。production solver、adapter 和 observer libraries 是 `EXTERNAL_SOLVER_DEPENDENCY`，保留原路径并校验 SHA256。本机环境为 WSL，APP 不安装环境、不复制求解器、不创建 RUN 按钮。

真实示例（默认已有则拒绝覆盖）：

```bash
cd /mnt/d/CFD_Work/APP
app/.venv/bin/python app/examples/generate_production_n5.py
```

输出 `/mnt/d/CFD_Work/APP/workspace/cases/production_N5_bridge_dryrun`；该命令只生成并 preflight，绝不启动 FSI。

运行 GUI：

```bash
cd /mnt/d/CFD_Work/APP/app
.venv/bin/python -m viv_app
```

测试只用一个 pytest 会话，避免共享临时目录相互清理：

```bash
cd /mnt/d/CFD_Work/APP/app
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -m smoke
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
```

测试不启动 OpenFOAM/preCICE/ANCF/MPI simulation。smoke 包含模型、flow、N5 topology、XML、manifest 和 fail-closed validation；完整测试保留原 offline acceptance。`production_integration` 在本机有真实外部 artifact 时只读导入并检查 GUI locks，其他机器会 skip。generated cases 已从 Git tracking 移除，本地原文件保留；最小 synthetic fixtures 在 `app/tests/fixtures/`，production descriptor 在 `app/resources/baseline_profiles/v2606_n5/`。本轮不支持 N3/arbitrary-N production、实时监控、restart、后处理、打包，也没有执行 production smoke。

审计见 `resources/V2606_N5_PRODUCTION_BASELINE_AUDIT.md`；就绪分类只代表配置/命令可供手动启动，NM12 原 short100 的物理验证范围不会自动推广到新流速或长运行。

## Run Manager / Monitor V1

1. 在 Case Setup 中生成新的 N5 production case，或用 **Select Generated Case** 选择未运行的生成目录。已经执行过的 smoke case/旧 runtime 不能再次 Run；本版没有 restart/continuation。
2. **Production Preflight** 检查环境和生产身份；**Prepare Case** 还会重新验证并执行 manifest 内五条 decomposePar argv，核对四分区、初始 fields/mesh，写 `preparation_result.json`。
3. 只有 Prepare 全部 PASS，Run 页面 **Run** 才启用。实际 Run 前后台再次执行 prepared 静态检查/Preflight，比较 Prepare 保存的配置 hash、分区初态的 bounded identities 和 APP source hashes。
4. Run 依照已验证 manifest 的 startup_order，先启动 Structure，再启动 Fluid-S1…S5；六方 preCICE handshake 后进入 RUNNING。原 schema 的 `execution=MANUAL_ONLY` 是生成器历史标记；Run Manager 不改它、不拼新 argv，严格复用该手动合同并额外做 Prepare/Run gate。
5. **Abort Run** 只操作本管理器创建的 PID tree/process groups，并校验进程创建时间防止 PID 复用。SIGTERM → configurable grace → 必要时 SIGKILL。界面关闭时也先清理本次子进程。显示 **ABORTED RUN MAY NOT BE RESTARTABLE**，不是 Safe Stop。

状态：CREATED → VALIDATED → PREFLIGHT_PASSED → PREPARING → PREPARED → STARTING → HANDSHAKING → RUNNING → COMPLETED；失败进入 FAILED，人工终止走 ABORTING → ABORTED。非法转换拒绝；FAILED/ABORTED/COMPLETED 不能复用旧 handles。只有六个自然 exit=0、所有 handshake、目标严格接受窗及 committed journal/Structure final count 一致，才 COMPLETED；零 exit 但窗口不足为 FAILED_INCOMPLETE。

所有执行在后台 supervisor 线程中，用 argv 数组和 manifest cwd/environment 启动独立 session，Qt signals 更新界面。Setup 与其他 case 操作在管理器工作期间锁定。stdout / stderr 完整保存在 `case/runtime/logs/<participant>.log` / `<participant>.stderr.log`；双击 participant 打开完整 stdout。每次实际启动保存 `runtime/run_<UTC timestamp>_<id>/run_manifest.json`、`participants.json`、`runtime_monitor.jsonl`、`run_result.json`，case 根也写最后 `run_result.json`。JSONL append+flush；GUI 崩溃时已写事件留盘，但本版不是脱离 GUI 的服务，进程强制崩溃/宿主掉电后的接管不受支持。

监控 parser 独立于 GUI，按实际 NM12 的 NM9_ATTEMPT/NM9_FINAL、preCICE 3.4.1 convergence grammar 和 v2606 Info grammar 解析；处理 ANSI、UTF-8 split、partial line，未知普通行忽略，损坏 authoritative NM9 marker/fatal/nonzero/handshake timeout 失败关闭。数值是 stdout 的格式化 residual，而非事后 full-precision CSV。相对 residual 的 bootstrap `inf` + zero normalization/native conv=true 尊重生产语义，不当作物理字段非有限。

主进度只由 accepted windows 的 coupled elapsed 推进；trial 不推进。显示时间/窗数/iteration/force、displacement residual/rejected count、max Co/mesh Co 及 slice。Rejected / Rollbacks 是 qualified Structure rejection marker 的观测计数，本版不重复逐窗读取 kernel q/v 做数学资格化。ETA 标记 ESTIMATE，20 窗前 warming up，此后最近 50 个 accepted timestamps 估计。三幅原生 QPainter 图最多保留 500 个 accepted points；Events 最多 2000 行；所有完整 structured events 仍写盘。资源每 1 s 轻量采样，通过已认证 PID 的 `/proc/<pid>/task/*/children` 逐层追踪自己登记的 roots/captured descendants（不调用会扫描全系统 PPID 的 psutil.children/process_iter/pids），显示 CPU、RSS（含 shared pages 的和）、系统 RAM 和磁盘余量，不扫描或控制其他 CFD。

非物理参数配置在 `viv_app/runner/run_options.json`：startup timeout=180 s，Abort grace=10 s，decompose timeout=300 s，poll=0.1 s，资源采样=1 s，退出后的 log drain timeout=5 s。ENODATA 只在 log tail 的显式 offset 读取处暂缓，cursor 不移动；退出后仍不可读则失败关闭。运行 manifest 记录这些值。dt=0.0004、五片各四 MPI/CPU bindings、N5 positions/physics/XML/IQN/PIMPLE/mesh 保持原生产合同；没有改变 kernel、binary、adapter、mapping、force conversion 或 coupling mathematics。

测试：

```bash
cd /mnt/d/CFD_Work/APP
QT_QPA_PLATFORM=offscreen app/.venv/bin/python -m pytest app/tests -m smoke
QT_QPA_PLATFORM=offscreen app/.venv/bin/python -m pytest app/tests
```

fake participants 只运行 tiny Python fixtures，没有 OpenFOAM、MPI、preCICE 或 ANCF。测试 artifacts 在 APP/workspace/cases/.tests，忽略，不提交 runtime。完整测试包含 slow startup/fatal/nonzero/incomplete/partial line/Co warning/own-only Abort/unrelated dummy/GUI close/event-loop。真实 smoke 的微小日志 excerpt 只用于 parser 格式回放。

本版不提供 Results/restart/continuation/committed stop、后处理、FFT/曲率/模态、动画、ParaView、N3/arbitrary-N production、网格生成、数据库或 installer/exe。offline 全部通过后 **STOP**，GUI-driven N5 五窗 smoke 必须等待下一次人工授权；本次不会自动启动。

Prepare 和 Run 目前必须在同一 GUI 会话完成；关闭后不能自动接管已有分区或运行。case lock 不自动恢复，FAILED/ABORTED/已执行目录也不自动清理或覆盖。若配置错误需要人工修正，使用原 case 目录并先确认没有使用它的进程；本版不实现恢复向导。
