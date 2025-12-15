from PyQt6.QtWidgets import QSlider, QStyleOptionSlider, QStyle
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QBrush

class AltSlider(QSlider):
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.alt_indices = set()
        self.setMouseTracking(True)
        self.hovered_index = -1
        
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

    def mouseMoveEvent(self, event):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self)
        handle_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)
        handle_width = handle_rect.width()
        
        min_val = self.minimum()
        max_val = self.maximum()
        
        hovered = -1
        for idx in self.alt_indices:
            if not (min_val <= idx <= max_val):
                continue
            
            rect = self.get_marker_rect(idx, groove_rect, handle_width)
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

        super().mousePressEvent(event)

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
