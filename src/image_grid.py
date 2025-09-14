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
from src.utils import load_thumbnail

class ImageGrid(QWidget):
    """Shows all images inside a folder as thumbnails."""
    def __init__(self, folder: Path):
        super().__init__()
        self.folder = folder

        main_layout = QVBoxLayout(self)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.back_to_grid_callback = None
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.back_to_grid)
        self.scroll_content = QWidget()
        self.flow_layout = FlowLayout(spacing=0)
        self.scroll_content.setLayout(self.flow_layout)

        self.scroll.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll)

        self.images = [p for p in sorted(folder.iterdir()) if p.is_file()]
        self.load_images()

    def load_images(self):
        for idx, img_path in enumerate(self.images):
            pix = load_thumbnail(img_path, 150, 200)
            label = ClickableLabel(img_path, idx)
            label.setPixmap(pix)
            label.clicked.connect(self.image_selected)
            self.flow_layout.addWidget(label)

    def image_selected(self, img_path: Path, idx: int):
        reader = MangaReader(self.images, idx)
        reader.back_to_grid_callback = self.show
        reader.show()
        self.close()

    def back_to_grid(self):
        """Close reader and return to folder grid."""
        if self.back_to_grid_callback:
            self.close()
            self.back_to_grid_callback()