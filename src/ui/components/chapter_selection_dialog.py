from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QLabel, QCheckBox
)
from PyQt6.QtCore import Qt
from pathlib import Path


def _split_virtual(path: str):
    if '|' in path:
        a, b = path.split('|', 1)
        return a, b.replace('\\', '/').strip('/')
    return None, path


def _is_descendant(parent_path: str, child_path: str) -> bool:
    """True if child_path lives inside parent_path. Handles both filesystem and virtual archive paths."""
    if parent_path == child_path:
        return False

    p_arc, p_inner = _split_virtual(parent_path)
    c_arc, c_inner = _split_virtual(child_path)

    if p_arc != c_arc:
        return False

    if p_arc is not None:
        # Both inside same archive — string-prefix check on internal paths.
        if not p_inner:
            return bool(c_inner)
        return c_inner.startswith(p_inner + '/')

    try:
        Path(c_inner).relative_to(Path(p_inner))
        return True
    except ValueError:
        return False


def flatten_chapters(chapters: list, series_path: str = None) -> list:
    """Collapse chapters whose path is inside another chapter's path.

    Sorted by path, a parent always appears just before its descendants, so a
    single sweep can absorb them. `series_path`, if given, is excluded from
    being an absorber — otherwise stray media at the series root would swallow
    every real chapter into itself.
    """
    series_norm = str(Path(series_path)) if series_path else None
    result = []
    sorted_it = sorted(chapters, key=lambda c: Path(c.get('path') or '').parts)
    for ch in sorted_it:
        path = ch.get('path', '')
        if not path:
            continue
        if (
            result
            and _is_descendant(result[-1]['path'], path)
            and (series_norm is None or str(Path(result[-1]['path'])) != series_norm)
        ):
            extras = result[-1].setdefault('extra_paths', [])
            if path not in extras:
                extras.append(path)
        else:
            result.append(dict(ch))
    return result


class ChapterSelectionDialog(QDialog):
    def __init__(self, chapters, parent=None, series_path: str = None):
        super().__init__(parent)
        self.setWindowTitle("Select Chapters")
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)

        self.series_path = series_path
        raw = list(chapters)
        # If the scan produced both the series root and real subfolder chapters,
        # the root is noise from stray media — drop it so it doesn't dominate the list.
        if series_path and len(raw) > 1:
            series_norm = str(Path(series_path))
            raw = [ch for ch in raw if str(Path(ch.get('path', ''))) != series_norm]

        self._raw_chapters = raw
        self._current_chapters = list(raw)
        self.selected_chapters = []
        self._checked_paths = {ch.get('path') for ch in self._raw_chapters if ch.get('path')}

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.info_label = QLabel()
        layout.addWidget(self.info_label)

        self.flatten_checkbox = QCheckBox("Treat subfolders as part of their parent chapter")
        self.flatten_checkbox.toggled.connect(self._on_flatten_toggled)
        layout.addWidget(self.flatten_checkbox)

        btn_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self.deselect_all)

        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.list_widget = QListWidget()
        self.list_widget.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list_widget)

        action_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        self.add_btn = QPushButton("Add Selected")
        self.add_btn.clicked.connect(self.accept_selection)

        action_layout.addStretch()
        action_layout.addWidget(self.cancel_btn)
        action_layout.addWidget(self.add_btn)
        layout.addLayout(action_layout)

        self._rebuild_list()

    def _rebuild_list(self):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for chapter in self._current_chapters:
            item = QListWidgetItem()
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = chapter.get('path') in self._checked_paths
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            label = chapter['name']
            extras = chapter.get('extra_paths') or []
            if extras:
                label = f"{label}  (+{len(extras)} subfolder{'s' if len(extras) != 1 else ''})"
            item.setText(label)
            item.setData(Qt.ItemDataRole.UserRole, chapter)
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)
        self.info_label.setText(
            f"Found {len(self._current_chapters)} chapters. Select chapters to import:"
        )

    def _on_flatten_toggled(self, checked: bool):
        if checked:
            self._current_chapters = flatten_chapters(self._raw_chapters, self.series_path)
        else:
            self._current_chapters = list(self._raw_chapters)
        # Drop check-marks for paths that no longer exist in the visible list.
        visible_paths = {ch.get('path') for ch in self._current_chapters}
        self._checked_paths &= visible_paths
        self._rebuild_list()

    def _on_item_changed(self, item: QListWidgetItem):
        chapter = item.data(Qt.ItemDataRole.UserRole)
        path = chapter.get('path') if chapter else None
        if not path:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._checked_paths.add(path)
        else:
            self._checked_paths.discard(path)

    def select_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Checked)

    def deselect_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)

    def accept_selection(self):
        self.selected_chapters = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                self.selected_chapters.append(item.data(Qt.ItemDataRole.UserRole))
        self.accept()

    def get_selected_chapters(self):
        return self.selected_chapters
