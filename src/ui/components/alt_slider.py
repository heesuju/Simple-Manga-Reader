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
        track_length = groove_rect.width() - handle_width
        if track_length <= 0:
            return QRect()

        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        pos = self.style().sliderPositionFromValue(self.minimum(), self.maximum(), idx, track_length, opt.upsideDown)
        x_pos = groove_rect.left() + pos + (handle_width / 2)

        hit_size = 12
        return QRect(int(x_pos - hit_size / 2), groove_rect.center().y() - hit_size // 2, hit_size, hit_size)

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
        if event.button() == Qt.MouseButton.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            handle_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)
            if handle_rect.contains(event.position().toPoint()):
                self._dragging = True
                event.accept()
                return

            if self.hovered_index != -1:
                self.setValue(self.hovered_index)
                event.accept()
                return

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

        track_length = groove_rect.width() - handle_rect.width()
        if track_length <= 0:
            return

        min_val = self.minimum()
        max_val = self.maximum()

        default_color = QColor("#03A9F4")
        hover_color = QColor("#FFEB3B")

        tick_w = 2
        tick_y = groove_rect.top() - 1
        tick_h = groove_rect.height() + 2

        painter.setPen(Qt.PenStyle.NoPen)

        for idx in self.alt_indices:
            if not (min_val <= idx <= max_val):
                continue
            pos = self.style().sliderPositionFromValue(min_val, max_val, idx, track_length, opt.upsideDown)
            x_pos = groove_rect.left() + pos + (handle_rect.width() / 2)
            color = hover_color if idx == self.hovered_index else default_color
            painter.setBrush(QBrush(color))
            painter.drawRect(int(x_pos - tick_w / 2), tick_y, tick_w, tick_h)

        # Redraw handle on top of ticks
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawEllipse(handle_rect)
