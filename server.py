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

from src.core.library_manager import LibraryManager

library_manager = LibraryManager()
ROOT_DIRS = library_manager.library['root_directories']

def find_number(text:str)->int:
    numbers = re.findall(r'\d+', text)
    return int(numbers[0]) if numbers else float('inf')

def get_chapter_number(path):
    """Extract the chapter number as integer from the folder or file name."""
    if isinstance(path, str) and '|' in path:
        name = Path(path.split('|')[1]).name
    else:
        name = Path(path).name
    
    match = re.search(r'Ch\.\s*(\d+)', name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    else:
        return find_number(name)

PORT = 8000

class MangaHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = 'web/index.html'
            try:
                with open(self.path, 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.send_error(404, "File not found")
            return
        elif self.path == '/style.css':
            self.path = 'web/style.css'
            try:
                with open(self.path, 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-type', 'text/css')
                    self.end_headers()
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.send_error(404, "File not found")
            return
        elif self.path == '/script.js':
            self.path = 'web/script.js'
            try:
                with open(self.path, 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/javascript')
                    self.end_headers()
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.send_error(404, "File not found")
            return
        elif self.path.startswith('/api/folders'):
            series = library_manager.get_series()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(series).encode('utf-8'))
            return
        elif self.path.startswith('/api/series/'):
            series_name = urllib.parse.unquote(self.path[len('/api/series/'):])
            series = next((s for s in library_manager.get_series() if s['name'] == series_name), None)
            if series:
                if not series.get('chapters'):
                    # Series with no chapters, add images from the series folder
                    full_series_path = Path(os.path.join(series['root_dir'], series['path']))
                    images = []
                    try:
                        for item in sorted(os.scandir(full_series_path), key=lambda e: e.name):
                            if item.is_file() and item.name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
                                images.append(os.path.relpath(item.path, series['root_dir']))
                    except FileNotFoundError:
                        pass
                    series['images'] = images
                else:
                    # Add thumbnails and image lists to chapters
                    for chapter in series.get('chapters', []):
                        chapter_rel_path = chapter['path']
                        full_chapter_path = None
                        root_dir = None
                        for r in ROOT_DIRS:
                            test_path = os.path.join(r, chapter_rel_path)
                            if os.path.exists(test_path):
                                full_chapter_path = test_path
                                root_dir = r
                                break

                        if full_chapter_path:
                            images = []
                            thumbnail = None
                            try:
                                for item in sorted(os.scandir(full_chapter_path), key=lambda e: e.name):
                                    if item.is_file() and item.name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
                                        image_rel_path = os.path.relpath(item.path, root_dir)
                                        images.append(image_rel_path)
                                        if not thumbnail:
                                            thumbnail = image_rel_path
                            except FileNotFoundError:
                                pass
                            chapter['thumbnail'] = thumbnail
                            chapter['images'] = images

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(series).encode('utf-8'))
            else:
                self.send_error(404, "Series not found")
            return
        elif self.path.startswith('/api/images'):
            query_components = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            path_param = query_components.get("path", [""])[0]
            full_path = None
            root_dir_found = None
            for r in ROOT_DIRS:
                test_path = os.path.join(r, path_param)
                if os.path.exists(test_path):
                    full_path = test_path
                    root_dir_found = r
                    break

            if full_path and os.path.isdir(full_path):
                images = []
                for item in sorted(os.scandir(full_path), key=lambda e: e.name):
                    if item.is_file() and item.name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
                        images.append(os.path.relpath(item.path, root_dir_found))
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(images).encode('utf-8'))
            else:
                self.send_error(404, "Not found")
            return
        elif self.path.startswith('/images/'):
            parts = self.path.split('?')
            image_path = urllib.parse.unquote(parts[0][len('/images/'):])
            query_params = urllib.parse.parse_qs(parts[1]) if len(parts) > 1 else {}

            full_image_path = None
            for root_dir in ROOT_DIRS:
                test_path = os.path.join(root_dir, image_path)
                if os.path.isfile(test_path):
                    full_image_path = test_path
                    break

            if full_image_path:
                try:
                    width = int(query_params.get('width', [0])[0])
                    quality = int(query_params.get('quality', [75])[0])

                    if width > 0:
                        with Image.open(full_image_path) as img:
                            img.thumbnail((width, width * 10)) # Keep aspect ratio
                            buffer = io.BytesIO()
                            img_format = 'jpeg' if img.mode == 'RGB' else 'png'
                            img.save(buffer, format=img_format, quality=quality)
                            buffer.seek(0)
                            image_data = buffer.read()

                            self.send_response(200)
                            self.send_header('Content-type', f'image/{img_format}')
                            self.end_headers()
                            self.wfile.write(image_data)
                    else:
                        with open(full_image_path, 'rb') as f:
                            self.send_response(200)
                            content_type = 'image/jpeg'
                            if full_image_path.lower().endswith('.png'):
                                content_type = 'image/png'
                            elif full_image_path.lower().endswith('.gif'):
                                content_type = 'image/gif'
                            elif full_image_path.lower().endswith('.webp'):
                                content_type = 'image/webp'
                            self.send_header('Content-type', content_type)
                            self.end_headers()
                            self.wfile.write(f.read())
                except FileNotFoundError:
                    self.send_error(404, "Image not found")
            else:
                self.send_error(404, "Image not found")
            return

        super().do_GET()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        ROOT_DIRS = sys.argv[1:]
    
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip_address = s.getsockname()[0]
    s.close()

    with socketserver.TCPServer(("0.0.0.0", PORT), MangaHandler) as httpd:
        print(f"Serving at http://{ip_address}:{PORT}")
        httpd.serve_forever()