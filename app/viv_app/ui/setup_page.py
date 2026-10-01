"""Setup presentation. Reads existing baseline/spec values; never launches work."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox, QComboBox, QLabel, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QPlainTextEdit, QStackedWidget,
    QStyledItemDelegate, QAbstractSpinBox)
from viv_app.utils.paths import CASES_ROOT
from viv_app.models.simulation_spec import FlowProfile, uniform_positions
from viv_app.generator.production_baseline import PROFILE, POSITIONS
from .strings import FLOW_MODES, PLACEMENT_MODES, STRUCTURE_FIELDS
from .widgets import Card, SemanticCombo, FlowModes, RankValue, SliceStatus, Disclosure, label, refresh_style


def number(default, minimum, maximum):
    box = QDoubleSpinBox(); box.setDecimals(8); box.setRange(minimum, maximum)
    box.setValue(default); box.setSingleStep(.01)
    box.setButtonSymbols(QAbstractSpinBox.NoButtons)
    return box


class RatioDelegate(QStyledItemDelegate):
    """Compact paint text only; model text and editable precision are unchanged."""
    def displayText(self, value, locale):
        try: return f'{float(value):.6g}'
        except (ValueError, TypeError): return str(value)


class SetupPage(QWidget):
    # Explicit compatibility references used by the existing view/controller.
    REFERENCES = ('form_widget', 'case_name', 'profile_selector', 'baseline_path', 'browse', 'output_root',
        'initial_time', 'baseline_note', 'count', 'placement', 'ranks', 'interval_note', 'flow_type',
        'flow_values', 'flow_labels', 'structure_fields', 'structure_labels', 'damping', 'nodes',
        'dt', 'end', 'write', 'write_label', 'purge', 'preview', 'table', 'validation_label', 'error',
        'generate', 'validate', 'open_folder', 'preflight', 'prepare', 'load_case')

    def __init__(self):
        super().__init__(); self.baseline = None; self._updating = False
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 16, 24, 12); layout.setSpacing(12)
        row = QHBoxLayout(); row.addWidget(label('算例设置', 'pageTitle')); row.addStretch()
        row.addWidget(label('基于已审计算例生成 · 原始基准只读', 'secondary')); layout.addLayout(row)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.form_widget = QWidget(); self.form_widget.setObjectName('pageCanvas'); grid = QGridLayout(self.form_widget)
        grid.setContentsMargins(0, 0, 8, 0); grid.setHorizontalSpacing(16); grid.setVerticalSpacing(16)
        left = QVBoxLayout(); left.setSpacing(16); right = QVBoxLayout(); right.setSpacing(16)
        grid.addLayout(left, 0, 0); grid.addLayout(right, 0, 1); grid.setColumnStretch(0, 3); grid.setColumnStretch(1, 2)
        self.scroll.setWidget(self.form_widget); layout.addWidget(self.scroll, 1)

        self.info_card = Card('算例信息', '尚未审计'); left.addWidget(self.info_card)
        f = QGridLayout(); f.setHorizontalSpacing(12); f.setVerticalSpacing(8); self.info_card.content.addLayout(f)
        self.case_name = QLineEdit('VIV_N5_test')
        self.profile_selector = QComboBox(); self.profile_selector.addItems(['自定义基准 · 仅离线生成', 'V2606 N5 Production'])
        self.profile_selector.setItemData(1, PROFILE, Qt.ToolTipRole)
        f.addWidget(label('算例名称', 'secondary'), 0, 0); f.addWidget(label('计算配置', 'secondary'), 0, 1)
        f.addWidget(self.case_name, 1, 0); f.addWidget(self.profile_selector, 1, 1)
        self.baseline_path = QLineEdit(); self.baseline_path.setPlaceholderText('选择包含 app_baseline.json 的基准目录')
        self.browse = QPushButton('选择基准')
        path_row = QHBoxLayout(); path_row.setSpacing(8); path_row.addWidget(self.baseline_path, 1); path_row.addWidget(self.browse)
        path_content = QWidget(); path_form = QFormLayout(path_content); path_form.setContentsMargins(0, 0, 0, 0)
        path_form.addRow('基准目录', path_row)
        self.output_root = QLineEdit(str(CASES_ROOT)); self.output_root.setToolTip(str(CASES_ROOT))
        self.initial_time = QComboBox(); self.initial_display = label('—')
        self.initial_stack = QStackedWidget(); self.initial_stack.addWidget(self.initial_time); self.initial_stack.addWidget(self.initial_display)
        f.addWidget(label('初始状态时间', 'secondary'), 2, 0); f.addWidget(self.initial_stack, 2, 1)
        path_form.addRow('输出目录', self.output_root)
        self.paths_disclosure = Disclosure('基准与输出目录', path_content)
        self.paths_disclosure.toggle.setChecked(True); self.info_card.content.addWidget(self.paths_disclosure)
        self.baseline_note = label('请先选择并审计计算配置。', 'secondary'); self.baseline_note.setWordWrap(True)
        self.info_card.content.addWidget(self.baseline_note)

        flow_card = Card('来流条件'); left.addWidget(flow_card)
        self.flow_type = SemanticCombo(FLOW_MODES); self.flow_type.hide()
        flow_card.content.addWidget(self.flow_type); self.flow_modes = FlowModes(self.flow_type); flow_card.content.addWidget(self.flow_modes)
        self.flow_values = {}; self.flow_labels = {}; flow_form = QFormLayout(); flow_form.setVerticalSpacing(8)
        flow_card.content.addLayout(flow_form)
        for key, text, default, maximum in [('u0', 'U [m/s]', .31, 1000), ('u_bottom', 'U_bottom [m/s]', .31, 1000),
            ('u_top', 'U_top [m/s]', .31, 1000), ('transition', '分界位置 s/L', .45, 1),
            ('u_active', 'U_active [m/s]', .6, 1000), ('u_inactive', 'U_inactive [m/s]', 0, 1000)]:
            box = number(default, 0, maximum); self.flow_values[key] = box; self.flow_labels[key] = label(text)
            flow_form.addRow(self.flow_labels[key], box)

        self.slice_card = Card('Slice 配置'); left.addWidget(self.slice_card)
        controls = QWidget(); controls_layout = QHBoxLayout(controls); controls_layout.setContentsMargins(0, 0, 0, 0)
        self.slice_editors = controls
        self.count = QSpinBox(); self.count.setRange(1, 32); self.count.setValue(5)
        self.placement = SemanticCombo(PLACEMENT_MODES)
        self.ranks = QSpinBox(); self.ranks.setRange(1, 1024); self.ranks.setValue(4)
        for box in (self.count, self.ranks): box.setButtonSymbols(QAbstractSpinBox.NoButtons)
        for text, box in [('Slice 数量', self.count), ('位置', self.placement), ('MPI/片', self.ranks)]:
            column = QVBoxLayout(); column.addWidget(label(text, 'secondary')); column.addWidget(box); controls_layout.addLayout(column)
        self.slice_card.content.addWidget(controls)
        self.slice_locked = label('5 Slice · 每片 4 MPI · 位置已锁定', 'secondary'); self.slice_locked.hide()
        self.slice_card.content.addWidget(self.slice_locked)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['Slice', '位置 s [m]', 's/L', '状态', 'MPI', 'U [m/s]', 'Mesh source'])
        header = self.table.horizontalHeader(); header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Fixed); self.table.setColumnWidth(4, 86)
        header.moveSection(header.visualIndex(5), 3)
        header.moveSection(header.visualIndex(4), 4)
        self.table.setItemDelegateForColumn(2, RatioDelegate(self.table))
        self.table.setColumnHidden(6, True); self.table.verticalHeader().hide(); self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setShowGrid(False); self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(False); self.table.setMinimumHeight(120)
        self.table.setToolTip('所有 Slice 继承同一 baseline mesh；配置不会重建或缩放 mesh。')
        self.slice_card.content.addWidget(self.table)
        self.interval_note = label('均匀间距使用基准 active interval。', 'secondary'); self.interval_note.setWordWrap(True)
        self.slice_card.content.addWidget(self.interval_note); left.addStretch()

        self.structure_card = Card('结构模型', '尚未审计'); right.addWidget(self.structure_card)
        self.structure_fields = {}; self.structure_labels = {}; self.structure_values = {}
        form = QGridLayout(); form.setVerticalSpacing(10); self.structure_card.content.addLayout(form)
        # Existing not-wired editors remain read-only; visible values use labels.
        for i, (key, text, unit) in enumerate(STRUCTURE_FIELDS):
            field = QLineEdit('—'); field.setReadOnly(True); field.hide(); field.setParent(self)
            field.setToolTip('NOT YET WIRED：修改需要一致的 mesh 和结构初始平衡态。')
            self.structure_fields[key] = field
            self.structure_labels[key] = label(text, 'secondary'); self.structure_labels[key].setProperty('baseLabel', text)
            value = label('—'); value.setTextInteractionFlags(Qt.TextSelectableByMouse); self.structure_values[key] = value
            form.addWidget(self.structure_labels[key], i, 0); form.addWidget(value, i, 1, Qt.AlignRight)
        self.damping = number(0, 0, 1000); self.damping_display = label('—'); self.damping_stack = QStackedWidget()
        self.damping_stack.addWidget(self.damping); self.damping_stack.addWidget(self.damping_display)
        form.addWidget(label('结构阻尼 · Rayleigh α [1/s]', 'secondary'), 7, 0); form.addWidget(self.damping_stack, 7, 1)
        self.nodes = label('节点数由单元数推导。', 'secondary'); self.structure_card.content.addWidget(self.nodes)
        self.structure_notice = label('基础物理参数尚未接线；保留基准值。', 'secondary'); self.structure_notice.setWordWrap(True)
        self.structure_card.content.addWidget(self.structure_notice)

        self.numerics_card = Card('数值与并行'); right.addWidget(self.numerics_card)
        f = QFormLayout(); f.setVerticalSpacing(10); self.numerics_card.content.addLayout(f)
        self.dt = number(.0002, .000000001, 100); self.dt.setDecimals(9)
        self.dt_display = label('—'); self.dt_stack = QStackedWidget(); self.dt_stack.addWidget(self.dt); self.dt_stack.addWidget(self.dt_display)
        self.end = number(.2, .000000001, 1e9); self.write = number(.01, .000000001, 1e9)
        self.end.setToolTip('流体绝对时间，必须与初始状态之差构成整数个 coupling windows。')
        self.write_label = label('writeInterval'); self.purge = QSpinBox(); self.purge.setRange(0, 1000000); self.purge.setEnabled(False)
        self.purge.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.purge_label = label('purgeWrite')
        f.addRow('deltaT [s]', self.dt_stack); f.addRow('endTime [s]', self.end); f.addRow(self.write_label, self.write)
        f.addRow(self.purge_label, self.purge)
        self.numeric_notice = label('其余参数继承基准：PIMPLE、RBF、turbulence。', 'secondary'); self.numeric_notice.setWordWrap(True)
        self.numerics_card.content.addWidget(self.numeric_notice)

        overview = Card('算例摘要'); right.addWidget(overview)
        self.preview = QPlainTextEdit(); self.preview.setReadOnly(True); self.preview.setObjectName('preview')
        self.preview.setMaximumHeight(150); self.preview.document().setMaximumBlockCount(100)
        overview.content.addWidget(self.preview); right.addStretch()

        self.workflow_region = QWidget(); self.workflow_region.setObjectName('workflowRegion')
        footer = QVBoxLayout(self.workflow_region); footer.setContentsMargins(0, 8, 8, 0)
        self.workflow_card = Card('检查与生成'); footer.addWidget(self.workflow_card)
        layout.addWidget(self.workflow_region)
        self.workflow_card.title.setToolTip('生成算例 → 静态检查 → 运行前检查 → 准备计算 → 运行监控')
        status = QHBoxLayout(); self.validation_label = label('● 就绪', 'validation'); status.addWidget(self.validation_label, 1)
        self.load_case = QPushButton('选择已生成算例'); self.open_folder = QPushButton('打开算例目录'); self.open_folder.setEnabled(False)
        status.addWidget(self.load_case); status.addWidget(self.open_folder); self.workflow_card.content.addLayout(status)
        self.error = label('', 'error'); self.error.setWordWrap(True); self.error.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.error.setTextFormat(Qt.PlainText)
        self.error.setVisible(False); self.workflow_card.content.addWidget(self.error)
        buttons = QHBoxLayout(); buttons.setSpacing(8)
        self.generate = QPushButton('生成算例'); self.generate.setProperty('intent', 'primary')
        self.validate = QPushButton('静态检查'); self.preflight = QPushButton('运行前检查'); self.prepare = QPushButton('准备计算')
        self.view_run = QPushButton('进入运行监控')
        for b in (self.generate, self.validate, self.preflight, self.prepare, self.view_run): buttons.addWidget(b)
        for b in (self.validate, self.preflight, self.prepare, self.view_run): b.setEnabled(False)
        buttons.addStretch(); self.workflow_card.content.addLayout(buttons)
        self.workflow_stage = 'new'

    def production(self):
        return bool(self.baseline and self.baseline.descriptor.get('contract_profile') == PROFILE)

    def show_baseline(self, baseline):
        self.baseline = baseline; prod = self.production(); s = baseline.structure
        self.paths_disclosure.toggle.setChecked(not prod)
        self.info_card.badge.setText('已资格化 · N5' if prod else '仅离线生成'); self.info_card.badge.setProperty('tone', 'success' if prod else 'warning')
        refresh_style(self.info_card.badge)
        self.structure_card.badge.setText('Production 锁定' if prod else 'NOT YET WIRED')
        self.numerics_card.badge.setText('Production 锁定' if prod else '继承基准'); self.numerics_card.badge.show()
        self.slice_editors.setVisible(not prod); self.slice_locked.setVisible(prod)
        self.initial_stack.setCurrentIndex(1 if prod else 0); self.initial_display.setText(baseline.descriptor['initial_time_default'])
        self.dt_stack.setCurrentIndex(1 if prod else 0); self.dt_display.setText(f'{float(baseline.controls.scalar("deltaT")):g} s')
        self.damping_stack.setCurrentIndex(1 if prod else 0); self.damping_display.setText(f'{s.damping_alpha:g}')
        self.purge.setVisible(prod); self.purge_label.setVisible(prod)
        for key, text, unit in STRUCTURE_FIELDS:
            self.structure_values[key].setText(f'{getattr(s, key):g}' + (' ' + unit if unit else ''))
        self.structure_notice.setText('初始状态 P1_REF_NE32 · 保留已资格化结构与初态。' if prod else '基础物理参数 NOT YET WIRED；仅已接线的 Rayleigh α 可编辑。')
        self.numeric_notice.setText('当前 Production 配置的 deltaT 与 MPI 已锁定；其余数值参数继承基准。' if prod else '其余参数继承基准：fvSchemes、fvSolution、PIMPLE、RBF、turbulence。')

    def flow_profile(self):
        return FlowProfile(kind=self.flow_type.currentData(), **{k: b.value() for k, b in self.flow_values.items()})

    def flow_changed(self):
        visible = {'Uniform': {'u0'}, 'Linear Shear': {'u_bottom', 'u_top'}, 'Step Current': {'transition', 'u_active', 'u_inactive'}}[self.flow_type.currentData()]
        for key, box in self.flow_values.items():
            box.setVisible(key in visible); self.flow_labels[key].setVisible(key in visible)
        self.update_preview()

    def positions(self):
        return tuple(float(self.table.item(i, 2).text()) for i in range(self.table.rowCount()))

    def rebuild_table(self):
        self._updating = True; self.table.blockSignals(True); n = self.count.value()
        b = self.baseline; prod = self.production()
        positions = tuple(x/b.model.length_m for x in POSITIONS) if prod else uniform_positions(n, b.model.length_m, b.manifest.active_start_m, b.manifest.active_end_m) if b else uniform_positions(n, 1, 0, 1)
        length = b.model.length_m if b else 1; old = []
        if self.placement.currentIndex() == 1:
            try: old = list(self.positions())
            except (ValueError, AttributeError): pass
        self.table.setRowCount(n); self.table.setFixedHeight(min(9, n)*34+38)
        for i in range(n):
            x = old[i] if i < len(old) else positions[i]
            for col, text in [(0, f'S{i+1}' if prod else f'slice_{i:04d}'), (1, f'{x*length:.6g}'), (2, f'{x:.15g}'), (5, '—'), (6, 'baseline mesh')]:
                item = QTableWidgetItem(text); flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
                if col == 2 and self.placement.currentIndex() == 1 and not prod: flags |= Qt.ItemIsEditable
                item.setToolTip(text)
                item.setFlags(flags); self.table.setItem(i, col, item)
            enabled = SliceStatus(prod); enabled.stateChanged.connect(self.update_preview); self.table.setCellWidget(i, 3, enabled)
            rank = RankValue(self.ranks.value(), prod); rank.valueChanged.connect(self.update_preview); self.table.setCellWidget(i, 4, rank)
        self.table.blockSignals(False); self._updating = False; self.update_preview()

    def apply_ranks(self):
        for i in range(self.table.rowCount()):
            box = self.table.cellWidget(i, 4)
            if box: box.setValue(self.ranks.value())
        self.update_preview()

    def update_preview(self):
        if self._updating: return
        self.table.blockSignals(True)
        try:
            positions = self.positions(); flow = self.flow_profile(); b = self.baseline; length = b.model.length_m if b else 1
            total = 0
            for i, x in enumerate(positions):
                u = flow.velocity(x); rank = self.table.cellWidget(i, 4).value(); enabled = self.table.cellWidget(i, 3).isChecked()
                total += rank if enabled else 0; self.table.item(i, 1).setText(f'{x*length:.6g}'); self.table.item(i, 5).setText(f'{u:.6g}')
            lines = [f'算例  {self.case_name.text()}', f'{len(positions)} Slice · {FLOW_MODES[flow.kind]}', f'CFD MPI 总进程数  {total}']
            if b: lines.append(f'ANCF  {b.model.elements} 单元 / {6*b.structure.nodes} DOFs')
            lines.append('每片继承 baseline mesh')
            self.preview.setPlainText('\n'.join(lines))
        except (ValueError, AttributeError, TypeError) as exc:
            self.preview.setPlainText(f'Slice 表配置无效：{exc}')
        finally: self.table.blockSignals(False)

    def emphasize(self, stage):
        self.workflow_stage = stage
        primary = {'new': self.generate, 'generated': self.preflight, 'validated': self.preflight,
                   'preflight': self.prepare, 'prepared': self.view_run}.get(stage)
        for button in (self.generate, self.validate, self.preflight, self.prepare, self.view_run):
            button.setProperty('intent', 'primary' if button is primary else 'secondary'); refresh_style(button)
