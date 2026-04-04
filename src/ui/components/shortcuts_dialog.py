from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt6.QtCore import Qt

SHORTCUTS = [
    ("→ / ←",           "Next / previous page"),
    ("Space",            "Play / pause (video & GIF)"),
    ("Tab",              "Cycle alt variant"),
    ("Ctrl + Drag",      "Drag current image or frame out"),
    ("Ctrl + Scroll",    "Zoom in / out"),
    ("Double-click",     "Reset zoom"),
    ("Ctrl + V",         "Paste image as alternate"),
    ("Ctrl + S",         "Save area selection"),
    ("F11 / Alt+Enter",  "Toggle fullscreen"),
    ("`  (backtick)",    "Hide / show screen"),
    ("Escape",           "Go back"),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        table = QTableWidget(len(SHORTCUTS), 2, self)
        table.setHorizontalHeaderLabels(["Shortcut", "Action"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)

        for row, (key, desc) in enumerate(SHORTCUTS):
            table.setItem(row, 0, QTableWidgetItem(key))
            table.setItem(row, 1, QTableWidgetItem(desc))

        table.resizeRowsToContents()
        layout.addWidget(table)
