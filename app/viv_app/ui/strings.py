"""Simplified Chinese presentation vocabulary; wire tokens remain unchanged."""
PRODUCT = 'VIV Studio'
SUBTITLE = 'CFD–ANCF 柔性立管涡激振动仿真平台'
FLOW_MODES = {'Uniform': '均匀流', 'Linear Shear': '线性剪切流', 'Step Current': '阶梯流'}
PLACEMENT_MODES = {'Uniform spacing': '均匀间距', 'Custom positions': '自定义位置'}
STATES = {
    'CREATED': '等待检查与准备', 'VALIDATED': '静态检查通过', 'PREFLIGHT_PASSED': '运行前检查通过',
    'PREPARING': '正在准备计算', 'PREPARED': '准备完成，可以开始计算', 'STARTING': '正在启动参与端',
    'HANDSHAKING': '等待六个参与端连接', 'RUNNING': '正在计算', 'COMPLETED': '计算自然完成',
    'FAILED': '计算失败，请查看首个错误', 'ABORTING': '正在终止本次计算', 'ABORTED': '计算已终止',
}
PARTICIPANT_STATES = {'WAITING': '等待', 'STARTING': '启动中', 'CONNECTED': '已连接', 'RUNNING': '运行中',
                      'EXITED': '已退出', 'FAILED': '失败', 'ABORTED': '已终止'}
METRICS = {'Physical Time': '物理时间', 'Coupled elapsed': '已接受耦合时长', 'Accepted Windows': '已接受窗口',
           'Current Coupling Iteration': '当前耦合迭代', 'Force Residual': 'Force residual（力残差）',
           'Displacement Residual': 'Displacement residual（位移残差）', 'Rejected / Rollbacks': '回滚次数',
           'Elapsed Wall Time': '已运行时间', 'ETA · ESTIMATE': 'ETA · ESTIMATE',
           'GLOBAL MAX Co': '最大 Co', 'GLOBAL MAX mesh Co': '最大 Mesh Co', 'Current Window': '当前窗口'}
STRUCTURE_FIELDS = [('diameter_m', '直径 D', 'm'), ('length_m', '长度 L', 'm'), ('ea_n', 'EA', 'N'),
                    ('ei_nm2', 'EI', 'N m²'), ('mass_per_length', '线质量', 'kg/m'),
                    ('pretension_n', '预张力', 'N'), ('elements', 'ANCF 单元数', '')]
ABORT_NOTICE = '终止计算不是 checkpoint-safe stop，终止后的算例当前不保证可继续计算。'


def state_description(token):
    return STATES.get(token, token)


def event_text(event):
    """Translate only the presentation envelope; preserve causal diagnostics."""
    kind, name, value = event['event_type'], event['participant'], event['value']
    if kind == 'accepted_window':
        return f"窗口 {event['window']} 已接受 · {event['iteration']} 次迭代"
    if kind == 'participant_started': return f'{name} 已启动'
    if kind == 'participant_connected': return f'{name} 已连接'
    if kind == 'participant_exit': return f'{name} 已退出 · exit={value["exit_code"]}'
    if kind == 'prepared_slice': return f'{name} 准备完成 · {value}'
    if kind == 'preflight_passed': return '运行前检查通过 · PASS'
    if kind == 'run_state': return f'{value} · {state_description(value)}'
    if kind == 'fatal': return f'{name} · 错误 · {value.get("reason", str(value)) if isinstance(value, dict) else value}'
    if kind == 'warning': return f'{name} · 提示 · {value}'
    return f'{name} · {kind} · {value}'
