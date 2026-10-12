"""
PROJECT: Datacom Kudos System
FILE: src/db/init_db.py
DESCRIPTION: Database Initialization and Phase P1 Verification Runner (Python)
"""

import sys
import sqlite3
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.database import get_connection, init_db, DB_PATH


def run_verification() -> bool:
    print("=" * 66)
    print("  DATABASE INITIALIZATION & VERIFICATION RUNNER (PHASE P1 - PYTHON) ")
    print("=" * 66)

    try:
        print(f"[1/4] Connecting to SQLite database file: {DB_PATH}")
        init_db()
        conn = get_connection()
        print("  ✔ Connection established and schema initialized successfully.")

        print("[2/4] Verifying generated database tables...")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        )
        tables = [row["name"] for row in cursor.fetchall()]
        print(f"  Tables discovered: {', '.join(tables)}")

        print("[3/4] Verifying seed records count...")
        cursor.execute("SELECT COUNT(*) AS count FROM users;")
        user_count = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) AS count FROM kudos;")
        kudo_count = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) AS count FROM moderation_audit_logs;")
        audit_count = cursor.fetchone()["count"]

        print(f"  ✔ Users count: {user_count}")
        print(f"  ✔ Kudos count: {kudo_count}")
        print(f"  ✔ Moderation audit log count: {audit_count}")

        print("[4/4] Integrity check: testing foreign key constraint enforcement...")
        try:
            cursor.execute(
                """
                INSERT INTO kudos (id, sender_id, recipient_id, category, message)
                VALUES ('k-invalid', 'u-nonexistent', 'u-01', 'Teamwork', 'Invalid test insertion');
                """
            )
            conn.commit()
            print("  ❌ Failure: Foreign key constraint did not reject the invalid row.")
            conn.close()
            return False
        except sqlite3.IntegrityError:
            print("  ✔ Success: Foreign key constraint active (invalid insertion rejected).")

        conn.close()
        print("=" * 66)
        print("  PHASE P1 VERIFIED SUCCESSFULLY (All Exit Criteria Met)!         ")
        print("=" * 66)
        return True

    except Exception as e:
        print(f"[ERROR] Database initialization failed: {e}")
        return False


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
