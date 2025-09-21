from pathlib import PurePath

from pathlib import Path

def normalize_path(path: str) -> str:
    # Convert to Path, then force POSIX-style (forward slashes)
    return Path(path).as_posix()