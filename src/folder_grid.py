import os
#!/usr/bin/env python3
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, QLabel, QPushButton,
    QVBoxLayout, QScrollArea, QMessageBox
)
from PyQt6.QtGui import QPixmap, QMouseEvent, QCursor
from PyQt6.QtCore import Qt, QTimer

# Import the MangaReader from the previous code
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QHBoxLayout, QLineEdit
from PyQt6.QtGui import QKeySequence, QPainter, QShortcut, QColor
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from src.reader import MangaReader
from src.clickable_label import ClickableLabel
from src.flow_layout import FlowLayout
# ----- MangaReader code (unchanged except for being in this file) -----
# Paste the MangaReader class code from previous step here
# For brevity, I’ll assume it's included above as `MangaReader`
# -----------------------------------------------------------------------

import re

def get_chapter_number(path: Path):
    """Extract the chapter number as integer from the folder name."""
    name = path.name
    match = re.search(r'Ch\.\s*(\d+)', name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return -1  # folders without 'Ch.' come first (optional)


class FolderGrid(QWidget):
    """Shows a grid of manga folders with responsive thumbnails."""
    def __init__(self, manga_root: str = "manga"):
        super().__init__()
        self.manga_root = Path(manga_root)
        self.folders = [p for p in sorted(self.manga_root.iterdir()) if p.is_dir()]
        self.folders = sorted(self.folders, key=get_chapter_number)
        
        self.init_ui()

        self.showFullScreen()

    def init_ui(self):
        self.setWindowTitle("Select Manga Folder")
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()

        self.flow_layout = FlowLayout(spacing=15)
        scroll_content.setLayout(self.flow_layout)

        for idx, folder in enumerate(self.folders):
            first_page = os.listdir(folder)[0]
            thumb_path = folder / first_page
            if not thumb_path.exists():
                thumb_path = None
            
            label = ClickableLabel(folder, idx)

            if thumb_path.exists():
                pix = QPixmap(str(thumb_path)).scaled(
                    150, 200, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
                label.setPixmap(pix)
            else:
                placeholder = QPixmap(150, 200)
                placeholder.fill(QColor("gray"))
                label.setPixmap(placeholder)

            label.clicked.connect(self.folder_selected)
            self.flow_layout.addWidget(label)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

    def folder_selected(self, folder_path: Path, selected_index:int):
        self.reader = MangaReader(self.folders, selected_index)
        self.reader.back_to_grid_callback = self.show  # Show this grid again
        self.reader.show()
        self.close()
