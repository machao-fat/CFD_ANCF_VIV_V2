import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from viv_app.ui.main_window import MainWindow


def main():
    app=QApplication(sys.argv)
    app.setApplicationName('VIV Case Generator')
    app.setStyle('Fusion')
    app.setStyleSheet((Path(__file__).parent/'ui/theme.qss').read_text(encoding='utf-8'))
    window=MainWindow(); window.show()
    return app.exec()
