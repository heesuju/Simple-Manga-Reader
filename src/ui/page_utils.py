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
    
    # Target directory structure: alts/{main_stem}/main/
    alts_root_dir = chapter_dir / "alts"
    specific_alts_dir = alts_root_dir / main_stem / "main"
    if not specific_alts_dir.exists():
        specific_alts_dir.mkdir(parents=True, exist_ok=True)
        
    final_alt_files = []
    
    # To avoid naming collisions during multi-move, check current occupancy
    existing_in_category = 0
    if specific_alts_dir.exists():
        for f in specific_alts_dir.iterdir():
            if f.is_file() and f.stem.startswith("main") and not f.stem.endswith('_fix'):
                existing_in_category += 1
    
    start_index = existing_in_category + 1

    for i, alt_path in enumerate(original_alt_files):
        p = Path(alt_path)
        if not p.exists(): continue
        
        new_name = f"main_{start_index + i}{p.suffix}"
        dst = specific_alts_dir / new_name

        while dst.exists() and dst.resolve() != p.resolve():
            new_name = f"main_{start_index + i}_{uuid.uuid4().hex[:4]}{p.suffix}"
            dst = specific_alts_dir / new_name
        
        if p.resolve() == dst.resolve():
            try:
                rel_path = dst.relative_to(chapter_dir)
                final_alt_files.append(str(rel_path).replace('\\', '/'))
            except ValueError:
                final_alt_files.append(str(dst))
            continue
            
        try:
            shutil.move(p, dst)
            try:
                rel_path = dst.relative_to(chapter_dir)
                final_alt_files.append(str(rel_path).replace('\\', '/'))
            except ValueError:
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
    
    # Load alts_fix to identify pairs
    series_path = model.series['path']
    current_data = AltManager.load_alts(series_path)
    main_name = main_file_path.name
    ch_entry = current_data.get(chapter_name, {}).get(main_name, {})
    if isinstance(ch_entry, list):
        ch_entry = {"alts": ch_entry, "translations": {}}
    alts_fix = ch_entry.get("alts_fix", {})
    fix_to_orig = {v: k for k, v in alts_fix.items()}

    def get_pair_abs(p_abs):
        try:
            rel = str(p_abs.relative_to(chapter_dir)).replace('\\', '/')
        except ValueError:
            return [p_abs]
        if rel in alts_fix:
            return [p_abs, chapter_dir / alts_fix[rel]]
        if rel in fix_to_orig:
            return [p_abs, chapter_dir / fix_to_orig[rel]]
        return [p_abs]

    files_to_detach = []
    if is_main_file:
        for p_str in page.images:
            p_abs = Path(p_str)
            if p_abs.resolve() != main_file_path.resolve():
                files_to_detach.extend(get_pair_abs(p_abs))
    else:
        files_to_detach = get_pair_abs(current_file_path)
    
    # Now that we've identified what to detach on disk, remove from metadata
    AltManager.unlink_page(series_path, chapter_name, str(current_file_path))
        
    seen = set()
    for p in files_to_detach:
        p_res = p.resolve()
        if p_res in seen: continue
        seen.add(p_res)
        
        if not p.exists(): continue
        
        # If it's in any 'alts' hierarchy, we move it out/rename it
        if "alts" in [parent.name.lower() for parent in p.parents]:
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

