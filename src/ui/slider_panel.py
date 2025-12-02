from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSlider, QLabel, QPushButton, QVBoxLayout, QComboBox, QSpacerItem, QSizePolicy
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from src.ui.components.input_label import InputLabel


class SliderPanel(QWidget):
    """
    A panel containing a slider for page navigation and slideshow controls.
    """
    valueChanged = pyqtSignal(int)
    page_changed = pyqtSignal(int)
    chapter_changed = pyqtSignal(int)
    page_input_clicked = pyqtSignal()
    chapter_input_clicked = pyqtSignal()
    slideshow_button_clicked = pyqtSignal()
    speed_changed = pyqtSignal()
    repeat_changed = pyqtSignal(bool)
    zoom_mode_changed = pyqtSignal(str)
    zoom_reset = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 170);")

        # --- Icons ---
        self.play_icon = QIcon("assets/icons/play.png")
        self.pause_icon = QIcon("assets/icons/pause.png")
        self.repeat_on_icon = QIcon("assets/icons/repeat_on.png")
        self.repeat_off_icon = QIcon("assets/icons/repeat_off.png")
        self.zoom_fit_icon = QIcon("assets/icons/fit.png")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 5, 10, 5)
        main_layout.setSpacing(5)

        # Top part (slider)
        top_widget = QWidget()
        top_widget.setStyleSheet("background: transparent;")
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self.on_slider_value_changed)

        self.chapter_input = InputLabel("Chapter", 1, 1)
        self.page_input = InputLabel("Page", 1, 1)

        self.chapter_input.enterPressed.connect(self.chapter_changed.emit)
        self.page_input.enterPressed.connect(self.page_changed.emit)
        self.chapter_input.clicked.connect(self.chapter_input_clicked.emit)
        self.page_input.clicked.connect(self.page_input_clicked.emit)

        top_layout.addWidget(self.page_input)
        top_layout.addWidget(self.slider, 1) # Add stretch factor
        top_layout.addWidget(self.chapter_input)

        # Bottom part (buttons)
        bottom_widget = QWidget()
        bottom_widget.setStyleSheet("background: transparent;")
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(10)
        bottom_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        button_size = QSize(32, 32)

        self.slideshow_button = QPushButton()
        self.slideshow_button.setIcon(self.play_icon)
        self.slideshow_button.setIconSize(QSize(16, 16))
        self.slideshow_button.setFixedSize(button_size)
        self.slideshow_button.clicked.connect(self.slideshow_button_clicked.emit)

        self.speed_button = QPushButton("1x")
        self.speed_button.setStyleSheet("font-weight: bold;")
        self.speed_button.setFixedSize(button_size)
        self.speed_button.clicked.connect(self.speed_changed.emit)

        self.repeat_button = QPushButton()
        self.repeat_button.setIcon(self.repeat_off_icon)
        self.repeat_button.setIconSize(QSize(16, 16))
        self.repeat_button.setFixedSize(button_size)
        self.repeat_button.setCheckable(True)
        self.repeat_button.toggled.connect(self._on_repeat_toggled)

        bottom_layout.addWidget(self.slideshow_button)
        bottom_layout.addWidget(self.speed_button)
        bottom_layout.addWidget(self.repeat_button)

        bottom_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        self.zoom_combobox = QComboBox()
        self.zoom_combobox.setEditable(True)
        self.zoom_combobox.addItems(['Fit Page', 'Fit Width', '25%', '50%', '75%', '100%', '125%', '150%', '200%'])
        self.zoom_combobox.currentTextChanged.connect(self.zoom_mode_changed.emit)

        self.reset_zoom_button = QPushButton()
        self.reset_zoom_button.setIcon(self.zoom_fit_icon)
        self.reset_zoom_button.setIconSize(QSize(16, 16))
        self.reset_zoom_button.setFixedSize(button_size)
        self.reset_zoom_button.clicked.connect(self.zoom_reset)

        bottom_layout.addWidget(self.zoom_combobox)
        bottom_layout.addWidget(self.reset_zoom_button)

        main_layout.addWidget(top_widget)
        main_layout.addWidget(bottom_widget)

    def set_zoom_text(self, text: str):
        self.zoom_combobox.blockSignals(True)
        self.zoom_combobox.setCurrentText(text)
        self.zoom_combobox.blockSignals(False)

    def set_slideshow_state(self, is_playing: bool):
        if is_playing:
            self.slideshow_button.setIcon(self.pause_icon)
        else:
            self.slideshow_button.setIcon(self.play_icon)

    def _on_repeat_toggled(self, checked: bool):
        if checked:
            self.repeat_button.setIcon(self.repeat_on_icon)
        else:
            self.repeat_button.setIcon(self.repeat_off_icon)
        self.repeat_changed.emit(checked)

    def set_range(self, max_value):
        """Sets the range of the slider."""
        self.slider.blockSignals(True)
        self.slider.setRange(0, max_value)
        self.slider.blockSignals(False)
        self.page_input.set_total(max_value + 1)

    def set_value(self, value):
        """Sets the current value of the slider and updates the label."""
        # Block signals to prevent feedback loop if the value is set from outside
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        self.page_input.set_value(value + 1)

    def on_slider_value_changed(self, value):
        """Emits the valueChanged signal and updates the label."""
        self.page_input.set_value(value + 1)
        self.valueChanged.emit(value)

    def set_chapter(self, current: int, total: int):
        self.chapter_input.set_value(current)
        self.chapter_input.set_total(total)
