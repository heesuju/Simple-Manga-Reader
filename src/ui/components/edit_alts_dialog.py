from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QWidget,
    QTreeWidget, QTreeWidgetItem, QInputDialog, QMessageBox,
    QAbstractItemView, QHeaderView, QFileDialog, QSplitter, QListWidget, QSizePolicy,
    QStackedWidget, QTextEdit
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QColor, QBrush, QTextCursor, QDrag, QPainter
from src.utils.img_utils import load_thumbnail_from_path
from src.utils.str_utils import natural_sort_key

THUMB_W = 80
THUMB_H = 120

_ROLE_PATH     = Qt.ItemDataRole.UserRole
_ROLE_ORIG_CAT = Qt.ItemDataRole.UserRole + 1
_ROLE_IS_NEW   = Qt.ItemDataRole.UserRole + 2
_ROLE_NOTE     = Qt.ItemDataRole.UserRole + 3

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


class _NoteEditor(QTextEdit):
    commit_requested = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.commit_requested.emit()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.commit_requested.emit()


class NoteWidget(QWidget):
    def __init__(self, note_text='', parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.label.setCursor(Qt.CursorShape.IBeamCursor)
        self.label.mousePressEvent = lambda _: self._start_edit()
        self._stack.addWidget(self.label)

        self.editor = _NoteEditor()
        self.editor.setStyleSheet("background: rgba(0,0,0,100); border: 1px solid rgba(255,255,255,40); border-radius:3px; padding: 2px; font-size: 11px;")
        self.editor.commit_requested.connect(self._commit)
        self._stack.addWidget(self.editor)

        self._set_note(note_text)

    def _set_note(self, text):
        self.editor.setPlainText(text)
        self._sync_label()

    def _sync_label(self):
        text = self.editor.toPlainText().strip()
        if text:
            self.label.setText(text)
            self.label.setStyleSheet("font-size: 11px; color: rgba(255,255,255,180); padding: 4px;")
        else:
            self.label.setText("Add a note...")
            self.label.setStyleSheet("font-size: 11px; color: rgba(255,255,255,60); font-style: italic; padding: 4px;")

    def _start_edit(self):
        self._stack.setCurrentIndex(1)
        self.editor.setFocus()
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.editor.setTextCursor(cursor)

    def _commit(self):
        if self._stack.currentIndex() == 1:
            self._stack.setCurrentIndex(0)
            self._sync_label()

    def get_note(self):
        return self.editor.toPlainText().strip()


class CategoryListWidget(QListWidget):
    category_dropped_internal = pyqtSignal(str, list)
    files_dropped_external = pyqtSignal(list, str)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        elif event.source() and event.source() != self:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        elif event.source() and event.source() != self:
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        target_cat = item.text() if item else None

        if event.mimeData().hasUrls():
            file_paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            if file_paths:
                self.files_dropped_external.emit(file_paths, target_cat if target_cat else "")
            event.acceptProposedAction()
        elif event.source() and event.source() != self:
            if target_cat:
                paths = []
                for s_item in event.source().selectedItems():
                    paths.append(s_item.data(0, _ROLE_PATH))
                self.category_dropped_internal.emit(target_cat, paths)
            event.setDropAction(Qt.DropAction.IgnoreAction)
            event.accept()
        else:
            super().dropEvent(event)


class AltItemsTreeWidget(QTreeWidget):
    items_rearranged = pyqtSignal()
    files_dropped = pyqtSignal(list, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_category = ""

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

    def startDrag(self, supported_actions):
        selected = self.selectedItems()
        if not selected:
            return

        names = [Path(item.data(0, _ROLE_PATH)).name for item in selected if item.data(0, _ROLE_PATH)]
        text = "\n".join(names[:3])
        if len(names) > 3:
            text += f"\n+{len(names) - 3} more"

        fm = self.fontMetrics()
        lines = text.split("\n")
        w = max(fm.horizontalAdvance(l) for l in lines) + 20
        h = fm.height() * len(lines) + 12

        pixmap = QPixmap(w, h)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(50, 50, 50, 220))
        painter.setPen(QColor(120, 120, 120))
        painter.drawRoundedRect(pixmap.rect().adjusted(0, 0, -1, -1), 4, 4)
        painter.setPen(QColor(220, 220, 220))
        painter.drawText(pixmap.rect().adjusted(10, 6, -10, -6), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        painter.end()

        drag = QDrag(self)
        drag.setMimeData(self.mimeData(selected))
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())
        drag.exec(supported_actions, Qt.DropAction.MoveAction)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            file_paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            if file_paths:
                self.files_dropped.emit(file_paths, self.current_category)
            event.acceptProposedAction()
        else:
            for i in range(self.topLevelItemCount()):
                item = self.topLevelItem(i)
                note_widget = self.itemWidget(item, 1)
                if isinstance(note_widget, NoteWidget):
                    item.setData(0, _ROLE_NOTE, note_widget.get_note())
            super().dropEvent(event)
            self.items_rearranged.emit()


class EditAltsDialog(QDialog):
    def __init__(self, parent=None, page_obj=None, model=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Alternates")
        self.resize(740, 700)

        self.page_obj = page_obj
        self.model = model
        self.chapter_dir = Path(model.manga_dir) if model else None

        self._data = {}
        self._orig_order = {}
        self._pending_removal = set()
        self._current_cat = None

        self.main_layout = QVBoxLayout(self)

        info_label = QLabel("Select a category. Drag to reorder, or drop files to add. Double-click a category to rename it. Drag items to a category on the left to move them.")
        info_label.setWordWrap(True)
        info_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.main_layout.addWidget(info_label)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_layout.addWidget(self.splitter, 1)

        _PLUS_STYLE = "QPushButton { border: none; background: transparent; color: #aaa; font-size: 16px; padding: 0 4px; } QPushButton:hover { color: #fff; }"

        # Left Column - Categories
        cat_layout = QVBoxLayout()
        cat_layout.setContentsMargins(0, 0, 0, 0)
        cat_layout.setSpacing(2)

        cat_header = QHBoxLayout()
        cat_header.setContentsMargins(0, 0, 0, 0)
        cat_header.addWidget(QLabel("Categories"))
        cat_header.addStretch()
        add_cat_btn = QPushButton("+")
        add_cat_btn.setFixedSize(24, 24)
        add_cat_btn.setToolTip("Add Category")
        add_cat_btn.setStyleSheet(_PLUS_STYLE)
        add_cat_btn.clicked.connect(self._add_category)
        cat_header.addWidget(add_cat_btn)
        cat_layout.addLayout(cat_header)

        self.cat_list = CategoryListWidget()
        self.cat_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.cat_list.itemDoubleClicked.connect(self._on_cat_double_clicked)
        self.cat_list.currentItemChanged.connect(self._on_category_changed)
        self.cat_list.category_dropped_internal.connect(self._on_items_moved_to_category)
        self.cat_list.files_dropped_external.connect(self._on_files_dropped)
        self.cat_list.setAcceptDrops(True)
        self.cat_list.setDragEnabled(False)
        cat_layout.addWidget(self.cat_list)

        cat_widget = QWidget()
        cat_widget.setLayout(cat_layout)
        self.splitter.addWidget(cat_widget)

        # Right Column - Items
        item_layout = QVBoxLayout()
        item_layout.setContentsMargins(0, 0, 0, 0)
        item_layout.setSpacing(2)

        item_header = QHBoxLayout()
        item_header.setContentsMargins(0, 0, 0, 0)
        item_header.addWidget(QLabel("Alternates"))
        item_header.addStretch()
        add_file_btn = QPushButton("+")
        add_file_btn.setFixedSize(24, 24)
        add_file_btn.setToolTip("Add File")
        add_file_btn.setStyleSheet(_PLUS_STYLE)
        add_file_btn.clicked.connect(self._pick_files)
        item_header.addWidget(add_file_btn)
        item_layout.addLayout(item_header)

        self.item_tree = AltItemsTreeWidget()
        self.item_tree.header().hide()
        self.item_tree.setColumnCount(3)
        self.item_tree.setIconSize(QSize(THUMB_W, THUMB_H))
        header = self.item_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.item_tree.setColumnWidth(2, 40)
        self.item_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        self.item_tree.setDragEnabled(True)
        self.item_tree.setAcceptDrops(True)
        self.item_tree.setDropIndicatorShown(True)
        self.item_tree.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.item_tree.setDefaultDropAction(Qt.DropAction.MoveAction)

        self.item_tree.items_rearranged.connect(self._update_change_indicators)
        self.item_tree.files_dropped.connect(self._on_files_dropped)
        item_layout.addWidget(self.item_tree)

        item_widget = QWidget()
        item_widget.setLayout(item_layout)
        self.splitter.addWidget(item_widget)

        self.splitter.setSizes([200, 500])

        btn_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self._apply_changes)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.apply_btn)
        self.main_layout.addLayout(btn_layout)

        self._init_data()

    # ---------------------------------------------------------------- helpers

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

    def _is_path_added(self, path):
        for i in range(self.item_tree.topLevelItemCount()):
            if self.item_tree.topLevelItem(i).data(0, _ROLE_PATH) == path:
                return True
        for items in self._data.values():
            for item in items:
                if item['path'] == path:
                    return True
        return False

    # ---------------------------------------------------------------- populate

    def _init_data(self):
        self._data.clear()
        self.cat_list.clear()

        if not self.page_obj:
            return

        page_categories = self.page_obj.get_categorized_variants()
        main_file = self.page_obj.images[0]
        
        # Assuming model has necessary path attributes
        self.series_path = Path(self.model.manga_dir).parent
        self.chapter_name = Path(self.model.manga_dir).name

        import src.core.alt_manager as alt_m
        data = alt_m.AltManager.load_alts(self.series_path)
        page_entry = data.get(self.chapter_name, {}).get(Path(main_file).name, {})
        if isinstance(page_entry, list):
            page_entry = {"alts": page_entry, "translations": {}}
        alts_fix_map = page_entry.get("alts_fix", {})
        fix_to_orig = {v: k for k, v in alts_fix_map.items()}

        cat_names = sorted(page_categories.keys(), key=lambda c: (0 if c.lower() == "main" else 1, natural_sort_key(c)))
        if not any(c.lower() == "main" for c in cat_names):
            cat_names.insert(0, "Main")

        for cat_name in cat_names:
            self._data[cat_name] = []
            if cat_name in page_categories:
                for variant_path in page_categories[cat_name]:
                    if variant_path != main_file:
                        note_text = ""
                        try:
                            rel = str(Path(variant_path).relative_to(self.model.manga_dir)).replace('\\', '/')
                            original_rel = fix_to_orig.get(rel, rel)
                            note_text = alt_m.AltManager.get_alt_note(self.series_path, self.chapter_name, Path(main_file).name, original_rel)
                        except ValueError:
                            pass
                            
                        self._data[cat_name].append({
                            'path': variant_path,
                            'orig_cat': cat_name,
                            'is_new': False,
                            'note': note_text,
                            '_orig_note': note_text,
                        })
            self.cat_list.addItem(cat_name)

        self._orig_order = {cat: [d['path'] for d in items] for cat, items in self._data.items()}

        if self.cat_list.count() > 0:
            self.cat_list.setCurrentRow(0)

    # --------------------------------------------------------- syncing & state

    def _on_category_changed(self, current, previous):
        if previous:
            old_cat = previous.text()
            self._save_current_category_order(old_cat)
        if current:
            new_cat = current.text()
            self._current_cat = new_cat
            self._load_category_items(new_cat)

    def _save_current_category_order(self, cat_name):
        if not cat_name:
            return

        new_items = []
        for i in range(self.item_tree.topLevelItemCount()):
            item = self.item_tree.topLevelItem(i)
            path = item.data(0, _ROLE_PATH)
            
            existing = None
            for d in self._data.get(cat_name, []):
                if d['path'] == path:
                    existing = d
                    break
                    
            note_widget = self.item_tree.itemWidget(item, 1)
            note_text = note_widget.get_note() if note_widget else ""

            if existing:
                existing['note'] = note_text
                new_items.append(existing)
            else:
                new_items.append({
                    'path': path,
                    'orig_cat': None,
                    'is_new': True,
                    'note': note_text
                })

        self._data[cat_name] = new_items

    def _load_category_items(self, cat_name):
        self.item_tree.clear()
        if cat_name not in self._data:
            return

        self.item_tree.current_category = cat_name
        for d in self._data[cat_name]:
            self._add_variant_item(d['path'], d['orig_cat'], d['is_new'], d)

        self._update_change_indicators()

    def _add_variant_item(self, path, orig_cat, is_new, existing_dict=None):
        file_name = Path(path).name
        variant_item = QTreeWidgetItem(self.item_tree, [file_name, "", ""])
        variant_item.setData(0, _ROLE_PATH, path)
        variant_item.setData(0, _ROLE_ORIG_CAT, orig_cat)
        variant_item.setData(0, _ROLE_IS_NEW, is_new)
        variant_item.setIcon(0, self._make_thumbnail_icon(path))
        variant_item.setSizeHint(0, QSize(THUMB_W, THUMB_H + 8))
        variant_item.setSizeHint(1, QSize(150, THUMB_H + 8))
        variant_item.setSizeHint(2, QSize(40, THUMB_H + 8))
        variant_item.setFlags(variant_item.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
        
        note_text = existing_dict.get('note', '') if existing_dict else ''
        note_widget = NoteWidget(note_text)
        self.item_tree.setItemWidget(variant_item, 1, note_widget)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(_STYLE_REMOVE)
        del_btn.clicked.connect(lambda _, i=variant_item, p=path: self._toggle_removal_or_cancel(i, p))

        btn_container = QWidget()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_layout.addWidget(del_btn)
        self.item_tree.setItemWidget(variant_item, 2, btn_container)

    def _toggle_removal_or_cancel(self, item, path):
        if item.data(0, _ROLE_IS_NEW):
            for cat, items in self._data.items():
                self._data[cat] = [d for d in items if d['path'] != path]
            index = self.item_tree.indexOfTopLevelItem(item)
            if index >= 0:
                self.item_tree.takeTopLevelItem(index)
        else:
            if path in self._pending_removal:
                self._pending_removal.discard(path)
            else:
                self._pending_removal.add(path)
            self._update_item_visuals(item)

    # ---------------------------------------------------------------- adding

    def _on_files_dropped(self, file_paths, cat_name):
        valid = [p for p in file_paths if Path(p).suffix.lower() in _MEDIA_EXTS]
        if not valid: return

        target_cat = cat_name if cat_name else self._current_cat
        if not target_cat:
            target_cat = self._ask_category()

        if target_cat:
            self._add_pending_files(valid, target_cat)

    def _pick_files(self):
        default_dir = str(self.chapter_dir) if self.chapter_dir else ""
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select Images/Videos", default_dir, _MEDIA_FILTER)
        if not file_paths: return

        target_cat = self._current_cat if self._current_cat else self._ask_category()
        if target_cat:
            self._add_pending_files(file_paths, target_cat)

    def _ask_category(self):
        cats = list(self._data.keys())
        if not cats: cats = ["Main"]
        name, ok = QInputDialog.getItem(self, "Select Category", "Add to category:", cats, 0, True)
        if not ok or not name.strip(): return None
        new_cat_raw = name.strip()
        new_cat = new_cat_raw.lower() if new_cat_raw.lower() != "main" else "Main"
        
        for existing in cats:
            if existing.lower() == new_cat.lower():
                return existing
                
        if new_cat not in self._data:
            self._data[new_cat] = []
            self.cat_list.addItem(new_cat)
        return new_cat

    def _add_pending_files(self, file_paths, cat_name):
        if cat_name not in self._data:
            self._data[cat_name] = []
            self.cat_list.addItem(cat_name)

        for src_path in sorted(file_paths, key=lambda p: natural_sort_key(Path(p).name)):
            if self._is_path_added(src_path):
                continue

            new_item = {
                'path': src_path,
                'orig_cat': None,
                'is_new': True,
                'note': ''
            }
            if cat_name == self._current_cat:
                self._add_variant_item(src_path, None, True, new_item)
            else:
                self._data[cat_name].append(new_item)

    # ------------------------------------------------------------- moves

    def _on_items_moved_to_category(self, target_cat, paths):
        if not self._current_cat or target_cat == self._current_cat:
            return

        self._save_current_category_order(self._current_cat)

        path_set = set(paths)
        moved_items = []
        new_current = []
        for d in self._data[self._current_cat]:
            if d['path'] in path_set:
                moved_items.append(d)
            else:
                new_current.append(d)

        self._data[self._current_cat] = new_current
        self._data[target_cat].extend(moved_items)

        self._load_category_items(self._current_cat)

    # ---------------------------------------------------------- visual updates

    def _update_item_visuals(self, item):
        path = item.data(0, _ROLE_PATH)
        is_new = item.data(0, _ROLE_IS_NEW)
        orig_cat = item.data(0, _ROLE_ORIG_CAT)

        font = item.font(0)
        btn_container = self.item_tree.itemWidget(item, 2)
        btn = btn_container.findChild(QPushButton) if btn_container else None

        if is_new:
            item.setForeground(0, QBrush(QColor("#4daa70")))
            item.setToolTip(0, f"New — will be added from:\n{path}")
            if btn:
                btn.setText("✕")
                btn.setToolTip("Cancel addition")
                btn.setStyleSheet(_STYLE_REMOVE)
            return

        is_pending = path in self._pending_removal
        is_moved = orig_cat and self._current_cat != orig_cat

        if is_pending:
            font.setStrikeOut(True)
            item.setForeground(0, QBrush(QColor("#888888")))
            item.setToolTip(0, "Will be removed from this category")
            if btn:
                btn.setText("↩")
                btn.setToolTip("Undo removal")
                btn.setStyleSheet(_STYLE_UNDO)
        elif is_moved:
            font.setStrikeOut(False)
            item.setForeground(0, QBrush(QColor("#f0a030")))
            item.setToolTip(0, f"Moved from: {orig_cat}")
            if btn:
                btn.setText("✕")
                btn.setToolTip("Mark for removal")
                btn.setStyleSheet(_STYLE_REMOVE)
        else:
            font.setStrikeOut(False)
            item.setForeground(0, QBrush())
            item.setToolTip(0, "")
            if btn:
                btn.setText("✕")
                btn.setToolTip("Mark for removal")
                btn.setStyleSheet(_STYLE_REMOVE)

        item.setFont(0, font)

    def _update_change_indicators(self):
        for i in range(self.item_tree.topLevelItemCount()):
            item = self.item_tree.topLevelItem(i)
            path = item.data(0, _ROLE_PATH)

            if self.item_tree.itemWidget(item, 1) is None:
                note_text = item.data(0, _ROLE_NOTE) or ''
                self.item_tree.setItemWidget(item, 1, NoteWidget(note_text))

            if self.item_tree.itemWidget(item, 2) is None:
                del_btn = QPushButton("✕")
                del_btn.setFixedSize(24, 24)
                del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                del_btn.setStyleSheet(_STYLE_REMOVE)
                del_btn.clicked.connect(lambda _, it=item, p=path: self._toggle_removal_or_cancel(it, p))
                btn_container = QWidget()
                btn_layout = QHBoxLayout(btn_container)
                btn_layout.setContentsMargins(0, 0, 0, 0)
                btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                btn_layout.addWidget(del_btn)
                self.item_tree.setItemWidget(item, 2, btn_container)

            self._update_item_visuals(item)

    # --------------------------------------------------------- category actions

    def _add_category(self):
        name, ok = QInputDialog.getText(self, "New Category", "Category Name:")
        if ok and name.strip():
            cat_name = name.strip()
            for existing in self._data.keys():
                if existing.lower() == cat_name.lower():
                    QMessageBox.warning(self, "Duplicate", f"Category '{cat_name}' already exists.")
                    return
            self._data[cat_name] = []
            self.cat_list.addItem(cat_name)
            items = self.cat_list.findItems(cat_name, Qt.MatchFlag.MatchExactly)
            if items:
                self.cat_list.setCurrentItem(items[0])

    def _on_cat_double_clicked(self, item):
        old_name = item.text()
        new_name, ok = QInputDialog.getText(self, "Rename Category", "New Category Name:", text=old_name)
        if ok and new_name.strip():
            new_name = new_name.strip()
            if new_name == old_name: return
            for existing in self._data.keys():
                if existing.lower() == new_name.lower() and existing != old_name:
                    QMessageBox.warning(self, "Error", "Category already exists.")
                    return

            self._save_current_category_order(self._current_cat)

            renamed_items = self._data.pop(old_name)
            for d in renamed_items:
                if d.get('orig_cat') == old_name:
                    d['orig_cat'] = new_name
            self._data[new_name] = renamed_items
            item.setText(new_name)

            if self._current_cat == old_name:
                self._current_cat = new_name
                self.item_tree.current_category = new_name
                for i in range(self.item_tree.topLevelItemCount()):
                    tree_item = self.item_tree.topLevelItem(i)
                    if tree_item.data(0, _ROLE_ORIG_CAT) == old_name:
                        tree_item.setData(0, _ROLE_ORIG_CAT, new_name)

            self._update_change_indicators()

    # ------------------------------------------------------------------ apply

    def _apply_changes(self):
        self._save_current_category_order(self._current_cat)

        removals = sorted(self._pending_removal, key=lambda p: Path(p).name)
        new_structure = {}
        additions = []
        moves = []
        new_notes_mapping = {}

        for cat_name, items in self._data.items():
            paths = []
            for d in items:
                path = d['path']
                if 'note' in d and d['note'].strip():
                    new_notes_mapping[path] = d['note'].strip()
                else:
                    new_notes_mapping[path] = ""
                    
                if d['is_new']:
                    additions.append((path, cat_name))
                elif path not in self._pending_removal:
                    paths.append(path)
                    if d['orig_cat'] and d['orig_cat'] != cat_name:
                        moves.append((Path(path).name, d['orig_cat'], cat_name))
            if paths:
                new_structure[cat_name] = paths

        notes_changed = any(
            new_notes_mapping.get(d['path'], '') != d.get('_orig_note', '')
            for items in self._data.values() for d in items
        )
        order_changed = any(
            [d['path'] for d in self._data.get(cat, [])] != self._orig_order.get(cat, [])
            for cat in self._data
        )
        if not removals and not moves and not additions and not notes_changed and not order_changed:
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

        from src.ui.page_utils import apply_alt_edits, process_add_alts

        success_edit = apply_alt_edits(self.model, self.page_obj, new_structure, new_notes=new_notes_mapping)
        if not success_edit:
            QMessageBox.critical(self, "Error", "Failed to apply changes.")
            return

        if additions:
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
                    on_reload=None,
                    on_variants_updated=None,
                    category=cat,
                    new_notes=new_notes_mapping
                )

        self.accept()
