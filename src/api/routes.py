"""
PROJECT: Datacom Kudos System
FILE: src/api/routes.py
DESCRIPTION: REST API Routes Implementation (v1 endpoints).
             Implements all contracts defined in SPECIFICATION.md:
             - Active users directory (GET /users)
             - Paginated kudos feed with DTO segregation (GET /kudos)
             - Submission of kudos (POST /kudos)
             - Admin moderation: toggle visibility (PATCH /kudos/{id}/moderate)
             - Admin moderation: dismiss AI flag (POST /kudos/{id}/dismiss-flag)
             - Admin moderation: permanent deletion (DELETE /kudos/{id})
             - Admin moderation: immutable audit trail (GET /kudos/{id}/audit)
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, Path, Body, status
from pydantic import BaseModel, Field

from src.middleware.auth import get_current_user, require_admin
from src.services.kudos_service import (
    get_active_users,
    get_user_statistics,
    get_kudos_feed,
    create_kudo,
    moderate_kudo,
    dismiss_ai_flag,
    delete_kudo,
    get_kudo_audit
)

router = APIRouter(prefix="/api/v1", tags=["Kudos API"])


# ============================================================================
# REQUEST SCHEMAS (PYDANTIC DTOs)
# ============================================================================

class CreateKudoRequest(BaseModel):
    """Payload schema for submitting a new appreciation kudo."""
    recipient_id: str = Field(..., description="Unique ID of recipient colleague")
    category: str = Field(..., description="Category from approved list (BR-03)")
    message: str = Field(..., description="Appreciation message (3 to 500 characters, BR-04)")


class ModerateKudoRequest(BaseModel):
    """Payload schema for administrative visibility changes."""
    is_visible: bool = Field(..., description="Target visibility (True: restore, False: hide)")
    reason: str = Field(..., description="Mandatory audit explanation for moderation")


class DismissFlagRequest(BaseModel):
    """Payload schema for dismissing false-positive AI flags."""
    reason: str = Field(..., description="Mandatory audit justification for flag dismissal")


class DeleteKudoRequest(BaseModel):
    """Payload schema for permanent kudo deletion."""
    reason: str = Field(..., description="Mandatory audit explanation for deletion")


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/users")
def list_users(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Retrieves the list of active colleagues for the recipient dropdown selector.
    Accessible to any authenticated user.
    """
    return get_active_users()


@router.get("/users/{user_id}/statistics")
def get_user_statistics_endpoint(
    user_id: str = Path(..., description="Unique ID of the user"),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Retrieves personal kudos statistics (received and sent counts) for an employee (US-05).
    Accessible to any authenticated user.
    """
    return get_user_statistics(user_id)


@router.get("/kudos")
def list_kudos(
    limit: int = Query(20, ge=1, le=50, description="Number of items to retrieve (max 50)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    filter: str = Query("all", description="Admin filter: 'all', 'flagged', or 'hidden'"),
    scope: str = Query("all", description="Personal scope: 'all', 'received', or 'sent' (US-05)"),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Retrieves the paginated kudos feed.
    Enforces strict DTO segregation (BR-06):
    - Standard employees receive PublicKudoDTO (only visible kudos, internal moderation expunged).
    - Administrators receive AdminKudoDTO (including visibility flags, AI warnings, and audit data).
    - Supports personal scope ('all', 'received', 'sent') per US-05.
    """
    # Enforce default filter for standard users
    filter_type = filter if current_user.get("role") == "admin" else "all"

    return get_kudos_feed(
        current_user=current_user,
        limit=limit,
        offset=offset,
        filter_type=filter_type,
        scope=scope
    )


@router.post("/kudos", status_code=status.HTTP_201_CREATED)
def submit_kudo(
    payload: CreateKudoRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Submits a new appreciation kudo.
    The sender identity is strictly derived from the authenticated session (X-User-Id).
    Enforces business rules BR-01 to BR-05 and runs synchronous AI moderation.
    """
    return create_kudo(
        current_user=current_user,
        recipient_id=payload.recipient_id,
        category=payload.category,
        message=payload.message
    )


@router.patch("/kudos/{kudo_id}/moderate")
def moderate_kudo_endpoint(
    kudo_id: str = Path(..., description="Unique ID of the kudo to moderate"),
    payload: ModerateKudoRequest = Body(...),
    current_user: Dict[str, Any] = Depends(require_admin)
):
    """
    Hides or restores a kudo.
    Requires administrator privileges. Executes an atomic transaction that updates
    kudos current state and appends an immutable entry to moderation_audit_logs.
    """
    return moderate_kudo(
        kudo_id=kudo_id,
        admin_user=current_user,
        is_visible=payload.is_visible,
        reason=payload.reason
    )


@router.post("/kudos/{kudo_id}/dismiss-flag")
def dismiss_flag_endpoint(
    kudo_id: str = Path(..., description="Unique ID of the flagged kudo"),
    payload: DismissFlagRequest = Body(...),
    current_user: Dict[str, Any] = Depends(require_admin)
):
    """
    Dismisses an unfounded AI alert (false positive).
    Requires administrator privileges. Atomically clears the AI flag and writes an audit log.
    """
    return dismiss_ai_flag(
        kudo_id=kudo_id,
        admin_user=current_user,
        reason=payload.reason
    )


@router.delete("/kudos/{kudo_id}")
def delete_kudo_endpoint(
    kudo_id: str = Path(..., description="Unique ID of the kudo to permanently delete"),
    payload: Optional[DeleteKudoRequest] = Body(None),
    reason: Optional[str] = Query(None, description="Optional fallback query parameter for reason"),
    current_user: Dict[str, Any] = Depends(require_admin)
):
    """
    Permanently deletes a kudo while retaining the immutable audit record (BR-09).
    Requires administrator privileges.
    """
    delete_reason = ""
    if payload and payload.reason:
        delete_reason = payload.reason
    elif reason:
        delete_reason = reason

    return delete_kudo(
        kudo_id=kudo_id,
        admin_user=current_user,
        reason=delete_reason
    )


@router.get("/kudos/{kudo_id}/audit")
def get_audit_trail_endpoint(
    kudo_id: str = Path(..., description="Unique ID of the kudo whose audit trail to fetch"),
    current_user: Dict[str, Any] = Depends(require_admin)
):
    """
    Retrieves the complete immutable audit trail for a specific kudo.
    Requires administrator privileges.
    """
    return get_kudo_audit(
        kudo_id=kudo_id,
        admin_user=current_user
    )
