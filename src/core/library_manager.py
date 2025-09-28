import json
import os
from .library_scanner import LibraryScanner

class LibraryManager:
    def __init__(self, library_file="library.json"):
        self.library_file = library_file
        self.library = self.load_library()

    def load_library(self):
        if os.path.exists(self.library_file):
            with open(self.library_file, "r") as f:
                return json.load(f)
        else:
            return {"root_directories": [], "series": []}

    def save_library(self):
        with open(self.library_file, "w") as f:
            json.dump(self.library, f, indent=4)

    def get_series(self):
        return self.library.get("series", [])

    def get_chapters(self, series):
        return series.get("chapters", [])

    def scan_library(self):
        scanner = LibraryScanner()
        series = scanner.find_series(self.library["root_directories"])
        self.library["series"] = series
        self.save_library()

    def add_root_directory(self, path):
        if path not in self.library["root_directories"]:
            self.library["root_directories"].append(path)
            self.save_library()

    def remove_root_directory(self, path):
        if path in self.library["root_directories"]:
            self.library["root_directories"].remove(path)
            self.save_library()
