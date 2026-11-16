"""Phase 7D failure-injection tests for PAPER risk audit.

No database connection is made. The fake transaction rolls back every
mutation on failure and makes no assumptions about a shared TEST account.
"""
from contextlib import contextmanager
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from app import postgres_risk_audit as audit


class FakeDatabase:
    def __init__(self, fail_on=None):
        self.documents = {}
        self.fail_on = fail_on
        self.statements = []

    @contextmanager
    def transaction(self):
        snapshot = deepcopy(self.documents)
        try:
            yield
        except BaseException:
            self.documents = snapshot
            raise

    @contextmanager
    def cursor(self):
        yield FakeCursor(self)


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.row = None

    def execute(self, sql, args=None):
        self.db.statements.append(sql)
        if self.db.fail_on and self.db.fail_on in sql:
            raise OSError("Injected database failure")
        if "insert into playgo_private.documents" in sql:
            import json
            collection, key, body = args
            self.db.documents.setdefault((collection, key), json.loads(body))
        elif "select body from playgo_private.documents" in sql and "for update" in sql:
            collection, key = args
            self.row = (deepcopy(self.db.documents[(collection, key)]),)
        elif "select revision from playgo_private.documents" in sql:
            self.row = (7,)
        elif "update playgo_private.documents" in sql:
            import json
            body, collection, key = args
            self.db.documents[(collection, key)] = json.loads(body)
        else:
            raise AssertionError("Unexpected SQL: " + sql)

    def fetchone(self):
        return self.row


class RiskAuditFailureTests(TestCase):
    def setUp(self):
        self.proposal = {"pair": "EURUSD", "side": "BUY", "units": 1000,
                         "entry_price": "1.085", "stop_loss": "1.080"}
        self.state = {"revision": 7, "positions": [], "balance": 10000,
                      "paused": True}
        self.accounting = {"consistent": True,
                           "balances_cents": {"CASH": 1000000}}
        self.decision = {"mode": "PAPER", "phase": "7D",
                         "execution": "OBSERVATION_ONLY",
                         "eligible": False, "reasons": ["AUTOMATION_DISABLED"]}

    def record(self, db, assessment_id="risk_001"):
        with patch.object(audit.postgres_state, "load",
                          return_value=deepcopy(self.state)), \
             patch.object(audit.postgres_accounting, "reconcile",
                          return_value=deepcopy(self.accounting)), \
             patch.object(audit.postgres_automated_risk, "assess",
                          return_value=deepcopy(self.decision)):
            return audit.record(db, assessment_id=assessment_id,
                                proposal=deepcopy(self.proposal))

    def test_failed_audit_update_rolls_back_pending_record(self):
        db = FakeDatabase(fail_on="update playgo_private.documents")
        with self.assertRaisesRegex(OSError, "Injected"):
            self.record(db)
        self.assertEqual(db.documents, {})

    def test_failed_state_lock_rolls_back_pending_record(self):
        db = FakeDatabase(fail_on="select revision from playgo_private.documents")
        with self.assertRaisesRegex(OSError, "Injected"):
            self.record(db)
        self.assertEqual(db.documents, {})

    def test_successful_record_does_not_modify_paper_state(self):
        db = FakeDatabase()
        before = deepcopy(self.state)
        result = self.record(db)
        self.assertEqual(result["state_revision"], 7)
        self.assertEqual(result["execution"], "OBSERVATION_ONLY")
        self.assertEqual(self.state, before)
        self.assertEqual(len(db.documents), 1)
        self.assertEqual(
            db.documents[(audit.COLLECTION, "risk_001")]["status"], "RECORDED")

    def test_idempotent_retry_does_not_reassess(self):
        db = FakeDatabase()
        first = self.record(db)
        with patch.object(audit.postgres_automated_risk, "assess",
                          side_effect=AssertionError("Must not reassess")):
            self.assertEqual(audit.record(
                db, assessment_id="risk_001", proposal=self.proposal), first)
        self.assertEqual(len(db.documents), 1)

    def test_conflicting_retry_preserves_original_record(self):
        db = FakeDatabase()
        first = self.record(db)
        with self.assertRaises(audit.AuditConflict):
            audit.record(db, assessment_id="risk_001",
                         proposal={**self.proposal, "side": "SELL"})
        self.assertEqual(
            db.documents[(audit.COLLECTION, "risk_001")]["result"], first)


if __name__ == "__main__":
    import unittest
    unittest.main()
