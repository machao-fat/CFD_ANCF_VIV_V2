"""UI-only acceptance: injected views/managers, never production execution."""
import importlib.util
import pytest
from PySide6.QtCore import QTimer, QEventLoop
from PySide6.QtWidgets import QApplication, QLabel
from viv_app.ui.main_window import MainWindow
from viv_app.runner.state import RunState, ACTIVE
from viv_app.monitor.run_monitor import RunMonitor
from viv_app.monitor.models import MonitorEvent
from viv_app.generator.production_baseline import POSITIONS, STRUCTURE
from viv_app.utils.paths import APP_ROOT

spec = importlib.util.spec_from_file_location('ui_preview', APP_ROOT/'app/tests/fixtures/ui_preview.py')
preview = importlib.util.module_from_spec(spec); spec.loader.exec_module(preview)


@pytest.fixture
def window(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('UI-only test attempted production work')
    for name in ('generate_case', 'production_preflight', 'RunManager'):
        monkeypatch.setattr('viv_app.ui.main_window.'+name, forbidden)
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.runner_timer.stop(); w.show(); app.processEvents()
    yield w
    w.run_manager = None; w.close(); app.processEvents()


@pytest.mark.smoke
def test_chinese_shell_navigation_and_unavailable_results(window):
    w = window
    assert w.windowTitle() == 'VIV Studio'
    texts = {item.text() for item in w.findChildren(QLabel)}
    assert 'CFD–ANCF 柔性立管涡激振动仿真平台' in texts
    assert '算例设置' in texts and '运行监控' in texts
    assert w.pages.count() == 2
    w.navigation.buttons[1].click(); assert w.pages.currentIndex() == 1
    w.navigation.buttons[0].click(); assert w.pages.currentIndex() == 0
    assert not w.navigation.buttons[2].isEnabled()
    w.navigation.buttons[2].click(); w.navigation.setCurrentRow(2)
    assert w.pages.currentIndex() == 0 and w.run_manager is None


@pytest.mark.smoke
def test_production_locked_summary_and_spec_identical(window, tmp_path):
    b = preview.production_view(tmp_path); window.baseline_path.setText(str(b.root)); window.baseline_loaded(b)
    assert all(not box.isEnabled() for box in [window.count, window.ranks, window.placement, window.dt, window.initial_time, window.damping])
    assert all(field.isReadOnly() for field in window.structure_fields.values())
    assert window.setup_page.dt_stack.currentIndex() == 1 and window.setup_page.initial_stack.currentIndex() == 1
    assert not window.setup_page.slice_editors.isVisible()
    assert all(window.table.cellWidget(i, 4).currentIndex() == 1 and not window.table.cellWidget(i, 4).isEnabled() for i in range(5))
    result = window.simulation_spec()
    assert result.structure == STRUCTURE and result.delta_t == .0004 and result.mpi_ranks == (4,)*5
    assert result.initial_state_time == b.descriptor['initial_time_default']
    assert result.positions_over_l == tuple(float(f'{x/STRUCTURE.length_m:.15g}') for x in POSITIONS)
    assert window.setup_page.structure_values['diameter_m'].text() == '0.028 m'
    assert window.structure_fields['diameter_m'].isHidden()
    assert window.table.item(0, 2).text() == f'{POSITIONS[0]/STRUCTURE.length_m:.15g}'


@pytest.mark.smoke
@pytest.mark.parametrize('index,wire,keys', [(0,'Uniform',{'u0'}),(1,'Linear Shear',{'u_bottom','u_top'}),
                                          (2,'Step Current',{'transition','u_active','u_inactive'})])
def test_localized_flow_modes_preserve_wire_values(index, wire, keys, window):
    buttons = window.setup_page.flow_modes.buttons
    buttons[index].click(); buttons[index].click()
    assert sum(button.isChecked() for button in buttons) == 1
    assert window.flow_profile().kind == wire
    assert {key for key, box in window.flow_values.items() if not box.isHidden()} == keys
    window.flow_type.setCurrentText(wire); assert window.flow_type.currentData() == wire


@pytest.mark.smoke
@pytest.mark.parametrize('state', list(RunState))
def test_button_gates_and_state_cards_match_original_contract(state, window, tmp_path):
    busy = state in ACTIVE
    manager = preview.PreviewManager(tmp_path, state, busy); window.run_manager = manager; window.generated = manager.root
    window.runner_state(state.value); window.refresh_run_controls()
    assert window.prepare.isEnabled() == (state == RunState.CREATED and not busy)
    assert window.run_page.run.isEnabled() == (state == RunState.PREPARED and not busy)
    assert window.run_page.abort.isEnabled() == (busy and state in ACTIVE and state != RunState.ABORTING)
    assert window.run_page.state.text() == state.value
    assert window.run_page.state_card.note.text() and manager.calls == []


@pytest.mark.smoke
def test_worker_and_abort_requested_disable_actions(window, tmp_path):
    manager = preview.PreviewManager(tmp_path); window.run_manager = manager
    window.thread = object(); window.refresh_run_controls()
    assert not window.run_page.run.isEnabled() and not window.prepare.isEnabled()
    window.thread = None; manager.state = RunState.RUNNING; manager.busy = True; manager.abort_requested.set()
    window.refresh_run_controls(); assert not window.run_page.abort.isEnabled()
    assert manager.calls == []


@pytest.mark.smoke
def test_localized_actions_dispatch_existing_controller_only(window, tmp_path):
    manager = preview.PreviewManager(tmp_path, RunState.CREATED); window.run_manager = manager; window.refresh_run_controls()
    window.prepare.click(); assert manager.calls == ['prepare']
    manager.state = RunState.PREPARED; window.refresh_run_controls(); window.run_page.run.click()
    assert manager.calls[-1] == 'run' and window.navigation.currentRow() == 1
    manager.state = RunState.RUNNING; manager.busy = True; window.refresh_run_controls(); window.run_page.abort.click()
    assert manager.calls[-1] == 'abort' and not window.run_page.abort.isEnabled()


@pytest.mark.smoke
def test_snapshots_metrics_participants_resources_and_bounded_plots(window):
    page = window.run_page; data = preview.snapshot(); page.show_snapshot(data)
    assert page.metrics['Accepted Windows'].text() == '3 / 5'
    assert page.metrics['Physical Time'].text() == '30.001200 s'
    assert page.metrics['Current Window'].text() == '4'
    assert page.metrics['Current Coupling Iteration'].text() == '2'
    assert page.metrics['Rejected / Rollbacks'].text() == '9'
    assert page.metrics['Force Residual'].text() == '0.0012'
    assert page.metrics['Displacement Residual'].text() == '0.0006'
    assert page.metrics['Elapsed Wall Time'].text() == '00:42'
    assert page.progress.value() == 6000 and '预热中' in page.metrics['ETA · ESTIMATE'].text()
    assert '0.88' in page.metrics['GLOBAL MAX Co'].text() and 'Fluid-S5' in page.metrics['GLOBAL MAX Co'].text()
    assert '1260.0%' in page.resources.text() and '920.0 MiB' in page.resources.text()
    assert page.participants.isColumnHidden(2) and not page.advanced.toggle.isChecked()
    assert page.participants.item(1, 1).text() == '● 运行中' and 'OFFLINE' in page.participant_details.toPlainText()
    page.plots[0].set_history([(i, .1, .2, .3) for i in range(2000)]); assert len(page.plots[0].history) == 500
    before = page.progress.value(); data['iteration'] = 20; page.show_snapshot(data)
    assert page.progress.value() == before


@pytest.mark.smoke
def test_progress_and_eta_only_reflect_existing_monitor(window):
    clock = [0.]; monitor = RunMonitor(30, .0004, 30, clock=lambda: clock[0])
    monitor.consume(MonitorEvent('rejected_attempt', 'Structure', window=1, iteration=1))
    window.run_page.show_snapshot(monitor.snapshot()); assert window.run_page.progress.value() == 0
    for w in range(1, 21):
        clock[0] += 2
        monitor.consume(MonitorEvent('accepted_window', 'Structure', 30+w*.0004, w, 3, {'force_residual': .001, 'displacement_residual': .002}))
        window.run_page.show_snapshot(monitor.snapshot())
        if w < 20: assert '预热中' in window.run_page.metrics['ETA · ESTIMATE'].text()
    assert '20 s' in window.run_page.metrics['ETA · ESTIMATE'].text()
    assert window.run_page.progress.value() == round(10000*20/30)


@pytest.mark.smoke
def test_failure_retains_first_details_and_evidence_semantics(window, tmp_path):
    manager = preview.PreviewManager(tmp_path, RunState.FAILED); window.run_manager = manager
    window.navigation.setCurrentRow(1)
    data = {'phase': 'prepare', 'reason': 'TEST_ONLY: missing required initial field <U>', 'traceback': 'FULL FAKE TRACEBACK'}
    window.runner_finished({'state': 'FAILED', 'first_failure': data})
    assert window.run_page.failure.text() == data['reason'] and window.run_page.failure_panel.isVisible()
    assert window.run_page._failure_data == data and window.run_page.failure_panel.title.text() == '计算准备失败'
    assert not window.run_page.run.isEnabled() and manager.state == RunState.FAILED
    assert 'checkpoint-safe stop' in window.run_page.notice.text() and manager.calls == []


@pytest.mark.smoke
def test_log_access_uses_existing_path_and_completed_exit_display(window, monkeypatch):
    data = preview.snapshot(5, 'COMPLETED')
    for row in data['participants'].values(): row.update(status='EXITED', exit_code=0)
    page = window.run_page; page.show_snapshot(data); opened = []
    monkeypatch.setattr('viv_app.ui.run_page.QDesktopServices.openUrl', lambda url: opened.append(url.toLocalFile()))
    page.open_log(1, 0); assert opened == ['/offline-preview/Fluid-S1.log']
    assert not page.participants.isColumnHidden(3) and page.participants.item(1, 3).text() == '0'
    assert page.state.text() == 'COMPLETED' and page.progress.value() == 10000
    page.reset_view(); assert page.metrics['Accepted Windows'].text() == '—' and page.progress.value() == 0


@pytest.mark.smoke
@pytest.mark.parametrize('size', [(1280,800),(1366,768),(1440,900),(1920,1080)])
def test_offscreen_desktop_sizes_event_loop_and_no_horizontal_overflow(size, window, tmp_path):
    from PySide6.QtWidgets import QAbstractScrollArea
    b = preview.production_view(tmp_path); window.baseline_path.setText(str(b.root)); window.baseline_loaded(b)
    app = QApplication.instance(); window.resize(*size); app.processEvents()
    for page in (0, 1):
        window.navigation.setCurrentRow(page); app.processEvents()
        scroll = window.setup_page.scroll if page == 0 else window.run_page.scroll
        assert scroll.horizontalScrollBar().maximum() == 0
        for area in window.pages.currentWidget().findChildren(QAbstractScrollArea):
            if area.isVisible():
                assert area.horizontalScrollBar().maximum() == 0
                assert not area.horizontalScrollBar().isVisible()
        assert window.width() == size[0] and window.height() == size[1]
    assert not window.progress.isVisible()  # idle IO progress must not resemble a horizontal scrollbar
    setup = window.setup_page
    assert setup.workflow_region.y() >= setup.scroll.geometry().bottom() + 12
    beats = []; timer = QTimer(); timer.setInterval(5); timer.timeout.connect(lambda: beats.append(1))
    loop = QEventLoop(); timer.start(); QTimer.singleShot(100, loop.quit); loop.exec(); timer.stop()
    assert len(beats) >= 5 and window.grab().width() == size[0]
