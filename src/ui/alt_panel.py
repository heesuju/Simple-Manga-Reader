import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QSizePolicy, QMenu,
    QDialog, QPlainTextEdit, QApplication, QLayout
)
from PyQt6.QtCore import Qt, QTimer, QSize, QPoint, QRect
from src.ui.styles import SCROLL_AREA_TRANSPARENT
from PyQt6.QtGui import QIcon, QPixmap, QImage
from src.enums import ViewMode
from src.ui.components.grip_strip import GripStrip, GRIP_W
from src.utils.resource_utils import resource_path
from src.utils.img_utils import load_thumbnail_from_path, load_thumbnail_from_virtual_path
from src.utils.str_utils import natural_sort_key
from src.workers.thumbnail_worker import ThumbnailWorker
from src.core.alt_manager import AltManager

THUMB_W = 80
THUMB_H = 100
PANEL_W = THUMB_W + 40


class FlowLayout(QLayout):
    """Layout that arranges widgets left-to-right, wrapping to the next row."""
    def __init__(self, parent=None, h_spacing=3, v_spacing=3):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def clear_widgets(self):
        while self._items:
            item = self._items.pop()
            if item.widget():
                item.widget().deleteLater()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, apply):
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effective.x()
        y = effective.y()
        row_h = 0

        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            if x + w > effective.right() + 1 and x > effective.x():
                x = effective.x()
                y += row_h + self._v_spacing
                row_h = 0
            if apply:
                item.setGeometry(QRect(x, y, w, h))
            row_h = max(row_h, h)
            x += w + self._h_spacing

        return y + row_h - rect.y() + m.bottom()


