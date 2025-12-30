import sys
import http.server
import socketserver
import json
import os
from pathlib import Path
import urllib.parse
import re
from PIL import Image
import io
import hashlib
from src.utils.resource_utils import resource_path
from src.core.library_manager import LibraryManager


library_manager = LibraryManager()

def find_number(text: str) -> float:
    numbers = re.findall(r'\d+(?:\.\d+)?', text)
    return float(numbers[0]) if numbers else float('inf')

def get_chapter_number(path):
    """Extract the chapter number as integer or float from the folder or file name."""
    if isinstance(path, str) and '|' in path:
        name = Path(path.split('|')[1]).name
    else:
        name = Path(path).name

    match = re.search(r'Ch\.\s*(\d+(?:\.\d+)?)', name, re.IGNORECASE)
    if match:
        return float(match.group(1))
    else:
        return find_number(name)

PORT = 8000
CACHE_DIR = Path(".cache/thumbnails")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def make_thumb_name(image_path: str, width: int, quality: int) -> Path:
    """Generate a safe thumbnail cache filename."""
    key = f"{image_path}|w{width}|q{quality}"
    digest = hashlib.md5(key.encode()).hexdigest()
    ext = ".jpg"
    return CACHE_DIR / f"{digest}{ext}"

class MangaHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = resource_path('web/index.html')
            return self.serve_static(self.path, 'text/html')

        elif self.path == '/style.css':
            self.path = resource_path('web/style.css')
            return self.serve_static(self.path, 'text/css')

        elif self.path == '/script.js':
            self.path = resource_path('web/script.js')
            return self.serve_static(self.path, 'application/javascript')

        elif self.path.startswith('/api/folders'):
            series = library_manager.get_series()
            self.send_json(series)
            return

        elif self.path.startswith('/api/series/'):
            series_name = urllib.parse.unquote(self.path[len('/api/series/'):])
            all_series = library_manager.get_series()
            series = next((s for s in all_series if s['name'] == series_name), None)

            if series:
                # Fill chapters with thumbnails/images
                valid_chapters = []
                for chapter in series.get('chapters', []):
                    full_chapter_path = series['path'] if not chapter['path'] else chapter['path']
                    if os.path.isdir(full_chapter_path):
                        images = []
                        thumbnail = None
                        try:
                            # Filter out cover images from being pages
                            for item in sorted(os.scandir(full_chapter_path), key=lambda e: get_chapter_number(e.path)):
                                if item.is_file() and item.name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.mp4', '.avi', '.mkv', '.webm', '.mov')):
                                    if item.name.lower() not in ['cover.jpg', 'cover.png']:
                                        images.append(item.path)
                                        if not thumbnail:
                                            thumbnail = item.path
                        except FileNotFoundError:
                            pass
                        
                        if images:
                            chapter['thumbnail'] = thumbnail
                            chapter['images'] = images
                            valid_chapters.append(chapter)
                
                series['chapters'] = valid_chapters

                # For series without chapters → treat image files in series folder
                if not series.get('chapters'):
                    series_images = []
                    try:
                        for item in sorted(os.scandir(series['path']), key=lambda e: get_chapter_number(e.path)):
                            if item.is_file() and item.name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.mp4', '.avi', '.mkv', '.webm', '.mov')):
                                series_images.append(item.path)
                    except FileNotFoundError:
                        pass
                    series['images'] = series_images

                self.send_json(series)
            else:
                self.send_error(404, "Series not found")
            return

        elif self.path.startswith('/api/images'):
            query_components = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            path_param = query_components.get("path", [""])[0]

            if os.path.isdir(path_param):
                images = []
                for item in sorted(os.scandir(path_param), key=lambda e: get_chapter_number(e.path)):
                    if item.is_file() and item.name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.mp4', '.avi', '.mkv', '.webm', '.mov')):
                        images.append(item.path)
                self.send_json(images)
            else:
                self.send_error(404, "Not found")
            return

        elif self.path.startswith('/images/'):
            parts = self.path.split('?')
            image_path = urllib.parse.unquote(parts[0][len('/images/'):])
            query_params = urllib.parse.parse_qs(parts[1]) if len(parts) > 1 else {}

            if os.path.isfile(image_path):
                try:
                    width = int(query_params.get('width', [0])[0])
                    quality = int(query_params.get('quality', [75])[0])

                    # Cached thumbnail path
                    if width > 0:
                        thumb_file = make_thumb_name(image_path, width, quality)
                        if thumb_file.exists():
                            # Serve cached thumb
                            with open(thumb_file, "rb") as f:
                                self.send_response(200)
                                self.send_header("Content-type", "image/jpeg")
                                self.end_headers()
                                self.wfile.write(f.read())
                            return

                        # Create and cache thumbnail
                        with Image.open(image_path) as img:
                            img.thumbnail((width, width * 10))  # maintain aspect ratio
                            img = img.convert("RGB")
                            img.save(thumb_file, format="JPEG", quality=quality)

                        with open(thumb_file, "rb") as f:
                            self.send_response(200)
                            self.send_header("Content-type", "image/jpeg")
                            self.end_headers()
                            self.wfile.write(f.read())
                        return

                    # If no resizing → serve original with Range support
                    file_size = os.path.getsize(image_path)
                    
                    # Determine Content-Type
                    content_type = 'image/jpeg'
                    if image_path.lower().endswith('.png'):
                        content_type = 'image/png'
                    elif image_path.lower().endswith('.gif'):
                        content_type = 'image/gif'
                    elif image_path.lower().endswith('.webp'):
                        content_type = 'image/webp'
                    elif image_path.lower().endswith('.mp4'):
                        content_type = 'video/mp4'
                    elif image_path.lower().endswith('.avi'):
                        content_type = 'video/x-msvideo'
                    elif image_path.lower().endswith('.webm'):
                        content_type = 'video/webm'
                    elif image_path.lower().endswith('.mov'):
                        content_type = 'video/quicktime'
                    elif image_path.lower().endswith('.mkv'):
                        content_type = 'video/x-matroska'

                    if image_path.lower().endswith(('.avi', '.mkv')):
                        # Transcode on the fly to WebM
                        self.send_response(200)
                        self.send_header('Content-type', 'video/webm')
                        self.end_headers()

                        import subprocess
                        # ffmpeg command to transcode to WebM (VP8/Vorbis for compatibility and speed)
                        # -f webm: force format
                        # -c:v libvpx -b:v 1M -crf 23: video settings (balance speed/quality)
                        # -c:a libvorbis: audio settings
                        # -deadline realtime -cpu-used 4: speed up encoding
                        cmd = [
                            'ffmpeg',
                            '-i', image_path,
                            '-f', 'webm',
                            '-c:v', 'libvpx',
                            '-b:v', '1M',
                            '-crf', '30',
                            '-c:a', 'libvorbis',
                            '-deadline', 'realtime',
                            '-cpu-used', '4',
                            '-'
                        ]
                        
                        try:
                            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**6)
                            while True:
                                chunk = process.stdout.read(4096)
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                            process.wait()
                        except Exception as e:
                            print(f"Transcoding error: {e}")
                        return

                    range_header = self.headers.get('Range')
                    
                    if range_header:
                        try:
                            # Parse Range header (bytes=start-end)
                            byte_range = range_header.strip().split('=')[1]
                            start_str, end_str = byte_range.split('-')
                            start = int(start_str)
                            end = int(end_str) if end_str else file_size - 1
                            
                            if start >= file_size:
                                self.send_error(416, 'Requested Range Not Satisfiable')
                                self.send_header('Content-Range', f'bytes */{file_size}')
                                self.end_headers()
                                return

                            length = end - start + 1
                            
                            self.send_response(206)
                            self.send_header('Content-type', content_type)
                            self.send_header('Accept-Ranges', 'bytes')
                            self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                            self.send_header('Content-Length', str(length))
                            self.end_headers()

                            with open(image_path, 'rb') as f:
                                f.seek(start)
                                self.wfile.write(f.read(length))
                            return

                        except ValueError:
                            pass # Fallback to 200

                    # Standard 200 OK response
                    with open(image_path, 'rb') as f:
                        self.send_response(200)
                        self.send_header('Content-type', content_type)
                        self.send_header('Accept-Ranges', 'bytes')
                        self.send_header('Content-Length', str(file_size))
                        self.end_headers()
                        self.wfile.write(f.read())

                except FileNotFoundError:
                    self.send_error(404, "Image not found")
            else:
                self.send_error(404, "Image not found")
            return

        super().do_GET()

    def serve_static(self, path, mime_type):
        try:
            with open(path, 'rb') as f:
                self.send_response(200)
                self.send_header('Content-type', mime_type)
                self.end_headers()
                self.wfile.write(f.read())
        except FileNotFoundError:
            self.send_error(404, "File not found")

    def send_json(self, obj):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode('utf-8'))


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True


def run_server():
    import socket
    # Get LAN IP (works even with VPNs/adapters present)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        s.close()
    except:
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)

    with ThreadingTCPServer(("0.0.0.0", PORT), MangaHandler) as httpd:
        print(f"Serving at http://{ip_address}:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    run_server()