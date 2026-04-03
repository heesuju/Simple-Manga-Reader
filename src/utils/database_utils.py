
import sqlite3
from contextlib import contextmanager
from pathlib import Path

def get_db_connection():
    db_path = Path("library.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def db_cursor():
    """Context manager that opens a connection and yields (conn, cursor), closing on exit."""
    conn = get_db_connection()
    try:
        yield conn, conn.cursor()
    finally:
        conn.close()

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS series (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        path TEXT NOT NULL UNIQUE,
        cover_image TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS authors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS genres (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS series_authors (
        series_id INTEGER,
        author_id INTEGER,
        PRIMARY KEY (series_id, author_id),
        FOREIGN KEY (series_id) REFERENCES series (id) ON DELETE CASCADE,
        FOREIGN KEY (author_id) REFERENCES authors (id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS series_genres (
        series_id INTEGER,
        genre_id INTEGER,
        PRIMARY KEY (series_id, genre_id),
        FOREIGN KEY (series_id) REFERENCES series (id) ON DELETE CASCADE,
        FOREIGN KEY (genre_id) REFERENCES genres (id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS themes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS formats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS series_themes (
        series_id INTEGER,
        theme_id INTEGER,
        PRIMARY KEY (series_id, theme_id),
        FOREIGN KEY (series_id) REFERENCES series (id) ON DELETE CASCADE,
        FOREIGN KEY (theme_id) REFERENCES themes (id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS series_formats (
        series_id INTEGER,
        format_id INTEGER,
        PRIMARY KEY (series_id, format_id),
        FOREIGN KEY (series_id) REFERENCES series (id) ON DELETE CASCADE,
        FOREIGN KEY (format_id) REFERENCES formats (id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        series_id INTEGER NOT NULL,
        path TEXT NOT NULL UNIQUE,
        name TEXT,
        FOREIGN KEY (series_id) REFERENCES series (id)
    )
    """)

    # Add columns that don't exist yet (schema migrations)
    _MIGRATIONS = {
        'series': [
            ('description',         'TEXT'),
            ('last_read_chapter',   'TEXT'),
            ('last_opened_date',    'DATETIME'),
            ('last_read_page',      'INTEGER DEFAULT 0'),
            ('last_read_image_path','TEXT'),
        ],
        'chapters': [
            ('cover_path', 'TEXT'),
        ],
    }
    for table, cols in _MIGRATIONS.items():
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row['name'] for row in cursor.fetchall()}
        for col, col_type in cols:
            if col not in existing:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")

    conn.commit()
    conn.close()
