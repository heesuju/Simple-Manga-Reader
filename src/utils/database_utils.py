
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
        cover_image TEXT,
        last_read_chapter TEXT
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

    conn.commit()
    conn.close()
