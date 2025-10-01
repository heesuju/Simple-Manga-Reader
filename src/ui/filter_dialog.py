
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QScrollArea, QWidget, QCheckBox, QLabel

class FilterDialog(QDialog):
    def __init__(self, library_manager, parent=None):
        super().__init__(parent)
        self.library_manager = library_manager

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

        # Buttons
        self.button_layout = QHBoxLayout()
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply_filters)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.button_layout.addWidget(self.apply_button)
        self.button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(self.button_layout)

        self.populate_filters()

    def populate_filters(self):
        # Authors
        all_authors = self.library_manager.get_all_authors()
        self.author_checkboxes = []
        for author in all_authors:
            checkbox = QCheckBox(author)
            self.authors_layout.addWidget(checkbox)
            self.author_checkboxes.append(checkbox)

        # Genres
        all_genres = self.library_manager.get_all_genres()
        self.genre_checkboxes = []
        for genre in all_genres:
            checkbox = QCheckBox(genre)
            self.genres_layout.addWidget(checkbox)
            self.genre_checkboxes.append(checkbox)

    def get_selected_filters(self):
        selected_authors = [cb.text() for cb in self.author_checkboxes if cb.isChecked()]
        selected_genres = [cb.text() for cb in self.genre_checkboxes if cb.isChecked()]
        return {'authors': selected_authors, 'genres': selected_genres}

    def apply_filters(self):
        self.accept()
