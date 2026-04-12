import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QSizePolicy, QMenu, QComboBox,
    QDialog, QPlainTextEdit, QApplication, QStackedWidget
)
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal
from src.ui.styles import SCROLL_AREA_TRANSPARENT
from PyQt6.QtGui import QIcon, QPixmap, QImage
from src.enums import ViewMode
from src.ui.components.grip_strip import GripStrip, GRIP_W
from src.utils.resource_utils import resource_path
from src.utils.img_utils import load_thumbnail_from_path, load_thumbnail_from_virtual_path
from src.utils.str_utils import natural_sort_key
from src.workers.thumbnail_worker import ThumbnailWorker
from src.core.alt_manager import AltManager

THUMB_W = 120
THUMB_H = 150
PANEL_W = THUMB_W + 20


class AltThumbnail(QWidget):
    """Single clickable alt thumbnail with index badge overlay."""
    def __init__(self, parent, variant_path, display_index, is_selected=False, has_note=False, is_fix=False, has_fix=False, on_click=None, on_right_click=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.variant_path = variant_path
        self.on_click = on_click
        self.on_right_click = on_right_click
        self.is_selected = is_selected

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(THUMB_W + 4, THUMB_H + 4)

        self.thumb_label = QLabel(self)
        self.thumb_label.setFixedSize(THUMB_W, THUMB_H)
        self.thumb_label.move(2, 2)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet("background: transparent;")

        is_orig = str(display_index) == "ORIG"
        if str(display_index):
            self.badge = QLabel(str(display_index), self)
            self.badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            if is_orig:
                self.badge.setStyleSheet(
                    "background: rgba(200, 120, 30, 200); color: white;"
                    "font-size: 8px; font-weight: bold; padding: 0px 4px;"
                    "border-radius: 3px;"
                )
            else:
                self.badge.setStyleSheet(
                    "background: rgba(0, 0, 0, 160); color: rgba(255, 255, 255, 200);"
                    "font-size: 9px; font-weight: bold; padding: 0px 4px;"
                    "border-radius: 3px;"
                )
            self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.badge.adjustSize()
            self.badge.setFixedHeight(16)
            if self.badge.width() < 16:
                self.badge.setFixedWidth(16)
            self.badge.move(4, 4)
            self.badge.raise_()

        if has_note:
            self.note_icon = QLabel(self)
            pixmap = QIcon(resource_path("assets/icons/note.svg")).pixmap(12, 12)
            self.note_icon.setPixmap(pixmap)
            self.note_icon.setStyleSheet("background: rgba(0,0,0,160); border-radius: 3px;")
            self.note_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.note_icon.setFixedSize(16, 16)
            self.note_icon.move(THUMB_W - 16 - 2, 4)
            self.note_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.note_icon.raise_()

        if is_fix or has_fix:
            self.fix_icon = QLabel(self)
            pixmap = QIcon(resource_path("assets/icons/auto_fix.svg")).pixmap(12, 12)
            self.fix_icon.setPixmap(pixmap)
            if is_fix:
                self.fix_icon.setStyleSheet("background: rgba(156, 39, 176, 180); border-radius: 3px;")
            else:
                self.fix_icon.setStyleSheet("background: rgba(0,0,0,160); border-radius: 3px;")
            self.fix_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.fix_icon.setFixedSize(16, 16)
            self.fix_icon.move(THUMB_W - 16 - 2, THUMB_H - 16 - 2)
            self.fix_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.fix_icon.raise_()

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
    """Vertical panel showing alt thumbnails for the current page, organized by category, or page info."""
    reload_requested = pyqtSignal()

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

        # Content Wrapper to hold top tabs + stacked content
        self.content_container = QWidget()
        self.content_container.hide()
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        outer_layout.addWidget(self.content_container)

        # --- Top Tab Bar ---
        self.tabs_row = QWidget()
        self.tabs_row.setFixedHeight(30)
        self.tabs_row.setStyleSheet("background: rgba(255, 255, 255, 10); border-bottom: 1px solid rgba(255, 255, 255, 20);")
        tabs_layout = QHBoxLayout(self.tabs_row)
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.setSpacing(0)

        _tab_btn_style = """
            QPushButton {
                background: transparent;
                color: rgba(255, 255, 255, 150);
                border: none;
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QPushButton:hover { color: white; background: rgba(255, 255, 255, 10); }
            QPushButton[active="true"] { 
                color: #4a86e8; 
                border-bottom: 2px solid #4a86e8; 
            }
        """
        
        self.alt_tab_btn = QPushButton("ALTS")
        self.alt_tab_btn.setProperty("active", "true")
        self.alt_tab_btn.setStyleSheet(_tab_btn_style)
        self.alt_tab_btn.clicked.connect(lambda: self._on_tab_clicked(0))
        
        self.info_tab_btn = QPushButton("INFO")
        self.info_tab_btn.setProperty("active", "false")
        self.info_tab_btn.setStyleSheet(_tab_btn_style)
        self.info_tab_btn.clicked.connect(lambda: self._on_tab_clicked(1))

        tabs_layout.addWidget(self.alt_tab_btn)
        tabs_layout.addWidget(self.info_tab_btn)
        content_layout.addWidget(self.tabs_row)

        # Content stack (Alt vs Info)
        self.content_stack = QStackedWidget(self)
        content_layout.addWidget(self.content_stack)

        self._grip = GripStrip(self._toggle_collapse, parent=self)
        outer_layout.addWidget(self._grip)

        # --- Stack 0: Alternates View ---
        self.alt_view_widget = QWidget()
        alt_main_layout = QVBoxLayout(self.alt_view_widget)
        alt_main_layout.setContentsMargins(5, 5, 5, 5)
        alt_main_layout.setSpacing(4)

        # Pinned original thumbnail
        self._orig_widget = AltThumbnail(self.alt_view_widget, "", "ORIG")
        self._orig_widget.hide()
        alt_main_layout.addWidget(self._orig_widget)

        # Scroll area for alt thumbnails
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setLineWidth(0)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(SCROLL_AREA_TRANSPARENT)
        alt_main_layout.addWidget(self.scroll_area, 1)

        # Category dropdown (bottom)
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
        alt_main_layout.addWidget(self.cat_combo)

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
        self.play_btn.setStyleSheet(_btn_style + """
            QPushButton:checked { background-color: rgba(50, 200, 255, 180); border: 1px solid rgba(50, 200, 255, 200); }
        """)
        self.play_btn.clicked.connect(self._on_play_clicked)
        btn_row.addWidget(self.play_btn, 1)

        self.batch_refine_btn = QPushButton()
        self.batch_refine_btn.setIcon(QIcon(resource_path("assets/icons/auto_fix.svg")))
        self.batch_refine_btn.setFixedHeight(26)
        self.batch_refine_btn.setStyleSheet(_btn_style)
        self.batch_refine_btn.clicked.connect(self._on_batch_refine_clicked)
        btn_row.addWidget(self.batch_refine_btn, 1)

        self.edit_alts_btn = QPushButton("✎")
        self.edit_alts_btn.setFixedHeight(26)
        self.edit_alts_btn.setStyleSheet(_btn_style)
        self.edit_alts_btn.clicked.connect(self._on_edit_alts_clicked)
        btn_row.addWidget(self.edit_alts_btn, 1)

        alt_main_layout.addLayout(btn_row)

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent; border: none;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(5)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)

        self.content_stack.addWidget(self.alt_view_widget)

        # --- Stack 1: Info View ---
        self.info_view_widget = QWidget()
        info_layout = QVBoxLayout(self.info_view_widget)
        info_layout.setContentsMargins(8, 8, 8, 8)
        
        info_scroll = QScrollArea()
        info_scroll.setWidgetResizable(True)
        info_scroll.setFrameShape(QFrame.Shape.NoFrame)
        info_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        info_scroll.setStyleSheet(SCROLL_AREA_TRANSPARENT)
        
        self.info_label = QLabel("No information available.")
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.info_label.setStyleSheet("color: rgba(255, 255, 255, 210); font-size: 11px; line-height: 1.4;")
        
        info_scroll.setWidget(self.info_label)
        info_layout.addWidget(info_scroll)
        
        self.content_stack.addWidget(self.info_view_widget)

        self.alt_widgets = []
        self._panel_page_index = -1
        self._panel_images_signature = ()
        self._panel_active_category = None

        # Slideshow state
        self.slideshow_states = {}
        self.speeds = [2000, 1000, 500, 250]
        self.speed_labels = ["x1", "x2", "x4", "x8"]

        self.hide()

        if self.model:
            self.model.image_loaded.connect(self._on_image_loaded)
            self.model.double_image_loaded.connect(self._on_double_image_loaded)

    def set_info_text(self, text: str):
        """Update the info tab with formatted metadata from the ImageInfoWorker."""
        if not text:
            self.info_label.setText("No information available.")
            return

        # Split info blocks (e.g. for double-page mode)
        blocks = text.split("  +  ")
        formatted_info = ""
        
        for i, block in enumerate(blocks):
            # Parse key-value pairs from the pipe-separated string
            fields = {}
            for field in block.split('|'):
                if ':' in field:
                    k, v = field.split(':', 1)
                    fields[k] = v

            if not fields:
                continue
                
            # Block header if multi-file
            if len(blocks) > 1:
                formatted_info += f"<div style='color: #4a86e8; font-size: 11px; font-weight: bold; margin-bottom: 3px;'>FILE {i+1}</div>"
            
            # Filename (Primary - Always NAME)
            filename = fields.pop("NAME", "Unknown")
            formatted_info += f"<div style='color: #eee; font-size: 12px; font-weight: bold; margin-bottom: 6px;'>{filename}</div>"
            
            # Dynamically render all other metadata fields
            # Sorted to keep a consistent order: SIZE, TYPE, DIM, RATIO, then others
            field_order = ["SIZE", "TYPE", "DIM", "RATIO", "DATE"]
            sorted_keys = sorted(fields.keys(), key=lambda x: field_order.index(x) if x in field_order else 99)
            
            for key in sorted_keys:
                value = fields[key]
                # Label with fixed width-like alignment using padding or just consistent spacing
                label = f"{key:<6}".replace(" ", "&nbsp;")
                formatted_info += (
                    f"<div style='margin-bottom: 3px; font-family: Consolas, monospace;'>"
                    f"<span style='color: #888; font-size: 10px;'>{label}:</span> "
                    f"<span style='color: #ccc; font-size: 11px;'>{value}</span>"
                    f"</div>"
                )
            
            # Separator between blocks
            if i < len(blocks) - 1:
                formatted_info += "<div style='border-bottom: 1px solid rgba(255,255,255,15); margin: 10px 0;'></div>"

        self.info_label.setText(formatted_info)

    def _on_tab_clicked(self, index):
        self.content_stack.setCurrentIndex(index)
        
        # Update button visual state
        self.alt_tab_btn.setProperty("active", "true" if index == 0 else "false")
        self.info_tab_btn.setProperty("active", "true" if index == 1 else "false")
        
        # Refresh stylesheets to apply property changes
        self.alt_tab_btn.style().unpolish(self.alt_tab_btn)
        self.alt_tab_btn.style().polish(self.alt_tab_btn)
        self.info_tab_btn.style().unpolish(self.info_tab_btn)
        self.info_tab_btn.style().polish(self.info_tab_btn)

    def _on_image_loaded(self, path):
        self._dispatch_update(self.model.current_index)

    def _on_double_image_loaded(self, path1, path2):
        self._dispatch_update(self.model.current_index)

    def _dispatch_update(self, idx):
        page = self.model.images[idx] if 0 <= idx < len(self.model.images) else None
        active_cat = self.active_categories.get(idx, "All")
        
        if (page and
                idx == self._panel_page_index and
                tuple(page.images) == self._panel_images_signature and
                active_cat == self._panel_active_category):
            self._update_selection(idx)
        else:
            self._update_panel(idx)

    def _update_selection(self, idx):
        page = self.model.images[idx]
        is_playing = idx in self.slideshow_states
        current_v = page.current_variant_index

        self._orig_widget.set_selected((not is_playing) and current_v == 0)
        for w in self.alt_widgets:
            if isinstance(w, AltThumbnail):
                try:
                    w.set_selected((not is_playing) and page.images.index(w.variant_path) == current_v)
                except ValueError:
                    pass

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        self.content_container.setVisible(not self._collapsed)
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
            self._orig_widget.hide()
            self.hide()
            return

        idx = primary_index
        if not (0 <= idx < len(self.model.images)):
            self._orig_widget.hide()
            self.hide()
            return

        page = self.model.images[idx]
        
        # Get categories and check for alternates
        categories = page.get_categorized_variants()
        cat_names = sorted(list(categories.keys()), key=lambda c: (0 if c == "Main" else 1, natural_sort_key(c)))
        has_alts = len(page.images) > 1 and bool(cat_names)
        active_cat = "All"

        if has_alts:
            self.cat_combo.show()
            self.play_btn.show()
            self.batch_refine_btn.show()
            self.edit_alts_btn.show()

            # Restore user's last selection for this page; default to "All"
            active_cat = self.active_categories.get(idx, "All")
            if active_cat != "All" and active_cat not in cat_names:
                active_cat = "All"
            self.active_categories[idx] = active_cat

            # Update category combo box
            self.cat_combo.blockSignals(True)
            self.cat_combo.clear()
            self.cat_combo.addItem("ALL", "All")
            self.cat_combo.insertSeparator(1)
            for cat in cat_names:
                self.cat_combo.addItem(cat.upper(), cat)
            if active_cat == "All":
                self.cat_combo.setCurrentIndex(0)
            else:
                for i in range(self.cat_combo.count()):
                    if self.cat_combo.itemData(i) == active_cat:
                        self.cat_combo.setCurrentIndex(i)
                        break
            self.cat_combo.blockSignals(False)
            self.cat_combo.setVisible(len(cat_names) > 1)

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

            # Pinned original thumbnail
            orig_selected = (not is_playing) and (page.current_variant_index == 0)
            self._orig_widget.variant_path = original_image_path
            self._orig_widget.on_click = lambda: self._on_variant_clicked(idx, 0)
            self._orig_widget.is_selected = orig_selected
            self._orig_widget._update_style()
            self._orig_widget.show()
            self._load_thumb_for_widget(self._orig_widget, self._resolve_path(original_image_path))

            # Determine which categories to render
            cats_to_render = cat_names if active_cat == "All" else ([active_cat] if active_cat in categories else cat_names)
            show_group_labels = active_cat == "All" and len(cat_names) > 1

            non_orig_count = 0
            series_path = str(self.model.series['path'])
            chapter_name = Path(str(self.model.manga_dir)).name
            main_file = Path(page.images[0]).name
            manga_dir = Path(str(self.model.manga_dir))

            # Pre-load metadata for the whole page once
            data = AltManager.load_alts(series_path)
            page_entry = data.get(chapter_name, {}).get(main_file, {})
            if isinstance(page_entry, list):
                page_entry = {"alts": page_entry, "translations": {}}
            alts_fix_map = page_entry.get("alts_fix", {})

            for cat in cats_to_render:
                cat_paths = list(categories.get(cat, []))

                # Remove original from category lists (it's pinned above)
                cat_paths = [p for p in cat_paths if p != original_image_path]

                if not cat_paths:
                    continue

                if show_group_labels:
                    lbl = self._make_group_label(cat)
                    self.scroll_layout.addWidget(lbl)
                    self.alt_widgets.append(lbl)

                for variant_path in cat_paths:
                    true_v_idx = page.images.index(variant_path)
                    is_selected = (not is_playing) and (true_v_idx == page.current_variant_index)
                    non_orig_count += 1
                    
                    try:
                        rel_variant = str(Path(variant_path).relative_to(manga_dir)).replace('\\', '/')
                    except ValueError:
                        rel_variant = None

                    is_fix = False
                    has_fix = False
                    if rel_variant:
                        if rel_variant in alts_fix_map.values():
                            is_fix = True
                        if rel_variant in alts_fix_map.keys():
                            has_fix = True

                    has_note = False
                    original_rel = self._get_original_rel_for_variant(variant_path, page)
                    if original_rel:
                        note = AltManager.get_alt_note(series_path, chapter_name, main_file, original_rel)
                        if note and note.strip():
                            has_note = True

                    thumb = AltThumbnail(
                        self.scroll_content,
                        variant_path,
                        display_index=non_orig_count,
                        is_selected=is_selected,
                        has_note=has_note,
                        is_fix=is_fix,
                        has_fix=has_fix,
                        on_click=lambda v=true_v_idx: self._on_variant_clicked(idx, v),
                        on_right_click=lambda pos, vp=variant_path: self._show_alt_context_menu(idx, vp, pos)
                    )
                    self.scroll_layout.addWidget(thumb)
                    self.alt_widgets.append(thumb)

                    self._load_thumb_for_widget(thumb, self._resolve_path(variant_path))
        else:
            # No alternates, hide the alt-specific UI
            self._orig_widget.hide()
            self.cat_combo.hide()
            self.play_btn.hide()
            self.batch_refine_btn.hide()
            self.edit_alts_btn.hide()
            
            # Add a placeholder label for the ALT tab
            no_alts_lbl = QLabel("No alternates\nfor this page.")
            no_alts_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_alts_lbl.setStyleSheet("color: rgba(255, 255, 255, 80); font-size: 11px; margin-top: 50px;")
            self.scroll_layout.addWidget(no_alts_lbl)
            self.alt_widgets.append(no_alts_lbl)

        # Show panel if parent allows
        if hasattr(self.parent(), "panels_visible"):
            if self.parent().panels_visible:
                self.show()
                if hasattr(self.parent(), '_update_side_panels_geometry'):
                    QTimer.singleShot(100, self.parent()._update_side_panels_geometry)
            else:
                self.hide()
        else:
            self.show()

        self._panel_page_index = primary_index
        self._panel_images_signature = tuple(page.images)
        self._panel_active_category = active_cat

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

    def _get_original_rel_for_variant(self, variant_path, page):
        manga_dir = Path(str(self.model.manga_dir))
        main_file = Path(page.images[0]).name
        series_path = str(self.model.series['path'])
        chapter_name = manga_dir.name

        data = AltManager.load_alts(series_path)
        page_entry = data.get(chapter_name, {}).get(main_file, {})
        if isinstance(page_entry, list):
            page_entry = {"alts": page_entry, "translations": {}}
            
        alts_list = page_entry.get("alts", [])
        alts_fix_map = page_entry.get("alts_fix", {})

        try:
            rel_variant = str(Path(variant_path).relative_to(manga_dir)).replace('\\', '/')
        except ValueError:
            rel_variant = None

        original_rel = None
        if rel_variant:
            for orig_key, fix_val in alts_fix_map.items():
                if fix_val == rel_variant:
                    original_rel = orig_key
                    break
            if not original_rel and rel_variant in alts_list:
                original_rel = rel_variant

        if original_rel is None:
            vname = Path(variant_path).name
            for a in alts_list:
                if Path(a).name == vname:
                    original_rel = a
                    break

        return original_rel

    def _on_combo_changed(self, index):
        """Handle category dropdown selection change."""
        if index < 0:
            return
        category = self.cat_combo.itemData(index)
        if not category:
            return
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

    def _on_edit_alts_clicked(self):
        if not self.model: return
        idx = self.model.current_index
        if idx < 0 or idx >= len(self.model.images): return
        page_obj = self.model.images[idx]
        if not page_obj or len(page_obj.images) <= 1: return
        from src.ui.components.edit_alts_dialog import EditAltsDialog
        dialog = EditAltsDialog(self, page_obj, self.model)
        if dialog.exec():
            self.reload_requested.emit()
