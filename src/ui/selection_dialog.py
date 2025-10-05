from PyQt6.QtWidgets import QDialog, QVBoxLayout, QScrollArea, QWidget
from PyQt6.QtCore import pyqtSignal
from src.ui.flow_layout import FlowLayout
from src.ui.result_widget import ResultWidget
from src.utils.manga_utils import get_cover_from_manga_dex

class SelectionDialog(QDialog):
    manga_selected = pyqtSignal(dict)

    def __init__(self, manga_list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Manga")
        self.setMinimumSize(800, 600)

        layout = QVBoxLayout(self)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        container = QWidget()
        self.flow_layout = FlowLayout(container)
        scroll_area.setWidget(container)

        for manga_info in manga_list:
            cover_filename = None
            for rel in manga_info.get('relationships', []):
                if rel['type'] == 'cover_art':
                    cover_filename = rel['attributes']['fileName']
                    break
            
            cover_path = None
            if cover_filename:
                cover_path = get_cover_from_manga_dex(manga_info['id'], cover_filename)

            result_widget = ResultWidget(manga_info, cover_path)
            result_widget.clicked.connect(self.on_manga_selected)
            self.flow_layout.addWidget(result_widget)

    def on_manga_selected(self, manga_info):
        self.manga_selected.emit(manga_info)
        self.accept()
