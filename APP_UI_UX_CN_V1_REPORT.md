# VIV APP UI/UX CN V1 报告

最终分类：`VIV_APP_UI_UX_CN_V1_PASS`。

用户于 2026-10-01 在收到收尾截图和全部离线测试结果后回复“可以收尾”，完成最终视觉验收及收尾授权。

## 来源与隔离

- 仓库：machao-fat/CFD_ANCF_VIV_V2。
- 冻结 base：`471619c2eec718d9ad834752c7c6e8c613cbd843`。
- 开始时实际分支：`app/prepared-symlink-contract-repair-v1`，HEAD 与 base 完全一致，worktree clean。
- 新分支：`app/ui-ux-cn-v1`，从上述 base 建立。
- 本地目录：`D:\CFD_Work\APP` / `/mnt/d/CFD_Work/APP`。
- UI 实现 HEAD：`25f41d059b69556a52bf1321e07a5f75916b64ec`；该提交直接继承冻结 base。最终交付的后续报告提交只补充本报告和小型 JSON。UI_PASS_HEAD 为该 closeout 提交；用 `git rev-parse app/ui-ux-cn-v1` 读取，精确 SHA 同时保存在本轮 ignored evidence 的 final_classification.json 和交付消息中，避免报告自引用 commit SHA。
- 受保护的 repair / run-manager / bridge / main 分支未更新。完整 refs 与限定 source SHA 见本轮 evidence 的 source_scope_check.json。

## 信息架构与语言

显示品牌为 VIV Studio，副标题为“CFD–ANCF 柔性立管涡激振动仿真平台”。包名、入口 module、schema、manifest 字段和 production profile ID 未重命名。

白色产品外壳包含左侧导航和两页：算例设置、运行监控。“结果分析 · 尚未开放”禁用，没有第三个假页面。

设置页拆成算例信息、来流条件、Slice 配置、只读结构模型、数值与并行、算例摘要和底部检查与生成区域。基准/输出的长路径默认收起，可展开查看。三种流型通过模式按钮调用既有 FlowProfile，稳定 wire token 保留。s/L 只精简绘制文字，model 中的 15 位精度文本与 SimulationSpec 输入不变。

锁定的结构参数、deltaT、MPI 和初态以只读标签呈现；Production 的 D=0.028 m、L=13.12 m、32 ANCF 单元、33 节点 / 198 DOFs、P1_REF_NE32 等来自已有合同，没有套用任务中的示例直径。generic offline profile 保留原有可编辑能力，NOT YET WIRED 物理量仍不可编辑。

运行页顶部四张卡：状态、已接受窗口、物理时间、已运行时间。耦合指标和参与端健康分开；PID/路径/日志位于高级信息，退出码在完成后显示。三个原生 QPainter 图保留最多 500 点；资源次级展示；运行事件默认折叠且最多 2000 行。错误摘要保留第一因果技术文本，详情保留完整对象和 traceback。Abort 警告始终可见。

普通界面文案以简体中文为主，OpenFOAM/preCICE/ANCF/MPI/Slice/PID/CPU/RAM/Co/IQN-ILS/PIMPLE 和科学量名保留。状态机英文 token 加中文解释。文案在 ui 模块组织，业务日志和持久化 schema 不翻译。

## 视觉与收尾

浅色 tokens：background #F6F7F9、card #FFFFFF、primary text #1F2329、secondary text #626B78、muted #9AA0AA、border #E5E7EB、divider #EEF0F3、primary #1684FC、success #22A06B、warning text #A86C08、danger #D9485F。卡片圆角 14 px，按钮 9 px，输入 8 px；按 4/8/12/16/20/24/32 px 间距组织。没有渐变、图标包或新绘图库。

按人工 CONDITIONAL_PASS 的四条要求完成一轮收尾：

1. 检查各可见 scroll area，四种桌面尺寸的两页水平范围均为 0；另检查 PREPARED/RUNNING/FAILED 三种模拟状态在四尺寸下也无水平 overflow；空闲文件进度条隐藏，避免被误认为整体滚动条。文件操作时仍显示进度，未改变 worker 调度。
2. Participants/Exit 改为参与端/退出码，ANCF 单元和资源说明中文化；保留技术名和状态 token。
3. secondary 与图表辅助文字加深至 #626B78，不改变白色基调。
4. 底部操作区增加独立分隔与留白，没有覆盖或交叠 scroll 内容；按钮 gate 不变。

main_window.py 从 565 行降为 397 行，SetupPage / Navigation / widgets / strings 承担显示职责，没有新增框架。

字体使用宿主已有 fallback。本机缺少 Noto CJK，Qt 进程注册 Windows 已有 msyh.ttc，使用 Microsoft YaHei UI；不复制、安装、提交或分发字体。仍是 WSL/Linux + PySide6/WSLg 架构，未安装 Windows Python 或引入 Windows↔WSL 协议。

## 功能冻结与明确授权例外

`src/`、runner、monitor、models、production descriptor、依赖定义及原有测试文件均与 base 相同。prepared uniform symlink whitelist 和 bounded identity 完整保留；既有生产 generation/XML/Preflight 代码未改。RunState、command argv/cwd/environment/CPU masks、PID birth-time authentication、Abort own-tree、handshake、accepted progress、completion gate 和 provenance 不变。

唯一经用户明确授权的非显示层例外：在 `generator/validation.py` 与 `generator/production_validation.py` 的既有 APP_PROVENANCE branch tuple 中，各增加 `app/ui-ux-cn-v1`。否则独立新分支无法生成算例。没有删除原分支、扩大其他规则或改验证行为；人工 polish 阶段没有再次修改 validator。

