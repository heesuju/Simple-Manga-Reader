import os
from pathlib import Path
from datetime import datetime
from .library_scanner import LibraryScanner
from src.utils.database_utils import get_db_connection, create_tables

class LibraryManager:
    def __init__(self):
        self.init_db()

    def init_db(self):
        create_tables()
        conn = get_db_connection()
        conn.close()

    def get_series(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM series")
        series_list = [dict(row) for row in cursor.fetchall()]
        conn.close()
        for series in series_list:
            series['chapters'] = self.get_chapters(series)
            series['authors'] = self.get_authors(series['id'])
            series['genres'] = self.get_genres(series['id'])
        return series_list

    def search_series(self, search_term):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM series WHERE name LIKE ?", (f'%{search_term}%',))
        series_list = [dict(row) for row in cursor.fetchall()]
        conn.close()
        for series in series_list:
            series['chapters'] = self.get_chapters(series)
            series['authors'] = self.get_authors(series['id'])
            series['genres'] = self.get_genres(series['id'])
        return series_list

    def get_recently_opened_series(self, limit=20):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM series WHERE last_opened_date IS NOT NULL ORDER BY last_opened_date DESC LIMIT ?", (limit,))
        series_list = [dict(row) for row in cursor.fetchall()]
        conn.close()
        for series in series_list:
            series['chapters'] = self.get_chapters(series)
            series['authors'] = self.get_authors(series['id'])
            series['genres'] = self.get_genres(series['id'])
        return series_list

    def get_authors(self, series_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.name FROM authors a
            JOIN series_authors sa ON a.id = sa.author_id
            WHERE sa.series_id = ?
        """, (series_id,))
        authors = [row['name'] for row in cursor.fetchall()]
        conn.close()
        return authors

    def get_genres(self, series_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT g.name FROM genres g
            JOIN series_genres sg ON g.id = sg.genre_id
            WHERE sg.series_id = ?
        """, (series_id,))
        genres = [row['name'] for row in cursor.fetchall()]
        conn.close()
        return genres

    def get_all_authors(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM authors ORDER BY name")
        authors = [row['name'] for row in cursor.fetchall()]
        conn.close()
        return authors

    def get_all_genres(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM genres ORDER BY name")
        genres = [row['name'] for row in cursor.fetchall()]
        conn.close()
        return genres

    def search_series_with_filters(self, search_term, filters):
        conn = get_db_connection()
        cursor = conn.cursor()

        query = "SELECT DISTINCT s.* FROM series s"
        params = []
        joins = ""

        if filters.get('authors'):
            joins += " JOIN series_authors sa ON s.id = sa.series_id JOIN authors a ON sa.author_id = a.id"
            query += joins
            query += " WHERE a.name IN ({})".format(', '.join('?'*len(filters['authors'])))
            params.extend(filters['authors'])
        
        if filters.get('genres'):
            if not joins: # if joins is empty, we need to add the joins
                joins += " JOIN series_genres sg ON s.id = sg.series_id JOIN genres g ON sg.genre_id = g.id"
                query += joins
                query += " WHERE g.name IN ({})".format(', '.join('?'*len(filters['genres'])))
            else: # if joins is not empty, we need to use AND
                query += " AND s.id IN (SELECT s.id FROM series s JOIN series_genres sg ON s.id = sg.series_id JOIN genres g ON sg.genre_id = g.id WHERE g.name IN ({})) ".format(', '.join('?'*len(filters['genres'])))
            params.extend(filters['genres'])

        if search_term:
            if not filters.get('authors') and not filters.get('genres'):
                query += " WHERE s.name LIKE ?"
            else:
                query += " AND s.name LIKE ?"
            params.append(f'%{search_term}%')

        cursor.execute(query, params)
        series_list = [dict(row) for row in cursor.fetchall()]
        conn.close()

        for series in series_list:
            series['chapters'] = self.get_chapters(series)
            series['authors'] = self.get_authors(series['id'])
            series['genres'] = self.get_genres(series['id'])
        
        return series_list

    def get_series_by_path(self, path):
        normalized_path = str(Path(path))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM series WHERE path = ?", (normalized_path,))
        series_row = cursor.fetchone()
        conn.close()
        if series_row:
            series = dict(series_row)
            series['chapters'] = self.get_chapters(series)
            series['authors'] = self.get_authors(series['id'])
            series['genres'] = self.get_genres(series['id'])
            return series
        return None

    def get_chapters(self, series):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chapters WHERE series_id = ?", (series['id'],))
        chapters = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return chapters

    def add_series(self, path, metadata=None):
        normalized_path = str(Path(path))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM series WHERE path = ?", (normalized_path,))
        if cursor.fetchone():
            conn.close()
            return  # Series already exists

        scanner = LibraryScanner()
        series_data = scanner.scan_series(normalized_path)
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
                
                if metadata:
                    if 'authors' in metadata and metadata['authors']:
                        for author_name in metadata['authors']:
                            cursor.execute("SELECT id FROM authors WHERE name = ?", (author_name,))
                            author_row = cursor.fetchone()
                            if not author_row:
                                cursor.execute("INSERT INTO authors (name) VALUES (?)", (author_name,))
                                author_id = cursor.lastrowid
                            else:
                                author_id = author_row['id']
                            cursor.execute("INSERT INTO series_authors (series_id, author_id) VALUES (?, ?)", (series_id, author_id))

                    if 'genres' in metadata and metadata['genres']:
                        for genre_name in metadata['genres']:
                            cursor.execute("SELECT id FROM genres WHERE name = ?", (genre_name,))
                            genre_row = cursor.fetchone()
                            if not genre_row:
                                cursor.execute("INSERT INTO genres (name) VALUES (?)", (genre_name,))
                                genre_id = cursor.lastrowid
                            else:
                                genre_id = genre_row['id']
                            cursor.execute("INSERT INTO series_genres (series_id, genre_id) VALUES (?, ?)", (series_id, genre_id))

                conn.commit()
            except Exception as e:
                print(f"Error adding series: {e}")
                conn.rollback()
            finally:
                conn.close()

    def add_series_batch(self, paths, metadata=None):
        for path in paths:
            self.add_series(path, metadata)

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
            cursor.execute("UPDATE series SET last_read_chapter = ?, last_opened_date = ? WHERE id = ?", (chapter_path, datetime.now(), series_id))
            conn.commit()
        except Exception as e:
            print(f"Error updating last read chapter: {e}")
            conn.rollback()
        finally:
            conn.close()

    def update_series_info(self, series_id, new_info):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Update description
            if 'description' in new_info:
                cursor.execute("UPDATE series SET description = ? WHERE id = ?", (new_info['description'], series_id))

            # Update authors
            if 'authors' in new_info:
                # First, delete existing author links for the series
                cursor.execute("DELETE FROM series_authors WHERE series_id = ?", (series_id,))
                # Then, add the new authors
                for author_name in new_info['authors']:
                    # Get author id or create new author
                    cursor.execute("SELECT id FROM authors WHERE name = ?", (author_name,))
                    author_id = cursor.fetchone()
                    if not author_id:
                        cursor.execute("INSERT INTO authors (name) VALUES (?) RETURNING id", (author_name,))
                        author_id = cursor.fetchone()
                    cursor.execute("INSERT INTO series_authors (series_id, author_id) VALUES (?, ?)", (series_id, author_id['id']))

            # Update genres
            if 'genres' in new_info:
                # First, delete existing genre links for the series
                cursor.execute("DELETE FROM series_genres WHERE series_id = ?", (series_id,))
                # Then, add the new genres
                for genre_name in new_info['genres']:
                    # Get genre id or create new genre
                    cursor.execute("SELECT id FROM genres WHERE name = ?", (genre_name,))
                    genre_id = cursor.fetchone()
                    if not genre_id:
                        cursor.execute("INSERT INTO genres (name) VALUES (?) RETURNING id", (genre_name,))
                        genre_id = cursor.fetchone()
                    cursor.execute("INSERT INTO series_genres (series_id, genre_id) VALUES (?, ?)", (series_id, genre_id['id']))

            conn.commit()
        except Exception as e:
            print(f"Error updating series info: {e}")
            conn.rollback()
        finally:
            conn.close()