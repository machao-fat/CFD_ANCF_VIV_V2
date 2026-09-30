"""Read-only GUI acceptance on existing production example; no generation/run."""
from pathlib import Path
import json,time
from PySide6.QtCore import QTimer,QEventLoop
from PySide6.QtWidgets import QApplication
from viv_app.ui.main_window import MainWindow
from viv_app.generator.production_baseline import PROFILE_ROOT
from viv_app.utils.paths import APP_ROOT,CASES_ROOT

app=QApplication([]);app.setStyle('Fusion')
app.setStyleSheet((APP_ROOT/'app/viv_app/ui/theme.qss').read_text())
window=MainWindow();window.show()
beats=[];timer=QTimer();timer.setInterval(20);timer.timeout.connect(lambda:beats.append(time.monotonic()));timer.start()
def idle():
    loop=QEventLoop();poll=QTimer();poll.setInterval(20)
    poll.timeout.connect(lambda:loop.quit() if window.thread is None else None)
    poll.start();loop.exec();poll.stop()
window.select_profile(1);idle()
assert window.baseline and window.is_production(),window.error.text()
window.generated=CASES_ROOT/'production_N5_bridge_dryrun';window.case_name.setText(window.generated.name)
window.preflight.setEnabled(True);before=len(beats)
window.start_preflight();idle()
assert 'PASS' in window.validation_label.text(),window.error.text()
assert len(beats)-before>=10
assert not window.count.isEnabled() and window.count.value()==5
window.grab().save(str(APP_ROOT/'app/resources/production-bridge-gui-preview.png'))
(APP_ROOT/'app/resources/production-bridge-gui-acceptance.json').write_text(json.dumps({
    'status':'PASS','qualified_profile_import':'PASS','N5_physics_and_MPI_locks':'PASS',
    'production_preflight_through_QThread':'PASS','event_loop_timer_beats_during_preflight':len(beats)-before,
    'real_fsi_started':False,'generated_case':str(window.generated)},indent=2)+'\n')
timer.stop();window.close();app.processEvents()
print('GUI qualified import / locked N5 / threaded preflight / responsiveness PASS; no FSI')
