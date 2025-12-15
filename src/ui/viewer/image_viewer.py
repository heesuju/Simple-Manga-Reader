import os
import io
from typing import Union, List
from PIL import Image, ImageQt

from PyQt6.QtWidgets import QGraphicsPixmapItem
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QTimer

from src.ui.viewer.base_viewer import BaseViewer
from src.utils.img_utils import get_image_data_from_zip, empty_placeholder
from src.workers.view_workers import AnimationFrameLoaderWorker
from src.enums import ViewMode

class ImageViewer(BaseViewer):
    def __init__(self, reader_view):
        super().__init__(reader_view)
        self.pixmap_item = None
        self.animation_timer = QTimer(reader_view)
        self.animation_timer.timeout.connect(self._show_next_frame)
        self.animation_frames = []
        self.current_frame_index = 0
        self.original_pixmap = None

    def set_active(self, active: bool):
        if active:
            if self.pixmap_item:
                self.pixmap_item.setVisible(True)
            self.reader_view.media_stack.show()
            self.reader_view.media_stack.setCurrentWidget(self.reader_view.view)
            self.reader_view.layout_btn.show()
        else:
            if self.pixmap_item:
                self.pixmap_item.setVisible(False)
            self.animation_timer.stop()
            self.reader_view.layout_btn.hide() # Hide layout button when not in image mode (e.g. video)

    def load(self, item):
        # Stop any ongoing animations
        self.animation_timer.stop()
        self.animation_frames.clear()
        self.current_frame_index = 0

        # item can be a single path (str) or a tuple of paths (for double view) or None
        if isinstance(item, tuple) or (isinstance(item, list) and len(item) == 2):
             self._load_double_images(item[0], item[1])
        elif isinstance(item, str):
             self._load_single_image(item)
        else:
            # Maybe just clear?
            pass

    def _load_single_image(self, path: str):
        self._clear_scene_pixmaps()
        
        # Handle animated images
        if path.lower().endswith((".gif", ".webp")):
            image_data = None
            if '|' in path:
                image_data = get_image_data_from_zip(path)
            elif os.path.exists(path):
                with open(path, 'rb') as f:
                    image_data = f.read()

            if image_data:
                try:
                    img = Image.open(io.BytesIO(image_data))
                    # Display first frame synchronously
                    img.seek(0)
                    first_frame_pixmap = ImageQt.toqpixmap(img)
                    self._set_pixmap(first_frame_pixmap)

                    # If animated, start worker for the rest
                    if getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1:
                        self.reader_view.loading_label.show()
                        worker = AnimationFrameLoaderWorker(path, image_data)
                        worker.signals.finished.connect(self._on_animation_loaded)
                        self.reader_view.thread_pool.start(worker)

                except Exception:
                    # Fallback to static image loading on error
                    self.original_pixmap = self._load_pixmap(path)
                    self._set_pixmap(self.original_pixmap)
        else:
            # Normal image
            self.original_pixmap = self._load_pixmap(path)
            self._set_pixmap(self.original_pixmap)

        self.reader_view.view.reset_zoom_state()
        QTimer.singleShot(0, self.reader_view.apply_last_zoom)

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
        self.pixmap_item = item1 # Tracking one of them for visibility control

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
        
        # Ensure underlying video items are hidden is handled by set_active or the video viewer, 
        # but here we just ensure this one is visible
        self.pixmap_item.setVisible(True)

    def _clear_scene_pixmaps(self):
        # Remove all QGraphicsPixmapItem except potentially the video underlay if we want to be safe,
        # but simpler is:
        for item in self.reader_view.scene.items():
            if isinstance(item, QGraphicsPixmapItem):
                # We need to distinguish regular pixmaps from video underlays.
                # In ReaderView refactor, we should probably let VideoViewer handle its underlay item exclusively
                # or give it a special tag.
                # For now, let's assume VideoViewer manages its own setVisible in set_active(False)
                # and we just add things here.
                # However, scene.clear() was used in ReaderView. 
                # Let's try to remove only items we own or clear scene if we are sure.
                # Use removeItem is safer.
                
                # Check if it is the video_last_frame_item from ReaderView (we will need to expose it or move it)
                # Let's assume we won't touch items we didn't create if possible, 
                # BUT the current ReaderView clears scene.
                pass
                
        # Better approach: Clear scene if we are switching major modes? 
        # But we share the scene with video player.
        # Let's clean up OUR items.
        if self.pixmap_item and self.pixmap_item.scene():
            self.reader_view.scene.removeItem(self.pixmap_item)
        
        # Also clean up double page items if any
        # This is tricky without tracking them all. 
        # We can implement a "clear()" method that removes all standard PixmapItems
        
        # Simplification: Clear entire scene and let VideoViewer restore its item if needed? 
        # No, VideoViewer keeps its item in scene.
        
        # Let's try to remove all QGraphicsPixmapItems that are NOT the video underlay.
        # We need a way to identify the video underlay.
        video_underlay = getattr(self.reader_view, 'video_last_frame_item', None)
        # Note: video_last_frame_item is not in reader_view anymore, it is in VideoViewer.
        # But we don't have access to VideoViewer easily here unless we go via reader_view.video_viewer
        
        video_underlay = None
        if hasattr(self.reader_view, 'video_viewer') and self.reader_view.video_viewer:
             video_underlay = self.reader_view.video_viewer.video_last_frame_item

        items_to_remove = []
        for item in self.reader_view.scene.items():
            if isinstance(item, QGraphicsPixmapItem) and item != video_underlay:
                items_to_remove.append(item)
        
        for item in items_to_remove:
            self.reader_view.scene.removeItem(item)

        self.pixmap_item = None

    def _on_animation_loaded(self, result: dict):
        self.reader_view.loading_label.hide()
        frames = result["frames"]
        duration = result["duration"]
        path = result["path"]
        
        # Check against current model image
        if path != self.reader_view.model.images[self.reader_view.model.current_index]:
            return

        if frames:
            self.animation_frames = frames
            self.animation_timer.start(duration)

    def _show_next_frame(self):
        if not self.animation_frames:
            return
        self.current_frame_index = (self.current_frame_index + 1) % len(self.animation_frames)
        self._set_pixmap(self.animation_frames[self.current_frame_index])
        self.reader_view.apply_last_zoom()

    def zoom(self, mode: str):
        if not self.pixmap_item and not (isinstance(mode, str) and mode.startswith("Fit")): 
            # Allow Fit even if no pixmap potentially? No.
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
        # Delegate to model via reader view or directly? 
        # ReaderView's show_next handles index incrementing. 
        # Viewer just shows what it's told? 
        # Actually ReaderView.show_next calls model.load_image which calls reader_view._load_image.
        # So we don't need to implement navigation logic here, it is driven by ReaderView.
        # BaseViewer.show_next was intended to be "do I handle next?" 
        # But really ReaderView handles next.
        pass

    def cleanup(self):
        self.animation_timer.stop()

    def reset(self):
        self.pixmap_item = None
        self.animation_timer.stop()
        self.animation_frames.clear()
        self.current_frame_index = 0
