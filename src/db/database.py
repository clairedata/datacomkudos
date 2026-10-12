"""
PROJECT: Datacom Kudos System
FILE: src/db/database.py
DESCRIPTION: SQLite Database Connection Manager and Schema Initializer using Python standard library sqlite3
"""

import os
import sqlite3
from pathlib import Path
from typing import Optional
from src.db.seeds import INITIAL_USERS, INITIAL_KUDOS

# Path to database file
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "kudos.db"
DB_PATH = Path(os.getenv("DB_PATH", str(DEFAULT_DB_PATH)))


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Creates and returns a connection to the SQLite database.
    Enforces foreign key constraint checks and configures Row factory for dict-like access.
    """
    target_path = db_path or Path(os.getenv("DB_PATH", str(DB_PATH)))
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row

    # Enforce foreign key constraints in SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    
    # Enable WAL mode for performance and concurrent read access
    conn.execute("PRAGMA journal_mode = WAL;")

    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """
    Applies the DDL schema and seeds demo data if the database is uninitialized.
    """
    target_path = db_path or Path(os.getenv("DB_PATH", str(DB_PATH)))
    target_path.parent.mkdir(parents=True, exist_ok=True)

    schema_file = Path(__file__).resolve().parent / "schema.sql"
    with open(schema_file, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    with get_connection(target_path) as conn:
        # Execute multi-statement SQL schema script
        conn.executescript(schema_sql)

        # Check if users table is populated
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM users;")
        user_count = cursor.fetchone()["count"]

        if user_count == 0:
            print("[DATABASE] Users table is empty. Seeding initial Datacom records...")

            # Insert users
            user_insert_sql = """
                INSERT INTO users (id, name, email, role, avatar, department, is_active)
                VALUES (:id, :name, :email, :role, :avatar, :department, :is_active);
            """
            cursor.executemany(user_insert_sql, INITIAL_USERS)
            print(f"[DATABASE] {len(INITIAL_USERS)} employees seeded successfully.")

            # Insert sample kudos with timestamps 1 hour in the past so demo users are not inside a cooldown window
            kudo_insert_sql = """
                INSERT INTO kudos (
                    id, sender_id, recipient_id, category, message, is_visible,
                    moderated_by, moderated_at, reason_for_moderation, ai_flagged, ai_flag_reason,
                    created_at, updated_at
                ) VALUES (
                    :id, :sender_id, :recipient_id, :category, :message, :is_visible,
                    :moderated_by, :moderated_at, :reason_for_moderation, :ai_flagged, :ai_flag_reason,
                    datetime('now', '-1 hour'), datetime('now', '-1 hour')
                );
            """
            cursor.executemany(kudo_insert_sql, INITIAL_KUDOS)
            print(f"[DATABASE] {len(INITIAL_KUDOS)} sample kudos seeded successfully.")

            conn.commit()


if __name__ == "__main__":
    init_db()
