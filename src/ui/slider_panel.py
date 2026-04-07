from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox
from pathlib import Path
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
    zoom_mode_changed = pyqtSignal(str)
    zoom_reset = pyqtSignal()

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

        self.chapter_input = QComboBox()
        self.chapter_input.setStyleSheet("""
            QComboBox {
                background: transparent;
                color: white;
                border: none;
                padding: 2px 4px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e1e;
                color: white;
                selection-background-color: #3e3e3e;
                border: 1px solid rgba(255, 255, 255, 60);
            }
        """)
        self.chapter_input.setFixedWidth(200)
        self.chapter_input.activated.connect(lambda idx: self.chapter_changed.emit(idx + 1))

        self.page_input = InputLabel(1, 1)

        from PyQt6.QtGui import QIcon
        from PyQt6.QtCore import QSize
        from PyQt6.QtWidgets import QPushButton, QFrame
        from src.utils.resource_utils import resource_path
        
        btn_style = """
            QPushButton { 
                background: transparent; 
                border: none; 
            } 
            QPushButton:hover { 
                background: rgba(255, 255, 255, 20);
                border-radius: 4px;
            }
        """

        self.chapter_btn = QPushButton()
        self.chapter_btn.setIcon(QIcon(resource_path("assets/icons/grid.svg")))
        self.chapter_btn.setIconSize(QSize(16, 16))
        self.chapter_btn.setFixedSize(QSize(22, 22))
        self.chapter_btn.setStyleSheet(btn_style)
        self.chapter_btn.clicked.connect(self.chapter_input_clicked.emit)
        self.chapter_btn.setToolTip("Show Chapter Grid")
        
        chap_group = QWidget()
        chap_group.setStyleSheet("background: transparent;")
        chap_layout = QHBoxLayout(chap_group)
        chap_layout.setContentsMargins(0, 0, 0, 0)
        chap_layout.setSpacing(4)
        chap_layout.addWidget(self.chapter_btn)
        chap_layout.addWidget(self.chapter_input)

        self.page_btn = QPushButton()
        self.page_btn.setIcon(QIcon(resource_path("assets/icons/grid.svg")))
        self.page_btn.setIconSize(QSize(16, 16))
        self.page_btn.setFixedSize(QSize(22, 22))
        self.page_btn.setStyleSheet(btn_style)
        self.page_btn.clicked.connect(self.page_input_clicked.emit)
        self.page_btn.setToolTip("Show Page Grid")

        self.page_input.enterPressed.connect(self._on_page_input_entered)

        page_group = QWidget()
        page_group.setStyleSheet("background: transparent;")
        page_layout = QHBoxLayout(page_group)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(4)
        page_layout.addWidget(self.page_btn)
        page_layout.addWidget(self.page_input)

        row.addWidget(chap_group)
        
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 40); border: none; max-height: 16px; margin: 0 8px; }")
        row.addWidget(divider)
        
        row.addWidget(page_group)
        row.addWidget(self.slider, 1)

        divider2 = QFrame()
        divider2.setFrameShape(QFrame.Shape.VLine)
        divider2.setFrameShadow(QFrame.Shadow.Sunken)
        divider2.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 40); border: none; max-height: 16px; margin: 0 4px; }")
        row.addWidget(divider2)

        self.zoom_combobox = QComboBox()
        self.zoom_combobox.addItems(['Fit Page', 'Fit Width', 'Fit Height', 'Stretch', '25%', '50%', '75%', '100%', '125%', '150%', '200%'])
        self.zoom_combobox.setFixedSize(90, 24)
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

        from src.utils.resource_utils import resource_path as _rp
        self.reset_zoom_button = QPushButton()
        self.reset_zoom_button.setIcon(QIcon(_rp("assets/icons/reset_zoom.svg")))
        self.reset_zoom_button.setIconSize(QSize(16, 16))
        self.reset_zoom_button.setFixedSize(QSize(22, 22))
        self.reset_zoom_button.setStyleSheet(btn_style)
        self.reset_zoom_button.setToolTip("Reset Zoom")
        self.reset_zoom_button.clicked.connect(self.zoom_reset.emit)

        row.addWidget(self.zoom_combobox)
        row.addWidget(self.reset_zoom_button)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_info_text(self, text: str):
        """Show file info as a tooltip on the page input."""
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

    def set_chapters_list(self, chapters: list, current_index: int):
        self.chapter_input.blockSignals(True)
        self.chapter_input.clear()
        for chapter in chapters:
            name = Path(str(chapter)).name if not isinstance(chapter, dict) else chapter.get('name', Path(chapter['path']).name)
            self.chapter_input.addItem(name)
        self.chapter_input.setCurrentIndex(current_index)
        self.chapter_input.blockSignals(False)

    def set_chapter(self, current: int, total: int):
        self.chapter_input.blockSignals(True)
        self.chapter_input.setCurrentIndex(current - 1)
        self.chapter_input.blockSignals(False)

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
