from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QScrollArea, 
    QHBoxLayout, QGridLayout, QStackedWidget
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QThreadPool

from src.ui.thumbnail_widget import ThumbnailWidget
from src.core.item_loader import ItemLoader
from src.ui.styles import FLAT_BUTTON_STYLE

class GroupCard(QWidget):
    clicked = pyqtSignal(object)

    def __init__(self, group, parent=None):
        super().__init__(parent)
        self.group = group
        self.setFixedSize(160, 200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 10, 5, 5)
        layout.setSpacing(4)

        self.card_widget = QWidget()
        self.card_widget.setFixedSize(150, 150)
        self._update_style(False)

        card_layout = QVBoxLayout(self.card_widget)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.addStretch()
        count = group.get('count', 0)
        count_label = QLabel(f"{count} series" if count != 1 else "1 series")
        count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_label.setStyleSheet("color: rgba(200, 200, 200, 200); font-size: 12px; background: transparent;")
        card_layout.addWidget(count_label)
        card_layout.addStretch()

        self.name_label = QLabel(group['name'])
        self.name_label.setWordWrap(True)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setMaximumHeight(40)

        layout.addWidget(self.card_widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.name_label)

    def _update_style(self, hover):
        bg = "rgba(60, 80, 130, 220)" if hover else "rgba(40, 55, 100, 200)"
        self.card_widget.setStyleSheet(
            f"QWidget {{ border-radius: 8px; background-color: {bg}; }}"
        )

    def enterEvent(self, event):
        self._update_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._update_style(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.group)
        super().mousePressEvent(event)


