from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, pyqtSignal
from src.utils.manga_utils import get_manga_dex_author

class ResultWidget(QWidget):
    clicked = pyqtSignal(dict)

    def __init__(self, manga_info, cover_path, parent=None):
        super().__init__(parent)
        self.manga_info = manga_info
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        
        self.cover_label = QLabel()
        if cover_path:
            pixmap = QPixmap(cover_path)
            self.cover_label.setPixmap(pixmap.scaled(150, 225, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.title_label = QLabel(manga_info['attributes']['title'].get('en', 'No Title'))
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Authors
        creator_ids = set()
        for rel in manga_info.get("relationships", []):
            if rel["type"] in ("author", "artist"):
                creator_ids.add(rel["id"])
        author_names = [get_manga_dex_author(creator_id) for creator_id in creator_ids]
        self.authors_label = QLabel(f'<b>Authors:</b> {", ".join(filter(None, author_names))}')
        self.authors_label.setWordWrap(True)

        # Genres, Themes, Formats
        attributes = manga_info.get("attributes", {})
        genres = [tag["attributes"]["name"]["en"] for tag in attributes.get("tags", []) if tag["attributes"]["group"] == "genre"]
        self.genres_label = QLabel(f'<b>Genres:</b> {", ".join(genres)}')
        self.genres_label.setWordWrap(True)

        themes = [tag["attributes"]["name"]["en"] for tag in attributes.get("tags", []) if tag["attributes"]["group"] == "theme"]
        self.themes_label = QLabel(f'<b>Themes:</b> {", ".join(themes)}')
        self.themes_label.setWordWrap(True)

        formats = [tag["attributes"]["name"]["en"] for tag in attributes.get("tags", []) if tag["attributes"]["group"] == "format"]
        self.formats_label = QLabel(f'<b>Formats:</b> {", ".join(formats)}')
        self.formats_label.setWordWrap(True)

        layout.addWidget(self.cover_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.authors_label)
        layout.addWidget(self.genres_label)
        layout.addWidget(self.themes_label)
        layout.addWidget(self.formats_label)

    def mousePressEvent(self, event):
        self.clicked.emit(self.manga_info)
