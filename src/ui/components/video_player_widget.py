from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton

class VideoPlayerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.media_player = QMediaPlayer()
        self.video_widget = QVideoWidget()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video_widget)
        self.setLayout(layout)

        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.errorOccurred.connect(self.handle_error)

    def set_source(self, url: QUrl):
        self.media_player.setSource(url)

    def play(self):
        self.media_player.play()

    def pause(self):
        self.media_player.pause()

    def stop(self):
        self.media_player.stop()

    def handle_error(self, error):
        print(f"Video Player Error: {error}")
        print(self.media_player.errorString())

    def is_playing(self):
        return self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def set_position(self, position):
        self.media_player.setPosition(position)

    def duration(self):
        return self.media_player.duration()

    def position(self):
        return self.media_player.position()
