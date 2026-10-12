"""
PROJECT: Datacom Kudos System
FILE: tests/test_api.py
DESCRIPTION: Integration Test Suite for REST API & RBAC (Phase P3).
             Validates all endpoints, HTTP status codes (200, 201, 401, 403, 422, 429),
             DTO segregation, session validation, and RFC 7807 error structures.
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from src.main import app
from src.db.database import init_db


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Spins up an ephemeral SQLite database for each API test run,
    overriding DB_PATH and running initial schema and seed migrations.
    """
    test_db_file = tmp_path / "test_api_kudos.db"
    monkeypatch.setenv("DB_PATH", str(test_db_file))
    monkeypatch.setattr("src.db.database.DB_PATH", test_db_file)
    init_db(test_db_file)

    with TestClient(app) as test_client:
        yield test_client


# ============================================================================
# 0. SPA FRONTEND HEALTH & ROOT ROUTE
# ============================================================================

def test_root_serves_spa_index_html(client: TestClient):
    """GET / serves the SPA index.html frontend."""
    response = client.get("/")
    assert response.status_code == 200
    assert "DATACOM" in response.text
    assert "kudoForm" in response.text


# ============================================================================
# 1. AUTHENTICATION & RBAC MIDDLEWARE TESTS
# ============================================================================

def test_missing_x_user_id_returns_401(client: TestClient):
    """Requests without X-User-Id must return HTTP 401 Unauthorized in RFC 7807 format."""
    response = client.get("/api/v1/users")
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert data["error"]["status"] == 401


def test_unknown_x_user_id_returns_401(client: TestClient):
    """Requests with non-existent user IDs must return HTTP 401 Unauthorized."""
    response = client.get("/api/v1/users", headers={"X-User-Id": "u-unknown-999"})
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"


def test_inactive_user_returns_403(client: TestClient):
    """Inactive users (e.g., Lucas u-06) must be denied access with HTTP 403 Forbidden."""
    response = client.get("/api/v1/users", headers={"X-User-Id": "u-06"})
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "FORBIDDEN"
    assert "inactive" in data["error"]["message"].lower()


# ============================================================================
# 2. DIRECTORY & FEED TESTS (GET /users, GET /kudos)
# ============================================================================

def test_get_users_returns_only_active_colleagues(client: TestClient):
    """GET /api/v1/users returns active users; inactive user Lucas (u-06) is excluded."""
    response = client.get("/api/v1/users", headers={"X-User-Id": "u-01"})
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    user_ids = [u["id"] for u in users]
    assert "u-01" in user_ids
    assert "u-03" in user_ids  # Thomas (Admin)
    assert "u-06" not in user_ids  # Lucas is inactive


def test_feed_dto_segregation_for_standard_user(client: TestClient):
    """
    Rule BR-06: Standard employees receive PublicKudoDTO.
    Internal moderation fields and AI alerts must be strictly expunged.
    """
    response = client.get("/api/v1/kudos", headers={"X-User-Id": "u-01"})
    assert response.status_code == 200
    feed = response.json()
    assert "data" in feed
    assert "pagination" in feed
    assert len(feed["data"]) > 0

    first_item = feed["data"][0]
    # Required public fields
    assert "id" in first_item
    assert "category" in first_item
    assert "message" in first_item
    assert "sender" in first_item
    assert "recipient" in first_item
    # Internal fields MUST NOT be present
    assert "is_visible" not in first_item
    assert "moderated_by" not in first_item
    assert "moderated_at" not in first_item
    assert "reason_for_moderation" not in first_item
    assert "ai_flagged" not in first_item
    assert "ai_flag_reason" not in first_item


def test_feed_dto_segregation_for_admin_user(client: TestClient):
    """
    Rule BR-06: Administrators (Thomas u-03) receive AdminKudoDTO with moderation metadata.
    """
    response = client.get("/api/v1/kudos", headers={"X-User-Id": "u-03"})
    assert response.status_code == 200
    feed = response.json()
    first_item = feed["data"][0]
    # Admin fields MUST be present
    assert "is_visible" in first_item
    assert "ai_flagged" in first_item
    assert "reason_for_moderation" in first_item


# ============================================================================
# 3. KUDO SUBMISSION TESTS (POST /kudos)
# ============================================================================

def test_successful_kudo_creation(client: TestClient):
    """Valid kudo submission returns HTTP 201 Created and persists record."""
    payload = {
        "recipient_id": "u-02",
        "category": "Innovation",
        "message": "Fabulous initiative building the new cloud provisioning script!"
    }
    response = client.post("/api/v1/kudos", json=payload, headers={"X-User-Id": "u-01"})
    assert response.status_code == 201
    created = response.json()
    assert created["sender_id"] == "u-01"
    assert created["recipient_id"] == "u-02"
    assert created["category"] == "Innovation"
    assert created["is_visible"] is True


