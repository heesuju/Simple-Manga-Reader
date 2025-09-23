import cv2
import numpy as np
import os

import cv2
import numpy as np
import os

def extract_panels_with_gutters(image_path, output_dir="panels_fixed"):
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # --- 1. Binarize ---
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)  # white ~ gutters
    inv = 255 - binary  # panels ~ white

    # --- 2. Detect horizontal & vertical gutters ---
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 3))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 50))

    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)

    gutters = cv2.bitwise_or(h_lines, v_lines)

    # --- 3. Enforce gutters into inverted ---
    separated = cv2.bitwise_and(inv, cv2.bitwise_not(gutters))

    # --- 4. Find contours ---
    contours, _ = cv2.findContours(separated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    panels = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 20000:  # ignore tiny
            x, y, w, h = cv2.boundingRect(cnt)
            panels.append((cnt, (x, y, w, h)))

    # Sort top→bottom, right→left
    panels.sort(key=lambda p: (p[1][1] // 50, -p[1][0]))

    os.makedirs(output_dir, exist_ok=True)
    panel_paths = []
    for i, (cnt, (x, y, w, h)) in enumerate(panels):
        # Mask contour
        mask = np.zeros(img.shape[:2], dtype=np.uint8)
        cv2.drawContours(mask, [cnt], -1, 255, -1)

        # RGBA crop
        panel = img[y:y+h, x:x+w]
        mask_crop = mask[y:y+h, x:x+w]
        b, g, r = cv2.split(panel)
        rgba = cv2.merge([b, g, r, mask_crop])
        panel_path = os.path.join(output_dir, f"panel_{i}.png")
        cv2.imwrite(panel_path, rgba)
        panel_paths.append(panel_path)

    print(f"✅ Extracted {len(panels)} panels into '{output_dir}'.")
    return panel_paths


# image_path = "C:/Users/mycom/Downloads/sample/12.webp"
# image_path = "C:/Users/mycom/Downloads/1.png"
# image_path = "C:/Users/mycom/Downloads/20250714200642_5de89599e2a87a5d3bc6a158e5b161d9_IMAG01_1.jpg"
# image_path = "C:/Users/mycom/Downloads/example/7527.png"
# image_path = "C:/Users/mycom/Downloads/example/7526.png"
# image_path = "C:/Users/mycom/Downloads/example/7554.png"


# Example usage
# extract_panels_with_gutters(image_path)