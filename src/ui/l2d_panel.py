from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QSizePolicy, QCheckBox, QSlider, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
import re

PANEL_W = 200

_SECTION_LABEL_STYLE = (
    "color: rgba(255,255,255,100); font-size: 9px; font-weight: bold; "
    "letter-spacing: 1px; background: transparent;"
)
_PLAY_BTN_STYLE = """
    QPushButton {
        background: rgba(255,255,255,15);
        color: white;
        border: none;
        border-radius: 3px;
        font-size: 12px;
    }
    QPushButton:hover { background: rgba(255,255,255,30); }
    QPushButton:checked { background: rgba(255,255,255,10); color: rgba(255,255,255,120); }
"""
_COMBO_STYLE = """
    QComboBox {
        background: rgba(255,255,255,12);
        color: rgba(255,255,255,200);
        border: none;
        border-radius: 3px;
        font-size: 11px;
        padding: 2px 6px;
    }
    QComboBox:hover { background: rgba(255,255,255,20); }
    QComboBox::drop-down { border: none; width: 18px; }
    QComboBox QAbstractItemView {
        background: #2a2a2a;
        color: rgba(255,255,255,200);
        selection-background-color: rgba(74,134,232,180);
        border: none;
    }
"""
_SETTING_LABEL_STYLE = (
    "color: rgba(255,255,255,160); font-size: 10px; background: transparent;"
)
_VALUE_LABEL_STYLE = (
    "color: rgba(255,255,255,120); font-size: 10px; background: transparent;"
)


