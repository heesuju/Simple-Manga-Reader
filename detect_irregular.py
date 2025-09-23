import cv2
import numpy as np
import os

def extract_irregular_panels(image_path, output_dir="panels_irregular"):
    # Load image
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Image not found: {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # --- Threshold ---
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )

    # --- Morphology (connect panel borders) ---
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    # --- Find contours ---
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # --- Filter + sort contours ---
    panels = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 20000:  # ignore tiny blobs
            x, y, w, h = cv2.boundingRect(cnt)
            cx, cy = x + w//2, y + h//2
            panels.append((cnt, (x, y, w, h), (cx, cy)))

    # Sort top→bottom, right→left
    panels.sort(key=lambda p: (p[2][1] // 50, -p[2][0]))

    # --- Save each panel using mask ---
    os.makedirs(output_dir, exist_ok=True)
    for i, (cnt, (x, y, w, h), _) in enumerate(panels):
        # Make a mask of just this panel
        mask = np.zeros(img.shape[:2], dtype=np.uint8)
        cv2.drawContours(mask, [cnt], -1, 255, -1)  # fill contour

        # Crop with mask
        panel = img[y:y+h, x:x+w]
        mask_crop = mask[y:y+h, x:x+w]
        panel_masked = cv2.bitwise_and(panel, panel, mask=mask_crop)

        # Save
        cv2.imwrite(os.path.join(output_dir, f"panel_{i}.png"), panel_masked)

        # Debug: draw outline on original
        cv2.drawContours(img, [cnt], -1, (0, 255, 0), 3)

    # Show detected panels
    cv2.imshow("Detected Irregular Panels", img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    print(f"✅ Extracted {len(panels)} panels into '{output_dir}'")

# image_path = "C:/Users/mycom/Downloads/16.webp"
image_path = "C:/Users/mycom/Downloads/sample/12.webp"
# image_path = "C:/Users/mycom/Downloads/1.png"
# image_path = "C:/Users/mycom/Downloads/sample/5.webp"

# image_path = "C:/Users/mycom/Downloads/sample/20.webp"
extract_irregular_panels(image_path)