import numpy as np
from collections import defaultdict

def get_box_center(box):
    """Calculates the center of a bounding box."""
    return np.mean(box, axis=0)

def get_box_dimensions(box):
    """Calculates the width and height of a bounding box."""
    min_coords = np.min(box, axis=0)
    max_coords = np.max(box, axis=0)
    return max_coords - min_coords

def group_text_by_proximity(ocr_result, x_dist_ratio=0.7, y_dist_ratio=1.0):
    """
    Groups OCR text results based on proximity.

    Args:
        ocr_result: The result from easyocr.readtext.
        x_dist_ratio: The horizontal distance between box centers, as a ratio of the average width,
                      to be considered in the same group.
        y_dist_ratio: The vertical distance between box centers, as a ratio of the average height,
                      to be considered in the same group.

    Returns:
        A list of strings, where each string is a group of text ordered from top-right to bottom-left.
    """
    if not ocr_result:
        return []

    boxes = []
    for i, (box_coords, text, _) in enumerate(ocr_result):
        center = get_box_center(np.array(box_coords))
        width, height = get_box_dimensions(np.array(box_coords))
        boxes.append({
            "id": i,
            "text": text,
            "box": box_coords,
            "center_x": center[0],
            "center_y": center[1],
            "width": width,
            "height": height
        })

    # Build adjacency list
    adj = defaultdict(list)
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            box1 = boxes[i]
            box2 = boxes[j]

            x_dist = abs(box1["center_x"] - box2["center_x"])
            y_dist = abs(box1["center_y"] - box2["center_y"])

            avg_width = (box1["width"] + box2["width"]) / 2
            avg_height = (box1["height"] + box2["height"]) / 2
            
            if x_dist < avg_width * x_dist_ratio and y_dist < avg_height * y_dist_ratio:
                adj[i].append(j)
                adj[j].append(i)

    # Find connected components (groups) using BFS
    visited = set()
    groups = []
    for i in range(len(boxes)):
        if i not in visited:
            component = []
            q = [i]
            visited.add(i)
            while q:
                u = q.pop(0)
                component.append(boxes[u])
                for v in adj[u]:
                    if v not in visited:
                        visited.add(v)
                        q.append(v)
            groups.append(component)

    # Sort and join text in each group
    result_groups = []
    for group in groups:
        # Sort top-to-bottom, then right-to-left
        group.sort(key=lambda b: (b["center_y"], -b["center_x"]))
        
        # Calculate union of bounding boxes
        all_boxes = np.vstack([b["box"] for b in group])
        min_x, min_y = np.min(all_boxes, axis=0)
        max_x, max_y = np.max(all_boxes, axis=0)
        
        text = " ".join([b["text"] for b in group])
        result_groups.append((text, (min_x, min_y, max_x, max_y)))

    return result_groups