class L2DPanel(QWidget):
    """Right-side panel for Spine/L2D viewer: animation list + mesh visibility toggles."""

    anim_selected           = pyqtSignal(int)
    anim_paused             = pyqtSignal(bool)
    mesh_toggled            = pyqtSignal(str, bool)
    slot_hovered            = pyqtSignal(str)
    slot_unhovered          = pyqtSignal()
    alpha_mode_changed      = pyqtSignal(bool)
    bones_toggled           = pyqtSignal(bool)
    neighbor_count_changed  = pyqtSignal(int)
    bounce_force_changed    = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mesh_checkboxes: list[QCheckBox] = []
        self._paused = False

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("L2DPanel { background-color: rgba(0,0,0,170); border: none; }")
        self.setFixedWidth(PANEL_W)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(6)

        # ── Animations ──────────────────────────────────────────────────────
        anim_label = QLabel("ANIMATIONS")
        anim_label.setStyleSheet(_SECTION_LABEL_STYLE)
        layout.addWidget(anim_label)

        anim_row = QHBoxLayout()
        anim_row.setContentsMargins(0, 0, 0, 0)
        anim_row.setSpacing(4)

        self._anim_combo = QComboBox()
        self._anim_combo.setFixedHeight(24)
        self._anim_combo.setStyleSheet(_COMBO_STYLE)
        self._anim_combo.currentIndexChanged.connect(self._on_combo_changed)
        anim_row.addWidget(self._anim_combo, 1)

        self._play_btn = QPushButton("⏸")
        self._play_btn.setFixedSize(28, 24)
        self._play_btn.setCheckable(True)
        self._play_btn.setChecked(False)
        self._play_btn.setStyleSheet(_PLAY_BTN_STYLE)
        self._play_btn.setToolTip("Pause / Resume")
        self._play_btn.clicked.connect(self._on_play_clicked)
        anim_row.addWidget(self._play_btn)
        layout.addLayout(anim_row)

        # ── Meshes ───────────────────────────────────────────────────────────
        self._mesh_section = QWidget()
        self._mesh_section.setStyleSheet("background: transparent;")
        mesh_layout = QVBoxLayout(self._mesh_section)
        mesh_layout.setContentsMargins(0, 0, 0, 0)
        mesh_layout.setSpacing(4)

        mesh_label = QLabel("MESHES")
        mesh_label.setStyleSheet(_SECTION_LABEL_STYLE)
        mesh_layout.addWidget(mesh_label)

        self._mesh_scroll = QScrollArea()
        self._mesh_scroll.setWidgetResizable(True)
        self._mesh_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._mesh_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._mesh_scroll.setStyleSheet("background: transparent; border: none;")

        self._mesh_content = QWidget()
        self._mesh_content.setStyleSheet("background: transparent;")
        self._mesh_layout = QVBoxLayout(self._mesh_content)
        self._mesh_layout.setContentsMargins(0, 0, 0, 0)
        self._mesh_layout.setSpacing(0)
        self._mesh_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._mesh_scroll.setWidget(self._mesh_content)
        mesh_layout.addWidget(self._mesh_scroll, 1)

        self._mesh_section.hide()
        layout.addWidget(self._mesh_section, 1)

        # ── Settings ─────────────────────────────────────────────────────────
        settings_label = QLabel("SETTINGS")
        settings_label.setStyleSheet(_SECTION_LABEL_STYLE)
        layout.addWidget(settings_label)

        self._premult_cb = QCheckBox("Premultiplied Alpha")
        self._premult_cb.setChecked(False)
        self._premult_cb.setStyleSheet(
            "QCheckBox { color: rgba(255,255,255,140); font-size: 10px; background: transparent; }"
            "QCheckBox::indicator { width: 12px; height: 12px; }"
        )
        self._premult_cb.toggled.connect(self.alpha_mode_changed.emit)
        layout.addWidget(self._premult_cb)

        self._bones_cb = QCheckBox("Show Bones")
        self._bones_cb.setChecked(False)
        self._bones_cb.setStyleSheet(
            "QCheckBox { color: rgba(255,255,255,140); font-size: 10px; background: transparent; }"
            "QCheckBox::indicator { width: 12px; height: 12px; }"
        )
        self._bones_cb.toggled.connect(self.bones_toggled.emit)
        layout.addWidget(self._bones_cb)

        self._neighbor_val = QLabel("6")
        self._neighbor_slider = QSlider(Qt.Orientation.Horizontal)
        self._neighbor_slider.setRange(1, 10)
        self._neighbor_slider.setValue(6)
        self._neighbor_slider.valueChanged.connect(self._on_neighbor_changed)
        layout.addLayout(self._slider_row("Neighbors", self._neighbor_slider, self._neighbor_val))

        self._force_val = QLabel("4")
        self._force_slider = QSlider(Qt.Orientation.Horizontal)
        self._force_slider.setRange(1, 10)
        self._force_slider.setValue(4)
        self._force_slider.valueChanged.connect(self._on_force_changed)
        layout.addLayout(self._slider_row("Force", self._force_slider, self._force_val))

        self.hide()

    # ── Public API ────────────────────────────────────────────────────────────

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def set_animations(self, names: list):
        self._anim_combo.blockSignals(True)
        self._anim_combo.clear()
        self._anim_combo.addItem("Static Pose")
        self._anim_combo.addItems(names)

        idle_idx = -1
        if names:
            # Match JS logic in common.js: shortest 'idle' string, then natural sort
            idles = [n for n in names if 'idle' in n.lower()]
            if idles:
                def extract_num(s):
                    m = re.search(r'\d+', s)
                    return int(m.group()) if m else float('inf')
                idles.sort(key=lambda x: (len(x), extract_num(x), x.lower()))
                idle_idx = names.index(idles[0])
            else:
                idle_idx = 0
            self._anim_combo.setCurrentIndex(idle_idx + 1)
        self._anim_combo.blockSignals(False)

        self._play_btn.setChecked(False)
        self._play_btn.setText("⏸")
        self._paused = False

        if names:
            self.anim_selected.emit(idle_idx)

    def set_meshes(self, names: list):
        while self._mesh_layout.count():
            item = self._mesh_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._mesh_checkboxes.clear()

        for name in names:
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.setStyleSheet(
                "QCheckBox { color: rgba(255,255,255,180); font-size: 11px; background: transparent; }"
                "QCheckBox::indicator { width: 14px; height: 14px; }"
            )
            cb.toggled.connect(lambda checked, n=name: self.mesh_toggled.emit(n, checked))
            cb.installEventFilter(self)
            self._mesh_layout.addWidget(cb)
            self._mesh_checkboxes.append(cb)

        self._mesh_section.setVisible(bool(names))

    def reapply_settings(self):
        """Re-push current slider/checkbox values to the viewer after a page reload."""
        self.neighbor_count_changed.emit(self._neighbor_slider.value())
        self.bounce_force_changed.emit(self._force_slider.value())

    def set_bones_checked(self, checked: bool):
        self._bones_cb.blockSignals(True)
        self._bones_cb.setChecked(checked)
        self._bones_cb.blockSignals(False)

    def clear(self):
        self._anim_combo.blockSignals(True)
        self._anim_combo.clear()
        self._anim_combo.blockSignals(False)
        self._bones_cb.blockSignals(True)
        self._bones_cb.setChecked(False)
        self._bones_cb.blockSignals(False)
        self.set_meshes([])

    # ── Internal ──────────────────────────────────────────────────────────────

    def _slider_row(self, label: str, slider: QSlider, val_label: QLabel) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        lbl = QLabel(label)
        lbl.setFixedWidth(58)
        lbl.setStyleSheet(_SETTING_LABEL_STYLE)
        val_label.setFixedWidth(16)
        val_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        val_label.setStyleSheet(_VALUE_LABEL_STYLE)
        row.addWidget(lbl)
        row.addWidget(slider, 1)
        row.addWidget(val_label)
        return row

    def _on_combo_changed(self, index: int):
        self.anim_selected.emit(index - 1)  # 0 = Static Pose → -1

    def _on_play_clicked(self, checked: bool):
        self._paused = checked
        self._play_btn.setText("▶" if checked else "⏸")
        self.anim_paused.emit(checked)

    def _on_neighbor_changed(self, value: int):
        self._neighbor_val.setText(str(value))
        self.neighbor_count_changed.emit(value)

    def _on_force_changed(self, value: int):
        self._force_val.setText(str(value))
        self.bounce_force_changed.emit(value)

    def eventFilter(self, source, event):
        if isinstance(source, QCheckBox):
            if event.type() == QEvent.Type.Enter:
                self.slot_hovered.emit(source.text())
            elif event.type() == QEvent.Type.Leave:
                self.slot_unhovered.emit()
        return super().eventFilter(source, event)
