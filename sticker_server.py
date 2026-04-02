#!/usr/bin/env python3
"""
Standalone sticker server — no Qt dependency.
Exposes:
  GET  /health  → {"status": "ok"}
  POST /sticker → body: {"image": "<base64 PNG/JPG>", "border": <int, optional>}
                ← {"image": "<base64 PNG>"}  (RGBA, transparent background, white border)
Run: python sticker_server.py [port]   (default port: 8083)
"""
import sys
import json
import base64
from io import BytesIO
from http.server import HTTPServer, BaseHTTPRequestHandler

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_BORDER = 8


def _make_sticker(image_bytes: bytes, border: int = DEFAULT_BORDER) -> bytes:
    from PIL import Image
    import numpy as np
    import cv2
    from rembg import remove

    input_image = Image.open(BytesIO(image_bytes)).convert("RGBA")
    result: Image.Image = remove(input_image)

    if border > 0:
        arr = np.array(result)
        alpha = arr[:, :, 3]

        kernel_size = border * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        border_mask = cv2.dilate(alpha, kernel, iterations=1)

        # Smooth only the outer edge of the border so it anti-aliases cleanly.
        # Erode slightly inward to find the "inner" region, then blur just the
        # difference (the outer fringe), leaving the body of the border solid.
        inner = cv2.erode(border_mask, kernel, iterations=1)
        outer_fringe = border_mask.astype(np.int16) - inner.astype(np.int16)
        outer_fringe = np.clip(outer_fringe, 0, 255).astype(np.uint8)
        outer_smooth = cv2.GaussianBlur(outer_fringe, (5, 5), 1.2)
        border_mask = np.clip(inner.astype(np.int16) + outer_smooth.astype(np.int16), 0, 255).astype(np.uint8)

        border_layer = np.zeros_like(arr)
        border_layer[:, :, 0] = 255
        border_layer[:, :, 1] = 255
        border_layer[:, :, 2] = 255
        border_layer[:, :, 3] = border_mask

        # Composite: border underneath, original on top
        border_img = Image.fromarray(border_layer, "RGBA")
        composite = Image.alpha_composite(border_img, result)
    else:
        composite = result

    buf = BytesIO()
    composite.save(buf, format="PNG")
    return buf.getvalue()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._reply(200, b'{"status":"ok"}')
        else:
            self._reply(404, b'{"error":"not found"}')

    def do_POST(self):
        if self.path == "/sticker":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                img_bytes = base64.b64decode(body["image"])
                border = int(body.get("border", DEFAULT_BORDER))
                result_bytes = _make_sticker(img_bytes, border)
                b64 = base64.b64encode(result_bytes).decode()
                payload = json.dumps({"image": b64}).encode()
                self._reply(200, payload)
            except Exception as e:
                print(f"Sticker request error: {e}", flush=True)
                import traceback; traceback.print_exc()
                payload = json.dumps({"error": str(e)}).encode()
                self._reply(500, payload)
        else:
            self._reply(404, b'{"error":"not found"}')

    def _reply(self, code: int, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8083
    print(f"Sticker server listening on port {port}", flush=True)
    HTTPServer(("localhost", port), _Handler).serve_forever()
