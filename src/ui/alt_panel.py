import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QSizePolicy, QComboBox, QMenu
)
from PyQt6.QtCore import Qt, QTimer, QSize, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QImage
from src.enums import ViewMode
from src.utils.resource_utils import resource_path
from src.utils.img_utils import load_thumbnail_from_path, load_thumbnail_from_virtual_path
from src.utils.str_utils import natural_sort_key
from src.workers.thumbnail_worker import ThumbnailWorker
from src.core.alt_manager import AltManager

THUMB_W = 120
THUMB_H = 160
TAB_W = 16   # width of the collapse/expand tab
TAB_H = 56   # height of the collapse/expand tab


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
        self._collapsed = False
        self.setFixedWidth(THUMB_W + 40)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        # Outer layout holds only the content widget; tab is a floating overlay
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._content_widget = QWidget(self)
        self._content_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._content_widget.setStyleSheet("background: transparent;")
        outer_layout.addWidget(self._content_widget)

        main_layout = QVBoxLayout(self._content_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(4)

        # Row 1: Category dropdown (full width)
        cat_row = QHBoxLayout()
        cat_row.setContentsMargins(0, 0, 0, 0)
        cat_row.setSpacing(0)

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
        cat_row.addWidget(self.cat_combo)

        main_layout.addLayout(cat_row)

        # Row 2: Action buttons — equally spaced across full panel width
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

        # Collapse tab — floats on the right edge, always visible when panel is shown
        self._tab_btn = QPushButton("‹", self)
        self._tab_btn.setFixedSize(TAB_W, TAB_H)
        self._tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_btn.setToolTip("Collapse panel")
        self._tab_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 140);
                color: rgba(255, 255, 255, 200);
                border: 1px solid rgba(255, 255, 255, 40);
                border-left: none;
                border-radius: 0px 5px 5px 0px;
                font-size: 13px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 50);
                color: white;
            }
        """)
        self._tab_btn.clicked.connect(self._toggle_collapse)
        self._tab_btn.raise_()

        self.hide()

        if self.model:
            self.model.image_loaded.connect(self._on_image_loaded)
            self.model.double_image_loaded.connect(self._on_double_image_loaded)

    def _on_image_loaded(self, path):
        self._update_panel(self.model.current_index)

    def _on_double_image_loaded(self, path1, path2):
        self._update_panel(self.model.current_index)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._reposition_tab()

    def set_tab_center_y(self, center_y: int):
        """Set the tab's vertical center to a viewport-relative y so it stays stable."""
        self._tab_center_y = center_y
        self._reposition_tab()

    def _reposition_tab(self):
        if hasattr(self, '_tab_center_y'):
            tab_y = max(0, min(self._tab_center_y - TAB_H // 2, self.height() - TAB_H))
        else:
            tab_y = max(0, (self.height() - TAB_H) // 2)
        self._tab_btn.move(self.width() - TAB_W, tab_y)
        self._tab_btn.raise_()

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        self._content_widget.setVisible(not self._collapsed)
        if self._collapsed:
            self.setFixedWidth(TAB_W)
            self._tab_btn.setText("›")
            self._tab_btn.setToolTip("Expand panel")
        else:
            self.setFixedWidth(THUMB_W + 40)
            self._tab_btn.setText("‹")
            self._tab_btn.setToolTip("Collapse panel")
        if hasattr(self.parent(), '_update_side_panels_geometry'):
            QTimer.singleShot(0, self.parent()._update_side_panels_geometry)

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
        cat_names = sorted(list(categories.keys()), key=natural_sort_key)

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
            self.play_btn.setIcon(self.play_icon)
            self.play_btn.setText(self.speed_labels[state['speed_idx']])
        else:
            self.play_btn.setIcon(self.play_icon)
            self.play_btn.setText("")

        # Build thumbnail rows for active category
        active_paths = categories.get(active_cat, [])
        original_image_path = page.images[0]
        
        if active_cat == "Main" and original_image_path in active_paths:
            # Keep original at top, sort the rest
            other_paths = [p for p in active_paths if p != original_image_path]
            other_paths = sorted(other_paths, key=lambda p: natural_sort_key(Path(p).name))
            active_paths = [original_image_path] + other_paths
        else:
            active_paths = sorted(active_paths, key=lambda p: natural_sort_key(Path(p).name))
            
        for cat_v_idx, variant_path in enumerate(active_paths):
            true_v_idx = page.images.index(variant_path)
            is_selected = (not is_playing) and (true_v_idx == page.current_variant_index)
            is_original = (variant_path == original_image_path)
            display_label = "ORIG" if is_original else cat_v_idx + 1

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

            # Load thumbnail async (or synchronously if no thread pool)
            resolved = self._resolve_path(variant_path)
            if self.thread_pool:
                worker = ThumbnailWorker(len(self.alt_widgets) - 1, resolved, self._load_thumbnail)
                worker.signals.finished.connect(self._on_thumbnail_loaded)
                self.thread_pool.start(worker)
            else:
                qimg = self._load_thumbnail(resolved)
                if qimg and not qimg.isNull():
                    pixmap = QPixmap.fromImage(qimg)
                    thumb.set_pixmap(pixmap)

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

    def _on_thumbnail_loaded(self, index, qimg):
        if qimg and not qimg.isNull() and index < len(self.alt_widgets):
            pixmap = QPixmap.fromImage(qimg)
            self.alt_widgets[index].set_pixmap(pixmap)

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

        action = menu.exec(global_pos if isinstance(global_pos, QPoint) else QPoint(global_pos))

        if action == refine_action:
            self._open_refine_dialog(
                page, page_idx, variant_path, main_file, original_rel,
                manga_dir, series_path, chapter_name
            )
        elif revert_action and action == revert_action:
            AltManager.remove_alt_fix(series_path, chapter_name, main_file, original_rel)
            self.model.refresh()

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
        active_cat = self.active_categories.get(page_idx)
        if not active_cat:
            return
            
        categories = page.get_categorized_variants()
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
            # Refresh model to show new fixes
            self.model.refresh()
