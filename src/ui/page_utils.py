import shutil
import os
import uuid
import subprocess
from pathlib import Path
from typing import List, Set, Callable, Optional, TYPE_CHECKING

from PyQt6.QtWidgets import QApplication, QFileDialog, QWidget
from PyQt6.QtCore import QObject

from src.core.alt_manager import AltManager
from src.data.reader_model import ReaderModel

def save_page_as(parent: QWidget, model: ReaderModel, index: int):
    page = model.images[index]
    if not page:
        return
        
    src_path = page.images[0]
    # Don't support saving directly from virtual paths (zips) efficiently yet without extraction logic 
    # If the path contains '|', it's a virtual path.
    if '|' in src_path:
         return
    
    path_to_save = src_path
    if not os.path.exists(path_to_save):
        return

    base_name = os.path.basename(path_to_save)
    ext = os.path.splitext(base_name)[1]
    
    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    initial_path = os.path.join(downloads_dir, base_name)
    
    file_path, _ = QFileDialog.getSaveFileName(
        parent,
        "Save Image As",
        initial_path,
        f"Image (*{ext});;All Files (*)"
    )
    
    if file_path:
        try:
            shutil.copy2(path_to_save, file_path)
        except Exception as e:
            print(f"Error copying image: {e}")

def link_selected_pages(model: ReaderModel, indices: Set[int], on_reload: Callable[[], None], on_page_changed: Callable[[int], None]):
    if len(indices) < 2:
        return
    
    sorted_indices = sorted(list(indices))
    main_page_idx = sorted_indices[0]
    
    main_page = model.images[main_page_idx]
    if not main_page: return

    all_paths = []
    for idx in sorted_indices:
        page = model.images[idx]
        if page:
            all_paths.extend(page.images)

    unique_paths = []
    seen = set()
    for p in all_paths:
        if p not in seen:
            unique_paths.append(p)
            seen.add(p)
    
    series_path = model.series['path']
    chapter_dir = Path(model.manga_dir)
    chapter_name = chapter_dir.name
    
    main_file = unique_paths[0]
    original_alt_files = unique_paths[1:]
    
    main_stem = Path(main_file).stem
    
    alts_dir = chapter_dir / "alts"
    if not alts_dir.exists():
        alts_dir.mkdir(parents=True, exist_ok=True)
        
    final_alt_files = []
    for i, alt_path in enumerate(original_alt_files):
        p = Path(alt_path)
        new_name = f"{main_stem}_{i+1}{p.suffix}"
        dst = alts_dir / new_name

        counter = i + 1
        while dst.exists() and dst.resolve() != p.resolve():
            new_name = f"{main_stem}_{counter}_{uuid.uuid4().hex[:4]}{p.suffix}"
            dst = alts_dir / new_name
        
        if alts_dir in p.parents and p.name == new_name:
            final_alt_files.append(str(p))
        else:
            try:
                shutil.move(p, dst)
                final_alt_files.append(str(dst))
            except Exception as e:
                print(f"Error moving alt {p}: {e}")
                final_alt_files.append(str(p))
    
    AltManager.link_pages(series_path, chapter_name, main_file, final_alt_files)
    
    if on_reload:
        on_reload()
    if on_page_changed:
        on_page_changed(main_page_idx + 1)

def unlink_page(model: ReaderModel, index: int):
    page = model.images[index]
    if not page: return
    
    series_path = model.series['path']
    chapter_dir = Path(model.manga_dir)
    if isinstance(chapter_dir, str): chapter_dir = Path(chapter_dir)
    chapter_name = chapter_dir.name
    
    current_file_path = Path(page.path)
    
    main_file_path = Path(page.images[0])
    is_main_file = (current_file_path.resolve() == main_file_path.resolve())
    
    AltManager.unlink_page(series_path, chapter_name, str(current_file_path))
    
    files_to_rename = []
    
    if is_main_file:
        files_to_rename = [Path(p) for p in page.images if Path(p).resolve() != main_file_path.resolve()]
    else:
        files_to_rename = [current_file_path]
        
    for p in files_to_rename:
        if "alts" in str(p.parent.name):
            new_stem = f"{p.stem}_detached_{uuid.uuid4().hex[:8]}"
            new_name = f"{new_stem}{p.suffix}"
            dst_path = p.parent / new_name
            
            try:
                shutil.move(p, dst_path)
            except Exception as e:
                print(f"Error moving detached file: {e}")
    
    model.update_page_variants(index)

