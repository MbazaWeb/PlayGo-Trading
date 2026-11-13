"""Single-company governance. Staff are operators, never account owners."""
from typing import Any

COMPANY_ID = "PLAYGO_TANZANIA_LIMITED"
ROLES = ("OWNER", "TRADER", "ACCOUNTANT", "AUDITOR")
PERMISSIONS = {
    "OWNER": frozenset(("read", "trade", "accounting", "staff")),
    "TRADER": frozenset(("read", "trade")),
    "ACCOUNTANT": frozenset(("read", "accounting")),
    "AUDITOR": frozenset(("read",)),
}


class CompanyAccessError(PermissionError):
    pass


def staff_context(user: dict[str, Any]) -> dict[str, str]:
    if user.get("disabled") or user.get("company_id") != COMPANY_ID:
        raise CompanyAccessError("Not an active PlayGo company operator")
    role = user.get("role")
    if role not in ROLES:
        raise CompanyAccessError("Unrecognized staff role")
    return {"staff_id": user["_id"], "company_id": COMPANY_ID, "role": role}


def require_permission(user: dict[str, Any], permission: str) -> dict[str, str]:
    context = staff_context(user)
    if permission not in PERMISSIONS[context["role"]]:
        raise CompanyAccessError("Insufficient company permissions")
    return context


def migration_preview(legacy_state: dict[str, Any],
                      account: dict[str, Any] | None,
                      journal_count: int) -> dict[str, Any]:
    """Read-only migration assessment; never copies or rewrites financial data."""
    return {
        "company_id": COMPANY_ID,
        "ownership": "SINGLE_COMPANY",
        "legacy_revision": legacy_state.get("revision"),
        "legacy_balance": legacy_state.get("balance"),
        "legacy_trade_count": len(legacy_state.get("trades", [])),
        "legacy_open_position_count": len(legacy_state.get("positions", [])),
        "accounting_revision": account.get("revision") if account else None,
        "accounting_journal_count": journal_count,
        "safe_to_auto_migrate": False,
        "blockers": [
            "Existing paper trading state and accounting ledger require reconciliation",
            "Opening capital and historical P&L require explicit accounting review",
            "All trading and accounting writes must be staff-authorized before cutover",
            "No automatic balance copy, duplicate ledger creation, or broker execution",
        ],
    }
