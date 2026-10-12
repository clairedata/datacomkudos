"""
PROJECT: Datacom Kudos System
FILE: src/services/kudos_service.py
DESCRIPTION: Core Business Logic and Persistence Layer for Kudos Operations
             Implements all business rules (BR-01 to BR-11), DTO transformations,
             anti-spam rate limiting, and atomic moderation audit transactions.
"""

import html
import uuid
import datetime
from typing import Dict, Any, List, Optional, Tuple
import sqlite3

from src.db.database import get_connection
from src.services.ai_moderation import evaluate_content

# Allowed categories per specification rule BR-03
VALID_CATEGORIES = {
    "Teamwork",
    "Innovation",
    "Customer Delight",
    "Leadership",
    "Above & Beyond"
}

# Anti-spam timing configuration per rule BR-05
COOLDOWN_SECONDS = 10
DUPLICATE_WINDOW_MINUTES = 5


def get_utc_now() -> datetime.datetime:
    """Returns current timezone-aware UTC datetime."""
    return datetime.datetime.now(datetime.timezone.utc)


def get_utc_now_iso() -> str:
    """Returns current UTC timestamp formatted as ISO-8601 string."""
    return get_utc_now().isoformat()


class KudosException(Exception):
    """Base exception for kudos domain operations."""
    def __init__(self, message: str, status_code: int = 400, details: Optional[List[Dict[str, str]]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or []


class ValidationError(KudosException):
    """Raised when an input business rule is violated (HTTP 422)."""
    def __init__(self, message: str, details: Optional[List[Dict[str, str]]] = None):
        super().__init__(message, status_code=422, details=details)


class RateLimitError(KudosException):
    """Raised when anti-spam or duplicate submission rule is violated (HTTP 429)."""
    def __init__(self, message: str, details: Optional[List[Dict[str, str]]] = None):
        super().__init__(message, status_code=429, details=details)


class NotFoundError(KudosException):
    """Raised when a requested resource does not exist (HTTP 404)."""
    def __init__(self, message: str):
        super().__init__(message, status_code=404)


class ForbiddenError(KudosException):
    """Raised when an action violates authorization / RBAC rules (HTTP 403)."""
    def __init__(self, message: str):
        super().__init__(message, status_code=403)


# ============================================================================
# READ OPERATIONS (USERS & KUDOS FEED)
# ============================================================================

def get_active_users(conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    """
    Retrieves all active colleagues for the recipient dropdown selector.
    """
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, email, department, role, avatar
            FROM users
            WHERE is_active = 1
            ORDER BY name ASC;
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        if close_after:
            conn.close()


def get_user_by_id(user_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    """
    Fetches a user by their unique identifier.
    """
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        if close_after:
            conn.close()


def get_user_statistics(user_id: str, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Retrieves personal kudos statistics for a given employee (User Story US-05).
    - kudos_received: total visible kudos received by this user
    - kudos_sent: total kudos given/sent by this user
    """
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, department, role FROM users WHERE id = ?;", (user_id,))
        user_row = cursor.fetchone()
        if not user_row:
            raise NotFoundError(f"User with ID '{user_id}' not found.")

        # Total visible kudos received
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM kudos
            WHERE recipient_id = ? AND is_visible = 1;
        """, (user_id,))
        kudos_received = cursor.fetchone()["total"]

        # Total kudos sent
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM kudos
            WHERE sender_id = ?;
        """, (user_id,))
        kudos_sent = cursor.fetchone()["total"]

        return {
            "user_id": user_id,
            "name": user_row["name"],
            "department": user_row["department"],
            "role": user_row["role"],
            "kudos_received": kudos_received,
            "kudos_sent": kudos_sent
        }
    finally:
        if close_after:
            conn.close()


def get_kudos_feed(
    current_user: Dict[str, Any],
    limit: int = 20,
    offset: int = 0,
    filter_type: str = "all",
    scope: str = "all",
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Retrieves the paginated feed of kudos.
    Enforces strict DTO segregation (BR-06):
    - Standard users receive PublicKudoDTO (only visible kudos, no moderation metadata).
    - Administrators receive AdminKudoDTO (full visibility into flags and audit info).
    - Supports scope filter: 'all', 'received' (kudos given to current user), 'sent' (kudos given by current user).
    """
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    try:
        cursor = conn.cursor()
        is_admin = current_user.get("role") == "admin"

        # Base WHERE clause
        where_clauses = []
        params = []

        if not is_admin:
            # Rule BR-06: Standard users only see visible kudos
            where_clauses.append("k.is_visible = 1")
        else:
            # Administrator filter options
            if filter_type == "flagged":
                where_clauses.append("k.ai_flagged = 1")
            elif filter_type == "hidden":
                where_clauses.append("k.is_visible = 0")

        # Personal Scope filter (User Story 5)
        if scope == "received":
            where_clauses.append("k.recipient_id = ?")
            params.append(current_user["id"])
        elif scope == "sent":
            where_clauses.append("k.sender_id = ?")
            params.append(current_user["id"])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Count total records matching criteria
        count_sql = f"SELECT COUNT(*) AS total FROM kudos k {where_sql};"
        cursor.execute(count_sql, params)
        total_count = cursor.fetchone()["total"]

        # Fetch enriched records joining sender and recipient
        fetch_sql = f"""
            SELECT 
                k.id, k.category, k.message, k.is_visible,
                k.moderated_by, k.moderated_at, k.reason_for_moderation,
                k.ai_flagged, k.ai_flag_reason, k.created_at,
                s.id AS sender_id, s.name AS sender_name, s.avatar AS sender_avatar,
                r.id AS recipient_id, r.name AS recipient_name, r.avatar AS recipient_avatar
            FROM kudos k
            JOIN users s ON k.sender_id = s.id
            JOIN users r ON k.recipient_id = r.id
            {where_sql}
            ORDER BY k.created_at DESC
            LIMIT ? OFFSET ?;
        """
        cursor.execute(fetch_sql, params + [limit, offset])
        rows = cursor.fetchall()

        # Format items according to user role (DTO segregation)
        data = []
        for row in rows:
            sender = {
                "id": row["sender_id"],
                "name": row["sender_name"],
                "avatar": row["sender_avatar"]
            }
            recipient = {
                "id": row["recipient_id"],
                "name": row["recipient_name"],
                "avatar": row["recipient_avatar"]
            }

            if not is_admin:
                # PublicKudoDTO: Exclude moderation internals and AI flags
                data.append({
                    "id": row["id"],
                    "category": row["category"],
                    "message": row["message"],
                    "created_at": row["created_at"],
                    "sender": sender,
                    "recipient": recipient
                })
            else:
                # AdminKudoDTO: Full visibility for moderation oversight
                data.append({
                    "id": row["id"],
                    "category": row["category"],
                    "message": row["message"],
                    "created_at": row["created_at"],
                    "sender": sender,
                    "recipient": recipient,
                    "is_visible": bool(row["is_visible"]),
                    "moderated_by": row["moderated_by"],
                    "moderated_at": row["moderated_at"],
                    "reason_for_moderation": row["reason_for_moderation"],
                    "ai_flagged": bool(row["ai_flagged"]),
                    "ai_flag_reason": row["ai_flag_reason"]
                })

        return {
            "data": data,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_count
            }
        }
    finally:
        if close_after:
            conn.close()


# ============================================================================
# WRITE OPERATIONS (CREATE, MODERATE, DISMISS, DELETE)
# ============================================================================

def create_kudo(
    current_user: Dict[str, Any],
    recipient_id: str,
    category: str,
    message: str,
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Validates and persists a new appreciation kudo.
    Enforces rules:
    - BR-01: sender_id != recipient_id
    - BR-02: recipient is active
    - BR-03: valid category
    - BR-04: message length 3..500 characters, XSS escaping
    - BR-05: anti-spam cooldown and duplicate submission check
    - Evaluates AI heuristics and saves initial kudo record.
    """
    sender_id = current_user.get("id")
    if not sender_id:
        raise ForbiddenError("Authenticated session is required.")

    # Rule BR-01: Cannot send kudos to oneself
    if sender_id == recipient_id:
        raise ValidationError(
            "An employee cannot send kudos to themselves.",
            details=[{"field": "recipient_id", "issue": "Self-kudos is prohibited."}]
        )

    # Rule BR-04: Length constraint
    trimmed_message = message.strip() if message else ""
    if len(trimmed_message) < 3 or len(trimmed_message) > 500:
        raise ValidationError(
            "Message must be between 3 and 500 characters in length.",
            details=[{"field": "message", "issue": f"Current length is {len(trimmed_message)} characters."}]
        )

    # Sanitize message to prevent XSS
    sanitized_message = html.escape(trimmed_message)

    # Rule BR-03: Category check
    if category not in VALID_CATEGORIES:
        raise ValidationError(
            f"Invalid category '{category}'. Allowed categories: {', '.join(sorted(VALID_CATEGORIES))}.",
            details=[{"field": "category", "issue": "Invalid category choice."}]
        )

    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    try:
        cursor = conn.cursor()

        # Rule BR-02: Validate recipient existence and active status
        cursor.execute("SELECT id, name, is_active FROM users WHERE id = ?;", (recipient_id,))
        recipient = cursor.fetchone()
        if not recipient:
            raise ValidationError(
                "Recipient employee not found.",
                details=[{"field": "recipient_id", "issue": "Unknown recipient ID."}]
            )
        if recipient["is_active"] != 1:
            raise ValidationError(
                "Cannot send kudos to an inactive employee account.",
                details=[{"field": "recipient_id", "issue": "Recipient is inactive."}]
            )

        # Rule BR-05: 1. Duplicate submission check FIRST (identical message within 5 minutes)
        cursor.execute("""
            SELECT COUNT(*) AS count FROM kudos
            WHERE sender_id = ? AND recipient_id = ? AND message = ?
            AND created_at >= datetime('now', '-5 minutes');
        """, (sender_id, recipient_id, sanitized_message))
        if cursor.fetchone()["count"] > 0:
            raise RateLimitError("Duplicate submission detected: identical kudo sent within the last 5 minutes.")

        # Rule BR-05: 2. Anti-spam cooldown check (10 seconds between consecutive kudos)
        cursor.execute("""
            SELECT created_at FROM kudos
            WHERE sender_id = ?
            ORDER BY created_at DESC
            LIMIT 1;
        """, (sender_id,))
        last_kudo = cursor.fetchone()
        if last_kudo:
            try:
                last_time_str = last_kudo["created_at"].replace("Z", "+00:00")
                if "T" in last_time_str:
                    last_time = datetime.datetime.fromisoformat(last_time_str)
                    if last_time.tzinfo is None:
                        last_time = last_time.replace(tzinfo=datetime.timezone.utc)
                else:
                    last_time = datetime.datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc)

                now_utc = get_utc_now()
                delta_sec = (now_utc - last_time).total_seconds()
                if 0 <= delta_sec < COOLDOWN_SECONDS:
                    raise RateLimitError(
                        f"Please wait {int(COOLDOWN_SECONDS - delta_sec)} seconds before submitting another kudo."
                    )
            except RateLimitError:
                raise
            except Exception:
                pass  # Fallback if SQLite datetime format slightly differs

        # Run AI Content Evaluation (Fail-Open policy handled internally)
        ai_flagged, ai_flag_reason = evaluate_content(trimmed_message)

        # Generate unique Kudo UUID
        kudo_id = f"k-{uuid.uuid4().hex[:12]}"
        now_iso = get_utc_now_iso()

        # Pre-moderation Quarantine Policy:
        # If flagged by AI heuristics, automatically quarantine (is_visible = 0)
        # to protect the recipient and public feed pending admin review.
        # Clean messages publish immediately (is_visible = 1).
        initial_visibility = 0 if ai_flagged else 1
        initial_reason = f"Automated AI Quarantine: {ai_flag_reason}" if ai_flagged else None

        cursor.execute("""
            INSERT INTO kudos (
                id, sender_id, recipient_id, category, message, is_visible,
                reason_for_moderation, ai_flagged, ai_flag_reason, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            kudo_id, sender_id, recipient_id, category, sanitized_message,
            initial_visibility, initial_reason,
            1 if ai_flagged else 0, ai_flag_reason, now_iso, now_iso
        ))
        conn.commit()

        return {
            "id": kudo_id,
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "category": category,
            "message": sanitized_message,
            "is_visible": bool(initial_visibility),
            "ai_flagged": ai_flagged,
            "ai_flag_reason": ai_flag_reason,
            "quarantined": bool(ai_flagged),
            "created_at": now_iso
        }
    finally:
        if close_after:
            conn.close()


def moderate_kudo(
    kudo_id: str,
    admin_user: Dict[str, Any],
    is_visible: bool,
    reason: str,
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Hides or restores a kudo.
    Enforces rules:
    - Admin-only authorization
    - Mandatory reason
    - Atomic transaction updating kudos state and inserting into moderation_audit_logs.
    """
    if admin_user.get("role") != "admin":
        raise ForbiddenError("Administrator permissions required to perform moderation.")

    if not reason or not reason.strip():
        raise ValidationError(
            "A moderation reason is mandatory.",
            details=[{"field": "reason", "issue": "Reason must not be empty."}]
        )

    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, is_visible FROM kudos WHERE id = ?;", (kudo_id,))
        kudo = cursor.fetchone()
        if not kudo:
            raise NotFoundError(f"Kudo '{kudo_id}' not found.")

        previous_visibility = kudo["is_visible"]
        new_visibility = 1 if is_visible else 0
        action = "RESTORE" if is_visible else "HIDE"
        admin_id = admin_user["id"]
        audit_id = f"aud-{uuid.uuid4().hex[:12]}"
        now_iso = get_utc_now_iso()

        # Atomic transaction (BR-08)
        cursor.execute("BEGIN TRANSACTION;")
        try:
            # Update current state on kudos table (REQ-SUJET-06)
            cursor.execute("""
                UPDATE kudos
                SET is_visible = ?,
                    moderated_by = ?,
                    moderated_at = ?,
                    reason_for_moderation = ?,
                    updated_at = ?
                WHERE id = ?;
            """, (new_visibility, admin_id, now_iso, reason.strip(), now_iso, kudo_id))

            # Insert immutable audit entry
            cursor.execute("""
                INSERT INTO moderation_audit_logs (
                    id, kudo_id, moderator_id, action, reason,
                    previous_visibility, new_visibility, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (audit_id, kudo_id, admin_id, action, reason.strip(), previous_visibility, new_visibility, now_iso))

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return {
            "id": kudo_id,
            "is_visible": bool(new_visibility),
            "moderated_by": admin_id,
            "moderated_at": now_iso,
            "reason_for_moderation": reason.strip(),
            "action": action
        }
    finally:
        if close_after:
            conn.close()


def dismiss_ai_flag(
    kudo_id: str,
    admin_user: Dict[str, Any],
    reason: str,
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Dismisses an unfounded AI alert (false positive).
    Clears ai_flagged on the kudo and writes an audit log entry.
    """
    if admin_user.get("role") != "admin":
        raise ForbiddenError("Administrator permissions required to dismiss AI flags.")

    if not reason or not reason.strip():
        raise ValidationError(
            "A reason justifying flag dismissal is mandatory.",
            details=[{"field": "reason", "issue": "Reason must not be empty."}]
        )

    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, ai_flagged, is_visible FROM kudos WHERE id = ?;", (kudo_id,))
        kudo = cursor.fetchone()
        if not kudo:
            raise NotFoundError(f"Kudo '{kudo_id}' not found.")

        admin_id = admin_user["id"]
        audit_id = f"aud-{uuid.uuid4().hex[:12]}"
        now_iso = get_utc_now_iso()

        cursor.execute("BEGIN TRANSACTION;")
        try:
            cursor.execute("""
                UPDATE kudos
                SET ai_flagged = 0,
                    ai_flag_reason = NULL,
                    updated_at = ?
                WHERE id = ?;
            """, (now_iso, kudo_id))

            cursor.execute("""
                INSERT INTO moderation_audit_logs (
                    id, kudo_id, moderator_id, action, reason,
                    previous_visibility, new_visibility, created_at
                ) VALUES (?, ?, ?, 'DISMISS_AI_FLAG', ?, ?, ?, ?);
            """, (audit_id, kudo_id, admin_id, reason.strip(), kudo["is_visible"], kudo["is_visible"], now_iso))

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return {
            "id": kudo_id,
            "ai_flagged": False,
            "action": "DISMISS_AI_FLAG",
            "reason": reason.strip()
        }
    finally:
        if close_after:
            conn.close()


def delete_kudo(
    kudo_id: str,
    admin_user: Dict[str, Any],
    reason: str,
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Permanently deletes a kudo while preserving full audit history (BR-09).
    """
    if admin_user.get("role") != "admin":
        raise ForbiddenError("Administrator permissions required to delete kudos.")

    if not reason or not reason.strip():
        raise ValidationError(
            "A deletion reason is mandatory.",
            details=[{"field": "reason", "issue": "Reason must not be empty."}]
        )

    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, is_visible FROM kudos WHERE id = ?;", (kudo_id,))
        kudo = cursor.fetchone()
        if not kudo:
            raise NotFoundError(f"Kudo '{kudo_id}' not found.")

        admin_id = admin_user["id"]
        audit_id = f"aud-{uuid.uuid4().hex[:12]}"
        now_iso = get_utc_now_iso()

        cursor.execute("BEGIN TRANSACTION;")
        try:
            # 1. Log deletion audit entry before row removal
            cursor.execute("""
                INSERT INTO moderation_audit_logs (
                    id, kudo_id, moderator_id, action, reason,
                    previous_visibility, new_visibility, created_at
                ) VALUES (?, ?, ?, 'DELETE', ?, ?, NULL, ?);
            """, (audit_id, kudo_id, admin_id, reason.strip(), kudo["is_visible"], now_iso))

            # 2. Hard delete kudo record
            cursor.execute("DELETE FROM kudos WHERE id = ?;", (kudo_id,))

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return {
            "success": True,
            "message": f"Kudo '{kudo_id}' permanently deleted and logged to audit trail."
        }
    finally:
        if close_after:
            conn.close()


def get_kudo_audit(
    kudo_id: str,
    admin_user: Dict[str, Any],
    conn: Optional[sqlite3.Connection] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves the complete audit trail for a specific kudo (Admin only).
    """
    if admin_user.get("role") != "admin":
        raise ForbiddenError("Administrator permissions required to view audit trail.")

    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.id, a.kudo_id, a.action, a.reason,
                   a.previous_visibility, a.new_visibility, a.created_at,
                   u.name AS moderator_name, u.email AS moderator_email
            FROM moderation_audit_logs a
            JOIN users u ON a.moderator_id = u.id
            WHERE a.kudo_id = ?
            ORDER BY a.created_at ASC;
        """, (kudo_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        if close_after:
            conn.close()
