import cv2
import numpy as np
import os

def extract_manga_panels(image_path, output_dir="panels_out"):
    # Load image
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Image not found: {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # --- 1. Threshold (invert: panels = white, background = black) ---
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )

    # --- 2. Morphology to connect borders ---
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    # --- 3. Find contours (only external) ---
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # --- 4. Extract bounding boxes ---
    boxes = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h
        
        if area > 30000 and w > 30 and h > 30:  # ignore tiny blobs
            boxes.append((x, y, w, h))

    # --- 5. Sort boxes in manga reading order (top->bottom, right->left) ---
    # First sort by y (top to bottom), then by x (right to left)
    boxes = sorted(boxes, key=lambda b: (b[1] // 50, -b[0]))

    # --- 6. Save crops ---
    os.makedirs(output_dir, exist_ok=True)
    for i, (x, y, w, h) in enumerate(boxes):
        crop = img[y:y+h, x:x+w]
        cv2.imwrite(os.path.join(output_dir, f"panel_{i}.png"), crop)
        cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 3)

    # Show detected panels for debugging
    cv2.imshow("Detected Panels", img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    print(f"✅ Extracted {len(boxes)} panels into {output_dir}")


# Example run
# Example usage
# image_path = "C:/Users/mycom/Downloads/16.webp"
# image_path = "C:/Users/mycom/Downloads/1.png"
# image_path = "C:/Users/mycom/Downloads/sample/5.webp"
image_path = "C:/Users/mycom/Downloads/sample/20.webp"
extract_manga_panels(image_path)
