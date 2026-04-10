import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTreeWidget, QTreeWidgetItem, QInputDialog, QMessageBox,
    QAbstractItemView, QHeaderView, QFileDialog
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QColor, QBrush
from src.utils.img_utils import load_thumbnail_from_path
from src.utils.str_utils import natural_sort_key

THUMB_W = 80
THUMB_H = 120

_ROLE_PATH     = Qt.ItemDataRole.UserRole
_ROLE_ORIG_CAT = Qt.ItemDataRole.UserRole + 1
_ROLE_IS_NEW   = Qt.ItemDataRole.UserRole + 2

_MEDIA_FILTER = "Media Files (*.png *.jpg *.jpeg *.jpe *.webp *.avif *.gif *.mp4 *.webm *.mkv)"
_MEDIA_EXTS   = {'.png', '.jpg', '.jpeg', '.jpe', '.webp', '.avif', '.gif', '.mp4', '.webm', '.mkv'}

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
    files_dropped = pyqtSignal(list, str)  # (absolute_file_paths, category_name or "")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            file_paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            if file_paths:
                item = self.itemAt(event.position().toPoint())
                cat_name = ""
                if item:
                    cat_name = item.text(0) if item.parent() is None else item.parent().text(0)
                self.files_dropped.emit(file_paths, cat_name)
            event.acceptProposedAction()
        else:
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
        self._pending_removal = set()        # existing paths to remove on Apply
        self._pending_add = []               # list of (src_path, category_name)
        self._pending_add_paths = set()      # for quick lookup

        self.main_layout = QVBoxLayout(self)

        info_label = QLabel("Drag to reorder or drop files to add. Double-click a category to rename it.")
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
        self.tree.files_dropped.connect(self._on_files_dropped)
        self.main_layout.addWidget(self.tree)

        action_layout = QHBoxLayout()
        add_file_btn = QPushButton("+ Add File")
        add_file_btn.clicked.connect(self._pick_files)
        action_layout.addWidget(add_file_btn)
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

    # ------------------------------------------------------------------ helpers

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

    def _get_or_create_cat_item(self, cat_name):
        for i in range(self.tree.topLevelItemCount()):
            if self.tree.topLevelItem(i).text(0) == cat_name:
                return self.tree.topLevelItem(i)
        cat_item = QTreeWidgetItem(self.tree, [cat_name])
        cat_item.setFlags(cat_item.flags() ^ Qt.ItemFlag.ItemIsDragEnabled)
        cat_item.setExpanded(True)
        return cat_item

    # ---------------------------------------------------------------- populate

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
        variant_item.setData(0, _ROLE_IS_NEW, False)
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

    # --------------------------------------------------------- pending removal

    def _toggle_removal(self, item):
        path = item.data(0, _ROLE_PATH)
        if path in self._pending_removal:
            self._pending_removal.discard(path)
        else:
            self._pending_removal.add(path)
        self._update_item_visuals(item)

    # ---------------------------------------------------------------- adding

    def _on_files_dropped(self, file_paths, cat_name):
        valid = [p for p in file_paths if Path(p).suffix.lower() in _MEDIA_EXTS]
        if not valid:
            return
        if not cat_name:
            cat_name = self._ask_category()
            if cat_name is None:
                return
        self._add_pending_files(valid, cat_name)

    def _pick_files(self):
        default_dir = str(self.chapter_dir) if self.chapter_dir else ""
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select Images/Videos", default_dir, _MEDIA_FILTER)
        if not file_paths:
            return
        cat_name = self._ask_category()
        if cat_name is None:
            return
        self._add_pending_files(file_paths, cat_name)

    def _ask_category(self):
        """Prompt user to pick an existing category or type a new one."""
        cats = [self.tree.topLevelItem(i).text(0) for i in range(self.tree.topLevelItemCount())]
        if not cats:
            cats = ["Main"]
        if len(cats) == 1:
            return cats[0]
        name, ok = QInputDialog.getItem(self, "Select Category", "Add to category:", cats, 0, True)
        if not ok or not name.strip():
            return None
        return name.strip()

    def _add_pending_files(self, file_paths, cat_name):
        cat_item = self._get_or_create_cat_item(cat_name)
        for src_path in sorted(file_paths, key=lambda p: natural_sort_key(Path(p).name)):
            if src_path in self._pending_add_paths:
                continue
            self._pending_add.append((src_path, cat_name))
            self._pending_add_paths.add(src_path)
            self._add_new_variant_item(cat_item, src_path)

    def _add_new_variant_item(self, cat_item, src_path):
        file_name = Path(src_path).name
        variant_item = QTreeWidgetItem(cat_item, [file_name])
        variant_item.setData(0, _ROLE_PATH, src_path)
        variant_item.setData(0, _ROLE_ORIG_CAT, None)
        variant_item.setData(0, _ROLE_IS_NEW, True)
        variant_item.setIcon(0, self._make_thumbnail_icon(src_path))
        variant_item.setSizeHint(0, QSize(THUMB_W, THUMB_H + 8))
        variant_item.setSizeHint(1, QSize(40, THUMB_H + 8))
        variant_item.setFlags(variant_item.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
        variant_item.setForeground(0, QBrush(QColor("#4daa70")))
        variant_item.setToolTip(0, f"New — will be added from:\n{src_path}")

        btn = QPushButton("✖")
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Cancel addition")
        btn.setStyleSheet(_STYLE_REMOVE)
        btn.clicked.connect(lambda _=False, i=variant_item, p=src_path: self._cancel_pending_add(i, p))
        self.tree.setItemWidget(variant_item, 1, btn)

    def _cancel_pending_add(self, item, src_path):
        self._pending_add = [(p, c) for p, c in self._pending_add if p != src_path]
        self._pending_add_paths.discard(src_path)
        parent = item.parent()
        if parent:
            parent.removeChild(item)

    # ---------------------------------------------------------- visual updates

    def _update_item_visuals(self, item):
        if item.data(0, _ROLE_IS_NEW):
            return  # new items keep their green style

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

    # --------------------------------------------------------- category actions

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

    # ------------------------------------------------------------------ apply

    def _collect_moves(self):
        moves = []
        for i in range(self.tree.topLevelItemCount()):
            cat_item = self.tree.topLevelItem(i)
            current_cat = cat_item.text(0)
            for j in range(cat_item.childCount()):
                variant_item = cat_item.child(j)
                if variant_item.data(0, _ROLE_IS_NEW):
                    continue
                path = variant_item.data(0, _ROLE_PATH)
                orig_cat = variant_item.data(0, _ROLE_ORIG_CAT)
                if path not in self._pending_removal and orig_cat and current_cat != orig_cat:
                    moves.append((Path(path).name, orig_cat, current_cat))
        return moves

    def _apply_changes(self):
        delete_from_disk = False

        removals = sorted(self._pending_removal, key=lambda p: Path(p).name)
        moves = self._collect_moves()
        # Collect additions in tree order (user may have reordered by dragging)
        additions = []
        for i in range(self.tree.topLevelItemCount()):
            cat_item = self.tree.topLevelItem(i)
            cat_name = cat_item.text(0)
            for j in range(cat_item.childCount()):
                variant_item = cat_item.child(j)
                if variant_item.data(0, _ROLE_IS_NEW):
                    additions.append((variant_item.data(0, _ROLE_PATH), cat_name))

        if not removals and not moves and not additions:
            QMessageBox.information(self, "No Changes", "No changes to apply.")
            return

        lines = []
        if additions:
            lines.append(f"Additions ({len(additions)}):")
            for src, cat in additions:
                lines.append(f"  • {Path(src).name}  →  {cat}")
        if moves:
            if lines: lines.append("")
            lines.append(f"Moves ({len(moves)}):")
            for name, orig, dest in moves:
                lines.append(f"  • {name}:  {orig}  →  {dest}")
        if removals:
            if lines: lines.append("")
            lines.append(f"Removals ({len(removals)}):")
            for p in removals:
                lines.append(f"  • {Path(p).name}")

        confirm = QMessageBox.question(
            self, "Apply Changes",
            f"The following changes will be applied:\n\n" + "\n".join(lines),
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

        # Build new_structure for existing variants only (exclude pending adds)
        new_structure = {}
        for i in range(self.tree.topLevelItemCount()):
            cat_item = self.tree.topLevelItem(i)
            cat_name = cat_item.text(0)
            paths = []
            for j in range(cat_item.childCount()):
                variant_item = cat_item.child(j)
                path = variant_item.data(0, _ROLE_PATH)
                if not variant_item.data(0, _ROLE_IS_NEW) and path not in self._pending_removal:
                    paths.append(path)
            if paths:
                new_structure[cat_name] = paths

        # 1. Apply edits to existing variants (moves, removals)
        from src.ui.page_utils import apply_alt_edits
        success = apply_alt_edits(self.model, self.page_obj, new_structure)
        if not success:
            QMessageBox.critical(self, "Error", "Failed to apply changes.")
            return

        if delete_from_disk:
            for path in self._pending_removal:
                resolved = self._resolve_path(path)
                if '|' in resolved:
                    QMessageBox.warning(self, "Unsupported", "Deleting files inside archives is not supported.")
                else:
                    try:
                        if os.path.exists(resolved):
                            os.remove(resolved)
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Failed to delete '{Path(path).name}': {e}")

        # 2. Add new files (grouped by category)
        if additions:
            from src.ui.page_utils import process_add_alts
            try:
                target_index = next(i for i, p in enumerate(self.model.images) if p is self.page_obj)
            except StopIteration:
                target_index = self.model.current_index

            by_cat = {}
            for src, cat in additions:
                by_cat.setdefault(cat, []).append(src)

            for cat, paths in by_cat.items():
                process_add_alts(
                    self.model, paths, target_index,
                    lambda: None, lambda _: None,
                    category=cat
                )

        self.accept()
