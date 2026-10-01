from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton
from .widgets import label


class Navigation(QFrame):
    currentRowChanged = Signal(int)

    def __init__(self):
        super().__init__(); self.setObjectName('navigation'); self.setFixedWidth(172); self._row = -1
        layout = QVBoxLayout(self); layout.setContentsMargins(12, 20, 12, 16); layout.setSpacing(8)
        layout.addWidget(label('工作空间', 'navSection'))
        self.buttons = []
        for i, text in enumerate(['算例设置', '运行监控', '结果分析 · 尚未开放']):
            button = QPushButton(text); button.setObjectName('navItem'); button.setCheckable(i < 2)
            button.setEnabled(i < 2); button.clicked.connect(lambda checked=False, index=i: self.setCurrentRow(index))
            self.buttons.append(button); layout.addWidget(button)
        layout.addStretch(); layout.addWidget(label('CFD · preCICE · ANCF', 'secondary'))

    def setCurrentRow(self, row):
        if row not in (0, 1): return
        for i, button in enumerate(self.buttons[:2]): button.setChecked(i == row)
        if row != self._row:
            self._row = row; self.currentRowChanged.emit(row)

    def currentRow(self): return self._row
