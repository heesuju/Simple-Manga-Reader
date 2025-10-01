import requests

def get_info_from_manga_dex(title: str):
    """
    Get manga info from MangaDex API by title.
    """
    try:
        response = requests.get(f"https://api.mangadex.org/manga", params={"title": title})
        response.raise_for_status()
        data = response.json()
        if data["data"]:
            return data["data"][0]
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