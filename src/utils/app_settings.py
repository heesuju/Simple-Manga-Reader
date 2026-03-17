import json
from pathlib import Path

# Project root: src/utils/app_settings.py -> src/utils -> src -> project root
_SETTINGS_PATH = Path(__file__).resolve().parent.parent.parent / "app_settings.json"
_settings: dict = {}
_loaded = False


def _load():
    global _settings, _loaded
    if _loaded:
        return
    _loaded = True
    if _SETTINGS_PATH.exists():
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            _settings = json.load(f)


def _save():
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(_settings, f, indent=2)


def get(key: str, default=None):
    _load()
    return _settings.get(key, default)


def set(key: str, value):
    _load()
    _settings[key] = value
    _save()
