from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox, QMenu, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QAction
from src.utils.resource_utils import resource_path
from src.enums import Language
from src.ui.styles import FLAT_BUTTON_STYLE, PANEL_BG_STYLE


BUTTON_SIZE = QSize(28, 28)
ICON_SIZE = QSize(18, 18)

from src.ui.components.shortcuts_dialog import ShortcutsDialog


class TopPanel(QWidget):
    """Compact single-row panel at the top of the reader view."""
    slideshow_clicked = pyqtSignal()
    speed_changed = pyqtSignal(int)
    repeat_changed = pyqtSignal(bool)
    translate_clicked = pyqtSignal(str)
    lang_changed = pyqtSignal(str)
    sort_changed = pyqtSignal(str)
    bg_color_changed = pyqtSignal(str)
    fullscreen_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(PANEL_BG_STYLE)

        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(8, 4, 8, 4)
        self._row.setSpacing(6)

        self.back_button = None
        self.layout_button = None

        # State tracked for overflow menu display
        self._slideshow_playing = False
        self._repeat_on = False
        self._speed_index = 0
        self._speed_options: list[str] = ["1x", "2x", "8x"]
        self._current_sort_mode = 'name'
        self._current_bg_color = 'Default (Gray)'

        # Zoom controls (view group — sits left of title)
        fullscreen_icon = QIcon(resource_path("assets/icons/fullscreen.svg"))

        self.fullscreen_button = QPushButton()
        self.fullscreen_button.setIcon(fullscreen_icon)
        self.fullscreen_button.setIconSize(ICON_SIZE)
        self.fullscreen_button.setFixedSize(BUTTON_SIZE)
        self.fullscreen_button.setStyleSheet(FLAT_BUTTON_STYLE)
        self.fullscreen_button.setToolTip("Toggle Fullscreen")
        self.fullscreen_button.clicked.connect(self.fullscreen_requested.emit)

        self.series_label = QLabel("Series Title")
        self.series_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.series_label.setStyleSheet("background: transparent; font-weight: bold;")
        
        self.info_label = QLabel("")
        self.info_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.info_label.setStyleSheet("background: transparent; color: rgba(255, 255, 255, 150); font-size: 11px;")
        self.info_label.hide()

        # Language combo (hidden, accessed via overflow menu)
        self.lang_combo = QComboBox(self)
        items = ["Original"] + [lang.value for lang in Language]
        self.lang_combo.addItems(items)
        self.lang_combo.currentTextChanged.connect(self.lang_changed.emit)
        self.lang_combo.hide()

        # Translate button (hidden, accessed via overflow menu)
        self.translate_btn = QPushButton("Translate", self)
        self.translate_btn.clicked.connect(self._on_translate_clicked)
        self.translate_btn.hide()

        # Overflow (•••) button — slideshow, speed, repeat, sort
        self.overflow_btn = QPushButton("•••")
        self.overflow_btn.setFixedSize(BUTTON_SIZE)
        self.overflow_btn.setStyleSheet(
            FLAT_BUTTON_STYLE + " QPushButton { font-weight: bold; font-size: 11px; letter-spacing: 1px; }"
        )
        self.overflow_btn.setToolTip("More options")
        self.overflow_btn.clicked.connect(self._on_overflow_clicked)

        self._row.addWidget(self.series_label)
        self._row.addWidget(self.info_label, 1)
        self._row.addWidget(self.fullscreen_button)
        self._row.addWidget(self.overflow_btn)

    # ── Injected buttons ────────────────────────────────────────────────────

    def add_back_button(self, button: QPushButton):
        self.back_button = button
        self._row.insertWidget(0, self.back_button)

    def add_layout_button(self, button: QPushButton):
        self.layout_button = button
        insert_at = 1 if self.back_button else 0
        self._row.insertWidget(insert_at, self.layout_button)

    # ── Public state setters ─────────────────────────────────────────────────

    def set_series_title(self, title: str):
        self.series_label.setText(title)

    def set_slideshow_state(self, is_playing: bool):
        self._slideshow_playing = is_playing

    def set_speed_options(self, labels: list[str]):
        """Called by reader_view when the viewer mode changes."""
        self._speed_options = labels
        self._speed_index = 0

    def set_speed_index(self, index: int):
        """Called by reader_view to sync the selected speed."""
        self._speed_index = index

    def set_sort_mode(self, mode: str):
        self._current_sort_mode = mode or 'name'

    def set_bg_color(self, color_name: str):
        self._current_bg_color = color_name

    def set_info_text(self, text: str):
        if text:
            self.info_label.setText(f"  •  {text}")
            self.info_label.show()
        else:
            self.info_label.hide()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _on_translate_clicked(self):
        text = self.lang_combo.currentText()
        if text == "Original":
            return
        lang = Language(text)
        self.translate_clicked.emit(lang)

    def _on_help_clicked(self):
        dlg = ShortcutsDialog(self)
        dlg.exec()

    def _on_overflow_clicked(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(30, 30, 30, 240);
                color: white;
                border: 1px solid rgba(255, 255, 255, 50);
            }
            QMenu::item { padding: 5px 20px 5px 28px; }
            QMenu::item:selected { background-color: rgba(255, 255, 255, 40); }
            QMenu::item:disabled { color: rgba(255, 255, 255, 100); }
            QMenu::separator { background-color: rgba(255, 255, 255, 30); height: 1px; margin: 3px 8px; }
            QMenu::indicator:checked { width: 6px; height: 6px; background: white; border-radius: 3px; margin-left: 10px; }
        """)

        # Translate action
        translate_action = QAction(self.translate_btn.text(), self)
        
        is_original = self.lang_combo.currentText() == "Original"
        translate_action.setEnabled(self.translate_btn.isEnabled() and not is_original)
        
        translate_action.triggered.connect(self.translate_btn.click)
        menu.addAction(translate_action)

        # Target language submenu
        lang_menu = menu.addMenu(f"Language: {self.lang_combo.currentText()}")
        lang_menu.setStyleSheet(menu.styleSheet())
        for i in range(self.lang_combo.count()):
            lang_text = self.lang_combo.itemText(i)
            a = QAction(lang_text, self)
            a.setCheckable(True)
            a.setChecked(lang_text == self.lang_combo.currentText())
            a.triggered.connect(lambda checked, text=lang_text: self.lang_combo.setCurrentText(text))
            lang_menu.addAction(a)

        menu.addSeparator()

        # Slideshow toggle
        ss_action = QAction("Slideshow", self)
        ss_action.setCheckable(True)
        ss_action.setChecked(self._slideshow_playing)
        ss_action.triggered.connect(lambda: self.slideshow_clicked.emit())
        menu.addAction(ss_action)

        # Speed submenu
        current_label = self._speed_options[self._speed_index] if self._speed_options else "1x"
        speed_menu = menu.addMenu(f"Speed: {current_label}")
        speed_menu.setStyleSheet(menu.styleSheet())
        for i, label in enumerate(self._speed_options):
            a = QAction(label, self)
            a.setCheckable(True)
            a.setChecked(i == self._speed_index)
            a.triggered.connect(lambda checked, idx=i: self.speed_changed.emit(idx))
            speed_menu.addAction(a)

        # Repeat toggle
        repeat_action = QAction("Repeat", self)
        repeat_action.setCheckable(True)
        repeat_action.setChecked(self._repeat_on)
        repeat_action.triggered.connect(self._on_repeat_toggled)
        menu.addAction(repeat_action)

        menu.addSeparator()

        # Background Color Submenu
        bg_menu = menu.addMenu(f"Background: {self._current_bg_color}")
        bg_menu.setStyleSheet(menu.styleSheet())
        for color_opt in ['Default (Gray)', 'Black', 'White']:
            a = QAction(color_opt, self)
            a.setCheckable(True)
            a.setChecked(color_opt == self._current_bg_color)
            a.triggered.connect(lambda checked, c=color_opt: self._select_bg_color(c))
            bg_menu.addAction(a)

        menu.addSeparator()

        # Sort submenu
        sort_menu = menu.addMenu("Sort Pages")
        sort_menu.setStyleSheet(menu.styleSheet())
        SORT_OPTIONS = [
            ('name',       'Name (A→Z)'),
            ('name_desc',  'Name (Z→A)'),
            ('mtime',      'Modified (Oldest first)'),
            ('mtime_desc', 'Modified (Newest first)'),
            ('ctime',      'Created (Oldest first)'),
            ('ctime_desc', 'Created (Newest first)'),
        ]
        for mode, label in SORT_OPTIONS:
            a = QAction(label, self)
            a.setCheckable(True)
            a.setChecked(self._current_sort_mode == mode)
            a.triggered.connect(lambda checked, m=mode: self._select_sort(m))
            sort_menu.addAction(a)

        menu.addSeparator()
        shortcuts_action = QAction("Keyboard Shortcuts", self)
        shortcuts_action.triggered.connect(self._on_help_clicked)
        menu.addAction(shortcuts_action)

        menu.exec(self.overflow_btn.mapToGlobal(self.overflow_btn.rect().bottomRight()))

    def _on_repeat_toggled(self, checked: bool = None):
        if checked is None:
            checked = not self._repeat_on
        self._repeat_on = checked
        self.repeat_changed.emit(checked)

    def _select_sort(self, mode: str):
        if mode == self._current_sort_mode:
            return
        self._current_sort_mode = mode
        self.sort_changed.emit(mode)

    def _select_bg_color(self, color_name: str):
        if color_name == self._current_bg_color:
            return
        self._current_bg_color = color_name
        self.bg_color_changed.emit(color_name)

    def update_translate_button(self, state: str = 'TRANSLATE', lang: str = ""):
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
        else:
            self.translate_btn.setEnabled(True)
            self.translate_btn.setText("Translate")
            self.translate_btn.setStyleSheet("font-weight: bold; background-color: rgba(0, 120, 215, 150); border: 1px solid rgba(255, 255, 255, 50); border-radius: 3px; color: white;")
