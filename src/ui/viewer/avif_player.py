import io
from PIL import Image, ImageQt
from PyQt6.QtGui import QPixmap, QMovie
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

class AvifPlayer(QObject):
    frameChanged = pyqtSignal(int)
    
    def __init__(self, data: bytes, parent=None):
        super().__init__(parent)
        self.data = data
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._next_frame)
        self._state = QMovie.MovieState.NotRunning
        self.current_frame = 0
        try:
            self.img = Image.open(io.BytesIO(data))
            self.n_frames = getattr(self.img, "n_frames", 1)
        except Exception:
            self.img = None
            self.n_frames = 1
            
    def isValid(self):
        return self.img is not None and getattr(self.img, "is_animated", False) and self.n_frames > 1
        
    def start(self):
        if not self.isValid(): return
        self._state = QMovie.MovieState.Running
        self.img.seek(0)
        self.current_frame = 0
        dur = self.img.info.get('duration', 100)
        self.timer.start(dur if dur > 0 else 100)
        
    def stop(self):
        self._state = QMovie.MovieState.NotRunning
        self.timer.stop()
        self.current_frame = 0
        
    def setPaused(self, paused: bool):
        if paused:
            self.timer.stop()
            self._state = QMovie.MovieState.NotRunning
        else:
            self.start()
            
    def state(self):
        return self._state
            
    def _next_frame(self):
        if not self.isValid(): return
        self.current_frame = (self.current_frame + 1) % self.n_frames
        try:
            self.img.seek(self.current_frame)
            dur = self.img.info.get('duration', 100)
            self.timer.start(dur if dur > 0 else 100)
            self.frameChanged.emit(self.current_frame)
        except Exception:
            self.stop()
            
    def currentPixmap(self) -> QPixmap:
        if not self.img: return QPixmap()
        try:
            qimg = ImageQt.ImageQt(self.img.convert('RGBA')).copy()
            return QPixmap.fromImage(qimg)
        except Exception:
            return QPixmap()
