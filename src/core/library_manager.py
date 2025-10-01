import os
from .library_scanner import LibraryScanner
from src.utils.database_utils import get_db_connection

class LibraryManager:
    def __init__(self):
        self.init_db()

    def init_db(self):
        conn = get_db_connection()
        # The create_tables function from database_utils can be called here if needed
        # to ensure tables are created on startup.
        conn.close()

    def get_series(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM series")
        series_list = [dict(row) for row in cursor.fetchall()]
        conn.close()
        # For each series, you might want to load its chapters as well
        for series in series_list:
            series['chapters'] = self.get_chapters(series)
        return series_list

    def search_series(self, search_term):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM series WHERE name LIKE ?", (f'%{search_term}%',))
        series_list = [dict(row) for row in cursor.fetchall()]
        conn.close()
        for series in series_list:
            series['chapters'] = self.get_chapters(series)
        return series_list

    def get_chapters(self, series):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chapters WHERE series_id = ?", (series['id'],))
        chapters = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return chapters

    def add_series(self, path):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM series WHERE path = ?", (path,))
        if cursor.fetchone():
            conn.close()
            return  # Series already exists

        scanner = LibraryScanner()
        series_data = scanner.scan_series(path)
        if series_data:
            try:
                cursor.execute(
                    "INSERT INTO series (name, path, cover_image) VALUES (?, ?, ?)",
                    (series_data['name'], series_data['path'], series_data['cover_image'])
                )
                series_id = cursor.lastrowid
                for chapter in series_data.get('chapters', []):
                    cursor.execute(
                        "INSERT INTO chapters (series_id, name, path) VALUES (?, ?, ?)",
                        (series_id, chapter['name'], chapter['path'])
                    )
                conn.commit()
            except Exception as e:
                print(f"Error adding series: {e}")
                conn.rollback()
            finally:
                conn.close()

    def add_series_batch(self, paths):
        for path in paths:
            self.add_series(path)

    def remove_series(self, series_to_remove):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # First, delete chapters associated with the series
            cursor.execute("DELETE FROM chapters WHERE series_id = ?", (series_to_remove['id'],))
            # Then, delete the series itself
            cursor.execute("DELETE FROM series WHERE id = ?", (series_to_remove['id'],))
            conn.commit()
        except Exception as e:
            print(f"Error removing series: {e}")
            conn.rollback()
        finally:
            conn.close()

    def update_last_read_chapter(self, series_id, chapter_path):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE series SET last_read_chapter = ? WHERE id = ?", (chapter_path, series_id))
            conn.commit()
        except Exception as e:
            print(f"Error updating last read chapter: {e}")
            conn.rollback()
        finally:
            conn.close()

    def update_series_info(self, series_path, new_info):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Assuming new_info is a dictionary with column names as keys
            # This example only updates the name. Extend as needed.
            if 'name' in new_info:
                cursor.execute("UPDATE series SET name = ? WHERE path = ?", (new_info['name'], series_path))
            conn.commit()
        except Exception as e:
            print(f"Error updating series info: {e}")
            conn.rollback()
        finally:
            conn.close()