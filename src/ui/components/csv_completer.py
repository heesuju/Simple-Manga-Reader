from PyQt6.QtWidgets import QCompleter
from PyQt6.QtCore import Qt

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
