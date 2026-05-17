# Wave 5 Audit P — WebSocket Implementation Deep-Dive

Reviewed at commit `0a3fb23580b3497c1e004d1b79f783b2dda38e24` against the v1.1.0 release.

## Summary

The WebSocket layer is well-structured: connection / subscription / dispatch /
sequence / orderbook concerns are cleanly separated, the durable `client_id`
abstraction over server `sid` is the right idea, and the public API
(`subscribe_*`, `on(...)`, `orderbook(...)`) is ergonomic. There is decent
unit-level coverage of each module and one integration suite against a fake
server.

Concurrency safety is **partly there but not robust**. The main hot paths
(`_recv_loop` → dispatcher → queue) are single-task and therefore mostly safe,
but several real-world scenarios break the invariants the code assumes:
sid-remapping on reconnect can mis-route messages that are in flight, the
sequence tracker leaks state across reconnects and across sid reassignment,
DROP_OLDEST and ERROR overflow have a hole that lets sequence detection
silently drift, and the `on()` decorator-vs-iterator contract is undefined
for the same channel.

The most material findings are concentrated around reconnect: subscribe
races during a recv-loop reconnect, dropped messages skipping `last_seq`
update, and `resubscribe_all` aborting on the first failure leaving the
sub_mgr in an inconsistent state.

## Findings

### F-P-01 — `resubscribe_all` aborts on first failure, partially-resubscribed sub_mgr (severity: high)
**File:** `kalshi/ws/channels.py:199-228`
**Scenario:** Server reconnect succeeds, then resubscribe of (say) `ticker`
succeeds, then the server returns `error` for the next `subscribe` (e.g. the
private channel is rate-limited mid-reconnect, or `_wait_for_response` times
out on one ack).
**Impact:** `resubscribe_all` raises out of `_recv_loop`'s reconnect
`try` block. The except handler at `client.py:197-203` treats it like
"reconnect failed" — pushes sentinels to *all* queues and exits the loop —
even though the actual socket is up and some subs are healthy. From the
caller's perspective every iterator terminates and they get no error, only
the silent end-of-iteration.
Worse, `self._subscriptions` is left half-mutated: `sub.server_sid` has been
cleared to `None` on every subscription before the loop even starts iterating
(line 209), so successfully-resubscribed entries are fine, but the failing
entry has `server_sid=None` while the iterator is still presumed alive. A
subsequent `unsubscribe(client_id)` will return early at line 155.
**Evidence:**
```python
# channels.py:208-228
for client_id, sub in old_subs.items():
    sub.server_sid = None  # Clear old sid
    ...
    data = await self._wait_for_response(msg_id)  # ← can raise
    new_sid = data.get("msg", {}).get("sid")
    if new_sid is not None:
        sub.server_sid = new_sid
        self._sid_to_client[new_sid] = client_id
```
The `_wait_for_response` helper raises `KalshiSubscriptionError` on timeout
or error response. No try/except, no partial-state cleanup.
**Suggested fix:** Wrap each subscription's resubscribe in its own
try/except. On per-sub failure, log + push a sentinel to that one queue and
remove it from `_subscriptions`, but continue resubscribing the rest.
Optionally surface a structured event via `on_error`. Always restore an
invariant: `sub.server_sid is None` ↔ `client_id not in _subscriptions`.

### F-P-02 — Dropped messages still update `last_seq`, but ERROR-overflow drops do not (severity: high)
**File:** `kalshi/ws/client.py:142-179` + `kalshi/ws/backpressure.py:45-58`
**Scenario:** Slow consumer on `orderbook_delta` (`ERROR` overflow). Queue
fills, `MessageQueue.put` raises `KalshiBackpressureError`. `_recv_loop`
catches it at line 204-207 as a generic `Exception`, logs, and continues.
**Impact:** The sequence tracker has already incremented `last_seq` for that
message at line 161-163 (it ran before dispatch). The orderbook manager has
**already applied** the delta to the local book at line 173-175. The
consumer's iterator missed the message entirely. The user sees:
1. Their book is silently more up-to-date than the messages they consumed.
2. No gap is detected on the next message — `last_seq` already advanced.
3. The docs say `ERROR` overflow prevents corruption, but the local book
   built via `orderbook(ticker)` *is* corrupted from the consumer's
   perspective (mutations they never observed).
