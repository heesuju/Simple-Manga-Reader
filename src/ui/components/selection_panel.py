from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QFrame, QScrollArea
from PyQt6.QtCore import Qt, pyqtSignal
from src.ui.styles import FLAT_BUTTON_STYLE

class HorizontalScrollArea(QScrollArea):
    def wheelEvent(self, event):
        if event.angleDelta().y() != 0:
            # Shift scroll to horizontal
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - event.angleDelta().y()
            )
            event.accept()
        else:
            super().wheelEvent(event)

class SelectionPanel(QWidget):
    ratio_selected = pyqtSignal(object)  # float or None
    apply_clicked = pyqtSignal()
    cancel_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Removed border-top
        self.setStyleSheet("background-color: rgba(20, 20, 20, 220); color: white;")
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 8, 15, 8)
        main_layout.setSpacing(10)

        title = QLabel("Area Selection")
        title.setStyleSheet("font-weight: bold; margin-right: 10px; color: #aaa;")
        main_layout.addWidget(title)

        # Scroll Area for Aspect Ratios
        self.scroll_area = HorizontalScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        self.ratio_layout = QHBoxLayout(scroll_content)
        self.ratio_layout.setContentsMargins(0, 0, 0, 0)
        self.ratio_layout.setSpacing(8)

        # Aspect Ratios
        self.ratios = [
            ("Free", None),
            ("1:1", 1.0),
            ("4:3", 4/3),
            ("3:4", 3/4),
            ("16:9", 16/9),
            ("9:16", 9/16),
            ("2:3", 2/3),
            ("3:2", 3/2),
            ("4:5", 4/5),
            ("5:4", 5/4),
            ("9:21", 9/21),
            ("21:9", 21/9)
        ]

        self.ratio_buttons = []
        for label, value in self.ratios:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(FLAT_BUTTON_STYLE + """
                QPushButton { padding: 4px 10px; min-width: 45px; color: #ccc; border-bottom: 2px solid transparent; }
                QPushButton:checked { background-color: rgba(255, 255, 255, 50); color: white; border-bottom: 2px solid #0078d7; }
                QPushButton:hover { background-color: rgba(255, 255, 255, 30); }
            """)
            btn.clicked.connect(lambda checked, v=value, b=btn: self._on_ratio_clicked(v, b))
            self.ratio_layout.addWidget(btn)
            self.ratio_buttons.append(btn)
        
        # Add a stretch at the end of ratio_layout so buttons don't spread out too much if few
        self.ratio_layout.addStretch()

        self.scroll_area.setWidget(scroll_content)
        self.scroll_area.setMaximumHeight(45)
        # Give it a stretch factor of 1 to fill space
        main_layout.addWidget(self.scroll_area, 1)

        # Default to Free
        self.ratio_buttons[0].setChecked(True)

        # Remove the stretch that was after the scroll area

        # Action Buttons
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(FLAT_BUTTON_STYLE + "QPushButton { color: #ff5555; padding: 4px 15px; font-weight: bold; }")
        self.cancel_btn.clicked.connect(self.cancel_clicked)
        main_layout.addWidget(self.cancel_btn)

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
        main_layout.addWidget(self.apply_btn)

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
