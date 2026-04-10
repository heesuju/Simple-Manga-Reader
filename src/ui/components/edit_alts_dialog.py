import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTreeWidget, QTreeWidgetItem, QInputDialog, QMessageBox,
    QAbstractItemView, QHeaderView
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QColor, QBrush
from src.utils.img_utils import load_thumbnail_from_path
from src.utils.str_utils import natural_sort_key

THUMB_W = 80
THUMB_H = 120

_ROLE_PATH = Qt.ItemDataRole.UserRole
_ROLE_ORIG_CAT = Qt.ItemDataRole.UserRole + 1

_STYLE_REMOVE = """
    QPushButton { border: none; background: transparent; color: #ff4d4d; font-weight: bold; font-size: 16px; }
    QPushButton:hover { color: #ff0000; background-color: rgba(255,0,0,0.1); border-radius: 12px; }
"""
_STYLE_UNDO = """
    QPushButton { border: none; background: transparent; color: #888888; font-weight: bold; font-size: 16px; }
    QPushButton:hover { color: #bbbbbb; background-color: rgba(255,255,255,0.1); border-radius: 12px; }
"""


class AltTreeWidget(QTreeWidget):
    items_rearranged = pyqtSignal()

    def dropEvent(self, event):
        super().dropEvent(event)
        self.items_rearranged.emit()


