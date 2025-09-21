import zipfile
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, QLabel, QPushButton,
    QVBoxLayout, QScrollArea, QMessageBox, QFileDialog, QLineEdit, QHBoxLayout
)
from PyQt6.QtGui import QPixmap, QMouseEvent, QCursor, QKeySequence, QShortcut, QImageReader
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QRunnable, QThreadPool, QSize

from src.ui.reader_view import ReaderView
from src.ui.clickable_label import ClickableLabel
from src.ui.flow_layout import FlowLayout
from src.core.item_loader import ItemLoader
from src.utils.img_utils import get_chapter_number, get_image_size
from src.core.thumbnail_worker import get_common_size_ratio, get_image_ratio
from src.enums import ViewMode
import math

def is_double_page(size, common_ratio):
    ratio = get_image_ratio(size[0]/2, size[1])

    if math.isclose(ratio, common_ratio):
        return True
    else:
        return False

class FolderGrid(QWidget):
    """Shows a grid of folders and images."""
    def __init__(self, root_dir: str = ""):
        super().__init__()
        
        self.root_dir = Path(root_dir) if root_dir else Path.home()
        self.loading_generation = 0
        self.loader = None
        self.received_items = {}
        self.next_item_to_display = 0
        self.total_items_to_load = 0
        
        self.threadpool = QThreadPool()

        self.init_ui()
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.exit_program)
        self.showFullScreen()

    def init_ui(self):
        self.setWindowTitle("Manga Browser")
        main_layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        self.path_input = QLineEdit(str(self.root_dir))
        self.path_input.returnPressed.connect(self.path_entered)
        up_btn = QPushButton("Up")
        up_btn.clicked.connect(self.go_up)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_folder)
        
        top_layout.addWidget(up_btn)
        top_layout.addWidget(self.path_input)
        top_layout.addWidget(browse_btn)
        main_layout.addLayout(top_layout)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.flow_layout = FlowLayout(spacing=0)
        self.scroll_content.setLayout(self.flow_layout)
        self.scroll.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll)

        if self.root_dir:
            self.load_items()
    
    def load_items(self):
        """Load items from a directory or a zip file."""
        self.loading_generation += 1

        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.root_dir.exists():
            return

        items = []
        if self.root_dir.is_file() and self.root_dir.suffix.lower() == '.zip':
            # Load items from zip file
            try:
                with zipfile.ZipFile(self.root_dir, 'r') as zf:
                    image_files = sorted([f for f in zf.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')) and not f.startswith('__MACOSX')])
                    items = [f"{self.root_dir}|{image_name}" for image_name in image_files]
            except zipfile.BadZipFile:
                QMessageBox.warning(self, "Error", "Could not read the zip file.")
                self.go_up()
                return
        else:
            # Load items from directory
            try:
                all_items = list(self.root_dir.iterdir())
            except PermissionError:
                QMessageBox.warning(self, "Permission Denied", f"Cannot access the directory: {self.root_dir}")
                self.go_up()
                return

            subdirs = [p for p in all_items if p.is_dir()]
            files = [p for p in all_items if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.zip'}]

            image_files = [f for f in files if f.suffix.lower() != '.zip']
            zip_files = [f for f in files if f.suffix.lower() == '.zip']
            
            filtered_images = []
            is_implicit_cover_present = (len(image_files) == 1 and len(subdirs) > 0)

            for img in image_files:
                is_explicit_cover = img.name.lower().startswith('cover.')
                if is_explicit_cover or is_implicit_cover_present:
                    continue
                filtered_images.append(img)

            items = subdirs + zip_files + filtered_images
            items = sorted(items, key=get_chapter_number)

        # Split wide images
        common_size, ratio, _, _ = get_common_size_ratio(items)
        if common_size[0] > 0:
            new_items = []
            for item in items:
                if isinstance(item, (Path, str)):
                    size = get_image_size(item)
                    
                    if is_double_page(size, ratio):
                        new_items.append(str(item) + "_right")
                        new_items.append(str(item) + "_left")
                    else:
                        new_items.append(item)
                else:
                    new_items.append(item)
            items = new_items

        self.total_items_to_load = len(items)
        self.received_items.clear()
        self.next_item_to_display = 0

        loader = ItemLoader(items, self.loading_generation)
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

    def item_selected(self, path: object, selected_index: int):
        if isinstance(path, Path) and path.is_dir():
            self.root_dir = path
            self.path_input.setText(str(self.root_dir))
            self.load_items()
        elif isinstance(path, Path) and path.suffix.lower() == '.zip':
            self.root_dir = path
            self.path_input.setText(str(self.root_dir))
            self.load_items()
        elif (isinstance(path, Path) and path.is_file()) or (isinstance(path, str)):
            # This is either a regular image file or a virtual path to an image in a zip
            if '|' in str(path):
                # Virtual path
                zip_path_str = str(path).split('|')[0]
                zip_path = Path(zip_path_str)
                series_dir = zip_path.parent
                chapter_files = [str(p) for p in series_dir.iterdir() if p.suffix.lower() == '.zip']
                images = [item for item in self.loader.items if isinstance(item, str) and item.startswith(zip_path_str)]
                chapter_index = chapter_files.index(zip_path_str)
                start_file = path
            else:
                # Regular image file
                image_dir = Path(path).parent
                series_dir = image_dir.parent
                chapter_files = [d for d in series_dir.iterdir() if d.is_dir()]
                chapter_files = sorted(chapter_files, key=get_chapter_number)
                images = [str(item) for item in self.loader.items if isinstance(item, (str, Path)) and str(item).startswith(str(image_dir))]
                chapter_index = chapter_files.index(image_dir)
                start_file = str(path)

            self.reader = ReaderView(chapter_files, chapter_index, start_file=start_file, images=images)
            self.reader.back_to_grid_callback = self.show
            self.reader.show()
            self.close()

    def go_up(self):
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
