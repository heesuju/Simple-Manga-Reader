from pathlib import Path
from datetime import datetime
from src.utils.database_utils import create_tables, db_cursor
from src.utils.img_utils import get_chapter_number
from src.utils.str_utils import natural_sort_key

class LibraryManager:
    _TAG_CONFIG = {
        'authors': ('authors', 'series_authors', 'author_id'),
        'genres':  ('genres',  'series_genres',  'genre_id'),
        'themes':  ('themes',  'series_themes',  'theme_id'),
        'formats': ('formats', 'series_formats', 'format_id'),
    }

    def __init__(self):
        self.init_db()

    def init_db(self):
        create_tables()

    def get_series(self):
        with db_cursor() as (_, cursor):
            cursor.execute("SELECT * FROM series")
            series_list = [dict(row) for row in cursor.fetchall()]
        self._populate_metadata(series_list)
        return series_list

    def search_series(self, search_term):
        with db_cursor() as (_, cursor):
            cursor.execute("SELECT * FROM series WHERE name LIKE ?", (f'%{search_term}%',))
            series_list = [dict(row) for row in cursor.fetchall()]
        self._populate_metadata(series_list)
        return series_list

    def get_recently_opened_series(self, limit=20):
        with db_cursor() as (_, cursor):
            cursor.execute("SELECT * FROM series WHERE last_opened_date IS NOT NULL ORDER BY last_opened_date DESC LIMIT ?", (limit,))
            series_list = [dict(row) for row in cursor.fetchall()]
        self._populate_metadata(series_list)
        return series_list

    def _get_tag_list(self, series_id, tag):
        table, junction, fk = self._TAG_CONFIG[tag]
        with db_cursor() as (_, cursor):
            cursor.execute(f"""
                SELECT t.name FROM {table} t
                JOIN {junction} j ON t.id = j.{fk}
                WHERE j.series_id = ?
            """, (series_id,))
            return [row['name'] for row in cursor.fetchall()]

    def _get_all_tags(self, tag):
        table = self._TAG_CONFIG[tag][0]
        with db_cursor() as (_, cursor):
            cursor.execute(f"SELECT name FROM {table} ORDER BY name")
            return [row['name'] for row in cursor.fetchall()]

    def get_authors(self, series_id):  return self._get_tag_list(series_id, 'authors')
    def get_genres(self, series_id):   return self._get_tag_list(series_id, 'genres')
    def get_themes(self, series_id):   return self._get_tag_list(series_id, 'themes')
    def get_formats(self, series_id):  return self._get_tag_list(series_id, 'formats')

    def get_all_authors(self):  return self._get_all_tags('authors')
    def get_all_genres(self):   return self._get_all_tags('genres')
    def get_all_themes(self):   return self._get_all_tags('themes')
    def get_all_formats(self):  return self._get_all_tags('formats')

    def search_series_with_filters(self, search_term, filters):
        query = "SELECT DISTINCT s.* FROM series s"
        params = []
        has_filter = False

        for key, (table, junction, fk) in self._TAG_CONFIG.items():
            values = filters.get(key)
            if not values:
                continue
            ph = ', '.join('?' * len(values))
            clause = (
                f" WHERE s.id IN (SELECT series_id FROM {junction} j"
                f" JOIN {table} t ON t.id = j.{fk} WHERE t.name IN ({ph}))"
                if not has_filter else
                f" AND s.id IN (SELECT series_id FROM {junction} j"
                f" JOIN {table} t ON t.id = j.{fk} WHERE t.name IN ({ph}))"
            )
            query += clause
            params.extend(values)
            has_filter = True

        if search_term:
            query += " WHERE s.name LIKE ?" if not has_filter else " AND s.name LIKE ?"
            params.append(f'%{search_term}%')

        with db_cursor() as (_, cursor):
            cursor.execute(query, params)
            series_list = [dict(row) for row in cursor.fetchall()]

        self._populate_metadata(series_list)
        return series_list

    def get_series_by_path(self, path):
        normalized_path = str(Path(path))
        with db_cursor() as (_, cursor):
            cursor.execute("SELECT * FROM series WHERE path = ?", (normalized_path,))
            series_row = cursor.fetchone()
        if series_row:
            series = dict(series_row)
            self._populate_metadata([series])
            return series
        return None

    def get_chapters(self, series):
        with db_cursor() as (_, cursor):
            cursor.execute("SELECT * FROM chapters WHERE series_id = ?", (series['id'],))
            chapters = [dict(row) for row in cursor.fetchall()]
        chapters.sort(key=lambda x: get_chapter_number(x['path']))
        return chapters


    def add_series_from_data(self, series_data, metadata=None):
        with db_cursor() as (conn, cursor):
            cursor.execute("SELECT id FROM series WHERE path = ?", (series_data['path'],))
            if cursor.fetchone():
                return

            try:
                # Use name from metadata if provided, else use scanning result
                final_name = series_data['name']
                if metadata and 'name' in metadata and metadata['name']:
                    final_name = metadata['name']

                cursor.execute(
                    "INSERT INTO series (name, path, cover_image) VALUES (?, ?, ?)",
                    (final_name, series_data['path'], series_data['cover_image'])
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
                            cursor.execute("INSERT INTO series_themes (series_id, theme_id) VALUES (?, ?)", (series_id, theme_id['id']))

                # Formats can come from metadata OR from our auto-detector via series_data
                formats_to_add = []
                if metadata and 'formats' in metadata and metadata['formats']:
                    formats_to_add = metadata['formats']
                elif 'formats' in series_data and series_data['formats']:
                    formats_to_add = series_data['formats']

                for format_name in formats_to_add:
                    cursor.execute("SELECT id FROM formats WHERE name = ?", (format_name,))
                    format_row = cursor.fetchone()
                    if not format_row:
                        cursor.execute("INSERT INTO formats (name) VALUES (?)", (format_name,))
                        format_id = cursor.lastrowid
                    else:
                        format_id = format_row['id']
                    
                    if isinstance(format_id, dict):
                         format_id = format_id['id']
                    cursor.execute("INSERT INTO series_formats (series_id, format_id) VALUES (?, ?)", (series_id, format_id))

                conn.commit()
            except Exception as e:
                print(f"Error adding series: {e}")
                conn.rollback()


    def update_series_batch(self, series_list, metadata):
        for series in series_list:
            self.update_series_info(series['id'], metadata)

    def hide_chapter(self, series_path: str, chapter: dict):
        """Remove chapter from DB and add to blacklist in info.json so it is not rescanned."""
        from src.core.alt_manager import AltManager

        chapter_path = chapter.get('path', '')
        chapter_name = chapter.get('name')
        if not chapter_name:
            if '|' in chapter_path:
                _, internal = chapter_path.split('|', 1)
                chapter_name = Path(internal.rstrip('/')).name or Path(chapter_path.split('|')[0]).stem
            else:
                chapter_name = Path(chapter_path).name

        with db_cursor() as (conn, cursor):
            try:
                cursor.execute("DELETE FROM chapters WHERE path = ?", (chapter_path,))
                conn.commit()
            except Exception as e:
                print(f"Error hiding chapter: {e}")
                conn.rollback()

        AltManager.blacklist_chapter(series_path, chapter_name)

    def remove_series(self, series_to_remove):
        with db_cursor() as (conn, cursor):
            try:
                sid = series_to_remove['id']
                cursor.execute("DELETE FROM series_authors WHERE series_id = ?", (sid,))
                cursor.execute("DELETE FROM series_genres WHERE series_id = ?", (sid,))
                cursor.execute("DELETE FROM series_themes WHERE series_id = ?", (sid,))
                cursor.execute("DELETE FROM series_formats WHERE series_id = ?", (sid,))
                cursor.execute("DELETE FROM chapters WHERE series_id = ?", (sid,))
                cursor.execute("DELETE FROM series WHERE id = ?", (sid,))
                conn.commit()
            except Exception as e:
                print(f"Error removing series: {e}")
                conn.rollback()

    def update_last_read_chapter(self, series_id, chapter_path, page_index=0, image_path=None):
        with db_cursor() as (conn, cursor):
            try:
                if image_path is not None:
                    cursor.execute(
                        "UPDATE series SET last_read_chapter = ?, last_opened_date = ?, last_read_page = ?, last_read_image_path = ? WHERE id = ?",
                        (chapter_path, datetime.now(), page_index, image_path, series_id)
                    )
                else:
                    cursor.execute(
                        "UPDATE series SET last_read_chapter = ?, last_opened_date = ?, last_read_page = ? WHERE id = ?",
                        (chapter_path, datetime.now(), page_index, series_id)
                    )
                conn.commit()
            except Exception as e:
                print(f"Error updating last read chapter: {e}")
                conn.rollback()

    def set_chapter_cover_path(self, chapter_id, cover_path):
        with db_cursor() as (conn, cursor):
            try:
                cursor.execute("UPDATE chapters SET cover_path = ? WHERE id = ?", (cover_path, chapter_id))
                conn.commit()
            except Exception as e:
                print(f"Error updating chapter cover path: {e}")
                conn.rollback()

    def update_series_info(self, series_id, new_info):
        with db_cursor() as (conn, cursor):
            try:
                if 'name' in new_info:
                    cursor.execute("UPDATE series SET name = ? WHERE id = ?", (new_info['name'], series_id))
                if 'description' in new_info:
                    cursor.execute("UPDATE series SET description = ? WHERE id = ?", (new_info['description'], series_id))
                if 'cover_image' in new_info:
                    cursor.execute("UPDATE series SET cover_image = ? WHERE id = ?", (new_info['cover_image'], series_id))

                if 'authors' in new_info:
                    cursor.execute("DELETE FROM series_authors WHERE series_id = ?", (series_id,))
                    for author_name in new_info['authors']:
                        cursor.execute("SELECT id FROM authors WHERE name = ?", (author_name,))
                        author_id = cursor.fetchone()
                        if not author_id:
                            cursor.execute("INSERT INTO authors (name) VALUES (?) RETURNING id", (author_name,))
                            author_id = cursor.fetchone()
                        cursor.execute("INSERT INTO series_authors (series_id, author_id) VALUES (?, ?)", (series_id, author_id['id']))

                if 'genres' in new_info:
                    cursor.execute("DELETE FROM series_genres WHERE series_id = ?", (series_id,))
                    for genre_name in new_info['genres']:
                        cursor.execute("SELECT id FROM genres WHERE name = ?", (genre_name,))
                        genre_id = cursor.fetchone()
                        if not genre_id:
                            cursor.execute("INSERT INTO genres (name) VALUES (?) RETURNING id", (genre_name,))
                            genre_id = cursor.fetchone()
                        cursor.execute("INSERT INTO series_genres (series_id, genre_id) VALUES (?, ?)", (series_id, genre_id['id']))

                if 'themes' in new_info:
                    cursor.execute("DELETE FROM series_themes WHERE series_id = ?", (series_id,))
                    for theme_name in new_info['themes']:
                        cursor.execute("SELECT id FROM themes WHERE name = ?", (theme_name,))
                        theme_id = cursor.fetchone()
                        if not theme_id:
                            cursor.execute("INSERT INTO themes (name) VALUES (?) RETURNING id", (theme_name,))
                            theme_id = cursor.fetchone()
                        cursor.execute("INSERT INTO series_themes (series_id, theme_id) VALUES (?, ?)", (series_id, theme_id['id']))

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

    def rescan_series_from_data(self, series_id, new_path, series_data):
        normalized_path = str(Path(new_path))
        with db_cursor() as (conn, cursor):
            try:
                cursor.execute(
                    "UPDATE series SET path = ?, cover_image = ? WHERE id = ?",
                    (normalized_path, series_data['cover_image'], series_id)
                )
                cursor.execute("DELETE FROM chapters WHERE series_id = ?", (series_id,))
                for chapter in series_data.get('chapters', []):
                    cursor.execute(
                        "INSERT INTO chapters (series_id, name, path) VALUES (?, ?, ?)",
                        (series_id, chapter['name'], chapter['path'])
                    )
                conn.commit()
            except Exception as e:
                print(f"Error rescanning series path from data: {e}")
                conn.rollback()


    def get_field_values_with_counts(self, field):
        """Returns [{'name': str, 'count': int}] for authors/genres/themes/formats."""
        field_table = {'author': 'authors', 'genre': 'genres', 'theme': 'themes', 'format': 'formats'}
        junction = {'author': 'series_authors', 'genre': 'series_genres', 'theme': 'series_themes', 'format': 'series_formats'}
        id_col = {'author': 'author_id', 'genre': 'genre_id', 'theme': 'theme_id', 'format': 'format_id'}
        if field not in field_table:
            return []
        with db_cursor() as (_, cursor):
            cursor.execute(f"""
                SELECT t.name, COUNT(j.series_id) as count
                FROM {field_table[field]} t
                JOIN {junction[field]} j ON t.id = j.{id_col[field]}
                JOIN series s ON j.series_id = s.id
                GROUP BY t.id, t.name
                HAVING COUNT(j.series_id) > 0
                ORDER BY t.name
            """)
            return [{'name': row['name'], 'count': row['count']} for row in cursor.fetchall()]

    def get_series_by_field_value(self, field, value):
        """Returns series filtered by a specific field value."""
        return self.search_series_with_filters('', {f'{field}s': [value]})

    def get_series_without_field(self, field):
        """Returns series that have no values for the given field (untagged)."""
        junction = {'author': 'series_authors', 'genre': 'series_genres', 'theme': 'series_themes', 'format': 'series_formats'}
        if field not in junction:
            return []
        with db_cursor() as (_, cursor):
            cursor.execute(f"""
                SELECT s.* FROM series s
                WHERE s.id NOT IN (SELECT DISTINCT series_id FROM {junction[field]})
            """)
            series_list = [dict(row) for row in cursor.fetchall()]
        self._populate_metadata(series_list)
        return series_list

    def _populate_metadata(self, series_list):
        if not series_list:
            return

        series_map = {series['id']: series for series in series_list}
        series_ids = list(series_map.keys())
        
        # Initialize default empty lists
        for series in series_list:
            series['chapters'] = []
            series['authors'] = []
            series['genres'] = []
            series['themes'] = []
            series['formats'] = []

        if not series_ids:
            return

        placeholders = ', '.join('?' * len(series_ids))

        with db_cursor() as (_, cursor):
            try:
                cursor.execute(f"SELECT * FROM chapters WHERE series_id IN ({placeholders})", series_ids)
                all_chapters = [dict(row) for row in cursor.fetchall()]

                for chapter in all_chapters:
                    sid = chapter['series_id']
                    if sid in series_map:
                        series_map[sid]['chapters'].append(chapter)

                def make_sort_key(x):
                    path = x.get('path')
                    name = x.get('name') or ''
                    if not isinstance(path, str) or not path:
                        return ('.', natural_sort_key(name))
                    try:
                        # Defensive split for virtual paths
                        if '|' in path:
                            parts = path.split('|')
                            if len(parts) > 1:
                                parent = str(Path(parts[1]).parent)
                            else:
                                parent = '.'
                        else:
                            parent = str(Path(path).parent)
                    except (IndexError, TypeError, OSError):
                        parent = '.'
                    return (parent, natural_sort_key(name))

                for series in series_list:
                    try:
                        series['chapters'].sort(key=make_sort_key)
                    except Exception as e:
                        print(f"Error sorting chapters for series {series.get('id')}: {e}")

                def fetch_junction(table, join_table, join_id_col, target_field):
                    cursor.execute(f"""
                        SELECT j.series_id, t.name
                        FROM {table} t
                        JOIN {join_table} j ON t.id = j.{join_id_col}
                        WHERE j.series_id IN ({placeholders})
                    """, series_ids)
                    for row in cursor.fetchall():
                        if row['series_id'] in series_map:
                            series_map[row['series_id']][target_field].append(row['name'])

                for tag, (table, junction, fk) in self._TAG_CONFIG.items():
                    fetch_junction(table, junction, fk, tag)

            except Exception as e:
                import traceback
                print(f"Error populating metadata: {e}")
                traceback.print_exc()