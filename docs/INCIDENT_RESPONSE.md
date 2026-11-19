# Incident Response

## Severity classification

| Severity | Definition | Examples |
|---|---|---|
| CRITICAL | Funds, authorization, order execution, or financial integrity at risk | Unauthorized order placed; ledger out of balance; broker token leaked; LIVE authorization bypassed |
| HIGH | Significant operational impact; likely to become critical if unresolved | Emergency stop fails to block; reconciliation discrepancy unresolved; broker disconnect during open positions |
| MEDIUM | Degraded but contained | Market data stale; single risk check misfiring; UI error |
| LOW | Minor | Cosmetic; non-blocking warning |

CRITICAL and HIGH issues block live readiness until resolved.

## Response procedure

1. **Detect:** monitoring alert, audit-log review, or user report.
2. **Triage:** assign severity; activate the emergency stop if funds/order execution are at risk.
3. **Contain:** block new orders (emergency stop or revoke broker connection); isolate affected account.
4. **Investigate:** pull audit logs, trade events, reconciliation records; identify root cause.
5. **Remediate:** fix the root cause; verify with tests.
6. **Reconcile:** confirm financial records are consistent (trial balance balanced, integrity hashes match).
7. **Postmortem:** document timeline, root cause, remediation, prevention; file in `docs/incidents/`.
8. **Reauthorize:** if LIVE was active, re-authorization requires a new human sign-off.

## Specific playbooks

### Unauthorized order placed (CRITICAL)
1. Activate emergency stop on the account.
2. Revoke the broker connection.
3. Identify the order in the audit log; reverse via an `ADJUSTMENT` journal if it posted.
4. Rotate all credentials.
5. Investigate the authorization path; patch before re-enabling.

### Ledger out of balance (CRITICAL)
1. Stop the trading engine (emergency stop).
2. Run `verifyIntegrity()`; identify mismatched journals.
3. Do NOT mutate existing journals (append-only). Post a corrective `ADJUSTMENT` journal that restores balance, with a clear description and audit entry.
4. Document the root cause (likely a bug in `postTradeSettlement`).

### Broker token leaked (CRITICAL)
1. Revoke the broker connection immediately.
2. Rotate the token at the broker.
3. Rotate any other credentials that may have been co-located.
4. Review audit logs for unauthorized access.

### Reconciliation discrepancy (HIGH)
1. Block new risk-taking orders on the affected account.
2. Compare internal orders/positions/balances vs broker state.
3. Resolve the discrepancy (corrective journal or broker dispute).
4. Do not resume new orders until `Reconciliation.status=CLEAN`.

### Emergency stop fails to block (CRITICAL)
1. Manually revoke the broker connection.
2. Investigate `risk.checkOrderRisk()` and `isEmergencyStopActive()`.
3. Patch and re-test before re-enabling any trading.

## Credential rotation (incident-triggered)

Any credential exposure triggers immediate rotation of: GitHub PAT, Supabase keys, Deriv token, DB token, JWT secret. See `SECURITY_MODEL.md`.
