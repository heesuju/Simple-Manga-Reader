from PyQt6.QtWidgets import QWidget, QHBoxLayout, QComboBox, QFrame
from PyQt6.QtCore import Qt, pyqtSignal
from src.ui.components.input_label import InputLabel
from src.ui.components.alt_slider import AltSlider
from src.ui.styles import PANEL_BG_STYLE


class SliderPanel(QWidget):
    """Single-row panel for page navigation."""
    valueChanged = pyqtSignal(int)
    page_changed = pyqtSignal(int)
    page_input_clicked = pyqtSignal()
    zoom_mode_changed = pyqtSignal(str)

    def __init__(self, parent=None, model=None):
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(PANEL_BG_STYLE)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 5, 10, 5)
        row.setSpacing(10)

        self.slider = AltSlider(Qt.Orientation.Horizontal)
        self.slider.setStyleSheet("""
            QSlider { background: transparent; }
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 40);
                height: 4px;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: rgba(255, 255, 255, 100);
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
        """)
        self.slider.valueChanged.connect(self.on_slider_value_changed)

        self.page_input = InputLabel(1, 1)
        self.page_input.clicked.connect(self.page_input_clicked.emit)
        self.page_input.enterPressed.connect(self._on_page_input_entered)

        page_group = QWidget()
        page_group.setStyleSheet("background: transparent;")
        page_layout = QHBoxLayout(page_group)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(4)
        page_layout.addWidget(self.page_input)

        row.addWidget(page_group)
        row.addWidget(self.slider, 1)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 40); border: none; max-height: 16px; margin: 0 4px; }")
        row.addWidget(divider)

        self.zoom_combobox = QComboBox()
        self.zoom_combobox.addItems(['Fit', 'Width', 'Height', 'Stretch', '25%', '50%', '75%', '100%', '125%', '150%', '200%'])
        self.zoom_combobox.setFixedSize(75, 24)
        self.zoom_combobox.setStyleSheet("""
            QComboBox {
                color: white;
                background: transparent;
                border: none;
                padding: 2px 4px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1e1e1e;
                color: white;
                selection-background-color: #3e3e3e;
                border: 1px solid rgba(255, 255, 255, 60);
            }
        """)
        self.zoom_combobox.currentTextChanged.connect(self.zoom_mode_changed.emit)

        row.addWidget(self.zoom_combobox)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_info_text(self, text: str):
        self.page_input.setToolTip(text)

    def set_zoom_text(self, text: str):
        self.zoom_combobox.blockSignals(True)
        self.zoom_combobox.setCurrentText(text)
        self.zoom_combobox.blockSignals(False)

    def set_range(self, max_value):
        self.slider.blockSignals(True)
        self.slider.setRange(0, max_value)
        self.slider.blockSignals(False)
        self.update_page_input_total(max_value)

    def update_alt_indicators(self, images):
        alt_indices = [i for i, page in enumerate(images) if len(page.images) > 1]
        self.slider.set_alt_indices(alt_indices)

    def set_alt_indices(self, indices: list[int]):
        self.slider.set_alt_indices(indices)

    def set_value(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        self.update_page_input_value(value)

    def update_page_input_total(self, max_value):
        self.page_input.set_total(max_value + 1)

    def update_page_input_value(self, index):
        self.page_input.set_value(index + 1)

    # ── Internal ─────────────────────────────────────────────────────────────

    def on_slider_value_changed(self, value):
        self.update_page_input_value(value)
        self.valueChanged.emit(value)

    def _on_page_input_entered(self, display_val):
        real_index = max(0, min(display_val - 1, self.slider.maximum()))
        self.page_changed.emit(real_index + 1)
