
from PyQt6.QtWidgets import QPushButton, QSizePolicy
from PyQt6.QtCore import pyqtSignal

class FilterToken(QPushButton):
    remove_requested = pyqtSignal(str, str)

    def __init__(self, token_type, token_value, parent=None):
        super().__init__(f"{token_value} ✕", parent)
        self.token_type = token_type
        self.token_value = token_value
        self.setStyleSheet("""
        QPushButton { 
            background-color: #8AB4F7; 
            color: black;
            border-radius: 5px; 
            padding: 2px 5px; 
        } 
        QToolTip { 
            color: #ffffff; 
            background-color: #2a82da; 
            border: 1px solid black; 
        }""")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.clicked.connect(self.emit_remove_request)

    def emit_remove_request(self):
        self.remove_requested.emit(self.token_type, self.token_value)
  