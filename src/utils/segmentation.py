import cv2
import numpy as np

def get_panel_coordinates(image_path):
    img = cv2.imread(image_path)
    if img is None:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    h, w = gray.shape
    corners = [gray[0, 0], gray[0, w-1], gray[h-1, 0], gray[h-1, w-1]]
    corner_mean = np.mean(corners)

    # --- 1. Binarize ---
    if corner_mean > 127: # light background
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)  # white ~ gutters
        inv = 255 - binary  # panels ~ white
    else: # dark background
        _, inv = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        binary = 255 - inv

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
        x, y, w, h = cv2.boundingRect(cnt)
        if area > 20000 and w > 50 and h > 50:  # ignore tiny
            panels.append((x, y, w, h))

    # --- 5. Filter out contained panels ---
    filtered_panels = []
    for i, p1 in enumerate(panels):
        is_contained = False
        for j, p2 in enumerate(panels):
            if i == j:
                continue
            # p1 is contained in p2 if p2's area is larger and p1 is inside p2
            if p1[2]*p1[3] < p2[2]*p2[3] and \
               p1[0] >= p2[0] and p1[1] >= p2[1] and \
               p1[0]+p1[2] <= p2[0]+p2[2] and p1[1]+p1[3] <= p2[1]+p2[3]:
                is_contained = True
                break
        if not is_contained:
            filtered_panels.append(p1)

    # --- 6. Group panels by rows and sort ---
    if not filtered_panels:
        return []

    # Sort panels by y-coordinate
    sorted_panels = sorted(filtered_panels, key=lambda p: p[1])

    rows = []
    while sorted_panels:
        current_row = [sorted_panels.pop(0)]
        row_y_center = current_row[0][1] + current_row[0][3] / 2

        remaining_panels = []
        for panel in sorted_panels:
            panel_y_center = panel[1] + panel[3] / 2
            if abs(panel_y_center - row_y_center) < 50: # 50px tolerance
                current_row.append(panel)
            else:
                remaining_panels.append(panel)
        
        rows.append(sorted(current_row, key=lambda p: -p[0]))
        sorted_panels = remaining_panels

    # Flatten the rows into a single list
    final_panels = [panel for row in rows for panel in row]

    return final_panels

def detect_bubbles(image_path, debug=True):
    # --- 1. Load ---
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not load image: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # --- 2. Threshold ---
    # Adaptive works better on manga scans
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        25, 15
    )

    # --- 3. Find contours ---
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    bubble_boxes = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < 1000 or area > 200000:  # filter small noise / huge panels
            continue

        x, y, w, h = cv2.boundingRect(c)
        aspect_ratio = w / float(h)

        hull = cv2.convexHull(c)
        hull_area = cv2.contourArea(hull) if cv2.contourArea(hull) > 0 else 1
        solidity = float(area) / hull_area

        rect_area = w * h
        rectangularity = float(area) / rect_area

        # --- 4. Bubble-like filtering ---
        # Ovals (solidity ~0.9), spiky (~0.6–0.85), boxes (~0.9 rect)
        if 0.2 < aspect_ratio < 5.0 and 0.5 < solidity <= 1.0:
            if rectangularity > 0.5:  # exclude long thin lines
                bubble_boxes.append((x, y, w, h))

    # --- 5. Debug visualization ---
    if debug:
        vis = img.copy()
        for (x, y, w, h) in bubble_boxes:
            cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 2)

        cv2.imshow("Detected Bubbles", vis)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return bubble_boxes

from src.utils.ocr_utils import OCR_SINGLETON
from src.utils.text_utils import group_text_by_proximity

def get_text_bubbles_from_image(image_path):
    """
    Detects text bubbles in an image using OCR and clustering.

    Args:
        image_path (str): The path to the image file.

    Returns:
        A list of (text, box) tuples, where each tuple represents a text bubble.
    """
    ocr_result = OCR_SINGLETON.read_text(image_path)
    grouped_text = group_text_by_proximity(ocr_result)
    return grouped_text