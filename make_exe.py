import PyInstaller.__main__
import shutil
import os

def build():
    print("Cleaning previous builds...")
    if os.path.exists('build'):
        try:
            shutil.rmtree('build')
        except Exception as e:
            print(f"Warning: Could not remove build directory: {e}")
            
    if os.path.exists('dist'):
        try:
            shutil.rmtree('dist')
        except Exception as e:
            print(f"Warning: Could not remove dist directory: {e}")

    print("Starting PyInstaller build...")
    
    # Use the existing spec file to respect user customization
    args = [
        'SimpleMangaReader.spec',
        '--noconfirm',
        '--clean'
    ]
    
    # Run
    PyInstaller.__main__.run(args)
    
    print("\nBuild complete!")
    print(f"Executable is located at: {os.path.abspath('dist/SimpleMangaReader.exe')}")

if __name__ == "__main__":
    build()
