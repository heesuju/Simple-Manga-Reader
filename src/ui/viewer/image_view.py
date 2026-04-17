import os
import tempfile
from PyQt6.QtWidgets import QGraphicsView, QFrame, QMenu, QFileDialog, QGraphicsPixmapItem, QApplication
from PyQt6.QtGui import QAction, QPainter, QTransform, QDrag
from PyQt6.QtCore import Qt, pyqtProperty, pyqtSignal, QRectF, QMimeData, QUrl

from src.ui.components.selection_overlay import AdvancedSelectionOverlay
from src.workers.view_workers import ArchiveExtractWorker, VideoTimestampFrameExtractorWorker


class ImageView(QGraphicsView):
    """QGraphicsView subclass that scales pixmap from original for sharp zooming."""
    translate_requested = pyqtSignal(str)
    zoom_started = pyqtSignal()
    ratio_changed = pyqtSignal(object)

    def __init__(self, manga_reader=None):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setStyleSheet("QGraphicsView { background: transparent; border: none; padding: 0px; margin: 0px; outline: none; }")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.manga_reader = manga_reader
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        

        self._user_scaled = False
        self._zoom_steps = 0
        self._zoom_factor = 1.0  # 1.0 = fit to screen

        self._selection_mode = False
        self._selection_overlay = AdvancedSelectionOverlay(self.viewport(), parent_view=self)
        self._selection_overlay.ratio_changed.connect(self.ratio_changed)

        self._ctrl_drag_start_pos = None
        self._frame_temp_path = None
        self._frame_extraction_active = False
        self._waiting_for_frame_drag = False

        # Smooth rendering
        hints = (
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform |
            QPainter.RenderHint.TextAntialiasing
        )
        if hasattr(QPainter.RenderHint, 'LosslessImageRendering'):
            hints |= QPainter.RenderHint.LosslessImageRendering
        self.setRenderHints(hints)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

    def contextMenuEvent(self, event):
        # Look for the top-most item that has our path data
        # (This avoids being blocked by translation overlays)
        items = self.items(event.pos())
        for item in items:
            path = item.data(0)
            if path and (hasattr(item, 'pixmap') or isinstance(item, QGraphicsPixmapItem)):
                self._show_context_menu(event.globalPos(), path)
                return
                
        super().contextMenuEvent(event)

    def _show_context_menu(self, global_pos, path):
         if not os.path.exists(path):
             return

         menu = QMenu(self)
         
         translate_action = QAction("Translate Page", self)
         translate_action.triggered.connect(lambda: self.translate_requested.emit(path))
         menu.addAction(translate_action)
         
         save_action = QAction("Save As...", self)
         save_action.triggered.connect(lambda: self._save_image(path))
         menu.addAction(save_action)

         save_area_action = QAction("Save Area As...", self)
         save_area_action.triggered.connect(self.start_area_selection)
         menu.addAction(save_area_action)
         
         menu.addSeparator()

         add_file_action = QAction("Add Alternate from File...", self)
         add_file_action.triggered.connect(self._add_alt_from_file)
         menu.addAction(add_file_action)

         add_dd_action = QAction("Add Alternates (Drag & Drop)...", self)
         add_dd_action.triggered.connect(self._open_drag_drop_dialog)
         menu.addAction(add_dd_action)

         edit_alts_action = QAction("Edit Alts...", self)
         edit_alts_action.triggered.connect(self._open_edit_alts_dialog)
         model = self.manga_reader.model if self.manga_reader else None
         if model and 0 <= model.current_index < len(model.images):
            page_obj = model.images[model.current_index]
            edit_alts_action.setEnabled(page_obj is not None and len(page_obj.images) > 1)
         else:
            edit_alts_action.setEnabled(False)
         menu.addAction(edit_alts_action)

         menu.exec(global_pos)

    def _add_alt_from_file(self):
        if not self.manga_reader: return
        
        default_dir = self.manga_reader.model.manga_dir if self.manga_reader.model else ""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, 
            "Select Images/Videos", 
            str(default_dir), 
            "Media Files (*.png *.jpg *.jpeg *.jpe *.webp *.avif *.gif *.mp4 *.webm *.mkv)"
        )
        if file_paths:
            self.manga_reader._add_alts_from_files(file_paths)

    def _open_edit_alts_dialog(self):
        if not self.manga_reader: return
        from src.ui.components.edit_alts_dialog import EditAltsDialog
        model = self.manga_reader.model
        if not model: return
        idx = model.current_index
        if idx < 0 or idx >= len(model.images): return
        page_obj = model.images[idx]
        if not page_obj or len(page_obj.images) <= 1: return
        dialog = EditAltsDialog(self, page_obj, model)
        if dialog.exec():
            self.manga_reader.reload_chapter()

    def _open_drag_drop_dialog(self):
        if not self.manga_reader: return
        
        from src.ui.components.drag_drop_alt_dialog import DragDropAltDialog
        
        target_index = self.manga_reader.model.current_index
        if target_index == -1: return
        
        page_obj = self.manga_reader.model.images[target_index]
        existing_cats = list(page_obj.get_categorized_variants().keys())

        dialog = DragDropAltDialog(self, existing_categories=existing_cats)
        if dialog.exec():
            files = dialog.get_files()
            cat = dialog.get_category()
            if files:
                 import src.ui.page_utils as page_utils
                 page_utils.process_add_alts(
                    self.manga_reader.model,
                    files,
                    target_index,
                    lambda: self.manga_reader.reload_chapter(),
                    lambda idx: self.manga_reader.model.update_page_variants(idx),
                    category=cat if cat else None
                )

    def _save_image(self, path):
        base_name = os.path.basename(path)
        ext = os.path.splitext(base_name)[1]
        
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        initial_path = os.path.join(downloads_dir, base_name)
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Image As",
            initial_path,
            f"Image (*{ext});;All Files (*)"
        )
        
        if file_path:
            try:
                if '|' in path:
                    from src.utils.img_utils import get_image_data_from_zip
                    data = get_image_data_from_zip(path)
                    if data:
                        with open(file_path, "wb") as f:
                            f.write(data)
                    else:
                        raise Exception("Failed to extract data from zip")
                else:
                    import shutil
                    shutil.copy2(path, file_path)
            except Exception as e:
                print(f"Error saving image: {e}")

    def start_area_selection(self):
        self._selection_mode = True
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setCursor(Qt.CursorShape.CrossCursor)
        # Ensure overlay covers entire viewport
        self._selection_overlay.setGeometry(self.viewport().rect())
        
        # Get the media bounds from scene
        image_bounds = QRectF()
        if self.scene():
            image_bounds = self.scene().sceneRect()
            if not image_bounds.isValid() or image_bounds.isEmpty():
                # Fallback to item bounds
                from PyQt6.QtWidgets import QGraphicsPixmapItem
                from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
                for item in self.scene().items():
                    if isinstance(item, (QGraphicsPixmapItem, QGraphicsVideoItem)):
                        image_bounds = image_bounds.united(item.sceneBoundingRect())
        
        self._selection_overlay.start_selection(image_bounds=image_bounds)
        if self.manga_reader:
            self.manga_reader._on_area_selection_started()

    def set_selection_ratio(self, ratio):
        self._selection_overlay.set_aspect_ratio(ratio)

    def get_selection_rect(self):
        """Returns the current selection rect in scene coordinates."""
        if self._selection_mode:
            rect = self._selection_overlay.get_selection()
            if rect.isValid() and not rect.isEmpty():
                return rect
        return None

    def clear_selection(self):
        self._selection_mode = False
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._selection_overlay.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_selection_overlay'):
            self._selection_overlay.setGeometry(self.viewport().rect())

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)

    def _update_overlay_bounds(self):
        """Calculates and updates the image scene bounds in the selection overlay."""
        if not hasattr(self, '_selection_overlay'):
            return
            
        image_bounds = None
        if self.scene():
            # Use sceneRect as it's specifically managed by our viewers to match media dimensions
            image_bounds = self.scene().sceneRect()
            
            # If sceneRect is not explicitly set, fallback to item bounding rects
            if not image_bounds.isValid() or image_bounds.isEmpty():
                image_bounds = QRectF()
                from PyQt6.QtWidgets import QGraphicsPixmapItem
                from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
                for item in self.scene().items():
                    if isinstance(item, (QGraphicsPixmapItem, QGraphicsVideoItem)):
                        image_bounds = image_bounds.united(item.sceneBoundingRect())
        
        self._selection_overlay.set_image_bounds(image_bounds)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._ctrl_drag_start_pos = event.pos()
            self._frame_temp_path = None
            self._frame_extraction_active = False
            self._waiting_for_frame_drag = False
            if self._is_video_mode():
                self._start_frame_extraction_async()
            else:
                path = self._get_current_image_path()
                if path and '|' not in path and path.lower().endswith(('.gif', '.webp')):
                    self._extract_gif_frame_sync()
                elif path and '|' in path:
                    self._start_archive_extraction_async(path)
            event.accept()
            return
        self._ctrl_drag_start_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._ctrl_drag_start_pos is not None
                and event.buttons() & Qt.MouseButton.LeftButton
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if (event.pos() - self._ctrl_drag_start_pos).manhattanLength() >= QApplication.startDragDistance():
                self._ctrl_drag_start_pos = None
                if self._frame_extraction_active or self._frame_temp_path:
                    if self._frame_temp_path:
                        self._execute_file_drag(self._frame_temp_path)
                    else:
                        self._waiting_for_frame_drag = True
                        self.setCursor(Qt.CursorShape.WaitCursor)
                else:
                    self._start_file_drag()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._ctrl_drag_start_pos = None
        self._waiting_for_frame_drag = False
        self._frame_extraction_active = False
        if self._frame_temp_path:
            try:
                os.remove(self._frame_temp_path)
            except OSError:
                pass
            self._frame_temp_path = None
        super().mouseReleaseEvent(event)

    def _get_current_image_path(self):
        if not self.manga_reader or not self.manga_reader.model:
            return None
        model = self.manga_reader.model
        if not model.images or model.current_index < 0 or model.current_index >= len(model.images):
            return None
        return model.images[model.current_index].path

    def _start_file_drag(self):
        path = self._get_current_image_path()
        if not path or '|' in path:
            return
        self._execute_file_drag(path)

    def _execute_file_drag(self, path):
        is_temp = (path == self._frame_temp_path)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path)])
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)
        if is_temp:
            self._frame_temp_path = None
            try:
                os.remove(path)
            except OSError:
                pass

    def _is_video_mode(self):
        if not self.manga_reader:
            return False
        from src.ui.viewer.video_viewer import VideoViewer
        return isinstance(self.manga_reader.current_viewer, VideoViewer)

    def _start_frame_extraction_async(self):
        video_viewer = self.manga_reader.video_viewer
        source_path = video_viewer.media_player.source().toLocalFile()
        if not source_path:
            return
        current_time = video_viewer.media_player.position()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        tmp.close()
        self._frame_extraction_active = True
        worker = VideoTimestampFrameExtractorWorker(source_path, current_time, tmp.name)
        worker.signals.finished.connect(lambda s, img, p: self._on_drag_frame_ready(img, p))
        self.manga_reader.thread_pool.start(worker)

    def _extract_gif_frame_sync(self):
        movie = self.manga_reader.image_viewer.movie
        if not movie:
            return
        frame = movie.currentImage()
        if frame.isNull():
            return
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        tmp.close()
        frame.save(tmp.name)
        self._frame_temp_path = tmp.name

    def _start_archive_extraction_async(self, path):
        ext = os.path.splitext(path.split('|', 1)[1])[1] or '.jpg'
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        tmp.close()
        self._frame_extraction_active = True
        worker = ArchiveExtractWorker(path, tmp.name)
        worker.signals.finished.connect(self._on_archive_ready)
        self.manga_reader.thread_pool.start(worker)

    def _on_archive_ready(self, save_path):
        if not self._frame_extraction_active:
            if save_path:
                try:
                    os.remove(save_path)
                except OSError:
                    pass
            return
        self._frame_extraction_active = False
        self._on_temp_file_ready(save_path)

    def _on_drag_frame_ready(self, q_image, save_path):
        if not self._frame_extraction_active:
            try:
                os.remove(save_path)
            except OSError:
                pass
            return
        self._frame_extraction_active = False
        q_image.save(save_path)
        self._on_temp_file_ready(save_path)

    def _on_temp_file_ready(self, save_path):
        if not save_path:
            return
        self._frame_temp_path = save_path
        if self._waiting_for_frame_drag:
            self._waiting_for_frame_drag = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._execute_file_drag(save_path)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.manga_reader and getattr(self.manga_reader, 'last_zoom_mode', '') == "Stretch":
                self.manga_reader.set_zoom_mode("Fit")
                return

            self.zoom_started.emit()
            angle = event.angleDelta().y()
            factor = 1.25 if angle > 0 else 0.8
            self._zoom_steps += 1 if angle > 0 else -1

            if self._zoom_steps > 30: self._zoom_steps = 30; return
            if self._zoom_steps < -30: self._zoom_steps = -30; return

            self._zoom_factor *= factor
            self._user_scaled = True

            if self.manga_reader:
                self.manga_reader._update_zoom(self._zoom_factor)
        else:
            super().wheelEvent(event)

    @pyqtProperty(float)
    def _zoom(self):
        return self._zoom_factor

    @_zoom.setter
    def _zoom(self, value):
        self.setTransform(QTransform().scale(value, value))
        self._zoom_factor = value

    def reset_zoom_state(self):
        self._zoom_factor = 1.0
        self._zoom_steps = 0

    def mouseDoubleClickEvent(self, event):
        if self.manga_reader:
            self.manga_reader.set_zoom_mode("Fit")
        event.accept()

