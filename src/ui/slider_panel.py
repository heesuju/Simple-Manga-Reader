from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSlider, QLabel, QPushButton, QVBoxLayout, QComboBox, QSpacerItem, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal
from src.ui.input_label import InputLabel


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

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 5, 10, 5)
        main_layout.setSpacing(5)

        # Top part (slider)
        top_widget = QWidget()
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
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(10)
        bottom_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.slideshow_button = QPushButton("▶") # Play icon
        self.slideshow_button.clicked.connect(self.slideshow_button_clicked.emit)

        self.speed_button = QPushButton("1X")
        self.speed_button.clicked.connect(self.speed_changed.emit)

        self.repeat_button = QPushButton("Repeat")
        self.repeat_button.setCheckable(True)
        self.repeat_button.toggled.connect(self.repeat_changed.emit)

        bottom_layout.addWidget(self.slideshow_button)
        bottom_layout.addWidget(self.speed_button)
        bottom_layout.addWidget(self.repeat_button)

        bottom_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        self.zoom_combobox = QComboBox()
        self.zoom_combobox.setEditable(True)
        self.zoom_combobox.addItems(['Fit Page', 'Fit Width', '25%', '50%', '75%', '100%', '125%', '150%', '200%'])
        self.zoom_combobox.currentTextChanged.connect(self.zoom_mode_changed.emit)

        self.reset_zoom_button = QPushButton("Reset")
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
            self.slideshow_button.setText("⏸") # Pause icon
        else:
            self.slideshow_button.setText("▶") # Play icon

    def set_range(self, max_value):
        """Sets the range of the slider."""
        self.slider.setRange(0, max_value)
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
