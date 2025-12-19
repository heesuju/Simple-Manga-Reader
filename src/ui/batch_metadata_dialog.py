from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QCompleter,
    QDialogButtonBox
)
from PyQt6.QtCore import QStringListModel, Qt

from src.ui.components.csv_completer import CsvCompleter

class BatchMetadataDialog(QDialog):
    def __init__(self, library_manager, parent=None):
        super().__init__(parent)
        self.library_manager = library_manager

        self.setWindowTitle("Batch Apply Metadata")
        self.layout = QVBoxLayout(self)

        # Authors input
        self.authors_label = QLabel("Authors (comma-separated):")
        self.authors_input = QLineEdit()
        self.layout.addWidget(self.authors_label)
        self.layout.addWidget(self.authors_input)

        # Genres input
        self.genres_label = QLabel("Genres (comma-separated):")
        self.genres_input = QLineEdit()
        self.layout.addWidget(self.genres_label)
        self.layout.addWidget(self.genres_input)

        # Themes input
        self.themes_label = QLabel("Themes (comma-separated):")
        self.themes_input = QLineEdit()
        self.layout.addWidget(self.themes_label)
        self.layout.addWidget(self.themes_input)

        # Formats input
        self.formats_label = QLabel("Formats (comma-separated):")
        self.formats_input = QLineEdit()
        self.layout.addWidget(self.formats_label)
        self.layout.addWidget(self.formats_input)

        # Setup completers
        self.setup_completers()

        # OK and Cancel buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

    def setup_completers(self):
        all_authors = self.library_manager.get_all_authors()
        author_completer = CsvCompleter(all_authors, self)
        self.authors_input.setCompleter(author_completer)

        all_genres = self.library_manager.get_all_genres()
        genre_completer = CsvCompleter(all_genres, self)
        self.genres_input.setCompleter(genre_completer)

        all_themes = self.library_manager.get_all_themes()
        theme_completer = CsvCompleter(all_themes, self)
        self.themes_input.setCompleter(theme_completer)

        all_formats = self.library_manager.get_all_formats()
        format_completer = CsvCompleter(all_formats, self)
        self.formats_input.setCompleter(format_completer)

    def get_metadata(self):
        authors = [author.strip() for author in self.authors_input.text().split(',') if author.strip()]
        genres = [genre.strip() for genre in self.genres_input.text().split(',') if genre.strip()]
        themes = [theme.strip() for theme in self.themes_input.text().split(',') if theme.strip()]
        formats = [format.strip() for format in self.formats_input.text().split(',') if format.strip()]
        return {'authors': authors, 'genres': genres, 'themes': themes, 'formats': formats}