And in the `DROP_OLDEST` ticker case, the dropped frame's `last_seq` was
likewise advanced — fine for ticker since it's not sequenced, but the same
code path would silently drift if a sequenced channel ever runs DROP_OLDEST
(which docs do say "don't do unless you know"). The drift detection
documentation claim that "missed delta is exactly what sequence-gap detection
catches" is **not true** for the ERROR-overflow path.
**Evidence:** `_recv_loop` at `client.py:142-179` does seq-track + apply
orderbook **before** the dispatcher routes to the queue. By the time the
queue raises, both side-effects are committed. The catch at line 204-207
swallows it.
**Suggested fix:** Either (a) move seq tracking + orderbook apply *after*
dispatch succeeds, so a backpressure error rolls back the implicit state, or
(b) on `KalshiBackpressureError` for an orderbook subscription, treat it like
a gap: clear the local book and reset the seq tracker for that sid so the
next snapshot rebootstraps.

### F-P-03 — Reconnect: messages arriving on old `sid`s during sid-remap are silently dropped or mis-routed (severity: high)
**File:** `kalshi/ws/channels.py:205-228` and `kalshi/ws/client.py:188-196`
**Scenario:** Server reissues a stale or recycled `sid`. Suppose
pre-reconnect there were two subs: ticker on sid=1, orderbook on sid=2.
After reconnect the server happens to assign sid=1 to the orderbook channel
(server-side recycling). During `resubscribe_all`, the iteration order over
`old_subs.items()` is dict insertion order; ticker is processed first,
acquires sid=1 (or any new sid). Mid-loop, if any `orderbook_snapshot` or
`orderbook_delta` arrives for the freshly-assigned ticker sid=1 but is
processed *while* the loop is still mid-iteration, it will be routed to the
ticker subscription queue.
**Impact:** Mis-routed messages: an `orderbook_snapshot` lands in a ticker
iterator that will `model_validate` it as a `TickerMessage` and fail (caught
silently by dispatch.py:91-95) — message lost. Even worse, after reconnect
some pre-reconnect snapshot messages may still be flushed by the server with
the *old* sid; those will hit the new mapping and get mis-routed silently.
Note `recv_loop` is paused only during one `subscribe()` call (in
`_do_subscribe`); during `resubscribe_all` the connection is in active recv
state.

Also: `resubscribe_all` is called *from* `_recv_loop` (client.py:195) without
the `_subscribe_lock`, but at the same time **any user-level
`subscribe_*` call** can hold that lock and try to drive the connection. The
resubscribe path and a concurrent user subscribe interleave their `send`s
and their `wait_for_response` consumers (both reading from the same
`connection.recv()`).
**Evidence:**
```python
# client.py:189-196 (in _recv_loop, NO lock held)
await self._connection.reconnect()
if self._sub_mgr:
    ...
    await self._sub_mgr.resubscribe_all()
```
```python
# client.py:241-249 (user-facing subscribe path)
async with self._subscribe_lock:
    await self._pause_recv_loop()
    try:
        sub = await self._sub_mgr.subscribe(...)
```
**Suggested fix:** Acquire `_subscribe_lock` in the reconnect path before
calling `resubscribe_all`. Clear `_sid_to_client` *before* sending any
resubscribe so any stale message arriving on an old sid hits
`get_subscription_by_sid → None` and is dropped instead of mis-routed
(currently done at line 206 ✓, but the new-mapping window still overlaps
with delivery from in-flight messages on the new socket). Consider draining
any frame in the recv buffer that has a sid not in the just-built mapping.

