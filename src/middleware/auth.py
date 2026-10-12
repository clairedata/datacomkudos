"""
PROJECT: Datacom Kudos System
FILE: src/middleware/auth.py
DESCRIPTION: Role-Based Access Control (RBAC) and Session Context Dependency.
             Resolves user identity from the evaluation header 'X-User-Id',
             validates active status, and enforces administrative privileges.
"""

from typing import Dict, Any, Optional
from fastapi import Header, HTTPException, Depends
from src.services.kudos_service import get_user_by_id


async def get_current_user(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
) -> Dict[str, Any]:
    """
    Dependency: Extracts and authenticates the user from the 'X-User-Id' HTTP header.
    
    Security Context:
    - This mechanism serves as a local evaluation testbed mock (REQ-GAP-01).
    - Checks that the user ID is supplied, exists in the database, and is active.
    
    Raises:
    - HTTP 401 Unauthorized if header is missing, empty, or user not found.
    - HTTP 403 Forbidden if user account is marked inactive (is_active == 0).
    """
    if not x_user_id or not x_user_id.strip():
        raise HTTPException(
            status_code=401,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Missing or empty 'X-User-Id' authentication header."
            }
        )

    user = get_user_by_id(x_user_id.strip())
    if not user:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "UNAUTHORIZED",
                "message": f"User identity '{x_user_id}' does not exist in the system."
            }
        )

    if user.get("is_active") != 1:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "FORBIDDEN",
                "message": "User account is inactive. Access denied."
            }
        )

    return user


async def require_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Dependency: Requires the authenticated user to possess administrator privileges.
    
    Raises:
    - HTTP 403 Forbidden if current_user.role is not 'admin'.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "FORBIDDEN",
                "message": "Administrator privileges required to perform this action."
            }
        )
    return current_user
