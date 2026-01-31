import os
import shutil
import platform
import subprocess
import hashlib
from typing import Optional, List
from pathlib import Path

ARCHIVE_CACHE_DIR = Path('.cache/archives')
ARCHIVE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def find_executable(names: list[str], extra_paths: list[str] = []) -> Optional[str]:
    """
    Find an executable by trying multiple names and extra paths.
    """
    # 1. Search in PATH
    for name in names:
        path = shutil.which(name)
        if path:
            return path
            
    # 2. Search in extra paths
    for path in extra_paths:
        if os.path.exists(path):
            return path
            
    return None

def find_7z() -> Optional[str]:
    """
    Search for 7-Zip executable based on platform.
    """
    system = platform.system()
    
    if system == "Windows":
        # Common Windows names and paths
        names = ["7z", "7za", "7z.exe"]
        extra_paths = [
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe"
        ]
        return find_executable(names, extra_paths)
    else:
        # Linux / Unix
        names = ["7z", "7za", "p7zip"]
        return find_executable(names)

SEVEN_ZIP_PATH = find_7z()

class SevenZipHandler:
    @staticmethod
    def is_available():
        return SEVEN_ZIP_PATH is not None

    @staticmethod
    def list_files(archive_path: str) -> List[str]:
        if not SEVEN_ZIP_PATH:
            return []
        
        try:
            cmd = [SEVEN_ZIP_PATH, "l", "-slt", str(archive_path), "-sccUTF-8"]
            
            startupinfo = None
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo
            )
            
            if result.returncode != 0:
                print(f"7z Error listing {archive_path}: {result.stderr}")
                return []
                
            files = []
            current_path = None
            is_folder = False
            
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("Path = "):
                    current_path = line[7:]
                    is_folder = False
                elif line.startswith("Attributes = "):
                    if "D" in line: # Directory
                         is_folder = True
                elif line == "":
                    if current_path and not is_folder:
                        files.append(current_path)
                    current_path = None
                    is_folder = False
            
            if current_path and not is_folder:
                files.append(current_path)
                
            return files
            
        except Exception as e:
            print(f"Error listing archive {archive_path}: {e}")
            return []

    @staticmethod
    def get_archive_id(archive_path: str) -> str:
        """Get a unique ID for an archive based on its path and modification time."""
        try:
            mtime = os.path.getmtime(archive_path)
        except Exception:
            mtime = 0
        return hashlib.md5(f"{archive_path}{mtime}".encode()).hexdigest()

    @staticmethod
    def get_extract_dir(archive_path: str) -> Path:
        """Get the specific extraction directory for this archive."""
        archive_id = SevenZipHandler.get_archive_id(archive_path)
        return ARCHIVE_CACHE_DIR / archive_id

    @staticmethod
    def read_file(archive_path: str, internal_path: str) -> Optional[bytes]:
        if not SEVEN_ZIP_PATH:
            return None
            
        # 1. Check chapter-specific extraction folder
        extract_dir = SevenZipHandler.get_extract_dir(archive_path)
        target_path = extract_dir / internal_path.replace('/', os.sep)
        target_path_alt = extract_dir / internal_path.replace('\\', '/')

        if target_path.exists():
            with open(target_path, 'rb') as f:
                return f.read()
        if target_path_alt.exists() and target_path_alt != target_path:
            with open(target_path_alt, 'rb') as f:
                return f.read()

        # 2. Extract on-demand if not found
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 'x' extracts with full paths, '-y' assumes Yes on all queries
            cmd = [SEVEN_ZIP_PATH, "x", str(archive_path), f"-o{extract_dir}", internal_path, "-y"]
            
            startupinfo = None
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            subprocess.run(cmd, capture_output=True, startupinfo=startupinfo)
            
            if target_path.exists():
                with open(target_path, 'rb') as f:
                    return f.read()
            if target_path_alt.exists():
                with open(target_path_alt, 'rb') as f:
                    return f.read()

            return None
        except Exception:
            return None

    @staticmethod
    def extract_all(archive_path: str, progress_callback=None) -> bool:
        """Background extraction of the entire archive."""
        if not SEVEN_ZIP_PATH:
            return False
            
        try:
            extract_dir = SevenZipHandler.get_extract_dir(archive_path)
            extract_dir.mkdir(parents=True, exist_ok=True)
            
            # 'x' extracts with full paths, '-y' assumes Yes on all queries
            cmd = [SEVEN_ZIP_PATH, "x", str(archive_path), f"-o{extract_dir}", "-y"]
            
            startupinfo = None
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                startupinfo=startupinfo
            )
            
            process.wait()
            return process.returncode == 0
        except Exception:
            return False
