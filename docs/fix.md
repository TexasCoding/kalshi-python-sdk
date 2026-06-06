# FIX protocol

The SDK ships a hand-rolled, **async-first** FIX engine (FIXT.1.1 transport /
FIX50SP2 application layer) for both Kalshi products — the prediction
(event-contract) exchange and the perps (margin) exchange. It speaks Kalshi's FIX
dialect directly: tag=value framing, typed Pydantic message models, an
RSA-PSS logon, and a session state machine with heartbeats, sequence tracking,
and automatic reconnect.

Use FIX when you want a persistent, low-latency session for order entry, fills,
market data, or settlement. For everything else — most REST endpoints, ad-hoc
queries — the [REST client](getting-started.md) is simpler; for streaming public
data without a FIX session, see [WebSocket](websockets.md).

!!! note "Async only"
    The FIX engine is built on `asyncio`; every session is an async context
    manager. There is no sync facade.

## Import

The two client entry points are re-exported from the top-level package; the
message models, enums, errors, and helpers live in `kalshi.fix`:

```python
from kalshi import FixClient, MarginFixClient, FixConfig, FixEnvironment, FixSessionType
from kalshi.fix import NewOrderSingle, ExecutionReport, decode_app_message, Side
```

## Authentication

FIX reuses the same **RSA-PSS** key as the REST client (the signature rides the
logon's `RawData` field). Credentials come from the same environment variables:

- **Prediction** (`FixClient`) — `KALSHI_KEY_ID` + `KALSHI_PRIVATE_KEY` (or
  `KALSHI_PRIVATE_KEY_PATH`). Same key as the REST `KalshiClient`.
- **Margin** (`MarginFixClient`) — the separate `KALSHI_PERPS_*` namespace
  (`KALSHI_PERPS_KEY_ID` + `KALSHI_PERPS_PRIVATE_KEY[_PATH]`).

Both `from_env(...)` constructors accept `password=` (or read
`KALSHI_PRIVATE_KEY_PASSPHRASE`) to decrypt an encrypted key. You can also build a
client from an existing `KalshiAuth` via `from_auth(auth)`.

```python
client = FixClient.from_env(environment=FixEnvironment.DEMO)
# or: FixClient.from_auth(auth, environment=FixEnvironment.DEMO)
```

## Sessions

A FIX connection is a **session** of a specific type. Construct one with a
factory method on the client; it is an async context manager that logs on when
entered and logs out + disconnects when exited.

| Factory | Session (TargetCompID) | Purpose | Prediction | Margin |
|---|---|---|:--:|:--:|
| `order_entry(retransmission=False)` | `KalshiNR` / `KalshiRT` | submit/cancel/amend orders, receive execution reports | ✅ | ✅ |
| `drop_copy()` | `KalshiDC` | replay historical execution reports | ✅ | ✅ |
| `market_data()` | `KalshiMD` | order-book snapshots/updates, security status | ✅ | ✅ |
| `post_trade()` | `KalshiPT` | market-settlement reports | ✅ | — |
| `rfq()` | `KalshiRFQ` | request-for-quote / market making | ✅ | — |

Every factory takes the same callbacks:

- `on_message(raw)` — each inbound **application** message as a raw
  `RawMessage`; decode it with `decode_app_message(raw)`.
- `on_state_change(old, new)` — session-state transitions.
- `on_decode_error(raw, exc)` — *optional*; routes a registered-but-malformed
  inbound message (see [Error handling](#error-handling)).

The engine handles logon/heartbeat/test-request liveness, sequence tracking with
gap-fill/resend (on the retransmission sessions `KalshiRT`/`KalshiPT`), and
AWS-style full-jitter reconnect automatically.

## Sending and receiving

Send a typed message with `session.send(msg)` (returns the assigned
`MsgSeqNum`). Inbound application messages arrive on `on_message` as raw frames;
turn each into its typed model with `decode_app_message`:

```python
import asyncio
from decimal import Decimal
from kalshi import FixClient, FixEnvironment
from kalshi.fix import NewOrderSingle, ExecutionReport, Side, decode_app_message

async def main() -> None:
    async def on_message(raw) -> None:
        msg = decode_app_message(raw)
        if isinstance(msg, ExecutionReport):
            print("exec", msg.cl_ord_id, msg.exec_type, msg.ord_status, msg.avg_px)

    client = FixClient.from_env(environment=FixEnvironment.DEMO)
    async with client.order_entry(on_message=on_message) as session:
        await session.send(
            NewOrderSingle(
                cl_ord_id="my-order-1",
                symbol="KXNBAGAME-26MAY25NYKCLE-NYK",
                side=Side.BUY_YES,
                order_qty=Decimal("10"),
                price=Decimal("0.55"),   # prediction: dollars or integer cents per UseDollars
            )
        )
        await asyncio.sleep(2)  # let execution reports arrive

asyncio.run(main())
```

The typed message families are exported from `kalshi.fix` (and
`kalshi.fix.messages`): order entry (`NewOrderSingle`, `OrderCancelRequest`,
`OrderCancelReplaceRequest`, `OrderMassCancelRequest`, `ExecutionReport`,
`OrderCancelReject`, …), order groups (`OrderGroupRequest`/`OrderGroupResponse`),
market data (`MarketDataRequest`, `MarketDataSnapshotFullRefresh`,
`MarketDataIncrementalRefresh`, `SecurityStatus`, …), RFQ/quoting (`QuoteRequest`,
`Quote`, `AcceptQuote`, `QuoteStatusReport`, …), and settlement
(`MarketSettlementReport`). Code fields on inbound messages are kept as raw
`str`/`int` — compare them against the enums in `kalshi.fix` (`ExecType`,
`OrdStatus`, `Side`, …).

Prices use `Decimal` via `DollarDecimal` end-to-end (no float drift). On
prediction, order prices follow the session's `UseDollars` setting (integer cents
by default, dollars when enabled); on margin they are fixed-point dollars.

## Market data and the order book

`MarketDataRequest` helpers build subscribe/snapshot/unsubscribe requests, and
`FixOrderBook` reconstructs an aggregated book from a `W` snapshot plus `X`
incrementals:

```python
from kalshi.fix import FixOrderBook, MarketDataRequest, decode_app_message

book = FixOrderBook()
async with client.market_data(on_message=lambda raw: book.apply(decode_app_message(raw))) as md:
    await md.send(MarketDataRequest.subscribe(["KXNBAGAME-26MAY25NYKCLE-NYK"]))
    ...
    view = book.get("KXNBAGAME-26MAY25NYKCLE-NYK")  # MarketDataBook | None (bids/offers)
```

`KalshiMD` does not support retransmission — a gap tears the session down and the
client reconnects + re-subscribes; call `book.clear()` before re-subscribing.

## Settlement (post-trade)

Settlement reports stream on `KalshiPT` (on by default) and on `KalshiRT` when
opted in via `FixConfig.receive_settlement_reports=True`. Large batches paginate
across fragments correlated by `Symbol`; `SettlementReassembler` accumulates them
into one report:

```python
from kalshi.fix import SettlementReassembler, decode_app_message

reasm = SettlementReassembler()
async def on_message(raw):
    complete = reasm.add(decode_app_message(raw))  # MarketSettlementReport | None until whole
    if complete is not None:
        ...  # complete.parties has every party for the batch

async with client.post_trade(on_message=on_message) as session:
    ...
```

## Error handling

FIX has its own exception family under `kalshi.fix` (all subclass `KalshiFixError`,
which subclasses the SDK-wide `KalshiError`):

| Exception | Raised when |
|---|---|
| `FixConnectionError` | TCP/TLS connect failed or reconnect attempts exhausted |
| `FixLogonError` | the gateway rejected the logon (bad signature, CompID, seq) |
| `FixSequenceError` | an unrecoverable sequence condition (gap on a non-retransmission session) |
| `FixCodecError` | a malformed frame (BodyLength / CheckSum / framing) |
| `FixDecodeError` | a registered message failed schema validation (one off-spec field) |
| `FixRejectError` | the gateway rejected a message we sent (Reject / BusinessMessageReject) |
| `FixSessionError` | a session-level protocol violation or unexpected lifecycle event |

`decode_app_message(raw)` returns `None` for both an unregistered message type
*and* a malformed known message. To distinguish them — so a genuine fill lost to a
single off-spec field is not silently dropped — set `on_decode_error`, which fires
with `(raw, FixDecodeError)` for the malformed case (the raw is still delivered to
`on_message`). `decode_app_message_strict(raw)` is the direct-call equivalent (it
raises `FixDecodeError` instead of returning `None`).

```python
async def on_decode_error(raw, exc):  # dead-letter / alert / halt
    log.error("undecodable %s: %s", exc.msg_type, exc.__cause__)

async with client.order_entry(on_message=handle, on_decode_error=on_decode_error) as s:
    ...
```

## Connectivity & configuration

`FixConfig.prediction(...)` / `FixConfig.margin(...)` resolve the host, port, and
session parameters per environment; pass `config=` to a client to override
defaults (heartbeat interval, connect timeout, retry policy, TLS, etc.). The
gateways require TLS to non-loopback hosts. A `host`/`port` override (e.g. a local
stunnel or a mock) is supported; a non-loopback host outside Kalshi's known FIX
endpoints must be opted into with `allow_unknown_host=True`.

```python
config = FixConfig.prediction(environment=FixEnvironment.DEMO, heartbeat_interval=10)
client = FixClient.from_env(config=config)
```

## Reference

Full public surface (clients, config, sessions, message models, enums, errors,
`FixOrderBook`, `SettlementReassembler`) is exported from `kalshi.fix`; see
[Reference](reference.md#fix-protocol).
