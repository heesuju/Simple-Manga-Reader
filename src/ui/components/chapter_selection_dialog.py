from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, 
    QListWidgetItem, QLabel, QCheckBox
)
from PyQt6.QtCore import Qt

class ChapterSelectionDialog(QDialog):
    def __init__(self, chapters, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Chapters")
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)
        
        self.chapters = chapters
        self.selected_chapters = []
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Info Label
        self.info_label = QLabel(f"Found {len(self.chapters)} chapters. Select chapters to import:")
        layout.addWidget(self.info_label)
        
        # Selection Buttons
        btn_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        
        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # List Widget
        self.list_widget = QListWidget()
        for chapter in self.chapters:
            item = QListWidgetItem()
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setText(chapter['name'])
            item.setData(Qt.ItemDataRole.UserRole, chapter)
            self.list_widget.addItem(item)
            
        layout.addWidget(self.list_widget)
        
        # Action Buttons
        action_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.add_btn = QPushButton("Add Selected")
        self.add_btn.clicked.connect(self.accept_selection)
        
        action_layout.addStretch()
        action_layout.addWidget(self.cancel_btn)
        action_layout.addWidget(self.add_btn)
        layout.addLayout(action_layout)
        
    def select_all(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setCheckState(Qt.CheckState.Checked)
            
    def deselect_all(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setCheckState(Qt.CheckState.Unchecked)
            
    def accept_selection(self):
        self.selected_chapters = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                self.selected_chapters.append(item.data(Qt.ItemDataRole.UserRole))
        
        self.accept()
        
    def get_selected_chapters(self):
        return self.selected_chapters
