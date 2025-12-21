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
        processed_files = set() # Stores filenames that have been processed or are subsidiary

        # Map filenames to full paths for easy lookup
        path_map = {Path(p).name: p for p in image_paths}

        for main_file_name, entry in alt_config.items():
            if isinstance(entry, list):
                for alt_name in entry:
                     if alt_name in path_map:
                         processed_files.add(alt_name)
            elif isinstance(entry, dict):
                 if "alts" in entry and isinstance(entry["alts"], list):
                     for alt_name in entry["alts"]:
                         if alt_name in path_map:
                             processed_files.add(alt_name)
                 if "translations" in entry and isinstance(entry["translations"], dict):
                     for trans_name in entry["translations"].values():
                         if trans_name in path_map:
                             processed_files.add(trans_name)

        for path in image_paths:
            name = Path(path).name
                
            if name in processed_files:
                continue

            variants = [path]
            processed_files.add(name)

            if name in alt_config:
                found_alts = []
                translations = {}
                entry = alt_config[name]
                
                # Check structure type: List (Legacy) vs Dict (New)
                if isinstance(entry, list):
                     for alt_name in entry:
                        if alt_name in path_map:
                            found_alts.append(path_map[alt_name])
                            processed_files.add(alt_name)
                elif isinstance(entry, dict):
                     # 1. Alts
                     if "alts" in entry and isinstance(entry["alts"], list):
                         for alt_name in entry["alts"]:
                             if alt_name in path_map:
                                 found_alts.append(path_map[alt_name])
                                 processed_files.add(alt_name)
                             else:
                                 main_dir = Path(path).parent
                                 alt_path_check = main_dir / "alts" / alt_name
                                 if alt_path_check.exists():
                                     found_alts.append(str(alt_path_check))

                     # 2. Translations
                     if "translations" in entry and isinstance(entry["translations"], dict):
                         for lang_key, trans_file in entry["translations"].items():
                             if trans_file in path_map:
                                 translations[lang_key] = path_map[trans_file]
                                 processed_files.add(trans_file)
                             else:
                                 # Check 'translations/<LANG>/<filename>'
                                 main_dir = Path(path).parent
                                 trans_path_check = main_dir / "translations" / lang_key / trans_file
                                 if trans_path_check.exists():
                                     translations[lang_key] = str(trans_path_check)


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
                
                grouped_pages.append(Page(variants, translations))
            else:
                grouped_pages.append(Page(variants, None))
        
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
        Returns a structure:
        {
            "Chapter Name": {
                "main_image.jpg": {
                    "alts": ["alt1.jpg"],
                    "translations": {"ENG": "eng.jpg"}
                }
            }
        }
        Legacy format (config value is list) is also supported during read, 
        but writes should migrate to new format.
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
    def _ensure_entry_structure(entry):
        """Convert list entry to dict entry if necessary."""
        if isinstance(entry, list):
            return {"alts": entry, "translations": {}}
        if "alts" not in entry: entry["alts"] = []
        if "translations" not in entry: entry["translations"] = {}
        return entry

    @staticmethod
    def link_pages(series_path: str, chapter_name: str, main_file: str, alt_files: List[str]):
        """
        Link alt_files to main_file for a specific chapter.
        Stores in the 'alts' list.
        """
        data = AltManager.load_alts(series_path)
        
        if chapter_name not in data:
            data[chapter_name] = {}
        
        # Ensure we are using filenames or relative paths
        main_name = Path(main_file).name
        alt_names = [p.replace('\\', '/') for p in alt_files]

        # Init or Migrate entry
        if main_name in data[chapter_name]:
            entry = AltManager._ensure_entry_structure(data[chapter_name][main_name])
        else:
            entry = {"alts": [], "translations": {}}

        # Update alts
        existing_alts = set(entry["alts"])
        existing_alts.update(alt_names)
        if main_name in existing_alts:
            existing_alts.remove(main_name)
            
        entry["alts"] = sorted(list(existing_alts))
        data[chapter_name][main_name] = entry

        # Clean up: Ensure alt files are not keys themselves
        for alt in alt_names:
            if alt in data[chapter_name]:
                # Merge its alts?
                sub_entry = data[chapter_name].pop(alt)
                # If sub_entry was list
                if isinstance(sub_entry, list):
                    sub_alts = sub_entry
                else:
                    sub_alts = sub_entry.get("alts", [])
                    # What about translations in the merged child? 
                    # For now just merging alts. Translations on alts might be edge case.
                
                for sub in sub_alts:
                    if sub != main_name and sub not in entry["alts"]:
                         entry["alts"].append(sub)
                
                # Re-sort
                entry["alts"].sort()

        AltManager.save_alts(series_path, data)

    from src.enums import Language
    @staticmethod
    def link_translation(series_path: str, chapter_name: str, main_file: str, lang: Language, translation_file: str):
        """
        Link a translation file to the main file.
        """
        data = AltManager.load_alts(series_path)
        
        if chapter_name not in data:
            data[chapter_name] = {}
            
        main_name = Path(main_file).name
        trans_name = Path(translation_file).name
        
        # Init or Migrate
        if main_name in data[chapter_name]:
            entry = AltManager._ensure_entry_structure(data[chapter_name][main_name])
        else:
            entry = {"alts": [], "translations": {}}
            
        # Update translation
        entry["translations"][lang.value] = trans_name
        data[chapter_name][main_name] = entry
        
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

        # Case 2: It is an Alt/Translation inside some Main file
        for main_img, entry in data[chapter_name].items():
            entry = AltManager._ensure_entry_structure(entry)
            
            # Check alts
            if target_name in entry["alts"]:
                entry["alts"].remove(target_name)
                # If empty, keep empty list
            
            # Check translations
            keys_to_remove = []
            for lang, trans_file in entry["translations"].items():
                if trans_file == target_name:
                    keys_to_remove.append(lang)
            for k in keys_to_remove:
                del entry["translations"][k]

            # Save (even if struct didn't change effectively, migration might have happened)
            data[chapter_name][main_img] = entry
            AltManager.save_alts(series_path, data)
            return
