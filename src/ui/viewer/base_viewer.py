from abc import ABC, abstractmethod
from PyQt6.QtCore import QObject

class BaseViewer(QObject):
    def __init__(self, reader_view):
        super().__init__()
        self.reader_view = reader_view

    @abstractmethod
    def set_active(self, active: bool):
        pass

    @abstractmethod
    def load(self, item):
        pass

    @abstractmethod
    def zoom(self, mode: str):
        pass

    def cleanup(self):
        pass

    def on_resize(self, event):
        pass
        
    def show_next(self):
        pass
        
    def show_prev(self):
        pass
