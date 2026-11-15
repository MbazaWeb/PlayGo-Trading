"""Pure, database-independent rules for PlayGo paper-only double-entry accounting."""
from typing import Any

ACCOUNT_ID = "paper-usd-ledger-v1"
ACCOUNTS = ("CASH", "CONTRIBUTED_CAPITAL", "REALIZED_PNL", "FEES", "WITHDRAWALS")
KINDS = ("CAPITAL_IN", "WITHDRAWAL", "REALIZED_GAIN", "REALIZED_LOSS", "FEE", "REVERSAL")
NORMAL = {"CASH": 1, "CONTRIBUTED_CAPITAL": -1, "REALIZED_PNL": -1,
          "FEES": 1, "WITHDRAWALS": 1}


class LedgerConflict(ValueError):
    pass


class InsufficientFunds(ValueError):
    pass


def opening_account() -> dict[str, Any]:
    return {"_id": ACCOUNT_ID, "mode": "PAPER", "currency": "USD",
            "revision": 0, "balances": {account: 0 for account in ACCOUNTS}}


def journal_lines(kind: str, amount_cents: int) -> list[dict[str, Any]]:
    if kind not in KINDS:
        raise ValueError("Unsupported journal kind")
    if type(amount_cents) is not int or amount_cents <= 0 or amount_cents > 10**12:
        raise ValueError("Amount must be positive integer cents within permitted bounds")
    if kind == "REVERSAL":
        raise ValueError("Reversal lines must reference an existing journal")
    mapping = {
        "CAPITAL_IN": ("CASH", "CONTRIBUTED_CAPITAL"),
        "WITHDRAWAL": ("WITHDRAWALS", "CASH"),
        "REALIZED_GAIN": ("CASH", "REALIZED_PNL"),
        "REALIZED_LOSS": ("REALIZED_PNL", "CASH"),
        "FEE": ("FEES", "CASH"),
    }
    debit, credit = mapping[kind]
    return [{"account": debit, "debit_cents": amount_cents, "credit_cents": 0},
            {"account": credit, "debit_cents": 0, "credit_cents": amount_cents}]


def apply_lines(balances: dict[str, int], lines: list[dict[str, Any]]) -> dict[str, int]:
    if sum(x["debit_cents"] for x in lines) != sum(x["credit_cents"] for x in lines):
        raise ValueError("Unbalanced journal")
    updated = dict(balances)
    for line in lines:
        name = line["account"]
        if name not in NORMAL:
            raise ValueError("Unknown ledger account")
        updated[name] += NORMAL[name] * (line["debit_cents"] - line["credit_cents"])
    if updated["CASH"] < 0:
        raise InsufficientFunds("Insufficient virtual cash")
    return updated