class EditAltsDialog(QDialog):
    def __init__(self, parent=None, page_obj=None, model=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Alternates")
        self.resize(560, 700)

        self.page_obj = page_obj
        self.model = model
        self.chapter_dir = Path(model.manga_dir) if model else None
        self._pending_removal = set()  # paths pending removal on Apply

        self.main_layout = QVBoxLayout(self)

        info_label = QLabel("Drag to reorder variants or drop them into different categories.\nDouble-click a category to rename it.")
        info_label.setWordWrap(True)
        self.main_layout.addWidget(info_label)

        self.tree = AltTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(THUMB_W, THUMB_H))

        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tree.setColumnWidth(1, 40)

        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.items_rearranged.connect(self._update_change_indicators)
        self.main_layout.addWidget(self.tree)

        action_layout = QHBoxLayout()
        add_cat_btn = QPushButton("+ Add Category")
        add_cat_btn.clicked.connect(self._add_category)
        action_layout.addWidget(add_cat_btn)
        action_layout.addStretch()
        self.main_layout.addLayout(action_layout)

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
        p = Path(path_str)
        if not p.is_absolute() and self.chapter_dir:
            p = self.chapter_dir / p
        return str(p)

    def _make_thumbnail_icon(self, path_str):
        resolved = self._resolve_path(path_str)
        try:
            qimg = load_thumbnail_from_path(resolved, THUMB_W, THUMB_H)
            if qimg and not qimg.isNull():
                return QIcon(QPixmap.fromImage(qimg))
        except Exception:
            pass
        return QIcon()

    def _populate_tree(self):
        self.tree.clear()
        if not self.page_obj:
            return

        categories = self.page_obj.get_categorized_variants()
        cat_names = sorted(categories.keys(), key=lambda c: (0 if c == "Main" else 1, natural_sort_key(c)))

        for cat_name in cat_names:
            items = categories[cat_name]
            valid_items = [p for p in items if p != self.page_obj.images[0]]
            valid_items = sorted(valid_items, key=lambda p: natural_sort_key(Path(p).name))

            if not valid_items and cat_name != "Main":
                continue

            cat_item = QTreeWidgetItem(self.tree, [cat_name])
            cat_item.setFlags(cat_item.flags() ^ Qt.ItemFlag.ItemIsDragEnabled)

            for path in valid_items:
                self._add_variant_item(cat_item, path, cat_name)

            cat_item.setExpanded(True)

    def _add_variant_item(self, cat_item, path, orig_cat):
        file_name = Path(path).name
        variant_item = QTreeWidgetItem(cat_item, [file_name])
        variant_item.setData(0, _ROLE_PATH, path)
        variant_item.setData(0, _ROLE_ORIG_CAT, orig_cat)
        variant_item.setIcon(0, self._make_thumbnail_icon(path))
        variant_item.setSizeHint(0, QSize(THUMB_W, THUMB_H + 8))
        variant_item.setSizeHint(1, QSize(40, THUMB_H + 8))
        variant_item.setFlags(variant_item.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)

        btn = QPushButton("✖")
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Mark for removal")
        btn.setStyleSheet(_STYLE_REMOVE)
        btn.clicked.connect(lambda _=False, i=variant_item: self._toggle_removal(i))
        self.tree.setItemWidget(variant_item, 1, btn)

    def _toggle_removal(self, item):
        path = item.data(0, _ROLE_PATH)
        if path in self._pending_removal:
            self._pending_removal.discard(path)
        else:
            self._pending_removal.add(path)
        self._update_item_visuals(item)

    def _update_item_visuals(self, item):
        path = item.data(0, _ROLE_PATH)
        orig_cat = item.data(0, _ROLE_ORIG_CAT)
        current_cat = item.parent().text(0) if item.parent() else None
        is_pending = path in self._pending_removal
        is_moved = current_cat and orig_cat and current_cat != orig_cat

        font = item.font(0)
        btn = self.tree.itemWidget(item, 1)

        if is_pending:
            font.setStrikeOut(True)
            item.setForeground(0, QBrush(QColor("#ff4d4d")))
            item.setToolTip(0, "Pending removal — click ↩ to undo")
            if btn:
                btn.setText("↩")
                btn.setToolTip("Undo removal")
                btn.setStyleSheet(_STYLE_UNDO)
        elif is_moved:
            font.setStrikeOut(False)
            item.setForeground(0, QBrush(QColor("#f0a030")))
            item.setToolTip(0, f"Moved from: {orig_cat}")
            if btn:
                btn.setText("✖")
                btn.setToolTip("Mark for removal")
                btn.setStyleSheet(_STYLE_REMOVE)
        else:
            font.setStrikeOut(False)
            item.setForeground(0, QBrush())
            item.setToolTip(0, "")
            if btn:
                btn.setText("✖")
                btn.setToolTip("Mark for removal")
                btn.setStyleSheet(_STYLE_REMOVE)

        item.setFont(0, font)

    def _update_change_indicators(self):
        for i in range(self.tree.topLevelItemCount()):
            cat_item = self.tree.topLevelItem(i)
            for j in range(cat_item.childCount()):
                self._update_item_visuals(cat_item.child(j))

    def _add_category(self):
        name, ok = QInputDialog.getText(self, "New Category", "Category Name:")
        if ok and name.strip():
            cat_name = name.strip().lower()
            for i in range(self.tree.topLevelItemCount()):
                if self.tree.topLevelItem(i).text(0) == cat_name:
                    QMessageBox.warning(self, "Duplicate", f"Category '{cat_name}' already exists.")
                    return
            cat_item = QTreeWidgetItem(self.tree, [cat_name])
            cat_item.setFlags(cat_item.flags() ^ Qt.ItemFlag.ItemIsDragEnabled)
            cat_item.setExpanded(True)

    def _on_item_double_clicked(self, item, _):
        if item.parent() is None:
            old_name = item.text(0)
            new_name, ok = QInputDialog.getText(self, "Rename Category", "New Category Name:", text=old_name)
            if ok and new_name.strip():
                item.setText(0, new_name.strip().lower())
                self._update_change_indicators()

    def _collect_moves(self):
        """Return list of (filename, orig_cat, new_cat) for items that changed category."""
        moves = []
        for i in range(self.tree.topLevelItemCount()):
            cat_item = self.tree.topLevelItem(i)
            current_cat = cat_item.text(0)
            for j in range(cat_item.childCount()):
                variant_item = cat_item.child(j)
                path = variant_item.data(0, _ROLE_PATH)
                orig_cat = variant_item.data(0, _ROLE_ORIG_CAT)
                if path not in self._pending_removal and orig_cat and current_cat != orig_cat:
                    moves.append((Path(path).name, orig_cat, current_cat))
        return moves

    def _apply_changes(self):
        delete_from_disk = False

        removals = sorted(self._pending_removal, key=lambda p: Path(p).name)
        moves = self._collect_moves()

        if not removals and not moves:
            QMessageBox.information(self, "No Changes", "No changes to apply.")
            return

        lines = []
        if moves:
            lines.append(f"Moves ({len(moves)}):")
            for name, orig, dest in moves:
                lines.append(f"  • {name}:  {orig} → {dest}")
        if removals:
            if lines:
                lines.append("")
            lines.append(f"Removals ({len(removals)}):")
            for p in removals:
                lines.append(f"  • {Path(p).name}")

        summary = "\n".join(lines)
        confirm = QMessageBox.question(
            self, "Apply Changes",
            f"The following changes will be applied:\n\n{summary}",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel
        )
        if confirm != QMessageBox.StandardButton.Ok:
            return

        if removals:
            delete_reply = QMessageBox.question(
                self, "Delete from Disk",
                "Also permanently delete the removed files from disk?\n\nThis cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            delete_from_disk = delete_reply == QMessageBox.StandardButton.Yes

        new_structure = {}
        for i in range(self.tree.topLevelItemCount()):
            cat_item = self.tree.topLevelItem(i)
            cat_name = cat_item.text(0)
            paths = []
            for j in range(cat_item.childCount()):
                variant_item = cat_item.child(j)
                path = variant_item.data(0, _ROLE_PATH)
                if path not in self._pending_removal:
                    paths.append(path)
            if paths:
                new_structure[cat_name] = paths

        from src.ui.page_utils import apply_alt_edits
        success = apply_alt_edits(self.model, self.page_obj, new_structure)

        if not success:
            QMessageBox.critical(self, "Error", "Failed to apply changes.")
            return

        if delete_from_disk:
            for path in self._pending_removal:
                resolved = self._resolve_path(path)
                if '|' in resolved:
                    QMessageBox.warning(self, "Unsupported", f"Deleting files inside archives is not supported.")
                else:
                    try:
                        if os.path.exists(resolved):
                            os.remove(resolved)
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Failed to delete '{Path(path).name}': {e}")

        self.accept()
