import os
import shutil
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QCheckBox, QSpinBox, QGroupBox, QComboBox, QScrollArea, QWidget, QFrame, QProgressBar
)
from PyQt6.QtCore import Qt, QThreadPool, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap, QImageReader

from src.utils.img_utils import load_thumbnail_from_path
from src.workers.alt_refiner_worker import AltRefinerWorker
from src.core.alt_manager import AltManager

PREVIEW_W = 120
PREVIEW_H = 160

class BatchRefineRow(QFrame):
    def __init__(self, parent, main_path, alt_abs_path, alt_rel_path, reference_paths, 
                 series_path, chapter_name, main_file):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            BatchRefineRow {
                background-color: rgba(255, 255, 255, 5);
                border: 1px solid rgba(255, 255, 255, 10);
                border-radius: 12px;
                margin: 2px;
            }
            BatchRefineRow QLabel, BatchRefineRow QCheckBox {
                background: transparent;
            }
            BatchRefineRow:hover {
                background-color: rgba(255, 255, 255, 12);
                border: 1px solid rgba(255, 255, 255, 25);
            }
        """)
        
        self.main_path = main_path
        self.alt_abs_path = alt_abs_path
        self.alt_rel_path = alt_rel_path
        self.reference_paths = reference_paths
        self.series_path = series_path
        self.chapter_name = chapter_name
        self.main_file = main_file
        
        self.current_ref_path = main_path
        self.temp_output_path = None
        self.is_processed = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(15)

        # 1. Checkbox
        self.cb_active = QCheckBox()
        self.cb_active.setChecked(True)
        layout.addWidget(self.cb_active)

        # 2. Reference Selection
        ref_col = QVBoxLayout()
        ref_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ref_combo = QComboBox()
        self.ref_combo.setFixedWidth(100)
        for rp in reference_paths:
            self.ref_combo.addItem(Path(rp).name, rp)
        self.ref_combo.currentIndexChanged.connect(self._on_ref_changed)
        ref_col.addWidget(self.ref_combo)
        
        self.ref_thumb, self.ref_size_lbl, ref_widget = self._make_thumb(main_path)
        self.ref_thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ref_thumb.mousePressEvent = lambda e: self.ref_combo.showPopup()
        ref_col.addWidget(ref_widget)
        layout.addLayout(ref_col)

        # 3. Arrow
        self.arrow_lbl = QLabel("→")
        self.arrow_lbl.setStyleSheet("background: transparent;")
        layout.addWidget(self.arrow_lbl)

        # 4. Original Alt
        alt_col = QVBoxLayout()
        alt_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        alt_col.addWidget(QLabel("Original", alignment=Qt.AlignmentFlag.AlignCenter))
        _, _, alt_widget = self._make_thumb(alt_abs_path)
        alt_col.addWidget(alt_widget)
        layout.addLayout(alt_col)

        # 5. Result
        res_col = QVBoxLayout()
        res_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        res_col.addWidget(QLabel("Result", alignment=Qt.AlignmentFlag.AlignCenter))
        self.res_thumb, self.res_size_lbl, res_widget = self._make_thumb(None)
        res_col.addWidget(res_widget)
        layout.addLayout(res_col)

        # 6. Status
        self.status_lbl = QLabel("Wait")
        self.status_lbl.setFixedWidth(80)
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_lbl)

    def _make_thumb(self, path):
        container = QWidget()
        v_layout = QVBoxLayout(container)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(2)
        v_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl = QLabel()
        lbl.setFixedSize(PREVIEW_W, PREVIEW_H)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("border: 1px solid rgba(255,255,255,30); background: rgba(0,0,0,60);")
        v_layout.addWidget(lbl)

        size_lbl = QLabel("-")
        size_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        size_lbl.setStyleSheet("font-size: 10px; color: rgba(255,255,255,150); font-family: 'Consolas', monospace;")
        v_layout.addWidget(size_lbl)

        if path:
            self._update_thumb_and_size(lbl, size_lbl, path)
        return lbl, size_lbl, container

    def _update_thumb_and_size(self, lbl, size_lbl, path):
        # Update image size text
        reader = QImageReader(path)
        size = reader.size()
        if not size.isEmpty():
            size_lbl.setText(f"{size.width()}x{size.height()}")
        
        # Load thumbnail
        qimg = load_thumbnail_from_path(path, PREVIEW_W, PREVIEW_H)
        if qimg and not qimg.isNull():
            lbl.setPixmap(QPixmap.fromImage(qimg).scaled(
                PREVIEW_W, PREVIEW_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
        else:
            lbl.setPixmap(QPixmap())
            size_lbl.setText("-")

    def _on_ref_changed(self, index):
        self.current_ref_path = self.ref_combo.itemData(index)
        self._update_thumb_and_size(self.ref_thumb, self.ref_size_lbl, self.current_ref_path)
        self.is_processed = False
        self.res_thumb.setPixmap(QPixmap())
        self.res_size_lbl.setText("-")
        self.status_lbl.setText("Wait")

    def set_status(self, text, color=None):
        self.status_lbl.setText(text)
        style = "background: transparent;"
        if color:
            style += f" color: {color};"
        self.status_lbl.setStyleSheet(style)

    def set_result(self, temp_path):
        self.temp_output_path = temp_path
        self.is_processed = True
        self._update_thumb_and_size(self.res_thumb, self.res_size_lbl, temp_path)
        self.set_status("Ready", "#4CAF50")

class BatchRefineDialog(QDialog):
    def __init__(self, parent, items_data, series_path, chapter_name, main_file, reference_paths, manga_dir):
        """
        items_data: list of dicts { 'alt_abs': str, 'alt_rel': str }
        """
        super().__init__(parent)
        self.setWindowTitle("Batch Refine Alternates")
        self.resize(1000, 700)
        
        self.series_path = series_path
        self.chapter_name = chapter_name
        self.main_file = main_file
        self.manga_dir = manga_dir
        self.rows = []

        layout = QVBoxLayout(self)

        # ── Global Options ───────────────────────────────────────────────────
        opts_group = QGroupBox("Global Options")
        opts_layout = QHBoxLayout(opts_group)
        
        self.cb_color = QCheckBox("Fix Color")
        self.cb_color.setChecked(True)
        opts_layout.addWidget(self.cb_color)
        
        self.cb_resize = QCheckBox("Auto Resize")
        self.cb_resize.setChecked(True)
        opts_layout.addWidget(self.cb_resize)
        
        self.cb_manual = QCheckBox("Manual Size:")
        opts_layout.addWidget(self.cb_manual)
        
        self.spin_w = QSpinBox()
        self.spin_w.setRange(1, 9999)
        self.spin_w.setValue(800)
        self.spin_w.setFixedWidth(65)
        self.spin_w.setEnabled(False)
        opts_layout.addWidget(self.spin_w)
        
        self.spin_h = QSpinBox()
        self.spin_h.setRange(1, 9999)
        self.spin_h.setValue(1200)
        self.spin_h.setFixedWidth(65)
        self.spin_h.setEnabled(False)
        opts_layout.addWidget(self.spin_h)
        
        self.cb_manual.toggled.connect(lambda c: (self.spin_w.setEnabled(c), self.spin_h.setEnabled(c), self.cb_resize.setEnabled(not c)))
        
        opts_layout.addStretch()
        
        # Select All/None
        sel_btn_layout = QHBoxLayout()
        self.btn_all = QPushButton("Select All")
        self.btn_all.setFixedWidth(80)
        self.btn_all.setStyleSheet("font-size: 11px; padding: 2px;")
        self.btn_all.clicked.connect(lambda: self._set_all_checkboxes(True))
        
        self.btn_none = QPushButton("Select None")
        self.btn_none.setFixedWidth(80)
        self.btn_none.setStyleSheet("font-size: 11px; padding: 2px;")
        self.btn_none.clicked.connect(lambda: self._set_all_checkboxes(False))
        
        sel_btn_layout.addWidget(self.btn_all)
        sel_btn_layout.addWidget(self.btn_none)
        opts_layout.addLayout(sel_btn_layout)
        
        opts_layout.addSpacing(20)

        # Global Ref Selection
        opts_layout.addWidget(QLabel("Global Ref:"))
        self.global_ref_combo = QComboBox()
        self.global_ref_combo.setMinimumWidth(120)
        self.global_ref_combo.addItem("- Keep Individual -", None)
        for rp in reference_paths:
            self.global_ref_combo.addItem(Path(rp).name, rp)
        self.global_ref_combo.currentIndexChanged.connect(self._on_global_ref_changed)
        opts_layout.addWidget(self.global_ref_combo)
        
        layout.addWidget(opts_group)

        # ── Progress Bar ───────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid rgba(255,255,255,10);
                border-radius: 5px;
                background-color: rgba(0,0,0,50);
                text-align: center;
                height: 10px;
                font-size: 9px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2196F3, stop:1 #00BCD4);
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # ── Batch List ───────────────────────────────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll)

        for item in items_data:
            row = BatchRefineRow(
                self.scroll_content,
                main_path=reference_paths[0],
                alt_abs_path=item['alt_abs'],
                alt_rel_path=item['alt_rel'],
                reference_paths=reference_paths,
                series_path=series_path,
                chapter_name=chapter_name,
                main_file=main_file
            )
            self.scroll_layout.addWidget(row)
            self.rows.append(row)

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.status_total = QLabel("")
        btn_row.addWidget(self.status_total)
        btn_row.addStretch()
        
        self.refine_btn = QPushButton("Refine Selected")
        self.refine_btn.clicked.connect(self._on_refine_all)
        btn_row.addWidget(self.refine_btn)
        
        self.save_btn = QPushButton("Save Selected")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_save_all)
        btn_row.addWidget(self.save_btn)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)
        
        layout.addLayout(btn_row)

        self.cache_dir = Path(".cache/alt_refine")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _on_global_ref_changed(self, index):
        ref_path = self.global_ref_combo.itemData(index)
        if not ref_path:
            return
        for row in self.rows:
            for i in range(row.ref_combo.count()):
                if row.ref_combo.itemData(i) == ref_path:
                    row.ref_combo.setCurrentIndex(i)
                    break

    def _set_all_checkboxes(self, state):
        for row in self.rows:
            row.cb_active.setChecked(state)

    def _on_refine_all(self):
        selected_rows = [row for row in self.rows if row.cb_active.isChecked()]
        if not selected_rows:
            return
            
        self.refine_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.status_total.setText("Processing...")
        
        active_rows = [row for row in self.rows if row.cb_active.isChecked()]
        if not active_rows:
            self.refine_btn.setEnabled(True)
            self.status_total.setText("")
            return
            
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(active_rows))
        self.progress_bar.setValue(0)
        
        manual_size = None
        if self.cb_manual.isChecked():
            manual_size = (self.spin_w.value(), self.spin_h.value())
            
        import time
        for row in selected_rows:
            row.is_processed = False # Reset state for new run
            row.set_status("Processing...", "#2196F3")
            
            alt_p = Path(row.alt_rel_path)
            # Use timestamp to make filename unique and avoid cache issues
            ts = int(time.time() * 1000)
            tmp_name = f"{alt_p.stem}_refine_{id(row)}_{ts}.png"
            # Cleanup old temp file if exists
            if row.temp_output_path and os.path.exists(row.temp_output_path):
                try: os.remove(row.temp_output_path)
                except: pass
            
            tmp_path = str(self.cache_dir / tmp_name)
            
            worker = AltRefinerWorker(
                main_path=row.current_ref_path,
                alt_path=row.alt_abs_path,
                output_path=tmp_path,
                fix_color=self.cb_color.isChecked(),
                auto_resize=self.cb_resize.isChecked(),
                manual_size=manual_size
            )
            # We need to capture the current row in the lambda
            worker.signals.finished.connect(lambda p, r=row: r.set_result(p))
            worker.signals.finished.connect(self._check_all_finished)
            worker.signals.error.connect(lambda m, r=row: r.set_status(f"Error", "#F44336"))
            worker.signals.error.connect(self._check_all_finished)
            
            QThreadPool.globalInstance().start(worker)

    def _check_all_finished(self):
        active_rows = [row for row in self.rows if row.cb_active.isChecked()]
        finished = [row for row in active_rows if row.is_processed or row.status_lbl.text() == "Error"]
        
        self.progress_bar.setValue(len(finished))
        self.status_total.setText(f"Progress: {len(finished)} / {len(active_rows)}")
        
        if len(finished) == len(active_rows):
            self.refine_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
            # Hide progress bar after a short delay or just leave it at 100%
            # For now, just keep it visible as feedback

    def _on_save_all(self):
        rows_to_save = [row for row in self.rows if row.cb_active.isChecked() and row.is_processed]
        if not rows_to_save:
            return
        self.save_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(rows_to_save))
        self.progress_bar.setValue(0)
        
        count = 0
        for i, row in enumerate(rows_to_save):
            try:
                alt_p = Path(row.alt_rel_path)
                # Avoid nested _fix_fix
                base_name = alt_p.stem
                if base_name.endswith('_fix'):
                    base_name = base_name[:-4]
                
                fix_name = base_name + '_fix' + alt_p.suffix
                fix_rel_path = str(alt_p.parent / fix_name).replace('\\', '/')
                final_output_path = str(self.manga_dir / fix_rel_path)
                
                Path(final_output_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(row.temp_output_path, final_output_path)
                
                AltManager.register_alt_fix(
                    self.series_path,
                    self.chapter_name,
                    self.main_file,
                    row.alt_rel_path,
                    fix_rel_path
                )
                row.set_status("Saved", "#4CAF50")
                count += 1
            except Exception as e:
                row.set_status("Save Fail", "#F44336")
            
            self.progress_bar.setValue(i + 1)
                
        self.status_total.setText(f"Batch saved: {count} items")
        self.save_btn.setEnabled(False)

    def accept(self):
        # Clean up temp files
        for row in self.rows:
            if row.temp_output_path and os.path.exists(row.temp_output_path):
                try:
                    os.remove(row.temp_output_path)
                except OSError:
                    pass
        super().accept()
