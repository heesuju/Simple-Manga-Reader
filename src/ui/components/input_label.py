from PyQt6.QtWidgets import QWidget, QLineEdit, QLabel, QHBoxLayout
from PyQt6.QtCore import pyqtSignal, Qt, QEvent
from PyQt6.QtGui import QIntValidator

class InputLabel(QWidget):
    """
    A widget showing an input box for the current number and a read-only label for the total.
    Emits `enterPressed` signal when Enter is pressed in the input.
    """
    enterPressed = pyqtSignal(int)  # emits the number entered
    clicked = pyqtSignal()

    def __init__(self, title:str, current:int = 1, total:int = 0, max_digits:int = 5, parent=None):
        super().__init__(parent)
        self._total = total
        
        self.setStyleSheet("""
            QLabel#titleLabel {
                background: transparent;
                color: rgba(255, 255, 255, 120);
                font-weight: bold;
                font-size: 10px;
                letter-spacing: 1px;
            }
            QLineEdit {
                background: transparent;
                color: white;
                font-weight: bold;
                font-size: 13px;
                border: none;
                margin: 0px 2px;
            }
            QLabel#totalLabel {
                background: transparent;
                color: rgba(255, 255, 255, 120);
                font-size: 13px;
            }
        """)

        self.label = QLabel(title.upper())
        self.label.setObjectName("titleLabel")
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.input = QLineEdit(str(current))
        self.input.setFixedWidth(30)
        self.input.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.input.setValidator(QIntValidator(1, 10**max_digits))

        self.total_label = QLabel(f"/ {total}")
        self.total_label.setObjectName("totalLabel")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        from PyQt6.QtWidgets import QToolButton
        from PyQt6.QtGui import QIcon
        from PyQt6.QtCore import QSize
        from src.utils.resource_utils import resource_path

        btn_style = "QToolButton { border: none; background: transparent; padding: 0px; margin: 0px; }"

        self.prev_btn = QToolButton(self)
        self.prev_btn.setIcon(QIcon(resource_path("assets/icons/arrow_left.svg")))
        self.prev_btn.setIconSize(QSize(14, 14))
        self.prev_btn.setFixedSize(16, 16)
        self.prev_btn.setStyleSheet(btn_style)
        self.prev_btn.clicked.connect(self.step_down)

        self.next_btn = QToolButton(self)
        self.next_btn.setIcon(QIcon(resource_path("assets/icons/arrow_right.svg")))
        self.next_btn.setIconSize(QSize(14, 14))
        self.next_btn.setFixedSize(16, 16)
        self.next_btn.setStyleSheet(btn_style)
        self.next_btn.clicked.connect(self.step_up)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.label)
        layout.addSpacing(4)
        layout.addWidget(self.prev_btn)
        layout.addWidget(self.input)
        layout.addWidget(self.total_label)
        layout.addWidget(self.next_btn)

        # Connect Enter key
        self.input.returnPressed.connect(self._on_enter)
        self.input.installEventFilter(self)

    def step_down(self):
        val = self.get_value()
        if val > 1:
            self.input.setText(str(val - 1))
            self.enterPressed.emit(val - 1)

    def step_up(self):
        val = self.get_value()
        max_val = self._total if self._total > 0 else 99999
        if val < max_val:
            self.input.setText(str(val + 1))
            self.enterPressed.emit(val + 1)

    def eventFilter(self, obj, event):
        if obj is self.input and event.type() == QEvent.Type.MouseButtonPress:
            self.clicked.emit()
            return False # Let the event continue to the QLineEdit
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

    def _on_enter(self):
        try:
            value = int(self.input.text())
            self.enterPressed.emit(value)
        except ValueError:
            pass  # ignore invalid input

    def set_total(self, total:int):
        """Update the total number displayed."""
        self._total = total
        self.total_label.setText(f"/ {total}")

    def set_value(self, value:int):
        """Set the current input value."""
        self.input.setText(str(value))

    def get_value(self) -> int:
        """Get the current value from the input box."""
        try:
            return int(self.input.text())
        except ValueError:
            return 0