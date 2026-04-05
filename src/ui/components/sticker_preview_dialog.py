import cv2
import numpy as np
from PIL import Image

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QWidget, QSizePolicy, QSlider
)
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QImage, QPen, QBrush


_CHECKER_SIZE = 12
_INCLUDE_COLOR = QColor(0, 220, 80, 140)
_EXCLUDE_COLOR = QColor(220, 40, 40, 140)


def _pil_to_qimage(pil_img: Image.Image) -> QImage:
    pil_img = pil_img.convert("RGBA")
    data = pil_img.tobytes("raw", "RGBA")
    return QImage(data, pil_img.width, pil_img.height,
                  pil_img.width * 4, QImage.Format.Format_RGBA8888).copy()


def _draw_checkerboard(painter: QPainter, rect: QRect):
    c1, c2 = QColor(160, 160, 160), QColor(210, 210, 210)
    s = _CHECKER_SIZE
    for row in range(0, rect.height(), s):
        for col in range(0, rect.width(), s):
            color = c1 if ((col // s) + (row // s)) % 2 == 0 else c2
            painter.fillRect(
                rect.x() + col, rect.y() + row,
                min(s, rect.width() - col),
                min(s, rect.height() - row),
                color,
            )


def _expand_stroke_to_region(
    orig_rgb: np.ndarray,
    stroke_mask: np.ndarray,
    tolerance: int,
) -> np.ndarray:
    """Expand a brush stroke mask to connected similar-colored regions.

    1. Compute the mean color of pixels under the stroke.
    2. Find all pixels within `tolerance` color distance of that mean.
    3. Keep only connected components that overlap with the original stroke.
    """
    painted_pixels = orig_rgb[stroke_mask > 0]
    if len(painted_pixels) == 0:
        return stroke_mask

    mean_color = painted_pixels.mean(axis=0).astype(np.float32)

    # Color distance (Euclidean in RGB) from the mean stroke color
    diff = np.linalg.norm(
        orig_rgb.astype(np.float32) - mean_color, axis=2
    )
    similar = (diff < tolerance).astype(np.uint8) * 255

    # Connected components — only keep regions touching the stroke
    num_labels, labels = cv2.connectedComponents(similar)
    touching_labels = set(np.unique(labels[stroke_mask > 0]))
    touching_labels.discard(0)

    result = np.zeros_like(stroke_mask)
    for lbl in touching_labels:
        result[labels == lbl] = 255

    # Always include the original stroke pixels
    result[stroke_mask > 0] = 255
    return result


class _StickerCanvas(QWidget):
    """Interactive canvas: paint seed strokes that auto-expand to similar regions."""

    def __init__(self, original_pil: Image.Image, result_pil: Image.Image, parent=None):
        super().__init__(parent)
        self.original_pil = original_pil.convert("RGBA")
        self.result_pil = result_pil.convert("RGBA")
        self.result_no_border_pil = self.result_pil

        self.img_w = self.original_pil.width
        self.img_h = self.original_pil.height

        # Working alpha channel
        self._alpha = np.array(self.result_pil)[:, :, 3].copy()
        self._original_rgba = np.array(self.original_pil)
        self._original_rgb = self._original_rgba[:, :, :3].copy()

        # Undo stack
        self._undo_stack: list[np.ndarray] = []
        self._max_undo = 30

        # Stroke accumulation: collect brush dots as a mask, expand on release
        self._stroke_mask = np.zeros((self.img_h, self.img_w), dtype=np.uint8)
        self._stroke_qimage = QImage(self.img_w, self.img_h, QImage.Format.Format_ARGB32)
        self._stroke_qimage.fill(Qt.GlobalColor.transparent)

        self._result_qimage = _pil_to_qimage(self.result_pil)

        self.mode = "include"  # "include" | "exclude"
        self.brush_size = 20
        self.tolerance = 40  # color distance threshold for region expansion
        self.drawing = False
        self._last_img_pos = None
        self._stroke_dirty = False

        # Zoom & pan
        self._zoom = 1.0
        self._pan_offset = QPoint(0, 0)  # pixel offset from centered position
        self._panning = False
        self._pan_start = QPoint()

        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(300, 300)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ── Coordinate helpers ────────────────────────────────────────────────

    def _display_rect(self) -> QRect:
        w, h = self.width(), self.height()
        base_scale = min(w / self.img_w, h / self.img_h)
        scale = base_scale * self._zoom
        dw = int(self.img_w * scale)
        dh = int(self.img_h * scale)
        cx = (w - dw) // 2 + self._pan_offset.x()
        cy = (h - dh) // 2 + self._pan_offset.y()
        return QRect(cx, cy, dw, dh)

    def _to_img_coords(self, widget_pos: QPoint):
        r = self._display_rect()
        if r.width() == 0 or r.height() == 0:
            return None
        ix = (widget_pos.x() - r.x()) * self.img_w // r.width()
        iy = (widget_pos.y() - r.y()) * self.img_h // r.height()
        if 0 <= ix < self.img_w and 0 <= iy < self.img_h:
            return (ix, iy)
        return None

    # ── Stroke collection (visual only during drag) ───────────────────────

    def _add_dot(self, ix: int, iy: int):
        """Record a brush dot into the stroke mask + draw colored feedback."""
        radius = max(1, self.brush_size // 2)

        # Add to stroke mask
        cv2.circle(self._stroke_mask, (ix, iy), radius, 255, -1)

        # Visual feedback
        p = QPainter(self._stroke_qimage)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        color = _INCLUDE_COLOR if self.mode == "include" else _EXCLUDE_COLOR
        p.setBrush(QBrush(color))
        p.drawEllipse(QPoint(ix, iy), radius, radius)
        p.end()

        self._stroke_dirty = True

    def _add_line(self, p0, p1):
        if p0 is None or p1 is None:
            return
        x0, y0 = p0
        x1, y1 = p1
        dist = max(abs(x1 - x0), abs(y1 - y0))
        steps = max(1, dist // max(1, self.brush_size // 4))
        for i in range(steps + 1):
            t = i / steps
            ix = int(x0 + (x1 - x0) * t)
            iy = int(y0 + (y1 - y0) * t)
            self._add_dot(ix, iy)

    # ── Apply stroke on release ───────────────────────────────────────────

    def _commit_stroke(self):
        """Expand the stroke to similar connected region, then apply to alpha."""
        if not np.any(self._stroke_mask):
            return

        expanded = _expand_stroke_to_region(
            self._original_rgb, self._stroke_mask, self.tolerance
        )

        if self.mode == "include":
            self._alpha[expanded > 0] = self._original_rgba[expanded > 0, 3]
        else:
            self._alpha[expanded > 0] = 0

        # Rebuild result
        result = self._original_rgba.copy()
        result[:, :, 3] = self._alpha
        self.result_pil = Image.fromarray(result, "RGBA")
        self.result_no_border_pil = self.result_pil
        self._result_qimage = _pil_to_qimage(self.result_pil)

        # Clear stroke state
        self._stroke_mask[:] = 0
        self._stroke_qimage.fill(Qt.GlobalColor.transparent)
        self._stroke_dirty = False

    def _push_undo(self):
        if len(self._undo_stack) >= self._max_undo:
            self._undo_stack.pop(0)
        self._undo_stack.append(self._alpha.copy())

    def undo(self):
        if not self._undo_stack:
            return
        self._alpha = self._undo_stack.pop()
        result = self._original_rgba.copy()
        result[:, :, 3] = self._alpha
        self.result_pil = Image.fromarray(result, "RGBA")
        self.result_no_border_pil = self.result_pil
        self._result_qimage = _pil_to_qimage(self.result_pil)
        self.update()

    # ── Mouse events ─────────────────────────────────────────────────────

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            event.accept()
            return

        old_zoom = self._zoom
        factor = 1.15 if delta > 0 else 1 / 1.15
        self._zoom = max(0.5, min(10.0, self._zoom * factor))

        # Zoom anchored to the center of the image
        zoom_ratio = self._zoom / old_zoom
        self._pan_offset = QPoint(
            int(self._pan_offset.x() * zoom_ratio),
            int(self._pan_offset.y() * zoom_ratio),
        )

        self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.pos() - self._pan_offset
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self._to_img_coords(event.pos())
            if pos:
                self.drawing = True
                self._push_undo()
                self._stroke_mask[:] = 0
                self._stroke_qimage.fill(Qt.GlobalColor.transparent)
                self._add_dot(*pos)
                self._last_img_pos = pos
                self.update()

    def mouseMoveEvent(self, event):
        if self._panning:
            self._pan_offset = event.pos() - self._pan_start
            self.update()
            return
        if self.drawing and event.buttons() & Qt.MouseButton.LeftButton:
            pos = self._to_img_coords(event.pos())
            if pos:
                self._add_line(self._last_img_pos, pos)
                self._last_img_pos = pos
                self.update()
        else:
            self.update()  # for brush cursor

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        if event.button() == Qt.MouseButton.LeftButton and self.drawing:
            self.drawing = False
            self._last_img_pos = None
            self._commit_stroke()
            self.update()

    # ── Rendering ────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(35, 35, 35))

        rect = self._display_rect()
        _draw_checkerboard(painter, rect)
        painter.drawImage(rect, self._result_qimage)

        # Stroke overlay while dragging
        if self._stroke_dirty:
            painter.setOpacity(0.6)
            painter.drawImage(rect, self._stroke_qimage)
            painter.setOpacity(1.0)

        # Brush cursor circle
        mouse_pos = self.mapFromGlobal(self.cursor().pos())
        if self.rect().contains(mouse_pos):
            r = self._display_rect()
            if r.width() > 0:
                scale = r.width() / self.img_w
                radius = max(2, int(self.brush_size / 2 * scale))
                color = _INCLUDE_COLOR if self.mode == "include" else _EXCLUDE_COLOR
                painter.setPen(QPen(color, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(mouse_pos, radius, radius)

        painter.end()

    def resizeEvent(self, event):
        self.update()

    # ── Public API ────────────────────────────────────────────────────────

    def set_result(self, result_pil: Image.Image):
        self.result_pil = result_pil.convert("RGBA")
        self._result_qimage = _pil_to_qimage(self.result_pil)
        self._alpha = np.array(self.result_pil)[:, :, 3].copy()
        self.update()

    def reset_zoom(self):
        self._zoom = 1.0
        self._pan_offset = QPoint(0, 0)
        self.update()

    def reset_mask(self, rembg_result: Image.Image):
        self._undo_stack.clear()
        self.result_no_border_pil = rembg_result.convert("RGBA")
        self.set_result(rembg_result)
        self.reset_zoom()


class StickerPreviewDialog(QDialog):
    def __init__(self, original_pil: Image.Image, result_pil: Image.Image,
                 result_no_border_pil: Image.Image = None, parent=None):
        super().__init__(parent)
        self._original_pil = original_pil
        self._rembg_result = result_no_border_pil or result_pil
        self.setWindowTitle("Sticker Preview")
        self.setMinimumSize(640, 560)
        self.resize(780, 640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        btn_style = """
            QPushButton {{
                background-color: {bg};
                border: 2px solid transparent;
                color: white;
                padding: 5px 14px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:checked {{
                border: 2px solid white;
            }}
            QPushButton:hover {{ opacity: 0.85; }}
        """

        paint_label = QLabel("Paint:")
        paint_label.setStyleSheet("color: #aaa; font-size: 12px;")
        toolbar.addWidget(paint_label)

        self.include_btn = QPushButton("Include")
        self.include_btn.setCheckable(True)
        self.include_btn.setChecked(True)
        self.include_btn.setStyleSheet(btn_style.format(bg="#1a8f3c"))
        self.include_btn.clicked.connect(lambda: self._set_mode("include"))
        toolbar.addWidget(self.include_btn)

        self.exclude_btn = QPushButton("Exclude")
        self.exclude_btn.setCheckable(True)
        self.exclude_btn.setStyleSheet(btn_style.format(bg="#b52020"))
        self.exclude_btn.clicked.connect(lambda: self._set_mode("exclude"))
        toolbar.addWidget(self.exclude_btn)

        self._mode_btns = [self.include_btn, self.exclude_btn]

        toolbar.addSpacing(12)

        brush_label = QLabel("Brush:")
        brush_label.setStyleSheet("color: #aaa; font-size: 12px;")
        toolbar.addWidget(brush_label)

        self.brush_slider = QSlider(Qt.Orientation.Horizontal)
        self.brush_slider.setRange(4, 80)
        self.brush_slider.setValue(20)
        self.brush_slider.setFixedWidth(100)
        self.brush_slider.valueChanged.connect(self._on_brush_size_changed)
        toolbar.addWidget(self.brush_slider)

        toolbar.addSpacing(12)

        tol_label = QLabel("Sensitivity:")
        tol_label.setStyleSheet("color: #aaa; font-size: 12px;")
        toolbar.addWidget(tol_label)

        self.tolerance_slider = QSlider(Qt.Orientation.Horizontal)
        self.tolerance_slider.setRange(10, 100)
        self.tolerance_slider.setValue(40)
        self.tolerance_slider.setFixedWidth(100)
        self.tolerance_slider.valueChanged.connect(self._on_tolerance_changed)
        toolbar.addWidget(self.tolerance_slider)

        toolbar.addSpacing(16)

        border_label = QLabel("Border:")
        border_label.setStyleSheet("color: #aaa; font-size: 12px;")
        toolbar.addWidget(border_label)

        self.border_btn = QPushButton("White Outline")
        self.border_btn.setCheckable(True)
        self.border_btn.setChecked(False)
        self.border_btn.setStyleSheet("""
            QPushButton {
                background-color: #444; border: 2px solid transparent;
                color: #ccc; padding: 5px 12px; border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:checked { border: 2px solid white; color: white; background-color: #555; }
            QPushButton:hover { background-color: #555; }
        """)
        self.border_btn.toggled.connect(self._on_border_toggled)
        toolbar.addWidget(self.border_btn)

        toolbar.addStretch()

        reset_btn = QPushButton("Reset")
        reset_btn.setStyleSheet("color: #aaa; padding: 5px 10px; background: #333; border-radius: 4px;")
        reset_btn.clicked.connect(self._reset)
        toolbar.addWidget(reset_btn)

        layout.addLayout(toolbar)

        # ── Legend ────────────────────────────────────────────────────────────
        legend = QLabel(
            "<span style='color:#2ecc71;'>&#9632;</span> Include (restore area) &nbsp;"
            "<span style='color:#e74c3c;'>&#9632;</span> Exclude (remove area) &nbsp;"
            "<span style='color:#888;'>Ctrl+Z to undo &middot; Paint a rough stroke — it auto-selects similar regions</span>"
        )
        legend.setStyleSheet("font-size: 11px; color: #999; margin-bottom: 2px;")
        layout.addWidget(legend)

        # ── Canvas ────────────────────────────────────────────────────────────
        self.canvas = _StickerCanvas(self._original_pil, result_pil, self)
        layout.addWidget(self.canvas, stretch=1)

        # ── Bottom bar ────────────────────────────────────────────────────────
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("color: #ff5555; padding: 9px 16px; background: transparent; border: none; font-weight: bold;")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)

        self.save_btn = QPushButton("Save Sticker")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #7b2fff;
                border: none; color: white;
                padding: 9px 24px; border-radius: 4px;
                font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #9147ff; }
            QPushButton:pressed { background-color: #6a1fd4; }
        """)
        self.save_btn.clicked.connect(self.accept)
        bottom.addWidget(self.save_btn)

        layout.addLayout(bottom)

    def keyPressEvent(self, event):
        from PyQt6.QtGui import QKeySequence
        if event.matches(QKeySequence.StandardKey.Undo):
            self.canvas.undo()
            return
        super().keyPressEvent(event)

    def _set_mode(self, mode: str):
        self.canvas.mode = mode
        for btn, m in zip(self._mode_btns, ("include", "exclude")):
            btn.setChecked(m == mode)

    def _on_brush_size_changed(self, value: int):
        self.canvas.brush_size = value

    def _on_tolerance_changed(self, value: int):
        self.canvas.tolerance = value

    def _on_border_toggled(self, checked: bool):
        from src.core.sticker_server_manager import StickerServerManager
        base = self.canvas.result_no_border_pil
        if checked:
            bordered = StickerServerManager.instance().make_sticker(base, border=8)
            self.canvas.set_result(bordered if bordered is not None else base)
        else:
            self.canvas.set_result(base)

    def _reset(self):
        self.canvas.reset_mask(self._rembg_result)

    def get_result(self) -> Image.Image:
        return self.canvas.result_pil
