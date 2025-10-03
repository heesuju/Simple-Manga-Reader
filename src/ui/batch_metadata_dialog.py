from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QCompleter,
    QDialogButtonBox
)
from PyQt6.QtCore import QStringListModel, Qt

class CsvCompleter(QCompleter):
    def __init__(self, model, parent=None):
        super().__init__(model, parent)
        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def pathFromIndex(self, index):
        completion = super().pathFromIndex(index)
        text = self.widget().text()
        parts = text.split(',')
        if len(parts) > 1:
            prefix = ",".join(parts[:-1])
            return f"{prefix.strip()}, {completion}"
        return completion

    def splitPath(self, path):
        return [path.split(',')[-1].strip()]

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

    def get_metadata(self):
        authors = [author.strip() for author in self.authors_input.text().split(',') if author.strip()]
        genres = [genre.strip() for genre in self.genres_input.text().split(',') if genre.strip()]
        return {'authors': authors, 'genres': genres}
