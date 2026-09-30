from dataclasses import replace
import time
from pathlib import Path
import pytest
from PySide6.QtCore import QTimer,QEventLoop
from PySide6.QtWidgets import QApplication
from viv_app.ui.main_window import MainWindow
from viv_app.utils.paths import APP_ROOT


@pytest.fixture(scope='session')
def qt_app():
    app=QApplication.instance() or QApplication([])
    yield app
    # Always let IO workers finish, even when an assertion fails. Never tear a
    # parent window/QThread down during an active generation operation.
    for window in app.topLevelWidgets():
        if isinstance(window,MainWindow):
            if window.thread is not None:
                await_idle(window)
            window.close()
    app.processEvents()


def await_idle(window,timeout=60000):
    loop=QEventLoop()
    poll=QTimer(); poll.setInterval(10)
    expired=[]
    watchdog=QTimer(); watchdog.setSingleShot(True)
    watchdog.timeout.connect(lambda:(expired.append(True),loop.quit()))
    poll.timeout.connect(lambda:loop.quit() if window.thread is None else None)
    poll.start(); watchdog.start(timeout); loop.exec(); poll.stop(); watchdog.stop()
    assert not expired,f'GUI worker failed to finish within {timeout} ms; status={window.statusBar().currentMessage()}'


def test_gui_baseline_generation_and_timer_stays_responsive(qt_app,baseline_factory,tmp_path,monkeypatch):
    from viv_app.generator import fluid_generator
    original=fluid_generator.shutil.copyfile
    def slow_copy(*args,**kwargs):
        # Simulate modest IO latency in real copy calls, not a fake generator.
        time.sleep(.01)
        return original(*args,**kwargs)
    monkeypatch.setattr(fluid_generator.shutil,'copyfile',slow_copy)
    baseline=baseline_factory()
    window=MainWindow(); window.show()
    window.baseline_path.setText(str(baseline)); window.load_baseline(); await_idle(window)
    assert window.baseline is not None
    window.output_root.setText(str(tmp_path/'gui_output'))
    window.case_name.setText('gui_N5')
    window.count.setValue(5)
    window.flow_type.setCurrentText('Step Current')
    assert window.table.rowCount()==5
    qt_app.processEvents()
    assert window.table.cellWidget(0,4).width() <= window.table.columnWidth(4)
    assert float(window.table.item(0,5).text())==.6
    assert float(window.table.item(2,5).text())==0
    assert all(window.structure_fields[x].isReadOnly() for x in window.structure_fields)
    beats=[]; timer=QTimer(); timer.setInterval(15); timer.timeout.connect(lambda:beats.append(time.monotonic()))
    timer.start(); window.start_generation()
    assert window.thread is not None and not window.generate.isEnabled()
    await_idle(window); timer.stop()
    assert len(beats)>=10,'GUI event loop did not advance during actual generation'
    assert window.generated and window.generated.is_dir()
    assert 'PASS' in window.validation_label.text()
    assert not window.error.text()
    assert window.generate.isEnabled() and window.validate.isEnabled()
    window.start_validation(); await_idle(window)
    assert 'PASS' in window.validation_label.text()
    window.close()


def test_gui_custom_table_realtime_flow_and_rank_override(qt_app,baseline_factory):
    window=MainWindow()
    window.baseline_path.setText(str(baseline_factory())); window.load_baseline(); await_idle(window)
    window.count.setValue(5); window.placement.setCurrentText('Custom positions')
    window.table.item(0,2).setText('0.05')
    window.flow_type.setCurrentText('Linear Shear')
    window.flow_values['u_bottom'].setValue(0); window.flow_values['u_top'].setValue(1)
    window.table.cellWidget(0,4).setValue(7)
    assert float(window.table.item(0,5).text())==.05
    assert float(window.table.item(0,1).text())==.5
    assert window.simulation_spec().mpi_ranks[0]==7
    window.close()


def test_gui_unknown_baseline_reports_fail(qt_app,tmp_path):
    window=MainWindow(); window.baseline_path.setText(str(tmp_path))
    window.load_baseline(); await_idle(window)
    assert window.baseline is None
    assert 'GENERATION_BLOCKED_BY_UNKNOWN_CONTRACT' in window.error.text()
    assert 'FAIL' in window.validation_label.text()
    window.close()
