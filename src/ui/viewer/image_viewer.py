import os
import io
from typing import Union, List
from PIL import Image, ImageQt

from PyQt6.QtWidgets import QGraphicsPixmapItem
from PyQt6.QtGui import QPixmap, QMovie, QImage
from PyQt6.QtCore import Qt, QTimer, QByteArray, QBuffer, QIODevice, QThreadPool

from src.ui.viewer.base_viewer import BaseViewer
from src.utils.img_utils import get_image_data_from_zip, empty_placeholder
from src.enums import ViewMode
from src.workers.view_workers import AsyncLoaderWorker

class ImageViewer(BaseViewer):
    def __init__(self, reader_view):
        super().__init__(reader_view)
        self.pixmap_item = None
        self.movie = None
        self.movie_buffer = None # Keep reference to buffer
        self.original_pixmap = None
        self.current_request_id = 0

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
        self.current_request_id += 1
        req_id = self.current_request_id
        
        paths = []
        if isinstance(item, tuple) or (isinstance(item, list) and len(item) == 2):
             paths = [item[0], item[1]]
        elif isinstance(item, str):
             paths = [item]
        else:
            return

        # Keep animated images on main thread for QMovie
        if len(paths) == 1:
            if paths[0].lower().endswith((".gif", ".webp")):
                # Check for actual animation done in _load_single_image
                # We can just delegate.
                self._load_single_image_sync(paths[0])
                return

        worker = AsyncLoaderWorker(req_id, paths)
        worker.signals.finished.connect(self._on_async_load_finished)
        self.reader_view.thread_pool.start(worker)

    def _on_async_load_finished(self, request_id: int, results: dict):
        if request_id != self.current_request_id:
            return
        
        if len(results) == 0:
            return

        self._clear_scene_pixmaps()
        
        loaded_keys = list(results.keys())
        
        if len(loaded_keys) == 1:
            # Single
            path = loaded_keys[0]
            q_img = results[path]
            pixmap = QPixmap.fromImage(q_img)
            self.original_pixmap = pixmap
            self._set_pixmap(pixmap, path)
            
        elif len(loaded_keys) >= 2:
            imgs = list(results.values())
            paths = list(results.keys())
            pix1 = QPixmap.fromImage(imgs[0])
            pix2 = QPixmap.fromImage(imgs[1])
            
            self._setup_double_view(pix1, pix2, paths[0], paths[1])

        self.reader_view.view.reset_zoom_state()
        QTimer.singleShot(0, self.reader_view.apply_last_zoom)

    def _setup_double_view(self, pix1, pix2, path1, path2):
        item1 = QGraphicsPixmapItem(pix1)
        item1.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        item1.setPos(0, 0)
        item1.setData(0, path1)
        self.reader_view.scene.addItem(item1)

        item2 = QGraphicsPixmapItem(pix2)
        item2.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        item2.setPos(pix1.width(), 0)
        item2.setData(0, path2)
        self.reader_view.scene.addItem(item2)

        total_width = pix1.width() + pix2.width()
        total_height = max(pix1.height(), pix2.height())
        
        self.reader_view.scene.setSceneRect(0, 0, total_width, total_height)
        self.pixmap_item = item1

    def _stop_movie(self):
        if self.movie:
             self.movie.stop()
             self.movie = None
        if self.movie_buffer:
             self.movie_buffer.close()
             self.movie_buffer = None

    def _load_single_image_sync(self, path: str):
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
                self._set_pixmap(self.original_pixmap, path)
            else:
                # Fallback if QMovie fails
                self.original_pixmap = self._load_pixmap(path)
                self._set_pixmap(self.original_pixmap, path)
        else:
             # Standard sync load (fallback or specific use)
             self.original_pixmap = self._load_pixmap(path)
             self._set_pixmap(self.original_pixmap, path)

        self.reader_view.view.reset_zoom_state()
        QTimer.singleShot(0, self.reader_view.apply_last_zoom)

    def _on_movie_frame_changed(self, frame_number):
        if self.movie and self.pixmap_item:
            pixmap = self.movie.currentPixmap()
            if not pixmap.isNull():
                 self.pixmap_item.setPixmap(pixmap)

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

    def _set_pixmap(self, pixmap: QPixmap, path: str = None):
        self._clear_scene_pixmaps()
        
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.pixmap_item.setPos(0, 0)
        if path:
            self.pixmap_item.setData(0, path)
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
