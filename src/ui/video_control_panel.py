from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QSlider, QLabel
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, pyqtSignal

from src.ui.components.volume_control import VolumeControl
from src.utils.resource_utils import resource_path



class VideoControlPanel(QWidget):
    play_pause_clicked = pyqtSignal()
    repeat_clicked = pyqtSignal(bool)
    auto_play_toggled = pyqtSignal(bool) # NEW signal
    speed_clicked = pyqtSignal()
    volume_changed = pyqtSignal(int)
    position_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._is_scrubbing = False
        self.init_ui()
        self.is_playing = False
        self.is_repeat = True
        self.is_auto_play = False # NEW state

    def init_ui(self):
        self.play_icon = QIcon(resource_path("assets/icons/play.png"))
        self.pause_icon = QIcon(resource_path("assets/icons/pause.png"))
        self.repeat_on_icon = QIcon(resource_path("assets/icons/repeat_on.png"))
        self.repeat_off_icon = QIcon(resource_path("assets/icons/repeat_off.png"))
        # Reuse repeat icon or use text for now since we might not have a dedicated icon
        self.auto_play_icon = QIcon(resource_path("assets/icons/auto_play.png")) # Assuming exists or use fallback
        
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)

        self.play_pause_btn = QPushButton(self.play_icon, "")
        self.play_pause_btn.clicked.connect(self.play_pause_clicked.emit)
        self.play_pause_btn.setFlat(True)
        layout.addWidget(self.play_pause_btn)
        
        self.current_time_label = QLabel("00:00")
        layout.addWidget(self.current_time_label)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.position_slider.sliderMoved.connect(self._on_slider_moved)
        layout.addWidget(self.position_slider)

        self.duration_label = QLabel("00:00")
        layout.addWidget(self.duration_label)

        self.volume_control = VolumeControl(self)
        self.volume_control.volume_changed.connect(self.volume_changed.emit)
        layout.addWidget(self.volume_control)

        self.speed_btn = QPushButton("1.0x")
        self.speed_btn.setFlat(True)
        self.speed_btn.clicked.connect(self.speed_clicked.emit)
        layout.addWidget(self.speed_btn)
        
        self.repeat_btn = QPushButton(self.repeat_on_icon, "")
        self.repeat_btn.setCheckable(True)
        self.repeat_btn.setChecked(True)
        self.repeat_btn.clicked.connect(self.toggle_repeat)
        self.repeat_btn.setFlat(True)
        self.repeat_btn.setToolTip("Repeat Video")
        layout.addWidget(self.repeat_btn)

        # Auto Play Button
        self.auto_play_btn = QPushButton("Auto")
        self.auto_play_btn.setCheckable(True)
        self.auto_play_btn.clicked.connect(self.toggle_auto_play)
        self.auto_play_btn.setFlat(True)
        self.auto_play_btn.setToolTip("Auto Play Next Video")
        self.auto_play_btn.setStyleSheet("font-weight: bold; color: #888;") # Dimmed when off
        layout.addWidget(self.auto_play_btn)

        self.setLayout(layout)

        self.setStyleSheet("""
            VideoControlPanel {
                background-color: rgba(0, 0, 0, 100);
                color: white;
                border-radius: 10px;
            }
            QPushButton {
                color: white;
                background-color: transparent;
                border: none;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 50);
            }
            QSlider {
                background: transparent;
            }
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: transparent;
                margin: 2px 0;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #fff;
                border: 1px solid #ccc;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background: #fff;
                border: none;
                height: 4px;
                border-radius: 2px;
            }
            QSlider::add-page:horizontal {
                background: rgba(255, 255, 255, 50);
                border: none;
                height: 4px;
                border-radius: 2px;
            }
            QLabel {
                color: white;
            }
        """)

    def _on_slider_pressed(self):
        self._is_scrubbing = True

    def _on_slider_released(self):
        self._is_scrubbing = False
        self.position_changed.emit(self.position_slider.value())

    def _on_slider_moved(self, position):
        self.position_changed.emit(position)

    def set_playing(self, playing):
        self.is_playing = playing
        self.play_pause_btn.setIcon(self.pause_icon if playing else self.play_icon)

    def set_duration(self, duration_ms):
        total_seconds = duration_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        self.duration_label.setText(f"{minutes:02d}:{seconds:02d}")
        self.position_slider.setRange(0, duration_ms)

    def set_position(self, position_ms):
        if not self._is_scrubbing:
            total_seconds = position_ms // 1000
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            self.current_time_label.setText(f"{minutes:02d}:{seconds:02d}")
            self.position_slider.setValue(position_ms)

    def toggle_repeat(self, checked):
        self.is_repeat = checked
        self.repeat_btn.setIcon(self.repeat_on_icon if checked else self.repeat_off_icon)
        self.repeat_clicked.emit(checked)
    
    def toggle_auto_play(self, checked):
        self.is_auto_play = checked
        # Visual feedback
        if checked:
            self.auto_play_btn.setStyleSheet("font-weight: bold; color: #4CAF50;") # Green when on
        else:
            self.auto_play_btn.setStyleSheet("font-weight: bold; color: #888;") # Dimmed when off
        self.auto_play_toggled.emit(checked)
        
    def set_speed_text(self, text):
        self.speed_btn.setText(text)

