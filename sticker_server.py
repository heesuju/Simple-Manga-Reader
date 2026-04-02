#!/usr/bin/env python3
"""
Standalone sticker server — no Qt dependency.
Exposes:
  GET  /health  → {"status": "ok"}
  POST /sticker → body: {"image": "<base64 PNG/JPG>", "border": <int, optional>, "model": <str, optional>}
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
DEFAULT_MODEL = "isnet-general-use"

# Cache rembg sessions so the model is only loaded once per process.
_session_cache: dict = {}


def _get_session(model: str):
    if model not in _session_cache:
        from rembg import new_session
        _session_cache[model] = new_session(model)
    return _session_cache[model]


def _make_sticker(image_bytes: bytes, border: int = DEFAULT_BORDER, model: str = DEFAULT_MODEL) -> bytes:
    from PIL import Image
    import numpy as np
    import cv2
    from rembg import remove

    input_image = Image.open(BytesIO(image_bytes)).convert("RGBA")

    # Use a higher-quality model with a cached session.
    try:
        session = _get_session(model)
        result: Image.Image = remove(input_image, session=session)
    except Exception:
        # Fall back to default rembg behaviour if the model isn't available.
        result = remove(input_image)

    arr = np.array(result, dtype=np.uint8)
    alpha = arr[:, :, 3]

    # ── Alpha cleanup ────────────────────────────────────────────────────────
    # rembg leaves semi-transparent fringe pixels that look like background
    # bleed.  Binarise first, then morphologically close small holes and open
    # away noise, then re-apply a thin smooth edge for a natural look.
    ALPHA_THRESHOLD = 15
    binary = (alpha > ALPHA_THRESHOLD).astype(np.uint8) * 255

    small_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    # Close: fill tiny transparent holes inside the subject.
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, small_kernel, iterations=2)
    # Open: remove stray opaque specks outside the subject.
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, small_kernel, iterations=1)

    # Smooth only the outermost 1-px ring of the subject edge; keep the body
    # fully opaque so colours don't bleed through.
    edge_blur = cv2.GaussianBlur(binary, (3, 3), 0.8)
    clean_alpha = np.where(binary == 255, 255, edge_blur).astype(np.uint8)

    arr[:, :, 3] = clean_alpha
    result = Image.fromarray(arr, "RGBA")

    if border <= 0:
        composite = result
    else:
        # ── Border ───────────────────────────────────────────────────────────
        # Dilate the *binary* mask (not the soft alpha) so the border is fully
        # opaque white.  Only the outermost ~1-2 px ring gets a light blur for
        # anti-aliasing; the rest stays at alpha 255.
        kernel_size = border * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        border_mask = cv2.dilate(binary, kernel, iterations=1)

        # Anti-alias only the outer fringe (fixed tiny kernel, not scaled).
        fringe_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        inner = cv2.erode(border_mask, fringe_kernel, iterations=1)
        outer_fringe = border_mask.astype(np.int16) - inner.astype(np.int16)
        outer_fringe = np.clip(outer_fringe, 0, 255).astype(np.uint8)
        outer_smooth = cv2.GaussianBlur(outer_fringe, (3, 3), 0.8)
        border_mask = np.clip(
            inner.astype(np.int16) + outer_smooth.astype(np.int16), 0, 255
        ).astype(np.uint8)

        border_layer = np.zeros_like(arr)
        border_layer[:, :, 0] = 255
        border_layer[:, :, 1] = 255
        border_layer[:, :, 2] = 255
        border_layer[:, :, 3] = border_mask

        # Composite: solid white border underneath, cleaned subject on top.
        border_img = Image.fromarray(border_layer, "RGBA")
        composite = Image.alpha_composite(border_img, result)

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
                model = str(body.get("model", DEFAULT_MODEL))
                result_bytes = _make_sticker(img_bytes, border, model)
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