def apply_alt_edits(model: ReaderModel, page_obj, new_structure: dict) -> bool:
    """
    Applies edited category groups and orders to a page's alternates.
    Renames and moves files on disk safely, then updates info.json.
    """
    if not page_obj or not page_obj.images: return False

    main_file = page_obj.images[0]
    main_name = Path(main_file).name
    main_stem = Path(main_file).stem
    chapter_dir = Path(model.manga_dir)
    alts_dir = chapter_dir / "alts"
    series_path = model.series['path']
    chapter_name = chapter_dir.name

    # Load current alts_fix before any changes
    current_data = AltManager.load_alts(series_path)
    ch_full_entry = current_data.get(chapter_name, {}).get(main_name, {})
    if isinstance(ch_full_entry, list):
        ch_full_entry = {"alts": ch_full_entry, "translations": {}}
    alts_fix = dict(ch_full_entry.get("alts_fix", {}))
    fix_to_orig = {v: k for k, v in alts_fix.items()}

    # Helper to get both paths if they exist
    def get_variant_pair(abs_path):
        try:
            rel = str(Path(abs_path).relative_to(chapter_dir)).replace('\\', '/')
        except ValueError:
            return abs_path, None, None, None
        
        if rel in alts_fix: # Current is original
            f_rel = alts_fix[rel]
            return abs_path, str(chapter_dir / f_rel), rel, f_rel
        if rel in fix_to_orig: # Current is fix
            o_rel = fix_to_orig[rel]
            return str(chapter_dir / o_rel), abs_path, o_rel, rel
        return abs_path, None, rel, None

    # 1. Handle Removal
    new_flat = {p for paths in new_structure.values() for p in paths if p != main_file}
    removed_abs_paths = [p for p in page_obj.images[1:] if p not in new_flat]

    for removed_abs in removed_abs_paths:
        orig_abs, fix_abs, orig_rel, fix_rel = get_variant_pair(removed_abs)
        
        # If the user chose to delete from disk in the dialog, ONE of these might already be gone.
        # We ensure BOTH are gone if they exist, to prevent orphans.
        for p_abs in [orig_abs, fix_abs]:
            if p_abs and os.path.exists(p_abs):
                try:
                    os.remove(p_abs)
                except OSError:
                    pass
        
        # Clean alts_fix map
        if orig_rel in alts_fix:
            del alts_fix[orig_rel]

    # 2. Process Moves/Renames
    flat_new_paths = [main_file]
    new_alts_fix = {}

    for cat_name, file_paths in new_structure.items():
        cat_dir = alts_dir / main_stem / cat_name.lower()
        if not cat_dir.exists():
            cat_dir.mkdir(parents=True, exist_ok=True)

        temp_moves = [] # List of ((orig_temp, fix_temp), (orig_old_rel, fix_old_rel))
        for path_str in file_paths:
            if path_str == main_file: continue
            
            o_abs, f_abs, o_rel, f_rel = get_variant_pair(path_str)
            
            o_temp = None
            if o_abs and os.path.exists(o_abs):
                o_temp = cat_dir / f"temp_o_{uuid.uuid4().hex[:8]}{Path(o_abs).suffix}"
                shutil.move(o_abs, o_temp)
            
            f_temp = None
            if f_abs and os.path.exists(f_abs):
                f_temp = cat_dir / f"temp_f_{uuid.uuid4().hex[:8]}{Path(f_abs).suffix}"
                shutil.move(f_abs, f_temp)
            
            if o_temp or f_temp:
                temp_moves.append(((o_temp, f_temp), (o_rel, f_rel)))

        # Rename to final names
        for i, ((o_temp, f_temp), (o_old_rel, f_old_rel)) in enumerate(temp_moves):
            prefix = f"{cat_name.lower()}_{i + 1}"
            
            # Final original path
            o_final_rel = None
            if o_temp:
                o_final_path = cat_dir / f"{prefix}{o_temp.suffix}"
                shutil.move(o_temp, o_final_path)
                o_final_rel = str(o_final_path.relative_to(chapter_dir)).replace('\\', '/')
            
            # Final fix path
            f_final_rel = None
            if f_temp:
                # Retain _fix suffix if it exists
                f_final_path = cat_dir / f"{prefix}_fix{f_temp.suffix}"
                shutil.move(f_temp, f_final_path)
                f_final_rel = str(f_final_path.relative_to(chapter_dir)).replace('\\', '/')

            # Always store the original path in 'alts'; fix is tracked separately in 'alts_fix'
            if o_final_rel:
                flat_new_paths.append(o_final_rel)
            elif f_final_rel:
                flat_new_paths.append(f_final_rel)
                
            # Update alts_fix
            if o_final_rel and f_final_rel:
                new_alts_fix[o_final_rel] = f_final_rel

    # Update info.json
    alts_to_link = flat_new_paths[1:] if flat_new_paths[0] == main_file else flat_new_paths
    AltManager.update_alts_order(series_path, chapter_name, main_file, alts_to_link)

    data = AltManager.load_alts(series_path)
    if chapter_name in data and main_name in data[chapter_name]:
        entry = AltManager._ensure_entry_structure(data[chapter_name][main_name])
        if new_alts_fix:
            entry["alts_fix"] = new_alts_fix
        elif "alts_fix" in entry:
            del entry["alts_fix"]
        data[chapter_name][main_name] = entry
        AltManager.save_alts(series_path, data)

    # Cleanup empty category folders
    page_alts_root = alts_dir / main_stem
    if page_alts_root.exists() and page_alts_root.is_dir():
        for sub_dir in page_alts_root.iterdir():
            if sub_dir.is_dir() and sub_dir.name.lower() != "main":
                try:
                    if not any(sub_dir.iterdir()):
                        sub_dir.rmdir()
                except (OSError, StopIteration):
                    pass

    return True

