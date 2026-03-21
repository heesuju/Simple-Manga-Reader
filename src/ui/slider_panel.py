from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from src.ui.components.input_label import InputLabel
from src.ui.components.alt_slider import AltSlider
from src.ui.styles import PANEL_BG_STYLE


class SliderPanel(QWidget):
    """Single-row panel for page/chapter navigation."""
    valueChanged = pyqtSignal(int)
    page_changed = pyqtSignal(int)
    chapter_changed = pyqtSignal(int)
    page_input_clicked = pyqtSignal()
    chapter_input_clicked = pyqtSignal()

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

        self.chapter_input = InputLabel("Chapter", 1, 1)
        self.page_input = InputLabel("Page", 1, 1)

        self.chapter_input.enterPressed.connect(self.chapter_changed.emit)
        self.page_input.enterPressed.connect(self._on_page_input_entered)
        self.chapter_input.clicked.connect(self.chapter_input_clicked.emit)
        self.page_input.clicked.connect(self.page_input_clicked.emit)

        row.addWidget(self.page_input)
        row.addWidget(self.slider, 1)
        row.addWidget(self.chapter_input)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_info_text(self, text: str):
        """Show file info as a tooltip on the page input."""
        self.page_input.setToolTip(text)

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

    def set_chapter(self, current: int, total: int):
        self.chapter_input.set_value(current)
        self.chapter_input.set_total(total)

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
