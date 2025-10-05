import requests
import json
import os
from pathlib import Path

def get_info_from_manga_dex(title: str):
    """
    Get manga info from MangaDex API by title.
    """
    try:
        response = requests.get(f"https://api.mangadex.org/manga?includes[]=author&includes[]=artist&includes[]=cover_art&title={title}")
        response.raise_for_status()
        data = response.json()
        if data["data"]:
            # print(json.dumps(data["data"], ensure_ascii=False))
            return data["data"]
        return None
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None

def get_manga_dex_author(id: str):
    try:
        response = requests.get(f"https://api.mangadex.org/author/{id}")
        response.raise_for_status()
        data = response.json()
        if data["data"]:
            return data["data"]["attributes"]["name"]
        return None
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None
    
def get_cover_from_manga_dex(manga_id: str, filename:str):
    url = f"https://uploads.mangadex.org/covers/{manga_id}/{filename}"
    cache_dir = Path(".cache/search_covers")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    image_path = cache_dir / filename
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(image_path, 'wb') as f:
            f.write(response.content)
        return str(image_path)
    except requests.exceptions.RequestException as e:
        print(f"An error occurred while downloading cover: {e}")
        return None