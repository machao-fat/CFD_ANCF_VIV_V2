"""Native Qt dashboard; bounded plots, no terminal stream retained in widgets."""
import math
from PySide6.QtCore import Qt,QUrl,QPointF
from PySide6.QtGui import QPainter,QPen,QColor,QPolygonF,QDesktopServices
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QGridLayout,QGroupBox,QProgressBar


class HistoryPlot(QWidget):
    def __init__(self,title,index,parent=None):
        super().__init__(parent);self.title=title;self.index=index;self.history=[]
        self.setMinimumHeight(140)

    def set_history(self,history):
        self.history=list(history[-500:]);self.update()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor('#b5c3d4'));p.drawText(10,20,self.title+' · accepted window')
        left,top,right,bottom=60,36,self.width()-12,self.height()-27
        p.setPen(QPen(QColor('#344151'),1));p.drawLine(left,bottom,right,bottom);p.drawLine(left,top,left,bottom)
        points=[(row[0],row[self.index])for row in self.history if isinstance(row[self.index],(int,float))and math.isfinite(row[self.index])]
        if not points:return
        lo=min(y for x,y in points);hi=max(y for x,y in points);span=max(hi-lo,1e-10);xmin=points[0][0];xspan=max(1,points[-1][0]-xmin)
        polygon=QPolygonF([QPointF(left+(x-xmin)/xspan*(right-left),bottom-(y-lo)/span*(bottom-top))for x,y in points])
        p.setPen(QPen(QColor('#7897b3'),1.6));p.drawPolyline(polygon)
        for point in polygon:p.drawEllipse(point,1.5,1.5)
        p.setPen(QColor('#8995a6'));p.drawText(2,top+8,f'{hi:.2g}');p.drawText(2,bottom,f'{lo:.2g}')
        p.drawText(left,bottom+20,str(xmin));p.drawText(right-30,bottom+20,str(points[-1][0]))


