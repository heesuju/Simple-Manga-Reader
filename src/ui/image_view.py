import os
import shutil
from PyQt6.QtWidgets import QGraphicsView, QFrame, QMenu, QFileDialog, QGraphicsPixmapItem, QWidget
from PyQt6.QtGui import QPixmap, QAction, QPainter, QTransform, QCursor, QColor, QPainterPath
from PyQt6.QtCore import Qt, pyqtProperty, pyqtSignal, QPoint, QRect, QSize, QRectF

from src.ui.components.selection_overlay import AdvancedSelectionOverlay

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
         
         menu.exec(global_pos)

    def _add_alt_from_file(self):
        if not self.manga_reader: return
        
        default_dir = self.manga_reader.model.manga_dir if self.manga_reader.model else ""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, 
            "Select Images/Videos", 
            str(default_dir), 
            "Media Files (*.png *.jpg *.jpeg *.webp *.gif *.mp4 *.webm *.mkv)"
        )
        if file_paths:
            self.manga_reader._add_alts_from_files(file_paths)

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

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
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
            self.manga_reader.reset_zoom()
        event.accept()

