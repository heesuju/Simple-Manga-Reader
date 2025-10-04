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

        self.label = QLabel(f"{title}:")
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.input = QLineEdit(str(current))
        
        self.input.setFixedWidth(40)
        self.input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.input.setValidator(QIntValidator(1, 10**max_digits))

        self.total_label = QLabel(f"/ {total}")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.total_label.setStyleSheet("""QLabel { color: white; }""")
        
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.label.setStyleSheet("""QLabel { color: white; }""")
        self.input.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)  # vertically center everything
        layout.addWidget(self.label)
        layout.addWidget(self.input)
        layout.addWidget(self.total_label)
        
        self.setLayout(layout)

        # Connect Enter key
        self.input.returnPressed.connect(self._on_enter)
        self.input.installEventFilter(self)

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