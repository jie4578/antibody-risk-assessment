from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout


class ColumnMappingDialog(QDialog):
    NONE_LABEL = "None"

    def __init__(self, columns, parent=None, initial_mapping=None):
        super().__init__(parent); self.setWindowTitle("Please confirm column mapping"); self.columns = list(columns); self.fields = {}
        layout = QVBoxLayout(self)
        for field in ("Antibody ID", "VH", "VL", "Sequence"):
            combo = QComboBox(); combo.addItem(self.NONE_LABEL, None)
            for column in self.columns: combo.addItem(str(column), column)
            self.fields[field] = combo
            canonical = {"Antibody ID": "antibody_id", "VH": "VH", "VL": "VL", "Sequence": "Sequence"}[field]
            preselected = (initial_mapping or {}).get(canonical)
            if preselected in self.columns: combo.setCurrentIndex(combo.findData(preselected))
            layout.addLayout(self._row(field, combo))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); buttons.accepted.connect(self._accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def _row(self, label, combo):
        form = QFormLayout(); form.addRow(label, combo); return form

    def _accept(self):
        selected = [combo.currentData() for combo in self.fields.values() if combo.currentData() is not None]
        if len(selected) != len(set(selected)): return
        if not any(self.fields[field].currentData() is not None for field in ("VH", "VL", "Sequence")): return
        self.accept()

    def mapping(self):
        names = {"Antibody ID": "antibody_id", "VH": "VH", "VL": "VL", "Sequence": "Sequence"}
        return {names[field]: combo.currentData() for field, combo in self.fields.items() if combo.currentData() is not None}
