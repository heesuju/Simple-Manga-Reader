from pathlib import Path
from typing import Callable, Dict, List, Set

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QStackedWidget, QPushButton, QMenu, QApplication, QComboBox,
)
from PyQt6.QtGui import QPixmap, QIcon, QImage
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint

from src.ui.styles import SCROLL_AREA_TRANSPARENT
from src.utils.resource_utils import resource_path
from src.utils.str_utils import natural_sort_key
from src.core.alt_manager import AltManager


class HorizontalScrollArea(QScrollArea):
    """Scroll area that redirects vertical mouse wheel input to horizontal scrolling."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setStyleSheet(SCROLL_AREA_TRANSPARENT)

    def wheelEvent(self, ev):
        if ev.angleDelta().y() != 0:
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - ev.angleDelta().y()
            )
        else:
            super().wheelEvent(ev)


_INFO_KEY   = "color:#777;font-size:9px;letter-spacing:0.5px;"
_INFO_VAL   = "color:#ddd;font-size:11px;"
_INFO_RATIO = "color:#bbb;font-size:10px;"
_INFO_SEP   = "color:#444;"

def _kv(key: str, val: str) -> str:
    return f"<span style='{_INFO_KEY}'>{key}</span> <span style='{_INFO_VAL}'>{val}</span>"

def format_image_info_html(text: str) -> str:
    if not text:
        return f"<span style='color:#666;'>No information available.</span>"
    blocks = text.split("  +  ")
    out_blocks = []
    for block in blocks:
        fields = {}
        for field in block.split('|'):
            if ':' in field:
                k, v = field.split(':', 1)
                fields[k] = v
        if not fields:
            continue

        parts = []
        if "SIZE" in fields:
            parts.append(_kv("SIZE", fields["SIZE"]))
        if "TYPE" in fields:
            parts.append(_kv("TYPE", fields["TYPE"]))
        if "DIM" in fields:
            dim = fields["DIM"]
            ratio = f" <span style='{_INFO_RATIO}'>({fields['RATIO']})</span>" if "RATIO" in fields else ""
            parts.append(f"<span style='{_INFO_KEY}'>DIM</span> <span style='{_INFO_VAL}'>{dim}</span>{ratio}")

        sep = f"  <span style='{_INFO_SEP}'>·</span>  "
        out_blocks.append(sep.join(parts))

    block_sep = f"  <span style='color:#333;'>│</span>  "
    return block_sep.join(out_blocks)


FRAME_STRIP_PAGE_SIZE = 50


class FrameThumb(QLabel):
    """Small clickable video-frame thumbnail for the horizontal frames strip."""
    W, H = 55, 80

    def __init__(self, parent, frame_index: int, on_click=None):
        super().__init__(parent)
        self._on_click = on_click
        self.frame_index = frame_index
        self.setFixedSize(self.W + 4, self.H + 4)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("border: 1px solid rgba(255,255,255,20); background: rgba(255,255,255,10);")

        self._badge = QLabel(str(frame_index), self)
        self._badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._badge.setStyleSheet(
            "background: rgba(0,0,0,160); color: rgba(255,255,255,200);"
            "font-size: 8px; font-weight: bold; padding: 1px 3px;"
            "border-radius: 2px; border: none;"
        )
        self._badge.adjustSize()
        self._badge.move(3, 3)
        self._badge.raise_()

    def set_qimage(self, qimage: QImage):
        if qimage and not qimage.isNull():
            scaled = QPixmap.fromImage(qimage).scaled(
                self.W, self.H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(scaled)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._on_click:
            self._on_click(self.frame_index)
        super().mousePressEvent(ev)


class StripThumb(QLabel):
    """Small clickable thumbnail for the horizontal alt strip."""
    W, H = 55, 75

    def __init__(self, parent, on_click, on_right_click=None, is_selected=False):
        super().__init__(parent)
        self._on_click = on_click
        self._on_right_click = on_right_click
        self.setFixedSize(self.W + 4, self.H + 4)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_selected(is_selected)

    def set_selected(self, selected: bool):
        border = "rgba(74,134,232,180)" if selected else "rgba(255,255,255,20)"
        self.setStyleSheet(f"border: 2px solid {border}; background: rgba(255,255,255,10);")

    def set_thumb(self, pixmap: QPixmap):
        scaled = pixmap.scaled(self.W, self.H, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(scaled)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._on_click:
            self._on_click()
        super().mousePressEvent(ev)

    def contextMenuEvent(self, ev):
        if self._on_right_click:
            self._on_right_click(ev.globalPos())
        else:
            super().contextMenuEvent(ev)


class TopStripPanel(QWidget):
    """Horizontal strip below the top panel: alt thumbnails (tab 0) or image info (tab 1)."""
    FIXED_HEIGHT  = 125
    HEIGHT_INFO   = 26
    HEIGHT_ANIM   = 42
    HEIGHT_THUMBS = 91
    HEIGHT_CATS   = 30

    has_alts_changed = pyqtSignal(bool)
    tab_changed      = pyqtSignal(int)   # -1=hidden, 0=alts, 1=info, 2=frames, 3=anim
    reload_requested = pyqtSignal()
    seek_requested   = pyqtSignal(int)
    anim_selected    = pyqtSignal(int)   # animation clip index chosen
    anim_paused      = pyqtSignal(bool)  # True=pause, False=resume

    _BTN_STYLE = """
        QPushButton {
            background: rgba(255,255,255,20);
            color: rgba(255,255,255,150);
            border: 1px solid rgba(255,255,255,30);
            border-radius: 3px;
            font-size: 10px; font-weight: bold;
            padding: 0px 4px;
        }
        QPushButton:hover { background: rgba(255,255,255,50); color: white; }
        QPushButton:checked { background: rgba(50,200,255,180); color: white;
                              border-color: rgba(50,200,255,200); }
    """
    _CHIP_STYLE = """
        QPushButton {
            background: rgba(74,134,232,160);
            color: white;
            border: 1px solid rgba(74,134,232,200);
            border-radius: 10px;
            font-size: 9px; font-weight: bold;
            padding: 2px 8px;
        }
        QPushButton:!checked {
            background: rgba(255,255,255,20);
            color: rgba(255,255,255,120);
            border-color: rgba(255,255,255,30);
        }
        QPushButton:hover { color: white; }
    """

    def __init__(self, parent, model, thread_pool, resolve_path_fn: Callable):
        super().__init__(parent)
        self._model       = model
        self._pool        = thread_pool
        self._resolve     = resolve_path_fn
        self._tab         = -1
        self._alt_widgets: List[StripThumb] = []
        self._thumb_cats:  List[str]        = []
        self._active_cats: Set[str]         = set()
        self._cats_chips:  List[QPushButton]= []
        self._slideshow_states: Dict        = {}
        self.speeds = [2000, 1000, 500, 250]
        self._last_page_idx = -1
        self._last_num_variants = -1
        self._last_chapter = ""

        self._video_path: str          = ""
        self._total_frames: int        = 0
        self._current_frame_page: int  = 0
        self._frame_thumbs: Dict       = {}
        self._active_frame_worker      = None
        self._needs_frame_load: bool   = False

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(0,0,0,170);")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")

        # ── Page 0: alts ────────────────────────────────────────────────────
        alts_page = QWidget()
        alts_page.setStyleSheet("background: transparent;")
        alts_l = QVBoxLayout(alts_page)
        alts_l.setContentsMargins(0, 0, 0, 0)
        alts_l.setSpacing(4)

        # Cats row: [play][refine][edit] | [chip1][chip2]…
        # Cats row: [chip1][chip2]… (stretch) | [play][refine][edit]
        self._cats_row = QWidget()
        self._cats_row.setStyleSheet("background: transparent;")
        self._cats_row.setFixedHeight(self.HEIGHT_CATS)
        cats_l = QHBoxLayout(self._cats_row)
        cats_l.setContentsMargins(0, 0, 0, 0)
        cats_l.setSpacing(4)

        chips_scroll = HorizontalScrollArea()
        chips_scroll.setFixedHeight(self.HEIGHT_CATS)

        self._chips_content = QWidget()
        self._chips_content.setStyleSheet("background: transparent;")
        self._chips_content.setFixedHeight(self.HEIGHT_CATS)
        self._chips_hlayout = QHBoxLayout(self._chips_content)
        self._chips_hlayout.setContentsMargins(0, 0, 0, 0)
        self._chips_hlayout.setSpacing(4)
        self._chips_hlayout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        chips_scroll.setWidget(self._chips_content)

        self._play_btn = QPushButton()
        self._play_btn.setIcon(QIcon(resource_path("assets/icons/play.svg")))
        self._play_btn.setCheckable(True)
        self._play_btn.setFixedSize(28, 22)
        self._play_btn.setStyleSheet(self._BTN_STYLE)
        self._play_btn.clicked.connect(self._on_play_clicked)

        self._btn_group = QWidget()
        self._btn_group_l = QHBoxLayout(self._btn_group)
        self._btn_group_l.setContentsMargins(0, 0, 0, 0)
        self._btn_group_l.setSpacing(4)

        self._refine_btn = QPushButton()
        self._refine_btn.setIcon(QIcon(resource_path("assets/icons/auto_fix.svg")))
        self._refine_btn.setFixedSize(28, 22)
        self._refine_btn.setStyleSheet(self._BTN_STYLE)
        self._refine_btn.clicked.connect(self._on_batch_refine_clicked)

        self._edit_btn = QPushButton("✎")
        self._edit_btn.setFixedSize(28, 22)
        self._edit_btn.setStyleSheet(self._BTN_STYLE)
        self._edit_btn.clicked.connect(self._on_edit_alts_clicked)

        self._btn_group_l.addWidget(self._play_btn)
        self._btn_group_l.addWidget(self._refine_btn)
        self._btn_group_l.addWidget(self._edit_btn)

        cats_l.addWidget(chips_scroll, 1)
        cats_l.addWidget(self._btn_group)

        self._cats_row.hide()
        alts_l.addWidget(self._cats_row)

        # Thumbnails scroll
        self._alts_scroll = HorizontalScrollArea()

        self._alts_content = QWidget()
        self._alts_content.setStyleSheet("background: transparent;")
        self._alts_content.setFixedHeight(83) # 125 - 4 (bottom) - 30 (cats) - 4 (sep) - 4 (wiggle room)
        self._alts_hlayout = QHBoxLayout(self._alts_content)
        self._alts_hlayout.setContentsMargins(0, 0, 0, 0)
        self._alts_hlayout.setSpacing(6)
        self._alts_hlayout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._alts_scroll.setWidget(self._alts_content)
        alts_l.addWidget(self._alts_scroll, 1)

        self._stack.addWidget(alts_page)

        # ── Page 1: info ────────────────────────────────────────────────────
        info_page = QWidget()
        info_page.setStyleSheet("background: transparent;")
        info_l = QVBoxLayout(info_page)
        info_l.setContentsMargins(6, 0, 6, 0)
        info_l.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._info_label = QLabel("No information available.")
        self._info_label.setWordWrap(False)
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info_label.setStyleSheet("background: transparent;")
        info_l.addWidget(self._info_label)
        self._stack.addWidget(info_page)

        # ── Page 2: frames ───────────────────────────────────────────────────
        frames_page = QWidget()
        frames_page.setStyleSheet("background: transparent;")
        frames_l = QVBoxLayout(frames_page)
        frames_l.setContentsMargins(4, 4, 4, 4)
        frames_l.setSpacing(4)

        frames_nav = QWidget()
        frames_nav.setStyleSheet("background: transparent;")
        frames_nav_l = QHBoxLayout(frames_nav)
        frames_nav_l.setContentsMargins(0, 0, 0, 0)
        frames_nav_l.setSpacing(4)

        self._frame_prev_btn = QPushButton("<")
        self._frame_prev_btn.setFixedSize(22, 20)
        self._frame_prev_btn.setStyleSheet(self._BTN_STYLE)
        self._frame_prev_btn.clicked.connect(self._prev_frame_page)

        self._frame_page_label = QLabel("—")
        self._frame_page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._frame_page_label.setStyleSheet(
            "color: rgba(255,255,255,150); font-size: 10px; background: transparent;"
        )
        self._frame_page_label.setFixedWidth(50)

        self._frame_next_btn = QPushButton(">")
        self._frame_next_btn.setFixedSize(22, 20)
        self._frame_next_btn.setStyleSheet(self._BTN_STYLE)
        self._frame_next_btn.clicked.connect(self._next_frame_page)

        frames_nav_l.addStretch()
        frames_nav_l.addWidget(self._frame_prev_btn)
        frames_nav_l.addWidget(self._frame_page_label)
        frames_nav_l.addWidget(self._frame_next_btn)
        frames_nav_l.addStretch()
        frames_l.addWidget(frames_nav)

        self._frames_scroll = HorizontalScrollArea()
        self._frames_content = QWidget()
        self._frames_content.setStyleSheet("background: transparent;")
        self._frames_hlayout = QHBoxLayout(self._frames_content)
        self._frames_hlayout.setContentsMargins(0, 0, 0, 0)
        self._frames_hlayout.setSpacing(6)
        self._frames_hlayout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._frames_scroll.setWidget(self._frames_content)
        frames_l.addWidget(self._frames_scroll, 1)

        self._stack.addWidget(frames_page)

        # ── Page 3: animations ────────────────────────────────────────────────
        anim_page = QWidget()
        anim_page.setStyleSheet("background: transparent;")
        anim_l = QHBoxLayout(anim_page)
        anim_l.setContentsMargins(12, 0, 12, 0)
        anim_l.setSpacing(8)
        anim_l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        anim_label = QLabel("Animation")
        anim_label.setStyleSheet("color: rgba(255,255,255,120); font-size: 10px; background: transparent;")

        self._anim_combo = QComboBox()
        self._anim_combo.setMinimumWidth(160)
        self._anim_combo.setMaximumWidth(320)
        self._anim_combo.setFixedHeight(24)
        self._anim_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255,255,255,20);
                color: white;
                border: 1px solid rgba(255,255,255,40);
                border-radius: 3px;
                padding: 0px 6px;
                font-size: 11px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #2a2a2a;
                color: white;
                selection-background-color: rgba(74,134,232,180);
            }
        """)
        self._anim_combo.currentIndexChanged.connect(lambda i: self.anim_selected.emit(i - 1))

        self._anim_play_btn = QPushButton("⏸")
        self._anim_play_btn.setFixedSize(28, 24)
        self._anim_play_btn.setCheckable(True)
        self._anim_play_btn.setChecked(False)
        self._anim_play_btn.setStyleSheet(self._BTN_STYLE)
        self._anim_play_btn.setToolTip("Pause / Resume")
        self._anim_play_btn.clicked.connect(self._on_anim_play_clicked)

        anim_l.addWidget(anim_label)
        anim_l.addWidget(self._anim_combo)
        anim_l.addWidget(self._anim_play_btn)

        self._stack.addWidget(anim_page)

        root.addWidget(self._stack)
        self.hide()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def tab(self) -> int:
        return self._tab

    @property
    def HEIGHT(self) -> int:
        return self.FIXED_HEIGHT

    @property
    def strip_height(self) -> int:
        if not self.isVisible():
            return 0
        if self._tab == 1:
            return self.HEIGHT_INFO
        if self._tab == 3:
            return self.HEIGHT_ANIM
        return self.HEIGHT

    def toggle(self, tab: int):
        if self._tab == tab:
            self._tab = -1
            self.hide()
        else:
            self._tab = tab
            self._stack.setCurrentIndex(tab)
            if tab == 0:
                self._populate_alts()
            elif tab == 2 and self._needs_frame_load:
                self._needs_frame_load = False
                self._update_frames_ui()
            self.show()
            self.raise_()
        self.tab_changed.emit(self._tab)

    def update_geometry(self, top_h: int, width: int):
        if self._tab >= 0 and self.isVisible():
            if self._tab == 1:
                h = self.HEIGHT_INFO
            elif self._tab == 3:
                h = self.HEIGHT_ANIM
            else:
                h = self.HEIGHT
            self.setGeometry(0, top_h, width, h)
            self.raise_()
        else:
            self.setGeometry(0, top_h, width, 0)

    def on_image_loaded(self, _path: str):
        if not self._model or not self._model.images:
            return
        idx = self._model.current_index
        if not (0 <= idx < len(self._model.images)):
            return
        page = self._model.images[idx]
        num_vars = len(page.images)
        chapter = str(self._model.manga_dir)
        has_alts = num_vars > 1
        self.has_alts_changed.emit(has_alts)

        if not has_alts and self._tab == 0:
            self.toggle(0)
            return

        if self._tab == 0:
            if (idx == self._last_page_idx and 
                chapter == self._last_chapter and 
                num_vars == self._last_num_variants):
                self._update_selection()
            else:
                self._populate_alts()
                self._last_page_idx = idx
                self._last_num_variants = num_vars
                self._last_chapter = chapter

    def _update_selection(self):
        """Quickly updates the selected state of existing thumbnails without repopulating."""
        idx = self._model.current_index
        if not (0 <= idx < len(self._model.images)):
            return
        page = self._model.images[idx]
        v_idx = page.current_variant_index
        for i, thumb in enumerate(self._alt_widgets):
            if hasattr(thumb, '_v_idx'):
                thumb.set_selected(thumb._v_idx == v_idx)

    def set_info_text(self, raw_text: str):
        self._info_label.setText(format_image_info_html(raw_text))

    # ── Frames ────────────────────────────────────────────────────────────────

    def set_video(self, path: str, total_frames: int, initial_frames: dict = None):
        if self._video_path == path and self._total_frames == total_frames:
            if initial_frames:
                self._apply_frame_images(initial_frames)
            return
        self._video_path = path
        self._total_frames = total_frames
        self._current_frame_page = 0
        if self._tab != 2:
            self._needs_frame_load = True
            return
        self._update_frames_ui(initial_frames=initial_frames)

    def clear_video(self):
        self._video_path = ""
        self._total_frames = 0
        self._current_frame_page = 0
        self._needs_frame_load = False
        self._clear_frame_thumbs()

    # ── Animations ────────────────────────────────────────────────────────────

    def show_animations(self, names: list):
        self._anim_combo.blockSignals(True)
        self._anim_combo.clear()
        self._anim_combo.addItem("Static Pose")
        self._anim_combo.addItems(names)
        # Select first real animation by default
        if names:
            self._anim_combo.setCurrentIndex(1)
        self._anim_combo.blockSignals(False)
        self._anim_play_btn.setChecked(False)
        self._anim_play_btn.setText("⏸")
        if self._tab != 3:
            self._tab = 3
            self._stack.setCurrentIndex(3)
            self.show()
            self.raise_()
            self.tab_changed.emit(3)

    def hide_animations(self):
        if self._tab == 3:
            self._tab = -1
            self.hide()
            self.tab_changed.emit(-1)

    def _on_anim_play_clicked(self, checked: bool):
        paused = checked
        self._anim_play_btn.setText("▶" if paused else "⏸")
        self.anim_paused.emit(paused)

    def _update_frames_ui(self, initial_frames: dict = None):
        self._clear_frame_thumbs()
        if not self._video_path or self._total_frames <= 0:
            return

        total_pages = (self._total_frames + FRAME_STRIP_PAGE_SIZE - 1) // FRAME_STRIP_PAGE_SIZE
        self._frame_page_label.setText(f"{self._current_frame_page + 1}/{total_pages}")
        self._frame_prev_btn.setEnabled(self._current_frame_page > 0)
        self._frame_next_btn.setEnabled(self._current_frame_page < total_pages - 1)

        start = self._current_frame_page * FRAME_STRIP_PAGE_SIZE
        end = min(start + FRAME_STRIP_PAGE_SIZE, self._total_frames)
        indices = list(range(start, end))

        for idx in indices:
            thumb = FrameThumb(self._frames_content, idx, on_click=self.seek_requested.emit)
            self._frames_hlayout.addWidget(thumb)
            self._frame_thumbs[idx] = thumb

        if initial_frames and self._current_frame_page == 0:
            self._apply_frame_images(initial_frames)
            missing = [i for i in indices if i not in initial_frames]
            if not missing:
                return

        if self._pool:
            if self._active_frame_worker:
                self._active_frame_worker.cancelled = True
            to_fetch = [i for i in indices if i not in (initial_frames or {})]
            if to_fetch:
                from src.workers.view_workers import VideoBatchFrameExtractorWorker
                self._active_frame_worker = VideoBatchFrameExtractorWorker(
                    self._video_path, to_fetch, FrameThumb.W, FrameThumb.H
                )
                self._active_frame_worker.signals.finished.connect(self._on_frame_batch_extracted)
                self._pool.start(self._active_frame_worker)

    def _apply_frame_images(self, frames: dict):
        for idx, qimage in frames.items():
            if idx in self._frame_thumbs:
                self._frame_thumbs[idx].set_qimage(qimage)

    def _on_frame_batch_extracted(self, path, results, *_):
        if self._active_frame_worker and getattr(self._active_frame_worker, 'path', None) == path:
            self._active_frame_worker = None
        if path != self._video_path:
            return
        self._apply_frame_images(results)

    def _clear_frame_thumbs(self):
        for w in self._frame_thumbs.values():
            w.deleteLater()
        self._frame_thumbs.clear()

    def _prev_frame_page(self):
        if self._current_frame_page > 0:
            self._current_frame_page -= 1
            self._update_frames_ui()

    def _next_frame_page(self):
        total_pages = (self._total_frames + FRAME_STRIP_PAGE_SIZE - 1) // FRAME_STRIP_PAGE_SIZE
        if self._current_frame_page < total_pages - 1:
            self._current_frame_page += 1
            self._update_frames_ui()

    # ── Alts population ───────────────────────────────────────────────────────

    def _populate_alts(self):
        for w in self._alt_widgets:
            w.deleteLater()
        self._alt_widgets.clear()
        self._thumb_cats.clear()

        if not self._model or not self._model.images:
            return
        idx = self._model.current_index
        if not (0 <= idx < len(self._model.images)):
            return

        page = self._model.images[idx]
        if len(page.images) <= 1:
            self._cats_row.hide()
        else:
            self._cats_row.show()

        categories = page.get_categorized_variants()
        cat_names = sorted(categories.keys(),
                           key=lambda c: (0 if c == "Main" else 1, natural_sort_key(c)))

        self._update_cats_chips(cat_names)

        for cat in cat_names:
            for variant_path in categories[cat]:
                try:
                    v_idx = page.images.index(variant_path)
                except ValueError:
                    continue
                thumb = StripThumb(
                    self._alts_content,
                    on_click=lambda vi=v_idx, pi=idx: self._model.change_variant(pi, vi),
                    on_right_click=lambda pos, vp=variant_path, pi=idx: self._show_context_menu(pi, vp, pos),
                    is_selected=(v_idx == page.current_variant_index),
                )
                thumb._v_idx = v_idx # Store for quick selection updates
                self._alts_hlayout.addWidget(thumb)
                self._alt_widgets.append(thumb)
                self._thumb_cats.append(cat)
                self._load_thumb(thumb, self._resolve(variant_path))

        self._apply_cat_filter()

    def _update_cats_chips(self, cat_names: List[str]):
        for w in self._cats_chips:
            w.deleteLater()
        self._cats_chips.clear()

        if not cat_names:
            self._cats_row.hide()
            return

        previous_cats = {getattr(b, '_cat', None) for b in self._cats_chips}
        new_cats = set(cat_names) - previous_cats
        
        self._active_cats = (self._active_cats & set(cat_names)) | new_cats

        for cat in cat_names:
            btn = QPushButton(cat.upper())
            btn._cat = cat
            btn.setCheckable(True)
            btn.setChecked(cat in self._active_cats)
            btn.setFixedHeight(20)
            btn.setStyleSheet(self._CHIP_STYLE)
            btn.clicked.connect(lambda checked, c=cat: self._on_chip_toggled(c, checked))
            self._chips_hlayout.addWidget(btn)
            self._cats_chips.append(btn)

        self._cats_row.show()

    def _on_chip_toggled(self, cat: str, checked: bool):
        if checked:
            self._active_cats.add(cat)
        else:
            self._active_cats.discard(cat)
        self._apply_cat_filter()
        self.tab_changed.emit(self._tab)  # trigger geometry update

    def _apply_cat_filter(self):
        for thumb, cat in zip(self._alt_widgets, self._thumb_cats):
            thumb.setVisible(cat in self._active_cats)

    # ── Thumbnail loading ─────────────────────────────────────────────────────

    def _load_thumb(self, thumb: StripThumb, path: str):
        from src.workers.thumbnail_worker import ThumbnailWorker
        from src.utils.img_utils import load_thumbnail_from_path, load_thumbnail_from_virtual_path
        W, H = StripThumb.W, StripThumb.H

        def _load(p):
            try:
                return (load_thumbnail_from_virtual_path(p, W, H) if '|' in p
                        else load_thumbnail_from_path(p, W, H))
            except Exception:
                return None

        def _apply(_, img, w=thumb):
            if img and not img.isNull():
                try:
                    w.set_thumb(QPixmap.fromImage(img))
                except RuntimeError:
                    pass

        worker = ThumbnailWorker(0, path, _load)
        worker.signals.finished.connect(_apply)
        self._pool.start(worker)

    # ── Slideshow ─────────────────────────────────────────────────────────────

    def _on_play_clicked(self):
        if not self._model or not self._model.images:
            return
        idx = self._model.current_index
        if idx not in self._slideshow_states:
            timer = QTimer(self)
            timer.timeout.connect(lambda: self._advance_variant(idx))
            timer.start(self.speeds[0])
            self._slideshow_states[idx] = {'speed_idx': 0, 'timer': timer}
        else:
            state = self._slideshow_states[idx]
            new_idx = (state['speed_idx'] + 1) % len(self.speeds)
            state['speed_idx'] = new_idx
            state['timer'].setInterval(self.speeds[new_idx])
        self._play_btn.setChecked(True)

    def _advance_variant(self, page_index: int):
        if not self._model or not (0 <= page_index < len(self._model.images)):
            return
        page = self._model.images[page_index]
        self._model.change_variant(page_index, (page.current_variant_index + 1) % len(page.images))

    # ── Context menu ──────────────────────────────────────────────────────────

    def _show_context_menu(self, page_idx: int, variant_path: str, global_pos):
        if not self._model or not (0 <= page_idx < len(self._model.images)):
            return
        page = self._model.images[page_idx]
        if variant_path == page.images[0]:
            return

        series_path  = str(self._model.series['path'])
        chapter_name = Path(str(self._model.manga_dir)).name
        manga_dir    = Path(str(self._model.manga_dir))
        main_file    = Path(page.images[0]).name

        data       = AltManager.load_alts(series_path)
        page_entry = data.get(chapter_name, {}).get(main_file, {})
        if isinstance(page_entry, list):
            page_entry = {"alts": page_entry, "translations": {}}
        alts_list    = page_entry.get("alts", [])
        alts_fix_map = page_entry.get("alts_fix", {})

        try:
            rel_variant = str(Path(variant_path).relative_to(manga_dir)).replace('\\', '/')
        except ValueError:
            rel_variant = None

        original_rel, is_fix = None, False
        if rel_variant:
            for orig_key, fix_val in alts_fix_map.items():
                if fix_val == rel_variant:
                    original_rel, is_fix = orig_key, True
                    break
            if not is_fix and rel_variant in alts_list:
                original_rel = rel_variant
        if original_rel is None:
            vname = Path(variant_path).name
            for a in alts_list:
                if Path(a).name == vname:
                    original_rel = a
                    break
        if original_rel is None:
            return

        _menu_style = """
            QMenu { background: rgba(30,30,30,240); color: white;
                    border: 1px solid rgba(255,255,255,50); }
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background: rgba(255,255,255,40); }
            QMenu::separator { background: rgba(255,255,255,30); height: 1px; margin: 3px 8px; }
        """
        menu = QMenu(self)
        menu.setStyleSheet(_menu_style)
        refine_action      = menu.addAction("Refine Alt")
        revert_action      = menu.addAction("Revert Alt") if is_fix else None
        menu.addSeparator()
        notes_action       = menu.addAction("Edit Notes...")
        copy_notes_action  = menu.addAction("Copy Notes")

        pos    = global_pos if isinstance(global_pos, QPoint) else QPoint(global_pos)
        action = menu.exec(pos)

        if action == refine_action:
            self._open_refine_dialog(page, page_idx, variant_path, main_file,
                                     original_rel, manga_dir, series_path, chapter_name)
        elif revert_action and action == revert_action:
            AltManager.remove_alt_fix(series_path, chapter_name, main_file, original_rel)
            self.reload_requested.emit()
        elif action == notes_action:
            from src.ui.alt_panel import _AltNotesDialog
            current = AltManager.get_alt_note(series_path, chapter_name, main_file, original_rel)
            dlg = _AltNotesDialog(self, current_note=current)
            if dlg.exec():
                AltManager.save_alt_note(series_path, chapter_name, main_file, original_rel, dlg.get_note())
        elif action == copy_notes_action:
            note = AltManager.get_alt_note(series_path, chapter_name, main_file, original_rel)
            if note:
                QApplication.clipboard().setText(note)

    def _open_refine_dialog(self, page, page_idx, variant_path, main_file,
                            alt_rel_path, manga_dir, series_path, chapter_name):
        from src.ui.components.refine_alt_dialog import RefineAltDialog

        data       = AltManager.load_alts(series_path)
        page_entry = data.get(chapter_name, {}).get(main_file, {})
        if isinstance(page_entry, list):
            page_entry = {"alts": page_entry, "translations": {}}

        reference_paths = [self._resolve(page.images[0])]
        for alt_rel in page_entry.get("alts", []):
            abs_p = self._resolve(alt_rel)
            if abs_p not in reference_paths:
                reference_paths.append(abs_p)

        alt_p        = Path(alt_rel_path)
        fix_rel_path = str(alt_p.parent / (alt_p.stem + '_fix' + alt_p.suffix)).replace('\\', '/')
        output_path  = str(manga_dir / fix_rel_path)

        dlg = RefineAltDialog(
            parent=self,
            main_path=self._resolve(page.images[0]),
            alt_path=str(manga_dir / alt_rel_path),
            output_path=output_path,
            series_path=series_path,
            chapter_name=chapter_name,
            main_file=main_file,
            alt_rel_path=alt_rel_path,
            fix_rel_path=fix_rel_path,
            reference_paths=reference_paths,
        )
        if dlg.exec():
            try:
                v_idx = page.images.index(variant_path)
            except ValueError:
                v_idx = None
            if v_idx is not None:
                page.images[v_idx] = output_path
                self._model.change_variant(page_idx, v_idx)
            else:
                self.reload_requested.emit()

    # ── Batch refine ──────────────────────────────────────────────────────────

    def _on_batch_refine_clicked(self):
        if not self._model or not (0 <= self._model.current_index < len(self._model.images)):
            return
        page_idx     = self._model.current_index
        page         = self._model.images[page_idx]
        series_path  = str(self._model.series['path'])
        chapter_name = Path(str(self._model.manga_dir)).name
        manga_dir    = Path(str(self._model.manga_dir))
        main_file    = Path(page.images[0]).name

        categories  = page.get_categorized_variants()
        active_cats = self._active_cats if self._active_cats else set(categories.keys())
        cat_paths   = [p for cat in active_cats for p in categories.get(cat, [])]
        if not cat_paths:
            return

        data       = AltManager.load_alts(series_path)
        page_entry = data.get(chapter_name, {}).get(main_file, {})
        if isinstance(page_entry, list):
            page_entry = {"alts": page_entry, "translations": {}}
        fix_to_orig = {v: k for k, v in page_entry.get("alts_fix", {}).items()}

        items_data = []
        for p in cat_paths:
            if p == page.images[0]:
                continue
            try:
                rel = str(Path(p).relative_to(manga_dir)).replace('\\', '/')
            except ValueError:
                rel = None
            orig_rel = fix_to_orig.get(rel, rel)
            orig_abs = str(manga_dir / orig_rel) if orig_rel else p
            items_data.append({'alt_abs': orig_abs, 'alt_rel': orig_rel})

        if not items_data:
            return

        reference_paths = [self._resolve(page.images[0])]
        for alt_rel in page_entry.get("alts", []):
            abs_p = self._resolve(alt_rel)
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
            manga_dir=manga_dir,
        )
        if dlg.exec():
            current_v = page.current_variant_index
            self._model.update_page_variants(page_idx)
            new_page = self._model.images[page_idx]
            self._model.change_variant(page_idx, min(current_v, len(new_page.images) - 1))

    # ── Edit alts ─────────────────────────────────────────────────────────────

    def _on_edit_alts_clicked(self):
        if not self._model:
            return
        idx = self._model.current_index
        if not (0 <= idx < len(self._model.images)):
            return
        page = self._model.images[idx]
        if not page or len(page.images) <= 1:
            return
        from src.ui.components.edit_alts_dialog import EditAltsDialog
        dialog = EditAltsDialog(self, page, self._model)
        if dialog.exec():
            self.reload_requested.emit()
