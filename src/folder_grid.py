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
    QWidget, QLabel, QPushButton, QVBoxLayout, QScrollArea, 
    QMessageBox, QFileDialog, QLineEdit, QHBoxLayout, QComboBox, QDialog, QListWidget, QListWidgetItem
)
from PyQt6.QtGui import QPixmap, QShortcut, QKeySequence
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QRunnable, QThreadPool, QSize

from src.ui.reader_view import ReaderView
from src.ui.clickable_label import ClickableLabel
from src.ui.flow_layout import FlowLayout
from src.core.item_loader import ItemLoader
from src.utils.img_utils import get_chapter_number, get_image_size
from src.core.thumbnail_worker import get_common_size_ratio, get_image_ratio
from src.enums import ViewMode
import math
import json
from src.core.library_scanner import LibraryScanner

def run_server(script_path, root_dir):
    import subprocess
    import sys
    subprocess.run([sys.executable, script_path, root_dir])


def is_double_page(size, common_ratio):
    ratio = get_image_ratio(size[0]/2, size[1])

    if math.isclose(ratio, common_ratio):
        return True
    else:
        return False

class FolderGrid(QWidget):
    """Shows a grid of folders and images."""
    series_selected = pyqtSignal(object)

    def __init__(self, library_manager, parent=None):
        super().__init__(parent)
        
        self.library_manager = library_manager
        self.root_dir = Path.home() # Default value, can be removed later
        self.loading_generation = 0
        self.loader = None
        self.received_items = {}
        self.next_item_to_display = 0
        self.total_items_to_load = 0
        self.language = 'ko'
        self.current_view = 'series' # or 'chapters'
        self.current_series = None
        
        self.threadpool = QThreadPool()
        self.web_server_process = None

        self.init_ui()
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.exit_program)
        self.showFullScreen()

    def init_ui(self):
        self.setWindowTitle("Manga Browser")
        main_layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        back_btn = QPushButton("←")
        back_btn.clicked.connect(self.go_up)
        self.path_input = QLineEdit(str(self.root_dir))
        self.path_input.returnPressed.connect(self.path_entered)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_folder)
        self.web_access_btn = QPushButton("Start Web Access")
        self.web_access_btn.clicked.connect(self.toggle_web_access)
        
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(self.open_settings)
        self.scan_btn = QPushButton("Scan Library")
        self.scan_btn.clicked.connect(self.scan_library)

        top_layout.addWidget(back_btn)
        top_layout.addWidget(self.path_input)
        top_layout.addWidget(browse_btn)
        # top_layout.addWidget(self.lang_combo)
        top_layout.addWidget(self.web_access_btn)
        top_layout.addWidget(self.settings_btn)
        top_layout.addWidget(self.scan_btn)
        main_layout.addLayout(top_layout)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.flow_layout = FlowLayout(spacing=0)
        self.scroll_content.setLayout(self.flow_layout)
        self.scroll.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll)

        self.info_label = QLabel(self)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet("background-color: rgba(0, 0, 0, 180); color: white; padding: 10px; border-radius: 5px;")
        self.info_label.hide()

        if self.root_dir:
            self.load_items()

    def lang_changed(self, text):
        self.language = self.lang_combo.currentData()
    
    def load_items(self):
        """Load series from the library."""
        self.loading_generation += 1

        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        series_list = self.library_manager.get_series()
        self.total_items_to_load = len(series_list)
        self.received_items.clear()
        self.next_item_to_display = 0

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

    def show_grid_at_path(self, path: Path):
        self.root_dir = path
        self.path_input.setText(str(self.root_dir))
        self.load_items()
        self.show()

    def on_item_loaded(self, pix, path, idx, generation, item_type):
        if generation != self.loading_generation:
            return
        self.received_items[idx] = (pix, path, item_type)
        self._display_pending_items()

    def on_item_invalid(self, idx, generation):
        if generation != self.loading_generation:
            return
        self.received_items[idx] = None
        self._display_pending_items()

    def _display_pending_items(self):
        while self.next_item_to_display < self.total_items_to_load and \
              self.next_item_to_display in self.received_items:
            
            item_data = self.received_items.pop(self.next_item_to_display)
            
            if item_data is not None:
                pix, path, item_type = item_data
                label = ClickableLabel(path, self.next_item_to_display, item_type)
                label.setPixmap(pix)
                label.clicked.connect(self.item_selected)
                self.flow_layout.addWidget(label)
            
            self.next_item_to_display += 1



    def item_selected(self, item: object, selected_index: int):
        if self.current_view == 'series':
            self.series_selected.emit(item)
        elif self.current_view == 'chapters':
            # This part is now handled by ChapterListView, but we keep it for now
            # to avoid breaking things before the full transition.
            series_path = Path(self.current_series['path'])
            chapter_files = [str(ch['path']) for ch in self.current_series['chapters']]
            chapter_index = selected_index
            start_file = None # Start from the beginning of the chapter

            # Get all images in the chapter
            chapter_path = Path(item['path'])
            images = [str(p) for p in chapter_path.iterdir() if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}]
            images = sorted(images, key=get_chapter_number)

            self.reader = ReaderView(chapter_files, chapter_index, start_file=start_file, images=images, language=self.language)
            self.reader.back_to_grid_callback = self.show_grid_at_path
            self.reader.show()
            self.close()

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
        images = [str(p) for p in chapter_path.iterdir() if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}]
        images = sorted(images, key=get_chapter_number)

        self.reader = ReaderView(chapter_files, chapter_index, start_file=start_file, images=images, language=self.language)
        self.reader.back_to_grid_callback = self.show_grid_at_path
        self.reader.show()
        self.close()

    def go_up(self):
        if self.current_view == 'chapters':
            self.load_items() # Go back to series view
            self.current_view = 'series'
            self.current_series = None
        else:
            if self.root_dir:
                parent = self.root_dir.parent
                if parent.exists() and parent != self.root_dir:
                    self.root_dir = parent
                    self.path_input.setText(str(self.root_dir))
                    self.load_items()

    def path_entered(self):
        path_text = self.path_input.text()
        path = Path(path_text)
        if path.exists() and (path.is_dir() or path.suffix.lower() == '.zip'):
            self.root_dir = path
            self.load_items()
        else:
            QMessageBox.warning(self, "Invalid Path", "The entered path does not exist or is not a directory/zip file.")
            self.path_input.setText(str(self.root_dir))

    def exit_program(self):
        self.close()

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", str(self.root_dir))
        if folder:
            self.path_input.setText(folder)
            self.root_dir = Path(folder)
            self.load_items()

    def toggle_web_access(self):
        if self.web_server_process and self.web_server_process.poll() is None:
            self.stop_web_access()
        else:
            self.start_web_access()

    def start_web_access(self):
        server_script_path = os.path.abspath("server.py")
        command = [sys.executable, server_script_path] + self.library_manager.library['root_directories']
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

    def closeEvent(self, event):
        self.stop_web_access()
        event.accept()

    def open_settings(self):
        dialog = SettingsDialog(self.library_manager, self)
        dialog.exec()

    def scan_library(self):
        self.library_manager.scan_library()
        self.load_items()

class SettingsDialog(QDialog):
    def __init__(self, library_manager, parent=None):
        super().__init__(parent)
        self.library_manager = library_manager
        self.setWindowTitle("Settings")
        self.layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        for directory in self.library_manager.library['root_directories']:
            self.list_widget.addItem(directory)

        self.add_btn = QPushButton("Add Directory")
        self.add_btn.clicked.connect(self.add_directory)
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self.remove_directory)
        self.save_btn = QPushButton("Save and Close")
        self.save_btn.clicked.connect(self.save_and_close)

        self.layout.addWidget(QLabel("Manga Library Folders:"))
        self.layout.addWidget(self.list_widget)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.remove_btn)
        self.layout.addLayout(btn_layout)
        self.layout.addWidget(self.save_btn)

    def add_directory(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.library_manager.add_root_directory(folder)
            self.list_widget.addItem(folder)

    def remove_directory(self):
        for item in self.list_widget.selectedItems():
            self.library_manager.remove_root_directory(item.text())
            self.list_widget.takeItem(self.list_widget.row(item))

    def save_and_close(self):
        self.library_manager.save_library()
        self.accept()