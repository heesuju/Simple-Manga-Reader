#!/usr/bin/env python3
"""
Standalone OCR server — no Qt dependency.
Exposes:
  GET  /health  → {"status": "ok"}
  POST /ocr     → body: {"image": "<base64 PNG/JPG>"}
                ← {"results": [{"bbox": [x,y,w,h], "text": "...", "class": "..."}]}
Run: python ocr_server.py [port]   (default port: 8082)
"""
import sys
import json
import base64
from io import BytesIO
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image

# Ensure project root is importable
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_detector = None
_ocr = None


def _get_detector():
    global _detector
    if _detector is None:
        from src.core.text_detector import TextDetector
        _detector = TextDetector()
    return _detector


def _get_ocr():
    global _ocr
    if _ocr is None:
        from src.core.ocr import OCR
        _ocr = OCR()
    return _ocr


def _run_ocr(image: Image.Image) -> list:
    detector = _get_detector()
    ocr_engine = _get_ocr()

    detections = detector.detect(image)
    img_w, img_h = image.size
    results = []

    for det in detections:
        x, y, w, h = det['bbox']
        x1 = max(0, int(x))
        y1 = max(0, int(y))
        x2 = min(img_w, int(x + w))
        y2 = min(img_h, int(y + h))

        text = ""
        if x2 > x1 and y2 > y1:
            crop = image.crop((x1, y1, x2, y2))
            try:
                text = ocr_engine.process(crop)
            except Exception as e:
                print(f"OCR failed for region: {e}", flush=True)

        results.append({
            'bbox': det['bbox'],
            'text': text,
            'class': det.get('class', 'text_bubble'),
        })

    return results


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self._reply(200, b'{"status":"ok"}')
        else:
            self._reply(404, b'{"error":"not found"}')

    def do_POST(self):
        if self.path == '/ocr':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length))
                img_bytes = base64.b64decode(body['image'])
                image = Image.open(BytesIO(img_bytes)).convert('RGB')
                results = _run_ocr(image)
                payload = json.dumps({'results': results}).encode()
                self._reply(200, payload)
            except Exception as e:
                print(f"OCR request error: {e}", flush=True)
                import traceback; traceback.print_exc()
                payload = json.dumps({'error': str(e)}).encode()
                self._reply(500, payload)
        else:
            self._reply(404, b'{"error":"not found"}')

    def _reply(self, code: int, body: bytes):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass  # suppress default request logging


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8082
    print(f'OCR server listening on port {port}', flush=True)
    HTTPServer(('localhost', port), _Handler).serve_forever()
