from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QPen, QCursor
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect, QRectF, QSize, QSizeF, QPointF

class AdvancedSelectionOverlay(QWidget):
    selection_finished = pyqtSignal(QRect)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)
        
        self._rect = QRectF()
        self._aspect_ratio = None
        
        self._is_dragging = False
        self._drag_start_pos = QPointF()
        self._rect_at_start = QRectF()
        
        # Handle types: 0=None, 1=TL, 2=TC, 3=TR, 4=ML, 5=MR, 6=BL, 7=BC, 8=BR
        self._active_handle = 0
        self._handle_size = 10
        self._handles = {} # type: QRectF
        
        self.hide()

    def set_aspect_ratio(self, ratio):
        self._aspect_ratio = ratio
        if ratio:
            if not self._rect.isValid() or self._rect.isEmpty():
                # Create default centered rect
                w = min(self.width(), self.height()) * 0.5
                h = w / ratio
                if h > self.height() * 0.8:
                     h = self.height() * 0.8
                     w = h * ratio
                
                cx, cy = self.width() / 2, self.height() / 2
                self._rect = QRectF(cx - w/2, cy - h/2, w, h)
            else:
                self._apply_ratio_constraint(self._rect, "TL")
        self.update()

    def start_selection(self, pos=None):
        self._rect = QRectF()
        self._active_handle = 0
        self.show()
        if pos:
            self._drag_start_pos = pos
            self._is_dragging = True
            self._active_handle = 8 # Bottom Right (as if creating)
        self.update()

    def _get_handle_rects(self):
        if not self._rect.isValid():
            return {}
        
        r = self._rect
        s = self._handle_size
        hs = s / 2
        
        return {
            1: QRectF(r.left() - hs, r.top() - hs, s, s),
            2: QRectF(r.center().x() - hs, r.top() - hs, s, s),
            3: QRectF(r.right() - hs, r.top() - hs, s, s),
            4: QRectF(r.left() - hs, r.center().y() - hs, s, s),
            5: QRectF(r.right() - hs, r.center().y() - hs, s, s),
            6: QRectF(r.left() - hs, r.bottom() - hs, s, s),
            7: QRectF(r.center().x() - hs, r.bottom() - hs, s, s),
            8: QRectF(r.right() - hs, r.bottom() - hs, s, s)
        }

    def _hit_test(self, pos):
        handles = self._get_handle_rects()
        for h_type, h_rect in handles.items():
            if h_rect.contains(pos):
                return h_type
        if self._rect.contains(pos):
            return -1 # Body
        return 0

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_test(event.position())
            if hit != 0:
                self._is_dragging = True
                self._active_handle = hit
                self._drag_start_pos = event.position()
                self._rect_at_start = QRectF(self._rect)
            else:
                # Clicked outside - start new selection
                self._rect = QRectF(event.position(), QSizeF(0, 0))
                self._is_dragging = True
                self._active_handle = 8 # Bottom Right
                self._drag_start_pos = event.position()
                self._rect_at_start = QRectF(self._rect)
            self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        
        if not self._is_dragging:
            # Update cursor based on hit test
            hit = self._hit_test(pos)
            if hit == 1 or hit == 8: self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif hit == 3 or hit == 6: self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif hit == 2 or hit == 7: self.setCursor(Qt.CursorShape.SizeVerCursor)
            elif hit == 4 or hit == 5: self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif hit == -1: self.setCursor(Qt.CursorShape.SizeAllCursor)
            else: self.setCursor(Qt.CursorShape.CrossCursor)
            return

        delta = pos - self._drag_start_pos
        new_rect = QRectF(self._rect_at_start)
        
        if self._active_handle == -1: # Move
            new_rect.translate(delta.x(), delta.y())
            # Constrain to parent
            if new_rect.left() < 0: new_rect.moveLeft(0)
            if new_rect.top() < 0: new_rect.moveTop(0)
            if new_rect.right() > self.width(): new_rect.moveRight(self.width())
            if new_rect.bottom() > self.height(): new_rect.moveBottom(self.height())
        else:
            # Resize
            h = self._active_handle
            left, top, right, bottom = new_rect.left(), new_rect.top(), new_rect.right(), new_rect.bottom()
            
            if h in [1, 4, 6]: left += delta.x()
            if h in [3, 5, 8]: right += delta.x()
            if h in [1, 2, 3]: top += delta.y()
            if h in [6, 7, 8]: bottom += delta.y()
            
            # Normalize and apply ratio
            rect = QRectF(left, top, right - left, bottom - top).normalized()
            
            if self._aspect_ratio:
                anchor = ""
                if h == 1: anchor = "BR"
                elif h == 2: anchor = "B"
                elif h == 3: anchor = "BL"
                elif h == 4: anchor = "R"
                elif h == 5: anchor = "L"
                elif h == 6: anchor = "TR"
                elif h == 7: anchor = "T"
                elif h == 8: anchor = "TL"
                self._apply_ratio_constraint(rect, anchor)
            
            new_rect = rect

        self._rect = new_rect
        self.update()

    def _apply_ratio_constraint(self, rect, anchor):
        ratio = self._aspect_ratio
        if not ratio: return
        
        w, h = rect.width(), rect.height()
        if h == 0:
            if w == 0: return
            h = w / ratio
        elif w / h > ratio:
            # Too wide
            w = h * ratio
        else:
            # Too tall
            h = w / ratio
            
        # Reposition based on anchor
        left, top = rect.left(), rect.top()
        if "R" in anchor: left = rect.right() - w
        if "B" in anchor: top = rect.bottom() - h
        if anchor == "T" or anchor == "B": left = rect.center().x() - w/2
        if anchor == "L" or anchor == "R": top = rect.center().y() - h/2
        
        rect.setRect(left, top, w, h)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background dimming
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))

        if self._rect.isValid():
            path.addRect(self._rect)
                
        painter.fillPath(path, QColor(0, 0, 0, 150))

        # Selection border
        if self._rect.isValid():
            painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
            painter.drawRect(self._rect)
            
            # Draw handles
            painter.setBrush(QColor(255, 255, 255, 200))
            painter.setPen(QPen(QColor(0, 0, 0, 100), 1))
            for h_rect in self._get_handle_rects().values():
                painter.drawEllipse(h_rect)

    def get_selection(self):
        return self._rect.toRect()
