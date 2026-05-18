# Testing

The SDK ships a record/replay test layer that lets you capture real HTTP
traffic once and serve it from disk forever after — no network, no auth, no
flakiness.

```python
from kalshi.testing import (
    RecordingTransport,
    AsyncRecordingTransport,
    ReplayTransport,
    AsyncReplayTransport,
    FixtureNotFoundError,
)
```

## Record once, replay forever

```python
from pathlib import Path
from kalshi import KalshiClient
from kalshi.testing import RecordingTransport, ReplayTransport

FIXTURES = Path("tests/fixtures/kalshi")

# Record once against demo (or real) API:
def record() -> None:
    with KalshiClient.from_env(transport=RecordingTransport(FIXTURES)) as c:
        c.exchange.status()
        c.markets.list(status="open", limit=5)

# Replay in tests — no network, no auth required:
def test_status_offline() -> None:
    with KalshiClient(transport=ReplayTransport(FIXTURES)) as c:
        assert c.exchange.status().exchange_active
```

Async mirror with `AsyncRecordingTransport` / `AsyncReplayTransport` and
`AsyncKalshiClient`.

## How matching works

Requests are fingerprinted as **HTTP method + URL path + sorted query
parameters**. Two things are deliberately ignored:

- The request body. Two POSTs with different bodies to the same path replay
  the same fixture.
- The `KALSHI-ACCESS-SIGNATURE` and `KALSHI-ACCESS-TIMESTAMP` headers. Your
  replays don't need a valid key; the signature drift between record and
  replay never causes a miss.

## On-disk layout

Each `(method, path)` pair gets one JSON file:

```
fixtures/
  GET_trade-api_v2_exchange_status.json
  GET_trade-api_v2_markets.json
  POST_trade-api_v2_portfolio_orders.json
```

Each file holds a list of `{request, response}` pairs. Replays cycle through
the list in FIFO order; when exhausted, they wrap to the first entry. This
lets you record the same call twice with different responses (e.g.
pre-and-post-order state).

## Re-entering a fixtures dir

Recording into an existing dir **appends** pairs to the right file rather
than overwriting it. If you want a clean re-record, delete the dir first.

## Misses

```python
def test_unknown_endpoint() -> None:
    with KalshiClient(transport=ReplayTransport(FIXTURES)) as c:
        try:
            c.markets.get("UNRECORDED-TICKER")
        except FixtureNotFoundError as e:
            print("missing:", e)
```

`FixtureNotFoundError` (a `LookupError` subclass) signals a request that has
no matching fixture file. Catch it in tests where you expect uncovered paths.

## When to re-record

Re-record after:

- An SDK upgrade that adds new request kwargs or response fields.
- A wire-spec drift (Kalshi adds a field; your fixtures are now stale).
- Any test that fails because the model can no longer parse the recorded body.

The contract-drift tests in CI catch model/spec misalignment; recorded
fixtures are a separate caching layer below that.

## Security

Recorded fixtures contain the **full** response body returned by Kalshi —
balances, positions, order history, anything else the API returns:

!!! danger "Treat fixture directories like secrets unless scrubbed"
    Always add the fixtures directory to `.gitignore` unless you've manually
    scrubbed the JSON. Prefer recording against the demo environment so the
    captured account state isn't real money.

## Mocking with `respx` (alternative)

If you don't want a disk fixture layer, the SDK accepts any
`httpx.BaseTransport`, so `respx.mock` works too:

```python
import respx
from kalshi import KalshiClient

with respx.mock(base_url="https://api.elections.kalshi.com") as router:
    router.get("/trade-api/v2/exchange/status").respond(200, json={"exchange_active": True})
    with KalshiClient(transport=router) as client:
        assert client.exchange.status().exchange_active
```

`kalshi.testing` is the better choice when you want to capture real responses
end-to-end; `respx` is the better choice when you want fully synthetic
responses with no record step.

## Reference

::: kalshi.testing
