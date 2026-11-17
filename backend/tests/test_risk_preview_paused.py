from copy import deepcopy
from unittest.mock import patch

from app import postgres_automated_risk as risk


def proposal():
    return {
        "pair": "EURUSD",
        "side": "BUY",
        "units": 1000,
        "entry_price": "1.10000",
        "stop_loss": "1.09500",
    }


def state():
    return {
        "paused": True,
        "risk_lock_reason": None,
        "automation_emergency_stop": False,
        "loss_streak": 0,
        "balance": "1000",
        "day_start_balance": "1000",
        "positions": [],
        "last_automated_entry_at": None,
    }


def evaluate_gate(*args, **kwargs):
    return {"reasons": ["AUTOMATION_DISABLED", "ENGINE_PAUSED"]}


def test_paused_engine_calculates_risk_without_mutation():
    original = state()
    before = deepcopy(original)

    with patch.object(risk.controller, "evaluate", evaluate_gate):
        result = risk.assess(
            original, {}, proposal=proposal(),
            automation_enabled=False,
        )

    assert original == before
    assert original["paused"] is True
    assert result["eligible"] is False
    assert "ENGINE_PAUSED" in result["reasons"]
    assert result["assessment"]["notional_usd"] == "1100.00000"
    assert result["assessment"]["risk_usd"] == "5.00000"


def test_invalid_stop_loss_still_rejected():
    invalid = proposal()
    invalid["stop_loss"] = "1.10500"

    with patch.object(risk.controller, "evaluate", evaluate_gate):
        result = risk.assess(
            state(), {}, proposal=invalid,
            automation_enabled=False,
        )

    assert result["eligible"] is False
    assert result["assessment"] is None
    assert "POSITION_RISK_REJECTED" in result["reasons"]


def test_excessive_risk_still_rejected():
    excessive = proposal()
    excessive["stop_loss"] = "1.05000"

    with patch.object(risk.controller, "evaluate", evaluate_gate):
        result = risk.assess(
            state(), {}, proposal=excessive,
            automation_enabled=False,
        )

    assert result["eligible"] is False
    assert result["assessment"] is None
    assert "POSITION_RISK_REJECTED" in result["reasons"]
