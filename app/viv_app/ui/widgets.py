"""Small native Qt presentation components, without solver dependencies."""
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QComboBox, QSpinBox, QStackedWidget, QToolButton, QWidget, QCheckBox, QAbstractSpinBox)


def apply_theme(app):
    if app.property('vivLightThemeApplied'): return
    app.setStyle('Fusion')
    families = list(QFontDatabase.families())
    candidates = ['Noto Sans CJK SC', 'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI']
    # WSL may lack CJK fonts. Register the existing host font in this process
    # only: no copying, bundling, installing, or distributing any font file.
    if not any(f in families for f in candidates[:3]):
        host_font = Path('/mnt/c/Windows/Fonts/msyh.ttc')
        if host_font.is_file():
            QFontDatabase.addApplicationFont(str(host_font))
            families = list(QFontDatabase.families())
    font = QFont(next((f for f in candidates if f in families), app.font().family()))
    font.setPixelSize(13)
    app.setFont(font)
    app.setStyleSheet((Path(__file__).parent / 'theme.qss').read_text(encoding='utf-8'))
    app.setProperty('vivLightThemeApplied', True)


def label(text, role='body'):
    widget = QLabel(text)
    widget.setObjectName(role)
    return widget


def refresh_style(widget):
    widget.style().unpolish(widget); widget.style().polish(widget); widget.update()


class Card(QFrame):
    def __init__(self, title, badge='', parent=None):
        super().__init__(parent); self.setObjectName('card')
        self.content = QVBoxLayout(self); self.content.setContentsMargins(20, 16, 20, 16); self.content.setSpacing(12)
        row = QHBoxLayout(); row.setSpacing(12)
        self.title = label(title, 'cardTitle'); row.addWidget(self.title); row.addStretch()
        self.badge = label(badge, 'badge'); self.badge.setVisible(bool(badge)); row.addWidget(self.badge)
        self.content.addLayout(row)


class MetricCard(Card):
    def __init__(self, title, value='—', note='', parent=None):
        super().__init__(title, parent=parent)
        self.value = label(value, 'metricValue'); self.note = label(note, 'secondary')
        self.content.addWidget(self.value); self.content.addWidget(self.note)


class SemanticCombo(QComboBox):
    """Localized labels with stable wire values; legacy setters stay valid."""
    def __init__(self, choices, parent=None):
        super().__init__(parent); self.choices = choices
        for value, text in choices.items(): self.addItem(text, value)

    def setCurrentText(self, text):
        index = self.findData(text)
        if index >= 0: self.setCurrentIndex(index)
        else: super().setCurrentText(text)


class RankValue(QStackedWidget):
    """An editor for offline profiles, an intentional plain value when locked."""
    valueChanged = Signal(int)

    def __init__(self, value, locked=False):
        super().__init__(); self.editor = QSpinBox(); self.editor.setRange(1, 1024)
        self.editor.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.display = label(str(value)); self.display.setAlignment(Qt.AlignCenter)
        self.addWidget(self.editor); self.addWidget(self.display)
        self.editor.valueChanged.connect(self._changed); self.editor.setValue(value)
        self.setCurrentIndex(1 if locked else 0); self.setEnabled(not locked); self.setFixedWidth(76)

    def _changed(self, value):
        self.display.setText(str(value)); self.valueChanged.emit(value)

    def value(self): return self.editor.value()
    def setValue(self, value): self.editor.setValue(value)


class Disclosure(QWidget):
    def __init__(self, title, body, parent=None):
        super().__init__(parent); layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(8)
        self.toggle = QToolButton(); self.toggle.setText(title); self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon); self.toggle.setArrowType(Qt.RightArrow)
        layout.addWidget(self.toggle); layout.addWidget(body); body.hide()
        self.toggle.toggled.connect(body.setVisible)
        self.toggle.toggled.connect(lambda checked: self.toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow))


class SliceStatus(QStackedWidget):
    stateChanged = Signal(int)

    def __init__(self, locked=False):
        super().__init__(); self.editor = QCheckBox('启用'); self.editor.setChecked(True)
        self.display = label('启用', 'successText'); self.display.setAlignment(Qt.AlignCenter)
        self.addWidget(self.editor); self.addWidget(self.display)
        self.editor.stateChanged.connect(self.stateChanged)
        self.setCurrentIndex(1 if locked else 0); self.setEnabled(not locked)

    def isChecked(self): return self.editor.isChecked()
    def setChecked(self, value): self.editor.setChecked(value)


class FlowModes(QWidget):
    """Buttons select the existing combo; no flow algorithm lives here."""
    def __init__(self, combo):
        super().__init__(); self.combo = combo; self.buttons = []; row = QHBoxLayout(self); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(8)
        for i in range(combo.count()):
            button = QPushButton(combo.itemText(i)); button.setCheckable(True); button.setObjectName('segment')
            button.clicked.connect(lambda checked=False, index=i: self.choose(index))
            self.buttons.append(button); row.addWidget(button)
        combo.currentIndexChanged.connect(self.select); self.select(combo.currentIndex())

    def choose(self, index):
        self.combo.setCurrentIndex(index); self.select(index)

    def select(self, index):
        for i, button in enumerate(self.buttons): button.setChecked(i == index)
