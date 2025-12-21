import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QDialogButtonBox, 
    QPushButton, QHBoxLayout, QWidget, QComboBox, QAbstractItemView,
    QListWidgetItem
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIcon
from src.utils.img_utils import load_thumbnail_from_path
from src.enums import Language

class AddTranslationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Translations (Drag Folder)")
        self.resize(600, 500)
        self.setAcceptDrops(True)
        
        self.layout = QVBoxLayout(self)
        
        # 1. Language Selection
        lang_layout = QHBoxLayout()
        lang_label = QLabel("Translation Language:")
        lang_label.setStyleSheet("color: white; font-weight: bold;")
        
        self.lang_combo = QComboBox()
        # Populate from Language Enum
        for lang in Language:
            self.lang_combo.addItem(lang.value, lang)
            
        lang_layout.addWidget(lang_label)
        lang_layout.addWidget(self.lang_combo)
        lang_layout.addStretch()
        self.layout.addLayout(lang_layout)
        
        # 2. Instructions
        self.label = QLabel("Drag and drop a FOLDER containing translated images here.\nThe system will automatically match them to the chapter pages.")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: #aaa; font-size: 14px; margin: 10px; border: 2px dashed #555; padding: 20px; border-radius: 10px;")
        self.label.setWordWrap(True)
        self.layout.addWidget(self.label)
        
        # 3. File List (Preview)
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
        """)
        self.layout.addWidget(self.list_widget)
        
        # 4. Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False) # Disable OK until files added
        self.layout.addWidget(self.button_box)
        
        self.image_paths = []

    def get_selected_language(self) -> Language:
        return self.lang_combo.currentData()

    def get_image_paths(self) -> list[str]:
        return self.image_paths

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.label.setStyleSheet("color: white; font-size: 14px; margin: 10px; border: 2px dashed #03A9F4; padding: 20px; border-radius: 10px; background-color: rgba(3, 169, 244, 0.1);")
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.label.setStyleSheet("color: #aaa; font-size: 14px; margin: 10px; border: 2px dashed #555; padding: 20px; border-radius: 10px;")
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self.label.setStyleSheet("color: #aaa; font-size: 14px; margin: 10px; border: 2px dashed #555; padding: 20px; border-radius: 10px;")
        
        self.image_paths = []
        self.list_widget.clear()
        
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.isdir(path):
                    # Scan folder for images
                    try:
                        valid_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
                        for f in os.listdir(path):
                            full_path = os.path.join(path, f)
                            if os.path.isfile(full_path):
                                if os.path.splitext(f)[1].lower() in valid_exts:
                                    self.image_paths.append(full_path)
                    except OSError:
                        pass
                elif os.path.isfile(path):
                     # Allow single file drop too?
                     valid_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
                     if os.path.splitext(path)[1].lower() in valid_exts:
                         self.image_paths.append(path)

            # Sort nicely
            # simple sort by name
            self.image_paths.sort()
            
            # Populate List
            for p in self.image_paths:
                item = QListWidgetItem(os.path.basename(p))
                pix = load_thumbnail_from_path(p, 60, 80) 
                if pix:
                     item.setIcon(QIcon(pix))
                self.list_widget.addItem(item)
            
            event.acceptProposedAction()
            
            if self.image_paths:
                self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
                self.label.setText(f"Found {len(self.image_paths)} images.")
            else:
                self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
                self.label.setText("No valid images found in drop.")
