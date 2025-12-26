import zipfile
from pathlib import Path
import multiprocessing
import sys
import os
import subprocess
import socket
import io
import qrcode
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QScrollArea, QSizePolicy,
    QMessageBox, QFileDialog, QLineEdit, QHBoxLayout, QComboBox, QDialog, QListWidget, QListWidgetItem, QMenu, QApplication, QGridLayout, QCompleter
)
from PyQt6.QtGui import QPixmap, QShortcut, QKeySequence, QIcon, QCursor, QPainter, QBrush, QColor
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QRunnable, QThreadPool, QSize, QStringListModel, QPropertyAnimation, QEasingCurve, QEvent, QSize

from src.ui.reader_view import ReaderView
from src.ui.clickable_label import ClickableLabel
from src.ui.thumbnail_widget import ThumbnailWidget
from src.core.item_loader import ItemLoader
from src.utils.img_utils import get_chapter_number
from src.enums import ViewMode
import math
import json
from src.core.library_scanner import LibraryScanner
from src.core.library_manager import LibraryManager
from src.ui.filter_token import FilterToken
from src.ui.batch_metadata_dialog import BatchMetadataDialog
from src.ui.info_dialog import InfoDialog
from src.ui.components.chapter_selection_dialog import ChapterSelectionDialog
from src.utils.resource_utils import resource_path


def run_server(script_path, root_dir):
    import subprocess
    import sys
    subprocess.run([sys.executable, script_path, root_dir])

class StatusButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.status_key = None
        self.setFixedSize(32, 32)
        # Font settings for emoji
        self.emoji_font = self.font()
        self.emoji_font.setPointSize(10)

    def set_status(self, status):
        self.status_key = status
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.status_key:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Map status to emoji
            emoji_map = {
                "error_install": "❌",
                "error_model": "⚠️",
                "downloading": "⬇️",
                "running": "✅",
                "stopped": "⭕"
            }
            
            icon_text = emoji_map.get(self.status_key)
            
            if icon_text:
                painter.setFont(self.emoji_font)
                painter.setPen(Qt.GlobalColor.white)
                # Draw text in bottom right corner
                rect = self.rect()
                # Adjust rect to bottom right quadrant
                target_rect = rect.adjusted(12, 12, 0, 0)
                painter.drawText(target_rect, Qt.AlignmentFlag.AlignCenter, icon_text)
                
from src.core.llm_server import LLMServerManager

