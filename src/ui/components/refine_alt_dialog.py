import os
import shutil
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QCheckBox, QSpinBox, QGroupBox, QComboBox
)
from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtGui import QPixmap, QImageReader

from src.utils.img_utils import load_thumbnail_from_path
from src.workers.alt_refiner_worker import AltRefinerWorker
from src.core.alt_manager import AltManager

PREVIEW_W = 240
PREVIEW_H = 320


def _read_size_str(path):
    if not path:
        return ""
    reader = QImageReader(path)
    sz = reader.size()
    if sz.isValid():
        return f"{sz.width()} × {sz.height()}"
    return ""


def _make_thumb_label(path=None):
    lbl = QLabel()
    lbl.setFixedSize(PREVIEW_W, PREVIEW_H)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet("border: 1px solid rgba(255,255,255,30); background: rgba(0,0,0,60);")
    if path:
        qimg = load_thumbnail_from_path(path, PREVIEW_W, PREVIEW_H)
        if qimg and not qimg.isNull():
            lbl.setPixmap(QPixmap.fromImage(qimg).scaled(
                PREVIEW_W, PREVIEW_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
    return lbl


class RefineAltDialog(QDialog):
    def __init__(self, parent=None, main_path=None, alt_path=None,
                 output_path=None, series_path=None, chapter_name=None,
                 main_file=None, alt_rel_path=None, fix_rel_path=None,
                 reference_paths=None):
        super().__init__(parent)
        self.setWindowTitle("Refine Alt")
        self.resize(820, 640)

        self.main_path = main_path
        self.alt_path = alt_path
        self.output_path = output_path
        self.series_path = series_path
        self.chapter_name = chapter_name
        self.main_file = main_file
        self.alt_rel_path = alt_rel_path
        self.fix_rel_path = fix_rel_path
        self.reference_paths = reference_paths or [main_path]

        # Temp file lives in .cache/alt_refine/ — never in the alt directory
        op = Path(output_path)
        cache_dir = Path(".cache/alt_refine")
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._temp_path = str(cache_dir / (op.stem + '_preview_tmp' + op.suffix))

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Preview row ──────────────────────────────────────────────────────
        preview_row = QHBoxLayout()
        preview_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_row.setSpacing(16)

        for title, path in [("Reference", self.main_path), ("Alt", alt_path)]:
            col = QVBoxLayout()
            col.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.setSpacing(4)
            
            if title == "Reference":
                title_row = QHBoxLayout()
                title_row.addWidget(QLabel("Reference:", alignment=Qt.AlignmentFlag.AlignRight))
                
                self.ref_combo = QComboBox()
                self.ref_combo.setMinimumWidth(120)
                for rp in self.reference_paths:
                    self.ref_combo.addItem(Path(rp).name, rp)
                
                # Select current
                for i in range(self.ref_combo.count()):
                    if self.ref_combo.itemData(i) == self.main_path:
                        self.ref_combo.setCurrentIndex(i)
                        break
                
                self.ref_combo.currentIndexChanged.connect(self._on_ref_changed)
                title_row.addWidget(self.ref_combo)
                col.addLayout(title_row)
            else:
                col.addWidget(QLabel(title, alignment=Qt.AlignmentFlag.AlignCenter))

            thumb = _make_thumb_label(path)
            col.addWidget(thumb)
            
            if title == "Reference":
                self.ref_thumb = thumb
                # Make thumbnail clickable to cycle or trigger selection? 
                # Request says "clicking it should allow it to be changed with combobox"
                # We'll just focus the combobox or show its popup? 
                # QComboBox.showPopup() is good.
                self.ref_thumb.setCursor(Qt.CursorShape.PointingHandCursor)
                self.ref_thumb.mousePressEvent = lambda e: self.ref_combo.showPopup()

            size_lbl = QLabel(_read_size_str(path))
            size_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            size_lbl.setStyleSheet("color: rgba(255,255,255,120); font-size: 11px;")
            col.addWidget(size_lbl)
            
            if title == "Reference":
                self.ref_size_lbl = size_lbl
                
            preview_row.addLayout(col)

        # Result column (empty until refined)
        result_col = QVBoxLayout()
        result_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_col.setSpacing(4)
        result_col.addWidget(QLabel("Result", alignment=Qt.AlignmentFlag.AlignCenter))
        self.result_thumb = _make_thumb_label()
        self.result_thumb.setText("–")
        self.result_thumb.setStyleSheet(
            "border: 1px solid rgba(255,255,255,30); background: rgba(0,0,0,60);"
            "color: rgba(255,255,255,60); font-size: 24px;"
        )
        result_col.addWidget(self.result_thumb)
        self.result_size_lbl = QLabel("–")
        self.result_size_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_size_lbl.setStyleSheet("color: rgba(255,255,255,120); font-size: 11px;")
        result_col.addWidget(self.result_size_lbl)
        preview_row.addLayout(result_col)

        layout.addLayout(preview_row)

        # ── Options ──────────────────────────────────────────────────────────
        opts_group = QGroupBox("Options")
        opts_layout = QVBoxLayout(opts_group)
        opts_layout.setSpacing(6)

        self.cb_color = QCheckBox("Fix Color  (LAB color transfer from original)")
        self.cb_color.setChecked(True)
        opts_layout.addWidget(self.cb_color)

        self.cb_resize = QCheckBox("Auto Resize  (ECC affine alignment, fallback to ratio fit)")
        self.cb_resize.setChecked(True)
        opts_layout.addWidget(self.cb_resize)

        manual_row = QHBoxLayout()
        self.cb_manual = QCheckBox("Manual Size:")
        self.cb_manual.toggled.connect(self._on_manual_toggled)
        manual_row.addWidget(self.cb_manual)
        manual_row.addWidget(QLabel("W:"))
        self.spin_w = QSpinBox()
        self.spin_w.setRange(1, 9999)
        self.spin_w.setValue(800)
        self.spin_w.setEnabled(False)
        self.spin_w.setFixedWidth(65)
        manual_row.addWidget(self.spin_w)
        manual_row.addWidget(QLabel("H:"))
        self.spin_h = QSpinBox()
        self.spin_h.setRange(1, 9999)
        self.spin_h.setValue(1200)
        self.spin_h.setEnabled(False)
        self.spin_h.setFixedWidth(65)
        manual_row.addWidget(self.spin_h)
        manual_row.addStretch()
        opts_layout.addLayout(manual_row)

        layout.addWidget(opts_group)

        # ── Status ───────────────────────────────────────────────────────────
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.refine_btn = QPushButton("Refine")
        self.refine_btn.setDefault(True)
        self.refine_btn.clicked.connect(self._on_refine)
        self.save_btn = QPushButton("Save")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.refine_btn)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _on_ref_changed(self, index):
        new_path = self.ref_combo.itemData(index)
        if new_path == self.main_path:
            return
        
        self.main_path = new_path
        
        # Update UI
        qimg = load_thumbnail_from_path(new_path, PREVIEW_W, PREVIEW_H)
        if qimg and not qimg.isNull():
            self.ref_thumb.setPixmap(QPixmap.fromImage(qimg).scaled(
                PREVIEW_W, PREVIEW_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
        else:
            self.ref_thumb.setPixmap(QPixmap())
            
        self.ref_size_lbl.setText(_read_size_str(new_path))
        
        # Reset result
        self.result_thumb.setPixmap(QPixmap())
        self.result_thumb.setText("–")
        self.result_size_lbl.setText("–")
        self.save_btn.setEnabled(False)
        self._set_status("Reference changed. Click Refine to update.")

    def _on_manual_toggled(self, checked):
        self.spin_w.setEnabled(checked)
        self.spin_h.setEnabled(checked)
        if checked:
            self.cb_resize.setChecked(False)
            self.cb_resize.setEnabled(False)
        else:
            self.cb_resize.setEnabled(True)

    def _on_refine(self):
        if not self.cb_color.isChecked() and not self.cb_resize.isChecked() and not self.cb_manual.isChecked():
            self._set_status("Select at least one option.", error=True)
            return

        self.refine_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self._set_status("Processing…")

        manual_size = None
        if self.cb_manual.isChecked():
            manual_size = (self.spin_w.value(), self.spin_h.value())

        worker = AltRefinerWorker(
            main_path=self.main_path,
            alt_path=self.alt_path,
            output_path=self._temp_path,
            fix_color=self.cb_color.isChecked(),
            auto_resize=self.cb_resize.isChecked(),
            manual_size=manual_size,
        )
        worker.signals.finished.connect(self._on_preview_ready)
        worker.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(worker)

    def _on_preview_ready(self, temp_path):
        qimg = load_thumbnail_from_path(temp_path, PREVIEW_W, PREVIEW_H)
        if qimg and not qimg.isNull():
            self.result_thumb.setStyleSheet(
                "border: 1px solid rgba(255,255,255,30); background: rgba(0,0,0,60);"
            )
            self.result_thumb.setText("")
            self.result_thumb.setPixmap(QPixmap.fromImage(qimg).scaled(
                PREVIEW_W, PREVIEW_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
        self.result_size_lbl.setText(_read_size_str(temp_path))
        self._set_status("Preview ready. Click Save to commit.")
        self.refine_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)

    def _on_save(self):
        try:
            if os.path.exists(self._temp_path):
                Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
                # copy2 + remove instead of os.replace so a lingering QImageReader
                # read-lock on the temp file doesn't block the operation on Windows
                shutil.copy2(self._temp_path, self.output_path)
                try:
                    os.remove(self._temp_path)
                except OSError:
                    pass
        except OSError as e:
            self._set_status(f"Save failed: {e}", error=True)
            return
        AltManager.register_alt_fix(
            self.series_path,
            self.chapter_name,
            self.main_file,
            self.alt_rel_path,
            self.fix_rel_path,
        )
        self.accept()

    def _on_error(self, message):
        self._set_status(f"Error: {message}", error=True)
        self.refine_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)

    def _set_status(self, text, error=False):
        self.status_label.setText(text)
        color = "#ff6b6b" if error else "#aaaaaa"
        self.status_label.setStyleSheet(f"color: {color};")

    def reject(self):
        # Clean up temp file if user cancels without saving
        if os.path.exists(self._temp_path):
            try:
                os.remove(self._temp_path)
            except OSError:
                pass
        super().reject()
