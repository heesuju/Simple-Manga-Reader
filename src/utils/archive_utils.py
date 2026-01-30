import os
import shutil
import platform
import subprocess
from typing import Optional, List
from pathlib import Path

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
    def read_file(archive_path: str, internal_path: str) -> Optional[bytes]:
        if not SEVEN_ZIP_PATH:
            return None
            
        try:
            cmd = [SEVEN_ZIP_PATH, "e", "-so", str(archive_path), internal_path]
            
            startupinfo = None
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                startupinfo=startupinfo
            )
            
            if result.returncode == 0:
                return result.stdout
            return None
        except Exception:
            return None
