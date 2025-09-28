import numpy as np
from sklearn.cluster import DBSCAN

def group_text_by_proximity(results, y_threshold=10, eps=80, min_samples=1):
    """
    Group OCR results into bubbles/columns and sort them. 
    
    :param results: EasyOCR output [(bbox, text, conf), ...]
    :param y_threshold: tolerance for grouping words into the same line
    :param eps: clustering distance (adjust for bubble separation)
    :param min_samples: DBSCAN parameter
    """
    if not results:
        return []

    boxes = []
    centers = []
    for (bbox, text, conf) in results:
        x_coords = [p[0] for p in bbox]
        y_coords = [p[1] for p in bbox]
        x_min, y_min = min(x_coords), min(y_coords)
        x_max, y_max = max(x_coords), max(y_coords)
        cx, cy = (x_min + x_max) / 2, (y_min + y_max) / 2
        boxes.append(((x_min, y_min, x_max, y_max), text))
        centers.append([cx, cy])

    centers = np.array(centers)

    # Cluster by proximity
    clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(centers)
    labels = clustering.labels_

    bubbles = {}
    for label, (box, text) in zip(labels, boxes):
        if label not in bubbles:
            bubbles[label] = []
        bubbles[label].append((box, text))

    ordered_bubbles = {} # Use a dict to store text and box
    for label, items in bubbles.items():
        # Sort inside bubble
        items.sort(key=lambda b: (b[0][1], b[0][0]))  # y, then x

        # Group into lines
        lines = []
        current_line = []
        last_y = None
        for (x_min, y_min, x_max, y_max), text in items:
            if last_y is None or abs(y_min - last_y) < y_threshold:
                current_line.append((x_min, text))
                last_y = y_min if last_y is None else (last_y + y_min) / 2
            else:
                current_line.sort(key=lambda t: t[0])
                lines.append(" ".join([t[1] for t in current_line]))
                current_line = [(x_min, text)]
                last_y = y_min
        if current_line:
            current_line.sort(key=lambda t: t[0])
            lines.append(" ".join([t[1] for t in current_line]))

        # Calculate bubble bounding box
        all_boxes_in_bubble = [item[0] for item in items]
        min_x = min(box[0] for box in all_boxes_in_bubble)
        min_y = min(box[1] for box in all_boxes_in_bubble)
        max_x = max(box[2] for box in all_boxes_in_bubble)
        max_y = max(box[3] for box in all_boxes_in_bubble)
        
        ordered_bubbles[label] = ("\n".join(lines), (min_x, min_y, max_x, max_y))

    # Sort bubbles left-to-right, top-to-bottom
    bubble_positions = []
    for label, items in bubbles.items():
        y_top = min(b[1] for b, _ in items)
        x_left = min(b[0] for b, _ in items)
        bubble_positions.append((label, x_left, y_top))

    # Sort by top-to-bottom, then left-to-right
    bubble_positions.sort(key=lambda b: (b[2], b[1]))

    # Get the final sorted bubbles
    final_bubbles = []
    for label, _, _ in bubble_positions:
        # Check if the label exists in ordered_bubbles before accessing
        if label in ordered_bubbles:
            final_bubbles.append(ordered_bubbles[label])

    return final_bubbles