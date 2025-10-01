
import sqlite3
from pathlib import Path

def get_db_connection():
    db_path = Path("library.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

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
    CREATE TABLE IF NOT EXISTS chapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        series_id INTEGER NOT NULL,
        path TEXT NOT NULL UNIQUE,
        name TEXT,
        FOREIGN KEY (series_id) REFERENCES series (id)
    )
    """)

    # Add columns to series table if they don't exist
    cursor.execute("PRAGMA table_info(series)")
    columns = [row['name'] for row in cursor.fetchall()]
    if 'description' not in columns:
        cursor.execute("ALTER TABLE series ADD COLUMN description TEXT")
    if 'last_read_chapter' not in columns:
        cursor.execute("ALTER TABLE series ADD COLUMN last_read_chapter TEXT")

    conn.commit()
    conn.close()
