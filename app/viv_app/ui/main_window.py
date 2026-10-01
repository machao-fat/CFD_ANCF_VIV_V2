from pathlib import Path
from PySide6.QtCore import QObject,Signal,Slot,Qt,QUrl,QTimer
from PySide6.QtGui import QDesktopServices,QColor,QTextCharFormat
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QProgressBar,QFileDialog,QPlainTextEdit,QStackedWidget)
from viv_app.utils.paths import APP_ROOT,CASES_ROOT,local_path
from viv_app.models.simulation_spec import SimulationSpec,StructureParameters
from viv_app.generator.baseline import inspect_baseline
from viv_app.generator.foam_dict import FoamDict
from viv_app.generator.case_generator import generate_case
from viv_app.generator.validation import validate_case
from viv_app.generator.production_baseline import PROFILE,PROFILE_ROOT
from viv_app.generator.production_preflight import production_preflight
from viv_app.runner.manager import RunManager
from viv_app.runner.state import RunState,ACTIVE
from viv_app.ui.run_page import RunPage
from viv_app.ui.setup_page import SetupPage
from viv_app.ui.navigation import Navigation
from viv_app.ui.widgets import apply_theme, label, Disclosure
from viv_app.ui.strings import PRODUCT, SUBTITLE, state_description, event_text
from viv_app.runner.contract import digest
from viv_app.generator.production_validation import validate_production_case
from datetime import datetime
import json
import threading


