"""Explicit C.2A controls inside the existing seventh Desktop page."""
from datetime import datetime, timezone
import json

from PySide6.QtCore import QPointF, Qt, Slot
from PySide6.QtGui import QColor, QPainter, QPolygonF
from PySide6.QtWidgets import (QCheckBox,QFileDialog,QFormLayout,QHBoxLayout,QLabel,QLineEdit,
    QPlainTextEdit,QPushButton,QTableWidget,QTableWidgetItem,QVBoxLayout,QWidget)

from desktop import protein_mm as application
from protein_engineering.mm_kinetics import FitReview


def label(text):
    value=QLabel(text);value.setWordWrap(True);value.setTextFormat(Qt.TextFormat.PlainText)
    return value


class FitPlot(QWidget):
    def __init__(self):
        super().__init__();self.result=None;self.setMinimumHeight(290);self.setMinimumWidth(600)

    def set_result(self,result):
        self.result=result;self.update()

    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor("white"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:plots=application.chart_geometry(self.result,max(self.width(),600),290)
        except (ValueError,OverflowError,ZeroDivisionError):plots=[]
        if not plots:
            painter.drawText(20,35,"尚无正常拟合曲线；参数区间未计算。")
            return
        for q in plots:
            l,t,r,b=q['rectangle'];painter.setPen(QColor('#555555'))
            painter.drawPolyline(QPolygonF([QPointF(l,t),QPointF(l,b),QPointF(r,b)]))
            painter.drawText(QPointF(l,22),q['title']);painter.drawText(QPointF(l,t-6),q['y_label'])
            painter.drawText(QPointF(l,b+40),q['x_label'])
            painter.drawText(QPointF(l,b+17),f"{q['x_range'][0]:.5g}")
            painter.drawText(QPointF(r-45,b+17),f"{q['x_range'][1]:.5g}")
            painter.drawText(QPointF(l-61,t+12),f"{q['y_range'][1]:.5g}")
            painter.drawText(QPointF(l-61,b),f"{q['y_range'][0]:.5g}")
            painter.setPen(QColor('#176b9c'))
            painter.drawPolyline(QPolygonF([QPointF(x,y) for x,y in q['line']]))
            painter.setPen(QColor('#b65320'));painter.setBrush(QColor('#b65320'))
            for x,y in q['scatter']:painter.drawEllipse(QPointF(x,y),3,3)


class MMFitPanel(QWidget):
    def __init__(self,host):
        super().__init__();self.host=host;self.snapshot=None;self.result=None;self._epoch=0;self._pending=False
        self._pending_operation=None
        layout=QVBoxLayout(self)
        layout.addWidget(label("C.2A：经典单底物 Michaelis–Menten 条件性拟合。只读核验已保存 C.1 记录，不自动选择数据、不写入数据库。"))
        layout.addWidget(label("NOT_ESTABLISHED 保持不变；确认不是实验有效性证明。未启用参数区间、真实 Monte Carlo、WT 比较、AI 或网络调用。"))
        row=QHBoxLayout();self.refresh_button=QPushButton("刷新已保存 C.1 记录")
        self.verify_button=QPushButton("核验所选来源与条件")
        row.addWidget(self.refresh_button);row.addWidget(self.verify_button);layout.addLayout(row)
        self.table=QTableWidget(0,11)
        self.table.setHorizontalHeaderLabels(["analysis_id","样品","批次","生物重复","技术重复","底物","底物单位","产物速率","速率单位","来源 SHA256","变体（核验后）"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True);self.table.setMaximumHeight(210);layout.addWidget(self.table)
        self.status=label("尚未刷新。没有自动预选记录；必须明确选择 analysis_id 并核验。")
        layout.addWidget(self.status)
        self.source_text=QPlainTextEdit();self.source_text.setReadOnly(True);self.source_text.setMaximumHeight(150)
        layout.addWidget(self.source_text)
        form=QFormLayout();self.reviewer=QLineEdit();self.review_time=QLineEdit();self.rationale=QLineEdit()
        self.review_time.setPlaceholderText("带 Z 或 +00:00 的 UTC 审核时间")
        form.addRow("审核人员（必填）",self.reviewer)
        time_row=QHBoxLayout();time_row.addWidget(self.review_time);self.now_button=QPushButton("填入当前 UTC")
        time_row.addWidget(self.now_button);form.addRow("审核时间",time_row)
        form.addRow("所选数据与条件性使用依据（必填）",self.rationale)
        self.acknowledge=QCheckBox("我接受初始速率有效性仍为 NOT_ESTABLISHED；本次只是条件性分析")
        self.direction=QCheckBox("已审阅标定与实验记录，确认产物生成方向 PRODUCT_FORMATION；不取负速率绝对值")
        form.addRow(self.acknowledge);form.addRow(self.direction);layout.addLayout(form)
        self.fit_button=QPushButton("按当前审核显式执行 C.2A 拟合")
        layout.addWidget(self.fit_button)
        self.parameter_label=label("Km / Vmax 尚未计算；参数区间未计算。")
        layout.addWidget(self.parameter_label)
        self.result_text=QPlainTextEdit();self.result_text.setReadOnly(True);self.result_text.setMaximumHeight(230)
        layout.addWidget(self.result_text)
        self.plot=FitPlot();layout.addWidget(self.plot)
        self.predictions=QTableWidget(0,5)
        self.predictions.setHorizontalHeaderLabels(["analysis_id","底物浓度","观察速率","拟合预测速率","残差（观察−拟合）"])
        self.predictions.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.predictions.setMaximumHeight(170)
        layout.addWidget(self.predictions)
        row=QHBoxLayout();self.html_button=QPushButton("导出本地 HTML 报告")
        self.json_button=QPushButton("导出严格 JSON 报告")
        row.addWidget(self.html_button);row.addWidget(self.json_button);layout.addLayout(row)
        self._controls=[self.refresh_button,self.verify_button,self.table,self.reviewer,self.review_time,self.rationale,
            self.now_button,self.acknowledge,self.direction]
        self.refresh_button.clicked.connect(self.refresh);self.verify_button.clicked.connect(self.verify)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        for widget in (self.reviewer,self.review_time,self.rationale):widget.textChanged.connect(self._review_edited)
        for widget in (self.acknowledge,self.direction):widget.toggled.connect(self._review_toggled)
        self.now_button.clicked.connect(lambda:self.review_time.setText(datetime.now(timezone.utc).isoformat()))
        self.fit_button.clicked.connect(self.fit)
        self.html_button.clicked.connect(lambda:self.export('html'));self.json_button.clicked.connect(lambda:self.export('json'))
        self.set_busy(False)

    def _path(self):
        return str(self.host.store.path) if self.host.store is not None else None

    def selected_ids(self):
        return tuple(sorted(self.table.item(i.row(),0).data(Qt.ItemDataRole.UserRole)
            for i in self.table.selectionModel().selectedRows()))

    def _discard_result(self):
        self._epoch+=1;self.result=None;self.result_text.clear();self.plot.set_result(None);self.predictions.setRowCount(0)
        self.parameter_label.setText("Km / Vmax 尚未计算；参数区间未计算。")

    def _clear_checks(self):
        for box in (self.acknowledge,self.direction):
            box.blockSignals(True);box.setChecked(False);box.blockSignals(False)

    def _selection_changed(self):
        self._discard_result();self.snapshot=None;self.source_text.clear();self._clear_checks()
        self.review_time.clear();self.rationale.clear()
        self.status.setText(f"已选择 {len(self.selected_ids())} 个明确 ID；旧审核失效，请重新核验。")
        self.set_busy(self.host._busy)

    def _review_edited(self,*_):
        self._discard_result();self._clear_checks();self.set_busy(self.host._busy)

    def _review_toggled(self,*_):
        self._discard_result();self.set_busy(self.host._busy)

    def reset(self):
        self._pending=False
        self._pending_operation=None
        self._discard_result();self.snapshot=None;self._clear_checks()
        self.table.blockSignals(True);self.table.setRowCount(0);self.table.blockSignals(False)
        self.source_text.clear()
        for w in (self.reviewer,self.review_time,self.rationale):w.clear()
        self.status.setText("数据库或保存记录已变化；旧审核失效，旧任务结果按 STALE_OPERATION 丢弃；请刷新并重新选择、核验和审核。")
        self.set_busy(self.host._busy)

    def set_busy(self,busy):
        available=not busy and not self._pending and self.host.store is not None
        for widget in self._controls:widget.setEnabled(available)
        self.verify_button.setEnabled(available and bool(self.selected_ids()))
        reviewed=bool(self.snapshot and self.snapshot['dependencies']['available'] and self.reviewer.text().strip()
            and self.review_time.text().strip() and self.rationale.text().strip() and self.acknowledge.isChecked() and self.direction.isChecked())
        self.fit_button.setEnabled(available and reviewed)
        for b in (self.html_button,self.json_button):b.setEnabled(available and self.result is not None)

    def _task(self,function,done,*,exporting=False):
        if self.host._busy or self._pending or self.host.store is None:return
        epoch,path=self._epoch,self._path();self._pending=True
        token=[None]
        def invoke():
            try:return dict(ok=True,value=function())
            except Exception as exc:return dict(ok=False,error=str(exc),io_error=isinstance(exc,OSError))
        def complete(response):
            if token[0]!=self._pending_operation:
                self.host.operation_history[token[0]]['status']='STALE_OPERATION'
                return
            self._pending=False
            self._pending_operation=None
            if epoch!=self._epoch or path!=self._path():
                self.host.operation_history[token[0]]['status']='STALE_OPERATION'
                self.status.setText("输入/审核已变化；旧后台结果已丢弃，请重新审核。")
            elif response['ok']:
                try:done(response['value'])
                except Exception as exc:
                    self._discard_result();self.snapshot=None;self._clear_checks()
                    self.status.setText("返回内容未通过展示完整性检查；未保留正常结果："+str(exc))
            else:
                if not exporting or not response['io_error']:
                    self._discard_result();self.snapshot=None;self._clear_checks()
                prefix=('报告导出未完成；已核验计算结果保留：' if response['io_error'] else '报告导出未完成；来源/结果失效：') if exporting else '未完成（没有绕过来源或数值核验）：'
                self.status.setText(prefix+response['error'])
            self.set_busy(self.host._busy)
        def abandoned(status):
            if token[0]!=self._pending_operation:return
            self._pending=False
            self._pending_operation=None
            self._discard_result();self.snapshot=None;self._clear_checks()
            self.status.setText(status+'：后台操作失效；请重新核验。')
            self.set_busy(self.host._busy)
        token[0]=self.host._run(invoke,complete,task_type='C2A_EXPORT' if exporting else 'C2A_'+done.__name__.strip('_').upper(),
            input_snapshot=dict(epoch=epoch,path=path,analysis_ids=self.selected_ids(),
                input_sha256=self.snapshot.get('input_sha256') if self.snapshot else None),abandoned=abandoned)
        self._pending_operation=token[0]
        if token[0] is None:self._pending=False

    def refresh(self):
        if self.host._busy or self._pending or self.host.store is None:return
        self.reset();path=self._path()
        self._task(lambda:application.list_saved_rates(path),self._loaded)

    def _loaded(self,records):
        self.table.blockSignals(True);self.table.setSortingEnabled(False);self.table.setRowCount(0)
        for record in records:
            c1=record.get('result',{});d=c1.get('derived_initial_rate') or {};raw=c1.get('raw_observations') or []
            rate=d.get('product_rate') or {};ident=record['analysis_id']
            source=", ".join(sorted({str(r.get('source_sha256','')) for r in raw}))
            values=[ident,d.get('sample_id'),d.get('batch_id'),d.get('biological_replicate'),d.get('technical_replicate'),
                d.get('substrate_concentration'),d.get('substrate_concentration_unit'),rate.get('slope'),rate.get('rate_unit'),source,"待核验"]
            row=self.table.rowCount();self.table.insertRow(row)
            for col,value in enumerate(values):
                item=QTableWidgetItem("缺失" if value is None else str(value));item.setData(Qt.ItemDataRole.UserRole,ident)
                self.table.setItem(row,col,item)
        self.table.setSortingEnabled(True);self.table.clearSelection();self.table.blockSignals(False)
        self.status.setText(f"已列出全部 {len(records)} 条已保存记录；尚未核验，未自动预选或去重。")

    def verify(self):
        if self.host._busy or self._pending or not self.selected_ids():return
        ids,path=self.selected_ids(),self._path();self._discard_result();self.snapshot=None;self._clear_checks()
        self.status.setText("正在只读核验所选来源与 C.1 快照…")
        self._task(lambda:application.verify_selection(path,ids),self._verified)

    def _verified(self,value):
        self.snapshot=value
        self.source_text.setPlainText(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))
        by_id={r['analysis_id']:r for r in value['sources']}
        self.table.blockSignals(True);sorting=self.table.isSortingEnabled();self.table.setSortingEnabled(False)
        for row in range(self.table.rowCount()):
            ident=self.table.item(row,0).data(Qt.ItemDataRole.UserRole)
            if ident in by_id:self.table.item(row,10).setText(by_id[ident]['variant_id'])
        self.table.setSortingEnabled(sorting);self.table.blockSignals(False)
        contexts={(r['variant_id'],r['sample_id'],r['batch_id'],r['biological_replicate']) for r in value['sources']}
        units={(r['substrate_unit'],r['rate']['rate_unit']) for r in value['sources']}
        self.status.setText(f"来源核验完成：{len(value['ids'])} 条；上下文 {len(contexts)} 组，单位 {len(units)} 组。最终资格由原内核判定；请完成审核。"
            if value['dependencies']['available'] else value['dependencies']['message'])

    def fit(self):
        if self.host._busy or self._pending or not self.fit_button.isEnabled():return
        try:
            stamp=datetime.fromisoformat(self.review_time.text().strip().replace('Z','+00:00'))
            if stamp.utcoffset() is None or stamp.utcoffset().total_seconds()!=0:raise ValueError("时间必须为 UTC")
            review=FitReview(self.reviewer.text().strip(),self.review_time.text().strip(),self.rationale.text().strip(),
                self.snapshot['input_sha256'],direction="PRODUCT_FORMATION",acknowledge_not_established=True)
        except ValueError as exc:
            self.status.setText("审核未完成："+str(exc));return
        ids,path,expected=self.selected_ids(),self._path(),self.snapshot['input_sha256']
        database_sha256=self.snapshot['database_sha256']
        identity=self.snapshot['database_identity']
        self._discard_result();self.status.setText("正在重新核验来源并执行原 C.2A 内核…")
        self._task(lambda:application.run_fit(path,ids,expected,review,database_sha256,identity),self._fitted)

    def _fitted(self,result):
        self.result=application.checked_result(result,self.snapshot['input_sha256'])
        display={k:v for k,v in self.result.items() if k!='input_records'}
        self.result_text.setPlainText("C.1 validity=NOT_ESTABLISHED；参数区间未计算；不代表机制验证。\n"+
            json.dumps(display,ensure_ascii=False,indent=2,allow_nan=False))
        self.plot.set_result(self.result);self.predictions.setRowCount(0)
        if result['status']=='FIT_WITH_LIMITATIONS':
            parameters=result['parameters'];stats=result['statistics']
            self.parameter_label.setText(f"Km = {parameters['Km']:.9g} {parameters['Km_unit']}；Vmax = {parameters['Vmax']:.9g} {parameters['Vmax_unit']}；N={stats['n']}；R²={stats['r_squared']}；FIT_WITH_LIMITATIONS；区间未计算。")
            for row,p in enumerate(result['predictions']):
                self.predictions.insertRow(row)
                for col,k in enumerate(('analysis_id','substrate_concentration','observed_rate','fitted_rate','residual')):
                    self.predictions.setItem(row,col,QTableWidgetItem(str(p[k])))
        else:self.parameter_label.setText("NOT_ESTIMABLE：未提供可用参数或正常拟合曲线；请查看拒绝原因。")
        self.status.setText("拟合完成："+result['status']+"；结果仅保留本会话，未写入数据库。")

    def export(self,kind):
        if self.host._busy or self._pending or self.result is None:return
        try:
            result=application.checked_result(self.result,self.snapshot['input_sha256'])
        except Exception as exc:
            self._discard_result();self.snapshot=None;self._clear_checks()
            self.status.setText('报告导出失败：计算结果已失效，未写入文件：'+str(exc))
            self.set_busy(self.host._busy)
            return
        try:
            destination,_=QFileDialog.getSaveFileName(self,"仅新文件：本地 C.2A 报告（不上传）","protein-c2a-report."+kind,kind.upper()+" (*."+kind+")")
        except Exception as exc:
            self.status.setText('报告路径选择未完成；计算结果保留：'+str(exc))
            return
        if not destination:
            self.status.setText("已取消报告导出；未写入文件。")
            return
        path,ids,expected=self._path(),self.selected_ids(),self.snapshot['input_sha256']
        database_sha256=self.snapshot['database_sha256']
        identity=self.snapshot['database_identity']
        self._task(lambda:application.export_report(path,ids,expected,result,destination,kind,database_sha256,identity),
            lambda value:self.status.setText("本地报告已导出，未覆盖/上传。报告 SHA256："+value['report_sha256']),exporting=True)
