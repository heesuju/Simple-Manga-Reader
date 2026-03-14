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

        # Size Limit Controls
        size_container = QWidget()
        size_layout = QHBoxLayout(size_container)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.setSpacing(5)
        
        size_label = QLabel("Limit:")
        size_label.setStyleSheet("color: #888; font-size: 11px; margin-left: 10px;")
        size_layout.addWidget(size_label)
        
        self.size_limits = [
            ("Original", None),
            ("2MB", 2),
            ("4MB", 4),
            ("6MB", 6),
            ("8MB", 8),
            ("10MB", 10)
        ]
        
        self.size_group = []
        self._current_size_limit = None
        
        for label, val in self.size_limits:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedWidth(55 if label == "Original" else 42)
            btn.setStyleSheet(FLAT_BUTTON_STYLE + """
                QPushButton { padding: 3px 5px; font-size: 11px; color: #999; border: 1px solid rgba(255,255,255,10); }
                QPushButton:checked { background-color: rgba(0, 120, 215, 60); color: white; border: 1px solid #0078d7; }
                QPushButton:hover:!checked { background-color: rgba(255, 255, 255, 20); }
            """)
            btn.clicked.connect(lambda checked, v=val, b=btn: self._on_size_clicked(v, b))
            size_layout.addWidget(btn)
            self.size_group.append(btn)
        
        # Default to Original
        self.size_group[0].setChecked(True)
        main_layout.addWidget(size_container)

        # Action Buttons
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(FLAT_BUTTON_STYLE + "QPushButton { color: #ff5555; padding: 4px 12px; font-weight: bold; margin-left: 10px; }")
        self.cancel_btn.clicked.connect(self.cancel_clicked)
        main_layout.addWidget(self.cancel_btn)

        self.apply_btn = QPushButton("Save Selection")
        self.apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d7;
                border: none;
                color: white;
                padding: 8px 20px;
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

    def _on_size_clicked(self, value, button):
        for btn in self.size_group:
            if btn != button:
                btn.setChecked(False)
        button.setChecked(True)
        self._current_size_limit = value

    def get_size_limit(self):
        """Returns the selected size limit in MB, or None if 'Original'."""
        return self._current_size_limit

    def reset(self):
        # Reset ratios
        for btn in self.ratio_buttons:
            btn.setChecked(False)
        self.ratio_buttons[0].setChecked(True)
        self.ratio_selected.emit(None)
        
        # Reset size limit
        for btn in self.size_group:
            btn.setChecked(False)
        self.size_group[0].setChecked(True)
        self._current_size_limit = None
