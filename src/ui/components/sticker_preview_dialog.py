from PIL import Image

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QWidget, QSizePolicy
)
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QImage


_CHECKER_SIZE = 12


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
    """Displays the sticker result on a checkerboard background."""

    def __init__(self, result_pil: Image.Image, parent=None):
        super().__init__(parent)
        self.result_pil = result_pil.convert("RGBA")
        self.result_no_border_pil = self.result_pil
        self._result_qimage = _pil_to_qimage(self.result_pil)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(300, 300)

    def _display_rect(self) -> QRect:
        w, h = self.width(), self.height()
        img_w, img_h = self.result_pil.width, self.result_pil.height
        scale = min(w / img_w, h / img_h)
        dw = int(img_w * scale)
        dh = int(img_h * scale)
        return QRect((w - dw) // 2, (h - dh) // 2, dw, dh)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(35, 35, 35))
        rect = self._display_rect()
        _draw_checkerboard(painter, rect)
        painter.drawImage(rect, self._result_qimage)
        painter.end()

    def resizeEvent(self, event):
        self.update()

    def set_result(self, result_pil: Image.Image):
        self.result_pil = result_pil.convert("RGBA")
        self._result_qimage = _pil_to_qimage(self.result_pil)
        self.update()


class StickerPreviewDialog(QDialog):
    def __init__(self, result_pil: Image.Image,
                 result_no_border_pil: Image.Image = None, parent=None):
        super().__init__(parent)
        self._result_no_border_pil = result_no_border_pil or result_pil
        self.setWindowTitle("Sticker Preview")
        self.setMinimumSize(640, 520)
        self.resize(780, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

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
        layout.addLayout(toolbar)

        # ── Canvas ────────────────────────────────────────────────────────────
        self.canvas = _StickerCanvas(result_pil, self)
        self.canvas.result_no_border_pil = self._result_no_border_pil
        layout.addWidget(self.canvas, stretch=1)

        # Apply initial border state now that canvas exists
        self._on_border_toggled(self.border_btn.isChecked())

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

    def _on_border_toggled(self, checked: bool):
        from src.core.sticker_server_manager import StickerServerManager
        base = self.canvas.result_no_border_pil
        if checked:
            bordered = StickerServerManager.instance().make_sticker(base, border=8)
            self.canvas.set_result(bordered if bordered is not None else base)
        else:
            self.canvas.set_result(base)

    def get_result(self) -> Image.Image:
        return self.canvas.result_pil