class AltThumbnail(QWidget):
    """Single clickable alt thumbnail row."""
    def __init__(self, parent, variant_path, display_index, is_selected=False, on_click=None, on_right_click=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.variant_path = variant_path
        self.on_click = on_click
        self.on_right_click = on_right_click
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

        is_orig = str(display_index) == "ORIG"
        self.name_label = QLabel(str(display_index))
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if is_orig:
            self.name_label.setStyleSheet("color: rgba(255, 180, 80, 200); font-size: 10px; font-weight: bold;")
        else:
            self.name_label.setStyleSheet("color: rgba(255, 255, 255, 160); font-size: 11px;")
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

    def contextMenuEvent(self, event):
        if self.on_right_click:
            self.on_right_click(event.globalPos())
        else:
            super().contextMenuEvent(event)


class _AltNotesDialog(QDialog):
    def __init__(self, parent, current_note=''):
        super().__init__(parent)
        self.setWindowTitle("Alt Notes")
        self.setMinimumWidth(420)
        self.setMinimumHeight(220)

        layout = QVBoxLayout(self)

        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setPlainText(current_note)
        self.text_edit.setPlaceholderText("Enter notes, prompt, model, etc...")
        layout.addWidget(self.text_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        save_btn = QPushButton("Save")
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def get_note(self):
        return self.text_edit.toPlainText().strip()


class AltPanel(QWidget):
    """Vertical panel showing alt thumbnails for the current page, organized by category."""

    def __init__(self, parent=None, model=None, thread_pool=None):
        super().__init__(parent)
        self.model = model
        self.thread_pool = thread_pool
        self.active_categories = {}  # {page_index: category_name}

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            AltPanel {
                background-color: rgba(0, 0, 0, 170);
                border: none;
            }
        """)
        self._collapsed = True
        self.setFixedWidth(GRIP_W)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        # Outer layout: content on the left, grip strip on the right
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._content_widget = QWidget(self)
        self._content_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._content_widget.setStyleSheet("background: transparent;")
        self._content_widget.hide()
        outer_layout.addWidget(self._content_widget)

        self._grip = GripStrip(self._toggle_collapse, self)
        outer_layout.addWidget(self._grip)

        main_layout = QVBoxLayout(self._content_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(4)

        # Scroll area for thumbnails (top — primary content)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setLineWidth(0)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(SCROLL_AREA_TRANSPARENT)
        main_layout.addWidget(self.scroll_area, 1)

        # Category chip buttons (bottom — wrapping flow)
        self._cat_chip_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 20);
                color: rgba(255, 255, 255, 160);
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 8px;
                font-size: 9px;
                font-weight: bold;
                padding: 2px 6px;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 50); }
        """
        self._cat_chip_active_style = """
            QPushButton {
                background-color: rgba(255, 150, 50, 180);
                color: white;
                border: 1px solid rgba(255, 150, 50, 200);
                border-radius: 8px;
                font-size: 9px;
                font-weight: bold;
                padding: 2px 6px;
            }
            QPushButton:hover { background-color: rgba(255, 170, 80, 200); }
        """

        self._cat_chips_widget = QWidget()
        self._cat_chips_widget.setStyleSheet("background: transparent;")
        self._cat_chips_layout = FlowLayout(self._cat_chips_widget, h_spacing=3, v_spacing=3)
        self._cat_chips_layout.setContentsMargins(0, 0, 0, 0)
        self._cat_chip_buttons = []
        main_layout.addWidget(self._cat_chips_widget)

        # Action buttons (bottom)
        _btn_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 30);
                color: white;
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                padding: 0px 2px;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 60); }
        """

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(3)

        self.play_icon = QIcon(resource_path("assets/icons/play.svg"))
        self.play_btn = QPushButton()
        self.play_btn.setIcon(self.play_icon)
        self.play_btn.setFixedHeight(26)
        self.play_btn.setCheckable(True)
        self.play_btn.setToolTip("Slideshow (click again to cycle speed: x1 → x2 → x4 → x8)")
        self.play_btn.setStyleSheet(_btn_style + """
            QPushButton:checked { background-color: rgba(50, 200, 255, 180); border: 1px solid rgba(50, 200, 255, 200); }
        """)
        self.play_btn.clicked.connect(self._on_play_clicked)
        btn_row.addWidget(self.play_btn, 1)

        self.revert_icon = QIcon(resource_path("assets/icons/search_reset.svg"))
        self.revert_btn = QPushButton()
        self.revert_btn.setIcon(self.revert_icon)
        self.revert_btn.setFixedHeight(26)
        self.revert_btn.setToolTip("Revert to Original")
        self.revert_btn.setStyleSheet(_btn_style)
        self.revert_btn.clicked.connect(self._on_revert_clicked)
        btn_row.addWidget(self.revert_btn, 1)

        self.batch_refine_icon = QIcon(resource_path("assets/icons/auto_fix.svg"))
        self.batch_refine_btn = QPushButton()
        self.batch_refine_btn.setIcon(self.batch_refine_icon)
        self.batch_refine_btn.setFixedHeight(26)
        self.batch_refine_btn.setToolTip("Batch Refine Category")
        self.batch_refine_btn.setStyleSheet(_btn_style)
        self.batch_refine_btn.clicked.connect(self._on_batch_refine_clicked)
        btn_row.addWidget(self.batch_refine_btn, 1)

        main_layout.addLayout(btn_row)

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

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        self._content_widget.setVisible(not self._collapsed)
        self.setFixedWidth(GRIP_W if self._collapsed else PANEL_W + GRIP_W)
        if hasattr(self.parent(), '_update_side_panels_geometry'):
            QTimer.singleShot(0, self.parent()._update_side_panels_geometry)

    def _clear_content(self):
        """Remove all thumbnail and group-label widgets."""
        for w in self.alt_widgets:
            w.deleteLater()
        self.alt_widgets.clear()

    def _make_group_label(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedHeight(18)
        lbl.setStyleSheet(
            "color: rgba(255, 200, 100, 200); font-size: 9px; font-weight: bold;"
            "background: rgba(255,255,255,15); border-radius: 2px; padding: 2px 0;"
        )
        return lbl

    def _load_thumb_for_widget(self, thumb: 'AltThumbnail', resolved_path: str):
        """Start async (or sync) thumbnail loading, targeting a specific widget."""
        def _apply(_, img, w=thumb):
            if img and not img.isNull():
                try:
                    w.set_pixmap(QPixmap.fromImage(img))
                except RuntimeError:
                    pass  # widget was deleted before the worker finished

        if self.thread_pool:
            worker = ThumbnailWorker(0, resolved_path, self._load_thumbnail)
            worker.signals.finished.connect(_apply)
            self.thread_pool.start(worker)
        else:
            qimg = self._load_thumbnail(resolved_path)
            if qimg and not qimg.isNull():
                try:
                    thumb.set_pixmap(QPixmap.fromImage(qimg))
                except RuntimeError:
                    pass

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
        cat_names = sorted(list(categories.keys()), key=lambda c: (0 if c == "Main" else 1, natural_sort_key(c)))

        if not cat_names:
            self.hide()
            return

        # Restore user's last selection for this page; default to "All"
        active_cat = self.active_categories.get(idx, "All")
        if active_cat != "All" and active_cat not in cat_names:
            active_cat = "All"
        self.active_categories[idx] = active_cat

        # Update category chip buttons
        self._cat_chips_layout.clear_widgets()
        self._cat_chip_buttons.clear()

        all_cats = ["All"] + cat_names
        for cat in all_cats:
            label = "ALL" if cat == "All" else cat.upper()
            chip = QPushButton(label)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            is_active = (cat == active_cat)
            chip.setStyleSheet(self._cat_chip_active_style if is_active else self._cat_chip_style)
            chip.clicked.connect(lambda checked, c=cat: self._on_chip_clicked(c))
            self._cat_chips_layout.addWidget(chip)
            self._cat_chip_buttons.append((cat, chip))

        # Hide chips row if only one category
        self._cat_chips_widget.setVisible(len(cat_names) > 1)

        # Update play button state
        is_playing = idx in self.slideshow_states
        self.play_btn.setChecked(is_playing)
        if is_playing:
            state = self.slideshow_states[idx]
            self.play_btn.setIcon(self.play_icon)
            self.play_btn.setText(self.speed_labels[state['speed_idx']])
        else:
            self.play_btn.setIcon(self.play_icon)
            self.play_btn.setText("")

        original_image_path = page.images[0]

        # Determine which categories to render
        cats_to_render = cat_names if active_cat == "All" else ([active_cat] if active_cat in categories else cat_names)
        show_group_labels = active_cat == "All" and len(cat_names) > 1

        non_orig_count = 0
        for cat in cats_to_render:
            cat_paths = list(categories.get(cat, []))

            if cat == "Main" and original_image_path in cat_paths:
                other_paths = sorted(
                    [p for p in cat_paths if p != original_image_path],
                    key=lambda p: natural_sort_key(Path(p).name)
                )
                cat_paths = [original_image_path] + other_paths
            else:
                cat_paths = sorted(cat_paths, key=lambda p: natural_sort_key(Path(p).name))

            if show_group_labels:
                lbl = self._make_group_label(cat)
                self.scroll_layout.addWidget(lbl)
                self.alt_widgets.append(lbl)

            for variant_path in cat_paths:
                true_v_idx = page.images.index(variant_path)
                is_selected = (not is_playing) and (true_v_idx == page.current_variant_index)
                is_original = (variant_path == original_image_path)
                if is_original:
                    display_label = "ORIG"
                else:
                    non_orig_count += 1
                    display_label = non_orig_count

                thumb = AltThumbnail(
                    self.scroll_content,
                    variant_path,
                    display_index=display_label,
                    is_selected=is_selected,
                    on_click=lambda v=true_v_idx: self._on_variant_clicked(idx, v),
                    on_right_click=lambda pos, vp=variant_path: self._show_alt_context_menu(idx, vp, pos)
                )
                self.scroll_layout.addWidget(thumb)
                self.alt_widgets.append(thumb)

                self._load_thumb_for_widget(thumb, self._resolve_path(variant_path))

        # Show panel
        if hasattr(self.parent(), "panels_visible"):
            if self.parent().panels_visible:
                self.show()
                if hasattr(self.parent(), '_update_side_panels_geometry'):
                    QTimer.singleShot(100, self.parent()._update_side_panels_geometry)
            else:
                self.hide()
        else:
            self.show()

    def _load_thumbnail(self, path: str):
        try:
            if '|' in path:
                return load_thumbnail_from_virtual_path(path, THUMB_W, THUMB_H)
            else:
                return load_thumbnail_from_path(path, THUMB_W, THUMB_H)
        except Exception:
            return None

    def _resolve_path(self, path_str):
        """Resolve relative path to absolute using model's manga_dir."""
        p = Path(path_str)
        if not p.is_absolute() and self.model:
            p = Path(self.model.manga_dir) / p
        return str(p)

    def _on_chip_clicked(self, category):
        """Handle category chip button click."""
        page_index = self.model.current_index if self.model else 0
        self.active_categories[page_index] = category
        if category == "All":
            self._update_panel(page_index)
            return
        if self.model and 0 <= page_index < len(self.model.images):
            page = self.model.images[page_index]
            categories = page.get_categorized_variants()
            if category in categories and categories[category]:
                cat_paths = categories[category]
                original_image_path = page.images[0]
                if category == "Main" and original_image_path in cat_paths:
                    sorted_paths = [original_image_path] + sorted(
                        [p for p in cat_paths if p != original_image_path],
                        key=lambda p: natural_sort_key(Path(p).name)
                    )
                else:
                    sorted_paths = sorted(cat_paths, key=lambda p: natural_sort_key(Path(p).name))
                try:
                    first_idx = page.images.index(sorted_paths[0])
                    self.model.change_variant(page_index, first_idx)
                    return
                except (ValueError, IndexError):
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

    def _show_alt_context_menu(self, page_idx, variant_path, global_pos):
        if not self.model or not (0 <= page_idx < len(self.model.images)):
            return
        page = self.model.images[page_idx]
        # No context menu for the main page (index 0)
        if variant_path == page.images[0]:
            return

        series_path = str(self.model.series['path'])
        chapter_name = Path(str(self.model.manga_dir)).name
        manga_dir = Path(str(self.model.manga_dir))
        main_file = Path(page.images[0]).name

        # Load alt config to determine fix state
        data = AltManager.load_alts(series_path)
        page_entry = data.get(chapter_name, {}).get(main_file, {})
        if isinstance(page_entry, list):
            page_entry = {"alts": page_entry, "translations": {}}
        alts_list = page_entry.get("alts", [])
        alts_fix_map = page_entry.get("alts_fix", {})

        # Resolve variant_path to relative for lookup
        try:
            rel_variant = str(Path(variant_path).relative_to(manga_dir)).replace('\\', '/')
        except ValueError:
            rel_variant = None

        # Determine if this variant is a fix or an original alt
        original_rel = None   # relative path of the original alt
        is_fix = False

        if rel_variant:
            # Check if rel_variant is a VALUE in alts_fix (i.e. it is a fix file)
            for orig_key, fix_val in alts_fix_map.items():
                if fix_val == rel_variant:
                    original_rel = orig_key
                    is_fix = True
                    break
            # If not a fix, check if it's directly in the alts list
            if not is_fix and rel_variant in alts_list:
                original_rel = rel_variant

        if original_rel is None:
            # Fallback: treat variant as original using filename match
            vname = Path(variant_path).name
            for a in alts_list:
                if Path(a).name == vname:
                    original_rel = a
                    break
            if original_rel is None:
                return  # Can't identify this alt

        # Build context menu
        menu = QMenu(self)
        refine_action = menu.addAction("Refine Alt")
        revert_action = menu.addAction("Revert Alt") if is_fix else None
        menu.addSeparator()
        notes_action = menu.addAction("Edit Notes...")
        copy_notes_action = menu.addAction("Copy Notes")

        action = menu.exec(global_pos if isinstance(global_pos, QPoint) else QPoint(global_pos))

        if action == refine_action:
            self._open_refine_dialog(
                page, page_idx, variant_path, main_file, original_rel,
                manga_dir, series_path, chapter_name
            )
        elif revert_action and action == revert_action:
            AltManager.remove_alt_fix(series_path, chapter_name, main_file, original_rel)
            self.model.refresh()
        elif action == notes_action:
            current = AltManager.get_alt_note(series_path, chapter_name, main_file, original_rel)
            dlg = _AltNotesDialog(self, current_note=current)
            if dlg.exec():
                AltManager.save_alt_note(series_path, chapter_name, main_file, original_rel, dlg.get_note())
        elif action == copy_notes_action:
            note = AltManager.get_alt_note(series_path, chapter_name, main_file, original_rel)
            if note:
                QApplication.clipboard().setText(note)

    def _open_refine_dialog(self, page, page_idx, variant_path, main_file, alt_rel_path, manga_dir, series_path, chapter_name):
        from src.ui.components.refine_alt_dialog import RefineAltDialog

        # Load metadata to filter fixes from being used as references
        data = AltManager.load_alts(series_path)
        page_entry = data.get(chapter_name, {}).get(main_file, {})
        if isinstance(page_entry, list):
            page_entry = {"alts": page_entry, "translations": {}}
        alts_fix_map = page_entry.get("alts_fix", {})

        # Collect all original variants as possible references
        reference_paths = [self._resolve_path(page.images[0])]
        for alt_rel in page_entry.get("alts", []):
            abs_p = self._resolve_path(alt_rel)
            if abs_p not in reference_paths:
                reference_paths.append(abs_p)

        main_path = self._resolve_path(page.images[0])
        alt_abs = str(manga_dir / alt_rel_path)

        alt_p = Path(alt_rel_path)
        fix_rel_path = str(alt_p.parent / (alt_p.stem + '_fix' + alt_p.suffix)).replace('\\', '/')
        output_path = str(manga_dir / fix_rel_path)

        dlg = RefineAltDialog(
            parent=self,
            main_path=main_path,
            alt_path=alt_abs,
            output_path=output_path,
            series_path=series_path,
            chapter_name=chapter_name,
            main_file=main_file,
            alt_rel_path=alt_rel_path,
            fix_rel_path=fix_rel_path,
            reference_paths=reference_paths
        )
        if dlg.exec():
            # Swap the in-memory path for this variant and reload the view immediately
            try:
                variant_idx = page.images.index(variant_path)
            except ValueError:
                variant_idx = None

            if variant_idx is not None:
                page.images[variant_idx] = output_path
                self.model.change_variant(page_idx, variant_idx)
            else:
                self.model.refresh()

    def _on_batch_refine_clicked(self):
        if not self.model or not (0 <= self.model.current_index < len(self.model.images)):
            return
        
        page_idx = self.model.current_index
        page = self.model.images[page_idx]
        active_cat = self.active_categories.get(page_idx, "All")

        categories = page.get_categorized_variants()
        if active_cat == "All":
            cat_paths = [p for paths in categories.values() for p in paths]
        else:
            cat_paths = categories.get(active_cat, [])
        if not cat_paths:
            return

        series_path = str(self.model.series['path'])
        chapter_name = Path(str(self.model.manga_dir)).name
        manga_dir = Path(str(self.model.manga_dir))
        main_file = Path(page.images[0]).name

        # Load metadata to identify original alts vs fixes
        data = AltManager.load_alts(series_path)
        page_entry = data.get(chapter_name, {}).get(main_file, {})
        if isinstance(page_entry, list):
            page_entry = {"alts": page_entry, "translations": {}}
        alts_fix_map = page_entry.get("alts_fix", {})
        fix_to_orig = {v: k for k, v in alts_fix_map.items()}

        items_data = []
        for p in cat_paths:
            # Skip the main page (index 0)
            if p == page.images[0]:
                continue
                
            try:
                rel = str(Path(p).relative_to(manga_dir)).replace('\\', '/')
            except ValueError:
                rel = None
            
            # If this is a fix, find its original
            if rel and rel in fix_to_orig:
                orig_rel = fix_to_orig[rel]
                orig_abs = str(manga_dir / orig_rel)
            else:
                orig_rel = rel
                orig_abs = str(manga_dir / rel) if rel else p
            
            items_data.append({
                'alt_abs': orig_abs,
                'alt_rel': orig_rel
            })

        if not items_data:
            return

        # Prepare reference paths
        reference_paths = [self._resolve_path(page.images[0])]
        for alt_rel in page_entry.get("alts", []):
            abs_p = self._resolve_path(alt_rel)
            if abs_p not in reference_paths:
                reference_paths.append(abs_p)

        from src.ui.components.batch_refine_dialog import BatchRefineDialog
        dlg = BatchRefineDialog(
            parent=self,
            items_data=items_data,
            series_path=series_path,
            chapter_name=chapter_name,
            main_file=main_file,
            reference_paths=reference_paths,
            manga_dir=manga_dir
        )
        if dlg.exec():
            current_variant_idx = page.current_variant_index
            self.model.update_page_variants(page_idx)
            new_page = self.model.images[page_idx]
            restore_idx = min(current_variant_idx, len(new_page.images) - 1)
            self.model.change_variant(page_idx, restore_idx)
