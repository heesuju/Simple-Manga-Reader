
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QPushButton, QCompleter, QScrollArea, QHBoxLayout, QSizePolicy
from PyQt6.QtCore import pyqtSignal, Qt, QStringListModel

class TokenInput(QWidget):
    filters_changed = pyqtSignal()

    def __init__(self, library_manager, parent=None):
        super().__init__(parent)
        self.library_manager = library_manager
        self.tokens = {}

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(5)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText("Filter by author or genre...")
        self.line_edit.returnPressed.connect(self.add_token_from_text)
        self.main_layout.addWidget(self.line_edit)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        self.token_container = QWidget()
        self.token_layout = QHBoxLayout(self.token_container)
        self.token_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.scroll_area.setWidget(self.token_container)
        self.main_layout.addWidget(self.scroll_area)

        self.setup_completer()

    def setup_completer(self):
        authors = [f"Author: {a}" for a in self.library_manager.get_all_authors()]
        genres = [f"Genre: {g}" for g in self.library_manager.get_all_genres()]
        model = QStringListModel(authors + genres)
        self.completer = QCompleter(model, self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated.connect(self.add_token_from_completer)
        self.line_edit.setCompleter(self.completer)

    def add_token(self, text):
        if text in self.tokens:
            return

        token_button = QPushButton(f"{text} ✕")
        token_button.setStyleSheet("QPushButton { background-color: #E0E0E0; border-radius: 5px; padding: 2px 5px; } QToolTip { color: #ffffff; background-color: #2a82da; border: 1px solid white; }")
        token_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        token_button.clicked.connect(lambda: self.remove_token(text))
        
        self.tokens[text] = token_button
        self.token_layout.addWidget(token_button)
        self.filters_changed.emit()

    def add_token_from_text(self):
        text = self.line_edit.text()
        if text:
            self.add_token(text)
            self.line_edit.clear()

    def add_token_from_completer(self, text):
        self.add_token(text)
        self.line_edit.clear()

    def remove_token(self, text):
        if text in self.tokens:
            self.tokens[text].deleteLater()
            del self.tokens[text]
            self.filters_changed.emit()

    def clear_tokens(self):
        for text in list(self.tokens.keys()):
            self.remove_token(text)
        self.filters_changed.emit()

    def get_filters(self):
        authors = []
        genres = []
        for text in self.tokens.keys():
            if text.startswith("Author: "):
                authors.append(text.replace("Author: ", ""))
            elif text.startswith("Genre: "):
                genres.append(text.replace("Genre: ", ""))
        return {'authors': authors, 'genres': genres}
