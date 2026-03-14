from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QFrame
from PyQt6.QtCore import Qt, pyqtSignal
from src.ui.styles import FLAT_BUTTON_STYLE

class SelectionPanel(QWidget):
    ratio_selected = pyqtSignal(object)  # float or None
    apply_clicked = pyqtSignal()
    cancel_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(20, 20, 20, 220); color: white; border-top: 1px solid rgba(255, 255, 255, 30);")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 8, 15, 8)
        layout.setSpacing(10)

        title = QLabel("Area Selection")
        title.setStyleSheet("font-weight: bold; margin-right: 10px; color: #aaa;")
        layout.addWidget(title)

        # Aspect Ratios
        self.ratios = [
            ("Free", None),
            ("1:1", 1.0),
            ("4:3", 4/3),
            ("3:4", 3/4),
            ("16:9", 16/9),
            ("9:16", 9/16),
            ("2:3", 2/3),
            ("3:2", 3/2)
        ]

        self.ratio_buttons = []
        for label, value in self.ratios:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(FLAT_BUTTON_STYLE + """
                QPushButton { padding: 4px 10px; min-width: 40px; color: #ccc; border-bottom: 2px solid transparent; }
                QPushButton:checked { background-color: rgba(255, 255, 255, 50); color: white; border-bottom: 2px solid #0078d7; }
                QPushButton:hover { background-color: rgba(255, 255, 255, 30); }
            """)
            btn.clicked.connect(lambda checked, v=value, b=btn: self._on_ratio_clicked(v, b))
            layout.addWidget(btn)
            self.ratio_buttons.append(btn)

        # Default to Free
        self.ratio_buttons[0].setChecked(True)

        layout.addStretch()

        # Action Buttons
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(FLAT_BUTTON_STYLE + "QPushButton { color: #ff5555; padding: 4px 15px; font-weight: bold; }")
        self.cancel_btn.clicked.connect(self.cancel_clicked)
        layout.addWidget(self.cancel_btn)

        self.apply_btn = QPushButton("Save Selection")
        self.apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d7;
                border: none;
                color: white;
                padding: 8px 25px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #0086f0; }
            QPushButton:pressed { background-color: #006cc1; }
        """)
        self.apply_btn.clicked.connect(self.apply_clicked)
        layout.addWidget(self.apply_btn)

    def _on_ratio_clicked(self, value, button):
        # Uncheck others
        for btn in self.ratio_buttons:
            if btn != button:
                btn.setChecked(False)
        
        # Ensure it stays checked
        button.setChecked(True)
        self.ratio_selected.emit(value)

    def reset(self):
        for btn in self.ratio_buttons:
            btn.setChecked(False)
        self.ratio_buttons[0].setChecked(True)
        self.ratio_selected.emit(None)
