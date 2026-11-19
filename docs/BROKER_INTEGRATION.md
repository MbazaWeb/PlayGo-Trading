# Broker Integration

## Supported brokers

| Broker key | Mode | Status |
|---|---|---|
| `PAPER` | PAPER | Active — synthetic feed, no external connection |
| `DERIV_DEMO` | DEMO | Modeled — requires real Deriv demo account + API client |
| `DERIV_LIVE` | LIVE | Modeled — requires Phase C acceptance + LIVE_AUTHORIZATION |
| `OANDA_PRACTICE` | DEMO | Modeled — requires real OANDA practice account + eligibility check |

## Broker abstraction interface

The `BrokerConnection` model records: broker, mode, status (`DISCONNECTED`/`CONNECTED`/`AUTHORIZED`/`REVOKED`), `accountRef` (non-secret identifier), `permissions` (`READ`/`TRADE`/`WITHDRAW`), and `lastCheckedAt`.

A production broker adapter must implement:

- Authentication (OAuth/token, stored in vault, never DB plaintext)
- Account information (balance, equity, margin)
- Market data (streaming quotes / historical candles)
- Instrument metadata (min/max size, precision, trading hours)
- Order placement (with durable `clientOrderId`)
- Order cancellation
- Order status polling
- Open/closed positions
- Transaction history
- Reconciliation (compare internal vs broker state)
- Connection health + reconnect

## PAPER vs DEMO vs LIVE separation

- **Distinct credentials:** PAPER uses none (synthetic). DEMO and LIVE must use separate broker credentials stored in separate vault paths.
- **Distinct configuration:** `TradingAccount.mode` + `broker` field separate the environments.
- **Execution boundaries:** the risk engine checks `mode === 'LIVE' && !liveAuthorized` and rejects.

## Deriv notes

- Deriv exposes synthetic indices (Volatility 100/75, Boom/Crash) which are reflected in the PAPER instrument universe as clearly-labeled synthetic feeds.
- The user supplied a Deriv app ID (`32hxfkzWYA2IiQoReM03s`) and API token in the development paste. **These must be rotated before live** and stored in a vault, never committed.
- Deriv's API is WebSocket-based; a production adapter should maintain a persistent connection in the worker process (not serverless).

## OANDA notes

- The directive explicitly notes not to assume OANDA is available to the user's jurisdiction.
- OANDA practice account eligibility, instrument availability, API permissions, and regulatory considerations must be verified before integration.
- OANDA's REST API supports practice (fxpractice) and live (fxtrade) endpoints with distinct tokens.

## Reconciliation

`POST /api/broker/connections` records a connection. A production reconciliation job must compare:
- Internal orders vs broker orders
- Internal positions vs broker positions
- Internal balances vs broker balances
- Fees, realized P&L, margin, execution timestamps

Unresolved discrepancies must block new risk-taking orders (per directive §B5). The `Reconciliation` model records daily results with `status` CLEAN/DISCREPANCY/BLOCKED.
