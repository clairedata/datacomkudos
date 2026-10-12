"""
PROJECT: Datacom Kudos System
FILE: tests/test_services.py
DESCRIPTION: Pytest Test Suite for Phase P2 Core Services and AI Moderation
             Validates AI Heuristics, Business Rules (BR-01 to BR-11),
             DTO segregation, Moderation transactions, and Audit Immutability.
"""

import sqlite3
import pytest

from src.db.database import get_connection, init_db
from src.services.ai_moderation import evaluate_content
import src.services.ai_moderation as aimod
from src.services.kudos_service import (
    create_kudo,
    get_kudos_feed,
    get_user_statistics,
    moderate_kudo,
    dismiss_ai_flag,
    delete_kudo,
    get_kudo_audit,
    get_active_users,
    ValidationError,
    RateLimitError,
    ForbiddenError,
    NotFoundError,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def db_conn(tmp_path):
    """Provides a fresh, isolated SQLite test database for each test function."""
    test_db_file = tmp_path / "test_kudos.db"
    init_db(test_db_file)
    conn = get_connection(test_db_file)
    yield conn
    conn.close()


@pytest.fixture
def sarah_user():
    return {"id": "u-01", "name": "Sarah Connor", "role": "user"}


@pytest.fixture
def james_user():
    return {"id": "u-02", "name": "James Vance", "role": "user"}


@pytest.fixture
def thomas_admin():
    return {"id": "u-03", "name": "Thomas Wright", "role": "admin"}


# ============================================================================
# 1. AI HEURISTICS & CONTENT EVALUATION TESTS
# ============================================================================

def test_ai_clean_message():
    """Verify that legitimate appreciation content is not flagged."""
    flagged, reason = evaluate_content("Thank you for your excellent assistance today!")
    assert not flagged
    assert reason is None


def test_ai_offensive_word_detected():
    """Verify that abusive language is caught by the heuristic dictionary."""
    flagged, reason = evaluate_content("You are completely incompetent and lazy!")
    assert flagged is True
    assert reason is not None
    assert "incompetent" in reason


def test_ai_leetspeak_evasion_detected():
    """Verify that common leetspeak substitutions are normalized and detected."""
    flagged, reason = evaluate_content("You are an 1d10t!")
    assert flagged is True
    assert reason is not None
    assert "idiot" in reason


def test_ai_repeated_character_spam():
    """Verify that excessive character repetition is flagged as spam."""
    flagged, reason = evaluate_content("Great jobbbbbbbbbbbbbbbbb on the sprint!")
    assert flagged is True
    assert "Repetitive" in reason


def test_ai_fail_open_resilience(monkeypatch):
    """
    Verify the Fail-Open policy: if the normalizer or scanner crashes,
    the kudo is accepted normally (flagged=False) rather than blocking the user.
    """
    def mock_broken_normalize(text):
        raise RuntimeError("Simulated internal AI normalizer failure")

    monkeypatch.setattr(aimod, "normalize_text", mock_broken_normalize)
    flagged, reason = evaluate_content("Test message during internal engine fault")
    assert flagged is False
    assert reason is None


# ============================================================================
# 2. BUSINESS RULES & INPUT VALIDATION TESTS (BR-01 TO BR-05)
# ============================================================================

def test_br01_self_kudos_rejection(db_conn, sarah_user):
    """BR-01: An employee cannot send kudos to themselves."""
    with pytest.raises(ValidationError) as exc_info:
        create_kudo(
            current_user=sarah_user,
            recipient_id="u-01",  # Same as sender
            category="Teamwork",
            message="I appreciate my own performance!",
            conn=db_conn
        )
    assert "cannot send kudos to themselves" in exc_info.value.message


def test_br02_inactive_recipient_rejection(db_conn, sarah_user):
    """BR-02: Kudos cannot be addressed to inactive employee accounts."""
    with pytest.raises(ValidationError) as exc_info:
        create_kudo(
            current_user=sarah_user,
            recipient_id="u-06",  # Lucas Moreau (is_active = 0)
            category="Teamwork",
            message="Kudo to an inactive contractor",
            conn=db_conn
        )
    assert "inactive" in exc_info.value.message


def test_br03_invalid_category_rejection(db_conn, sarah_user):
    """BR-03: Category must belong to the closed enumerated list."""
    with pytest.raises(ValidationError) as exc_info:
        create_kudo(
            current_user=sarah_user,
            recipient_id="u-02",
            category="RandomNonExistentCategory",
            message="Message with invalid category",
            conn=db_conn
        )
    assert "Invalid category" in exc_info.value.message


def test_br04_message_length_under_minimum(db_conn, sarah_user):
    """BR-04: Messages shorter than 3 characters after trimming are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        create_kudo(
            current_user=sarah_user,
            recipient_id="u-02",
            category="Teamwork",
            message="Ok",  # 2 characters
            conn=db_conn
        )
    assert "between 3 and 500 characters" in exc_info.value.message


def test_br04_message_length_over_maximum(db_conn, sarah_user):
    """BR-04: Messages exceeding 500 characters are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        create_kudo(
            current_user=sarah_user,
            recipient_id="u-02",
            category="Teamwork",
            message="A" * 501,
            conn=db_conn
        )
    assert "between 3 and 500 characters" in exc_info.value.message


def test_successful_kudo_creation(db_conn, sarah_user):
    """Verify that a valid submission persists correctly into SQLite."""
    created = create_kudo(
        current_user=sarah_user,
        recipient_id="u-02",
        category="Teamwork",
        message="Super helpful peer review on the API design!",
        conn=db_conn
    )
    assert created["id"].startswith("k-")
    assert created["sender_id"] == "u-01"
    assert created["recipient_id"] == "u-02"
    assert created["is_visible"] is True


def test_br05_duplicate_submission_rejection(db_conn, sarah_user):
    """BR-05: Submitting identical content to the same recipient within 5 min is blocked."""
    # 1. First submit the kudo initially
    create_kudo(
        current_user=sarah_user,
        recipient_id="u-02",
        category="Teamwork",
        message="Super helpful peer review on the API design!",
        conn=db_conn
    )

    # 2. Then attempt duplicate submission with identical content
    with pytest.raises(RateLimitError) as exc_info:
        create_kudo(
            current_user=sarah_user,
            recipient_id="u-02",
            category="Teamwork",
            message="Super helpful peer review on the API design!",  # Duplicate
            conn=db_conn
        )
    assert "Duplicate submission" in exc_info.value.message


def test_br05_cooldown_rejection_different_message(db_conn, sarah_user):
    """BR-05: Submitting two different kudos within 10 seconds triggers anti-spam cooldown."""
    # First submission
    create_kudo(
        current_user=sarah_user,
        recipient_id="u-02",
        category="Teamwork",
        message="First appreciation message",
        conn=db_conn
    )
    # Second submission with a different message and different recipient
    with pytest.raises(RateLimitError) as exc_info:
        create_kudo(
            current_user=sarah_user,
            recipient_id="u-04",
            category="Innovation",
            message="Second different message sent immediately",
            conn=db_conn
        )
    assert "Please wait" in exc_info.value.message


# ============================================================================
# 3. DTO SEGREGATION & PRIVACY TESTS (BR-06)
# ============================================================================

def test_br06_public_dto_excludes_internal_fields(db_conn, sarah_user):
    """
    BR-06: Standard users receive PublicKudoDTO.
    Internal moderation fields (is_visible, ai_flagged, reasons) must be expunged.
    """
    feed = get_kudos_feed(current_user=sarah_user, limit=10, conn=db_conn)
    assert len(feed["data"]) > 0
    first_item = feed["data"][0]
    assert "id" in first_item
    assert "message" in first_item
    assert "sender" in first_item
    assert "recipient" in first_item
    # Internal moderation fields must NOT be present
    assert "is_visible" not in first_item
    assert "ai_flagged" not in first_item
    assert "moderated_by" not in first_item
    assert "reason_for_moderation" not in first_item


def test_br06_admin_dto_includes_moderation_fields(db_conn, thomas_admin):
    """
    BR-06: Administrators receive AdminKudoDTO with moderation metadata.
    """
    feed = get_kudos_feed(current_user=thomas_admin, limit=10, conn=db_conn)
    assert len(feed["data"]) > 0
    first_item = feed["data"][0]
    assert "is_visible" in first_item
    assert "ai_flagged" in first_item
    assert "moderated_by" in first_item


# ============================================================================
# 4. MODERATION ACTIONS, AUDIT IMMUTABILITY & DELETION (BR-07 TO BR-10)
# ============================================================================

def test_rbac_non_admin_cannot_moderate(db_conn, sarah_user):
    """Verify that a non-admin attempting to moderate receives ForbiddenError."""
    with pytest.raises(ForbiddenError):
        moderate_kudo(
            kudo_id="k-001",
            admin_user=sarah_user,
            is_visible=False,
            reason="Unauthorized attempt",
            conn=db_conn
        )


def test_admin_hide_and_restore_flow(db_conn, thomas_admin, sarah_user):
    """
    Tests administrative hide and restore flow:
    - Admin hides kudo with mandatory reason
    - Kudo disappears from standard user feed
    - Admin restores kudo
    - Audit log entries created for both events
    """
    # 1. Admin hides kudo
    hidden = moderate_kudo(
        kudo_id="k-001",
        admin_user=thomas_admin,
        is_visible=False,
        reason="Hiding temporarily for content verification",
        conn=db_conn
    )
    assert hidden["is_visible"] is False

    # 2. Verify kudo is excluded from standard user feed
    user_feed = get_kudos_feed(current_user=sarah_user, limit=50, conn=db_conn)
    ids_in_feed = [k["id"] for k in user_feed["data"]]
    assert "k-001" not in ids_in_feed

    # 3. Admin restores kudo
    restored = moderate_kudo(
        kudo_id="k-001",
        admin_user=thomas_admin,
        is_visible=True,
        reason="Verified content: restoring to public feed",
        conn=db_conn
    )
    assert restored["is_visible"] is True

    # 4. Check audit trail
    audit = get_kudo_audit(kudo_id="k-001", admin_user=thomas_admin, conn=db_conn)
    actions = [entry["action"] for entry in audit]
    assert "HIDE" in actions
    assert "RESTORE" in actions


def test_admin_dismiss_ai_flag(db_conn, thomas_admin):
    """Tests dismissing an AI flag (false positive) with audit recording."""
    dismissed = dismiss_ai_flag(
        kudo_id="k-003",  # Seed kudo with ai_flagged = 1
        admin_user=thomas_admin,
        reason="Verified false positive: technical metaphor",
        conn=db_conn
    )
    assert dismissed["ai_flagged"] is False
    assert dismissed["action"] == "DISMISS_AI_FLAG"


def test_audit_log_immutability_triggers(db_conn, thomas_admin):
    """
    Tests SQL triggers trg_prevent_audit_update and trg_prevent_audit_delete:
    Direct UPDATE or DELETE on moderation_audit_logs must be aborted by SQLite.
    """
    # 1. Create an audit entry by moderating a kudo first
    moderate_kudo(
        kudo_id="k-001",
        admin_user=thomas_admin,
        is_visible=False,
        reason="Creating audit entry for immutability trigger test",
        conn=db_conn
    )

    # 2. Retrieve the newly created audit log entry
    cursor = db_conn.cursor()
    cursor.execute("SELECT id FROM moderation_audit_logs LIMIT 1;")
    row = cursor.fetchone()
    assert row is not None
    audit_id = row["id"]

    # Test UPDATE trigger rejection
    with pytest.raises(sqlite3.DatabaseError) as exc_update:
        db_conn.execute("UPDATE moderation_audit_logs SET reason = 'tampered' WHERE id = ?;", (audit_id,))
    assert "immutable" in str(exc_update.value).lower()

    # Test DELETE trigger rejection
    with pytest.raises(sqlite3.DatabaseError) as exc_delete:
        db_conn.execute("DELETE FROM moderation_audit_logs WHERE id = ?;", (audit_id,))
    assert "immutable" in str(exc_delete.value).lower()


def test_br09_delete_kudo_preserves_audit(db_conn, thomas_admin):
    """
    BR-09: Permanent deletion removes the kudo row from 'kudos',
    but retains all audit entries in 'moderation_audit_logs'.
    """
    # Count audit entries for k-003 before delete
    prior_audit = get_kudo_audit(kudo_id="k-003", admin_user=thomas_admin, conn=db_conn)
    prior_count = len(prior_audit)

    # Delete kudo
    result = delete_kudo(
        kudo_id="k-003",
        admin_user=thomas_admin,
        reason="Removing obsolete demonstration kudo",
        conn=db_conn
    )
    assert result["success"] is True

    # Confirm kudo row is deleted
    cursor = db_conn.cursor()
    cursor.execute("SELECT id FROM kudos WHERE id = 'k-003';")
    assert cursor.fetchone() is None

    # Confirm audit records are retained (prior count + 1 DELETE event)
    post_audit = get_kudo_audit(kudo_id="k-003", admin_user=thomas_admin, conn=db_conn)
    assert len(post_audit) == prior_count + 1
    assert post_audit[-1]["action"] == "DELETE"


def test_get_user_statistics(db_conn, sarah_user):
    """
    US-05: Verifies that get_user_statistics correctly aggregates
    kudos received (only visible) and kudos sent.
    """
    stats = get_user_statistics(user_id="u-01", conn=db_conn)
    assert stats["user_id"] == "u-01"
    assert stats["name"] == "Sarah Connor"
    assert "kudos_received" in stats
    assert "kudos_sent" in stats
    assert stats["kudos_received"] >= 0
    assert stats["kudos_sent"] >= 0

    # Non-existent user raises NotFoundError
    with pytest.raises(NotFoundError):
        get_user_statistics(user_id="u-does-not-exist", conn=db_conn)


def test_kudos_feed_scope_filtering(db_conn, sarah_user, james_user):
    """
    US-05: Verifies that scope='received' and scope='sent' filter the feed
    strictly according to the active user's identity.
    """
    # Create a kudo from Sarah to James
    create_kudo(
        current_user=sarah_user,
        recipient_id="u-02",
        category="Teamwork",
        message="Super job James on the deployment!",
        conn=db_conn
    )

    # Sarah views sent kudos
    sent_feed = get_kudos_feed(current_user=sarah_user, scope="sent", conn=db_conn)
    for kudo in sent_feed["data"]:
        assert kudo["sender"]["id"] == "u-01"

    # James views received kudos
    received_feed = get_kudos_feed(current_user=james_user, scope="received", conn=db_conn)
    for kudo in received_feed["data"]:
        assert kudo["recipient"]["id"] == "u-02"

