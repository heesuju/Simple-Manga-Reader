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
            series['themes'] = self.get_themes(series['id'])
            series['formats'] = self.get_formats(series['id'])
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
            series['themes'] = self.get_themes(series['id'])
            series['formats'] = self.get_formats(series['id'])
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
            series['themes'] = self.get_themes(series['id'])
            series['formats'] = self.get_formats(series['id'])
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

    def get_themes(self, series_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.name FROM themes t
            JOIN series_themes st ON t.id = st.theme_id
            WHERE st.series_id = ?
        """, (series_id,))
        themes = [row['name'] for row in cursor.fetchall()]
        conn.close()
        return themes

    def get_formats(self, series_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT f.name FROM formats f
            JOIN series_formats sf ON f.id = sf.format_id
            WHERE sf.series_id = ?
        """, (series_id,))
        formats = [row['name'] for row in cursor.fetchall()]
        conn.close()
        return formats

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

    def get_all_themes(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM themes ORDER BY name")
        themes = [row['name'] for row in cursor.fetchall()]
        conn.close()
        return themes

    def get_all_formats(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM formats ORDER BY name")
        formats = [row['name'] for row in cursor.fetchall()]
        conn.close()
        return formats

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

        if filters.get('themes'):
            if not joins:
                joins += " JOIN series_themes st ON s.id = st.series_id JOIN themes t ON st.theme_id = t.id"
                query += joins
                query += " WHERE t.name IN ({})".format(', '.join('?'*len(filters['themes'])))
            else:
                query += " AND s.id IN (SELECT s.id FROM series s JOIN series_themes st ON s.id = st.series_id JOIN themes t ON st.theme_id = t.id WHERE t.name IN ({})) ".format(', '.join('?'*len(filters['themes'])))
            params.extend(filters['themes'])

        if filters.get('formats'):
            if not joins:
                joins += " JOIN series_formats sf ON s.id = sf.series_id JOIN formats f ON sf.format_id = f.id"
                query += joins
                query += " WHERE f.name IN ({})".format(', '.join('?'*len(filters['formats'])))
            else:
                query += " AND s.id IN (SELECT s.id FROM series s JOIN series_formats sf ON s.id = sf.series_id JOIN formats f ON sf.format_id = f.id WHERE f.name IN ({})) ".format(', '.join('?'*len(filters['formats'])))
            params.extend(filters['formats'])

        if search_term:
            if not filters.get('authors') and not filters.get('genres') and not filters.get('themes') and not filters.get('formats'):
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
            series['themes'] = self.get_themes(series['id'])
            series['formats'] = self.get_formats(series['id'])
        
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
            series['themes'] = self.get_themes(series['id'])
            series['formats'] = self.get_formats(series['id'])
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

                    if 'themes' in metadata and metadata['themes']:
                        for theme_name in metadata['themes']:
                            cursor.execute("SELECT id FROM themes WHERE name = ?", (theme_name,))
                            theme_row = cursor.fetchone()
                            if not theme_row:
                                cursor.execute("INSERT INTO themes (name) VALUES (?) ", (theme_name,))
                                theme_id = cursor.lastrowid
                            else:
                                theme_id = theme_row['id']
                            cursor.execute("INSERT INTO series_themes (series_id, theme_id) VALUES (?, ?)", (series_id, theme_id))

                    if 'formats' in metadata and metadata['formats']:
                        for format_name in metadata['formats']:
                            cursor.execute("SELECT id FROM formats WHERE name = ?", (format_name,))
                            format_row = cursor.fetchone()
                            if not format_row:
                                cursor.execute("INSERT INTO formats (name) VALUES (?) ", (format_name,))
                                format_id = cursor.lastrowid
                            else:
                                format_id = format_row['id']
                            cursor.execute("INSERT INTO series_formats (series_id, format_id) VALUES (?, ?)", (series_id, format_id))

                conn.commit()
            except Exception as e:
                print(f"Error adding series: {e}")
                conn.rollback()
            finally:
                conn.close()

    def add_series_batch(self, paths, metadata=None):
        for path in paths:
            self.add_series(path, metadata)

    def update_series_batch(self, series_list, metadata):
        for series in series_list:
            self.update_series_info(series['id'], metadata)

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

    def set_chapter_cover_path(self, chapter_id, cover_path):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE chapters SET cover_path = ? WHERE id = ?", (cover_path, chapter_id))
            conn.commit()
        except Exception as e:
            print(f"Error updating chapter cover path: {e}")
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

            # Update cover_image
            if 'cover_image' in new_info:
                cursor.execute("UPDATE series SET cover_image = ? WHERE id = ?", (new_info['cover_image'], series_id))

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

            # Update themes
            if 'themes' in new_info:
                cursor.execute("DELETE FROM series_themes WHERE series_id = ?", (series_id,))
                for theme_name in new_info['themes']:
                    cursor.execute("SELECT id FROM themes WHERE name = ?", (theme_name,))
                    theme_id = cursor.fetchone()
                    if not theme_id:
                        cursor.execute("INSERT INTO themes (name) VALUES (?) RETURNING id", (theme_name,))
                        theme_id = cursor.fetchone()
                    cursor.execute("INSERT INTO series_themes (series_id, theme_id) VALUES (?, ?)", (series_id, theme_id['id']))

            # Update formats
            if 'formats' in new_info:
                cursor.execute("DELETE FROM series_formats WHERE series_id = ?", (series_id,))
                for format_name in new_info['formats']:
                    cursor.execute("SELECT id FROM formats WHERE name = ?", (format_name,))
                    format_id = cursor.fetchone()
                    if not format_id:
                        cursor.execute("INSERT INTO formats (name) VALUES (?) RETURNING id", (format_name,))
                        format_id = cursor.fetchone()
                    cursor.execute("INSERT INTO series_formats (series_id, format_id) VALUES (?, ?)", (series_id, format_id['id']))

            conn.commit()
        except Exception as e:
            print(f"Error updating series info: {e}")
            conn.rollback()
        finally:
            conn.close()

    def rescan_series_path(self, series_id, new_path):
        normalized_path = str(Path(new_path))
        
        scanner = LibraryScanner()
        series_data = scanner.scan_series(normalized_path)

        if not series_data:
            print(f"New path {new_path} does not seem to be a valid series folder.")
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # 1. Update series path and cover
            cursor.execute(
                "UPDATE series SET path = ?, cover_image = ? WHERE id = ?",
                (normalized_path, series_data['cover_image'], series_id)
            )

            # 2. Delete old chapters
            cursor.execute("DELETE FROM chapters WHERE series_id = ?", (series_id,))

            # 3. Insert new chapters
            for chapter in series_data.get('chapters', []):
                cursor.execute(
                    "INSERT INTO chapters (series_id, name, path) VALUES (?, ?, ?)",
                    (series_id, chapter['name'], chapter['path'])
                )
            
            conn.commit()
        except Exception as e:
            print(f"Error rescanning series path: {e}")
            conn.rollback()
        finally:
            conn.close()