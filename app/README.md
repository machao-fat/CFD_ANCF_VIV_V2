# VIV Case Generator MVP V1

单页 PySide6 Case Builder，只生成、静态验证文件；**不会启动 OpenFOAM、
preCICE、ANCF 或 MPI simulation**。

当前交付状态：**V2606 N5 production bridge READY**，真实 NM12 profile 可生成并做 Production Preflight；仍只生成配置与手动命令，不启动物理计算。原旧 HH06 / generic explicit profile 的 structural-launch blocker 保留。两个 profile 独立，synthetic 静态 PASS 不代表物理验证。详见下方 production bridge 部分。production profile 目前须在本机 WSL 环境运行；Windows native 环境只验证过原 offline 能力。

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

没有 RUN/STOP/RESTART、实时监控、FFT/PSD/曲率、结果页、网格生成、安装器、exe
打包或数据库。原 generic explicit profile 不提供多切片结构 CLI runner；其 launch manifest 中 structure
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

## V2606 N5 production baseline bridge V1

在 GUI 的 **Import Profile** 选择 `v2606 N5 implicit production (NM12)`。程序只读审计已登记的本机 NM12 N5 short100 PASS lineage；外部 evidence/binary/library 不存在或身份漂移时拒绝生成。原 `arbitrary-n-live-explicit-v1` offline profile 继续存在。

本版 production 只支持 **N5 → N5**。实际 participant 是 `Fluid-S1`…`Fluid-S5` 和 `Structure`。可修改 case name、APP 内 output root、流体绝对 endTime、timeStep writeInterval、purgeWrite 和三种 flow profile 算出的每片 inlet U_i。L=13.12 m，五个位置固定为 0.594/1.782/2.970/4.158/5.346 m；N、结构物理参数、dt=0.0004、初态、每片四 MPI ranks 均锁定，因为成功的 Structure executable 把这些值编译在代码中。endTime 与初态时间之差必须是整数个 coupling windows。流速变化仅修改当前 U/inlet/value，保留 developed internal field 和 old-time 文件；零流速关闭无定义的 forceCoeffs 归一化诊断，native forces/FSI 保留。

**Generate Case** 写真实生产配置和初态，自动 Static Validation。然后点击 **Production Preflight**：验证 OpenFOAM v2606、preCICE 3.4.1、XML、外部库/二进制身份、共享库依赖和 20+1 CPU layout。只有全部检查通过，`production_launch_ready=true`。所有复制、验证和环境探测在 QThread 执行。

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
