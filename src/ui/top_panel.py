from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon
from src.utils.resource_utils import resource_path
from src.enums import Language

class TopPanel(QWidget):
    """A simple panel at the top of the reader view."""
    slideshow_clicked = pyqtSignal()
    speed_changed = pyqtSignal()
    repeat_changed = pyqtSignal(bool)
    translate_clicked = pyqtSignal(str) # Emits selected language code
    lang_changed = pyqtSignal(str)

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
        self.play_icon = QIcon(resource_path("assets/icons/play.png"))
        self.pause_icon = QIcon(resource_path("assets/icons/pause.png"))
        self.repeat_on_icon = QIcon(resource_path("assets/icons/repeat_on.png"))
        self.repeat_off_icon = QIcon(resource_path("assets/icons/repeat_off.png"))

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

        # Translate controls
        self.translate_layout = QHBoxLayout()
        self.translate_layout.setSpacing(5)
        
        self.lang_combo = QComboBox()
        items = ["Original"] + [lang.value for lang in Language]
        self.lang_combo.addItems(items)
        self.lang_combo.setFixedSize(60, 32)
        self.lang_combo.setStyleSheet("color: white; background-color: rgba(255, 255, 255, 30); border: 1px solid rgba(255, 255, 255, 50); border-radius: 3px;")
        self.lang_combo.currentTextChanged.connect(self.lang_changed.emit)
        
        self.translate_btn = QPushButton("Translate")
        self.translate_btn.setFixedSize(80, 32)
        self.translate_btn.setStyleSheet("font-weight: bold; background-color: rgba(0, 120, 215, 150); border: 1px solid rgba(255, 255, 255, 50); border-radius: 3px; color: white;")
        self.translate_btn.clicked.connect(self._on_translate_clicked)

        self.translate_layout.addWidget(self.lang_combo)
        self.translate_layout.addWidget(self.translate_btn)

        self.layout.addWidget(self.series_label, 1) # Add stretch
        
        # Add slideshow controls to layout temporarily, will be ordered correctly by inserts or addWidgets
        # We want: Back | Series Title | Translate | Layout | Slideshow | Speed | Repeat
        
        self.layout.addLayout(self.translate_layout)
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

    def _on_translate_clicked(self):
        lang = Language(self.lang_combo.currentText())
        self.translate_clicked.emit(lang)

    def set_translating(self, is_translating: bool):
        if is_translating:
            self.translate_btn.setText("Working...")
            self.translate_btn.setEnabled(False)
            self.translate_btn.setStyleSheet("font-weight: bold; background-color: rgba(100, 100, 100, 150); border: 1px solid rgba(255, 255, 255, 50); border-radius: 3px; color: rgba(255, 255, 255, 100);")
        else:
            self.translate_btn.setText("Translate")
            self.translate_btn.setEnabled(True)
            self.translate_btn.setStyleSheet("font-weight: bold; background-color: rgba(0, 120, 215, 150); border: 1px solid rgba(255, 255, 255, 50); border-radius: 3px; color: white;")

    def update_translate_button(self, state: str, lang: str = ""):
        """
        Update translate button appearance and text.
        state: 'TRANSLATE', 'SHOW_TL', 'SHOW_ORG'
        """
        self.translate_btn.setEnabled(True)
        if state == 'TRANSLATE':
            self.translate_btn.setText("Translate")
            self.translate_btn.setStyleSheet("font-weight: bold; background-color: rgba(0, 120, 215, 150); border: 1px solid rgba(255, 255, 255, 50); border-radius: 3px; color: white;")
        elif state == 'SHOW_TL':
            self.translate_btn.setText(f"Show {lang}")
            self.translate_btn.setStyleSheet("font-weight: bold; background-color: rgba(0, 200, 83, 150); border: 1px solid rgba(255, 255, 255, 50); border-radius: 3px; color: white;")
        elif state == 'SHOW_ORG':
            self.translate_btn.setText("Show Original")
            self.translate_btn.setStyleSheet("font-weight: bold; background-color: rgba(255, 152, 0, 150); border: 1px solid rgba(255, 255, 255, 50); border-radius: 3px; color: white;")
