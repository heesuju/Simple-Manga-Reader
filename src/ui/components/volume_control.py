from PyQt6.QtWidgets import QWidget, QPushButton, QSlider, QVBoxLayout, QFrame, QStyle
from PyQt6.QtGui import QIcon, QMouseEvent
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint

class VolumeControl(QWidget):
    volume_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_muted = False
        self._last_volume = 100
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._check_and_hide_slider)
        self._init_ui()

    def _init_ui(self):
        style = self.style()
        self.volume_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaVolume)
        self.volume_muted_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaVolumeMuted)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.mute_btn = QPushButton(self.volume_icon, "")
        self.mute_btn.setFlat(True)
        self.mute_btn.clicked.connect(self.toggle_mute)
        layout.addWidget(self.mute_btn)
        self.setLayout(layout)

        self.slider_popup = QFrame(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.slider_popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.slider_popup.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 180); 
                border-radius: 5px;
                padding: 5px;
            }
            QSlider::groove:vertical {
                border: 1px solid #999999;
                width: 8px;
                background: #333;
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:vertical {
                background: #ccc;
                border: 1px solid #5c5c5c;
                height: 16px;
                margin: 0 -4px;
                border-radius: 8px;
            }
            QSlider::sub-page:vertical {
                background: #5c5c5c;
                border: 1px solid #999999;
                width: 8px;
                border-radius: 4px;
            }
        """)

        slider_layout = QVBoxLayout(self.slider_popup)
        self.volume_slider = QSlider(Qt.Orientation.Vertical)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self._last_volume)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        slider_layout.addWidget(self.volume_slider)

        self.mute_btn.installEventFilter(self)
        self.volume_slider.installEventFilter(self)
        self.slider_popup.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj in (self.mute_btn, self.volume_slider, self.slider_popup):
            if event.type() == QMouseEvent.Type.Enter:
                self._hide_timer.stop()
                self._show_slider()
            elif event.type() == QMouseEvent.Type.Leave:
                self._hide_timer.start(200)
        return super().eventFilter(obj, event)

    def _show_slider(self):
        btn_pos = self.mute_btn.mapToGlobal(QPoint(0, 0))
        popup_height = self.slider_popup.sizeHint().height()
        popup_width = self.slider_popup.sizeHint().width()
        x = btn_pos.x() + (self.mute_btn.width() - popup_width) // 2
        y = btn_pos.y() - popup_height - 5
        self.slider_popup.move(x, y)
        self.slider_popup.show()

    def _check_and_hide_slider(self):
        if not self.slider_popup.underMouse() and not self.mute_btn.underMouse():
            self.slider_popup.hide()

    def toggle_mute(self):
        self._is_muted = not self._is_muted
        if self._is_muted:
            if self.volume_slider.value() > 0:
                self._last_volume = self.volume_slider.value()
            self.volume_slider.setValue(0)
        else:
            self.volume_slider.setValue(self._last_volume)

    def _on_volume_changed(self, value):
        self._is_muted = (value == 0)
        self.mute_btn.setIcon(self.volume_muted_icon if self._is_muted else self.volume_icon)
        self.volume_changed.emit(value)
        if not self._is_muted:
            self._last_volume = value
