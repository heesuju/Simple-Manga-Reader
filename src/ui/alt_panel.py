import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QSizePolicy, QComboBox
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QIcon, QPixmap
from src.enums import ViewMode
from src.utils.resource_utils import resource_path
from src.utils.img_utils import load_thumbnail_from_path, load_thumbnail_from_virtual_path

THUMB_W = 120
THUMB_H = 160


class AltThumbnail(QWidget):
    """Single clickable alt thumbnail row."""
    def __init__(self, parent, variant_path, display_index, is_selected=False, on_click=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.variant_path = variant_path
        self.on_click = on_click
        self.is_selected = is_selected

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(THUMB_H + 30)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(THUMB_W, THUMB_H)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet("background: transparent;")
        layout.addWidget(self.thumb_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.name_label = QLabel(str(display_index))
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("color: white; font-size: 11px;")
        layout.addWidget(self.name_label)

        self._update_style()

    def set_pixmap(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(THUMB_W, THUMB_H, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.thumb_label.setPixmap(scaled)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self._update_style()

    def _update_style(self):
        if self.is_selected:
            self.setStyleSheet("AltThumbnail { border: 2px solid rgba(74, 134, 232, 180); }")
        else:
            self.setStyleSheet("AltThumbnail { border: 2px solid transparent; }")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.on_click:
            self.on_click()
        super().mousePressEvent(event)


class AltPanel(QWidget):
    """Vertical panel showing alt thumbnails for the current page, organized by category."""

    def __init__(self, parent=None, model=None):
        super().__init__(parent)
        self.model = model
        self.active_categories = {}  # {page_index: category_name}

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            AltPanel {
                background-color: rgba(0, 0, 0, 170);
                border: none;
            }
        """)
        self.setFixedWidth(THUMB_W + 40)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # Top row: Category dropdown + Play button
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(3)

        self.cat_combo = QComboBox()
        self.cat_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(255, 255, 255, 30);
                color: white;
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 3px;
                padding: 3px 6px;
                font-weight: bold;
                font-size: 11px;
            }
            QComboBox:hover { background-color: rgba(255, 255, 255, 60); }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { image: none; border: none; }
            QComboBox QAbstractItemView {
                background-color: rgba(30, 30, 30, 240);
                color: white;
                selection-background-color: rgba(255, 150, 50, 180);
                border: 1px solid rgba(255, 255, 255, 50);
            }
        """)
        self.cat_combo.currentIndexChanged.connect(self._on_combo_changed)
        top_row.addWidget(self.cat_combo, 1)

        self.play_icon = QIcon(resource_path("assets/icons/play.svg"))
        self.play_btn = QPushButton()
        self.play_btn.setIcon(self.play_icon)
        self.play_btn.setFixedSize(28, 28)
        self.play_btn.setCheckable(True)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 30);
                color: white;
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 60); }
            QPushButton:checked { background-color: rgba(50, 200, 255, 180); border: 1px solid rgba(50, 200, 255, 200); }
        """)
        self.play_btn.clicked.connect(self._on_play_clicked)
        top_row.addWidget(self.play_btn)

        # Revert button
        self.revert_icon = QIcon(resource_path("assets/icons/search_reset.svg"))
        self.revert_btn = QPushButton()
        self.revert_btn.setIcon(self.revert_icon)
        self.revert_btn.setFixedSize(28, 28)
        self.revert_btn.setToolTip("Revert to Original")
        self.revert_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 30);
                color: white;
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 60); }
        """)
        self.revert_btn.clicked.connect(self._on_revert_clicked)
        top_row.addWidget(self.revert_btn)

        main_layout.addLayout(top_row)

        # Scroll area for thumbnails
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setLineWidth(0)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        main_layout.addWidget(self.scroll_area, 1)

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent; border: none;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(5)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)

        self.alt_widgets = []

        # Slideshow state
        self.slideshow_states = {}
        self.speeds = [2000, 1000, 500, 250]
        self.speed_labels = ["x1", "x2", "x4", "x8"]

        self.hide()

        if self.model:
            self.model.image_loaded.connect(self._on_image_loaded)
            self.model.double_image_loaded.connect(self._on_double_image_loaded)

    def _on_image_loaded(self, path):
        self._update_panel(self.model.current_index)

    def _on_double_image_loaded(self, path1, path2):
        self._update_panel(self.model.current_index)

    def _clear_content(self):
        """Remove all thumbnail widgets."""
        for w in self.alt_widgets:
            w.deleteLater()
        self.alt_widgets.clear()

    def _update_panel(self, primary_index):
        self._clear_content()

        if not self.model or not self.model.images:
            self.hide()
            return

        idx = primary_index
        if not (0 <= idx < len(self.model.images)):
            self.hide()
            return

        page = self.model.images[idx]
        if len(page.images) <= 1:
            self.hide()
            return

        # Get categories
        categories = page.get_categorized_variants()
        cat_names = sorted(list(categories.keys()))

        if not cat_names:
            self.hide()
            return

        # Always sync active category to whichever category contains the current variant
        current_path = page.images[page.current_variant_index]
        active_cat = cat_names[0]
        for cat, paths in categories.items():
            if current_path in paths:
                active_cat = cat
                break
        self.active_categories[idx] = active_cat

        # Update combo box (block signals to avoid triggering _on_combo_changed during population)
        self.cat_combo.blockSignals(True)
        self.cat_combo.clear()
        for cat in cat_names:
            self.cat_combo.addItem(cat.upper(), cat)  # display text uppercase, data is original
        # Select active category
        for i in range(self.cat_combo.count()):
            if self.cat_combo.itemData(i) == active_cat:
                self.cat_combo.setCurrentIndex(i)
                break
        self.cat_combo.blockSignals(False)

        # Update play button state
        is_playing = idx in self.slideshow_states
        self.play_btn.setChecked(is_playing)
        if is_playing:
            state = self.slideshow_states[idx]
            self.play_btn.setText(self.speed_labels[state['speed_idx']])
            self.play_btn.setIcon(QIcon())
        else:
            self.play_btn.setText("")
            self.play_btn.setIcon(self.play_icon)

        # Build thumbnail rows for active category
        active_paths = categories.get(active_cat, [])
        for cat_v_idx, variant_path in enumerate(active_paths):
            true_v_idx = page.images.index(variant_path)
            is_selected = (not is_playing) and (true_v_idx == page.current_variant_index)

            thumb = AltThumbnail(
                self.scroll_content,
                variant_path,
                display_index=cat_v_idx + 1,
                is_selected=is_selected,
                on_click=lambda v=true_v_idx: self._on_variant_clicked(idx, v)
            )
            self.scroll_layout.addWidget(thumb)
            self.alt_widgets.append(thumb)

            # Load thumbnail async-ish (synchronous for simplicity, could be threaded)
            resolved = self._resolve_path(variant_path)
            try:
                if '|' in resolved:
                    pixmap = load_thumbnail_from_virtual_path(resolved, THUMB_W, THUMB_H)
                else:
                    pixmap = load_thumbnail_from_path(resolved, THUMB_W, THUMB_H)
                if pixmap:
                    thumb.set_pixmap(pixmap)
            except Exception:
                pass

        # Show panel
        if hasattr(self.parent(), "panels_visible"):
            if self.parent().panels_visible:
                self.show()
                if hasattr(self.parent(), '_update_alt_panel_height'):
                    QTimer.singleShot(100, self.parent()._update_alt_panel_height)
            else:
                self.hide()
        else:
            self.show()

    def _resolve_path(self, path_str):
        """Resolve relative path to absolute using model's manga_dir."""
        p = Path(path_str)
        if not p.is_absolute() and self.model:
            p = Path(self.model.manga_dir) / p
        return str(p)

    def _on_combo_changed(self, index):
        """Handle category dropdown selection change."""
        if index < 0:
            return
        category = self.cat_combo.itemData(index)
        if not category:
            return
        page_index = self.model.current_index if self.model else 0
        self.active_categories[page_index] = category
        if self.model and 0 <= page_index < len(self.model.images):
            page = self.model.images[page_index]
            categories = page.get_categorized_variants()
            if category in categories and categories[category]:
                first_path = categories[category][0]
                try:
                    first_idx = page.images.index(first_path)
                    self.model.change_variant(page_index, first_idx)
                    return
                except ValueError:
                    pass
        self._update_panel(self.model.current_index)

    def _on_variant_clicked(self, page_index, variant_index):
        if self.model:
            if page_index in self.slideshow_states:
                self.slideshow_states[page_index]['timer'].stop()
                del self.slideshow_states[page_index]
            self.model.change_variant(page_index, variant_index)

    def _on_play_clicked(self):
        if not self.model or not self.model.images:
            return
        idx = self.model.current_index
        if idx not in self.slideshow_states:
            timer = QTimer(self)
            timer.timeout.connect(lambda: self._advance_variant(idx))
            timer.start(self.speeds[0])
            self.slideshow_states[idx] = {'speed_idx': 0, 'timer': timer}
        else:
            state = self.slideshow_states[idx]
            new_speed_idx = (state['speed_idx'] + 1) % len(self.speeds)
            state['speed_idx'] = new_speed_idx
            state['timer'].setInterval(self.speeds[new_speed_idx])
        self._update_panel(self.model.current_index)

    def _on_revert_clicked(self):
        if self.model:
            page_index = self.model.current_index
            if 0 <= page_index < len(self.model.images):
                # Variant index 0 is always the original image
                self.model.change_variant(page_index, 0)

    def _advance_variant(self, page_index):
        if not self.model or not (0 <= page_index < len(self.model.images)):
            return
        page = self.model.images[page_index]
        new_variant_index = (page.current_variant_index + 1) % len(page.images)
        self.model.change_variant(page_index, new_variant_index)

