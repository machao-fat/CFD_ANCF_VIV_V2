import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from viv_app.ui.main_window import MainWindow


def main():
    app=QApplication(sys.argv)
    app.setApplicationName('VIV Studio')
    from viv_app.ui.widgets import apply_theme
    apply_theme(app)
    window=MainWindow(); window.show()
    return app.exec()