### F-P-04 — `_pause_recv_loop` races: messages received but not dispatched are lost (severity: high)
**File:** `kalshi/ws/client.py:129-135` + `137-179`
**Scenario:** `_recv_loop` is mid-iteration, has just `await
self._connection.recv()` returned a frame `raw` and is now in the JSON-parse
/ seq-track / orderbook block. A user calls `subscribe_*`. `_pause_recv_loop`
cancels the task. The cancel hits while we're between `recv()` and
`dispatcher.dispatch(raw)` — possibly while we're awaiting the `seq_tracker.track()`
call (which can await `on_gap` callback).
**Impact:** The frame held in `raw` is silently dropped. For
`orderbook_delta` this is a missed delta; the next frame on the same sid
will be `last_seq + 2` and trigger gap detection — so we **resync**, which
is graceful, but for a `ticker` or `fill` channel the message just vanishes
with no signal.
Worse, if cancellation happens *after* seq-track succeeded (advanced
`last_seq`) but before dispatch, the missed delta will never be re-counted
on the next frame — `last_seq` is set to e.g. 5, next frame is 6, no gap
detected, but the consumer never saw seq=5.
**Evidence:** The recv loop catches `asyncio.CancelledError` at line 181-182
with `break` — no attempt to dispatch the in-flight frame before exiting. The
`_pause_recv_loop` is called on every user-facing subscribe (line 242).
**Suggested fix:** Pause the recv loop via a flag + asyncio.Event rather
than cancellation. Or: cancel only if no frame is in-flight (track a
"processing" flag and wait for it to clear). The current approach assumes
cancel during `connection.recv()` (idle wait) is safe; it is, but
`_pause_recv_loop` doesn't enforce that timing.

### F-P-05 — Reconnect drops authentic-but-mid-flight ack frames, deadlocking subscribe (severity: high)
**File:** `kalshi/ws/channels.py:73-101` + `kalshi/ws/client.py:241-249`
**Scenario:** User calls `subscribe_ticker`. `_do_subscribe` pauses the recv
loop, sends the subscribe command, and starts `_wait_for_response(msg_id,
timeout=5.0)` reading frames from `connection.recv()`. The server connection
dies mid-subscribe (network blip). `connection.recv()` raises
`ConnectionClosed`.
**Impact:** `_wait_for_response` does not catch `ConnectionClosed`. It
propagates out of `subscribe()`, out of `_do_subscribe`, and up to the user
as an unhandled `websockets.ConnectionClosed` (not a `KalshiConnectionError`).
The subscription is not in `_subscriptions` (we never reached the assignment
at line 143). The recv loop is still cancelled (paused). The `finally`
restarts the recv loop at line 249, which will then see the closed
connection on its first `recv()` and trigger reconnect → resubscribe_all,
but the user's original subscribe call has already errored. The user retries
and the second subscribe succeeds, but the *first* attempt's sub is lost.
**Evidence:** `_wait_for_response` has no try/except for `ConnectionClosed`;
neither does `_do_subscribe`. The 5s `timeout` is the only escape, which is
fine for "server is slow" but not for "server is gone".
**Suggested fix:** Wrap the subscribe-and-await in `_do_subscribe` with a
catch for `ConnectionClosed` → wait for reconnect to land (via
state-change) then retry, or surface as `KalshiConnectionError` so the user
can retry deterministically.

### F-P-06 — Auth re-signing on reconnect uses fresh timestamp ✓ (severity: low — confirm)
**File:** `kalshi/ws/connection.py:122-172`
**Scenario:** Reconnect after token-ish auth expiry.
**Impact:** Each reconnect calls `_build_auth_headers()` (line 156) which
calls `self._auth.sign_request(...)` fresh — so a new timestamp/signature is
generated per attempt. **Good**.
**Evidence:** `connection.py:155-163` re-signs on every attempt inside the
retry loop.
**Suggested fix:** None needed; flagging as positive verification because
the audit prompt asked. One adjacent caveat: if the server's clock drifts vs.
client during a long sleep (`retry_max_delay` could be many seconds), and the
RSA-PSS signature is timestamp-bound, the signature timestamp is taken at
sign-time (just before `connect`), so should be safe.