class GroupView(QWidget):
    series_selected = pyqtSignal(object)
    remove_requested = pyqtSignal(object)
    rescan_requested = pyqtSignal(object)
    clear_cache_requested = pyqtSignal(object)

    def __init__(self, library_manager, parent=None):
        super().__init__(parent)
        self.library_manager = library_manager
        self.current_field = None
        self.current_group = None
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(3)
        self._active_loaders = []
        self.loading_generation = 0
        self.received_items = {}
        self.next_item_to_display = 0
        self.total_items_to_load = 0
        self.series_items = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header shown when drilled into a group
        self.header_widget = QWidget()
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(5, 2, 5, 2)
        self.back_btn = QPushButton("< Back")
        self.back_btn.setStyleSheet(FLAT_BUTTON_STYLE)
        self.back_btn.clicked.connect(self._back_to_groups)
        self.header_label = QLabel()
        self.header_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-left: 10px;")
        header_layout.addWidget(self.back_btn)
        header_layout.addWidget(self.header_label)
        header_layout.addStretch()
        self.header_widget.hide()
        main_layout.addWidget(self.header_widget)

        self.sub_stack = QStackedWidget()
        main_layout.addWidget(self.sub_stack)

        # Page 0: group cards
        self.group_scroll = QScrollArea()
        self.group_scroll.setWidgetResizable(True)
        self.group_scroll.setStyleSheet("border: none;")
        self.group_scroll_content = QWidget()
        group_content_layout = QVBoxLayout(self.group_scroll_content)
        group_content_layout.setContentsMargins(0, 0, 0, 0)
        group_content_layout.setSpacing(0)
        self.group_grid = QGridLayout()
        self.group_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.group_grid.setContentsMargins(0, 0, 0, 0)
        self.group_grid.setSpacing(0)
        group_content_layout.addLayout(self.group_grid)
        group_content_layout.addStretch(1)
        self.group_scroll.setWidget(self.group_scroll_content)
        self.sub_stack.addWidget(self.group_scroll)

        # Page 1: series thumbnails
        self.series_scroll = QScrollArea()
        self.series_scroll.setWidgetResizable(True)
        self.series_scroll.setStyleSheet("border: none;")
        self.series_scroll_content = QWidget()
        series_content_layout = QVBoxLayout(self.series_scroll_content)
        series_content_layout.setContentsMargins(0, 0, 0, 0)
        series_content_layout.setSpacing(0)
        self.series_grid = QGridLayout()
        self.series_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.series_grid.setContentsMargins(0, 0, 0, 0)
        self.series_grid.setSpacing(0)
        series_content_layout.addLayout(self.series_grid)
        series_content_layout.addStretch(1)
        self.series_scroll.setWidget(self.series_scroll_content)
        self.sub_stack.addWidget(self.series_scroll)

    def set_field(self, field):
        self.current_field = field
        self.current_group = None
        self.header_widget.hide()
        self.sub_stack.setCurrentIndex(0)
        self._load_group_grid()

    def _load_group_grid(self):
        while self.group_grid.count():
            item = self.group_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        groups = self.library_manager.get_field_values_with_counts(self.current_field)
        untagged = self.library_manager.get_series_without_field(self.current_field)

        num_cols = max(1, self.group_scroll.viewport().width() // 160)
        idx = 0

        for g in groups:
            card = GroupCard(g)
            card.clicked.connect(self._show_group)
            row, col = divmod(idx, num_cols)
            self.group_grid.addWidget(card, row, col)
            idx += 1

        if untagged:
            untagged_data = {'name': 'Untagged', 'count': len(untagged), '_series': untagged}
            card = GroupCard(untagged_data)
            card.clicked.connect(self._show_group)
            row, col = divmod(idx, num_cols)
            self.group_grid.addWidget(card, row, col)

    def _show_group(self, group):
        self.current_group = group
        count = group.get('count', 0)
        self.header_label.setText(f"{group['name']}  ({count})")
        self.header_widget.show()
        self.sub_stack.setCurrentIndex(1)

        if '_series' in group:
            series_list = group['_series']
        else:
            series_list = self.library_manager.get_series_by_field_value(
                self.current_field, group['name']
            )
        self._load_series(series_list)

    def _load_series(self, series_list):
        while self.series_grid.count():
            item = self.series_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for loader in self._active_loaders:
            if hasattr(loader, 'abort'):
                loader.abort()
        self._active_loaders.clear()

        self.loading_generation += 1
        self.total_items_to_load = len(series_list)
        self.received_items.clear()
        self.next_item_to_display = 0
        self.series_items.clear()

        if not series_list:
            return

        loader = ItemLoader(series_list, self.loading_generation, item_type='series')
        loader.signals.item_loaded.connect(self._on_item_loaded)
        loader.signals.item_invalid.connect(self._on_item_invalid)
        loader.signals.loading_finished.connect(
            lambda: self._active_loaders.remove(loader) if loader in self._active_loaders else None
        )
        self._active_loaders.append(loader)
        self.threadpool.start(loader)

    def _on_item_loaded(self, qimg, series, idx, generation, item_type):
        if generation != self.loading_generation:
            return
        self.received_items[idx] = (qimg, series, item_type)
        self._display_pending()

    def _on_item_invalid(self, idx, generation):
        if generation != self.loading_generation:
            return
        self.received_items[idx] = None
        self._display_pending()

    def _display_pending(self):
        num_cols = max(1, self.series_scroll.viewport().width() // 160)

        while self.next_item_to_display < self.total_items_to_load and \
              self.next_item_to_display in self.received_items:

            item_data = self.received_items.pop(self.next_item_to_display)

            if item_data is not None:
                qimg, series, item_type = item_data
                widget = ThumbnailWidget(series, self.library_manager)

                series_path = Path(series['path'])
                if not series_path.exists():
                    widget.set_as_missing()
                else:
                    if qimg and not qimg.isNull():
                        pixmap = QPixmap.fromImage(qimg)
                        widget.set_pixmap(pixmap)
                    widget.clicked.connect(self.series_selected)

                widget.remove_requested.connect(self.remove_requested)
                widget.rescan_requested.connect(self.rescan_requested)
                widget.clear_cache_requested.connect(self.clear_cache_requested)
                self.series_items.append(widget)

                row = self.next_item_to_display // num_cols
                col = self.next_item_to_display % num_cols
                self.series_grid.addWidget(widget, row, col)

            self.next_item_to_display += 1

    def refresh(self):
        """Re-query and redisplay the current view after external data changes."""
        if not self.current_field:
            return
        if self.sub_stack.currentIndex() == 0:
            self._load_group_grid()
        else:
            if self.current_group and '_series' not in self.current_group:
                series_list = self.library_manager.get_series_by_field_value(
                    self.current_field, self.current_group['name']
                )
            else:
                series_list = self.library_manager.get_series_without_field(self.current_field)
            if series_list:
                count = len(series_list)
                self.header_label.setText(f"{self.current_group['name']}  ({count})")
                self._load_series(series_list)
            else:
                self._back_to_groups()

    def _back_to_groups(self):
        self.current_group = None
        self.header_widget.hide()
        self.sub_stack.setCurrentIndex(0)
        self._load_group_grid()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.sub_stack.currentIndex() == 0:
            self._relayout_groups()
        else:
            self._relayout_series()

    def _relayout_groups(self):
        cards = []
        while self.group_grid.count():
            item = self.group_grid.takeAt(0)
            if item.widget():
                cards.append(item.widget())
                item.widget().setParent(None)
        num_cols = max(1, self.group_scroll.viewport().width() // 160)
        for i, card in enumerate(cards):
            row, col = divmod(i, num_cols)
            self.group_grid.addWidget(card, row, col)

    def _relayout_series(self):
        if not self.series_items:
            return
        while self.series_grid.count():
            item = self.series_grid.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        num_cols = max(1, self.series_scroll.viewport().width() // 160)
        for i, widget in enumerate(self.series_items):
            row, col = divmod(i, num_cols)
            self.series_grid.addWidget(widget, row, col)

