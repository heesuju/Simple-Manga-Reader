import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QDialogButtonBox, 
    QPushButton, QHBoxLayout, QWidget, QAbstractItemView
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

class DragDropAltDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Alternates (Drag & Drop)")
        self.resize(400, 500)
        self.setAcceptDrops(True)
        
        self.layout = QVBoxLayout(self)
        
        # Instructions
        self.label = QLabel("Drag and drop files here to add them as alternates.\nYou can add multiple files.")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: #aaa; font-size: 14px; margin: 10px;")
        self.label.setWordWrap(True)
        self.layout.addWidget(self.label)
        
        # File List
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: rgba(0, 0, 0, 50);
                border: 2px dashed #555;
                border-radius: 5px;
                color: white;
            }
            QListWidget::item {
                padding: 5px;
            }
        """)
        self.layout.addWidget(self.list_widget)
        
        # Remove Button
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self._remove_selected)
        self.layout.addWidget(self.remove_btn)
        
        # Dialog Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)
        
        self.file_paths = []

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.list_widget.setStyleSheet("""
                QListWidget {
                    background-color: rgba(50, 200, 255, 30);
                    border: 2px dashed #03A9F4;
                    border-radius: 5px;
                    color: white;
                }
            """)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: rgba(0, 0, 0, 50);
                border: 2px dashed #555;
                border-radius: 5px;
                color: white;
            }
        """)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: rgba(0, 0, 0, 50);
                border: 2px dashed #555;
                border-radius: 5px;
                color: white;
            }
        """)
        
        files_added = 0
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if os.path.isfile(file_path):
                    # Filter extensions if needed? 
                    # Assuming basic media check or just accept all and let caller handle
                    ext = os.path.splitext(file_path)[1].lower()
                    if ext in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.mp4', '.webm', '.mkv', '.avi', '.mov'}:
                        if file_path not in self.file_paths:
                            self.file_paths.append(file_path)
                            self.list_widget.addItem(os.path.basename(file_path))
                            files_added += 1
            
            event.acceptProposedAction()
            
    def _remove_selected(self):
        for item in self.list_widget.selectedItems():
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
            if row < len(self.file_paths):
                self.file_paths.pop(row)

    def get_files(self):
        return self.file_paths
