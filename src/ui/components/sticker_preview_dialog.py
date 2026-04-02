import io
import numpy as np
from PIL import Image

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QSlider, QLabel, QWidget, QSizePolicy, QApplication
)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, pyqtSignal
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QBrush, QPen, QImage, QCursor
)

_CHECKER_SIZE = 12
_INCLUDE_COLOR = QColor(0, 220, 80, 150)
_EXCLUDE_COLOR = QColor(220, 40, 40, 150)
_ERASE_ALPHA   = 0  # erase writes 0 to hints


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


class _StickerCanvas(QWidget):
    """Interactive canvas: displays the sticker result and lets user paint fg/bg hints."""

    def __init__(self, original_pil: Image.Image, result_pil: Image.Image, parent=None):
        super().__init__(parent)
        self.original_pil = original_pil.convert("RGBA")
        self.result_pil   = result_pil.convert("RGBA")
        # result without border kept separately so toggling doesn't stack borders
        self.result_no_border_pil = self.result_pil
        self.img_w = original_pil.width
        self.img_h = original_pil.height

        # Numpy hint array: 0=none, 1=include(fg), 2=exclude(bg)
        self.hints = np.zeros((self.img_h, self.img_w), dtype=np.uint8)

        # QImage painted incrementally for display (same res as image)
        self._hint_qimage = QImage(self.img_w, self.img_h, QImage.Format.Format_ARGB32)
        self._hint_qimage.fill(Qt.GlobalColor.transparent)

        self._result_qimage = _pil_to_qimage(self.result_pil)

        self.mode       = "include"   # "include" | "exclude" | "erase"
        self.brush_size = 16
        self.drawing    = False
        self._last_img_pos = None

        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(300, 300)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def _display_rect(self) -> QRect:
        w, h = self.width(), self.height()
        scale = min(w / self.img_w, h / self.img_h)
        dw = int(self.img_w * scale)
        dh = int(self.img_h * scale)
        return QRect((w - dw) // 2, (h - dh) // 2, dw, dh)

    def _to_img_coords(self, widget_pos: QPoint):
        r = self._display_rect()
        if r.width() == 0 or r.height() == 0:
            return None
        ix = (widget_pos.x() - r.x()) * self.img_w // r.width()
        iy = (widget_pos.y() - r.y()) * self.img_h // r.height()
        return (
            max(0, min(self.img_w - 1, ix)),
            max(0, min(self.img_h - 1, iy)),
        )

    # ── Painting ──────────────────────────────────────────────────────────────

    def _paint_stroke(self, ix: int, iy: int):
        import cv2

        radius = max(1, self.brush_size // 2)

        # Update hint QImage
        p = QPainter(self._hint_qimage)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        if self.mode == "erase":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(Qt.GlobalColor.transparent))
        else:
            color = _INCLUDE_COLOR if self.mode == "include" else _EXCLUDE_COLOR
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
        p.drawEllipse(QPoint(ix, iy), radius, radius)
        p.end()

        # Update numpy hints array
        circle_mask = np.zeros((self.img_h, self.img_w), dtype=np.uint8)
        cv2.circle(circle_mask, (ix, iy), radius, 1, -1)
        if self.mode == "erase":
            self.hints[circle_mask > 0] = 0
        elif self.mode == "include":
            self.hints[circle_mask > 0] = 1
        else:
            self.hints[circle_mask > 0] = 2

        self.update()

    def _paint_line(self, p0, p1):
        """Interpolate strokes between two image-space points for smooth lines."""
        import cv2
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
            self._paint_stroke(ix, iy)

    # ── Mouse events ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = True
            pos = self._to_img_coords(event.pos())
            if pos:
                self._paint_stroke(*pos)
                self._last_img_pos = pos

    def mouseMoveEvent(self, event):
        if self.drawing and event.buttons() & Qt.MouseButton.LeftButton:
            pos = self._to_img_coords(event.pos())
            if pos:
                self._paint_line(self._last_img_pos, pos)
                self._last_img_pos = pos

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = False
            self._last_img_pos = None

    # ── Rendering ────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(35, 35, 35))

        rect = self._display_rect()
        _draw_checkerboard(painter, rect)
        painter.drawImage(rect, self._result_qimage)

        # Hint overlay
        painter.setOpacity(0.75)
        painter.drawImage(rect, self._hint_qimage)
        painter.setOpacity(1.0)
        painter.end()

    def resizeEvent(self, event):
        self.update()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_result(self, result_pil: Image.Image):
        self.result_pil = result_pil.convert("RGBA")
        self._result_qimage = _pil_to_qimage(self.result_pil)
        self.update()

    def clear_hints(self):
        self.hints[:] = 0
        self._hint_qimage.fill(Qt.GlobalColor.transparent)
        self.update()

    def refine(self, border: int = 8):
        """Re-segment using GrabCut with current hint strokes. Returns True on success."""
        import cv2

        orig_rgb = np.array(self.original_pil.convert("RGB"))

        # Always use the borderless rembg alpha as the GrabCut seed.
        # Using result_pil when the border is on would include white outline
        # pixels in the mask, corrupting the foreground/background priors.
        rembg_alpha = np.array(self.result_no_border_pil)[:, :, 3]

        # Seed GrabCut mask from rembg alpha, then override with user hints
        gc_mask = np.where(rembg_alpha > 10,
                           cv2.GC_PR_FGD, cv2.GC_PR_BGD).astype(np.uint8)
        gc_mask[self.hints == 1] = cv2.GC_FGD   # hard foreground
        gc_mask[self.hints == 2] = cv2.GC_BGD   # hard background

        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)

        try:
            cv2.grabCut(orig_rgb, gc_mask, None, bgd_model, fgd_model,
                        5, cv2.GC_INIT_WITH_MASK)
        except Exception as e:
            print(f"GrabCut failed: {e}")
            return False

        # Use GrabCut as a binary gate on the clean rembg alpha so that
        # soft anti-aliased edges are preserved for kept pixels.
        gc_fg = (gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD)

        new_alpha = rembg_alpha.copy()
        new_alpha[~gc_fg] = 0  # cut regions GrabCut says are background

        # Where the user painted Include, restore any alpha rembg zeroed out.
        # Cap at the rembg value so we never exceed what rembg resolved.
        new_alpha[self.hints == 1] = np.maximum(
            new_alpha[self.hints == 1],
            rembg_alpha[self.hints == 1],
        )

        orig_rgba = np.array(self.original_pil)
        orig_rgba[:, :, 3] = new_alpha
        new_result = Image.fromarray(orig_rgba, "RGBA")

        self.result_no_border_pil = new_result  # store borderless for toggle
        # Re-apply border (or skip if border=0)
        from src.core.sticker_server_manager import StickerServerManager
        bordered = StickerServerManager.instance().make_sticker(new_result, border=border)
        self.set_result(bordered if bordered is not None else new_result)
        return True


