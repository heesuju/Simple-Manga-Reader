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
from src.page_input import PageInput
import math

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
        

        self.page_label = PageInput("Page", 0,0)
        self.ch_label = PageInput("Chapter", 0,0)

        self.page_label.enterPressed.connect(self.change_page)
        self.ch_label.enterPressed.connect(self.change_chapter)

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
        top_layout.setSpacing(0)
        top_layout.addWidget(self.back_btn)
        top_layout.addWidget(self.ch_label, 1, Qt.AlignmentFlag.AlignCenter)
        top_layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.page_label, 1, Qt.AlignmentFlag.AlignCenter)
        btn_layout.setSpacing(0)
        

        main_layout = QVBoxLayout()
        main_layout.setSpacing(0)
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.view)
        main_layout.addLayout(btn_layout)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)


        # Overlay container
        self.overlay_container = QWidget(self.centralWidget())
        self.overlay_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.overlay_container.setStyleSheet("background: transparent;")
        self.overlay_container.raise_()  # ensure it is on top
                

        # Left/right overlay buttons
        self.prev_btn = QPushButton("", self.overlay_container)
        self.next_btn = QPushButton("", self.overlay_container)
        for btn in (self.prev_btn, self.next_btn):
            btn.setStyleSheet("background-color: rgba(0,0,0,0.0); color: white; font-size: 32px; border: none;")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_btn.clicked.connect(self.show_prev)
        self.next_btn.clicked.connect(self.show_next)
        # Layout for overlay container
        overlay_layout = QHBoxLayout(self.overlay_container)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.addWidget(self.prev_btn)
        overlay_layout.addWidget(self.next_btn)
        overlay_layout.setStretch(0, 1)
        overlay_layout.setStretch(1, 1)

        original_resize = self.view.resizeEvent
        def resizeEvent(event):
            self._update_overlay_size(event)
            if original_resize:
                original_resize(event)
        self.view.resizeEvent = resizeEvent
        
        self.refresh()

    def _update_overlay_size(self, event=None):
        # Match overlay container to view
        geo = self.view.geometry()
        self.overlay_container.setGeometry(geo)

        w, h = geo.width(), geo.height()
        self.prev_btn.setGeometry(0, 0, w // 2, h)     # Left half
        self.next_btn.setGeometry(w // 2, 0, w // 2, h) # Right half

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
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())

        self.view.reset_zoom_state()
        self.page_label.set_total(len(self.images))
        self.ch_label.set_total(len(self.chapters))
        
        self.page_label.set_value(self.current_index + 1)
        self.ch_label.set_value(self.chapter_index + 1)

        QTimer.singleShot(0, self._fit_current_image)

    def _update_zoom(self, factor: float):
        """Zoom the view using GPU-accelerated transformation."""
        self.view.resetTransform()  # reset previous zoom
        self.view.scale(factor, factor)

    def _fit_current_image(self):
        """Fit image to view and reset zoom factor."""
        if not hasattr(self, "pixmap_item"):
            return
        
        self.view.resetTransform()  # remove any previous zoom
        self.view.reset_zoom_state()
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.overlay_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

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

    def change_page(self, page:int):
        index = page - 1
        if index < 0:
            index = 0
        elif index > len(self.images) - 1:
            index = len(self.images) - 1
            
        self.current_index = index
        self._load_image(self.images[self.current_index])

    def change_chapter(self, chapter:int):
        index = chapter - 1
        total_chapters = len(self.chapters)
        
        if index < 0:
            index = 0
        elif index > total_chapters - 1:
            index = total_chapters - 1
        
        self.chapter_index = index
        self.manga_dir = self.chapters[self.chapter_index]
        self.refresh()

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
        QTimer.singleShot(50, self._update_overlay_size)

    def wheelEvent(self, event):
        # Forward to view for zooming
        self.view.wheelEvent(event)
        if not math.isclose(self.view._zoom_factor, 1.0):
            self.overlay_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        else:
            self.overlay_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)