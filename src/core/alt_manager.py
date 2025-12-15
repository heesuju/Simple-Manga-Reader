import json
import os
from pathlib import Path
from typing import Dict, List

from src.data.page import Page
class AltManager:
    INFO_FILE_NAME = "info.json"

    @staticmethod
    def group_images(image_paths: List[str], alt_config: Dict[str, Dict[str, List[str]]]) -> List[Page]:
        """
        Group raw image paths into Page objects based on configuration.
        """
        grouped_pages = []
        processed_files = set()
        
        # Map filenames to full paths for easy lookup
        path_map = {Path(p).name: p for p in image_paths}

        # Collect all subsidiary files (alts) to know what to skip
        subsidiary_files = set()
        for alts_list in alt_config.values():
            for alt_name in alts_list:
                subsidiary_files.add(alt_name)

        for path in image_paths:
            name = Path(path).name
            
            # If this file is a known alternate of another file, skip it.
            if name in subsidiary_files:
                continue
                
            if name in processed_files:
                continue

            variants = [path]
            processed_files.add(name)

            if name in alt_config:
                found_alts = []
                for alt_name in alt_config[name]:
                    if alt_name in path_map:
                        found_alts.append(path_map[alt_name])
                        processed_files.add(alt_name)
                
                # Sort alts: Image < GIF < Video, then filename
                # Priority: 0=Image, 1=GIF, 2=Video
                ANIM_EXTS = {'.gif'}
                VIDEO_EXTS = {'.mp4', '.webm', '.mkv', '.avi', '.mov'}
                
                def get_priority(path_str):
                    suffix = Path(path_str).suffix.lower()
                    if suffix in VIDEO_EXTS: return 2
                    if suffix in ANIM_EXTS: return 1
                    return 0 # Image
                
                found_alts.sort(key=lambda p: (get_priority(p), Path(p).suffix.lower(), Path(p).name.lower()))
                variants.extend(found_alts)
            
            grouped_pages.append(Page(variants))
        
        return grouped_pages
    INFO_FILE_NAME = "info.json"

    @staticmethod
    def _get_info_path(series_path: str) -> Path:
        return Path(series_path) / AltManager.INFO_FILE_NAME

    @staticmethod
    def load_alts(series_path: str) -> Dict[str, Dict[str, List[str]]]:
        """
        Load the alt configuration from info.json.
        Returns a structure:
        {
            "Chapter Name": {
                "main_image.jpg": ["alt1.jpg", "alt2.jpg"]
            }
        }
        """
        info_path = AltManager._get_info_path(series_path)
        if not info_path.exists():
            return {}

        try:
            with open(info_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def save_alts(series_path: str, data: Dict[str, Dict[str, List[str]]]):
        """Save the alt configuration to info.json."""
        info_path = AltManager._get_info_path(series_path)
        try:
            with open(info_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            print(f"Error saving info.json: {e}")

    @staticmethod
    def link_pages(series_path: str, chapter_name: str, main_file: str, alt_files: List[str]):
        """
        Link alt_files to main_file for a specific chapter.
        This updates the existing configuration or creates a new one.
        """
        data = AltManager.load_alts(series_path)
        
        if chapter_name not in data:
            data[chapter_name] = {}
        
        # Ensure we are using filenames, not full paths
        main_name = Path(main_file).name
        alt_names = [Path(p).name for p in alt_files]

        # If main_name already has alts, append unique ones
        if main_name in data[chapter_name]:
            existing_alts = set(data[chapter_name][main_name])
            existing_alts.update(alt_names)
            # Remove main_name if it accidentally got into alts
            if main_name in existing_alts:
                existing_alts.remove(main_name)
            data[chapter_name][main_name] = sorted(list(existing_alts))
        else:
            data[chapter_name][main_name] = sorted(alt_names)

        # Clean up: Ensure alt files are not keys themselves (naive approach, but safe for now)
        for alt in alt_names:
            if alt in data[chapter_name]:
                # Merge its alts into the new main? Or just delete?
                # For simplicity, move its alts to main and delete entry
                sub_alts = data[chapter_name].pop(alt)
                for sub in sub_alts:
                    if sub != main_name and sub not in data[chapter_name][main_name]:
                         data[chapter_name][main_name].append(sub)

        AltManager.save_alts(series_path, data)

    @staticmethod
    def unlink_page(series_path: str, chapter_name: str, file_name: str):
        """
        Remove a file from any grouping in the chapter.
        It could be a main file (delete key) or an alt file (remove from list).
        """
        data = AltManager.load_alts(series_path)
        if chapter_name not in data:
            return

        target_name = Path(file_name).name
        
        # Case 1: It is a Main file
        if target_name in data[chapter_name]:
            del data[chapter_name][target_name]
            AltManager.save_alts(series_path, data)
            return

        # Case 2: It is an Alt file inside some Main file
        for main_img, alts in data[chapter_name].items():
            if target_name in alts:
                alts.remove(target_name)
                # If alts is empty, we can keep the main img key or remove it?
                # Keeping it is harmless, but removing cleans up.
                if not alts:
                     del data[chapter_name][main_img]
                AltManager.save_alts(series_path, data)
                return
