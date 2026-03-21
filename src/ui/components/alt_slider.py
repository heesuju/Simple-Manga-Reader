from PyQt6.QtWidgets import QSlider, QStyleOptionSlider, QStyle
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QBrush

class AltSlider(QSlider):
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.alt_indices = set()
        self.setMouseTracking(True)
        self.hovered_index = -1
        self._dragging = False
        
    def set_alt_indices(self, indices):
        self.alt_indices = set(indices)
        self.update()

    def get_marker_rect(self, idx, groove_rect, handle_width):
        # Calculate position logic reused from paintEvent
        available_width = groove_rect.width()
        track_length = available_width - handle_width
        
        if track_length <= 0:
            return QRect()
            
        min_val = self.minimum()
        max_val = self.maximum()
        
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        
        pos = self.style().sliderPositionFromValue(min_val, max_val, idx, track_length, opt.upsideDown)
        
        x_pos = groove_rect.left() + pos + (handle_width / 2)
        marker_w = 4
        marker_h = 4
        
        # Original drawing position
        y_pos = groove_rect.top() - marker_h - 2
        
        # Return a slightly larger rect for hit testing
        # Center the hit rect on the drawn marker
        hit_size = 12
        return QRect(int(x_pos - hit_size/2), int(y_pos - hit_size/2), hit_size, hit_size)

    def _value_from_pos(self, x: float) -> int:
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self)
        handle_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)
        track_length = groove_rect.width() - handle_rect.width()
        if track_length <= 0:
            return self.value()
        click_x = x - groove_rect.left() - handle_rect.width() / 2
        click_x = max(0.0, min(click_x, float(track_length)))
        return self.style().sliderValueFromPosition(
            self.minimum(), self.maximum(), int(click_x), track_length, opt.upsideDown
        )

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.setValue(self._value_from_pos(event.position().x()))
            event.accept()
            return

        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self)
        handle_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)

        hovered = -1
        for idx in self.alt_indices:
            if not (self.minimum() <= idx <= self.maximum()):
                continue
            rect = self.get_marker_rect(idx, groove_rect, handle_rect.width())
            if rect.contains(event.position().toPoint()):
                hovered = idx
                break

        if hovered != self.hovered_index:
            self.hovered_index = hovered
            self.update()

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self.hovered_index != -1:
            self.hovered_index = -1
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self.hovered_index != -1:
            self.setValue(self.hovered_index)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.setValue(self._value_from_pos(event.position().x()))
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        
        if not self.alt_indices:
            return

        painter = QPainter(self)
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        
        groove_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self)
        handle_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)
        
        available_width = groove_rect.width()
        handle_width = handle_rect.width()
        track_length = available_width - handle_width
        
        if track_length <= 0:
            return

        min_val = self.minimum()
        max_val = self.maximum()
        
        default_color = QColor("#03A9F4")  # Light Blue
        hover_color = QColor("#FFEB3B") # Yellow for hover
        
        painter.setPen(Qt.PenStyle.NoPen)
        
        for idx in self.alt_indices:
            if not (min_val <= idx <= max_val):
                continue
                
            pos = self.style().sliderPositionFromValue(min_val, max_val, idx, track_length, opt.upsideDown)
            x_pos = groove_rect.left() + pos + (handle_width / 2)
            
            is_hovered = (idx == self.hovered_index)
            
            # Draw highlight if hovered
            if is_hovered:
                marker_w = 6
                marker_h = 6
                painter.setBrush(QBrush(hover_color))
            else:
                marker_w = 4
                marker_h = 4
                painter.setBrush(QBrush(default_color))

            y_pos = groove_rect.top() - marker_h - 2
            
            draw_rect = QRect(int(x_pos - marker_w/2), int(y_pos), marker_w, marker_h)
            painter.drawRect(draw_rect)
