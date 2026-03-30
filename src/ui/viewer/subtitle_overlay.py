import os
import re

from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt


class SubtitleOverlay:
    """Loads an SMI subtitle file and displays subtitles as a floating label
    above the video control panel."""

    def __init__(self, reader_view):
        self._reader_view = reader_view
        self._label: QLabel | None = None
        self._subtitles: list[tuple[int, int, str]] = []  # (start_ms, end_ms, text)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, video_path: str):
        """Parse the .smi file that sits next to *video_path*, if any."""
        self._subtitles = []
        if '|' in video_path:
            return
        smi_path = os.path.splitext(video_path)[0] + '.smi'
        if not os.path.isfile(smi_path):
            return
        self._subtitles = self._parse_smi(smi_path)
        if not self._subtitles and self._label:
            self._label.hide()

    def update(self, position_ms: int):
        """Show the subtitle for *position_ms*, or hide if none applies."""
        if not self._subtitles:
            if self._label and self._label.isVisible():
                self._label.hide()
            return

        text = ''
        for start, end, t in self._subtitles:
            if start <= position_ms < end:
                text = t
                break

        if text:
            self._ensure_widget()
            self._label.setText(text)
            self._label.adjustSize()
            self._reposition()
            self._label.show()
            self._label.raise_()
        elif self._label:
            self._label.hide()

    def reposition(self):
        """Re-place the label (call on resize or control-panel move)."""
        if self._label and self._label.isVisible():
            self._reposition()

    def hide(self):
        if self._label:
            self._label.hide()
        self._subtitles = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_widget(self):
        if self._label is not None:
            return
        self._label = QLabel(self._reader_view)
        self._label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self._label.setStyleSheet(
            "QLabel { background-color: rgba(0,0,0,180); color: white; "
            "font-size: 16pt; font-weight: bold; padding: 6px 14px; border-radius: 4px; }"
        )
        self._label.hide()

    def _reposition(self):
        panel = self._reader_view.video_control_panel
        max_w = int(self._reader_view.width() * 0.85)
        if self._label.width() > max_w:
            self._label.setFixedWidth(max_w)
            self._label.adjustSize()
        else:
            self._label.setMaximumWidth(max_w)

        w, h = self._label.width(), self._label.height()
        x = (self._reader_view.width() - w) // 2
        y = panel.y() - h - 8
        self._label.setGeometry(x, y, w, h)

    def _parse_smi(self, smi_path: str) -> list[tuple[int, int, str]]:
        content = None
        for enc in ('utf-8-sig', 'utf-8', 'cp949', 'euc-kr', 'latin-1'):
            try:
                with open(smi_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if not content:
            return []

        syncs = re.findall(
            r'<SYNC\s+Start\s*=\s*(\d+)[^>]*>(.*?)(?=<SYNC|\Z)',
            content, re.IGNORECASE | re.DOTALL,
        )
        entries = []
        for i, (start_str, body) in enumerate(syncs):
            start_ms = int(start_str)
            end_ms = int(syncs[i + 1][0]) if i + 1 < len(syncs) else start_ms + 5000

            p_match = re.search(r'<P[^>]*>(.*?)(?:</P>|$)', body, re.IGNORECASE | re.DOTALL)
            raw = p_match.group(1) if p_match else body
            raw = re.sub(r'<br\s*/?>', '\n', raw, flags=re.IGNORECASE)
            raw = re.sub(r'<[^>]+>', '', raw)
            raw = (raw.replace('&nbsp;', '').replace('&amp;', '&')
                      .replace('&lt;', '<').replace('&gt;', '>').strip())
            raw = re.sub(r'[ \t]+', ' ', raw)

            if raw:
                entries.append((start_ms, end_ms, raw))
        return entries