# ── Dialog ────────────────────────────────────────────────────────────────────

class StickerPreviewDialog(QDialog):
    def __init__(self, original_pil: Image.Image, result_pil: Image.Image,
                 result_no_border_pil: Image.Image = None, parent=None):
        super().__init__(parent)
        self._original_pil = original_pil
        self._result_pil = result_pil
        self._result_no_border_pil = result_no_border_pil or result_pil
        self.setWindowTitle("Sticker Preview")
        self.setMinimumSize(640, 560)
        self.resize(780, 640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        hint_label = QLabel("Paint:")
        hint_label.setStyleSheet("color: #aaa; font-size: 12px;")
        toolbar.addWidget(hint_label)

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

        self.erase_btn = QPushButton("Erase")
        self.erase_btn.setCheckable(True)
        self.erase_btn.setStyleSheet(btn_style.format(bg="#555"))
        self.erase_btn.clicked.connect(lambda: self._set_mode("erase"))
        toolbar.addWidget(self.erase_btn)

        self._mode_btns = [self.include_btn, self.exclude_btn, self.erase_btn]

        toolbar.addSpacing(12)

        brush_label = QLabel("Brush:")
        brush_label.setStyleSheet("color: #aaa; font-size: 12px;")
        toolbar.addWidget(brush_label)

        self.brush_slider = QSlider(Qt.Orientation.Horizontal)
        self.brush_slider.setRange(4, 60)
        self.brush_slider.setValue(16)
        self.brush_slider.setFixedWidth(100)
        self.brush_slider.valueChanged.connect(self._on_brush_size_changed)
        toolbar.addWidget(self.brush_slider)

        toolbar.addSpacing(16)

        border_label = QLabel("Border:")
        border_label.setStyleSheet("color: #aaa; font-size: 12px;")
        toolbar.addWidget(border_label)

        self.border_btn = QPushButton("White Outline")
        self.border_btn.setCheckable(True)
        self.border_btn.setChecked(True)
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

        clear_btn = QPushButton("Clear Hints")
        clear_btn.setStyleSheet("color: #aaa; padding: 5px 10px; background: #333; border-radius: 4px;")
        clear_btn.clicked.connect(self._clear_hints)
        toolbar.addWidget(clear_btn)

        layout.addLayout(toolbar)

        # ── Legend ────────────────────────────────────────────────────────────
        legend = QLabel(
            "<span style='color:#2ecc71;'>■</span> Include (restore area)  "
            "<span style='color:#e74c3c;'>■</span> Exclude (remove area)  "
            "<span style='color:#888;'>Paint, then click Refine to update.</span>"
        )
        legend.setStyleSheet("font-size: 11px; color: #999; margin-bottom: 2px;")
        layout.addWidget(legend)

        # ── Canvas ────────────────────────────────────────────────────────────
        self.canvas = _StickerCanvas(self._original_pil, self._result_pil, self)
        self.canvas.result_no_border_pil = self._result_no_border_pil
        layout.addWidget(self.canvas, stretch=1)

        # Apply initial border state now that canvas exists
        self._on_border_toggled(self.border_btn.isChecked())

        # ── Bottom bar ────────────────────────────────────────────────────────
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self.refine_btn = QPushButton("Refine")
        self.refine_btn.setStyleSheet("""
            QPushButton {
                background-color: #e67e22;
                border: none; color: white;
                padding: 9px 20px; border-radius: 4px;
                font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #f39c12; }
            QPushButton:pressed { background-color: #ca6f1e; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        self.refine_btn.clicked.connect(self._on_refine)
        bottom.addWidget(self.refine_btn)

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

    # ── Toolbar handlers ─────────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        self.canvas.mode = mode
        for btn, m in zip(self._mode_btns, ("include", "exclude", "erase")):
            btn.setChecked(m == mode)

    def _on_brush_size_changed(self, value: int):
        self.canvas.brush_size = value

    def _on_border_toggled(self, checked: bool):
        from src.core.sticker_server_manager import StickerServerManager
        base = self.canvas.result_no_border_pil
        if checked:
            bordered = StickerServerManager.instance().make_sticker(base, border=8)
            self.canvas.set_result(bordered if bordered is not None else base)
        else:
            self.canvas.set_result(base)

    def _clear_hints(self):
        self.canvas.clear_hints()

    def _on_refine(self):
        self.refine_btn.setEnabled(False)
        self.refine_btn.setText("Refining...")
        QApplication.processEvents()
        self.canvas.refine(border=8 if self.border_btn.isChecked() else 0)
        self.refine_btn.setEnabled(True)
        self.refine_btn.setText("Refine")

    # ── Result access ─────────────────────────────────────────────────────────

    def get_result(self) -> Image.Image:
        return self.canvas.result_pil
