from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon

class TopPanel(QWidget):
    """A simple panel at the top of the reader view."""
    slideshow_clicked = pyqtSignal()
    speed_changed = pyqtSignal()
    repeat_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 170); color: white;")
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 5, 10, 5)
        self.layout.setSpacing(10)

        self.back_button = None
        self.layout_button = None
        self.series_label = QLabel("Series Title")
        self.series_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.series_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.series_label.setStyleSheet("background-color: transparent;")

        # Icons
        self.play_icon = QIcon("assets/icons/play.png")
        self.pause_icon = QIcon("assets/icons/pause.png")
        self.repeat_on_icon = QIcon("assets/icons/repeat_on.png")
        self.repeat_off_icon = QIcon("assets/icons/repeat_off.png")

        button_size = QSize(32, 32)
        
        # Slideshow controls
        self.slideshow_button = QPushButton()
        self.slideshow_button.setIcon(self.play_icon)
        self.slideshow_button.setIconSize(QSize(16, 16))
        self.slideshow_button.setFixedSize(button_size)
        self.slideshow_button.setToolTip("Toggle Slideshow")
        self.slideshow_button.clicked.connect(self.slideshow_clicked.emit)

        self.speed_button = QPushButton("1x")
        self.speed_button.setStyleSheet("font-weight: bold; background-color: rgba(255, 255, 255, 30); border: 1px solid rgba(255, 255, 255, 50); border-radius: 3px;")
        self.speed_button.setFixedSize(button_size)
        self.speed_button.setToolTip("Change Speed")
        self.speed_button.clicked.connect(self.speed_changed.emit)

        self.repeat_button = QPushButton()
        self.repeat_button.setIcon(self.repeat_off_icon)
        self.repeat_button.setIconSize(QSize(16, 16))
        self.repeat_button.setFixedSize(button_size)
        self.repeat_button.setCheckable(True)
        self.repeat_button.setToolTip("Toggle Repeat")
        self.repeat_button.toggled.connect(self._on_repeat_toggled)

        self.layout.addWidget(self.series_label, 1) # Add stretch
        
        # Add slideshow controls to layout temporarily, will be ordered correctly by inserts or addWidgets
        # We want: Back | Series Title | Layout | Slideshow | Speed | Repeat
        
        self.layout.addWidget(self.slideshow_button)
        self.layout.addWidget(self.speed_button)
        self.layout.addWidget(self.repeat_button)

    def add_back_button(self, button: QPushButton):
        self.back_button = button
        self.layout.insertWidget(0, self.back_button)

    def add_layout_button(self, button: QPushButton):
        self.layout_button = button
        # Insert before slideshow controls. 
        # Items: 0=Back, 1=Title, 2=Slideshow, 3=Speed, 4=Repeat. 
        # If we insert at 2, we get Back, Title, Layout, Slideshow... Correct.
        self.layout.insertWidget(2, self.layout_button)

    def set_series_title(self, title: str):
        self.series_label.setText(title)

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
