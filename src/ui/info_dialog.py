from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QTextEdit, QFileDialog
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
from pathlib import Path
import shutil
from src.utils.manga_utils import get_info_from_manga_dex, get_manga_dex_author, get_cover_from_manga_dex
from src.ui.selection_dialog import SelectionDialog

class InfoDialog(QDialog):
    def __init__(self, series, library_manager, parent=None):
        super().__init__(parent)
        self.series = series
        self.library_manager = library_manager
        self.fetched_info = {}

        self.setWindowTitle("Get Manga Info")
        self.layout = QVBoxLayout(self)

        # Title input
        self.title_input = QLineEdit(series['name'])
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_info)

        title_layout = QHBoxLayout()
        title_layout.addWidget(self.title_input)
        title_layout.addWidget(self.search_button)
        self.layout.addLayout(title_layout)

        # Cover art display
        self.cover_label = QLabel()
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.cover_label)

        cover_path_layout = QHBoxLayout()
        self.cover_path_input = QLineEdit()
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_for_cover)
        cover_path_layout.addWidget(self.cover_path_input)
        cover_path_layout.addWidget(self.browse_button)
        self.layout.addLayout(cover_path_layout)

        self.load_current_cover()

        # Info display
        self.description_label = QLabel("Description:")
        self.description_text = QTextEdit()
        self.description_text.setText(series.get('description', ''))
        self.genres_label = QLabel("Genres:")
        self.genres_input = QLineEdit(", ".join(series.get('genres', [])))
        self.themes_label = QLabel("Themes:")
        self.themes_input = QLineEdit(", ".join(series.get('themes', [])))
        self.formats_label = QLabel("Formats:")
        self.formats_input = QLineEdit(", ".join(series.get('formats', [])))
        self.authors_label = QLabel("Authors:")
        self.authors_input = QLineEdit(", ".join(series.get('authors', [])))

        self.layout.addWidget(self.description_label)
        self.layout.addWidget(self.description_text)
        self.layout.addWidget(self.genres_label)
        self.layout.addWidget(self.genres_input)
        self.layout.addWidget(self.themes_label)
        self.layout.addWidget(self.themes_input)
        self.layout.addWidget(self.formats_label)
        self.layout.addWidget(self.formats_input)
        self.layout.addWidget(self.authors_label)
        self.layout.addWidget(self.authors_input)

        # Save button
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_info)
        self.layout.addWidget(self.save_button)

    def load_current_cover(self):
        cover_path = self.series.get('cover_image')
        if cover_path and Path(cover_path).exists():
            self.cover_path_input.setText(cover_path)
            pixmap = QPixmap(cover_path)
            self.cover_label.setPixmap(pixmap.scaled(200, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def browse_for_cover(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Cover Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)")
        if file_path:
            self.cover_path_input.setText(file_path)
            pixmap = QPixmap(file_path)
            self.cover_label.setPixmap(pixmap.scaled(200, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def search_info(self):
        title = self.title_input.text()
        if not title:
            return

        manga_list = get_info_from_manga_dex(title)
        if not manga_list:
            return

        if len(manga_list) == 1:
            self.populate_fields(manga_list[0])
        else:
            selection_dialog = SelectionDialog(manga_list, self)
            selection_dialog.manga_selected.connect(self.populate_fields)
            selection_dialog.exec()

    def populate_fields(self, info):
        self.fetched_info['title'] = self.title_input.text()

        attributes = info.get("attributes", {})
        description = attributes.get("description", {}).get("en", "No description available.")
        self.description_text.setText(description)
        self.fetched_info['description'] = description

        genres = [tag["attributes"]["name"]["en"] for tag in attributes.get("tags", []) if tag["attributes"]["group"] == "genre"]
        self.genres_input.setText(", ".join(genres))
        self.fetched_info['genres'] = genres

        themes = [tag["attributes"]["name"]["en"] for tag in attributes.get("tags", []) if tag["attributes"]["group"] == "theme"]
        self.themes_input.setText(", ".join(themes))
        self.fetched_info['themes'] = themes

        formats = [tag["attributes"]["name"]["en"] for tag in attributes.get("tags", []) if tag["attributes"]["group"] == "format"]
        self.formats_input.setText(", ".join(formats))
        self.fetched_info['formats'] = formats

        creator_ids = set()
        for rel in info.get("relationships", []):
            if rel["type"] in ("author", "artist"):
                creator_ids.add(rel["id"])

        author_names = [get_manga_dex_author(creator_id) for creator_id in creator_ids]
        self.authors_input.setText(", ".join(filter(None, author_names)))
        self.fetched_info['authors'] = author_names

        # Cover art
        cover_filename = None
        for rel in info.get('relationships', []):
            if rel['type'] == 'cover_art':
                cover_filename = rel['attributes']['fileName']
                break
        
        if cover_filename:
            cover_path = get_cover_from_manga_dex(info['id'], cover_filename)
            if cover_path:
                self.cover_path_input.setText(cover_path)
                pixmap = QPixmap(cover_path)
                self.cover_label.setPixmap(pixmap.scaled(200, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def save_info(self):
        new_info = {
            'description': self.description_text.toPlainText(),
            'authors': [author.strip() for author in self.authors_input.text().split(',') if author.strip()],
            'genres': [genre.strip() for genre in self.genres_input.text().split(',') if genre.strip()],
            'themes': [theme.strip() for theme in self.themes_input.text().split(',') if theme.strip()],
            'formats': [format.strip() for format in self.formats_input.text().split(',') if format.strip()]
        }

        # Save cover image
        new_cover_path = self.cover_path_input.text()
        if new_cover_path and new_cover_path != self.series.get('cover_image'):
            source_path = Path(new_cover_path)
            if source_path.exists():
                series_path = Path(self.series['path'])
                series_path.mkdir(exist_ok=True)
                dest_filename = f"cover{source_path.suffix}"
                dest_path = series_path / dest_filename
                try:
                    shutil.copy(str(source_path), str(dest_path))
                    new_info['cover_image'] = str(dest_path)
                except Exception as e:
                    print(f"Error saving cover image: {e}")
        
        self.library_manager.update_series_info(self.series['id'], new_info)
        self.accept()
