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
         
         export_action = QAction("Export in Lower Quality...", self)
         export_action.triggered.connect(lambda: self._export_lower_quality(path))
         menu.addAction(export_action)

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
                shutil.copy2(path, file_path)
            except Exception as e:
                print(f"Error copying image: {e}")

    def _export_lower_quality(self, path):
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        from PyQt6.QtCore import QByteArray, QBuffer
        from PyQt6.QtGui import QImage
        import math

        target_kb, ok = QInputDialog.getInt(
            self,
            "Export Lower Quality",
            "Enter target file size in KB:",
            value=500, min=10, max=100000
        )
        if not ok:
            return

        base_name = os.path.basename(path)
        name, _ = os.path.splitext(base_name)
        
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        initial_path = os.path.join(downloads_dir, f"{name}_lowq.jpg")
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Image As (Lower Quality)",
            initial_path,
            "JPEG Image (*.jpg);;All Files (*)"
        )
        
        if not file_path:
            return

        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Error", "Failed to load image for export.")
            return

        target_bytes = target_kb * 1024
        
        # Binary search for best quality
        low = 0
        high = 100
        best_quality = -1
        best_data = None
        
        for _ in range(8):
            mid = (low + high) // 2
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QBuffer.OpenModeFlag.WriteOnly)
            img.save(buf, "JPEG", mid)
            if ba.size() <= target_bytes:
                best_quality = mid
                best_data = ba
                low = mid + 1
            else:
                high = mid - 1
                
        if best_data is not None:
            try:
                with open(file_path, "wb") as f:
                    f.write(best_data.data())
                QMessageBox.information(self, "Success", f"Exported successfully at quality {best_quality}.\nSize: {len(best_data)//1024} KB")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to save file:\n{e}")
        else:
            # Need to resize image because even quality 0 is too large
            scale_factor = 0.9
            current_img = img
            while True:
                new_width = int(current_img.width() * scale_factor)
                new_height = int(current_img.height() * scale_factor)
                if new_width < 10 or new_height < 10:
                    break
                current_img = current_img.scaled(new_width, new_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                ba = QByteArray()
                buf = QBuffer(ba)
                buf.open(QBuffer.OpenModeFlag.WriteOnly)
                current_img.save(buf, "JPEG", 0)
                if ba.size() <= target_bytes:
                    best_data = ba
                    break

            if best_data is not None:
                 try:
                     with open(file_path, "wb") as f:
                         f.write(best_data.data())
                     QMessageBox.information(self, "Success", f"Exported successfully (resized).\nSize: {len(best_data)//1024} KB")
                 except Exception as e:
                     QMessageBox.warning(self, "Error", f"Failed to save file:\n{e}")
            else:
                 QMessageBox.warning(self, "Error", "Could not compress to the target size.")

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
        self._zoom_steps = 0

    @_zoom.setter
    def _zoom(self, value):
        self.setTransform(QTransform().scale(value, value))
        self._zoom_factor = value

    def mouseDoubleClickEvent(self, event):
        if self.manga_reader:
            self.manga_reader.reset_zoom()
        event.accept()

