"""
Compatibility wrapper for security helpers.

New location: `backend.core.security`
"""

from backend.core.security import (  # noqa: F401
    create_access_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
