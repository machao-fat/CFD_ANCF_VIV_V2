from pathlib import Path
from PySide6.QtCore import QObject,QThread,Signal,Slot,Qt,QUrl,QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,
    QLineEdit,QPushButton,QSpinBox,QDoubleSpinBox,QComboBox,QLabel,QSplitter,
    QScrollArea,QGroupBox,QTableWidget,QTableWidgetItem,QHeaderView,QPlainTextEdit,
    QProgressBar,QFileDialog,QAbstractItemView,QCheckBox)
from viv_app.utils.paths import APP_ROOT,CASES_ROOT,local_path
from viv_app.models.simulation_spec import SimulationSpec,FlowProfile,StructureParameters,uniform_positions
from viv_app.generator.baseline import inspect_baseline
from viv_app.generator.foam_dict import FoamDict
from viv_app.generator.case_generator import generate_case
from viv_app.generator.validation import validate_case
from viv_app.generator.production_baseline import PROFILE,PROFILE_ROOT,POSITIONS
from viv_app.generator.production_preflight import production_preflight


class Worker(QObject):
    progress=Signal(int,str)
    completed=Signal(object)
    failed=Signal(str)
    finished=Signal()

    def __init__(self,action):
        super().__init__()
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
        self.setWindowTitle('VIV Case Generator · Production Bridge V1')
        self.resize(1380,900)
        self.baseline=None
        self.generated=None
        self.worker=None
        self.thread=None
        self._updating=False
        self._completion=None
        self._operation_ok=False
        container=QWidget()
        self.setCentralWidget(container)
        layout=QVBoxLayout(container)
        title=QLabel('VIV Case Generator')
        title.setObjectName('title')
        subtitle=QLabel('CFD–preCICE–ANCF  /  Case Builder  /  Offline configuration')
        subtitle.setObjectName('subtitle')
        layout.addWidget(title)
        layout.addWidget(subtitle)
        self.splitter=QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter,1)
        self.form_widget=QWidget()
        form_layout=QVBoxLayout(self.form_widget)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form_widget)
        self.splitter.addWidget(scroll)
        project=self.group('Project / Baseline',form_layout)
        f=QFormLayout(project)
        self.case_name=QLineEdit('VIV_N5_test')
        f.addRow('Case Name',self.case_name)
        self.profile_selector=QComboBox()
        self.profile_selector.addItems(['Custom / offline baseline','v2606 N5 implicit production (NM12)'])
        f.addRow('Import Profile',self.profile_selector)
        self.baseline_path=QLineEdit()
        self.baseline_path.setPlaceholderText('Select an audited baseline root (app_baseline.json)')
        self.browse=QPushButton('Browse Baseline')
        row=QWidget(); r=QHBoxLayout(row); r.setContentsMargins(0,0,0,0)
        r.addWidget(self.baseline_path); r.addWidget(self.browse)
        f.addRow('Baseline Directory',row)
        self.output_root=QLineEdit(str(CASES_ROOT))
        f.addRow('Output Root',self.output_root)
        self.initial_time=QComboBox()
        f.addRow('Initial State Time',self.initial_time)
        self.baseline_note=QLabel('Baseline is read only. Select a supported contract.')
        self.baseline_note.setWordWrap(True)
        f.addRow(self.baseline_note)
        slices=self.group('Slice Configuration',form_layout)
        f=QFormLayout(slices)
        self.count=QSpinBox(); self.count.setRange(1,32); self.count.setValue(5)
        self.placement=QComboBox(); self.placement.addItems(['Uniform spacing','Custom positions'])
        self.ranks=QSpinBox(); self.ranks.setRange(1,1024); self.ranks.setValue(4)
        f.addRow('Number of Slices',self.count)
        f.addRow('Placement',self.placement)
        f.addRow('MPI ranks per slice',self.ranks)
        self.interval_note=QLabel('Uniform centers use the inherited active interval.')
        self.interval_note.setWordWrap(True); f.addRow(self.interval_note)
        flow=self.group('Flow Profile',form_layout); f=QFormLayout(flow)
        self.flow_type=QComboBox(); self.flow_type.addItems(['Uniform','Linear Shear','Step Current'])
        f.addRow('Profile',self.flow_type)
        self.flow_values={}
        self.flow_labels={}
        for key,label,default,maximum in [('u0','U0 [m/s]',0.31,1000),('u_bottom','U_bottom [m/s]',0.31,1000),
            ('u_top','U_top [m/s]',0.31,1000),('transition','Transition s/L [-]',0.45,1),
            ('u_active','U_active [m/s]',0.6,1000),('u_inactive','U_inactive [m/s]',0,1000)]:
            box=self.number(default,0,maximum)
            lab=QLabel(label); f.addRow(lab,box)
            self.flow_values[key]=box; self.flow_labels[key]=lab
            box.valueChanged.connect(self.update_preview)
        structure=self.group('Structure · native ANCF',form_layout); f=QFormLayout(structure)
        self.structure_fields={}
        self.structure_labels={}
        for key,label in [('diameter_m','D [m]'),('length_m','L [m]'),('ea_n','EA [N]'),('ei_nm2','EI [N m²]'),
            ('mass_per_length','Line mass [kg/m]'),('pretension_n','Pretension [N]'),('elements','ANCF elements')]:
            value=QLineEdit('—'); value.setReadOnly(True)
            value.setToolTip('NOT YET WIRED: requires a compatible mesh / structural equilibrium state.')
            self.structure_fields[key]=value
            self.structure_labels[key]=QLabel(f'{label} · NOT YET WIRED')
            self.structure_labels[key].setProperty('baseLabel',label)
            f.addRow(self.structure_labels[key],value)
        self.damping=self.number(0,0,1000)
        f.addRow('Structural damping · Rayleigh α [1/s]',self.damping)
        self.nodes=QLabel('Nodes derived from element count.')
        f.addRow(self.nodes)
        numerics=self.group('Numerics / Parallel',form_layout); f=QFormLayout(numerics)
        self.dt=self.number(0.0002,0.000000001,100); self.dt.setDecimals(9)
        self.end=self.number(0.2,0.000000001,1e9)
        self.write=self.number(0.01,0.000000001,1e9)
        self.write_label=QLabel('writeInterval')
        f.addRow('deltaT [s]',self.dt); f.addRow('endTime [s, fluid absolute]',self.end)
        f.addRow(self.write_label,self.write)
        self.purge=QSpinBox(); self.purge.setRange(0,1000000); self.purge.setEnabled(False)
        f.addRow("purgeWrite (production)",self.purge)
        note=QLabel('fvSchemes, fvSolution, PIMPLE, RBF and turbulence inherit baseline.')
        note.setWordWrap(True); f.addRow(note)
        form_layout.addStretch()
        right=QWidget(); rl=QVBoxLayout(right)
        preview_title=QLabel('Case Preview'); preview_title.setObjectName('sectionTitle')
        rl.addWidget(preview_title)
        self.preview=QPlainTextEdit(); self.preview.setReadOnly(True); self.preview.setMaximumHeight(220)
        rl.addWidget(self.preview)
        self.table=QTableWidget(0,7)
        self.table.setHorizontalHeaderLabels(['Slice ID','s [m]','s/L [-]','Enabled','MPI','U_i [m/s]','Mesh source'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        # Qt does not include embedded spinbox size hints in content sizing.
        self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.Fixed)
        self.table.setColumnWidth(4,90)
        self.table.horizontalHeader().setSectionResizeMode(5,QHeaderView.Fixed)
        self.table.setColumnWidth(5,100)
        self.table.horizontalHeader().setSectionResizeMode(6,QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        rl.addWidget(self.table,1)
        self.validation_label=QLabel('CASE GENERATION\nReady'); self.validation_label.setObjectName('validation')
        rl.addWidget(self.validation_label)
        self.error=QLabel(); self.error.setWordWrap(True); self.error.setObjectName('error')
        self.error.setTextInteractionFlags(Qt.TextSelectableByMouse); rl.addWidget(self.error)
        buttons=QHBoxLayout()
        self.generate=QPushButton('Generate Case'); self.generate.setObjectName('primary')
        self.validate=QPushButton('Validate Generated Case'); self.validate.setEnabled(False)
        self.open_folder=QPushButton('Open Case Folder'); self.open_folder.setEnabled(False)
        for b in (self.generate,self.validate,self.open_folder): buttons.addWidget(b)
        rl.addLayout(buttons)
        self.preflight=QPushButton("Production Preflight"); self.preflight.setEnabled(False)
        rl.addWidget(self.preflight)
        self.splitter.addWidget(right); self.splitter.setSizes([480,900])
        self.progress=QProgressBar(); self.progress.setRange(0,100); layout.addWidget(self.progress)
        self.log=QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(100)
        self.log.document().setMaximumBlockCount(150); layout.addWidget(self.log)
        self.statusBar().showMessage('Ready · V1 generates and validates configuration only')
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
        self.flow_changed()
        self.rebuild_table()

    @staticmethod
    def group(title,layout):
        group=QGroupBox(title); layout.addWidget(group); return group

    @staticmethod
    def number(default,minimum,maximum):
        box=QDoubleSpinBox(); box.setDecimals(8); box.setRange(minimum,maximum)
        box.setValue(default); box.setSingleStep(0.01); return box

    def is_production(self):
        return bool(self.baseline and self.baseline.descriptor.get('contract_profile')==PROFILE)

    @Slot(int)
    def select_profile(self,index):
        if index==1:
            self.baseline_path.setText(str(PROFILE_ROOT));self.load_baseline()

    @Slot()
    def start_preflight(self):
        if self.generated and self.is_production():
            self.run_worker('Production Preflight',lambda progress:production_preflight(self.generated,progress),self.preflight_completed)

    def preflight_completed(self,result):
        self.validation_label.setText(f"PRODUCTION PREFLIGHT\n{result['status']} · real FSI started = NO")
        if result['status']=='FAIL':self.operation_failed(result['first_failure'])
        else:
            self.log.appendPlainText('production_launch_ready=true; manual decomposition and launch only')
            for warning in result['warnings']:self.log.appendPlainText(warning)

    @Slot()
    def browse_baseline(self):
        path=QFileDialog.getExistingDirectory(self,'Select Baseline (read only)',str(APP_ROOT/'workspace/baselines'))
        if path:
            self.baseline_path.setText(path); self.load_baseline()

    @Slot()
    def load_baseline(self):
        if self.thread is not None or not self.baseline_path.text().strip(): return
        self.baseline=None
        path=self.baseline_path.text()
        self.run_worker('Auditing baseline',lambda progress:inspect_baseline(path),self.baseline_loaded)

    def baseline_loaded(self,b):
        self.baseline=b
        self.initial_time.clear(); self.initial_time.addItems(b.times)
        self.initial_time.setCurrentText(b.descriptor['initial_time_default'])
        prod=self.is_production()
        self.profile_selector.setCurrentIndex(1 if prod else 0)
        for label in self.structure_labels.values():label.setText(label.property("baseLabel")+(" · LOCKED" if prod else " · NOT YET WIRED"))
        if prod:
            self.baseline_note.setText('USER_PROJECT_QUALIFIED · NM12 short100\nImplicit N5 / external immutable Structure. Physics, positions, dt and ranks locked. Manual preparation required.')
        else:
            self.baseline_note.setText(f"{b.descriptor['evidence_status']}\n{b.manifest.reconstruction_mode} / generic explicit. Structural runner: NOT YET WIRED in main.")
        self.count.setRange(5,5) if prod else self.count.setRange(1,32)
        self.count.setEnabled(not prod); self.placement.setEnabled(not prod)
        self.placement.setCurrentIndex(0)
        self.ranks.setEnabled(not prod); self.dt.setEnabled(not prod);self.damping.setEnabled(not prod)
        self.initial_time.setEnabled(not prod);self.purge.setEnabled(prod)
        self.purge.setValue(int(b.controls.scalar('purgeWrite')) if prod else 0)
        self.generated=None;self.preflight.setEnabled(False)
        s=b.structure
        for name,field in self.structure_fields.items(): field.setText(str(getattr(s,name)))
        self.damping.setValue(s.damping_alpha)
        self.nodes.setText(f'{s.nodes} nodes / {6*s.nodes} DOFs · inherited equilibrium state')
        self.dt.setValue(float(b.controls.scalar('deltaT')))
        self.end.setValue(float(b.controls.scalar('endTime')))
        self.write.setValue(float(b.controls.scalar('writeInterval')))
        self.write_label.setText(f"writeInterval [{b.controls.scalar('writeControl')}]")
        self.flow_values['u0'].setValue(b.inlet_speed)
        self.flow_values['u_bottom'].setValue(b.inlet_speed); self.flow_values['u_top'].setValue(b.inlet_speed)
        self.count.setValue(b.manifest.ns)
        self.ranks.setValue(int(FoamDict((b.fluid/'system/decomposeParDict').read_bytes()).scalar('numberOfSubdomains')))
        self.interval_note.setText(f'Active interval [{b.manifest.active_start_m:g}, {b.manifest.active_end_m:g}] m; s measured bottom to top. SLD1 requires N ≥ 2.')
        self.rebuild_table()

    @Slot()
    def flow_changed(self):
        visible={'Uniform':{'u0'},'Linear Shear':{'u_bottom','u_top'},'Step Current':{'transition','u_active','u_inactive'}}[self.flow_type.currentText()]
        for key,box in self.flow_values.items():
            box.setVisible(key in visible); self.flow_labels[key].setVisible(key in visible)
        self.update_preview()

    def positions(self):
        return tuple(float(self.table.item(i,2).text()) for i in range(self.table.rowCount()))

    @Slot()
    def rebuild_table(self):
        self._updating=True
        self.table.blockSignals(True)
        n=self.count.value()
        if self.baseline:
            b=self.baseline
            positions=tuple(x/b.model.length_m for x in POSITIONS) if self.is_production() else uniform_positions(n,b.model.length_m,b.manifest.active_start_m,b.manifest.active_end_m)
            length=b.model.length_m
        else:
            positions=uniform_positions(n,1,0,1); length=1
        old=[]
        if self.placement.currentIndex()==1:
            try: old=list(self.positions())
            except (ValueError,AttributeError): pass
        self.table.setRowCount(n)
        for i in range(n):
            x=old[i] if i<len(old) else positions[i]
            for col,text in [(0,f'S{i+1}' if self.is_production() else f'slice_{i:04d}'),(1,f'{x*length:.6g}'),(2,f'{x:.15g}'),(5,'—'),(6,'baseline mesh')]:
                item=QTableWidgetItem(text)
                flags=Qt.ItemIsSelectable|Qt.ItemIsEnabled
                if col==2 and self.placement.currentIndex()==1 and not self.is_production(): flags|=Qt.ItemIsEditable
                item.setFlags(flags); self.table.setItem(i,col,item)
            enabled=QCheckBox(); enabled.setChecked(True); enabled.stateChanged.connect(self.update_preview)
            enabled.setEnabled(not self.is_production())
            self.table.setCellWidget(i,3,enabled)
            rank=QSpinBox(); rank.setRange(1,1024); rank.setValue(self.ranks.value())
            rank.setEnabled(not self.is_production())
            rank.setFixedWidth(82)
            rank.valueChanged.connect(self.update_preview); self.table.setCellWidget(i,4,rank)
        self.table.blockSignals(False); self._updating=False; self.update_preview()

    @Slot()
    def apply_ranks(self):
        for i in range(self.table.rowCount()):
            box=self.table.cellWidget(i,4)
            if box: box.setValue(self.ranks.value())
        self.update_preview()

    def flow_profile(self):
        return FlowProfile(kind=self.flow_type.currentText(),**{k:b.value() for k,b in self.flow_values.items()})

    @Slot()
    def update_preview(self):
        if self._updating or not hasattr(self,'preview'): return
        self.table.blockSignals(True)
        try:
            values=self.positions(); flow=self.flow_profile()
            length=self.baseline.model.length_m if self.baseline else 1
            lines=[f'Case   {self.case_name.text()}',f'Slices   {len(values)}',f'Flow   {flow.kind}','']
            total=0
            for i,x in enumerate(values):
                u=flow.velocity(x)
                rank=self.table.cellWidget(i,4).value()
                enabled=self.table.cellWidget(i,3).isChecked()
                total+=rank if enabled else 0
                self.table.item(i,1).setText(f'{x*length:.6g}')
                self.table.item(i,5).setText(f'{u:.6g}')
                lines.append(f'Slice {i:02d}   s/L={x:.4f}   U={u:.4f}   MPI={rank}'+('   DISABLED' if not enabled else ''))
            lines.extend(['',f'Total CFD ranks   {total}'])
            if self.baseline: lines.append(f'Structure   ANCF / {self.baseline.model.elements} elements')
            self.preview.setPlainText('\n'.join(lines))
        except (ValueError,AttributeError,TypeError) as exc:
            self.preview.setPlainText(f'Invalid slice table: {exc}')
        finally:
            self.table.blockSignals(False)

    def simulation_spec(self):
        if not self.baseline: raise ValueError('Select and successfully audit a supported baseline first.')
        if local_path(self.baseline_path.text())!=self.baseline.root:
            raise ValueError('Baseline path changed; audit it again before generation.')
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
            self.run_worker('Generating',lambda progress:generate_case(spec,progress),self.generation_completed)
        except Exception as exc: self.operation_failed(str(exc))

    def generation_completed(self,path):
        self.generated=Path(path)
        self.validation_label.setText('CASE GENERATION\nPASS · offline configuration')
        self.log.appendPlainText(f'Generated: {path}')
        self.log.appendPlainText('External Structure command recovered; run Production Preflight. No FSI started.' if self.is_production() else 'Structural runner remains NOT YET WIRED in main. No simulation started.')
        if self.is_production():self.validation_label.setText('CASE GENERATION\nPASS · production configuration; preflight pending')

    @Slot()
    def start_validation(self):
        if self.generated:
            self.run_worker('Validating',lambda progress:validate_case(self.generated),self.validation_completed)

    def validation_completed(self,result):
        scope='production configuration' if self.is_production() else 'offline configuration'
        self.validation_label.setText(f"CASE GENERATION\n{result['status']} · {scope}")
        if result['status']=='FAIL': self.operation_failed(result['first_failure'])
        else: self.log.appendPlainText('Static validation PASS')

    @Slot()
    def open_case_folder(self):
        if self.generated: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.generated)))

    def run_worker(self,status,action,completion):
        if self.thread is not None: return
        self.error.clear(); self.progress.setValue(0)
        self.validation_label.setText(f'CASE GENERATION\n{status}')
        self.statusBar().showMessage(status); self.log.appendPlainText(status)
        self.form_widget.setEnabled(False); self.table.setEnabled(False)
        self.generate.setEnabled(False); self.validate.setEnabled(False);self.preflight.setEnabled(False)
        self.thread=QThread(self)
        self.worker=Worker(action); self.worker.moveToThread(self.thread)
        self._completion=completion; self._operation_ok=False
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.worker_progress)
        self.worker.completed.connect(self.worker_completed)
        self.worker.failed.connect(self.operation_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.worker_finished)
        self.thread.finished.connect(self.thread.deleteLater)
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
        self.validation_label.setText('CASE GENERATION\nFAIL')
        self.statusBar().showMessage('FAIL · '+message)
        self.log.appendPlainText(message)

    @Slot()
    def worker_finished(self):
        self.thread=None; self.worker=None; self._completion=None
        self.form_widget.setEnabled(True); self.table.setEnabled(True)
        self.generate.setEnabled(True)
        self.preflight.setEnabled(self.generated is not None and self.is_production())
        self.validate.setEnabled(self.generated is not None); self.open_folder.setEnabled(self.generated is not None)
        if self._operation_ok:
            self.progress.setValue(100); self.statusBar().showMessage('Ready · operation completed')

    def closeEvent(self,event):
        if self.thread is not None:
            self.statusBar().showMessage('Wait for the current file operation to finish before closing.')
            event.ignore()
        else: super().closeEvent(event)