def open_in_explorer(model: ReaderModel, index: int):
    page = model.images[index]
    if not page:
         return
         
    path = page.images[0]
    if '|' in path:
        path = path.split('|')[0]
        
    path = os.path.normpath(path)
    
    if os.name == 'nt':
        subprocess.Popen(['explorer', '/select,', str(path)])

def process_add_alts(model: ReaderModel, file_paths: List[str], target_index: int, on_reload: Callable[[], None], on_variants_updated: Callable[[int], None]):
    target_page = model.images[target_index]
    if not target_page: return
    
    target_main_file = target_page.images[0]
    
    chapter_dir = Path(model.manga_dir)
    alts_dir = chapter_dir / "alts"
    if not alts_dir.exists():
        try:
            alts_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"Error creating alts directory: {e}")
            return

    series_path = model.series['path']
    chapter_name = chapter_dir.name
    
    files_to_link = []
    main_stem = Path(target_main_file).stem
    start_index = len(target_page.images)
    if start_index < 1: start_index = 1

    for i, file_path in enumerate(file_paths):
        src_path = Path(file_path)
        if not src_path.exists(): continue
        
        new_name = f"{main_stem}_{start_index + i}{src_path.suffix}"
        dst_path = alts_dir / new_name
        
        while dst_path.exists() and dst_path.resolve() != src_path.resolve():
             new_name = f"{main_stem}_{start_index + i}_{uuid.uuid4().hex[:4]}{src_path.suffix}"
             dst_path = alts_dir / new_name
        
        if src_path.resolve() == dst_path.resolve():
            files_to_link.append(str(dst_path))
            continue

        try:
            target_parent = Path(target_main_file).parent.resolve()
            src_parent = src_path.parent.resolve()
            
            if src_parent == target_parent:
                 shutil.move(src_path, dst_path)
            else:
                 shutil.copy2(src_path, dst_path)
                 
            files_to_link.append(str(dst_path))
            
        except Exception as e:
            print(f"Error processing file {src_path}: {e}")

    if files_to_link:
        AltManager.link_pages(series_path, chapter_name, target_main_file, files_to_link)
        
        needs_full_reload = False
        for fp in file_paths:
            p = Path(fp)
            if chapter_dir.resolve() in p.resolve().parents:
                if p.parent.name != "alts":
                    needs_full_reload = True
                    break
        
        if needs_full_reload:
             if on_reload: on_reload()
        else:
             if on_variants_updated: on_variants_updated(target_index)

def save_merged_pair_as(parent: QWidget, model: ReaderModel, layout_index: int):
    if layout_index < 0 or layout_index >= len(model._layout_pairs):
        return

    left, right = model._layout_pairs[layout_index]
    
    valid_left = left and hasattr(left, 'path') and left.path != "placeholder"
    valid_right = right and hasattr(right, 'path') and right.path != "placeholder"

    if valid_left and not valid_right:
        idx = model.get_page_index(left.path)
        save_page_as(parent, model, idx)
        return
    elif valid_right and not valid_left:
        idx = model.get_page_index(right.path)
        save_page_as(parent, model, idx)
        return
    elif not valid_left and not valid_right:
        return

    path_left = left.images[0]
    path_right = right.images[0]
    
    if '|' in path_left or '|' in path_right:
         return

    from PyQt6.QtGui import QImage, QPainter, QColor
    from PyQt6.QtCore import QPoint

    img_left = QImage(path_left)
    img_right = QImage(path_right)
    
    if img_left.isNull() or img_right.isNull():
        return

    h = max(img_left.height(), img_right.height())
    w = img_left.width() + img_right.width()
    
    merged = QImage(w, h, QImage.Format.Format_ARGB32)
    merged.fill(QColor(0, 0, 0, 0))
    
    p = QPainter(merged)
    p.drawImage(0, 0, img_left)
    p.drawImage(img_left.width(), 0, img_right)
    p.end()
    
    base_name = os.path.basename(path_left)
    name_part, ext = os.path.splitext(base_name)
    default_name = f"{name_part}_merged{ext}"
    
    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    initial_path = os.path.join(downloads_dir, default_name)
    
    file_path, _ = QFileDialog.getSaveFileName(
        parent,
        "Save Merged Image As",
        initial_path,
        f"Image (*{ext});;PNG (*.png);;JPG (*.jpg);;All Files (*)"
    )
    
    if file_path:
        merged.save(file_path)
