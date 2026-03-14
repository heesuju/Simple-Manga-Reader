from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QSlider, QLabel
from src.ui.components.volume_control import VolumeControl
from src.utils.resource_utils import resource_path
from src.ui.styles import FLAT_BUTTON_STYLE
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QSize



class VideoControlPanel(QWidget):
    play_pause_clicked = pyqtSignal()
    repeat_clicked = pyqtSignal(bool)
    auto_play_toggled = pyqtSignal(bool) # NEW signal
    speed_clicked = pyqtSignal()
    volume_changed = pyqtSignal(int)
    position_changed = pyqtSignal(int)
    mode_changed = pyqtSignal(str) # "time" or "frame"
    seek_frame = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._is_scrubbing = False
        self.init_ui()
        self.is_playing = False
        self.is_repeat = True
        self.is_auto_play = False
        self.seek_mode = "time" # "time" or "frame"
        self.total_frames = 0
        self.fps = 0.0

    def init_ui(self):
        self.play_icon = QIcon(resource_path("assets/icons/play.svg"))
        self.pause_icon = QIcon(resource_path("assets/icons/pause.svg"))
        self.repeat_on_icon = QIcon(resource_path("assets/icons/repeat_on.svg"))
        self.repeat_off_icon = QIcon(resource_path("assets/icons/repeat_off.svg"))
        # Reuse repeat icon or use text for now since we might not have a dedicated icon
        self.auto_play_icon = QIcon(resource_path("assets/icons/slideshow.svg")) # Assuming exists or use fallback
        
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)

        self.play_pause_btn = QPushButton(self.play_icon, "")
        self.play_pause_btn.setIconSize(QSize(24, 24))
        self.play_pause_btn.setFixedSize(32, 32)
        self.play_pause_btn.setStyleSheet(FLAT_BUTTON_STYLE)
        self.play_pause_btn.clicked.connect(self.play_pause_clicked.emit)
        layout.addWidget(self.play_pause_btn)
        
        self.current_time_label = QLabel("00:00")
        layout.addWidget(self.current_time_label)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.position_slider.sliderMoved.connect(self._on_slider_moved)
        layout.addWidget(self.position_slider)

        self.mode_toggle_btn = QPushButton("Time")
        self.mode_toggle_btn.setFixedSize(50, 32)
        self.mode_toggle_btn.setStyleSheet(FLAT_BUTTON_STYLE + " QPushButton { font-weight: bold; color: #aaa; }")
        self.mode_toggle_btn.setToolTip("Toggle Time/Frame Seek")
        self.mode_toggle_btn.clicked.connect(self.toggle_seek_mode)
        layout.addWidget(self.mode_toggle_btn)

        self.duration_label = QLabel("00:00")
        layout.addWidget(self.duration_label)

        self.volume_control = VolumeControl(self)
        self.volume_control.volume_changed.connect(self.volume_changed.emit)
        layout.addWidget(self.volume_control)

        self.speed_btn = QPushButton("1.0x")
        self.speed_btn.setFixedSize(48, 32)
        self.speed_btn.setStyleSheet(FLAT_BUTTON_STYLE + " QPushButton { font-weight: bold; }")
        self.speed_btn.clicked.connect(self.speed_clicked.emit)
        layout.addWidget(self.speed_btn)
        
        self.repeat_btn = QPushButton(self.repeat_on_icon, "")
        self.repeat_btn.setCheckable(True)
        self.repeat_btn.setChecked(True)
        self.repeat_btn.setIconSize(QSize(24, 24))
        self.repeat_btn.setFixedSize(32, 32)
        self.repeat_btn.setStyleSheet(FLAT_BUTTON_STYLE)
        self.repeat_btn.clicked.connect(self.toggle_repeat)
        self.repeat_btn.setToolTip("Repeat Video")
        layout.addWidget(self.repeat_btn)

        # Auto Play Button
        self.auto_play_btn = QPushButton("Auto")
        self.auto_play_btn.setCheckable(True)
        self.auto_play_btn.setFixedSize(48, 32)
        self.auto_play_btn.clicked.connect(self.toggle_auto_play)
        self.auto_play_btn.setStyleSheet(FLAT_BUTTON_STYLE + " QPushButton { font-weight: bold; color: #888; }") # Dimmed when off
        self.auto_play_btn.setToolTip("Auto Play Next Video")
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
                background-color: rgba(255, 255, 255, 30);
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
        if self.seek_mode == "time":
            self.position_changed.emit(self.position_slider.value())
        else:
            self.seek_frame.emit(self.position_slider.value())

    def _on_slider_moved(self, position):
        if self.seek_mode == "time":
            total_seconds = position // 1000
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            self.current_time_label.setText(f"{minutes:02d}:{seconds:02d}")
            self.position_changed.emit(position)
        else:
            self.current_time_label.setText(f"F: {position}")
            self.seek_frame.emit(position)

    def set_playing(self, playing):
        self.is_playing = playing
        self.play_pause_btn.setIcon(self.pause_icon if playing else self.play_icon)

    def set_duration(self, duration_ms):
        self.duration_ms = duration_ms
        if self.seek_mode == "time":
            total_seconds = duration_ms // 1000
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            self.duration_label.setText(f"{minutes:02d}:{seconds:02d}")
            self.position_slider.setRange(0, duration_ms)
        else:
            self.duration_label.setText(str(self.total_frames))
            self.position_slider.setRange(0, self.total_frames)

    def set_position(self, position_ms):
        self.current_position_ms = position_ms
        if not self._is_scrubbing:
            if self.seek_mode == "time":
                total_seconds = position_ms // 1000
                minutes = total_seconds // 60
                seconds = total_seconds % 60
                self.current_time_label.setText(f"{minutes:02d}:{seconds:02d}")
                self.position_slider.setValue(position_ms)
            elif self.fps > 0:
                current_frame = int(position_ms * self.fps / 1000)
                self.current_time_label.setText(f"F: {current_frame}")
                self.position_slider.setValue(current_frame)

    def set_video_metadata(self, total_frames, fps):
        self.total_frames = total_frames
        self.fps = fps
        if self.seek_mode == "frame":
            self.update_ui_for_mode()

    def toggle_seek_mode(self):
        self.seek_mode = "frame" if self.seek_mode == "time" else "time"
        self.mode_toggle_btn.setText("Frame" if self.seek_mode == "frame" else "Time")
        self.mode_toggle_btn.setStyleSheet(
            FLAT_BUTTON_STYLE + (" QPushButton { font-weight: bold; color: #4CAF50; }" if self.seek_mode == "frame" else " QPushButton { font-weight: bold; color: #aaa; }")
        )
        self.update_ui_for_mode()
        self.mode_changed.emit(self.seek_mode)

    def update_ui_for_mode(self):
        if self.seek_mode == "time":
            self.set_duration(getattr(self, 'duration_ms', 0))
            self.set_position(getattr(self, 'current_position_ms', 0))
        else:
            self.position_slider.setRange(0, self.total_frames)
            self.duration_label.setText(str(self.total_frames))
            # Trigger refresh of current frame label
            self.set_position(getattr(self, 'current_position_ms', 0))

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

