import os
import shutil
from PyQt6.QtWidgets import QGraphicsView, QFrame, QMenu, QFileDialog, QGraphicsPixmapItem
from PyQt6.QtGui import QPixmap, QAction, QPainter, QTransform
from PyQt6.QtCore import Qt, pyqtProperty, pyqtSignal

class ImageView(QGraphicsView):
    """QGraphicsView subclass that scales pixmap from original for sharp zooming."""
    translate_requested = pyqtSignal(str)
    zoom_started = pyqtSignal()

    def __init__(self, manga_reader=None):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setStyleSheet("background: transparent; border: none; padding: 0px; margin: 0px;")
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

        # Smooth rendering
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform |
            QPainter.RenderHint.TextAntialiasing
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if not item:
            return

        # Handle Pixmap items or items with path data
        path = item.data(0)
        if hasattr(item, 'pixmap') and path: # Ensure it is likely our image item
             self._show_context_menu(event.globalPos(), path)
        else:
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
         
         menu.exec(global_pos)

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
                shutil.copy2(path, file_path)
            except Exception as e:
                print(f"Error copying image: {e}")

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
    
    def reset_zoom_state(self):
        self._zoom_factor = 1.0

    @_zoom.setter
    def _zoom(self, value):
        self.setTransform(QTransform().scale(value, value))
        self._zoom_factor = value

    def mouseDoubleClickEvent(self, event):
        if self.manga_reader:
            self.manga_reader.reset_zoom()
        event.accept()

