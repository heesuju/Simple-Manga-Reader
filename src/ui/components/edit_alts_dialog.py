import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QTreeWidget, QTreeWidgetItem, QInputDialog, QMessageBox,
    QAbstractItemView
)
from PyQt6.QtCore import Qt

class EditAltsDialog(QDialog):
    def __init__(self, parent=None, page_obj=None, model=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Alternates")
        self.resize(500, 600)
        
        self.page_obj = page_obj
        self.model = model
        
        self.layout = QVBoxLayout(self)
        
        info_label = QLabel("Drag to reorder variants or drop them into different categories.\nDouble-click a category to rename it.")
        info_label.setWordWrap(True)
        self.layout.addWidget(info_label)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        # Enable Drag and Drop
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        
        # Double clicking allows renaming categories
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.layout.addWidget(self.tree)
        
        btn_layout = QHBoxLayout()
        self.apply_btn = QPushButton("Apply Changes")
        self.apply_btn.clicked.connect(self._apply_changes)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.apply_btn)
        
        self.layout.addLayout(btn_layout)
        
        self._populate_tree()
        
    def _populate_tree(self):
        self.tree.clear()
        
        if not self.page_obj: return
        
        categories = self.page_obj.get_categorized_variants()
        
        for cat_name, items in categories.items():
            cat_item = QTreeWidgetItem(self.tree, [cat_name])
            cat_item.setFlags(cat_item.flags() ^ Qt.ItemFlag.ItemIsDragEnabled) # Disable dragging categories themselves
            
            for path in items:
                file_name = Path(path).name
                variant_item = QTreeWidgetItem(cat_item, [file_name])
                variant_item.setData(0, Qt.ItemDataRole.UserRole, path)
                
            cat_item.setExpanded(True)
            
    def _on_item_double_clicked(self, item, column):
        # Allow editing ONLY category items
        if item.parent() is None:
            old_name = item.text(0)
            new_name, ok = QInputDialog.getText(self, "Rename Category", "New Category Name:", text=old_name)
            if ok and new_name.strip():
                item.setText(0, new_name.strip().lower())

    def _apply_changes(self):
        # Reconstruct the expected categorical logic to pass down
        new_structure = {}
        for i in range(self.tree.topLevelItemCount()):
            cat_item = self.tree.topLevelItem(i)
            cat_name = cat_item.text(0)
            
            paths = []
            for j in range(cat_item.childCount()):
                variant_item = cat_item.child(j)
                path = variant_item.data(0, Qt.ItemDataRole.UserRole)
                paths.append(path)
                
            if paths:
                new_structure[cat_name] = paths
                
        # TODO: send this new structure to page utils to physically rename and modify info.json
        from src.ui.page_utils import apply_alt_edits
        success = apply_alt_edits(self.model, self.page_obj, new_structure)
        
        if success:
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "Failed to apply changes.")
