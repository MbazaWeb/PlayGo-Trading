"""Unit tests for Phase 7B signal screening. No DB writes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

import postgres_signal_validator as validator
import postgres_state


class SignalValidatorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.state = postgres_state.initial_state()
        self.state["paused"] = False
        self.signal = {
            "signal_id": "sig-1", "pair": "EURUSD", "side": "BUY",
            "confidence": "0.85",
            "timestamp": self.now.isoformat(),
            "stop_loss": "1.0800",
        }

    def check(self, reason):
        result = validator.validate_signal(
            self.signal, self.state, now=self.now)
        self.assertFalse(result["accepted"])
        self.assertIn(reason, result["reasons"])
        self.assertIsNone(result["proposal"])

    def test_valid_signal_is_proposal_only(self):
        before = deepcopy(self.state)
        result = validator.validate_signal(
            self.signal, self.state, now=self.now)
        self.assertTrue(result["accepted"], result["reasons"])
        self.assertEqual(result["execution"], "VALIDATION_ONLY")
        self.assertLessEqual(result["proposal"]["units"], 1000)
        self.assertEqual(self.state, before)

    def test_low_confidence(self):
        self.signal["confidence"] = "0.69"
        self.check("LOW_CONFIDENCE")

    def test_expired(self):
        self.signal["timestamp"] = (
            self.now - timedelta(seconds=301)).isoformat()
        self.check("SIGNAL_EXPIRED_OR_FUTURE")

    def test_future_signal(self):
        self.signal["timestamp"] = (
            self.now + timedelta(seconds=11)).isoformat()
        self.check("SIGNAL_EXPIRED_OR_FUTURE")

    def test_invalid_pair(self):
        self.signal["pair"] = "USDJPY"
        self.check("UNSUPPORTED_SIGNAL")

    def test_risk_lock(self):
        self.state["paused"] = True
        self.check("RISK_REJECTED")

    def test_duplicate_id(self):
        result = validator.validate_signal(
            self.signal, self.state, now=self.now, seen_ids={"sig-1"})
        self.assertIn("DUPLICATE_SIGNAL", result["reasons"])
        self.assertFalse(result["accepted"])

    def test_invalid_timestamp(self):
        self.signal["timestamp"] = "2026-11-15T12:00:00"
        self.check("INVALID_TIMESTAMP")

    def test_wrong_side_stop(self):
        self.signal["stop_loss"] = "1.2000"
        self.check("RISK_REJECTED")


if __name__ == "__main__":
    unittest.main()
