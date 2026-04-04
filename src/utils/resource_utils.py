import sys
import os
from pathlib import Path

def resource_path(relative_path: str) -> str:
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Use the project root (two levels up from src/utils/) regardless of cwd
        base_path = str(Path(__file__).resolve().parent.parent.parent)

    return os.path.join(base_path, relative_path)

def get_asset_path(relative_path: str) -> str:
    """Helper specifically for assets/web items"""
    return resource_path(relative_path)
