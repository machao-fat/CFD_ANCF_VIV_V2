"""Light Qt monitor view. All metrics come from the unchanged Run Manager."""
import json
import math
from PySide6.QtCore import Qt, QUrl, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QPolygonF, QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar, QScrollArea,
    QPlainTextEdit, QDialog)
from .widgets import Card, MetricCard, Disclosure, label
from .strings import METRICS, PARTICIPANT_STATES, ABORT_NOTICE, state_description


class HistoryPlot(QWidget):
    def __init__(self, title, index, parent=None):
        super().__init__(parent); self.title = title; self.index = index; self.history = []
        self.setMinimumHeight(136)

    def set_history(self, history):
        self.history = list(history[-500:]); self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor('#626B78')); p.drawText(12, 20, self.title)
        left, top, right, bottom = 60, 36, self.width()-20, self.height()-28
        p.setPen(QPen(QColor('#E5E7EB'), 1)); p.drawLine(left, bottom, right, bottom); p.drawLine(left, top, left, bottom)
        points = [(row[0], row[self.index]) for row in self.history if isinstance(row[self.index], (int, float)) and math.isfinite(row[self.index])]
        if not points:
            p.setPen(QColor('#727B88')); p.drawText(left+8, top+30, '等待已接受窗口'); return
        lo = min(y for x, y in points); hi = max(y for x, y in points); span = max(hi-lo, 1e-10)
        xmin = points[0][0]; xspan = max(1, points[-1][0]-xmin)
        polygon = QPolygonF([QPointF(left+(x-xmin)/xspan*(right-left), bottom-(y-lo)/span*(bottom-top)) for x, y in points])
        p.setPen(QPen(QColor('#1684FC'), 1.8)); p.drawPolyline(polygon)
        for point in polygon: p.drawEllipse(point, 2, 2)
        p.setPen(QColor('#626B78')); p.drawText(2, top+8, f'{hi:.2g}'); p.drawText(2, bottom, f'{lo:.2g}')
        p.drawText(left, bottom+20, str(xmin)); p.drawText(right-22, bottom+20, str(points[-1][0]))


def format_number(value):
    return '—' if value is None else f'{value:.6g}' if isinstance(value, (float, int)) else str(value)


def wall_time(seconds):
    seconds = max(0, int(seconds)); hours, remainder = divmod(seconds, 3600); minutes, seconds = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes:02d}:{seconds:02d}'


class RunPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.manager = None; self.records = {}; self._failure_data = None
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 16, 24, 12); layout.setSpacing(12)
        header = QHBoxLayout(); title = QVBoxLayout(); title.setSpacing(4)
        title.addWidget(label('运行监控', 'pageTitle'))
        self.case = label('请在算例设置中生成或选择未运行的 Production 算例。', 'secondary')
        self.case.setWordWrap(True); self.case.setTextInteractionFlags(Qt.TextSelectableByMouse); title.addWidget(self.case)
        header.addLayout(title, 1); self.run = QPushButton('▶ 开始计算'); self.run.setProperty('intent', 'primary'); self.run.setEnabled(False)
        self.abort = QPushButton('终止计算'); self.abort.setProperty('intent', 'danger'); self.abort.setEnabled(False)
        header.addWidget(self.run); header.addWidget(self.abort); layout.addLayout(header)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(); content.setObjectName('pageCanvas'); body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 8, 0); body.setSpacing(16); self.scroll.setWidget(content); layout.addWidget(self.scroll, 1)
        self.failure_panel = Card('计算失败'); self.failure_panel.setObjectName('failureCard')
        self.failure = label('', 'error'); self.failure.setWordWrap(True); self.failure.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.failure.setTextFormat(Qt.PlainText)
        self.failure_panel.content.addWidget(self.failure)
        self.failure_details = QPushButton('查看详细信息'); self.failure_details.clicked.connect(self.open_failure_details)
        self.failure_panel.content.addWidget(self.failure_details, 0, Qt.AlignLeft); body.addWidget(self.failure_panel); self.failure_panel.hide()
        cards = QHBoxLayout(); cards.setSpacing(12); self.metrics = {}
        self.state_card = MetricCard('运行状态', 'CREATED', state_description('CREATED')); self.state = self.state_card.value
        cards.addWidget(self.state_card, 1)
        for key in ['Accepted Windows', 'Physical Time', 'Elapsed Wall Time']:
            card = MetricCard(METRICS[key]); self.metrics[key] = card.value; cards.addWidget(card, 1)
        body.addLayout(cards)
        center = QHBoxLayout(); center.setSpacing(16)
        coupling = Card('耦合计算'); center.addWidget(coupling, 3)
        grid = QGridLayout(); grid.setHorizontalSpacing(16); grid.setVerticalSpacing(12); coupling.content.addLayout(grid)
        for i, key in enumerate(['Current Window', 'Current Coupling Iteration', 'Rejected / Rollbacks', 'Force Residual',
                                'Displacement Residual', 'GLOBAL MAX Co', 'GLOBAL MAX mesh Co']):
            cell = QVBoxLayout(); cell.setSpacing(4); cell.addWidget(label(METRICS[key], 'secondary'))
            value = label('—', 'couplingValue'); cell.addWidget(value); self.metrics[key] = value; grid.addLayout(cell, i//3, i%3)
        self.progress_label = label('耦合计算进度 · 等待准备完成', 'secondary'); coupling.content.addWidget(self.progress_label)
        self.progress = QProgressBar(); self.progress.setRange(0, 10000); self.progress.setFormat('%p%'); coupling.content.addWidget(self.progress)
        timing = QHBoxLayout(); self.metrics['Coupled elapsed'] = label('—', 'secondary'); self.metrics['ETA · ESTIMATE'] = label('预热中 / 暂不可用', 'secondary')
        timing.addWidget(self.metrics['Coupled elapsed'], 1); timing.addWidget(self.metrics['ETA · ESTIMATE']); coupling.content.addLayout(timing)
        participant_card = Card('参与端', '6 个参与端'); center.addWidget(participant_card, 2)
        self.participants = QTableWidget(6, 4); self.participants.setHorizontalHeaderLabels(['参与端', '状态', 'PID', '退出码'])
        self.participants.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.participants.verticalHeader().hide()
        self.participants.verticalHeader().setDefaultSectionSize(32); self.participants.setFixedHeight(236); self.participants.setShowGrid(False)
        self.participants.setEditTriggers(QTableWidget.NoEditTriggers); self.participants.setColumnHidden(2, True); self.participants.setColumnHidden(3, True)
        for i, name in enumerate(['Structure', *[f'Fluid-S{j}' for j in range(1, 6)]]):
            for j, text in enumerate([name, '● 等待', '—', '—']): self.participants.setItem(i, j, QTableWidgetItem(text))
        self.participants.cellDoubleClicked.connect(self.open_log); participant_card.content.addWidget(self.participants)
        self.participants.setToolTip('双击参与端打开完整 stdout 日志；stderr 与运行证据保留在算例目录。')
        self.participant_details = QPlainTextEdit(); self.participant_details.setReadOnly(True); self.participant_details.setMaximumHeight(160)
        self.participant_details.document().setMaximumBlockCount(250)
        self.advanced = Disclosure('高级信息 · PID / 路径 / 日志', self.participant_details); participant_card.content.addWidget(self.advanced)
        body.addLayout(center)
        plots = QHBoxLayout(); plots.setSpacing(12); self.plots = []
        for text, index in [('Force residual', 1), ('Displacement residual', 2), ('Max Co', 3)]:
            card = Card(text); plot = HistoryPlot('横轴：已接受窗口', index); card.content.addWidget(plot)
            self.plots.append(plot); plots.addWidget(card)
        body.addLayout(plots)
        resource_card = Card('资源', '仅本次管理器启动的求解器进程'); self.resources = label('等待轻量 CPU / RAM 采样。', 'secondary')
        self.resources.setWordWrap(True); resource_card.content.addWidget(self.resources); body.addWidget(resource_card)
        self.notice = label('运行使用已保存算例，不使用尚未生成的设置更改。\n'+ABORT_NOTICE, 'secondary')
        self.notice.setWordWrap(True); layout.addWidget(self.notice); body.addStretch()

    def show_state(self, token):
        self.state.setText(token); self.state_card.note.setText(state_description(token))

    def reset_view(self):
        for value in self.metrics.values(): value.setText('—')
        self.show_participants({}); self.progress.setValue(0); self.show_state('CREATED'); self.clear_failure()
        self.progress_label.setText('耦合计算进度 · 等待准备完成')
        self.resources.setText('等待轻量 CPU / RAM 采样。')
        for plot in self.plots: plot.set_history([])

    def clear_failure(self):
        self._failure_data = None; self.failure.clear(); self.failure_panel.hide()

    def show_failure(self, value, participant=''):
        self._failure_data = value
        reason = value.get('reason', str(value)) if isinstance(value, dict) else str(value)
        phase = value.get('phase') if isinstance(value, dict) else None
        self.failure_panel.title.setText('计算准备失败' if phase == 'prepare' else '计算失败')
        self.failure.setText((participant+' · ' if participant else '')+reason[:600]); self.failure_panel.show()

    def open_failure_details(self):
        dialog = QDialog(self); dialog.setWindowTitle('首个错误 · 详细信息'); dialog.resize(800, 480)
        box = QVBoxLayout(dialog); detail = QPlainTextEdit(); detail.setReadOnly(True)
        detail.setPlainText(json.dumps(self._failure_data, indent=2, ensure_ascii=False) if isinstance(self._failure_data, dict) else str(self._failure_data))
        box.addWidget(detail); close = QPushButton('关闭'); close.clicked.connect(dialog.accept); box.addWidget(close, 0, Qt.AlignRight)
        dialog.exec()

    def open_log(self, row, column):
        name = self.participants.item(row, 0).text(); record = self.records.get(name)
        if record: QDesktopServices.openUrl(QUrl.fromLocalFile(record['stdout_log']))

    def show_snapshot(self, s):
        values = {'Physical Time': f"{s['physical_time']:.6f} s", 'Coupled elapsed': f"耦合时长 {s['coupled_elapsed']:.6f} / {s['target_duration']:.6f} s",
            'Accepted Windows': f"{s['accepted_windows']} / {s['target_windows']}", 'Current Window': str(s['window']),
            'Current Coupling Iteration': str(s['iteration']), 'Force Residual': format_number(s['force_residual']),
            'Displacement Residual': format_number(s['displacement_residual']), 'Rejected / Rollbacks': str(s['rollback_count']),
            'Elapsed Wall Time': wall_time(s['elapsed_wall_s']),
            'ETA · ESTIMATE': f"ETA {s['eta_estimate_s']:.0f} s · ESTIMATE" if s['eta_estimate_s'] is not None else 'ETA 预热中 / 暂不可用（<20 窗）',
            'GLOBAL MAX Co': f"{format_number(s['max_Co'])} · {s['max_Co_slice'] or '—'}",
            'GLOBAL MAX mesh Co': f"{format_number(s['max_mesh_Co'])} · {s['max_mesh_Co_slice'] or '—'}"}
        for key, value in values.items(): self.metrics[key].setText(value)
        self.progress_label.setText(f"耦合计算进度 · 已接受窗口 {s['accepted_windows']} / {s['target_windows']}")
        self.metrics['Physical Time'].setToolTip(f"目标物理时间：{s['target_physical_time']:.6f} s")
        self.progress.setValue(round(10000*s['progress']))
        for plot in self.plots: plot.set_history(s['history'])
        self.show_participants(s.get('participants', {})); self.show_state(s.get('state', 'CREATED'))
        r = s.get('resources')
        if r:
            self.resources.setText(f"求解器 CPU  {r['solver_cpu_percent']:.1f}%（跨核合计）  ·  求解器 RSS  {r['solver_rss_bytes']/2**20:.1f} MiB  ·  系统 CPU  {r['system_cpu_percent']:.1f}%  ·  系统 RAM  {r['system_ram_percent']:.1f}%  ·  磁盘剩余  {r['disk_free_bytes']/2**30:.1f} GiB")

    def show_participants(self, records):
        self.records = records
        colors = {'WAITING': '#9AA0AA', 'STARTING': '#1684FC', 'CONNECTED': '#1684FC', 'RUNNING': '#1684FC',
                  'EXITED': '#22A06B', 'FAILED': '#D9485F', 'ABORTED': '#A86C08'}
        self.participants.setColumnHidden(3, not any(r.get('exit_code') is not None for r in records.values()))
        for i in range(6):
            name = self.participants.item(i, 0).text(); r = records.get(name, {}); status = r.get('status', 'WAITING')
            self.participants.item(i, 1).setText('● '+PARTICIPANT_STATES.get(status, status))
            self.participants.item(i, 1).setForeground(QColor(colors.get(status, '#9AA0AA')))
            self.participants.item(i, 1).setToolTip(status)
            self.participants.item(i, 2).setText(str(r.get('PID', '—')))
            self.participants.item(i, 3).setText('—' if r.get('exit_code') is None else str(r['exit_code']))
        self.participant_details.setPlainText(json.dumps(records, indent=2, ensure_ascii=False))
