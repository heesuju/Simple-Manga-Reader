import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QTreeWidget, QTreeWidgetItem, QInputDialog, QMessageBox,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap
from src.utils.img_utils import load_thumbnail_from_path

THUMB_SIZE = 48

class EditAltsDialog(QDialog):
    def __init__(self, parent=None, page_obj=None, model=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Alternates")
        self.resize(500, 600)
        
        self.page_obj = page_obj
        self.model = model
        self.chapter_dir = Path(model.manga_dir) if model else None
        
        self.main_layout = QVBoxLayout(self)
        
        info_label = QLabel("Drag to reorder variants or drop them into different categories.\nDouble-click a category to rename it.")
        info_label.setWordWrap(True)
        self.main_layout.addWidget(info_label)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
        # Enable Drag and Drop
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        
        # Double clicking allows renaming categories
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.main_layout.addWidget(self.tree)
        
        # Action buttons row
        action_layout = QHBoxLayout()
        add_cat_btn = QPushButton("+ Add Category")
        add_cat_btn.clicked.connect(self._add_category)
        action_layout.addWidget(add_cat_btn)
        action_layout.addStretch()
        self.main_layout.addLayout(action_layout)
        
        # Bottom buttons
        btn_layout = QHBoxLayout()
        self.apply_btn = QPushButton("Apply Changes")
        self.apply_btn.clicked.connect(self._apply_changes)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.apply_btn)
        
        self.main_layout.addLayout(btn_layout)
        
        self._populate_tree()
        
    def _resolve_path(self, path_str):
        """Resolve a potentially relative path to absolute using chapter_dir."""
        p = Path(path_str)
        if not p.is_absolute() and self.chapter_dir:
            p = self.chapter_dir / p
        return str(p)
    
    def _make_thumbnail_icon(self, path_str):
        """Load a small thumbnail as a QIcon for tree items."""
        resolved = self._resolve_path(path_str)
        try:
            pixmap = load_thumbnail_from_path(resolved, THUMB_SIZE, THUMB_SIZE)
            if pixmap and not pixmap.isNull():
                return QIcon(pixmap)
        except Exception:
            pass
        return QIcon()
        
    def _populate_tree(self):
        self.tree.clear()
        
        if not self.page_obj: return
        
        categories = self.page_obj.get_categorized_variants()
        
        for cat_name, items in categories.items():
            # Don't show the category if the only thing inside is the original un-editable first image
            valid_items = [p for p in items if p != self.page_obj.images[0]]
            
            if not valid_items:
                continue
                
            cat_item = QTreeWidgetItem(self.tree, [cat_name])
            cat_item.setFlags(cat_item.flags() ^ Qt.ItemFlag.ItemIsDragEnabled) # Disable dragging categories themselves
            
            for path in valid_items:
                file_name = Path(path).name
                variant_item = QTreeWidgetItem(cat_item, [file_name])
                variant_item.setData(0, Qt.ItemDataRole.UserRole, path)
                variant_item.setIcon(0, self._make_thumbnail_icon(path))
                # Prevent dropping items AS CHILDREN of this item — only reorder within the category
                variant_item.setFlags(variant_item.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
                
            cat_item.setExpanded(True)

    def _add_category(self):
        """Add a new empty category to the tree."""
        name, ok = QInputDialog.getText(self, "New Category", "Category Name:")
        if ok and name.strip():
            cat_name = name.strip().lower()
            # Check if it already exists
            for i in range(self.tree.topLevelItemCount()):
                if self.tree.topLevelItem(i).text(0) == cat_name:
                    QMessageBox.warning(self, "Duplicate", f"Category '{cat_name}' already exists.")
                    return
            cat_item = QTreeWidgetItem(self.tree, [cat_name])
            cat_item.setFlags(cat_item.flags() ^ Qt.ItemFlag.ItemIsDragEnabled)
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
                
        from src.ui.page_utils import apply_alt_edits
        success = apply_alt_edits(self.model, self.page_obj, new_structure)
        
        if success:
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "Failed to apply changes.")
