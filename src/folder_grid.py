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
    QMessageBox, QFileDialog, QLineEdit, QHBoxLayout, QComboBox, QDialog, QListWidget, QListWidgetItem, QMenu, QApplication, QGridLayout
)
from PyQt6.QtGui import QPixmap, QShortcut, QKeySequence
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QRunnable, QThreadPool, QSize

from src.ui.reader_view import ReaderView
from src.ui.clickable_label import ClickableLabel
from src.ui.thumbnail_widget import ThumbnailWidget
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
        self.loading_generation = 0
        self.loader = None
        self.received_items = {}
        self.next_item_to_display = 0
        self.total_items_to_load = 0
        self.language = 'ko'
        self.current_view = 'series' # or 'chapters'
        self.current_series = None
        self.items = []
        
        self.threadpool = QThreadPool()
        self.web_server_process = None

        self.init_ui()
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.exit_program)
        self.showFullScreen()

    def init_ui(self):
        self.setWindowTitle("Manga Browser")
        main_layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search...")
        self.search_bar.textChanged.connect(self.search_items)
        top_layout.addWidget(self.search_bar)

        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self.show_add_menu)
        self.web_access_btn = QPushButton("Start Web Access")
        self.web_access_btn.clicked.connect(self.toggle_web_access)

        top_layout.addWidget(self.add_btn)
        top_layout.addWidget(self.web_access_btn)
        main_layout.addLayout(top_layout)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.grid_layout = QGridLayout(self.scroll_content)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll)

        self.info_label = QLabel(self)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet("background-color: rgba(0, 0, 0, 180); color: white; padding: 10px; border-radius: 5px;")
        self.info_label.hide()

        self.load_items()

    def search_items(self, text):
        if not text:
            self.load_items()
            return
        
        filtered_series = self.library_manager.search_series(text)
        self.load_items(filtered_series)

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
                widget.set_pixmap(pix)
                widget.clicked.connect(self.item_selected)
                widget.remove_requested.connect(self.remove_series)
                self.items.append(widget)
                
                row = self.next_item_to_display // num_cols
                col = self.next_item_to_display % num_cols
                self.grid_layout.addWidget(widget, row, col)
            
            self.next_item_to_display += 1



    def item_selected(self, series: object):
        self.series_selected.emit(series)

    def remove_series(self, series: object):
        self.library_manager.remove_series(series)
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
        images = [str(p) for p in chapter_path.iterdir() if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}]
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

    def add_single_series(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Manga Series Folder")
        if folder:
            self.library_manager.add_series(folder)
            self.load_items()

    def add_multiple_series(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder with Manga Series")
        if folder:
            subfolders = [f.path for f in os.scandir(folder) if f.is_dir()]
            self.library_manager.add_series_batch(subfolders)
            self.load_items()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.relayout_items()

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

    def closeEvent(self, event):
        self.stop_web_access()
        event.accept()