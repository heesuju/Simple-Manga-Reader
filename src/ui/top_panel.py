from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox, QMenu
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QAction
from src.utils.resource_utils import resource_path
from src.enums import Language
from src.ui.styles import FLAT_BUTTON_STYLE

class TopPanel(QWidget):
    """A simple panel at the top of the reader view."""
    slideshow_clicked = pyqtSignal()
    speed_changed = pyqtSignal()
    repeat_changed = pyqtSignal(bool)
    translate_clicked = pyqtSignal(str) # Emits selected language code
    lang_changed = pyqtSignal(str)
    sort_changed = pyqtSignal(str)  # Emits sort mode: 'name', 'mtime', 'ctime'

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
        self.play_icon = QIcon(resource_path("assets/icons/slideshow_play.svg"))
        self.pause_icon = QIcon(resource_path("assets/icons/slideshow_pause.svg"))
        self.repeat_on_icon = QIcon(resource_path("assets/icons/repeat_on.svg"))
        self.repeat_off_icon = QIcon(resource_path("assets/icons/repeat_off.svg"))

        self._current_sort_mode = 'name'

        button_size = QSize(32, 32)
        
        # Slideshow controls
        self.slideshow_button = QPushButton()
        self.slideshow_button.setIcon(self.play_icon)
        self.slideshow_button.setIconSize(QSize(24, 24))
        self.slideshow_button.setFixedSize(button_size)
        self.slideshow_button.setStyleSheet(FLAT_BUTTON_STYLE)
        self.slideshow_button.setToolTip("Toggle Slideshow")
        self.slideshow_button.clicked.connect(self.slideshow_clicked.emit)

        self.speed_button = QPushButton("1x")
        self.speed_button.setFixedSize(button_size)
        self.speed_button.setStyleSheet(FLAT_BUTTON_STYLE + " QPushButton { font-weight: bold; }")
        self.speed_button.setToolTip("Change Speed")
        self.speed_button.clicked.connect(self.speed_changed.emit)

        self.repeat_button = QPushButton()
        self.repeat_button.setIcon(self.repeat_off_icon)
        self.repeat_button.setIconSize(QSize(24, 24))
        self.repeat_button.setFixedSize(button_size)
        self.repeat_button.setCheckable(True)
        self.repeat_button.setStyleSheet(FLAT_BUTTON_STYLE)
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
        self.translate_btn.setStyleSheet(FLAT_BUTTON_STYLE + " QPushButton { font-weight: bold; background-color: rgba(0, 120, 215, 150); }")
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

        # Sort button
        self.sort_button = QPushButton("⇅")
        self.sort_button.setFixedSize(button_size)
        self.sort_button.setStyleSheet(FLAT_BUTTON_STYLE + " QPushButton { font-weight: bold; font-size: 16px; }")
        self.sort_button.setToolTip("Sort Pages")
        self.sort_button.clicked.connect(self._on_sort_clicked)
        self.layout.addWidget(self.sort_button)

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

    def _on_sort_clicked(self):
        menu = QMenu(self)

        SORT_OPTIONS = [
            ('name',  'Name (A→Z)'),
            ('mtime', 'Modified Date'),
            ('ctime', 'Created Date'),
        ]

        for mode, label in SORT_OPTIONS:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(self._current_sort_mode == mode)
            action.triggered.connect(lambda checked, m=mode: self._select_sort(m))
            menu.addAction(action)

        menu.exec(self.sort_button.mapToGlobal(self.sort_button.rect().bottomLeft()))

    def _select_sort(self, mode: str):
        if mode == self._current_sort_mode:
            return
        self._current_sort_mode = mode
        self.sort_changed.emit(mode)

    def set_sort_mode(self, mode: str):
        """Update the button to reflect the currently active sort mode."""
        self._current_sort_mode = mode or 'name'
        labels = {'name': 'Name', 'mtime': 'Mod. Date', 'ctime': 'Cre. Date'}
        self.sort_button.setToolTip(f"Sort Pages: {labels.get(self._current_sort_mode, 'Name')}")


    def update_translate_button(self, state: str = 'TRANSLATE', lang: str = ""):
        """
        Reset translate button to default state.
        'state' arg is kept for compatibility but only 'TRANSLATE' is supported effectively.
        """
        if state == 'TRANSLATING':
            self.translate_btn.setEnabled(False)
            self.translate_btn.setText("Translating...")
            self.translate_btn.setStyleSheet("font-weight: bold; background-color: rgba(255, 165, 0, 150); border: 1px solid rgba(255, 255, 255, 50); border-radius: 3px; color: white;")
        elif state == 'QUEUED':
            self.translate_btn.setEnabled(False)
            self.translate_btn.setText("Queued")
            self.translate_btn.setStyleSheet("font-weight: bold; background-color: rgba(128, 128, 128, 150); border: 1px solid rgba(255, 255, 255, 50); border-radius: 3px; color: white;")
        elif state == 'REDO':
            self.translate_btn.setEnabled(True)
            self.translate_btn.setText("Redo TL")
            self.translate_btn.setStyleSheet("font-weight: bold; background-color: rgba(156, 39, 176, 150); border: 1px solid rgba(255, 255, 255, 50); border-radius: 3px; color: white;")
        elif state == 'DISABLED':
            self.translate_btn.setEnabled(False)
            self.translate_btn.setText("Translate")
            self.translate_btn.setStyleSheet("font-weight: bold; background-color: rgba(100, 100, 100, 150); border: 1px solid rgba(255, 255, 255, 50); border-radius: 3px; color: rgba(255, 255, 255, 100);")
        else: # Default / Ready
            self.translate_btn.setEnabled(True)
            self.translate_btn.setText("Translate")
            self.translate_btn.setStyleSheet("font-weight: bold; background-color: rgba(0, 120, 215, 150); border: 1px solid rgba(255, 255, 255, 50); border-radius: 3px; color: white;")