class FolderGrid(QWidget):
    """Shows a grid of folders and images."""
    series_selected = pyqtSignal(object)
    recent_series_selected = pyqtSignal(object)

    def __init__(self, library_manager, parent=None):
        super().__init__(parent)
        
        self.library_manager = library_manager
        self.llm_manager = LLMServerManager.instance()
        self.llm_manager.status_changed.connect(self.on_llm_status_changed)
        
        self.loading_generation = 0
        self.recent_loading_generation = 0
        self.loader = None
        self.received_items = {}
        self.next_item_to_display = 0
        self.total_items_to_load = 0
        self.language = 'ko'
        self.current_view = 'series' # or 'chapters'
        self.current_series = None
        self.items = []
        self.tokens = {}
        self.recent_items = []
        self.recent_loader = None
        
        self.threadpool = QThreadPool()
        self.web_server_process = None

        self.is_in_selection_mode = False
        self.setAcceptDrops(True)
        self.init_ui()
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.exit_program)
        self.showFullScreen()
        
        # Initial status check
        QTimer.singleShot(100, self.llm_manager.emit_status)

    def on_llm_status_changed(self, status):
        if hasattr(self, 'llm_config_btn'):
            self.llm_config_btn.set_status(status)

    def init_ui(self):
        self.setWindowTitle("Manga Browser")
        self.add_icon = QIcon(resource_path("assets/icons/add.png"))
        self.qr_icon = QIcon(resource_path("assets/icons/qr.png"))

        main_layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()

        self.search_container = QWidget()
        self.search_container.setStyleSheet(
            "QWidget { border: none; border-radius: 5px; background-color: rgba(0, 0, 0, 170); color: white; }"
        )
        search_container_layout = QHBoxLayout(self.search_container)
        search_container_layout.setContentsMargins(4, 2, 4, 2)
        search_container_layout.setSpacing(4)

        self.token_layout = QHBoxLayout()
        self.token_layout.setContentsMargins(0, 0, 0, 0)
        self.token_layout.setSpacing(2)
        self.token_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        search_container_layout.addLayout(self.token_layout)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search by title, or type / to filter by author/genre")
        self.search_bar.textChanged.connect(self.search_items)
        self.search_bar.setStyleSheet("border: none; background: transparent;")
        self.search_bar.installEventFilter(self)
        search_container_layout.addWidget(self.search_bar, 1)

        top_layout.addWidget(self.search_container)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_search)
        top_layout.addWidget(self.clear_btn)

        self.add_btn = QPushButton()
        self.add_btn.setIcon(self.add_icon)
        self.add_btn.setIconSize(QSize(32, 32))
        self.add_btn.setFixedSize(QSize(32, 32))
        self.add_btn.clicked.connect(self.show_add_menu)

        self.web_access_btn = QPushButton()
        self.web_access_btn.setIcon(self.qr_icon)
        self.web_access_btn.setIconSize(QSize(32, 32))
        self.web_access_btn.setFixedSize(QSize(32, 32))
        self.web_access_btn.clicked.connect(self.toggle_web_access)
        
        self.llm_config_btn = StatusButton()
        self.llm_config_btn.setIcon(QIcon(resource_path("assets/icons/lang.png")))
        self.llm_config_btn.setIconSize(QSize(24, 24))
        self.llm_config_btn.clicked.connect(self.show_llm_config)

        top_layout.addWidget(self.web_access_btn)
        top_layout.addWidget(self.llm_config_btn)
        main_layout.addLayout(top_layout)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border: none;")
        self.scroll_content = QWidget()
        self.scroll.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll)

        # Footer
        self.footer_container = QWidget()
        footer_container_layout = QVBoxLayout(self.footer_container)
        footer_container_layout.setContentsMargins(0,0,0,0)
        footer_container_layout.setSpacing(0)
        
        self.normal_footer = QWidget()
        normal_footer_layout = QHBoxLayout(self.normal_footer)
        normal_footer_layout.setContentsMargins(0, 0, 0, 0)
        normal_footer_layout.addStretch()
        normal_footer_layout.addWidget(self.add_btn)

        self.more_options_btn = QPushButton("...")
        self.more_options_btn.setFixedSize(QSize(32, 32))
        self.more_options_btn.clicked.connect(self.show_more_options_menu)
        normal_footer_layout.addWidget(self.more_options_btn)
        
        self.selection_footer = QWidget()
        selection_footer_layout = QHBoxLayout(self.selection_footer)
        selection_footer_layout.setContentsMargins(0, 0, 0, 0)
        self.selection_count_label = QLabel("0 items selected")
        self.cancel_selection_btn = QPushButton("Cancel")
        self.cancel_selection_btn.clicked.connect(lambda: self.toggle_selection_mode(False))
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        self.apply_batch_edit_btn = QPushButton("Edit")
        self.apply_batch_edit_btn.clicked.connect(self.apply_batch_edit)
        self.remove_selected_btn = QPushButton("Remove")
        self.remove_selected_btn.clicked.connect(self.remove_selected_series)
        selection_footer_layout.addWidget(self.selection_count_label)
        selection_footer_layout.addWidget(self.cancel_selection_btn)
        selection_footer_layout.addStretch()
        selection_footer_layout.addWidget(self.select_all_btn)
        selection_footer_layout.addWidget(self.apply_batch_edit_btn)
        selection_footer_layout.addWidget(self.remove_selected_btn)
        self.selection_footer.hide()

        footer_container_layout.addWidget(self.normal_footer)
        footer_container_layout.addWidget(self.selection_footer)
        main_layout.addWidget(self.footer_container)
        
        content_layout = QVBoxLayout(self.scroll_content)
        content_layout.setContentsMargins(0,0,0,0)
        content_layout.setSpacing(0)

        self.recent_label = QLabel("Recently Opened")
        self.recent_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-left: 10px;")
        content_layout.addWidget(self.recent_label)

        self.recent_scroll_container = QWidget()
        container_layout = QGridLayout(self.recent_scroll_container)
        container_layout.setContentsMargins(0,0,0,0)
        content_layout.addWidget(self.recent_scroll_container)

        self.recent_scroll = QScrollArea()
        self.recent_scroll.setWidgetResizable(True)
        self.recent_scroll.setStyleSheet("border: none;")
        self.recent_scroll.viewport().setContentsMargins(0, 0, 0, 0)
        self.recent_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.recent_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.recent_scroll.setFixedHeight(260)
        self.recent_scroll.viewport().installEventFilter(self)
        container_layout.addWidget(self.recent_scroll, 0, 0)

        self.recent_scroll_content = QWidget()
        self.recent_layout = QHBoxLayout(self.recent_scroll_content)
        self.recent_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.recent_layout.setContentsMargins(0,0,0,0)
        self.recent_layout.setSpacing(0)
        self.recent_scroll.setWidget(self.recent_scroll_content)

        self.recent_scroll_left_btn = QPushButton("<", self.recent_scroll_container)
        self.recent_scroll_left_btn.setFixedWidth(30)
        self.recent_scroll_left_btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.recent_scroll_left_btn.setStyleSheet("background-color: rgba(0, 0, 0, 128); color: white; border: none;")
        self.recent_scroll_left_btn.hide()
        container_layout.addWidget(self.recent_scroll_left_btn, 0, 0, Qt.AlignmentFlag.AlignLeft)

        self.recent_scroll_right_btn = QPushButton(">", self.recent_scroll_container)
        self.recent_scroll_right_btn.setFixedWidth(30)
        self.recent_scroll_right_btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.recent_scroll_right_btn.setStyleSheet("background-color: rgba(0, 0, 0, 128); color: white; border: none;")
        self.recent_scroll_right_btn.hide()
        container_layout.addWidget(self.recent_scroll_right_btn, 0, 0, Qt.AlignmentFlag.AlignRight)

        self.recent_scroll_left_btn.clicked.connect(self.scroll_left)
        self.recent_scroll_right_btn.clicked.connect(self.scroll_right)

        scroll_bar = self.recent_scroll.horizontalScrollBar()
        scroll_bar.rangeChanged.connect(self.update_scroll_buttons_visibility)
        scroll_bar.valueChanged.connect(self.update_scroll_buttons_visibility)

        self.all_series_label = QLabel("All (0)")
        self.all_series_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-left: 10px;")
        content_layout.addWidget(self.all_series_label)

        self.grid_layout = QGridLayout()
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid_layout.setContentsMargins(0,0,0,0)
        self.grid_layout.setSpacing(0)
        content_layout.addLayout(self.grid_layout)
        content_layout.addStretch(1)

        self.info_label = QLabel(self)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet("background-color: rgba(0, 0, 0, 180); color: white; padding: 10px; border-radius: 5px;")
        self.info_label.hide()

        self.setup_completer()
        self.load_recent_items()
        self.load_items()

    def setup_completer(self):
        self.completer = QCompleter(self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setWidget(self.search_bar)
        self.completer.activated.connect(self.handle_completion)

    def handle_completion(self, text):
        current_text = self.search_bar.text()
        if current_text.startswith("/author:") or current_text.startswith("/genre:") or current_text.startswith("/theme:") or current_text.startswith("/format:"):
            prefix = current_text.split(":")[0] + ":"
            self.add_token(prefix, text)
            self.search_bar.clear()
        elif current_text.startswith("/"):
            self.search_bar.setText(text)

    def add_token(self, token_type, token_value):
        token_key = f"{token_type}{token_value}"
        if token_key in self.tokens:
            return

        token_widget = FilterToken(token_type, token_value)
        token_widget.remove_requested.connect(self.remove_token)
        self.tokens[token_key] = token_widget
        self.token_layout.addWidget(token_widget)
        self.apply_filters()

    def remove_token(self, token_type, token_value):
        token_key = f"{token_type}{token_value}"
        if token_key in self.tokens:
            self.tokens[token_key].deleteLater()
            del self.tokens[token_key]
            self.apply_filters()

    def clear_search(self):
        self.search_bar.clear()
        for token_key in list(self.tokens.keys()):
            self.tokens[token_key].deleteLater()
            del self.tokens[token_key]
        self.apply_filters()
        
    def get_filters(self):
        filters = {'authors': [], 'genres': [], 'themes': [], 'formats': []}
        for token_widget in self.tokens.values():
            token_type = token_widget.token_type.strip('/').strip(':')
            token_value = token_widget.token_value
            if token_type == 'author':
                filters['authors'].append(token_value)
            elif token_type == 'genre':
                filters['genres'].append(token_value)
            elif token_type == 'theme':
                filters['themes'].append(token_value)
            elif token_type == 'format':
                filters['formats'].append(token_value)
        return filters

    def apply_filters(self):
        search_text = self.search_bar.text()
        if search_text.startswith("/"):
             search_text = ""
        filters = self.get_filters()

        if search_text or filters.get('authors') or filters.get('genres') or filters.get('themes') or filters.get('formats'):
            self.recent_label.hide()
            self.recent_scroll_container.hide()
        else:
            self.recent_label.show()
            self.recent_scroll_container.show()

        series_list = self.library_manager.search_series_with_filters(search_text, filters)
        self.load_items(series_list)

    def apply_tag_filter(self, tag_type, tag_value):
        self.search_bar.clear()
        for token_key in list(self.tokens.keys()):
            self.tokens[token_key].deleteLater()
            del self.tokens[token_key]
        self.add_token(f'/{tag_type}:', tag_value)
        self.apply_filters()

    def search_items(self, text):
        if text.startswith("/"):
            filtered = []
            if text.startswith("/author:"):
                value = text.split(":", 1)[1]
                authors = self.library_manager.get_all_authors()
                filtered = [author for author in authors if value.lower() in author.lower()]
            elif text.startswith("/genre:"):
                value = text.split(":", 1)[1]
                genres = self.library_manager.get_all_genres()
                filtered = [genre for genre in genres if value.lower() in genre.lower()]
            elif text.startswith("/theme:"):
                value = text.split(":", 1)[1]
                themes = self.library_manager.get_all_themes()
                filtered = [theme for theme in themes if value.lower() in theme.lower()]
            elif text.startswith("/format:"):
                value = text.split(":", 1)[1]
                formats = self.library_manager.get_all_formats()
                filtered = [format for format in formats if value.lower() in format.lower()]
            else:
                filtered = [tag for tag in ["/author:", "/genre:", "/theme:", "/format:"] if text.lower() in tag.lower()]
            self.completer.setModel(QStringListModel(filtered))
            self.completer.complete()
        else:
            self.apply_filters()
        self.toggle_selection_mode(False)

    def lang_changed(self, text):
        self.language = self.lang_combo.currentData()
    
    def load_items(self, series_list=None):
        self.loading_generation += 1

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if series_list is None:
            series_list = self.library_manager.get_series()
        self.total_items_to_load = len(series_list)
        self.all_series_label.setText(f"All ({self.total_items_to_load})")
        self.received_items.clear()
        self.next_item_to_display = 0
        self.items.clear()

        if not series_list:
            return

        items_to_load = []
        for series in series_list:
            items_to_load.append(series)

        loader = ItemLoader(items_to_load, self.loading_generation, item_type='series')
        if self.loader:
            try:
                self.loader.signals.item_loaded.disconnect()
                self.loader.signals.item_invalid.disconnect()
                self.loader.signals.loading_finished.disconnect()
            except TypeError:
                pass
        self.loader = loader
        loader.signals.item_loaded.connect(self.on_item_loaded)
        loader.signals.item_invalid.connect(self.on_item_invalid)
        self.threadpool.start(loader)

    def load_recent_items(self):
        self.recent_loading_generation += 1

        while self.recent_layout.count():
            item = self.recent_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        recent_series_list = self.library_manager.get_recently_opened_series()

        if not recent_series_list:
            self.recent_label.hide()
            self.recent_scroll.hide()
            return

        self.recent_label.show()
        self.recent_scroll.show()

        loader = ItemLoader(recent_series_list, self.recent_loading_generation, item_type='series')
        if self.recent_loader:
            try:
                self.recent_loader.signals.item_loaded.disconnect()
            except TypeError:
                pass
        self.recent_loader = loader
        loader.signals.item_loaded.connect(self.on_recent_item_loaded)
        self.threadpool.start(loader)

    def on_recent_item_loaded(self, pix, series, idx, generation, item_type):
        if generation != self.recent_loading_generation:
            return
        
        widget = ThumbnailWidget(series, self.library_manager, show_chapter_number=len(series["chapters"]) > 0)
        
        series_path = Path(series['path'])
        if not series_path.exists() or not series_path.is_dir():
            widget.set_as_missing()
            widget.clicked.connect(lambda s=series, w=widget: self.missing_item_selected(s, w))
        else:
            widget.set_pixmap(pix)
            widget.set_chapter_number(series)
            widget.clicked.connect(self.recent_series_selected)

        widget.remove_requested.connect(self.remove_series)
        self.recent_layout.addWidget(widget)

    def scroll_left(self):
        scroll_bar = self.recent_scroll.horizontalScrollBar()
        current_pos = scroll_bar.value()
        viewport_width = self.recent_scroll.viewport().width()
        
        target_pos = current_pos - viewport_width
        
        closest_widget = None
        min_dist = float('inf')
        
        for i in range(self.recent_layout.count()):
            widget = self.recent_layout.itemAt(i).widget()
            if widget:
                dist = abs(widget.pos().x() - target_pos)
                if dist < min_dist:
                    min_dist = dist
                    closest_widget = widget
        
        if closest_widget:
            self.animate_scroll(closest_widget.pos().x())

    def scroll_right(self):
        scroll_bar = self.recent_scroll.horizontalScrollBar()
        current_pos = scroll_bar.value()
        viewport_width = self.recent_scroll.viewport().width()
        visible_right = current_pos + viewport_width

        target_widget = None
        for i in range(self.recent_layout.count()):
            widget = self.recent_layout.itemAt(i).widget()
            if widget and widget.pos().x() >= visible_right:
                target_widget = widget
                break
        
        if target_widget:
            self.animate_scroll(target_widget.pos().x())
        else:
            # If no widget is completely off-screen, scroll to the end
            self.animate_scroll(scroll_bar.maximum())

    def animate_scroll(self, value):
        self.scroll_animation = QPropertyAnimation(self.recent_scroll.horizontalScrollBar(), b"value")
        self.scroll_animation.setDuration(300)
        self.scroll_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.scroll_animation.setEndValue(value)
        self.scroll_animation.start()

    def update_scroll_buttons_visibility(self):
        scroll_bar = self.recent_scroll.horizontalScrollBar()
        scrollable = scroll_bar.maximum() > 0

        self.recent_scroll_left_btn.setVisible(scrollable)
        self.recent_scroll_right_btn.setVisible(scrollable)

        self.recent_scroll_left_btn.setEnabled(scroll_bar.value() > 0)
        self.recent_scroll_right_btn.setEnabled(scroll_bar.value() < scroll_bar.maximum())

    def on_item_loaded(self, pix, series, idx, generation, item_type):
        if generation != self.loading_generation:
            return
        self.received_items[idx] = (pix, series, item_type)
        self._display_pending_items()

    def on_item_invalid(self, idx, generation):
        if generation != self.loading_generation:
            return
        self.received_items[idx] = None
        self._display_pending_items()

    def _display_pending_items(self):
        if not self.total_items_to_load:
            return

        num_cols = max(1, self.scroll.viewport().width() // 160)
        
        while self.next_item_to_display < self.total_items_to_load and \
              self.next_item_to_display in self.received_items:
            
            item_data = self.received_items.pop(self.next_item_to_display)
            
            if item_data is not None:
                pix, series, item_type = item_data
                widget = ThumbnailWidget(series, self.library_manager)

                series_path = Path(series['path'])
                if not series_path.exists() or not series_path.is_dir():
                    widget.set_as_missing()
                    widget.clicked.connect(lambda s=series, w=widget: self.missing_item_selected(s, w))
                else:
                    widget.set_pixmap(pix)
                    widget.clicked.connect(self.item_selected)

                widget.remove_requested.connect(self.remove_series)
                widget.checkbox.toggled.connect(self.update_selection_count)
                self.items.append(widget)
                
                row = self.next_item_to_display // num_cols
                col = self.next_item_to_display % num_cols
                self.grid_layout.addWidget(widget, row, col)
            
            self.next_item_to_display += 1

    def item_selected(self, series: object):
        self.series_selected.emit(series)

    def missing_item_selected(self, series, widget):
        menu = QMenu(self)
        change_dir_action = menu.addAction("Change Directory")
        remove_action = menu.addAction("Remove")
        
        action = menu.exec(QCursor.pos())

        if action == change_dir_action:
            self.change_series_directory(series)
        elif action == remove_action:
            self.remove_series(series)

    def change_series_directory(self, series):
        new_path = QFileDialog.getExistingDirectory(self, "Select New Folder for " + series['name'])
        if new_path:
            self.library_manager.rescan_series_path(series['id'], new_path)
            self.load_items()
            self.load_recent_items()

    def remove_series(self, series: object):
        confirm_msg = f"Are you sure you want to remove '{series['name']}' from the library? This will not delete the files."
        reply = QMessageBox.question(self, 'Confirm Removal', confirm_msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.library_manager.remove_series(series)
            self.load_recent_items()
            self.load_items()

    def display_chapters(self, chapters):
        self.loading_generation += 1

        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.total_items_to_load = len(chapters)
        self.received_items.clear()
        self.next_item_to_display = 0

        if not chapters:
            return

        loader = ItemLoader(chapters, self.loading_generation, item_type='chapter')
        if self.loader:
            try:
                self.loader.signals.item_loaded.disconnect()
                self.loader.signals.item_invalid.disconnect()
                self.loader.signals.loading_finished.disconnect()
            except TypeError:
                pass
        self.loader = loader
        loader.signals.item_loaded.connect(self.on_item_loaded)
        loader.signals.item_invalid.connect(self.on_item_invalid)
        self.threadpool.start(loader)

    def open_reader_for_chapter(self, series, chapter):
        series_path = Path(series['path'])
        chapter_files = [str(ch['path']) for ch in series['chapters']]
        chapter_index = series['chapters'].index(chapter)
        start_file = None # Start from the beginning of the chapter

        # Get all images in the chapter
        chapter_path = Path(chapter['path'])
        images = [str(p) for p in chapter_path.iterdir() if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.mp4', '.webm', '.mkv', '.avi', '.mov'}]
        images = sorted(images, key=get_chapter_number)

        self.reader = ReaderView(chapter_files, chapter_index, start_file=start_file, images=images, language=self.language)
        self.reader.back_to_grid_callback = self.show_grid_at_path
        self.reader.show()
        self.close()

    def exit_program(self):
        QApplication.instance().quit()

    def toggle_web_access(self):
        if self.web_server_process and self.web_server_process.poll() is None:
            self.stop_web_access()
        else:
            self.start_web_access()

    def start_web_access(self):
        server_script_path = os.path.abspath("server.py")
        # The web server needs to be updated to work with the new library structure
        # For now, we will not pass any arguments
        command = [sys.executable, server_script_path]
        self.web_server_process = subprocess.Popen(command)
        self.web_access_btn.setText("Stop Web Access")

        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        url = f"http://{ip_address}:8000"

        # Generate QR code
        qr_image = qrcode.make(url)
        img_byte_array = io.BytesIO()
        qr_image.save(img_byte_array, format='PNG')
        pixmap = QPixmap()
        pixmap.loadFromData(img_byte_array.getvalue())

        # Display QR code in a dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Web Access QR Code")
        layout = QVBoxLayout()
        label = QLabel()
        label.setPixmap(pixmap)
        layout.addWidget(label)
        dialog.setLayout(layout)
        dialog.exec()

    def stop_web_access(self):
        if self.web_server_process and self.web_server_process.poll() is None:
            self.web_server_process.terminate()
        self.web_server_process = None
        self.web_access_btn.setText("Start Web Access")

    def show_add_menu(self):
        menu = QMenu(self)
        add_single_action = menu.addAction("Add Single")
        add_multiple_action = menu.addAction("Add Multiple")
        
        action = menu.exec(self.add_btn.mapToGlobal(self.add_btn.rect().bottomLeft()))
        
        if action == add_single_action:
            self.add_single_series()
        elif action == add_multiple_action:
            self.add_multiple_series()

    def show_llm_config(self):
        from src.ui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        dialog.exec()

    def show_more_options_menu(self):
        menu = QMenu(self)
        edit_action = menu.addAction("Edit")
        action = menu.exec(self.more_options_btn.mapToGlobal(self.more_options_btn.rect().bottomLeft()))
        if action == edit_action:
            self.toggle_selection_mode(True)

    def add_single_series(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Manga Series Folder")
        if folder:
            normalized_path = str(Path(folder))
            # 1. Scan manually first
            scanner = LibraryScanner()
            series_data = scanner.scan_series(normalized_path)
            
            if not series_data:
                QMessageBox.warning(self, "Invalid Folder", "Could not find any manga/media in the selected folder.")
                return

            # 2. If chapters exist, prompt user
            if series_data.get('chapters'):
                dialog = ChapterSelectionDialog(series_data['chapters'], self)
                if dialog.exec():
                    selected_chapters = dialog.get_selected_chapters()
                    # Update series_data with selected chapters
                    series_data['chapters'] = selected_chapters
                else:
                    return # User cancelled

            # Use root if no chapters selected
            if not series_data.get('chapters'):
                series_data['chapters'] = [{
                    "name": series_data['name'],
                    "path": series_data['path']
                }]

            # 3. Add to library using the (potentially modified) series data
            self.library_manager.add_series_from_data(series_data)
            
            # 4. Show info dialog
            # Need to refetch from DB to get the ID and full object
            new_series = self.library_manager.get_series_by_path(folder)
            if new_series:
                info_dialog = InfoDialog(new_series, self.library_manager, self)
                info_dialog.exec()
            
            self.load_recent_items()
            self.load_items()

    def add_multiple_series(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder with Manga Series")
        if folder:
            dialog = BatchMetadataDialog(self.library_manager, self)
            if dialog.exec():
                metadata = dialog.get_metadata()
                subfolders = [f.path for f in os.scandir(folder) if f.is_dir()]
                self.library_manager.add_series_batch(subfolders, metadata)
                self.load_recent_items()
                self.load_items()

    def show_info(self, message):
        self.info_label.setText(message)
        self.info_label.show()
        self.info_label.raise_()
        QTimer.singleShot(3000, self.info_label.hide)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(Path(url.toLocalFile()).is_dir() or url.toLocalFile().lower().endswith('.zip') for url in urls):
                event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [Path(url.toLocalFile()) for url in urls]
        valid_paths = [str(p) for p in paths if p.is_dir() or p.suffix.lower() == '.zip']

        if not valid_paths:
            return

        if len(valid_paths) == 1:
            self.add_single(valid_paths[0])
        else:
            self.add_multiple(valid_paths)

    def add_single(self, path):
        normalized_path = str(Path(path))
        # 1. Scan manually first
        scanner = LibraryScanner()
        series_data = scanner.scan_series(normalized_path)
        
        if not series_data:
             # For drag and drop, maybe just log or ignore if invalid, or show small warning?
             # Showing warning is consistent
            QMessageBox.warning(self, "Invalid Folder", "Could not find any manga/media in the selected folder.")
            return

        # 2. If chapters exist, prompt user
        if series_data.get('chapters'):
            dialog = ChapterSelectionDialog(series_data['chapters'], self)
            if dialog.exec():
                selected_chapters = dialog.get_selected_chapters()
                # Update series_data with selected chapters
                series_data['chapters'] = selected_chapters
            else:
                return # User cancelled

        # 2a. If NO chapters selected (or none found initially but logic implies finding none?),
        # If user deselected ALL chapters, treat root as the single chapter
        if not series_data.get('chapters'):
            # Construct a single chapter pointing to series root
            series_data['chapters'] = [{
                "name": series_data['name'],
                "path": series_data['path']
            }]
        self.library_manager.add_series_from_data(series_data)
        
        # 4. Show info dialog
        new_series = self.library_manager.get_series_by_path(path)
        if new_series:
            info_dialog = InfoDialog(new_series, self.library_manager, self)
            info_dialog.exec()
        self.load_recent_items()
        self.load_items()

    def add_multiple(self, paths):
        dialog = BatchMetadataDialog(self.library_manager, self)
        if dialog.exec():
            metadata = dialog.get_metadata()
            self.library_manager.add_series_batch(paths, metadata)
            self.load_recent_items()
            self.load_items()

    def toggle_selection_mode(self, enabled):
        self.is_in_selection_mode = enabled
        
        self.normal_footer.setVisible(not enabled)
        self.selection_footer.setVisible(enabled)
        
        for widget in self.items:
            widget.set_selection_mode(enabled)
            
        if not enabled:
            self.select_all_btn.setText("Select All")
        
        self.update_selection_count()

    def update_selection_count(self):
        count = sum(1 for widget in self.items if widget.is_selected())
        self.selection_count_label.setText(f"{count} items selected")

    def select_all(self):
        all_selected = all(widget.is_selected() for widget in self.items)
        
        select = not all_selected
        for widget in self.items:
            widget.checkbox.setChecked(select)
            
        if select:
            self.select_all_btn.setText("Deselect All")
        else:
            self.select_all_btn.setText("Select All")
        
        self.update_selection_count()

    def apply_batch_edit(self):
        selected_series = [widget.series for widget in self.items if widget.is_selected()]
        
        if not selected_series:
            self.toggle_selection_mode(False)
            return
            
        dialog = BatchMetadataDialog(self.library_manager, self)
        if dialog.exec():
            metadata = dialog.get_metadata()
            self.library_manager.update_series_batch(selected_series, metadata)
            self.load_items()
            
        self.toggle_selection_mode(False)

    def remove_selected_series(self):
        selected_series = [widget.series for widget in self.items if widget.is_selected()]
        
        if not selected_series:
            self.toggle_selection_mode(False)
            return
            
        confirm_msg = f"Are you sure you want to remove {len(selected_series)} series from the library? This will not delete the files."
        reply = QMessageBox.question(self, 'Confirm Removal', confirm_msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            for series in selected_series:
                self.library_manager.remove_series(series)
        self.toggle_selection_mode(False)
        self.load_recent_items()
        self.load_items()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.relayout_items)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.relayout_items()
        self.update_scroll_buttons_visibility()

    def relayout_items(self):
        if not self.items:
            return

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                # This is important to avoid deleting the widgets
                item.widget().setParent(None)

        num_cols = max(1, self.scroll.viewport().width() // 160)
        for i, widget in enumerate(self.items):
            row = i // num_cols
            col = i % num_cols
            self.grid_layout.addWidget(widget, row, col)

    def remove_last_token(self):
        if not self.tokens:
            return
        # The key of the last token is the last one in the dictionary
        last_token_key = list(self.tokens.keys())[-1]
        token_widget = self.tokens[last_token_key]
        self.remove_token(token_widget.token_type, token_widget.token_value)

    def eventFilter(self, source, event):
        if source == self.search_bar and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Backspace and self.search_bar.cursorPosition() == 0:
            self.remove_last_token()
            return True
        if hasattr(self, 'recent_scroll') and source == self.recent_scroll.viewport() and event.type() == QEvent.Type.Wheel:
            QApplication.sendEvent(self.scroll.viewport(), event)
            return True
        return super().eventFilter(source, event)

    def closeEvent(self, event):
        self.stop_web_access()
        event.accept()