def test_self_kudos_rejected(client: TestClient):
    """Rule BR-01: An employee cannot send kudos to themselves (HTTP 422)."""
    payload = {
        "recipient_id": "u-01",
        "category": "Leadership",
        "message": "I am sending kudos to myself!"
    }
    response = client.post("/api/v1/kudos", json=payload, headers={"X-User-Id": "u-01"})
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "themselves" in data["error"]["message"].lower()


def test_inactive_recipient_rejected(client: TestClient):
    """Rule BR-02: Sending kudos to an inactive employee account is rejected (HTTP 422)."""
    payload = {
        "recipient_id": "u-06",
        "category": "Teamwork",
        "message": "Thanks for your past efforts Lucas!"
    }
    response = client.post("/api/v1/kudos", json=payload, headers={"X-User-Id": "u-01"})
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_invalid_category_rejected(client: TestClient):
    """Rule BR-03: Categories outside the approved list are rejected (HTTP 422)."""
    payload = {
        "recipient_id": "u-02",
        "category": "RandomUnapprovedCategory",
        "message": "Great work on this task!"
    }
    response = client.post("/api/v1/kudos", json=payload, headers={"X-User-Id": "u-01"})
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_message_length_bounds(client: TestClient):
    """Rule BR-04: Messages shorter than 3 or longer than 500 characters are rejected (HTTP 422)."""
    short_payload = {
        "recipient_id": "u-02",
        "category": "Teamwork",
        "message": "ok"
    }
    res_short = client.post("/api/v1/kudos", json=short_payload, headers={"X-User-Id": "u-01"})
    assert res_short.status_code == 422

    long_payload = {
        "recipient_id": "u-02",
        "category": "Teamwork",
        "message": "x" * 501
    }
    res_long = client.post("/api/v1/kudos", json=long_payload, headers={"X-User-Id": "u-01"})
    assert res_long.status_code == 422


def test_cooldown_rate_limiting(client: TestClient):
    """Rule BR-05: Consecutive kudos within 10 seconds trigger HTTP 429 Rate Limit."""
    payload1 = {
        "recipient_id": "u-02",
        "category": "Teamwork",
        "message": "First legitimate compliment of the sprint."
    }
    res1 = client.post("/api/v1/kudos", json=payload1, headers={"X-User-Id": "u-01"})
    assert res1.status_code == 201

    payload2 = {
        "recipient_id": "u-04",
        "category": "Innovation",
        "message": "Second compliment sent immediately without waiting."
    }
    res2 = client.post("/api/v1/kudos", json=payload2, headers={"X-User-Id": "u-01"})
    assert res2.status_code == 429
    data = res2.json()
    assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"


# ============================================================================
# 4. MODERATION & AUDIT TESTS (ADMIN ONLY)
# ============================================================================

def test_admin_routes_forbidden_for_standard_user(client: TestClient):
    """Standard employees attempting admin endpoints receive HTTP 403 Forbidden."""
    user_header = {"X-User-Id": "u-01"}

    # Attempt moderate
    res_mod = client.patch(
        "/api/v1/kudos/k-001/moderate",
        json={"is_visible": False, "reason": "Unauthorized attempt"},
        headers=user_header
    )
    assert res_mod.status_code == 403

    # Attempt dismiss flag
    res_dismiss = client.post(
        "/api/v1/kudos/k-001/dismiss-flag",
        json={"reason": "Unauthorized attempt"},
        headers=user_header
    )
    assert res_dismiss.status_code == 403

    # Attempt delete
    res_del = client.request(
        "DELETE",
        "/api/v1/kudos/k-001",
        json={"reason": "Unauthorized attempt"},
        headers=user_header
    )
    assert res_del.status_code == 403

    # Attempt view audit
    res_audit = client.get("/api/v1/kudos/k-001/audit", headers=user_header)
    assert res_audit.status_code == 403


def test_admin_moderate_toggle_visibility_and_audit(client: TestClient):
    """Admin (Thomas u-03) can hide and restore a kudo, writing immutable audit log entries."""
    admin_header = {"X-User-Id": "u-03"}

    # 1. Hide kudo k-001
    hide_res = client.patch(
        "/api/v1/kudos/k-001/moderate",
        json={"is_visible": False, "reason": "Violates internal guidelines"},
        headers=admin_header
    )
    assert hide_res.status_code == 200
    assert hide_res.json()["is_visible"] is False

    # 2. Verify audit entry
    audit_res = client.get("/api/v1/kudos/k-001/audit", headers=admin_header)
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert len(logs) >= 1
    assert logs[-1]["action"] == "HIDE"
    assert logs[-1]["reason"] == "Violates internal guidelines"

    # 3. Restore visibility
    restore_res = client.patch(
        "/api/v1/kudos/k-001/moderate",
        json={"is_visible": True, "reason": "Issue resolved, restored."},
        headers=admin_header
    )
    assert restore_res.status_code == 200
    assert restore_res.json()["is_visible"] is True


