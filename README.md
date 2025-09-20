This is a simple manga reader that reads from multiple folders labeled by chapters.

## Setup

### Install Requirements
```sh
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements
```

### Setup Registry to add Right-click option
Open cmd with admin
```sh
.\.venv\Scripts\activate
python reg.py
```

### How to Use:
1. Right-click folder containing chapters and click `View in Manga Reader`
2. Select the chapter to read
3. Click left and right sides to change page and ctrl + scroll to zoom

### Features:
1. View manga pages by right-clicking folders in file explorer
2. Orders chapters by number
3. Zoom with ctrl+scroll (reset by double-clicking)
4. left and right sides of image change pages
5. Skips to next chapter without needing to open another folder (e.g. ch1. last page -> ch1. first page)

### To Do:
- [X] Simple grid layout to show chapters
- [X] Support for long strip viewing mode
- [X] Support for double page viewing mode
- [X] Grid view for pages
- [X] View zip files
- [ ] Use uniform ratio for single/double mode
- [ ] Bookmarks

### Disclaimer:
- Ignores `vol` in chapter folders. (e.g. `Vol 1. Ch2` and `Vol 0. Ch3` are ordered `Ch2` and `Ch3`)