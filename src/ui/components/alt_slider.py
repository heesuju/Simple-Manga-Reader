from PyQt6.QtWidgets import QSlider, QStyleOptionSlider, QStyle
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QBrush

class AltSlider(QSlider):
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.alt_indices = set()
        
    def set_alt_indices(self, indices):
        self.alt_indices = set(indices)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        
        if not self.alt_indices:
            return

        painter = QPainter(self)
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        
        # Calculate geometry
        groove_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self)
        handle_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)
        
        # Dimensions
        available_width = groove_rect.width()
        handle_width = handle_rect.width()
        
        # The handle moves within the available width minus its own width
        track_length = available_width - handle_width
        
        if track_length <= 0:
            return

        # Assuming horizontal slider for now as per app usage
        min_val = self.minimum()
        max_val = self.maximum()
        
        marker_color = QColor("#03A9F4")  # Light Blue
        painter.setBrush(QBrush(marker_color))
        painter.setPen(Qt.PenStyle.NoPen)
        
        for idx in self.alt_indices:
            if not (min_val <= idx <= max_val):
                continue
                
            # Use QStyle to calculate exact handle position for the value
            # Note: We pass track_length as the span
            pos = self.style().sliderPositionFromValue(min_val, max_val, idx, track_length, opt.upsideDown)
            
            # Position is relative to the start of the groove
            # 'pos' gives the left edge of the handle
            x_pos = groove_rect.left() + pos + (handle_width / 2)
            
            # Adjust y to be just above the groove
            marker_w = 4
            marker_h = 4
            
            y_pos = groove_rect.top() - marker_h - 2
            
            draw_rect = QRect(int(x_pos - marker_w/2), int(y_pos), marker_w, marker_h)
            painter.drawRect(draw_rect)
