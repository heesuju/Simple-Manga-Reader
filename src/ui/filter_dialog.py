
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QScrollArea, QWidget, QCheckBox, QLabel

class FilterDialog(QDialog):
    def __init__(self, all_authors, all_genres, all_themes, all_formats, current_filters, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filter Library")
        self.layout = QVBoxLayout(self)

        # Authors
        self.authors_label = QLabel("Authors")
        self.authors_scroll = QScrollArea()
        self.authors_widget = QWidget()
        self.authors_layout = QVBoxLayout(self.authors_widget)
        self.authors_scroll.setWidgetResizable(True)
        self.authors_scroll.setWidget(self.authors_widget)
        self.layout.addWidget(self.authors_label)
        self.layout.addWidget(self.authors_scroll)

        # Genres
        self.genres_label = QLabel("Genres")
        self.genres_scroll = QScrollArea()
        self.genres_widget = QWidget()
        self.genres_layout = QVBoxLayout(self.genres_widget)
        self.genres_scroll.setWidgetResizable(True)
        self.genres_scroll.setWidget(self.genres_widget)
        self.layout.addWidget(self.genres_label)
        self.layout.addWidget(self.genres_scroll)

        # Themes
        self.themes_label = QLabel("Themes")
        self.themes_scroll = QScrollArea()
        self.themes_widget = QWidget()
        self.themes_layout = QVBoxLayout(self.themes_widget)
        self.themes_scroll.setWidgetResizable(True)
        self.themes_scroll.setWidget(self.themes_widget)
        self.layout.addWidget(self.themes_label)
        self.layout.addWidget(self.themes_scroll)

        # Formats
        self.formats_label = QLabel("Formats")
        self.formats_scroll = QScrollArea()
        self.formats_widget = QWidget()
        self.formats_layout = QVBoxLayout(self.formats_widget)
        self.formats_scroll.setWidgetResizable(True)
        self.formats_scroll.setWidget(self.formats_widget)
        self.layout.addWidget(self.formats_label)
        self.layout.addWidget(self.formats_scroll)

        # Buttons
        self.button_layout = QHBoxLayout()
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply_filters)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.button_layout.addWidget(self.apply_button)
        self.button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(self.button_layout)

        self.populate_filters(all_authors, all_genres, all_themes, all_formats, current_filters)

    def populate_filters(self, all_authors, all_genres, all_themes, all_formats, current_filters):
        # Authors
        self.author_checkboxes = []
        for author in all_authors:
            checkbox = QCheckBox(author)
            if author in current_filters.get('authors', []):
                checkbox.setChecked(True)
            self.authors_layout.addWidget(checkbox)
            self.author_checkboxes.append(checkbox)

        # Genres
        self.genre_checkboxes = []
        for genre in all_genres:
            checkbox = QCheckBox(genre)
            if genre in current_filters.get('genres', []):
                checkbox.setChecked(True)
            self.genres_layout.addWidget(checkbox)
            self.genre_checkboxes.append(checkbox)

        # Themes
        self.theme_checkboxes = []
        for theme in all_themes:
            checkbox = QCheckBox(theme)
            if theme in current_filters.get('themes', []):
                checkbox.setChecked(True)
            self.themes_layout.addWidget(checkbox)
            self.theme_checkboxes.append(checkbox)

        # Formats
        self.format_checkboxes = []
        for format_item in all_formats:
            checkbox = QCheckBox(format_item)
            if format_item in current_filters.get('formats', []):
                checkbox.setChecked(True)
            self.formats_layout.addWidget(checkbox)
            self.format_checkboxes.append(checkbox)

    def get_selected_filters(self):
        selected_authors = [cb.text() for cb in self.author_checkboxes if cb.isChecked()]
        selected_genres = [cb.text() for cb in self.genre_checkboxes if cb.isChecked()]
        selected_themes = [cb.text() for cb in self.theme_checkboxes if cb.isChecked()]
        selected_formats = [cb.text() for cb in self.format_checkboxes if cb.isChecked()]
        return {'authors': selected_authors, 'genres': selected_genres, 'themes': selected_themes, 'formats': selected_formats}

    def apply_filters(self):
        self.accept()
