"""Render offline UI fixtures only. No Generate/Prepare/Run command is clicked."""
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QEvent
import importlib.util
import json
from PySide6.QtWidgets import QApplication
from viv_app.ui.main_window import MainWindow
from viv_app.runner.state import RunState
from viv_app.utils.paths import APP_ROOT


def capture():
    output = APP_ROOT/'workspace/evidence/viv_app_ui_ux_cn_v1/screenshots'; output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('ui_preview', APP_ROOT/'app/tests/fixtures/ui_preview.py')
    data = importlib.util.module_from_spec(spec); spec.loader.exec_module(data)
    app = QApplication.instance() or QApplication([]); window = MainWindow(); window.runner_timer.stop()
    window.resize(1440, 1080); window.demo_badge.show(); view = data.production_view(output.parent)
    window.baseline_path.setText(str(view.root)); window.baseline_loaded(view)
    window.case_name.setText('production_N5_ui_preview'); window.validation_label.setText('✓ 已加载资格化配置 · 尚未生成算例')
    window.show(); app.processEvents()
    names = []
    def save(name):
        app.processEvents(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete); app.processEvents()
        assert window.grab().save(str(output/name)); names.append(name)
    save('ui-cn-setup-production.png')
    manager = data.PreviewManager(output.parent); window.run_manager = manager; window.generated = manager.root
    window.navigation.setCurrentRow(1); window.run_page.case.setText('production_N5_ui_preview · 离线展示，未启动求解器')
    window.run_page.show_snapshot(data.snapshot(0, 'PREPARED')); window.refresh_run_controls(); window.runner_state('PREPARED')
    save('ui-cn-run-ready.png')
    manager.state = RunState.RUNNING; manager.busy = True
    window.run_page.show_snapshot(data.snapshot(3)); window.runner_state('RUNNING'); window.refresh_run_controls()
    save('ui-cn-run-active-fake.png')
    manager.state = RunState.FAILED; manager.busy = False
    window.run_page.show_snapshot(data.snapshot(0, 'FAILED')); window.runner_state('FAILED')
    window.run_page.show_failure({'phase': 'prepare', 'reason': 'OFFLINE DEMO: 未通过输入身份检查（展示数据）',
        'traceback': 'OFFLINE FAKE TRACEBACK — preserved detail example'})
    window.refresh_run_controls(); save('ui-cn-run-failed-fake.png')
    # Fixture manager has no processes; never exercise the production close/Abort path.
    window.run_manager = None; window.close(); app.processEvents()
    (output.parent/'screenshot_manifest.json').write_text(json.dumps({'real_cfd_started': False, 'real_decomposepar_started': False,
        'data_source': 'EXPLICIT_OFFLINE_UI_FIXTURE', 'screenshots': names, 'size': [1440, 1080]}, indent=2)+'\n')
    print(output)


if __name__ == '__main__': capture()
