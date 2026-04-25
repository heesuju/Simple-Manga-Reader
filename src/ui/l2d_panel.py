from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QSizePolicy, QCheckBox, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent

PANEL_W = 190

_SECTION_LABEL_STYLE = (
    "color: rgba(255,255,255,100); font-size: 9px; font-weight: bold; "
    "letter-spacing: 1px; background: transparent;"
)
_ANIM_BTN_STYLE = """
    QPushButton {
        background: rgba(255,255,255,8);
        color: rgba(255,255,255,180);
        border: none;
        border-radius: 3px;
        font-size: 11px;
        padding: 4px 6px;
        text-align: left;
    }
    QPushButton:hover { background: rgba(255,255,255,18); color: white; }
    QPushButton:checked { background: rgba(74,134,232,180); color: white; }
"""
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


class L2DPanel(QWidget):
    """Right-side panel for Spine/L2D viewer: animation list + mesh visibility toggles."""

    anim_selected = pyqtSignal(int)
    anim_paused   = pyqtSignal(bool)
    mesh_toggled            = pyqtSignal(str, bool)
    slot_hovered            = pyqtSignal(str)
    slot_unhovered          = pyqtSignal()
    alpha_mode_changed      = pyqtSignal(bool)
    neighbor_count_changed  = pyqtSignal(int)
    bounce_force_changed    = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim_buttons: list[QPushButton] = []
        self._mesh_checkboxes: list[QCheckBox] = []
        self._paused = False

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("L2DPanel { background-color: rgba(0,0,0,170); border: none; }")
        self.setFixedWidth(PANEL_W)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(6)

        # ── Settings ─────────────────────────────────────────────────────────
        self._premult_cb = QCheckBox("Premultiplied Alpha")
        self._premult_cb.setChecked(False)
        self._premult_cb.setStyleSheet(
            "QCheckBox { color: rgba(255,255,255,140); font-size: 10px; background: transparent; }"
            "QCheckBox::indicator { width: 12px; height: 12px; }"
        )
        self._premult_cb.toggled.connect(self.alpha_mode_changed.emit)
        layout.addWidget(self._premult_cb)

        # ── Interaction ───────────────────────────────────────────────────────
        interaction_label = QLabel("INTERACTION")
        interaction_label.setStyleSheet(_SECTION_LABEL_STYLE)
        layout.addWidget(interaction_label)

        self._neighbor_label = QLabel("Neighbors: 6")
        self._neighbor_label.setStyleSheet(
            "color: rgba(255,255,255,160); font-size: 10px; background: transparent;"
        )
        self._neighbor_slider = QSlider(Qt.Orientation.Horizontal)
        self._neighbor_slider.setRange(1, 10)
        self._neighbor_slider.setValue(6)
        self._neighbor_slider.valueChanged.connect(self._on_neighbor_changed)
        layout.addWidget(self._neighbor_label)
        layout.addWidget(self._neighbor_slider)

        self._force_label = QLabel("Force: 1")
        self._force_label.setStyleSheet(
            "color: rgba(255,255,255,160); font-size: 10px; background: transparent;"
        )
        self._force_slider = QSlider(Qt.Orientation.Horizontal)
        self._force_slider.setRange(1, 10)
        self._force_slider.setValue(1)
        self._force_slider.valueChanged.connect(self._on_force_changed)
        layout.addWidget(self._force_label)
        layout.addWidget(self._force_slider)

        # ── Animations ──────────────────────────────────────────────────────
        anim_header_row = QHBoxLayout()
        anim_header_row.setContentsMargins(0, 0, 0, 0)
        anim_label = QLabel("ANIMATIONS")
        anim_label.setStyleSheet(_SECTION_LABEL_STYLE)
        anim_header_row.addWidget(anim_label, 1)

        self._play_btn = QPushButton("⏸")
        self._play_btn.setFixedSize(28, 22)
        self._play_btn.setCheckable(True)
        self._play_btn.setChecked(False)
        self._play_btn.setStyleSheet(_PLAY_BTN_STYLE)
        self._play_btn.setToolTip("Pause / Resume")
        self._play_btn.clicked.connect(self._on_play_clicked)
        anim_header_row.addWidget(self._play_btn)
        layout.addLayout(anim_header_row)

        self._anim_scroll = QScrollArea()
        self._anim_scroll.setWidgetResizable(True)
        self._anim_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._anim_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._anim_scroll.setStyleSheet("background: transparent; border: none;")

        self._anim_content = QWidget()
        self._anim_content.setStyleSheet("background: transparent;")
        self._anim_layout = QVBoxLayout(self._anim_content)
        self._anim_layout.setContentsMargins(0, 0, 0, 0)
        self._anim_layout.setSpacing(2)
        self._anim_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._anim_scroll.setWidget(self._anim_content)
        layout.addWidget(self._anim_scroll, 1)

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

        self.hide()

    # ── Public API ────────────────────────────────────────────────────────────

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def set_animations(self, names: list):
        while self._anim_layout.count():
            item = self._anim_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._anim_buttons.clear()

        self._play_btn.setChecked(False)
        self._play_btn.setText("⏸")
        self._paused = False

        # Index 0 = Static Pose (emits -1), indices 1..n map to animation 0..n-1
        all_names = ["Static Pose"] + list(names)
        for i, name in enumerate(all_names):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setStyleSheet(_ANIM_BTN_STYLE)
            btn.clicked.connect(lambda _checked, idx=i: self._on_anim_clicked(idx))
            self._anim_layout.addWidget(btn)
            self._anim_buttons.append(btn)

        if names:
            idle_idx = next((i for i, n in enumerate(names) if 'idle' in n.lower()), -1)
            self._select_anim(idle_idx + 1 if idle_idx >= 0 else 1)
        else:
            self._select_anim(0)

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

    def clear(self):
        self.set_animations([])
        self.set_meshes([])

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_anim_clicked(self, index: int):
        self._select_anim(index)
        self.anim_selected.emit(index - 1)  # 0 = Static Pose → -1

    def _select_anim(self, index: int):
        for i, btn in enumerate(self._anim_buttons):
            btn.setChecked(i == index)

    def _on_play_clicked(self, checked: bool):
        self._paused = checked
        self._play_btn.setText("▶" if checked else "⏸")
        self.anim_paused.emit(checked)

    def _on_neighbor_changed(self, value: int):
        self._neighbor_label.setText(f"Neighbors: {value}")
        self.neighbor_count_changed.emit(value)

    def _on_force_changed(self, value: int):
        self._force_label.setText(f"Force: {value}")
        self.bounce_force_changed.emit(value)

    def eventFilter(self, source, event):
        if isinstance(source, QCheckBox):
            if event.type() == QEvent.Type.Enter:
                self.slot_hovered.emit(source.text())
            elif event.type() == QEvent.Type.Leave:
                self.slot_unhovered.emit()
        return super().eventFilter(source, event)
