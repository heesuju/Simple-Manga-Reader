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
from PyQt6.QtGui import QKeySequence, QPainter, QShortcut
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from src.reader import MangaReader
from src.folder_grid import FolderGrid

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "manga_root", nargs="?", default=""
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)

    # Show folder grid first
    folder_ui = FolderGrid(args.manga_root)
    folder_ui.show()

    sys.exit(app.exec())