class RunPage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.manager=None;self.records={};layout=QVBoxLayout(self)
        title=QLabel('Run · qualified V2606 N5');title.setObjectName('sectionTitle');layout.addWidget(title)
        row=QHBoxLayout();self.case=QLabel('Select or generate a fresh production case in Setup.');self.case.setWordWrap(True)
        row.addWidget(self.case,1);self.run=QPushButton('Run');self.run.setObjectName('primary');self.run.setEnabled(False)
        self.abort=QPushButton('Abort Run');self.abort.setEnabled(False);row.addWidget(self.run);row.addWidget(self.abort);layout.addLayout(row)
        self.state=QLabel('CREATED');layout.addWidget(self.state)
        self.failure=QLabel();self.failure.setObjectName('error');self.failure.setWordWrap(True);self.failure.setMaximumHeight(65)
        self.failure.setTextInteractionFlags(Qt.TextSelectableByMouse);layout.addWidget(self.failure);self.failure.hide()
        self.participants=QTableWidget(6,4);self.participants.setHorizontalHeaderLabels(['Participant','Status','PID','Exit'])
        self.participants.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.participants.verticalHeader().hide()
        self.participants.verticalHeader().setDefaultSectionSize(24);self.participants.setFixedHeight(185)
        self.participants.setEditTriggers(QTableWidget.NoEditTriggers)
        for i,name in enumerate(['Structure',*[f'Fluid-S{j}'for j in range(1,6)]]):
            for j,text in enumerate([name,'WAITING','—','—']):self.participants.setItem(i,j,QTableWidgetItem(text))
        self.participants.cellDoubleClicked.connect(self.open_log);layout.addWidget(self.participants)
        self.participants.setToolTip('Double-click participant to open its complete stdout log. Separate stderr log is in runtime/logs.')
        summary=QGroupBox('Coupling / Flow');grid=QGridLayout(summary);self.metrics={}
        for i,name in enumerate(['Physical Time','Coupled elapsed','Accepted Windows','Current Coupling Iteration','Force Residual','Displacement Residual','Rejected / Rollbacks','Elapsed Wall Time','ETA · ESTIMATE','GLOBAL MAX Co','GLOBAL MAX mesh Co']):
            box=QWidget();column=QVBoxLayout(box);column.addWidget(QLabel(name));value=QLabel('—');value.setObjectName('metricValue');column.addWidget(value);self.metrics[name]=value;grid.addWidget(box,i//4,i%4)
        layout.addWidget(summary)
        self.progress=QProgressBar();self.progress.setRange(0,10000);self.progress.setFormat('Accepted coupled time · %p%');layout.addWidget(self.progress)
        plots=QHBoxLayout();self.plots=[HistoryPlot('Force residual',1),HistoryPlot('Displacement residual',2),HistoryPlot('Max Co',3)]
        for p in self.plots:plots.addWidget(p)
        layout.addLayout(plots,1)
        self.resources=QLabel('CPU/RAM sampling · own launched PID tree only');self.resources.setWordWrap(True);layout.addWidget(self.resources)
        self.notice=QLabel('Run uses the saved case, not unsaved Setup edits. Abort is not a committed-state stop.\nABORTED RUN MAY NOT BE RESTARTABLE.');self.notice.setWordWrap(True);layout.addWidget(self.notice)

    def open_log(self,row,column):
        name=self.participants.item(row,0).text();record=self.records.get(name)
        if record:QDesktopServices.openUrl(QUrl.fromLocalFile(record['stdout_log']))

    def show_snapshot(self,s):
        def n(v):return '—'if v is None else f'{v:.6g}'if isinstance(v,(float,int))else str(v)
        values={'Physical Time':f"{s['physical_time']:.6f} / {s['target_physical_time']:.6f} s",
            'Coupled elapsed':f"{s['coupled_elapsed']:.6f} / {s['target_duration']:.6f} s",
            'Accepted Windows':f"{s['accepted_windows']} / {s['target_windows']}",
            'Current Coupling Iteration':str(s['iteration']),'Force Residual':n(s['force_residual']),
            'Displacement Residual':n(s['displacement_residual']),'Rejected / Rollbacks':str(s['rollback_count']),
            'Elapsed Wall Time':f"{s['elapsed_wall_s']:.1f} s",'ETA · ESTIMATE':f"{s['eta_estimate_s']:.0f} s · ESTIMATE"if s['eta_estimate_s'] is not None else 'warming up (<20 windows)',
            'GLOBAL MAX Co':f"{n(s['max_Co'])} · {s['max_Co_slice'] or '—'}",'GLOBAL MAX mesh Co':f"{n(s['max_mesh_Co'])} · {s['max_mesh_Co_slice'] or '—'}"}
        for key,value in values.items():self.metrics[key].setText(value)
        self.progress.setValue(round(10000*s['progress']))
        for p in self.plots:p.set_history(s['history'])
        self.show_participants(s.get('participants',{}));self.state.setText(s.get('state',''))
        r=s.get('resources')
        if r:self.resources.setText(f"System CPU {r['system_cpu_percent']:.1f}%  |  Own solvers CPU {r['solver_cpu_percent']:.1f}% (sum across cores)  |  Own RSS {r['solver_rss_bytes']/2**20:.1f} MiB  |  System RAM {r['system_ram_percent']:.1f}%  |  Disk free {r['disk_free_bytes']/2**30:.1f} GiB")

    def show_participants(self,records):
        self.records=records
        colors={'WAITING':'#8995a6','STARTING':'#7897b3','CONNECTED':'#7897b3','RUNNING':'#7897b3','EXITED':'#92ad99','FAILED':'#d79a94','ABORTED':'#c9aa7d'}
        for i in range(6):
            name=self.participants.item(i,0).text();r=records.get(name,{})
            status=r.get('status','WAITING')
            self.participants.item(i,1).setText('● '+status);self.participants.item(i,1).setForeground(QColor(colors[status]))
            self.participants.item(i,2).setText(str(r.get('PID','—')))
            self.participants.item(i,3).setText('—'if r.get('exit_code')is None else str(r['exit_code']))
