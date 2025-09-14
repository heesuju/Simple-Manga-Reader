from typing import List
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QPushButton, QHBoxLayout, QVBoxLayout, QLabel,
    QMessageBox, QFrame
)
from PyQt6.QtGui import QPixmap, QKeySequence, QPainter, QShortcut
from PyQt6.QtCore import Qt, QTimer
from src.image_view import ImageView

class MangaReader(QMainWindow):
    def __init__(self, manga_dirs: List[str], index:int):
        super().__init__()
        self.setWindowTitle("Manga Reader")
        if index > len(manga_dirs) - 1:
            return
        
        self.chapter_index = index
        self.chapters = manga_dirs
        self.manga_dir = Path(manga_dirs[index])
        self.back_to_grid_callback = None  # Will be set from grid


        self.showFullScreen()

        # Scene and view
        self.scene = QGraphicsScene()
        self.view = ImageView(manga_reader=self)
        self.view.setScene(self.scene)

        # Controls
        self.prev_btn = QPushButton("◀ Prev")
        self.next_btn = QPushButton("Next ▶")
        self.page_label = QLabel("0 / 0")
        self.prev_btn.clicked.connect(self.show_prev)
        self.next_btn.clicked.connect(self.show_next)

        # **Back button**
        self.back_btn = QPushButton("⬅ Back to Grid")
        self.back_btn.clicked.connect(self.back_to_grid)

        # Shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=self.show_prev)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=self.show_next)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.back_to_grid)

        # Layout
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.back_btn)
        top_layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.prev_btn)
        btn_layout.addWidget(self.page_label, 1, Qt.AlignmentFlag.AlignCenter)
        btn_layout.addWidget(self.next_btn)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.view)
        main_layout.addLayout(btn_layout)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
        self.refresh()

    def refresh(self, start_from_end:bool=False):
        # Load images
        self.images = self._scan_images(self.manga_dir)
        if start_from_end:
            self.current_index = len(self.images) - 1
        else:
            self.current_index = 0

        if not self.images:
            QMessageBox.information(self, "No images", f"No images found in: {self.manga_dir}")
        else:
            self._load_image(self.images[self.current_index])
    
    def back_to_grid(self):
        """Close reader and return to folder grid."""
        if self.back_to_grid_callback:
            self.close()
            self.back_to_grid_callback()

    @staticmethod
    def _scan_images(directory: Path):
        if not directory.exists() or not directory.is_dir():
            return []
        exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
        return [str(p) for p in sorted(directory.iterdir()) if p.suffix.lower() in exts and p.is_file()]

    def _load_image(self, path: str):
        """Load original high-res image into scene."""
        self.original_pixmap = QPixmap(path)
        self.scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(self.original_pixmap)
        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())

        self.view.reset_zoom_state()
        self.page_label.setText(f"{self.current_index + 1} / {len(self.images)}")

        QTimer.singleShot(0, self._fit_current_image)

    def _update_zoom(self, factor: float):
        """Update pixmap based on original to keep it sharp."""
        if not hasattr(self, "original_pixmap") or not hasattr(self, "pixmap_item"):
            return

        original = self.original_pixmap
        new_width = int(original.width() * factor)
        new_height = int(original.height() * factor)
        scaled = original.scaled(new_width, new_height, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        self.pixmap_item.setPixmap(scaled)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())

    def _fit_current_image(self):
        """Fit image to view and reset zoom factor."""
        if not hasattr(self, "pixmap_item"):
            return
        self.view.reset_zoom_state()
        self.view._zoom_factor = 1.0
        self.pixmap_item.setPixmap(self.original_pixmap)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def show_next(self):
        if not self.images: return
        if self.current_index < len(self.images) - 1:
            self.current_index += 1
            self._load_image(self.images[self.current_index])
        else:
            total_chapters = len(self.chapters)
            if self.chapter_index < total_chapters - 1:
                self.chapter_index += 1
                self.manga_dir = self.chapters[self.chapter_index]
                self.refresh()

    def show_prev(self):
        if not self.images: return
        if self.current_index > 0:
            self.current_index -= 1
            self._load_image(self.images[self.current_index])
        else:
            if self.chapter_index - 1 >= 0:
                self.chapter_index -= 1
                self.manga_dir = self.chapters[self.chapter_index]
                self.refresh(True)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        QTimer.singleShot(0, self._fit_current_image)

    def exit_if_not_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            QTimer.singleShot(0, self._fit_current_image)

    def showEvent(self, ev):
        super().showEvent(ev)
        QTimer.singleShot(0, self._fit_current_image)


# if __name__ == "__main__":
#     import argparse
#     parser = argparse.ArgumentParser()
#     parser.add_argument("manga_dir", nargs="?", default="C:/Utils/mangadex-dl_x64_v3.1.4/mangadex-dl/Chichi Chichi/Vol. 1 Ch. 1", help="Path to manga image folder")
#     args = parser.parse_args()

#     app = QApplication(sys.argv)
#     reader = MangaReader(args.manga_dir)
#     reader.show()
#     sys.exit(app.exec())

