"""Owner-only API authorization for PlayGo's single company account.

Identity routes are intentionally separate. All trading and financial API
routes require a valid OWNER session; bots are internal Python calls, not HTTP
users. This does not grant live trading capability.
"""
from typing import Any
from company import COMPANY_ID, CompanyAccessError, require_permission
from identity import IdentityError, verify_session

PUBLIC = frozenset((
    "/api/health",
    "/api/identity/login",
    "/api/identity/bootstrap-owner",
    "/api/identity/register",
))


def permission_for(path: str, method: str) -> str | None:
    if path in PUBLIC or not path.startswith("/api/"):
        return None
    if method.upper() in ("GET", "HEAD", "OPTIONS"):
        return "read"
    if path.startswith("/api/accounting/"):
        return "accounting"
    if path.startswith("/api/identity/") or path.startswith("/api/company/"):
        return "staff"
    return "trade"


def authorize_owner(*, path: str, method: str, authorization: str,
                    users: Any, sessions: Any) -> dict[str, str] | None:
    permission = permission_for(path, method)
    if permission is None:
        return None
    if users is None or sessions is None:
        raise IdentityError("Owner identity store unavailable")
    owner_id = verify_session(sessions, authorization)
    owner = users.find_one({"_id": owner_id, "company_id": COMPANY_ID, "role": "OWNER"})
    if owner is None:
        raise CompanyAccessError("PlayGo owner not found")
    return require_permission(owner, permission)
