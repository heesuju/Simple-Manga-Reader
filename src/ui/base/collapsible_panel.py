from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QScrollArea, QFrame, QPushButton, QCheckBox
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QPixmap
from src.utils.img_utils import load_thumbnail_from_path, load_thumbnail_from_zip, load_thumbnail_from_virtual_path

class HorizontalScrollArea(QScrollArea):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.animation = QPropertyAnimation(self.horizontalScrollBar(), b"value")
        self.animation.setDuration(50)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def snapToItem(self, index:int, width:int=110):
        current_value = self.horizontalScrollBar().value()
        target_value = (width * index // width) * width
        self.animation.setStartValue(current_value)
        self.animation.setEndValue(target_value)
        self.animation.start()

    def snapToItemIfOutOfView(self, index: int, width: int = 110):
        target_item_start_x = index * width
        target_item_end_x = (index + 1) * width

        viewport_start_x = self.horizontalScrollBar().value()
        viewport_end_x = viewport_start_x + self.viewport().width()

        # Check if the item is entirely outside the current view
        if target_item_end_x < viewport_start_x or target_item_start_x > viewport_end_x:
            self.snapToItem(index, width)
        # Check if the item is partially visible but its start is out of view (scrolling right)
        elif target_item_start_x < viewport_start_x:
            self.snapToItem(index, width)
        # Check if the item is partially visible but its end is out of view (scrolling left)
        elif target_item_end_x > viewport_end_x:
            self.snapToItem(index, width)
            
    def wheelEvent(self, event):
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
        self.thumbnails_layout = QHBoxLayout(self.thumbnails_widget)
        self.thumbnails_layout.setSpacing(10)
        self.thumbnails_layout.setContentsMargins(0,0,0,0)
        self.thumbnails_layout.addStretch()
        self.content_area.setWidget(self.thumbnails_widget)

        self.raise_()

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