from PyQt6.QtCore import QRunnable, QObject, pyqtSignal


class _Signals(QObject):
    finished = pyqtSignal(object, str)  # (PIL.Image or None, error_str)


class StickerWorker(QRunnable):
    def __init__(self, pil_image, border: int = 8):
        super().__init__()
        self.pil_image = pil_image
        self.border = border
        self.signals = _Signals()

    def run(self):
        try:
            from src.core.sticker_server_manager import StickerServerManager
            result = StickerServerManager.instance().make_sticker(self.pil_image, border=self.border)
            if result is None:
                self.signals.finished.emit(None, "Sticker server failed. Is rembg installed?")
            else:
                self.signals.finished.emit(result, "")
        except Exception as e:
            self.signals.finished.emit(None, str(e))
