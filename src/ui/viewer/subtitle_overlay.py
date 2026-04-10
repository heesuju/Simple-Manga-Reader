import os
import re

from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt

import src.utils.app_settings as app_settings

FONT_SIZES = {'Small': 16, 'Normal': 24, 'Big': 36}


class SubtitleOverlay:
    """Loads an SMI subtitle file and displays subtitles as a floating label
    above the video control panel."""

    def __init__(self, reader_view):
        self._reader_view = reader_view
        self._label: QLabel | None = None
        self._subtitles: list[tuple[int, int, str]] = []  # (start_ms, end_ms, text)
        self._font_size: int = app_settings.get("subtitle_font_size", 16)
        self._delay_s: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def has_subtitles(self) -> bool:
        return bool(self._subtitles)

    @property
    def font_size(self) -> int:
        return self._font_size

    @property
    def delay_s(self) -> float:
        return self._delay_s

    def set_font_size(self, size: int):
        self._font_size = size
        app_settings.set("subtitle_font_size", size)
        if self._label:
            self._label.setStyleSheet(self._make_stylesheet())
            self._label.adjustSize()
            if self._label.isVisible():
                self._reposition()

    def set_delay(self, delay_s: float):
        self._delay_s = delay_s

    def load(self, video_path: str):
        """Parse the .smi or .srt file that sits next to *video_path*, if any."""
        self._subtitles = []
        if '|' in video_path:
            return
            
        base_path = os.path.splitext(video_path)[0]
        smi_path = base_path + '.smi'
        srt_path = base_path + '.srt'
        
        if os.path.isfile(smi_path):
            self._subtitles = self._parse_smi(smi_path)
        elif os.path.isfile(srt_path):
            self._subtitles = self._parse_srt(srt_path)
            
        if not self._subtitles and self._label:
            self._label.hide()

    def update(self, position_ms: int):
        """Show the subtitle for *position_ms*, or hide if none applies."""
        if not self._subtitles:
            if self._label and self._label.isVisible():
                self._label.hide()
            return

        effective_ms = position_ms + int(self._delay_s * 1000)
        active_texts = []
        for start, end, t in self._subtitles:
            if start <= effective_ms < end:
                active_texts.append(t)

        text = '\n'.join(active_texts)

        if text:
            self._ensure_widget()
            self._label.setText(text)
            self._label.adjustSize()
            self._reposition()
            self._label.show()
            self._label.raise_()
        elif self._label:
            self._label.hide()

    def hide(self):
        if self._label:
            self._label.hide()
        self._subtitles = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_stylesheet(self) -> str:
        return (
            f"QLabel {{ background-color: rgba(0,0,0,180); color: white; "
            f"font-size: {self._font_size}pt; font-weight: bold; "
            f"padding: 6px 14px; border-radius: 4px; }}"
        )

    def _ensure_widget(self):
        if self._label is not None:
            return
        self._label = QLabel(self._reader_view)
        self._label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self._label.setStyleSheet(self._make_stylesheet())
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
        bottom = panel.y() - 8 if panel.isVisible() else panel.y() + panel.height()
        self._label.setGeometry(x, bottom - h, w, h)

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
                      .replace('&lt;', '<').replace('&gt;', '>'))
            # Strip each line, drop blank lines, collapse runs of spaces/tabs
            lines = [re.sub(r'[ \t]+', ' ', ln.strip()) for ln in raw.splitlines()]
            raw = '\n'.join(ln for ln in lines if ln)

            if raw:
                entries.append((start_ms, end_ms, raw))
        return entries

    def _parse_srt(self, srt_path: str) -> list[tuple[int, int, str]]:
        content = None
        for enc in ('utf-8-sig', 'utf-8', 'cp949', 'euc-kr', 'latin-1'):
            try:
                with open(srt_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if not content:
            return []

        entries = []
        # SRT blocks are separated by blank lines
        blocks = re.split(r'\n\s*\n', content.strip())
        for block in blocks:
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            if len(lines) >= 3:
                time_match = None
                text_start_idx = -1
                for i, ln in enumerate(lines):
                    time_match = re.search(r'(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})', ln)
                    if time_match:
                        text_start_idx = i + 1
                        break
                
                if time_match and text_start_idx < len(lines):
                    h1, m1, s1, ms1, h2, m2, s2, ms2 = time_match.groups()
                    start_ms = (int(h1)*3600 + int(m1)*60 + int(s1))*1000 + int(ms1)
                    end_ms = (int(h2)*3600 + int(m2)*60 + int(s2))*1000 + int(ms2)
                    
                    raw_text = '\n'.join(lines[text_start_idx:])
                    # Remove HTML-like tags commonly found in SRT
                    raw_text = re.sub(r'<[^>]+>', '', raw_text)
                    if raw_text:
                        entries.append((start_ms, end_ms, raw_text))
                        
        return entries