### F-P-07 — `OrderbookDeltaPayload.delta` typed as `FixedPointCount` (string) but used as `Decimal` (severity: medium)
**File:** `kalshi/ws/models/orderbook_delta.py:42-47` + `kalshi/ws/orderbook.py:68-94`
**Scenario:** Any delta application path.
**Impact:** `OrderbookDeltaPayload.delta` is annotated `FixedPointCount` and
`price` is `DollarDecimal`. The orderbook code treats both as `Decimal`
(`new_qty = existing.quantity + delta`, `levels.append(... quantity=delta)`).
This works at runtime because both `DollarDecimal` and `FixedPointCount` are
`Decimal` subtypes via Pydantic custom types. But the test fixture
(`tests/ws/test_orderbook.py:44-55`) constructs `OrderbookDeltaPayload`
directly with `Decimal("10")` — `FixedPointCount` may accept it, but the
field type annotation as documented in the comment is "fixed-point count
string". This is a type-vs-runtime mismatch that could bite a downstream
user typing on the field annotation.
**Evidence:** `kalshi/types.py` defines `FixedPointCount` (need to verify
it's a `Decimal` alias and not a `str` alias). Quick check would resolve
this; if it's a `Decimal` alias, the docstring on `OrderbookDeltaPayload` is
misleading. If it's a `str` alias, the orderbook arithmetic crashes.
**Suggested fix:** Verify `FixedPointCount` is a Decimal-coercing type;
update the docstring on `OrderbookDeltaPayload` to say "parsed as Decimal"
not "fixed-point count string".

### F-P-08 — `unsubscribe` mutates state but doesn't push sentinel; iterator hangs (severity: high)
**File:** `kalshi/ws/channels.py:152-168`
**Scenario:** A caller obtains an iterator from `subscribe_ticker`, then
later calls `sub_mgr.unsubscribe(client_id)` (or — for some reason —
exposes this through a higher-level API in the future). The
`SubscriptionManager` deletes the entry and clears `sid_to_client`. But the
caller's iterator is still awaiting `queue.get()`.
**Impact:** The iterator hangs forever because no sentinel is pushed.
Also: `_recv_loop` will silently drop subsequent messages for the
unsubscribed sid (dispatch.py:104-106 → `Message for unknown sid`). There's
no public unsubscribe today on `KalshiWebSocket`, so user-facing impact is
zero — but the `_stop` path *does* push sentinels (client.py:117-119) and
that's the only graceful-shutdown contract. If any future code calls
`sub_mgr.unsubscribe` while the connection is alive, the iterator on that
sub becomes a zombie.
**Evidence:** `channels.py:152-168` `unsubscribe()` does not push a sentinel
into `sub.queue`.
**Suggested fix:** In `unsubscribe`, after the server ack, call
`await sub.queue.put_sentinel()` before removing the entry. Same for
`update_subscription` when removing markets (`delete_markets`) so the
caller's iterator can know the market is gone.

### F-P-09 — `_handle_seq_gap` clears only the first ticker's orderbook (severity: high)
**File:** `kalshi/ws/client.py:209-223`
**Scenario:** A single `orderbook_delta` subscription with multiple tickers
(e.g. `tickers=["A", "B"]`). The SDK allows this and the server returns one
sid for the multi-ticker sub. A gap is detected on this sid.
**Impact:** Only `tickers[0]` (e.g. `"A"`) is cleared from the orderbook
manager. Ticker `"B"`'s local book is left untouched and now diverges from
server truth. The next snapshot from the server (sent automatically on
resync? Actually — there's no automatic resync logic; the SDK relies on the
**server** to push a fresh snapshot after a gap, which is only guaranteed
on resubscribe). So `B`'s book stays corrupted until reconnect.
**Evidence:**
```python
# client.py:216-223
sub = self._sub_mgr.get_subscription_by_sid(gap.sid)
if sub and sub.channel == "orderbook_delta":
    tickers = sub.params.get("market_tickers", [])
    if tickers and self._orderbook_mgr:
        self._orderbook_mgr.remove(tickers[0])  # ← only first ticker!
```
Worse: even if the SDK iterated all tickers and removed them all, the gap
hits a single sid that covers multiple books, but the gap doesn't tell us
*which* ticker had the missed update. Removing all books is the safe option
but is destructive.
**Suggested fix:** Iterate the full `tickers` list, not just `[0]`. Also
trigger an `update_subscription` with `send_initial_snapshot=True` (or
unsubscribe+resubscribe) so the server pushes fresh snapshots for all
affected books. Without that step, the docs' "next snapshot from the server
re-bootstraps it" is wishful thinking.

### F-P-10 — `OrderbookManager.apply_delta` returns updated book but mutates Pydantic model in place (severity: medium)
**File:** `kalshi/ws/orderbook.py:56-96`
**Scenario:** Any delta application.
**Impact:** `book.yes` and `book.no` are lists on the `Orderbook` Pydantic
model. The code does `levels.pop`, `levels[idx] = ...`, `levels.append`,
`levels.sort` directly on these. If a consumer holds a reference to a
previously-returned `Orderbook` (e.g. snapshot of "state at delta N"), it
sees subsequent mutations leak in. The `_OrderbookIterator.__anext__`
returns `book = self._mgr.get(...)` which is the same shared instance — so
every yielded `Orderbook` is the same object, mutating across iterations.
**Evidence:**
```python
# orderbook.py:72-94
levels = book.yes if side == "yes" else book.no
...
levels.pop(existing_idx)
levels[existing_idx] = OrderbookLevel(...)
levels.append(...)
levels.sort(...)
```
The Pydantic model isn't frozen, so this mutation is allowed.
**Suggested fix:** Either (a) document that `Orderbook` yielded by
`orderbook()` is a live view (not a snapshot) and consumers must deep-copy
if they want to keep history, or (b) construct a fresh `Orderbook(ticker=...,
yes=list(new_yes), no=list(new_no))` per delta. Option (b) is
defensive-coding cost but matches the natural expectation.

### F-P-11 — `on()` decorator + iterator on same channel: iterator silently never receives (severity: medium)
**File:** `kalshi/ws/client.py:384-398` + `kalshi/ws/dispatch.py:108-113`
**Scenario:** User registers `@ws.on("ticker")` AND calls
`await ws.subscribe_ticker(tickers=["T1"])`.
**Impact:** Dispatcher routes every ticker message to the callback (line
109-110) and the iterator's queue stays empty forever. The iterator hangs
on `queue.get()`. The docs do call this out ("Registering a callback for a
channel takes over routing…"), but there's no runtime warning. A user who
adds a callback after-the-fact has their iterator silently stop yielding.
**Evidence:** `dispatch.py:109-113` — the callback branch returns;
`sub.queue.put` is never called.
**Suggested fix:** When `register_callback(channel, ...)` is called and
there exists an active subscription on that channel with a non-empty queue
consumer, log a warning. Or document this as a hard one-or-the-other API.
The current behavior is documented but unsignalled.

### F-P-12 — `_recv_loop` exception handler too broad: all errors are coerced to "log + continue" (severity: medium)
**File:** `kalshi/ws/client.py:204-207`
**Scenario:** A bug in user callback (raises any exception), a bug in
parsing (KeyError on dispatch), a `KalshiBackpressureError`, a
`KalshiSequenceGapError`, or any other unexpected condition.
**Impact:** All are collapsed into a single `logger.warning("Error
processing message: %s", e)` with `continue`. The user has no signal that
their callback crashed (no traceback shown — `logger.warning` doesn't pass
`exc_info=True`). Debugging is painful. A repeating callback bug would log
hundreds of warnings without indicating where it came from. The dispatcher
already swallows parse errors at `dispatch.py:91-95` with
`exc_info=True`, but the recv-loop-level catch hides everything beyond.
**Evidence:**
```python
# client.py:204-207
except Exception as e:
    logger.warning("Error processing message: %s", e)
    continue
```
**Suggested fix:** Add `exc_info=True` to the warning. Better: catch
`KalshiBackpressureError` and `KalshiSequenceGapError` explicitly and let
other exceptions propagate (or treat them as fatal — log error + push
sentinels + break).

### F-P-13 — Error envelope on unrecognized `sid` is dropped silently (severity: medium)
**File:** `kalshi/ws/dispatch.py:76-83`
**Scenario:** Server sends an `error` envelope with a `sid` field pointing
to a sid the client doesn't know (e.g., post-unsubscribe race).
**Impact:** The `on_error` handler is called only if `msg_type == "error"`
at the top of dispatch. But control messages skip the sid-lookup branch
entirely, so `on_error` does fire — good. However, the AsyncAPI spec also
allows server-side `error` messages tied to a specific subscription's sid
(`ErrorPayload` carries `market_ticker` / `market_id` but not sid by
default). If the server sends an error with a sid in the envelope but the
type is something other than `"error"` (e.g. a malformed message), it falls
through to the unknown-type log. The asymmetry between top-level
`type=="error"` (handled) vs. error-as-payload-on-a-channel (ignored) isn't
documented.
**Evidence:** `dispatch.py:79-83` only routes to `on_error` when
`msg_type == "error"`. `dispatch.py:86-95` returns silently on unknown
types.
**Suggested fix:** Log unknown types at WARNING (currently warning ✓), and
document that server-side errors on a channel sid are not routed to
`on_error` — only top-level error envelopes are.

### F-P-14 — `SequenceTracker._last_seq` leaks sids forever (severity: low)
**File:** `kalshi/ws/sequence.py:34, 77-83`
**Scenario:** Long-running session with many sids assigned over time
(reconnects, unsubscribes, re-subscribes — every iteration assigns a fresh
sid because the server uses a monotonic counter, e.g. fake server uses
`_next_sid`).
**Impact:** `_last_seq` grows unbounded. Memory leak. After 24h with many
subscription churns this is non-trivial for high-volume callers. `reset_all`
is called on full reconnect but not on `unsubscribe` (and `unsubscribe`
itself isn't exposed publicly today).
**Evidence:** No call to `seq_tracker.reset(sid)` from `unsubscribe`. The
gap-handler only resets the current sid. `reset_all` is only invoked from
the reconnect branch.
**Suggested fix:** When `SubscriptionManager.unsubscribe` succeeds, call
`self._seq_tracker.reset(server_sid)`. Same when a sid is replaced in
`resubscribe_all` (the old sid's entry is leaked because line 206 clears
`_sid_to_client` but doesn't touch `_seq_tracker._last_seq`).

### F-P-15 — `MessageQueue._buffer` deque has no `maxlen`, defeating its purpose (severity: low)
**File:** `kalshi/ws/backpressure.py:41`
**Scenario:** Cosmetic / defensive code review.
**Impact:** None functionally — the manual `len(self._buffer) >=
self._maxsize` check before append enforces the bound. But
`collections.deque(maxlen=None)` is the same as no maxlen and only obscures
intent. A reader expects `maxlen=self._maxsize` and naturally trusts the
deque to enforce it.
**Evidence:**
```python
self._buffer: collections.deque[T | object] = collections.deque(maxlen=None)
```
**Suggested fix:** Either set `maxlen=self._maxsize + 1` (allow one slot
for sentinel) with explicit drop logic, or drop the `maxlen=None`
declaration. Add a comment explaining why manual bounding is used (to fire
the ERROR overflow before append).

### F-P-16 — `run_forever` returns immediately if no subscribe was made (silent no-op) (severity: low)
**File:** `kalshi/ws/client.py:400-403`
**Scenario:** User registers `@ws.on("ticker")` then `async with ws.connect()`
then immediately `await ws.run_forever()` — without calling `subscribe_*`.
**Impact:** `run_forever` checks `if self._recv_task:` but the recv task is
only started by `_ensure_recv_loop`, which is only called from
`_do_subscribe`. So `_recv_task is None` → `run_forever` returns
immediately. The callback never fires, the user gets no error. The test at
`tests/ws/test_client.py:264-271` even asserts this behavior. This is a
foot-gun: the docs imply "register a callback then `run_forever`" works.
**Evidence:** `client.py:400-403`:
```python
async def run_forever(self) -> None:
    if self._recv_task:
        await self._recv_task
```
**Suggested fix:** `run_forever` should call `_ensure_recv_loop()` itself so
that callback-only consumers don't have to issue a dummy subscribe. Or
document that a callback-only path requires at least one `subscribe_*` call
to drive the recv loop.

---

## Coverage gaps in existing tests

The integration tests cover happy paths. Notably **not** covered:

- Reconnect during an in-flight `subscribe_*` call.
- Multiple sids assigned to the same channel (multi-ticker orderbook_delta).
- Backpressure overflow on a sequenced channel (orderbook_delta + ERROR + slow consumer).
- `resubscribe_all` partial failure.
- Callback exception inside the recv loop.
- `unsubscribe` while iterator is held.
- Reconnect that exceeds `ws_max_retries` mid-stream (sentinel push).

These tests would catch most of F-P-01 through F-P-08 above if added.
