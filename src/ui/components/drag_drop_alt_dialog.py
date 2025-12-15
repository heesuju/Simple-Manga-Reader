import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QDialogButtonBox, 
    QPushButton, QHBoxLayout, QWidget, QAbstractItemView, QListWidgetItem
)
from PyQt6.QtCore import Qt, QUrl, QSize
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPixmap
from src.utils.img_utils import load_thumbnail_from_path

class DragDropAltDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Alternates (Drag & Drop)")
        self.resize(600, 500)
        self.setAcceptDrops(True)
        
        self.layout = QVBoxLayout(self)
        
        # Instructions
        self.label = QLabel("Drag and drop files here to add them as alternates.\nYou can add multiple files.")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: #aaa; font-size: 14px; margin: 10px;")
        self.label.setWordWrap(True)
        self.layout.addWidget(self.label)
        
        # Count Label
        self.count_label = QLabel("Count: 0")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.count_label.setStyleSheet("color: #fff; font-weight: bold; margin-right: 10px;")
        self.layout.addWidget(self.count_label)
        
        # File List
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setIconSize(QSize(100, 140))
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setSpacing(10)
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
            QListWidget::item:selected {
                background-color: rgba(3, 169, 244, 0.5);
                border-radius: 5px;
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
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: rgba(3, 169, 244, 0.5);
                border-radius: 5px;
            }
        """)
        
        files_added = 0
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if os.path.isfile(file_path):
                    ext = os.path.splitext(file_path)[1].lower()
                    if ext in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.mp4', '.webm', '.mkv', '.avi', '.mov'}:
                        if file_path not in self.file_paths:
                            self.file_paths.append(file_path)
                            
                            # Create Item
                            item = QListWidgetItem(os.path.basename(file_path))
                            
                            # Load Thumbnail
                            # For better performance we could run this in a thread, but for D&D of a few files this is okay.
                            # We use 100x140 as base size
                            pixmap = load_thumbnail_from_path(file_path, 100, 140)
                            if pixmap:
                                item.setIcon(QIcon(pixmap))
                            
                            self.list_widget.addItem(item)
                            files_added += 1
            
            event.acceptProposedAction()
            self._update_count()
            
    def _remove_selected(self):
        for item in self.list_widget.selectedItems():
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
            if row < len(self.file_paths):
                self.file_paths.pop(row)
        self._update_count()

    def _update_count(self):
        count = len(self.file_paths)
        self.count_label.setText(f"Count: {count}")

    def get_files(self):
        return self.file_paths
