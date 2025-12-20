
from huggingface_hub import snapshot_download

def download_manga_ocr():
    print("Downloading MangaOCR model manually...")
    try:
        path = snapshot_download(repo_id="kha-white/manga-ocr-base", local_dir_use_symlinks=False)
        print(f"Model downloaded to: {path}")
    except Exception as e:
        print(f"Download failed: {e}")

if __name__ == "__main__":
    download_manga_ocr()
