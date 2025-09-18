from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, QLabel, QPushButton,
    QVBoxLayout, QScrollArea, QMessageBox, QFileDialog, QLineEdit, QHBoxLayout
)
from PyQt6.QtGui import QPixmap, QMouseEvent, QCursor, QKeySequence, QShortcut, QImageReader
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QRunnable, QThreadPool, QSize

from src.reader import MangaReader
from src.clickable_label import ClickableLabel
from src.flow_layout import FlowLayout
from src.utils import is_image_folder, get_chapter_number, load_thumbnail

class ItemLoaderSignals(QObject):
    item_loaded = pyqtSignal(QPixmap, object, int, int, str)  # pix, path, idx, gen, item_type
    item_invalid = pyqtSignal(int, int)  # idx, gen
    loading_finished = pyqtSignal(int) # gen

class ItemLoader(QRunnable):
    """Load thumbnails for folders and images in a separate thread."""
    def __init__(self, items, generation):
        super().__init__()
        self.items = items
        self.generation = generation
        self.signals = ItemLoaderSignals()

    @staticmethod
    def _folder_is_valid(folder_path: Path) -> bool:
        """Checks if a folder contains images or subfolders with images (1 level deep)."""
        try:
            # Check for images in the folder itself
            if any(f.is_file() and f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'} for f in folder_path.iterdir()):
                return True

            # Check subfolders for images
            for subfolder in folder_path.iterdir():
                if subfolder.is_dir():
                    try:
                        if any(f.is_file() and f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'} for f in subfolder.iterdir()):
                            return True
                    except PermissionError:
                        continue
        except PermissionError:
            return False
        return False

    def run(self):
        from PyQt6.QtGui import QPixmap, QColor
        for idx, item_path in enumerate(self.items):
            item_type = ''
            if item_path.is_dir():
                if not ItemLoader._folder_is_valid(item_path):
                    self.signals.item_invalid.emit(idx, self.generation)
                    continue
                item_type = 'folder'
            elif item_path.is_file():
                item_type = 'image'
            
            pix = None
            if item_path.is_dir():
                try:
                    first_image = next(f for f in item_path.iterdir() if f.is_file() and f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'})
                    if first_image:
                        pix = load_thumbnail(str(first_image), 150, 200)
                except (StopIteration, PermissionError):
                    pass  # No images in folder or permission error
            elif item_path.is_file():
                pix = load_thumbnail(str(item_path), 150, 200)

            if not pix:
                pix = QPixmap(150, 200)
                pix.fill(QColor("gray"))

            self.signals.item_loaded.emit(pix, item_path, idx, self.generation, item_type)
        
        self.signals.loading_finished.emit(self.generation)

class FolderGrid(QWidget):
    """Shows a grid of folders and images."""
    def __init__(self, manga_root: str = ""):
        super().__init__()
        
        self.manga_root = Path(manga_root) if manga_root else Path.home()
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
        self.path_input = QLineEdit(str(self.manga_root))
        self.path_input.returnPressed.connect(self.path_entered)
        up_btn = QPushButton("Up")
        up_btn.clicked.connect(self.go_up)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_folder)
        
        top_layout.addWidget(up_btn)
        top_layout.addWidget(self.path_input)
        top_layout.addWidget(browse_btn)
        main_layout.addLayout(top_layout)

        # --- Scrollable grid ---
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.flow_layout = FlowLayout(spacing=0)
        self.scroll_content.setLayout(self.flow_layout)
        self.scroll.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll)

        if self.manga_root:
            self.load_items()
    
    def load_items(self):
        """Load folders and images asynchronously, filtering out covers."""
        self.loading_generation += 1

        # Clear previous widgets
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.manga_root.exists():
            return

        try:
            all_items = list(self.manga_root.iterdir())
        except PermissionError:
            QMessageBox.warning(self, "Permission Denied", f"Cannot access the directory: {self.manga_root}")
            self.go_up()
            return

        subdirs = [p for p in all_items if p.is_dir()]
        image_files = [p for p in all_items if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}]

        # Cover filtering logic
        filtered_images = []
        is_implicit_cover_present = (len(image_files) == 1 and len(subdirs) > 0)

        for img in image_files:
            is_explicit_cover = img.name.lower().startswith('cover.')
            if is_explicit_cover or is_implicit_cover_present:
                continue  # Hide cover
            filtered_images.append(img)

        items = subdirs + filtered_images
        items = sorted(items, key=get_chapter_number)

        self.total_items_to_load = len(items)
        self.received_items.clear()
        self.next_item_to_display = 0

        # Start async loading
        loader = ItemLoader(items, self.loading_generation)
        if self.loader:
            try:
                self.loader.signals.item_loaded.disconnect()
                self.loader.signals.item_invalid.disconnect()
                self.loader.signals.loading_finished.disconnect()
            except TypeError:
                pass # was not connected
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

    def item_selected(self, path: Path, selected_index: int):
        if path.is_dir():
            self.manga_root = path
            self.path_input.setText(str(self.manga_root))
            self.load_items()
        elif path.is_file():
            image_dir = path.parent
            series_dir = image_dir.parent

            # Get all directories in the series_dir, and sort them
            chapter_dirs = [d for d in series_dir.iterdir() if d.is_dir()]
            chapter_dirs = sorted(chapter_dirs, key=get_chapter_number)

            try:
                chapter_index = chapter_dirs.index(image_dir)
            except ValueError:
                chapter_index = 0

            chapter_dirs_str = [d for d in chapter_dirs]

            self.reader = MangaReader(chapter_dirs_str, chapter_index, start_file=str(path))
            self.reader.back_to_grid_callback = self.show
            self.reader.show()
            self.close()

    def go_up(self):
        if self.manga_root:
            parent = self.manga_root.parent
            if parent.exists() and parent != self.manga_root:
                self.manga_root = parent
                self.path_input.setText(str(self.manga_root))
                self.load_items()

    def path_entered(self):
        path_text = self.path_input.text()
        path = Path(path_text)
        if path.exists() and path.is_dir():
            self.manga_root = path
            self.load_items()
        else:
            QMessageBox.warning(self, "Invalid Path", "The entered path does not exist or is not a directory.")
            self.path_input.setText(str(self.manga_root))


    def exit_program(self):
        self.close()

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", str(self.manga_root))
        if folder:
            self.path_input.setText(folder)
            self.manga_root = Path(folder)
            self.load_items()
