# VIV_APP_CASE_GENERATOR_MVP_V1

日期：2026-09-30（Asia/Shanghai）。

交付范围：独立 APP worktree 内的 PySide6 单页 Case Builder 和严格的 offline
case generator。**production baseline 接入仍为 CONTRACT BLOCKED；未达到
“选择现有 HH06 baseline 后可按现有生产方式手动启动新多切片 FSI”这一目标。**
不会将 synthetic static PASS 声称为完整工程可运行/物理验证。

## Git / 工作目录

* Branch：`app/mvp-case-generator-v1`。
* Fetch 后 origin/main / base commit：
  `a1c4988b23d4a61edbb4c00e6d53926add51d795`。
* 本地：`D:\CFD_Work\APP`；WSL：`/mnt/d/CFD_Work/APP`。
* 基于本机合法 clone 创建独立 worktree；APP 目录原为空。
* 原 diagnostic branch / HEAD 保持
  `diagnostic/phase1k32-v2606-rollback-repeatability-v1` /
  `e30c9583895746fc266b5d8ef1f0e4749cf882e1`，未提交项列表保持原样。
* `src/`、原 `cases/`、`scripts/`、`docs/`、原 `tests/`、`evidence/` 相对 base
  无差异。没有修改 main、production kernel/adapter、coupling mathematics、
  SHM1/SLD1 算法、历史证据或正在运行的算例；没有删除已有 worktree。

## 新增文件

* `APP_BASELINE_AUDIT.md`：真实 main 审计、可写/继承/锁定字段、production blockers。
* `app/pyproject.toml`、`app/README.md`、独立环境 ignore。
* `app/viv_app/main.py`、`__main__.py`、`ui/main_window.py`、`ui/theme.qss`。
* `models/simulation_spec.py`；`generator/` 中 baseline、native bridge、保留字节的
  OpenFOAM dictionary editor、fluid/structure/XML generator、原子发布、静态验证。
* `app/tests/`：generator 与 GUI offline tests；测试临时文件位于 APP 内。
* `app/resources/baseline_copy_rules.yaml`、测试记录/修复记录、`gui-preview.png`。
* `app/examples/`：小型 synthetic fixture / N1、N3、N5 示例生成脚本。
* `workspace/baselines/synthetic_distributed`、`synthetic_legacy_n1`；
  `workspace/cases/synthetic_N1_uniform`、`synthetic_N3_uniform`、`synthetic_N5_step`。
* 根 `.gitignore` 只新增 APP 下载/测试 cache ignore；没有生产源码修改。

## UI 当前能力

Baseline Browse、Initial State Time、Case Name、Output Root、N=1..32、Uniform / Custom
positions、实时 s/s/L/U_i/MPI 摘要；Uniform / Linear Shear / Step Current；统一和逐片
MPI ranks；deltaT/endTime/writeInterval；生成/验证/打开目录四个主要按钮。
低饱和深色 QSS。复制、baseline 审计与验证使用 QObject + QThread。
默认显示和 WSLg Wayland 启动 smoke 均通过。

D、L、EA、EI、线质量、预张力、ANCF 元素数显示 baseline 值并锁定为 NOT YET WIRED，
节点数由 element count 推导。可编辑阻尼明确限定为 Rayleigh alpha [1/s]。

## Generator 当前能力

复用 main 的 native manifest、XML/inspection、launch-plan 和 KernelModel 验证。
只接受经过明确声明并可静态核对的 generic explicit import profile，继承原 load
reconstruction/active region/unit span/SHM1/initial state，不自动切换耦合数学。

按切片复制 system、constant、指定初始 time；保留 opaque binary U 内部数据及
phi/Uf/meshPhi/old-time 文件，不伪造 restart fields。只编辑确定的 dictionary paths。
已有目标拒绝、同盘原子发布；D: DrvFS 使用 Windows Directory.Move 不覆盖。
固定失败 staging 保留，拒绝自动新目录重跑。输出 specification、native slice /
structure 配置、preCICE XML、launch manifest、provenance 和静态验证报告。

## 测试结果

* 完整 offline tests：**41 passed，0 failed，384.23 s**。
* N1/N3/N5 generator tests：全部 PASS；三个保存的示例分别重验证为 static PASS。
* Uniform / Linear Shear / Step、uniform/custom positions、N32 topology、XML /
  participant naming、invalid positions/ranks、existing-target/staging refusal：PASS。
* baseline immutability：N1/N3/N5 的 tiny fixture 全文件 SHA256 前后相同：PASS。
  正式 runtime 没有被全目录 hash，也没有被复制。
* binary U / selected developed-time / phi/Uf/meshPhi/old-time 保留：PASS。
* GUI 启动、真实复制期间 QTimer tick >=10、worker 正常结束、MPI widget 不覆盖
  U_i 列、FAIL display 和生成后重验证：PASS。
* `app/resources/acceptance-results.json` 保存验收范围；production_launch_ready=false。
* **以上测试证明 APP 的离线行为，不能消除 production contract blocker。**

第一次 combined GUI 测试的 15 s watchdog 导致测试退出时销毁尚在复制的线程。
已在原 APP 目录修复测试 deadline/收尾，并单独通过 3 个 GUI 回归；最终完整
回归记录见 `app/resources/offline-test-results.txt`。该初始失败保留在
`app/resources/TEST_REPAIR_LOG.md`，不计作 PASS。

## 已知限制 / 尚未支持

* main 中的 HH06 XML 是 implicit；现有 generic helper 是 explicit。
  HH06 Structure wrapper 固定单片/32 元素，并依赖外部 P1 artifact。
  不能把该 baseline 自动改成 arbitrary-N；目前明确 FAIL CLOSED。
* main 没有已核定的 generic multi-slice structural CLI launcher。结构 native
  配置生成了，但 launch manifest 的 structure command=null，
  production_launch_ready=false；不声称现有生产启动链已接通。
* bundled baselines 全为 SYNTHETIC_OFFLINE_ONLY，不是跑通的物理 baseline。
* 未知 include/code/substitution、未知 inlet、compressed fields、非 scotch、
  adaptive dt、独立 forceCoeffs reference-speed 合同、变截面 mesh/extrusion 等拒绝。
* geometry/material/pretension/element 编辑还需要匹配网格/平衡态，V1 不实现。
* V1 全部 slice 必须 Enabled；关闭时给出错误，需减少 N。
* GUI 不启动 CFD/preCICE/ANCF/MPI，不提供 solver launcher、监控、restart、
  continuation、FFT/PSD、后处理、自动网格、环境 installer、exe 或数据库。
* 本轮没有实际选择/复制/修改正式 runtime，也没有执行物理计算。

## 运行与示例

已安装的 WSL 环境：

```bash
cd /mnt/d/CFD_Work/APP/app
.venv/bin/python -m viv_app
```

Windows 原生安装/运行命令和测试命令见 `app/README.md`。Windows native Python
未在本轮实测；本轮实测平台为 WSL Python 3.10 / PySide6 6.11.2。

Generated example：
`D:\CFD_Work\APP\workspace\cases\synthetic_N5_step`。
该目录已有 static validation PASS，但其 synthetic status / structural runner gap
禁止把它解释成 production-ready。示例 manifest 如实记录生成时的 base commit、
APP branch、dirty=true、实际 APP source hashes 和 baseline key hashes。

交付后仅 push APP branch，不 merge main，不创建 PR，不进入下一 Phase。