def process_add_alts(model: ReaderModel, file_paths: List[str], target_index: int, on_reload: Callable[[], None], on_variants_updated: Callable[[int], None], category: str = None):
    from src.utils.str_utils import natural_sort_key
    file_paths = sorted(file_paths, key=lambda p: natural_sort_key(Path(p).name))
    
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
    
    if category:
        main_stem = category
        cat_dir_name = category.lower()
    else:
        main_stem = "main"
        cat_dir_name = "main"

    # Store subfolders of original file name (original page) first, then put subfolders inside that have categories in there
    original_file_stem = Path(target_main_file).stem
    specific_alts_dir = alts_dir / original_file_stem / cat_dir_name
    if not specific_alts_dir.exists():
        try:
            specific_alts_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"Error creating specific alts sub-directory: {e}")
            return
    
    # Calculate start index dynamically based strictly on files inside this specific category folder
    existing_in_category = 0
    if specific_alts_dir.exists():
        for f in specific_alts_dir.iterdir():
            if f.is_file() and f.stem.startswith(main_stem) and not f.stem.endswith('_fix'):
                existing_in_category += 1
                
    start_index = existing_in_category + 1

    for i, file_path in enumerate(file_paths):
        src_path = Path(file_path)
        if not src_path.exists(): continue
        
        new_name = f"{main_stem}_{start_index + i}{src_path.suffix}"
        dst_path = specific_alts_dir / new_name
        
        while dst_path.exists() and dst_path.resolve() != src_path.resolve():
             new_name = f"{main_stem}_{start_index + i}_{uuid.uuid4().hex[:4]}{src_path.suffix}"
             dst_path = specific_alts_dir / new_name
        
        if src_path.resolve() == dst_path.resolve():
            try:
                rel_path = dst_path.relative_to(chapter_dir)
                files_to_link.append(str(rel_path).replace('\\', '/'))
            except ValueError:
                files_to_link.append(str(dst_path))
            continue

        try:
            target_parent = Path(target_main_file).parent.resolve()
            src_parent = src_path.parent.resolve()
            
            if src_parent == target_parent:
                 shutil.move(src_path, dst_path)
            else:
                 shutil.copy2(src_path, dst_path)
                 
            try:
                rel_path = dst_path.relative_to(chapter_dir)
                files_to_link.append(str(rel_path).replace('\\', '/'))
            except ValueError:
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
        f"Image (*{ext});;PNG (*.png);;JPG (*.jpg *.jpeg *.jpe);;All Files (*)"
    )
    
    if file_path:
        merged.save(file_path)
