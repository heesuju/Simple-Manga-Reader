from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox, QMenu
from pathlib import Path
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
    info_clicked   = pyqtSignal()
    alts_clicked   = pyqtSignal()
    frames_clicked = pyqtSignal()
    anim_clicked   = pyqtSignal()
    chapter_changed = pyqtSignal(int)
    chapter_panel_requested = pyqtSignal()

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

        self.chapter_input = QComboBox()
        self.chapter_input.setStyleSheet("""
            QComboBox {
                background: transparent;
                color: white;
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
        self.chapter_input.setFixedWidth(150)
        self.chapter_input.activated.connect(lambda idx: self.chapter_changed.emit(idx + 1))
        self.chapter_input.currentTextChanged.connect(lambda t: self.chapter_input.setToolTip(t))

        self.chapter_panel_btn = QPushButton()
        self.chapter_panel_btn.setIcon(QIcon(resource_path("assets/icons/expand.svg")))
        self.chapter_panel_btn.setIconSize(QSize(14, 14))
        self.chapter_panel_btn.setFixedSize(QSize(22, 22))
        self.chapter_panel_btn.setStyleSheet(FLAT_BUTTON_STYLE)
        self.chapter_panel_btn.setToolTip("Show Chapter Panel")
        self.chapter_panel_btn.clicked.connect(self.chapter_panel_requested.emit)

        _strip_btn_style = FLAT_BUTTON_STYLE + """
            QPushButton { font-size: 10px; font-weight: bold; color: rgba(255,255,255,120); }
            QPushButton:hover { color: white; }
            QPushButton[active="true"] { color: #4a86e8; }
        """

        self.alts_btn = QPushButton("ALT")
        self.alts_btn.setFixedSize(QSize(32, 26))
        self.alts_btn.setProperty("active", "false")
        self.alts_btn.setStyleSheet(_strip_btn_style)
        self.alts_btn.setToolTip("Toggle Alts")
        self.alts_btn.clicked.connect(self.alts_clicked.emit)
        self.alts_btn.hide()

        self.frames_btn = QPushButton("FRM")
        self.frames_btn.setFixedSize(QSize(32, 26))
        self.frames_btn.setProperty("active", "false")
        self.frames_btn.setStyleSheet(_strip_btn_style)
        self.frames_btn.setToolTip("Toggle Frames")
        self.frames_btn.clicked.connect(self.frames_clicked.emit)
        self.frames_btn.hide()

        self.anim_btn = QPushButton("ANIM")
        self.anim_btn.setFixedSize(QSize(36, 26))
        self.anim_btn.setProperty("active", "false")
        self.anim_btn.setStyleSheet(_strip_btn_style)
        self.anim_btn.setToolTip("Toggle Animations")
        self.anim_btn.clicked.connect(self.anim_clicked.emit)
        self.anim_btn.hide()

        self.info_btn = QPushButton()
        self.info_btn.setIcon(QIcon(resource_path("assets/icons/info.svg")))
        self.info_btn.setIconSize(ICON_SIZE)
        self.info_btn.setFixedSize(BUTTON_SIZE)
        self.info_btn.setProperty("active", "false")
        self.info_btn.setStyleSheet(_strip_btn_style)
        self.info_btn.setToolTip("")
        self.info_btn.clicked.connect(self.info_clicked.emit)
        self.info_btn.hide()  # hidden until info is available

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

        # Overflow (more/menu) button — slideshow, speed, repeat, sort
        self.overflow_btn = QPushButton()
        self.overflow_btn.setIcon(QIcon(resource_path("assets/icons/more.svg")))
        self.overflow_btn.setIconSize(ICON_SIZE)
        self.overflow_btn.setFixedSize(BUTTON_SIZE)
        self.overflow_btn.setStyleSheet(FLAT_BUTTON_STYLE)
        self.overflow_btn.setToolTip("More options")
        self.overflow_btn.clicked.connect(self._on_overflow_clicked)

        self._row.addWidget(self.series_label, 1)
        self._row.addWidget(self.chapter_input)
        self._row.addWidget(self.chapter_panel_btn)
        self._row.addWidget(self.alts_btn)
        self._row.addWidget(self.frames_btn)
        self._row.addWidget(self.anim_btn)
        self._row.addWidget(self.info_btn)
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

    def set_chapters_list(self, chapters: list, current_index: int):
        self.chapter_input.blockSignals(True)
        self.chapter_input.clear()
        for chapter in chapters:
            name = Path(str(chapter)).name if not isinstance(chapter, dict) else chapter.get('name', Path(chapter['path']).name)
            self.chapter_input.addItem(name)
        self.chapter_input.setCurrentIndex(current_index)
        self.chapter_input.setToolTip(self.chapter_input.currentText())
        self.chapter_input.blockSignals(False)

    def set_chapter(self, current: int, total: int):
        self.chapter_input.blockSignals(True)
        self.chapter_input.setCurrentIndex(current - 1)
        self.chapter_input.blockSignals(False)

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

    def set_has_alts(self, has_alts: bool):
        self.alts_btn.setVisible(has_alts)

    def set_has_frames(self, has: bool):
        self.frames_btn.setVisible(has)

    def set_has_animations(self, has: bool):
        self.anim_btn.setVisible(has)

    def set_strip_tab(self, tab: int):
        """Update active state of strip toggle buttons. tab: 0=alts, 1=info, 2=frames, 3=anim, -1=none."""
        for btn, idx in ((self.alts_btn, 0), (self.info_btn, 1), (self.frames_btn, 2), (self.anim_btn, 3)):
            btn.setProperty("active", "true" if tab == idx else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def set_info_text(self, text: str):
        if text:
            self.info_btn.setToolTip(text)
            self.info_btn.show()
        else:
            self.info_btn.setToolTip("")
            self.info_btn.hide()

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
