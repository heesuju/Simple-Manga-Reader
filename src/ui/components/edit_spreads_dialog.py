import random
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget,
    QPushButton, QLabel, QCheckBox, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QThreadPool, QTimer
from PyQt6.QtGui import QPixmap

from src.core.alt_manager import AltManager
from src.workers.thumbnail_worker import ThumbnailWorker
from src.utils.img_utils import load_thumbnail_from_path, load_thumbnail_from_virtual_path

_THUMB_W = 100
_THUMB_H = 140
_ROWNR_W = 24


class _PageItem(QWidget):
    def __init__(self, index: int, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.index = index
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)

        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(_THUMB_W, _THUMB_H)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet("background: #2a2a2a; border: 1px solid #444;")
        layout.addWidget(self.thumb_label)

        num_label = QLabel(str(index + 1))
        num_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num_label.setFixedWidth(_THUMB_W)
        layout.addWidget(num_label)

        self.spread_check = QCheckBox("Spread")
        self.spread_check.setChecked(page.is_spread)
        layout.addWidget(self.spread_check, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_thumbnail(self, qimage):
        if qimage and not qimage.isNull():
            pixmap = QPixmap.fromImage(qimage).scaled(
                _THUMB_W, _THUMB_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.thumb_label.setPixmap(pixmap)

    @property
    def is_spread_checked(self) -> bool:
        return self.spread_check.isChecked()


class _EmptySlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # Match _PageItem's fixed width; height matches via the layout
        self.setFixedWidth(_THUMB_W + 4)
        self.setStyleSheet(
            "background: transparent; border: 1px dashed #333; border-radius: 2px;"
        )


def _load_pages(chapter: dict, series_path: str) -> tuple:
    from src.workers.view_workers import ChapterLoaderWorker

    chapter_path = str(chapter['path'])
    chapter_name = Path(chapter_path.split('|')[0]).stem if '|' in chapter_path else Path(chapter_path).name

    sort_mode = AltManager.get_chapter_sort(series_path, chapter_name)
    worker = ChapterLoaderWorker(
        manga_dir=chapter_path, series_path=series_path,
        start_from_end=False, sort_mode=sort_mode
    )
    image_list = worker._get_image_list()
    image_list = worker._sort_image_list(image_list)

    alt_config = AltManager.load_alts(series_path)
    pages = AltManager.group_images(image_list, alt_config.get(chapter_name, {}))
    return pages, chapter_name


class EditSpreadsDialog(QDialog):
    def __init__(self, parent, chapter: dict, series_path: str):
        super().__init__(parent)
        self.series_path = series_path
        self.items: list = []
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(4)
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(30)
        self._rebuild_timer.timeout.connect(self._rebuild_pairs_view)

        self.pages, self.chapter_name = _load_pages(chapter, series_path)
        self.setWindowTitle(f"Edit Spreads — {self.chapter_name}")

        # Width: row-nr + 2 cells + scrollbar clearance
        cell_w = _THUMB_W + 4
        win_w = _ROWNR_W + 2 * cell_w + 22
        self.setFixedWidth(win_w)
        self.resize(win_w, 600)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 6)
        root.setSpacing(0)

        self._scroll = QScrollArea()
        scroll = self._scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._pairs_layout = QVBoxLayout(self._container)
        self._pairs_layout.setContentsMargins(0, 0, 0, 0)
        self._pairs_layout.setSpacing(0)
        self._pairs_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._container)
        root.addWidget(scroll, 1)

        # Bottom bar
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 0)
        auto_btn = QPushButton("Auto-detect")
        auto_btn.clicked.connect(self._auto_detect)
        bar.addWidget(auto_btn)
        bar.addStretch()
        apply_btn = QPushButton("Apply")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._apply_and_accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        bar.addWidget(apply_btn)
        bar.addWidget(cancel_btn)
        root.addLayout(bar)

        for i, page in enumerate(self.pages):
            item = _PageItem(i, page, self)
            item.hide()
            item.spread_check.stateChanged.connect(lambda _: self._rebuild_timer.start())
            self.items.append(item)

        self._rebuild_pairs_view()
        self._start_thumbnail_loading()

    # ------------------------------------------------------------------
    def _compute_pairs(self) -> list:
        """
        Returns list of (left, right) where each is a _PageItem or None.
        Spread   → (item, None)  item.is_spread_checked=True
        Pair     → (item, item)
        Orphan   → (None, item)  matches _build_double_layout placeholder behaviour
        """
        pairs = []
        buffer = None
        for item in self.items:
            if item.is_spread_checked:
                if buffer is not None:
                    pairs.append((None, buffer))    # flush orphan to right slot
                    buffer = None
                pairs.append((item, None))          # spread, full row
            else:
                if buffer is not None:
                    pairs.append((buffer, item))
                    buffer = None
                else:
                    buffer = item
        if buffer is not None:
            pairs.append((None, buffer))            # trailing orphan
        return pairs

    def _rebuild_pairs_view(self):
        vbar = self._scroll.verticalScrollBar()
        saved_pos = vbar.value()
        self._container.setUpdatesEnabled(False)
        try:
            self._do_rebuild()
        finally:
            self._container.setUpdatesEnabled(True)
            vbar.setValue(saved_pos)

    def _do_rebuild(self):
        # Detach all page items so they survive row deletion
        for item in self.items:
            item.setParent(self)
            item.hide()

        # Remove all existing rows
        while self._pairs_layout.count():
            w = self._pairs_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        for row_idx, (left, right) in enumerate(self._compute_pairs()):
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(0)

            # Row number label
            nr = QLabel(str(row_idx + 1))
            nr.setFixedWidth(_ROWNR_W)
            nr.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            nr.setStyleSheet("color: #555; font-size: 10px; padding-right: 3px;")
            hl.addWidget(nr)

            # Always exactly two cells — fill with _EmptySlot when no page
            for cell in (left, right):
                if cell is not None:
                    cell.setParent(row)
                    cell.show()
                    hl.addWidget(cell)
                else:
                    hl.addWidget(_EmptySlot(row))

            self._pairs_layout.addWidget(row)

    # ------------------------------------------------------------------
    def _start_thumbnail_loading(self):
        for i, page in enumerate(self.pages):
            def _load(path):
                if '|' in path:
                    return load_thumbnail_from_virtual_path(path, _THUMB_W, _THUMB_H)
                return load_thumbnail_from_path(path, _THUMB_W, _THUMB_H)

            worker = ThumbnailWorker(i, page.path, _load)
            ci = i
            worker.signals.finished.connect(
                lambda __, img, _i=ci: self.items[_i].set_thumbnail(img) if _i < len(self.items) else None
            )
            self._pool.start(worker)

    def _auto_detect(self):
        from PyQt6.QtGui import QImageReader

        candidates = [p for p in self.pages if '|' not in p.path and not p.is_spread_explicit]
        if not candidates:
            return

        sample = random.sample(candidates, min(5, len(candidates)))
        ratios = []
        for page in sample:
            reader = QImageReader(page.path)
            size = reader.size()
            if size.isValid() and size.height() > 0:
                ratios.append(size.width() / size.height())

        if not ratios:
            return

        median_ratio = sorted(ratios)[len(ratios) // 2]
        if median_ratio == 0 or not all(abs(r - median_ratio) / median_ratio < 0.1 for r in ratios):
            return

        threshold = median_ratio * 1.5
        for item in self.items:
            if item.page.is_spread_explicit or '|' in item.page.path:
                continue
            reader = QImageReader(item.page.path)
            size = reader.size()
            if size.isValid() and size.height() > 0:
                item.spread_check.blockSignals(True)
                item.spread_check.setChecked((size.width() / size.height()) > threshold)
                item.spread_check.blockSignals(False)

        self._rebuild_pairs_view()

    def _apply_and_accept(self):
        updates = {}
        for item in self.items:
            if item.page.is_spread != item.is_spread_checked:
                updates[item.page.path] = item.is_spread_checked
        if updates:
            AltManager.save_spread_states(self.series_path, self.chapter_name, updates)
        self.accept()
