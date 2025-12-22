import os
import io
import time
from typing import Union, List
from PIL import Image, ImageQt

from PyQt6.QtWidgets import QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsTextItem, QGraphicsItem
from PyQt6.QtGui import QPixmap, QMovie, QImage, QBrush, QColor, QFont, QPen, QTextOption
from PyQt6.QtCore import Qt, QTimer, QByteArray, QBuffer, QIODevice, QThreadPool, QSize

from src.ui.viewer.base_viewer import BaseViewer
from src.utils.img_utils import get_image_data_from_zip, empty_placeholder
from src.enums import ViewMode
from src.workers.view_workers import AsyncLoaderWorker, AsyncScaleWorker

class ImageViewer(BaseViewer):
    def __init__(self, reader_view):
        super().__init__(reader_view)
        self.pixmap_item = None
        self.overlay_items = []
        self.movie = None
        self.movie_buffer = None # Keep reference to buffer
        self.original_pixmap = None # Stores the full resolution source
        self.current_request_id = 0
        
        # High Quality Scaling State
        self.scaled_pixmap_item = None # Separate item for high-quality scaled version
        self.hq_generation_id = 0
        self.last_viewport_size = None
        self.target_hq_size = None
        
        self.resize_timer = QTimer(reader_view)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.setInterval(100) # 100ms debounce
        self.resize_timer.timeout.connect(self._trigger_hq_rescale)

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
        
        # Reset HQ state
        self.hq_generation_id += 1
        self.scaled_pixmap_item = False 
        self.original_pixmap = None
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
            self._trigger_hq_rescale() # Attempt to load HQ version immediately
            
        elif len(loaded_keys) >= 2:
            imgs = list(results.values())
            paths = list(results.keys())
            pix1 = QPixmap.fromImage(imgs[0])
            pix2 = QPixmap.fromImage(imgs[1])
            
            self._setup_double_view(pix1, pix2, paths[0], paths[1])
            # Scaling double view is complex, skipping for simplicty in this iteration unless requested.
            # Usually double page spreads don't need as aggressive downscaling as they fill the screen more.

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
        
        self.original_pixmap = None # Disable HQ scaling for double view for now

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
             self._trigger_hq_rescale()

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
        self.scaled_pixmap_item = None
        self.clear_overlays()

    def zoom(self, mode: str):
        if not self.pixmap_item and not (isinstance(mode, str) and mode.startswith("Fit")): 
            pass
        
        # Always restore original before any zoom operation to prevent
        # stretching a low-res scaled image
        if self.scaled_pixmap_item and self.original_pixmap:
            self._restore_original_pixmap()

        if mode == "Fit Page":
            self.reader_view.view.resetTransform()
            
            scene_rect = self.reader_view.scene.sceneRect()
            viewport_rect = self.reader_view.view.viewport().rect()
            
            if scene_rect.width() > 0 and scene_rect.height() > 0:
                scale_w = viewport_rect.width() / scene_rect.width()
                scale_h = viewport_rect.height() / scene_rect.height()
                scale = min(scale_w, scale_h)
                
                self.reader_view.view.scale(scale, scale)
                self.reader_view.view.centerOn(scene_rect.center())
                
                # Update zoom factor to match reality so scrolling starts smoothly
                self.reader_view.view._zoom_factor = scale

            self.reader_view.zoom_changed.emit("Fit Page")
            self._trigger_hq_rescale()

        elif mode == "Fit Width":
            scene_rect = self.reader_view.scene.sceneRect()
            if scene_rect.width() > 0:
                view_width = self.reader_view.view.viewport().width()
                factor = view_width / scene_rect.width()
                self.reader_view.view._zoom_factor = factor
                self.reader_view._update_zoom(factor, update_last_mode=False)
                self.reader_view.zoom_changed.emit("Fit Width")
                self._trigger_hq_rescale()
        else:
            try:
                zoom_value = float(mode.replace('%', '')) / 100.0
                
                self.reader_view.view.resetTransform()
                self.reader_view.view.scale(zoom_value, zoom_value)
                
                # Center on the image to ensure predictable positioning
                if self.reader_view.scene.sceneRect().isValid():
                     self.reader_view.view.centerOn(self.reader_view.scene.sceneRect().center())

                self.reader_view.view._zoom_factor = zoom_value
                
                # Manually update tracking in ReaderView to keep UI in sync
                self.reader_view.last_zoom_mode = f"{int(zoom_value*100)}%"
                self.reader_view.zoom_changed.emit(self.reader_view.last_zoom_mode)
                
                self._trigger_hq_rescale()
            except ValueError:
                pass

    def on_resize(self, event):
        # Immediate restore on resize start/event
        if self.scaled_pixmap_item and self.original_pixmap:
             self._restore_original_pixmap()
             
        # Trigger rescale debounce
        self.resize_timer.start()

    def on_zoom_changed(self, zoom_mode: str):
        # Called when zoom level changes from ReaderView (manual or fit)
        self.resize_timer.start()

    def _trigger_hq_rescale(self):
        # Logic to decide if we need to scale
        if not self.original_pixmap or self.original_pixmap.isNull():
            return

        if self.movie:
            return
            
        view = self.reader_view.view
        
        scene_rect = self.reader_view.scene.sceneRect()
        if scene_rect.isEmpty(): return

        mapped_poly = view.mapFromScene(scene_rect)
        mapped_rect = mapped_poly.boundingRect()
        
        dpr = view.viewport().devicePixelRatio()
        target_w = int(mapped_rect.width() * dpr)
        original_w = self.original_pixmap.width()
        
        if target_w < (original_w * 0.9):
             self.hq_generation_id += 1
             q_image = self.original_pixmap.toImage()
             worker = AsyncScaleWorker(q_image, target_w, 0, self.hq_generation_id) # reusing index 0
             worker.signals.finished.connect(self._on_hq_scale_finished)
             self.reader_view.thread_pool.start(worker)
        else:
             if self.scaled_pixmap_item:
                 self._restore_original_pixmap()

    def _on_hq_scale_finished(self, index, q_image, generation_id):
        if generation_id != self.hq_generation_id:
            return
            
        if not self.pixmap_item:
            return
            
        scaled_pixmap = QPixmap.fromImage(q_image)
        
        original_w = self.original_pixmap.width()
        scaled_w = scaled_pixmap.width()
        
        if scaled_w == 0: return

        scale_factor = original_w / scaled_w
        
        self.pixmap_item.setPixmap(scaled_pixmap)
        self.pixmap_item.setScale(scale_factor)
        
        self.scaled_pixmap_item = True # flag

    def _restore_original_pixmap(self):
        if not self.original_pixmap or not self.pixmap_item:
            return
            
        self.pixmap_item.setPixmap(self.original_pixmap)
        self.pixmap_item.setScale(1.0)
        self.scaled_pixmap_item = False

    def show_next(self):
        pass

    def cleanup(self):
        self._stop_movie()
        self.resize_timer.stop()

    def show_overlays(self, overlays: list):
        self.clear_overlays()
        
        if not self.pixmap_item:
            return

        # ... (overlay logic same as before, ensuring it respects item transform) ...
        # If item is scaled, overlays are children or siblings? 
        # Overlays are added to scene directly in previous code.
        # Position is absolute scene coordinates. 
        # Since scene logic coords = original image size, this works perfectly even if we scale the item back up.
        
        for overlay in overlays:
            bbox = overlay['bbox'] # [x, y, w, h]
            text = overlay['text']
            
            x, y, w, h = bbox
            
            # Create background (white with some opacity)
            bg_item = QGraphicsRectItem(x, y, w, h)
            bg_item.setBrush(QBrush(QColor(255, 255, 255, 255)))
            bg_item.setPen(QPen(Qt.PenStyle.NoPen))
            bg_item.setZValue(10) # Above image
            
            self.reader_view.scene.addItem(bg_item)
            self.overlay_items.append(bg_item)
            
            # Create text
            text_item = QGraphicsTextItem(text)
            text_item.setDefaultTextColor(Qt.GlobalColor.black)
            
            # Dynamic font scaling
            min_font_size = 6
            max_font_size = 30 
            
            font = QFont("Arial")
            
            # Text config
            option = text_item.document().defaultTextOption()
            option.setAlignment(Qt.AlignmentFlag.AlignCenter) 
            option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere) 
            text_item.document().setDefaultTextOption(option)

            # Start from max size and go down
            final_font_size = min_font_size
            for size in range(max_font_size, min_font_size - 1, -2):
                font.setPointSize(size)
                text_item.setFont(font)
                text_item.setTextWidth(w)
                
                # Check height
                if text_item.boundingRect().height() <= h:
                    final_font_size = size
                    break
            
            if text_item.boundingRect().height() > h:
                final_font_size = min_font_size
            
            font.setPointSize(final_font_size)
            text_item.setFont(font)
            text_item.setTextWidth(w)
            
            actual_h = text_item.boundingRect().height()
            y_offset = max(0, (h - actual_h) / 2)
            
            text_item.setPos(x, y + y_offset)
            text_item.setZValue(11) 
            
            self.reader_view.scene.addItem(text_item)
            self.overlay_items.append(text_item)

    def clear_overlays(self):
        for item in self.overlay_items:
            if item.scene() == self.reader_view.scene:
                self.reader_view.scene.removeItem(item)
        self.overlay_items.clear()

    def reset(self):
        self._stop_movie()
        self.resize_timer.stop()
        self.pixmap_item = None
        self.original_pixmap = None
        self.clear_overlays()
