import os
import io
from typing import Union, List
from PIL import Image, ImageQt

from PyQt6.QtWidgets import QGraphicsPixmapItem
from PyQt6.QtGui import QPixmap, QMovie
from PyQt6.QtCore import Qt, QTimer, QByteArray, QBuffer, QIODevice

from src.ui.viewer.base_viewer import BaseViewer
from src.utils.img_utils import get_image_data_from_zip, empty_placeholder
from src.enums import ViewMode

class ImageViewer(BaseViewer):
    def __init__(self, reader_view):
        super().__init__(reader_view)
        self.pixmap_item = None
        self.movie = None
        self.movie_buffer = None # Keep reference to buffer
        self.original_pixmap = None

    def set_active(self, active: bool):
        if active:
            if self.pixmap_item:
                self.pixmap_item.setVisible(True)
            self.reader_view.media_stack.show()
            self.reader_view.media_stack.setCurrentWidget(self.reader_view.view)
            self.reader_view.layout_btn.show()
            
            if self.movie and self.movie.state() == QMovie.MovieState.NotRunning:
                self.movie.start()
        else:
            if self.pixmap_item:
                self.pixmap_item.setVisible(False)
            
            if self.movie:
                self.movie.setPaused(True)
                
            self.reader_view.layout_btn.hide()

    def load(self, item):
        self._stop_movie()
        
        # item can be a single path (str) or a tuple of paths (for double view) or None
        if isinstance(item, tuple) or (isinstance(item, list) and len(item) == 2):
             self._load_double_images(item[0], item[1])
        elif isinstance(item, str):
             self._load_single_image(item)
        else:
            pass

    def _stop_movie(self):
        if self.movie:
             self.movie.stop()
             self.movie = None
        if self.movie_buffer:
             self.movie_buffer.close()
             self.movie_buffer = None

    def _load_single_image(self, path: str):
        self._clear_scene_pixmaps()
        
        # Handle animated images via QMovie
        if path.lower().endswith((".gif", ".webp")):
            self.movie = QMovie()
            self.movie.setCacheMode(QMovie.CacheMode.CacheAll)
            
            loaded = False
            if '|' in path:
                image_data = get_image_data_from_zip(path)
                if image_data:
                    self.movie_buffer = QBuffer()
                    self.movie_buffer.setData(QByteArray(image_data))
                    self.movie_buffer.open(QIODevice.OpenModeFlag.ReadOnly)
                    self.movie.setDevice(self.movie_buffer)
                    loaded = True
            elif os.path.exists(path):
                self.movie.setFileName(path)
                loaded = True
                
            if loaded and self.movie.isValid():
                self.movie.frameChanged.connect(self._on_movie_frame_changed)
                self.movie.start()
                # Initial frame
                self.original_pixmap = self.movie.currentPixmap()
                self._set_pixmap(self.original_pixmap)
            else:
                # Fallback if QMovie fails
                self.original_pixmap = self._load_pixmap(path)
                self._set_pixmap(self.original_pixmap)

        else:
            # Normal image
            self.original_pixmap = self._load_pixmap(path)
            self._set_pixmap(self.original_pixmap)

        self.reader_view.view.reset_zoom_state()
        QTimer.singleShot(0, self.reader_view.apply_last_zoom)

    def _on_movie_frame_changed(self, frame_number):
        if self.movie and self.pixmap_item:
            pixmap = self.movie.currentPixmap()
            if not pixmap.isNull():
                 self.pixmap_item.setPixmap(pixmap)

    def _load_double_images(self, image1_path, image2_path):
        self._clear_scene_pixmaps()

        pix1 = self._load_pixmap(image1_path)
        pix2 = self._load_pixmap(image2_path) if image2_path else None

        item1 = QGraphicsPixmapItem(pix1)
        item1.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        item1.setPos(0, 0)
        self.reader_view.scene.addItem(item1)

        total_width = pix1.width()
        total_height = pix1.height()

        if pix2:
            item2 = QGraphicsPixmapItem(pix2)
            item2.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            item2.setPos(pix1.width(), 0)
            self.reader_view.scene.addItem(item2)

            total_width = pix1.width() + pix2.width()
            total_height = max(pix1.height(), pix2.height())

        self.reader_view.scene.setSceneRect(0, 0, total_width, total_height)
        self.pixmap_item = item1 

        self.reader_view.view.reset_zoom_state()
        QTimer.singleShot(0, self.reader_view.apply_last_zoom)

    def _load_pixmap(self, image_source: Union[str, bytes]) -> QPixmap:
        if image_source == "placeholder":
            return empty_placeholder()

        pixmap = QPixmap()
        path_str = ""
        crop = None

        if isinstance(image_source, str):
            path_str = image_source
            if path_str.endswith("_left"):
                path_str = path_str[:-5]
                crop = "left"
            elif path_str.endswith("_right"):
                path_str = path_str[:-6]
                crop = "right"

        if isinstance(image_source, bytes) or '|' in path_str:
            image_data = image_source if isinstance(image_source, bytes) else get_image_data_from_zip(path_str)
            if image_data:
                pixmap.loadFromData(image_data)
        else:
            pixmap.load(path_str)

        if crop and not pixmap.isNull():
            width = pixmap.width()
            height = pixmap.height()
            if crop == 'left':
                return pixmap.copy(0, 0, width // 2, height)
            elif crop == 'right':
                return pixmap.copy(width // 2, 0, width // 2, height)

        return pixmap

    def _set_pixmap(self, pixmap: QPixmap):
        self._clear_scene_pixmaps()
        
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.pixmap_item.setPos(0, 0)
        self.reader_view.scene.addItem(self.pixmap_item)
        self.reader_view.scene.setSceneRect(self.pixmap_item.boundingRect())
        
        self.pixmap_item.setVisible(True)

    def _clear_scene_pixmaps(self):
        video_underlay = getattr(self.reader_view, 'video_last_frame_item', None)
        if hasattr(self.reader_view, 'video_viewer') and self.reader_view.video_viewer:
             video_underlay = self.reader_view.video_viewer.video_last_frame_item

        items_to_remove = []
        for item in self.reader_view.scene.items():
            if isinstance(item, QGraphicsPixmapItem) and item != video_underlay:
                items_to_remove.append(item)
        
        for item in items_to_remove:
            self.reader_view.scene.removeItem(item)

        self.pixmap_item = None

    def zoom(self, mode: str):
        if not self.pixmap_item and not (isinstance(mode, str) and mode.startswith("Fit")): 
            pass
            
        if mode == "Fit Page":
            self.reader_view.view.resetTransform()
            self.reader_view.view.fitInView(self.reader_view.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self.reader_view.view.reset_zoom_state()
            self.reader_view.zoom_changed.emit("Fit Page")
        elif mode == "Fit Width":
            scene_rect = self.reader_view.scene.sceneRect()
            if scene_rect.width() > 0:
                view_width = self.reader_view.view.viewport().width()
                factor = view_width / scene_rect.width()
                self.reader_view.view._zoom_factor = factor
                self.reader_view._update_zoom(factor, update_last_mode=False)
                self.reader_view.zoom_changed.emit("Fit Width")
        else:
            try:
                zoom_value = float(mode.replace('%', '')) / 100.0
                self.reader_view.view._zoom_factor = zoom_value
                self.reader_view._update_zoom(zoom_value)
            except ValueError:
                pass

    def show_next(self):
        pass

    def cleanup(self):
        self._stop_movie()

    def reset(self):
        self._stop_movie()
        self.pixmap_item = None
