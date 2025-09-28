import sys
import http.server
import socketserver
import json
import os
from pathlib import Path
import urllib.parse
import re
import time
from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity: int):
        self.cache = OrderedDict()
        self.capacity = capacity

    def get(self, key: str):
        if key not in self.cache:
            return None
        else:
            self.cache.move_to_end(key)
            return self.cache[key]

    def put(self, key: str, value):
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last = False)

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
# IMPORTANT: Change this to the directory where your manga is stored
# ROOT_DIR = os.path.expanduser("~") 
ROOT_DIR = os.path.expanduser("C:/Utils/mangadex-dl_x64_v3.1.4/mangadex-dl") 

# Cache for API responses and images
api_cache = LRUCache(100)
image_cache = LRUCache(50)

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
            cached_response = api_cache.get(self.path)
            if cached_response:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(cached_response)
                return

            query_components = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            path_param = query_components.get("path", [""])[0]
            current_path = os.path.join(ROOT_DIR, path_param)

            items = []
            for item in os.scandir(current_path):
                if item.is_dir():
                    has_subfolders = any(sub.is_dir() for sub in os.scandir(item.path))
                    item_type = 'folder' if has_subfolders else 'leaf'
                    thumbnail = None
                    try:
                        for sub_item in os.scandir(item.path):
                            if sub_item.is_file() and sub_item.name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
                                thumbnail = os.path.relpath(sub_item.path, ROOT_DIR)
                                break
                    except FileNotFoundError:
                        pass # Ignore if thumbnail not found
                    items.append({'name': item.name, 'path': os.path.relpath(item.path, ROOT_DIR), 'type': item_type, 'thumbnail': thumbnail})
            
            items.sort(key=lambda x: get_chapter_number(x['name']))
            response = json.dumps(items).encode('utf-8')
            api_cache.put(self.path, response)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(response)
            return
        elif self.path.startswith('/api/images'):
            cached_response = api_cache.get(self.path)
            if cached_response:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(cached_response)
                return

            query_components = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            path_param = query_components.get("path", [""])[0]
            full_path = os.path.join(ROOT_DIR, path_param)
            if os.path.isdir(full_path):
                images = []
                for item in os.scandir(full_path):
                    if item.is_file() and item.name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
                        images.append(os.path.join(path_param, item.name))
                images.sort(key=get_chapter_number)
                response = json.dumps(images).encode('utf-8')
                api_cache.put(self.path, response)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(response)
            else:
                self.send_error(404, "Manga not found")
            return
        elif self.path.startswith('/api/series'):
            cached_response = api_cache.get(self.path)
            if cached_response:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(cached_response)
                return

            query_components = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            path_param = query_components.get("path", [""])[0]
            series_path = os.path.dirname(os.path.join(ROOT_DIR, path_param))

            chapters = []
            for item in os.scandir(series_path):
                if item.is_dir():
                    chapters.append(os.path.relpath(item.path, ROOT_DIR))
            
            chapters.sort(key=get_chapter_number)
            response = json.dumps(chapters).encode('utf-8')
            api_cache.put(self.path, response)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(response)
            return
            
        elif self.path.startswith('/images/'):
            image_path = urllib.parse.unquote(self.path[len('/images/'):])
            cached_image = image_cache.get(image_path)
            if cached_image:
                content_type, image_data = cached_image
                self.send_response(200)
                self.send_header('Content-type', content_type)
                self.end_headers()
                self.wfile.write(image_data)
                return

            full_image_path = os.path.join(ROOT_DIR, image_path)
            if os.path.isfile(full_image_path):
                try:
                    with open(full_image_path, 'rb') as f:
                        image_data = f.read()
                        content_type = 'image/jpeg'
                        if full_image_path.lower().endswith('.png'):
                            content_type = 'image/png'
                        elif full_image_path.lower().endswith('.gif'):
                            content_type = 'image/gif'
                        elif full_image_path.lower().endswith('.webp'):
                            content_type = 'image/webp'
                        
                        image_cache.put(image_path, (content_type, image_data))

                        self.send_response(200)
                        self.send_header('Content-type', content_type)
                        self.end_headers()
                        self.wfile.write(image_data)
                except FileNotFoundError:
                    self.send_error(404, "Image not found")
            else:
                self.send_error(404, "Image not found")
            return

        super().do_GET()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        ROOT_DIR = sys.argv[1]
    
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip_address = s.getsockname()[0]
    s.close()

    with socketserver.TCPServer(("0.0.0.0", PORT), MangaHandler) as httpd:
        print(f"Serving at http://{ip_address}:{PORT}")
        httpd.serve_forever()
