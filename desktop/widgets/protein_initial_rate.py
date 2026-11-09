"""Explicit, asynchronous Phase C.1 controls; no automatic fitting or network."""
from dataclasses import asdict
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from protein_engineering.initial_rate import RateConfig


def label(text):
    widget=QLabel(text)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


class InitialRatePanel(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host=host
        self.courses=[]
        self.result=None
        self.calibration=None
        self._saved_fingerprint=None
        layout=QVBoxLayout(self)
        layout.addWidget(label("可用：C.1 显式区间信号斜率、空白校正、条件充分时标定换算、QC 与派生记录。线性不证明初始速率有效；不自动选择最高 R² 区间。Michaelis–Menten、WT/变体统计比较仍为规划中。"))
        row=QHBoxLayout()
        self.refresh_button=QPushButton("刷新已导入时间序列")
        self.course=QComboBox()
        row.addWidget(self.refresh_button)
        row.addWidget(self.course,1)
        layout.addLayout(row)
        self.raw_text=QPlainTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setMaximumHeight(120)
        self.raw_text.setPlaceholderText("选择单一批次/样品/孔位/底物/生物重复/技术重复的原始观测；不跨重复平均。")
        layout.addWidget(self.raw_text)
        form=QFormLayout()
        self.confirm_timecourse=QCheckBox("我确认所选记录是时间序列，而非终点值或跨重复拼接")
        form.addRow(self.confirm_timecourse)
        window=QHBoxLayout()
        self.start=QLineEdit(); self.end=QLineEdit()
        self.start.setPlaceholderText("起始时间（必填）")
        self.end.setPlaceholderText("结束时间（必填）")
        self.unit=label("单位：选择序列后显示")
        window.addWidget(self.start);window.addWidget(self.end);window.addWidget(self.unit)
        form.addRow("拟合区间（含两端）",window)
        self.blank_mode=QComboBox()
        for text,value in [("不校正（不代表背景为零）","none"),("使用每行已报告 blank_signal","per_observation"),("另选同时间点空白序列","matched_time")]:
            self.blank_mode.addItem(text,value)
        form.addRow("显式空白方式",self.blank_mode)
        self.blank_course=QComboBox()
        form.addRow("匹配空白序列",self.blank_course)
        self.missing=QComboBox()
        self.missing.addItem("缺失则不估计（默认）","fail")
        self.missing.addItem("显式排除缺失并记录原因","exclude")
        form.addRow("缺失处理",self.missing)
        self.exclusions=QLineEdit()
        self.exclusions.setPlaceholderText('可留空；JSON：{"observation_id":"人工排除理由"}')
        form.addRow("逐条排除（可选）",self.exclusions)
        layout.addLayout(form)
        row=QHBoxLayout()
        self.calibration_button=QPushButton("导入标定元数据 JSON（可选）")
        self.clear_calibration_button=QPushButton("清除当前标定选择")
        row.addWidget(self.calibration_button);row.addWidget(self.clear_calibration_button)
        layout.addLayout(row)
        self.calibration_label=label("未选择标定：仅报告信号/时间，不换算产物或酶活。")
        layout.addWidget(self.calibration_label)
        row=QHBoxLayout()
        self.analyze_button=QPushButton("计算所选区间斜率与 QC")
        self.save_button=QPushButton("保存独立派生分析记录")
        self.read_saved_button=QPushButton("读取已保存派生记录")
        row.addWidget(self.analyze_button);row.addWidget(self.save_button)
        row.addWidget(self.read_saved_button)
        layout.addLayout(row)
        self.result_text=QPlainTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(210)
        layout.addWidget(self.result_text)
        self._controls=[self.refresh_button,self.course,self.start,self.end,self.blank_mode,self.blank_course,
                        self.missing,self.exclusions,self.calibration_button,self.clear_calibration_button,self.confirm_timecourse,self.read_saved_button]
        self.refresh_button.clicked.connect(self.refresh)
        self.course.currentIndexChanged.connect(self._selected)
        for widget in (self.start,self.end,self.exclusions):
            widget.textChanged.connect(self.invalidate)
        for widget in (self.blank_mode,self.blank_course,self.missing):
            widget.currentIndexChanged.connect(self.invalidate)
        self.confirm_timecourse.toggled.connect(self.invalidate)
        self.calibration_button.clicked.connect(self.choose_calibration)
        self.clear_calibration_button.clicked.connect(self.clear_calibration)
        self.analyze_button.clicked.connect(self.analyze)
        self.save_button.clicked.connect(self.save)
        self.read_saved_button.clicked.connect(self.read_saved)
        self.set_busy(False)

    def set_busy(self,busy):
        enabled=not busy and self.host.store is not None
        for widget in self._controls:
            widget.setEnabled(enabled)
        self.analyze_button.setEnabled(enabled and self.course.currentData() is not None)
        self.save_button.setEnabled(enabled and self.result is not None and self.result.get("status")=="ESTIMATED"
            and self.result["analysis_metadata"]["analysis_fingerprint"]!=self._saved_fingerprint)

    def invalidate(self,*_):
        self.result=None
        self.result_text.clear()
        self.save_button.setEnabled(False)

    def reset(self):
        self.invalidate()
        self._saved_fingerprint=None
        self.courses=[]
        self.confirm_timecourse.setChecked(False)
        self.course.clear();self.blank_course.clear();self.raw_text.clear()
        self.clear_calibration()
        self.set_busy(False)

    def refresh(self):
        if self.host.store:
            self.invalidate()
            store=self.host.store
            self.host._run(store.time_courses,self._loaded)

    def _loaded(self,courses):
        self.courses=courses
        self.course.clear();self.blank_course.clear()
        self.blank_course.addItem("未选择",None)
        for c in courses:
            text=f"{c['batch_id']} / {c['sample_id']} / bio={c['biological_replicate']} / tech={c['technical_replicate']} / 孔={c['well_id']} / S={c['substrate_concentration']} {c['substrate_concentration_unit']} / {len(c['records'])} 点"
            self.course.addItem(text,c["series_id"])
            self.blank_course.addItem(text,c["series_id"])
        self._selected()
        self.host.status.setText(f"已读取 {len(courses)} 条独立时间序列；尚未计算。")
        self.set_busy(False)

    def _selected(self,*_):
        self.invalidate()
        self.confirm_timecourse.setChecked(False)
        c=next((c for c in self.courses if c["series_id"]==self.course.currentData()),None)
        self.unit.setText("时间单位："+str(c["time_unit"]) if c else "单位：选择序列后显示")
        self.raw_text.setPlainText((f"共 {len(c['records'])} 条，显示前 500 条；分析使用完整序列。\n"+
            json.dumps(c["records"][:500],ensure_ascii=False,indent=2)) if c else "")
        self.set_busy(self.host._busy)

    def choose_calibration(self):
        if not self.host.store:
            return
        path,_=QFileDialog.getOpenFileName(self,"选择有来源与有效范围的标定元数据（只读）","","JSON (*.json)")
        if path:
            self.invalidate()
            store=self.host.store
            self.host._run(lambda:store.import_calibration(path),self._calibration_loaded)

    def _calibration_loaded(self,c):
        self.calibration=c
        self.invalidate()
        self.calibration_label.setText("标定已保存原件快照："+json.dumps(asdict(c),ensure_ascii=False))

    def clear_calibration(self):
        self.calibration=None
        self.invalidate()
        self.calibration_label.setText("未选择标定：仅报告信号/时间，不换算产物或酶活；已导入原件不会删除。")

    def analyze(self):
        if not self.host.store or not self.course.currentData():
            return
        self.invalidate()
        try:
            exclusions=json.loads(self.exclusions.text()) if self.exclusions.text().strip() else {}
            if not isinstance(exclusions,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in exclusions.items()):
                raise ValueError("排除项需为 observation_id:理由 的 JSON 对象")
            c=next(c for c in self.courses if c["series_id"]==self.course.currentData())
            cfg=RateConfig(float(self.start.text()),float(self.end.text()),c["time_unit"],
                blank_mode=self.blank_mode.currentData(),missing_policy=self.missing.currentData(),exclusions=tuple(exclusions.items()),
                measurement_kind="TIME_COURSE" if self.confirm_timecourse.isChecked() else "UNCONFIRMED")
            blank=self.blank_course.currentData() if cfg.blank_mode=="matched_time" else None
            series_id=self.course.currentData()
            store,calibration=self.host.store,self.calibration
            self.host._run(lambda:store.analyze_time_course(series_id,cfg,blank_series_id=blank,calibration=calibration),self._analyzed)
        except (ValueError,TypeError,StopIteration) as exc:
            self.host.status.setText("尚未计算；请检查区间/排除配置："+str(exc))

    def _analyzed(self,result):
        self.result=result
        lines=["状态："+result["status"],"初始速率生化有效性：尚未建立；需实验与人工核实。"]
        fit=result["derived_initial_rate"]
        if fit:
            lines += [f"N={fit['n']}；斜率={fit['slope']:.8g} {fit['rate_unit']}；截距={fit['intercept']:.8g} {fit['intercept_unit']}",
                f"R²={fit['r_squared']}；RMSE={fit['rmse']:.8g}；斜率标准误={fit['slope_standard_error']:.8g}"]
            if fit["product_rate"]:
                p=fit["product_rate"]
                lines.append(f"经显式标定的产物浓度速率={p['slope']:.8g} {p['rate_unit']}")
        lines += [i["code"]+"："+i["message"] for i in result["reasons"]+result["quality_control"]]
        lines += ["\n完整计算记录（残差、包含/排除理由、原件及配置）：",json.dumps(result,ensure_ascii=False,indent=2)]
        self.result_text.setPlainText("\n".join(lines))
        self.host.status.setText("计算完成，尚未保存派生记录。" if fit else "不能估计；原因已列出，未补造数值。")
        self.set_busy(False)

    def save(self):
        if self.host.store and self.result and self.result["status"]=="ESTIMATED":
            store,result=self.host.store,self.result
            self.host._run(lambda:store.save_initial_rate(result),self._saved)

    def _saved(self,identifier):
        self._saved_fingerprint=self.result["analysis_metadata"]["analysis_fingerprint"]
        self.host.status.setText("独立派生记录已保存："+identifier+"；原始观测未改写。")
        # Keep displayed evidence, require a new calculation before another save.
        self.save_button.setEnabled(False)

    def read_saved(self):
        if self.host.store:
            self.invalidate()
            store=self.host.store
            self.host._run(store.initial_rate_records,self._show_saved)

    def _show_saved(self,records):
        self.result_text.setPlainText(f"已保存 {len(records)} 个独立派生记录（只读，显示前 100 个）：\n"+
            json.dumps(records[:100],ensure_ascii=False,indent=2))
        self.host.status.setText("已读取历史派生记录；未重新分析，未覆盖原始观测。")