def test_admin_dismiss_ai_flag(client: TestClient):
    """Admin (Thomas u-03) can dismiss an AI flag, writing DISMISS_AI_FLAG into audit logs."""
    admin_header = {"X-User-Id": "u-03"}

    res = client.post(
        "/api/v1/kudos/k-002/dismiss-flag",
        json={"reason": "Technical slang accepted in context"},
        headers=admin_header
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ai_flagged"] is False
    assert data["action"] == "DISMISS_AI_FLAG"


def test_admin_delete_kudo_preserves_audit_trail(client: TestClient):
    """
    Rule BR-09: Deleting a kudo removes the kudo row but retains the audit history.
    """
    admin_header = {"X-User-Id": "u-03"}

    # Delete kudo k-003
    del_res = client.request(
        "DELETE",
        "/api/v1/kudos/k-003",
        json={"reason": "Severe spam deletion"},
        headers=admin_header
    )
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Audit history for k-003 is still accessible to admin
    audit_res = client.get("/api/v1/kudos/k-003/audit", headers=admin_header)
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert len(logs) >= 1
    assert logs[-1]["action"] == "DELETE"


def test_flagged_kudo_is_automatically_quarantined_from_public_feed(client: TestClient):
    """
    Suspicious or offensive content is automatically quarantined (is_visible = 0).
    It is hidden from standard users (including recipient) but visible to admins.
    """
    payload = {
        "recipient_id": "u-02",
        "category": "Teamwork",
        "message": "You are a complete idiot and jerk!"  # Triggers bad-words detection
    }
    # 1. Post by standard user u-01
    res = client.post("/api/v1/kudos", json=payload, headers={"X-User-Id": "u-01"})
    assert res.status_code == 201
    kudo = res.json()
    assert kudo["ai_flagged"] is True
    assert kudo["is_visible"] is False
    assert kudo["quarantined"] is True

    # 2. Recipient u-02 views public feed -> kudo is NOT present!
    feed_res = client.get("/api/v1/kudos", headers={"X-User-Id": "u-02"})
    feed_ids = [k["id"] for k in feed_res.json()["data"]]
    assert kudo["id"] not in feed_ids

    # 3. Admin u-03 views feed with filter=flagged -> kudo IS present!
    admin_feed = client.get("/api/v1/kudos?filter=flagged", headers={"X-User-Id": "u-03"})
    admin_ids = [k["id"] for k in admin_feed.json()["data"]]
    assert kudo["id"] in admin_ids


def test_get_user_statistics_api(client: TestClient):
    """
    US-05 / US-07: Tests GET /api/v1/users/{id}/statistics endpoint.
    Returns user details along with kudos_received and kudos_sent counts.
    """
    res = client.get("/api/v1/users/u-01/statistics", headers={"X-User-Id": "u-01"})
    assert res.status_code == 200
    data = res.json()
    assert data["user_id"] == "u-01"
    assert data["name"] == "Sarah Connor"
    assert "kudos_received" in data
    assert "kudos_sent" in data
    assert isinstance(data["kudos_received"], int)
    assert isinstance(data["kudos_sent"], int)

    # 404 for unknown user
    res_404 = client.get("/api/v1/users/u-ghost/statistics", headers={"X-User-Id": "u-01"})
    assert res_404.status_code == 404


def test_kudos_feed_scope_api(client: TestClient):
    """
    US-05: Tests GET /api/v1/kudos with personal scope parameter ('all', 'received', 'sent').
    """
    # 1. Scope=all returns general feed
    res_all = client.get("/api/v1/kudos?scope=all", headers={"X-User-Id": "u-01"})
    assert res_all.status_code == 200

    # 2. Scope=received returns kudos received by u-01
    res_received = client.get("/api/v1/kudos?scope=received", headers={"X-User-Id": "u-01"})
    assert res_received.status_code == 200
    for kudo in res_received.json()["data"]:
        assert kudo["recipient"]["id"] == "u-01"

    # 3. Scope=sent returns kudos sent by u-01
    res_sent = client.get("/api/v1/kudos?scope=sent", headers={"X-User-Id": "u-01"})
    assert res_sent.status_code == 200
    for kudo in res_sent.json()["data"]:
        assert kudo["sender"]["id"] == "u-01"

