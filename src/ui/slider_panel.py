from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSlider, QLabel, QPushButton, QVBoxLayout, QComboBox, QSpacerItem, QSizePolicy
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from src.ui.components.input_label import InputLabel
from src.ui.components.alt_selector import AltSelector
from src.ui.components.alt_slider import AltSlider
from src.utils.resource_utils import resource_path


class SliderPanel(QWidget):
    """
    A panel containing a slider for page navigation and slideshow controls.
    """
    valueChanged = pyqtSignal(int)
    page_changed = pyqtSignal(int)
    chapter_changed = pyqtSignal(int)
    page_input_clicked = pyqtSignal()
    chapter_input_clicked = pyqtSignal()
    zoom_mode_changed = pyqtSignal(str)
    zoom_reset = pyqtSignal()
    fullscreen_requested = pyqtSignal() # New signal

    def __init__(self, parent=None, model=None):
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 170); color: white;")
        
        # --- Icons ---
        self.zoom_fit_icon = QIcon(resource_path("assets/icons/fit.png"))
        # Fullscreen icon - using text for now, could be an icon later
        self.fullscreen_icon = QIcon(resource_path("assets/icons/fit.png")) # Reusing fit icon for now, consider adding a new one

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 5, 10, 5)
        main_layout.setSpacing(5)

        # Top part (slider)
        top_widget = QWidget()
        top_widget.setStyleSheet("background: transparent;")
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)

        self.slider = AltSlider(Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self.on_slider_value_changed)
        
        self.step = 1 # Default step

        self.chapter_input = InputLabel("Chapter", 1, 1)
        self.page_input = InputLabel("Page", 1, 1)

        self.chapter_input.enterPressed.connect(self.chapter_changed.emit)
        self.page_input.enterPressed.connect(self._on_page_input_entered)
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
        
        # AltSelector (Replaces slideshow controls)
        self.alt_selector = AltSelector(self, model)
        bottom_layout.addWidget(self.alt_selector)

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

        # New fullscreen button
        self.fullscreen_button = QPushButton("Full Screen") # Using text for now
        self.fullscreen_button.setFixedSize(button_size)
        self.fullscreen_button.clicked.connect(self.fullscreen_requested.emit)
        
        bottom_layout.addWidget(self.zoom_combobox)
        bottom_layout.addWidget(self.reset_zoom_button)
        bottom_layout.addWidget(self.fullscreen_button) # Add new button to layout

        main_layout.addWidget(top_widget)
        main_layout.addWidget(bottom_widget)

    def set_zoom_text(self, text: str):
        self.zoom_combobox.blockSignals(True)
        self.zoom_combobox.setCurrentText(text)
        self.zoom_combobox.blockSignals(False)

    def set_range(self, max_value):
        """Sets the range of the slider."""
        self._raw_max_value = max_value
        self._update_slider_range()
        self.update_page_input_total(max_value)
    
    def update_alt_indicators(self, images):
        alt_indices = []
        for i, page in enumerate(images):
            if len(page.images) > 1:
                alt_indices.append(i)
        self.slider.set_alt_indices(alt_indices)

    def set_value(self, value):
        """Sets the current value of the slider and updates the label."""
        # Block signals to prevent feedback loop if the value is set from outside
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        self.update_page_input_value(value)

    def on_slider_value_changed(self, value):
        """Emits the valueChanged signal and updates the label."""
        # With adjusted range, we don't strictly need snapping logic for the END, 
        # but we still need it for intermediate values if the user somehow drags to an odd pixel 
        # (though setSingleStep usually handles ticks).
        # We'll keep snapping just in case.
        if self.step > 1:
            remainder = value % self.step
            if remainder != 0:
                new_value = value - remainder
                self.slider.blockSignals(True)
                self.slider.setValue(new_value)
                self.slider.blockSignals(False)
                value = new_value

        self.update_page_input_value(value)
        self.valueChanged.emit(value)

    def set_chapter(self, current: int, total: int):
        self.chapter_input.set_value(current)
        self.chapter_input.set_total(total)

    # --- Step / Double Page Logic ---

    def set_step(self, step: int):
        self.step = step
        self.slider.setSingleStep(step)
        self.slider.setPageStep(step * 10) # Jump 10 "pages"
        
        self._update_slider_range()
        
        # Re-update the input labels with the new step
        # Use raw max value if available
        max_val = getattr(self, '_raw_max_value', self.slider.maximum())
        self.update_page_input_total(max_val)
        self.update_page_input_value(self.slider.value())

    def _update_slider_range(self):
        if not hasattr(self, '_raw_max_value'): 
            return

        # Adjust max so the last tick is reachable and represents the last page/pair
        remainder = self._raw_max_value % self.step
        adjusted_max = self._raw_max_value - remainder
        
        self.slider.blockSignals(True)
        self.slider.setRange(0, adjusted_max)
        self.slider.blockSignals(False)

    def update_page_input_total(self, max_value):
        # If step is 2, total is roughly half
        # e.g. 0..9 (10 pages). step=2 -> 5 pairs.
        # indices: 0, 2, 4, 6, 8.
        # count: (max_val // step) + 1
        total_display = (max_value // self.step) + 1
        self.page_input.set_total(total_display)

    def update_page_input_value(self, index):
        # e.g. index 0 -> page 1
        # index 2 -> page 2 (in pairs)
        display_val = (index // self.step) + 1
        self.page_input.set_value(display_val)

    def _on_page_input_entered(self, display_val):
        # Convert back to index
        # page 1 -> index 0
        # page 2 -> index 2 (if step=2)
        real_index = (display_val - 1) * self.step
        
        # Bounds check
        if real_index < 0: real_index = 0
        if real_index > self.slider.maximum(): real_index = self.slider.maximum()
        
        self.page_changed.emit(real_index + 1) # emitted value is 1-based usually expect by change_page

    def refresh_alt_selector(self, index: int):
        if self.alt_selector:
             self.alt_selector._update_selector(index)