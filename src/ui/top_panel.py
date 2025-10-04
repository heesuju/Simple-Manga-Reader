from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt

class TopPanel(QWidget):
    """A simple panel at the top of the reader view."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 170); color: white;")

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 5, 10, 5)
        self.layout.setSpacing(10)

        self.back_button = None
        self.layout_button = None
        self.series_label = QLabel("Series Title")
        self.series_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout.addWidget(self.series_label, 1) # Add stretch

    def add_back_button(self, button: QPushButton):
        self.back_button = button
        self.layout.insertWidget(0, self.back_button)

    def add_layout_button(self, button: QPushButton):
        self.layout_button = button
        self.layout.insertWidget(2, self.layout_button)

    def set_series_title(self, title: str):
        self.series_label.setText(title)
