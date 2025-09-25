import sys
from PyQt6.QtWidgets import QApplication
from src.folder_grid import FolderGrid
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("root_dir", nargs="?", default="")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    folder_ui = FolderGrid(args.root_dir)
    folder_ui.show()
    sys.exit(app.exec())