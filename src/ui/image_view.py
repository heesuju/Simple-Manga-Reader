import math
from PyQt6.QtWidgets import QGraphicsView, QFrame
from PyQt6.QtGui import QPixmap, QKeySequence, QPainter, QShortcut, QTransform
from PyQt6.QtCore import Qt, QTimer, pyqtProperty

class ImageView(QGraphicsView):
    """QGraphicsView subclass that scales pixmap from original for sharp zooming."""
    def __init__(self, manga_reader=None):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.NoFrame)
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
            QPainter.RenderHint.SmoothPixmapTransform
        )

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.manga_reader and not self._user_scaled:
            QTimer.singleShot(0, self.manga_reader._fit_current_image)