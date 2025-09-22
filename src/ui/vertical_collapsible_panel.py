from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFrame
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint
from PyQt6.QtGui import QMouseEvent

class VerticalCollapsiblePanel(QWidget):
    scrolled = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.is_content_visible = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.handle = QFrame(self)
        self.handle.setStyleSheet("background-color: rgba(50, 150, 255, 0.5); border: 0px solid rgba(255, 255, 255, 0.9); border-radius: 0px;")
        self.handle.setMouseTracking(True)
        self.handle.raise_()
    
        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(200)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_content)

        self._is_dragging = False
        self._drag_start_pos = QPoint()
        self._drag_start_handle_pos = 0

        self._scroll_range = (0, 0)
        self._page_step = 0
        self._value = 0

    def set_scroll_properties(self, value, page_step, scroll_range):
        self._value = value
        self._page_step = page_step
        self._scroll_range = scroll_range
        self.update_handle()

    def update_handle(self):
        if self._scroll_range[1] <= 0 or self._page_step >= self._scroll_range[1] + self._page_step:
            self.handle.hide()
            return

        self.handle.show()
        total_height = self.height()
        
        handle_height_ratio = self._page_step / (self._scroll_range[1] + self._page_step)
        handle_height = max(20, total_height * handle_height_ratio)
        
        scroll_pos_ratio = self._value / self._scroll_range[1] if self._scroll_range[1] > 0 else 0
        handle_y = scroll_pos_ratio * (total_height - handle_height)

        self.handle.setGeometry(0, int(handle_y), self.width(), int(handle_height))

    def mousePressEvent(self, event: QMouseEvent):
        if self.handle.geometry().contains(event.pos()):
            self._is_dragging = True
            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_start_handle_pos = self.handle.y()
            event.accept()
        else:
            # Click on track to jump
            total_height = self.height()
            handle_height = self.handle.height()
            
            if total_height <= handle_height:
                return

            target_y = event.pos().y() - handle_height / 2
            pos_ratio = target_y / (total_height - handle_height)

            new_value = int(pos_ratio * self._scroll_range[1])
            new_value = max(self._scroll_range[0], min(new_value, self._scroll_range[1]))

            self.scrolled.emit(new_value)
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_dragging:
            delta_y = event.globalPosition().toPoint().y() - self._drag_start_pos.y()
            new_handle_y = self._drag_start_handle_pos + delta_y

            total_height = self.height()
            handle_height = self.handle.height()
            scrollable_handle_area = total_height - handle_height
            
            if scrollable_handle_area <= 0: return

            pos_ratio = new_handle_y / scrollable_handle_area
            new_value = pos_ratio * self._scroll_range[1]
            
            new_value = max(self._scroll_range[0], min(new_value, self._scroll_range[1]))

            self.scrolled.emit(int(new_value))
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._is_dragging:
            self._is_dragging = False
            event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_handle()

    def show_content(self):
        self.hide_timer.stop()
        self.is_content_visible = True
        self.setVisible(True)

    def hide_content(self):
        if not self._is_dragging:
            self.is_content_visible = False
            self.setVisible(False)

    def enterEvent(self, event):
        self.hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hide_timer.start()
        super().leaveEvent(event)

    def raise_handle(self):
        self.handle.raise_()
