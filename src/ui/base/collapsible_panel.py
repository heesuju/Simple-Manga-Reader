from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QScrollArea, QFrame, QPushButton, QCheckBox
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QPixmap
from src.utils.img_utils import load_thumbnail_from_path, load_thumbnail_from_zip, load_thumbnail_from_virtual_path

from src.ui.components.flow_layout import FlowLayout

class HorizontalScrollArea(QScrollArea):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.animation = QPropertyAnimation(self.horizontalScrollBar(), b"value")
        self.animation.setDuration(50)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.vertical_mode = False


    def scrollToWidget(self, widget: QWidget):
        # Ensure widget layout geometry is up to date
        if not widget.isVisible():
            return

        target_pos = widget.pos()
        target_size = widget.size()
        
        if self.vertical_mode:
            scrollbar = self.verticalScrollBar()
            viewport_size = self.viewport().height()
            item_start = target_pos.y()
            item_size = target_size.height()
        else:
            scrollbar = self.horizontalScrollBar()
            viewport_size = self.viewport().width()
            item_start = target_pos.x()
            item_size = target_size.width()

        current_val = scrollbar.value()
        
        # Calculate target value to Ensure Visible (Snap to nearest edge)
        # If item is above/left of view, snap to start: target = item_start
        # If item is below/right of view, snap to end: target = item_end - viewport_size
        
        # item_end = item_start + item_size
        # We want: 
        # 1. item_start >= target_val
        # 2. item_start + item_size <= target_val + viewport_size  => item_start + item_size - viewport_size <= target_val
        
        # So target_val must be roughly between [item_start + item_size - viewport_size, item_start]
        # But we want minimal movement.
        
        min_needed = item_start  # If we are at this val, item is at top/left
        max_needed = item_start + item_size - viewport_size # If we are at this val, item is at bottom/right
        
        # If item is larger than viewport, prioritize start?
        if item_size > viewport_size:
             target_val = item_start
        else:
            if current_val > min_needed:
                # Viewport is too far down/right (current > item_start)
                # We need to scroll up/left
                target_val = min_needed
            elif current_val < max_needed:
                # Viewport is too far up/left (current + viewport < item_end)
                # We need to scroll down/right
                target_val = max_needed
            else:
                # Already visible (between min_needed and max_needed)
                return

        # Clamp
        target_val = max(0, min(target_val, scrollbar.maximum()))
        
        if self.vertical_mode:
            self.animation.setPropertyName(b"value")
            self.animation.setTargetObject(self.verticalScrollBar())
        else:
            self.animation.setPropertyName(b"value")
            self.animation.setTargetObject(self.horizontalScrollBar())

        self.animation.stop()
        self.animation.setStartValue(current_val)
        self.animation.setEndValue(int(target_val))
        self.animation.start()
        

    def wheelEvent(self, event):
        if self.vertical_mode:
            super().wheelEvent(event)
            return

        if self.animation.state() == QPropertyAnimation.State.Running:

            return

        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return

        item_width = 110  # Thumbnail width (100) + spacing (10)
        current_value = self.horizontalScrollBar().value()
        
        if delta < 0:
            target_value = (current_value // item_width + 1) * item_width
        else:
            target_value = (current_value // item_width) * item_width
            if target_value == current_value:
                target_value -= item_width

        self.animation.setStartValue(current_value)
        self.animation.setEndValue(target_value)
        self.animation.start()
        event.accept()

class CollapsiblePanel(QWidget):
    play_button_clicked = pyqtSignal()
    continuous_play_changed = pyqtSignal(bool)
    navigate_first = pyqtSignal()
    navigate_prev = pyqtSignal()
    navigate_next = pyqtSignal()
    navigate_last = pyqtSignal()
    expand_toggled = pyqtSignal(bool)

    def __init__(self, parent=None, name:str=""):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("CollapsiblePanel { background-color: rgba(0, 0, 0, 170); }")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        self.input_container = QWidget()
        self.input_layout = QHBoxLayout(self.input_container)
        self.input_layout.setContentsMargins(0,0,0,0)
        self.layout.addWidget(self.input_container)

        # Navigation Buttons (First, Prev, Next, Last)
        self.nav_buttons_layout = QHBoxLayout()
        self.nav_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_buttons_layout.setSpacing(5)
        btn_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 30);
                color: white;
                border: none;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 60);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 90);
            }
        """

        # Center: Collapse Button
        self.nav_buttons_layout.addStretch(1)
        
        self.btn_collapse = QPushButton("v")
        self.btn_collapse.setFixedSize(40, 20)
        self.btn_collapse.setStyleSheet(btn_style)
        self.btn_collapse.clicked.connect(self.hide_content)
        self.nav_buttons_layout.addWidget(self.btn_collapse)

        self.btn_expand = QPushButton("[]")
        self.btn_expand.setFixedSize(40, 20)
        self.btn_expand.setStyleSheet(btn_style)
        self.btn_expand.clicked.connect(self.toggle_expand)
        self.nav_buttons_layout.addWidget(self.btn_expand)
        
        self.nav_buttons_layout.addStretch(1)

        # Right: Navigation Buttons
        self.btn_first = QPushButton("<<")
        self.btn_prev = QPushButton("<")
        self.btn_next = QPushButton(">")
        self.btn_last = QPushButton(">>")


        for btn in [self.btn_first, self.btn_prev, self.btn_next, self.btn_last]:
            btn.setFixedSize(40, 20)
            btn.setStyleSheet(btn_style)
            self.nav_buttons_layout.addWidget(btn)

        self.btn_first.clicked.connect(self.navigate_first.emit)
        self.btn_prev.clicked.connect(self.navigate_prev.emit)
        self.btn_next.clicked.connect(self.navigate_next.emit)
        self.btn_last.clicked.connect(self.navigate_last.emit)
        
        self.layout.addLayout(self.nav_buttons_layout)

        self.content_area = HorizontalScrollArea()
        self.content_area.setStyleSheet("background: transparent;")
        self.content_area.setFrameShape(QFrame.Shape.NoFrame)
        self.content_area.setVisible(False)

        self.layout.addWidget(self.content_area, 1)

        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(200)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_content)
        
        self.thumbnails_widget = QWidget()
        self.thumbnails_widget.setStyleSheet("background: transparent;")
        
        # Use FlowLayout for both modes
        self.thumbnails_layout = FlowLayout(self.thumbnails_widget, margin=0, spacing=10)
        self.thumbnails_layout.setSingleRow(True) # Start in single row (horizontal) mode
        
        self.content_area.setWidget(self.thumbnails_widget)

        self.is_expanded = False
        self.raise_()

    def toggle_expand(self):
        self.is_expanded = not self.is_expanded
        self.btn_expand.setText("=" if self.is_expanded else "[]")
        self.expand_toggled.emit(self.is_expanded)
        self._update_layout_mode()

    def _update_layout_mode(self):
        # Refactored: No more widget moving or layout replacement!
        # Just toggle the mode on the FlowLayout.
        
        if self.is_expanded:
            self.thumbnails_layout.setSingleRow(False) # Wrap allowed (Grid)
            self.thumbnails_layout.setSpacing(5)       # tighter spacing
            
            self.content_area.vertical_mode = True
            self.content_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.content_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            self.thumbnails_layout.setSingleRow(True)  # No wrap (Horizontal Strip)
            self.thumbnails_layout.setSpacing(10)
            
            self.content_area.vertical_mode = False
            self.content_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.content_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            
        # Trigger update?
        self.thumbnails_layout.invalidate()
        self.thumbnails_widget.adjustSize() # Ensure widget resizes to fit new layout hint
        
    def show_content(self):
        self.content_area.setVisible(True)
        self.setVisible(True)
        # Update button capability if needed, or just let them be

    def hide_content(self):
        self.content_area.setVisible(False)
        self.setVisible(False)

    def _load_thumbnail(self, path: str) -> QPixmap | None:
        crop = None
        if path.endswith("_left"):
            path = path[:-5]
            crop = "left"
        elif path.endswith("_right"):
            path = path[:-6]
            crop = "right"

        if '|' in path:
            return load_thumbnail_from_virtual_path(virtual_path=path, crop=crop)
        elif path.endswith('.zip'):
            return load_thumbnail_from_zip(path=path)
        else:
            return load_thumbnail_from_path(path=path, crop=crop)