两个历史真实案例只读核对：production_N5_gui_smoke5_v1 与 production_N5_app_smoke5 各 20 个 qualified uniform links，raw link text、exact target 和三类 metadata identity 与上一阶段记录一致。该核对限定在链接/metadata，不声称对全部历史 runtime 做全盘 byte identity。

## 测试

执行环境：Python 3.10 / PySide6 6.11.2，QT_QPA_PLATFORM=offscreen。所有 pytest 逐个会话运行，输出在 APP workspace。fake participant / dummy process 属于既有离线测试，不是生产求解器。

- 新增 UI：27 项，包括中文导航、两页切换、禁用 Results、真实生产参数锁定/Spec 等价、三种 FlowProfile wire value、全部 RunState 的按钮 gate、busy/Abort-request gate、现有 controller dispatch、参与端/指标、accepted-only progress 与 ETA、500 点边界、first-failure detail、日志访问、四尺寸无水平 overflow / footer 不交叠 / event loop。
- 收尾版本 smoke：85 PASS、60 deselected，212.99 s。未删除原 acceptance；跨 D: 文件系统的 case/hash 检查使该 suite 超过 30 s。
- 完整回归：145 PASS，0 failed / error / skipped，511.60 s；原有 118 项 + 新增 27 项全部通过。
- entrypoint：实际 viv_app module 启动 Qt event loop，测试仅给 QApplication 注入 500 ms 退出计时器，exit=0；未点生产操作。
- 开发期间两项纠正：测试文件写入命令的工作目录前缀修正；一项 UI 测试在打开运行页之前检查卡片可见，修正测试导航后通过。没有改变 solver 或削弱原 acceptance。

JUnit / layout / scope / read-only witness / entrypoint 原始小型证据在：
`/mnt/d/CFD_Work/APP/workspace/evidence/viv_app_ui_ux_cn_v1/`。

## 截图与人工审议

四张图为明确标识的 offline injected presentation data，未执行 Generate/Prepare/Run，不是生产 readiness 或真实运行证据：

- [Setup Production](workspace/evidence/viv_app_ui_ux_cn_v1/screenshots/ui-cn-setup-production.png)
- [PREPARED](workspace/evidence/viv_app_ui_ux_cn_v1/screenshots/ui-cn-run-ready.png)
- [RUNNING fake](workspace/evidence/viv_app_ui_ux_cn_v1/screenshots/ui-cn-run-active-fake.png)
- [FAILED fake](workspace/evidence/viv_app_ui_ux_cn_v1/screenshots/ui-cn-run-failed-fake.png)

每张 1440×1080；截图方法可通过 app/examples/capture_ui_cn.py 复现。尺寸/文件 SHA 和 data_source 见 screenshot_manifest.json。截图保存在 ignored workspace，不提交大图或 runtime；Git 提交可重复的截图脚本和小型 summary。

初次人工审议为 CONDITIONAL_PASS；四项 polish 已完成并重新提供四张截图。用户最终回复“可以收尾”，记录为 HUMAN_VISUAL_REVIEW = PASS。代理逐张检查和用户审议均已完成。

## 改动文件

- app/viv_app/main.py：显示品牌和统一 theme 入口。
- app/viv_app/ui/main_window.py：保留 controller，提取布局并本地化显示。
- app/viv_app/ui/setup_page.py：设置 cards、production readonly 展示和 workflow footer。
- app/viv_app/ui/run_page.py：运行 dashboard、failure details、三图和 advanced participants。
- app/viv_app/ui/navigation.py：两页导航与不可用 Results。
- app/viv_app/ui/widgets.py：轻量 Card / Disclosure / 只读 value / mode buttons / font fallback。
- app/viv_app/ui/strings.py：中文显示文案与稳定 technical tokens。
- app/viv_app/ui/theme.qss：浅色 tokens 和 spacing。
- app/viv_app/generator/validation.py、production_validation.py：仅授权 branch allowlist。
- app/tests/test_ui_cn.py、app/tests/fixtures/ui_preview.py：offline UI acceptance 与模拟显示数据。
- app/examples/capture_ui_cn.py：四张离线截图。
- app/README.md：中文操作说明、WSL 定位、既有运行合同与资格边界。
- APP_UI_UX_CN_V1_REPORT.md、app/resources/ui-ux-cn-v1-summary.json：报告与小型机器摘要。

## 边界与限制

本阶段不证明新的真实 GUI 执行资格。历史 GUI smoke 在 Prepare 阶段失败的 evidence 未改；修复 + UI + Run Manager 的真实联合执行尚待独立阶段。

布局通过 1280×800、1366×768、1440×900、1920×1080 的 offscreen 检查；小窗口允许纵向滚动。所有 Windows DPI/WSLg 组合、无中文字体的其他主机尚未逐一实机验证。技术错误/traceback 不强行翻译。未提供 CC Switch 图片附件，按请求文字中的设计语言实现，没有复制其 branding/assets。

REAL_CFD_STARTED = NO
REAL_DECOMPOSEPAR_STARTED = NO
PRODUCTION_SOLVER_CHANGED = NO

UI 原任务记录的下一阶段标签为 VIV_APP_GUI_N5_REAL_SMOKE_V2。用户随后另提出 VIV_APP_HH06_PARAMETRIC_FOUNDATION_V1，其要求从正式 UI_PASS_HEAD 和 clean worktree 开始。本次仅完成 UI 收尾，两者均未启动；没有 restart、Safe Stop、Results、后处理或长跑扩展。
