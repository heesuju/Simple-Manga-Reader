from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QTextEdit
)
from src.utils.manga_utils import get_info_from_manga_dex, get_manga_dex_author

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

        # Info display
        self.description_label = QLabel("Description:")
        self.description_text = QTextEdit()
        self.description_text.setText(series.get('description', ''))
        self.genres_label = QLabel("Genres:")
        self.genres_input = QLineEdit(", ".join(series.get('genres', [])))
        self.authors_label = QLabel("Authors:")
        self.authors_input = QLineEdit(", ".join(series.get('authors', [])))

        self.layout.addWidget(self.description_label)
        self.layout.addWidget(self.description_text)
        self.layout.addWidget(self.genres_label)
        self.layout.addWidget(self.genres_input)
        self.layout.addWidget(self.authors_label)
        self.layout.addWidget(self.authors_input)

        # Save button
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_info)
        self.layout.addWidget(self.save_button)

    def search_info(self):
        title = self.title_input.text()
        if not title:
            return

        info = get_info_from_manga_dex(title)
        if info:
            self.fetched_info['title'] = self.title_input.text()

            attributes = info.get("attributes", {})
            description = attributes.get("description", {}).get("en", "No description available.")
            self.description_text.setText(description)
            self.fetched_info['description'] = description

            genres = [tag["attributes"]["name"]["en"] for tag in attributes.get("tags", []) if tag["attributes"]["group"] == "genre"]
            self.genres_input.setText(", ".join(genres))
            self.fetched_info['genres'] = genres

            author_ids = [rel["id"] for rel in info.get("relationships", []) if rel["type"] == "author"]
            author_names = [get_manga_dex_author(author_id) for author_id in author_ids]
            self.authors_input.setText(", ".join(filter(None, author_names)))
            self.fetched_info['authors'] = author_names

    def save_info(self):
        new_info = {
            'description': self.description_text.toPlainText(),
            'authors': [author.strip() for author in self.authors_input.text().split(',') if author.strip()],
            'genres': [genre.strip() for genre in self.genres_input.text().split(',') if genre.strip()]
        }
        self.library_manager.update_series_info(self.series['id'], new_info)
        self.accept()
