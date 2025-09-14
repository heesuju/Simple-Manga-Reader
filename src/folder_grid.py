from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, QLabel, QPushButton,
    QVBoxLayout, QScrollArea, QMessageBox, QFileDialog
)
from PyQt6.QtGui import QPixmap, QMouseEvent, QCursor, QKeySequence, QShortcut, QImageReader
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QRunnable, QThreadPool, QSize

from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QHBoxLayout, QLineEdit

from src.reader import MangaReader
from src.clickable_label import ClickableLabel
from src.flow_layout import FlowLayout
from src.image_grid import ImageGrid
from src.utils import is_image_folder, get_chapter_number, load_thumbnail

class FolderLoaderSignals(QObject):
    finished = pyqtSignal()
    add_label = pyqtSignal(QPixmap, object, int)  # pixmap, folder path, index

class FolderLoader(QRunnable):
    """Load thumbnails in a separate thread."""
    def __init__(self, folders):
        super().__init__()
        self.folders = folders
        self.signals = FolderLoaderSignals()

    def run(self):
        import os
        from PyQt6.QtGui import QPixmap, QColor

        for idx, folder in enumerate(self.folders):
            first_page = os.listdir(folder)[0] if os.listdir(folder) else None
            thumb_path = folder / first_page if first_page else None

            if thumb_path and thumb_path.exists():
                pix = load_thumbnail(str(thumb_path), 150, 200)
            else:
                pix = QPixmap(150, 200)
                pix.fill(QColor("gray"))

            self.signals.add_label.emit(pix, folder, idx)

        self.signals.finished.emit()

class FolderGrid(QWidget):
    """Shows a grid of manga folders with responsive thumbnails."""
    def __init__(self, manga_root: str = ""):
        super().__init__()
        
        self.manga_root = Path(manga_root) if manga_root else None
        
        self.threadpool = QThreadPool()

        self.init_ui()
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.exit_program)
        self.showFullScreen()

    def init_ui(self):
        self.setWindowTitle("Select Manga Folder")
        main_layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        self.path_input = QLineEdit(str(self.manga_root))
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_folder)
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
            self.load_folders()
    
    def load_folders(self):
        """Load manga folders asynchronously."""
        # Clear previous widgets
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.manga_root.exists():
            return

        self.folders = [p for p in sorted(self.manga_root.iterdir()) if p.is_dir()]
        self.folders = sorted(self.folders, key=get_chapter_number)

        # Start async loading
        loader = FolderLoader(self.folders)
        loader.signals.add_label.connect(self.add_folder_label)
        self.threadpool.start(loader)

    def add_folder_label(self, pix: QPixmap, folder: Path, idx: int):
        label = ClickableLabel(folder, idx)
        label.setPixmap(pix)
        label.clicked.connect(self.folder_selected)
        self.flow_layout.addWidget(label)

    def folder_selected(self, folder_path: Path, selected_index: int):
        self.reader = MangaReader(self.folders, selected_index)
        self.reader.back_to_grid_callback = self.show
        self.reader.show()
        self.close()

    def exit_program(self):
        self.close()

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Manga Root", str(self.manga_root))
        if folder:
            self.path_input.setText(folder)
            self.manga_root = Path(folder)
            self.load_folders()