class Worker(QObject):
    progress=Signal(int,str)
    completed=Signal(object)
    failed=Signal(str)
    finished=Signal()

    def __init__(self,action,parent):
        super().__init__(parent)
        self.action=action

    @Slot()
    def run(self):
        try:
            self.completed.emit(self.action(self.progress.emit))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(PRODUCT)
        self.resize(1440,900)
        self.setMinimumSize(1100,700)
        self.baseline=None
        self.generated=None
        self.worker=None
        self.thread=None
        self._completion=None
        self._operation_ok=False
        self.run_manager=None
        self._close_when_idle=False
        apply_theme(QApplication.instance())
        container=QWidget(); container.setObjectName('shell'); self.setCentralWidget(container)
        layout=QVBoxLayout(container); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        header=QWidget();header.setObjectName('topBar');hl=QHBoxLayout(header);hl.setContentsMargins(24,16,24,16)
        brand=QVBoxLayout();brand.setSpacing(4);brand.addWidget(label(PRODUCT,'title'));brand.addWidget(label(SUBTITLE,'secondary'))
        hl.addLayout(brand);hl.addStretch();self.demo_badge=label('离线展示数据','badge');self.demo_badge.hide();hl.addWidget(self.demo_badge)
        hl.addWidget(label('目标环境  OpenFOAM v2606  ·  preCICE 3.4.1','secondary'));layout.addWidget(header)
        body=QHBoxLayout();body.setContentsMargins(0,0,0,0);body.setSpacing(0);layout.addLayout(body,1)
        self.navigation=Navigation();body.addWidget(self.navigation)
        self.pages=QStackedWidget();body.addWidget(self.pages,1)
        self.setup_page=SetupPage();self.pages.addWidget(self.setup_page)
        for name in self.setup_page.REFERENCES:setattr(self,name,getattr(self.setup_page,name))
        self.run_page=RunPage();self.pages.addWidget(self.run_page)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex);self.navigation.setCurrentRow(0)
        self.setup_page.view_run.clicked.connect(lambda:self.navigation.setCurrentRow(1))
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setMaximumHeight(8);self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.progress.hide()
        self.navigation.currentRowChanged.connect(lambda index:self.progress.setVisible(index==0 and self.thread is not None))
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(130);self.log.document().setMaximumBlockCount(2000)
        self.events_box=Disclosure('运行事件',self.log);self.events_box.setObjectName('eventPanel');layout.addWidget(self.events_box)
        self.context=label('算例：未选择  ·  配置：未审计','secondary');self.statusBar().addPermanentWidget(self.context)
        self.statusBar().showMessage('就绪 · 开始计算前必须准备完成')
        self.prepare.clicked.connect(self.start_prepare)
        self.load_case.clicked.connect(self.select_generated_case)
        self.run_page.run.clicked.connect(self.start_run)
        self.run_page.abort.clicked.connect(self.abort_run)
        self.runner_timer=QTimer(self);self.runner_timer.setInterval(250);self.runner_timer.timeout.connect(self.refresh_run_controls);self.runner_timer.start()
        self.browse.clicked.connect(self.browse_baseline)
        self.baseline_path.editingFinished.connect(self.load_baseline)
        self.profile_selector.activated.connect(self.select_profile)
        self.preflight.clicked.connect(self.start_preflight)
        self.generate.clicked.connect(self.start_generation)
        self.validate.clicked.connect(self.start_validation)
        self.open_folder.clicked.connect(self.open_case_folder)
        self.count.valueChanged.connect(self.rebuild_table)
        self.placement.currentIndexChanged.connect(self.rebuild_table)
        self.ranks.valueChanged.connect(self.apply_ranks)
        self.table.itemChanged.connect(self.update_preview)
        self.flow_type.currentIndexChanged.connect(self.flow_changed)
        self.case_name.textChanged.connect(self.update_preview)
        self.damping.valueChanged.connect(self.update_preview)
        for box in self.flow_values.values():box.valueChanged.connect(self.update_preview)
        self.flow_changed()
        self.rebuild_table()

    def is_production(self):
        return bool(self.baseline and self.baseline.descriptor.get('contract_profile')==PROFILE)

    @Slot(int)
    def select_profile(self,index):
        if index==1:
            self.baseline_path.setText(str(PROFILE_ROOT));self.load_baseline()

    @Slot()
    def start_preflight(self):
        if self.generated and (self.is_production() or self.run_manager):
            prepared=bool(self.run_manager and self.run_manager.state==RunState.PREPARED)
            self.run_worker('运行前检查',lambda progress:production_preflight(self.generated,progress,write_report=not prepared,prepared=prepared),self.preflight_completed)

    def preflight_completed(self,result):
        self.validation_label.setText(f"运行前检查 {result['status']}")
        if result['status']=='FAIL':self.operation_failed(result['first_failure'])
        else:
            self.setup_page.emphasize('preflight')
            self.log.appendPlainText('运行前检查通过 · PASS；请继续准备计算。')
            for warning in result['warnings']:self.log.appendPlainText(warning)

    @Slot()
    def browse_baseline(self):
        path=QFileDialog.getExistingDirectory(self,'选择基准目录（只读）',str(APP_ROOT/'workspace/baselines'))
        if path:
            self.baseline_path.setText(path); self.load_baseline()

    @Slot()
    def load_baseline(self):
        if self.thread is not None or not self.baseline_path.text().strip(): return
        self.baseline=None
        path=self.baseline_path.text()
        self.run_worker('审计基准',lambda progress:inspect_baseline(path),self.baseline_loaded)

    def baseline_loaded(self,b):
        self.baseline=b
        self.setup_page.show_baseline(b)
        self.initial_time.clear(); self.initial_time.addItems(b.times)
        self.initial_time.setCurrentText(b.descriptor['initial_time_default'])
        prod=self.is_production()
        self.profile_selector.setCurrentIndex(1 if prod else 0)
        for label in self.structure_labels.values():label.setText(label.property("baseLabel"))
        if prod:
            self.baseline_note.setText('NM12 N5 lineage · 初始状态与生产参数已锁定。基准保持只读。')
        else:
            self.baseline_note.setText(f"仅离线生成 · {b.manifest.reconstruction_mode} · Structure runner NOT YET WIRED")
        self.count.setRange(5,5) if prod else self.count.setRange(1,32)
        self.count.setEnabled(not prod); self.placement.setEnabled(not prod)
        self.placement.setCurrentIndex(0)
        self.ranks.setEnabled(not prod); self.dt.setEnabled(not prod);self.damping.setEnabled(not prod)
        self.initial_time.setEnabled(not prod);self.purge.setEnabled(prod)
        self.purge.setValue(int(b.controls.scalar('purgeWrite')) if prod else 0)
        self.generated=None;self.preflight.setEnabled(False)
        self.attach_run_manager(None)
        s=b.structure
        for name,field in self.structure_fields.items(): field.setText(str(getattr(s,name)))
        self.damping.setValue(s.damping_alpha)
        self.nodes.setText(f'{s.nodes} 个节点 / {6*s.nodes} DOFs · 继承初始平衡态')
        self.dt.setValue(float(b.controls.scalar('deltaT')))
        self.end.setValue(float(b.controls.scalar('endTime')))
        self.write.setValue(float(b.controls.scalar('writeInterval')))
        self.write_label.setText(f"writeInterval [{b.controls.scalar('writeControl')}]")
        self.flow_values['u0'].setValue(b.inlet_speed)
        self.flow_values['u_bottom'].setValue(b.inlet_speed); self.flow_values['u_top'].setValue(b.inlet_speed)
        self.count.setValue(b.manifest.ns)
        self.ranks.setValue(int(FoamDict((b.fluid/'system/decomposeParDict').read_bytes()).scalar('numberOfSubdomains')))
        self.interval_note.setText(f'Active interval [{b.manifest.active_start_m:g}, {b.manifest.active_end_m:g}] m · s 自底向上 · SLD1 要求 N ≥ 2')
        self.rebuild_table()

    @Slot()
    def flow_changed(self):self.setup_page.flow_changed()

    def positions(self):return self.setup_page.positions()

    @Slot()
    def rebuild_table(self):
        self.setup_page.baseline=self.baseline
        self.setup_page.rebuild_table()

    @Slot()
    def apply_ranks(self):self.setup_page.apply_ranks()

    def flow_profile(self):return self.setup_page.flow_profile()

    @Slot()
    def update_preview(self):self.setup_page.update_preview()

    def simulation_spec(self):
        if not self.baseline: raise ValueError('请先选择并成功审计支持的基准配置。')
        if local_path(self.baseline_path.text())!=self.baseline.root:
            raise ValueError('基准路径已变更，请重新审计后再生成算例。')
        s=self.baseline.structure
        structure=StructureParameters(**{**s.__dict__,'damping_alpha':self.damping.value()})
        return SimulationSpec(case_name=self.case_name.text(),baseline_path=str(self.baseline.root),
            output_root=self.output_root.text(),initial_state_time=self.initial_time.currentText(),
            positions_over_l=self.positions(),mpi_ranks=tuple(self.table.cellWidget(i,4).value() for i in range(self.table.rowCount())),
            enabled=tuple(self.table.cellWidget(i,3).isChecked() for i in range(self.table.rowCount())),
            structure=structure,flow=self.flow_profile(),delta_t=self.dt.value(),end_time=self.end.value(),
            write_interval=self.write.value(),purge_write=self.purge.value(),placement='uniform' if self.placement.currentIndex()==0 else 'custom')

    @Slot()
    def start_generation(self):
        try:
            spec=self.simulation_spec(); spec.validate()
            self.run_worker('生成算例',lambda progress:generate_case(spec,progress),self.generation_completed)
        except Exception as exc: self.operation_failed(str(exc))

    def generation_completed(self,path):
        self.generated=Path(path)
        self.attach_run_manager(self.generated)
        self.validation_label.setText('✓ 生成与静态检查通过 · PASS')
        self.setup_page.emphasize('generated' if self.is_production() else 'new')
        self.log.appendPlainText(f'算例已生成：{path}')
        self.log.appendPlainText('请继续运行前检查与准备计算；尚未启动耦合求解。' if self.is_production() else '此配置仅支持离线生成；Structure runner NOT YET WIRED。')
        if self.is_production():self.validation_label.setText('✓ 生成与静态检查通过 · PASS  /  待运行前检查')

    @Slot()
    def start_validation(self):
        if self.generated:
            prepared=bool(self.run_manager and self.run_manager.state==RunState.PREPARED)
            self.run_worker('静态检查',lambda progress:validate_production_case(self.generated,prepared=True) if prepared else validate_case(self.generated),self.validation_completed)

    def validation_completed(self,result):
        scope='Production 算例' if self.is_production() else '离线算例'
        self.validation_label.setText(f"静态检查 {result['status']} · {scope}")
        if result['status']=='FAIL': self.operation_failed(result['first_failure'])
        else:
            self.log.appendPlainText('静态检查通过 · PASS')
            self.setup_page.emphasize('validated' if self.is_production() else 'new')

    @Slot()
    def open_case_folder(self):
        if self.generated: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.generated)))

    def run_worker(self,status,action,completion):
        if self.thread is not None or (self.run_manager and self.run_manager.busy): return
        self.error.clear(); self.error.hide(); self.progress.setValue(0)
        self.progress.setVisible(self.navigation.currentRow()==0)
        self.validation_label.setText(status+'…')
        self.statusBar().showMessage(status); self.log.appendPlainText(status)
        self.form_widget.setEnabled(False); self.table.setEnabled(False)
        self.generate.setEnabled(False); self.validate.setEnabled(False);self.preflight.setEnabled(False)
        # Keep QObject ownership in the GUI thread. Only the file action runs
        # in Python's background thread; every UI callback is explicitly queued.
        # Holding both references until the thread has returned also handles a
        # fast failure without racing QObject/QThread deferred deletion.
        self.worker=Worker(action,self)
        self.thread=threading.Thread(target=self.worker.run,name='viv-case-io',daemon=False)
        self._completion=completion; self._operation_ok=False
        self.worker.progress.connect(self.worker_progress,Qt.QueuedConnection)
        self.worker.completed.connect(self.worker_completed,Qt.QueuedConnection)
        self.worker.failed.connect(self.operation_failed,Qt.QueuedConnection)
        self.worker.finished.connect(self.worker_finished,Qt.QueuedConnection)
        self.thread.start()

    @Slot(int,str)
    def worker_progress(self,percent,message):
        self.progress.setValue(percent); self.statusBar().showMessage(message)
        self.log.appendPlainText(message)

    @Slot(object)
    def worker_completed(self,value):
        self._operation_ok=True
        self._completion(value)

    @Slot(str)
    def operation_failed(self,message):
        self._operation_ok=False
        self.error.setText(message)
        self.validation_label.setText('✕ 检查失败 · FAIL')
        self.error.show()
        self.statusBar().showMessage('检查失败 · FAIL')
        self.log.appendPlainText(message)
        if self.run_manager and not self.run_manager.busy and self.run_manager.state==RunState.PREPARED:
            self.run_manager.invalidate(message)

    @Slot()
    def worker_finished(self):
        if self.thread is not None and self.thread.is_alive():
            QTimer.singleShot(10,self.worker_finished)
            return
        if self.worker is not None:self.worker.deleteLater()
        self.thread=None; self.worker=None; self._completion=None
        self.form_widget.setEnabled(True); self.table.setEnabled(True)
        self.generate.setEnabled(True)
        self.preflight.setEnabled(self.generated is not None and self.is_production())
        self.validate.setEnabled(self.generated is not None); self.open_folder.setEnabled(self.generated is not None)
        if self._operation_ok:
            self.progress.setValue(100); self.statusBar().showMessage('就绪 · 操作完成')
        self.progress.hide()

    def closeEvent(self,event):
        if self.run_manager and self.run_manager.busy:
            self._close_when_idle=True
            if self.run_manager.state in ACTIVE and self.run_manager.state!=RunState.ABORTING:self.abort_run()
            self.statusBar().showMessage('正在关闭：终止本次管理器启动的进程，等待清理完成。')
            event.ignore()
        elif self.thread is not None:
            self.statusBar().showMessage('请等待当前文件操作完成后关闭。')
            event.ignore()
        else: super().closeEvent(event)

    def attach_run_manager(self,path):
        if self.run_manager and self.run_manager.busy:raise ValueError('Cannot replace active Run Manager')
        if self.run_manager:self.run_manager.deleteLater()
        self.run_manager=None
        self.run_page.reset_view()
        try:
            prod=path and json.loads((Path(path)/'generation_manifest.json').read_text())['contract_profile']==PROFILE
        except (OSError,ValueError,KeyError):prod=False
        if prod:
            try:self.run_manager=RunManager(path,parent=self)
            except ValueError as exc:self.error.setText(str(exc));self.refresh_run_controls();return
            self.run_manager.state_changed.connect(self.runner_state)
            self.run_manager.event.connect(self.runner_event)
            self.run_manager.snapshot.connect(self.run_page.show_snapshot)
            self.run_manager.finished.connect(self.runner_finished)
            self.run_page.case.setText(str(path));self.run_page.show_state('CREATED')
        else:self.run_page.case.setText('请生成或选择未运行的 V2606 N5 Production 算例。');self.run_page.show_state('CREATED')
        self.refresh_run_controls()

    def select_generated_case(self):
        if self.thread is not None or (self.run_manager and self.run_manager.busy):return
        path=QFileDialog.getExistingDirectory(self,'选择未运行的已生成 Production 算例',str(CASES_ROOT))
        if path:
            self.generated=local_path(path);self.attach_run_manager(self.generated);self.open_folder.setEnabled(True)

    def start_prepare(self):
        if self.run_manager:
            try:self.run_page.clear_failure();self.run_manager.prepare();self.refresh_run_controls()
            except Exception as exc:self.operation_failed(str(exc))

    def start_run(self):
        if self.run_manager:
            try:
                self.run_manager.run();self.navigation.setCurrentRow(1);self.refresh_run_controls()
            except Exception as exc:self.operation_failed(str(exc))

    def abort_run(self):
        if self.run_manager:
            try:self.run_manager.abort();self.run_page.abort.setEnabled(False)
            except ValueError as exc:self.statusBar().showMessage(str(exc))

    def runner_state(self,state):
        self.run_page.show_state(state);self.statusBar().showMessage(state+' · '+state_description(state))
        if state=='PREPARED':self.setup_page.emphasize('prepared');self.validation_label.setText('✓ 准备完成 · PREPARED')
        self.refresh_run_controls()

    def runner_event(self,event):
        kind=event['event_type'];name=event['participant'];value=event['value']
        text=event_text(event)
        if kind=='fatal':self.run_page.show_failure(value,participant=name)
        stamp=datetime.fromisoformat(event['timestamp']).astimezone().strftime('%H:%M:%S')
        cursor=self.log.textCursor();cursor.movePosition(cursor.MoveOperation.End)
        fmt=QTextCharFormat();fmt.setForeground(QColor('#D9485F'if kind=='fatal'else '#A86C08'if kind=='warning'else '#7A818D'))
        cursor.insertText(stamp+'  '+text+'\n',fmt);self.log.setTextCursor(cursor)

    def runner_finished(self,result):
        if result['first_failure']:
            self.error.setText(result['first_failure'].get('reason',str(result['first_failure'])));self.error.show()
            self.run_page.show_failure(result['first_failure'])
        self.statusBar().showMessage(result['state']+' · '+state_description(result['state']))
        self.refresh_run_controls()

    def refresh_run_controls(self):
        manager=self.run_manager;busy=bool(manager and manager.busy)
        case=self.generated.name if self.generated else '未选择'
        self.context.setText(f'算例：{case}  ·  配置：'+('N5 Production' if self.is_production() or manager else '离线基准'))
        state=manager.state if manager else None
        if manager and not busy and state==RunState.PREPARED:
            try:
                if digest(manager.root/'launch_manifest.json')!=manager.preparation['launch_manifest_sha256']:
                    manager.invalidate('Launch manifest changed after Prepare');state=manager.state
            except (OSError,ValueError):manager.invalidate('Launch manifest is unreadable');state=manager.state
        self.prepare.setEnabled(bool(manager and state==RunState.CREATED and not busy and self.thread is None))
        self.run_page.run.setEnabled(bool(manager and state==RunState.PREPARED and not busy and self.thread is None))
        self.run_page.abort.setEnabled(bool(busy and state in ACTIVE and state!=RunState.ABORTING and not manager.abort_requested.is_set()))
        self.load_case.setEnabled(not busy and self.thread is None)
        self.setup_page.view_run.setEnabled(bool(manager and state==RunState.PREPARED and not busy and self.thread is None))
        if busy:
            self.form_widget.setEnabled(False);self.table.setEnabled(False)
            for b in (self.generate,self.validate,self.preflight):b.setEnabled(False)
        elif self.thread is None:
            self.form_widget.setEnabled(True);self.table.setEnabled(True);self.generate.setEnabled(True)
            self.validate.setEnabled(self.generated is not None)
            self.preflight.setEnabled(self.generated is not None and (self.is_production() or manager is not None) and not (manager and state in (RunState.COMPLETED,RunState.FAILED,RunState.ABORTED)))
        if self._close_when_idle:
            if busy and state in ACTIVE and state!=RunState.ABORTING and not manager.abort_requested.is_set():self.abort_run()
            elif not busy and self.thread is None:self._close_when_idle=False;self.close()
