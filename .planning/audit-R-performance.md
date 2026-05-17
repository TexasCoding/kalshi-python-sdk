# Wave 5 Audit R — Performance & Async

Reviewed at commit `0a3fb23580b3497c1e004d1b79f783b2dda38e24` against the v1.1.0 release.

## Summary

The hot path is mostly tight. Sync/async are cleanly split — `time.sleep` only appears in `SyncTransport`, `asyncio.sleep` is used in both `AsyncTransport` and `ConnectionManager.reconnect`. The httpx Client/AsyncClient is constructed once per `KalshiClient` and reused (connection pool persists, no per-request DNS). The dispatcher lookup is `O(1)`. The two clearest wins are: (1) `MessageQueue.qsize()` does an `O(n)` linear scan over the deque on every call (~22 µs at 1000 items — measured); (2) `Page.to_dataframe()` does `model_dump(mode='python')` per row, which is unnecessary churn versus letting pandas/polars read attributes directly. The retry backoff math has one subtle issue: jitter is `random.uniform(0, 0.5)` (fixed magnitude, not proportional), so on the first attempt jitter dominates the base delay. There is also a duplicated `json.loads` in the WS recv loop, and `urlparse(base_url).path` is recomputed on every REST request when it could be cached at transport construction.

## Findings

### F-R-01 — `MessageQueue.qsize()` is O(n) linear scan (severity: medium)
**File:** `kalshi/ws/backpressure.py:80-82`
**Measurement:**
```
qsize() with 1000 items: 22.474 us/call
len(buffer):              0.035 us/call
```
**Impact:** Anyone polling `qsize()` from a monitoring loop or hot consumer pays 22 µs per call at maxsize=1000 — three orders of magnitude more than `len(self._buffer)`. The scan exists only to subtract the sentinel; at most one sentinel ever sits in the deque, and only at shutdown.
**Evidence:** `def qsize(self) -> int: return sum(1 for item in self._buffer if item is not _SENTINEL)`
**Suggested fix:** Track a counter incremented in `put` and decremented in `get`, or just return `len(self._buffer)` and subtract 1 when `self._closed and self._buffer and self._buffer[-1] is _SENTINEL`. Either approach is O(1).

### F-R-02 — `MessageQueue` uses unbounded `deque(maxlen=None)` (severity: low)
**File:** `kalshi/ws/backpressure.py:41`
**Measurement:** qualitative, not benchmarked
**Impact:** The bound is enforced manually in `put()` via `len(self._buffer) >= self._maxsize`, which is fine — but the `deque` is constructed with `maxlen=None`, meaning if any external caller (or future code path) appends past `maxsize` without going through `put()`, the deque will grow unbounded. The whole point of `maxsize` is partially defeated by the choice.
**Evidence:** `self._buffer: collections.deque[T | object] = collections.deque(maxlen=None)`
**Suggested fix:** Use `collections.deque(maxlen=maxsize+1)` (the +1 reserves a slot for the sentinel). When `put()` would overflow, deque's ring-buffer behavior also enforces the cap as a defense-in-depth. Or just keep `maxlen=None` but document that all writes must go through `put()`.

### F-R-03 — REST retry jitter is additive, not proportional (severity: low)
**File:** `kalshi/_base_client.py:73-76`
**Measurement:** qualitative, not benchmarked
**Impact:** `delay = config.retry_base_delay * (2**attempt) + random.uniform(0, 0.5)` adds a fixed-magnitude jitter regardless of the current backoff. At `retry_base_delay=0.5` and attempt 0 this gives a delay in `[0.5, 1.0]` — jitter is up to 100% of base. At attempt 5 (delay=16s) jitter is `<3%`. Standard practice (AWS "Full Jitter") is `random.uniform(0, base * 2**attempt)`, which spreads colliding retries evenly. With the current scheme, many clients that all hit a rate limit at the same time will retry within a 500ms window of each other on the first attempt.
**Evidence:** `delay = config.retry_base_delay * (2**attempt) + random.uniform(0, 0.5)`
**Suggested fix:** Replace with `random.uniform(0, config.retry_base_delay * (2**attempt))` (Full Jitter) or `delay/2 + random.uniform(0, delay/2)` (Equal Jitter). Cap with `retry_max_delay` as today.

### F-R-04 — `urlparse(base_url).path` recomputed on every REST request (severity: low)
**File:** `kalshi/_base_client.py:113` and `:226`
**Measurement:**
```
urlparse(base).path: 0.364 us/call
cached attr access:  0.013 us/call
```
**Impact:** ~0.35 µs saved per request. Negligible on its own, but free — the base_url is immutable on `KalshiConfig` (frozen dataclass).
**Evidence:** `sign_path = urlparse(self._config.base_url).path + path`
**Suggested fix:** Cache the parsed path on the transport in `__init__`: `self._base_path = urlparse(config.base_url).path`. Then `sign_path = self._base_path + path`.

### F-R-05 — Async `_list_all` paginates strictly serially (severity: low)
**File:** `kalshi/resources/_base.py:260-291`
**Measurement:** qualitative, not benchmarked
**Impact:** Cursor pagination is inherently sequential (next cursor comes from prior response), so this is not really a defect — but it's worth calling out that `async for x in client.markets.list_all()` does N round-trips of `RTT + parse` in series. For high-page-count endpoints (`/portfolio/fills` with full history), a parallel-prefetch strategy (kick off next page while caller consumes current page items) could overlap network with consumer processing. The current code yields each item, blocks for cursor fetch, yields the next batch.
**Evidence:** `for _ in range(max_pages): page = await self._list(...); for item in page.items: yield item; ...`
**Suggested fix:** Optional `prefetch=True` mode that schedules the next page fetch as an `asyncio.Task` while the consumer iterates the current page. Adds complexity; only worth doing if users report slow `list_all` over async.

### F-R-06 — WS recv loop double-parses every JSON frame (severity: low)
**File:** `kalshi/ws/client.py:144-179` and `kalshi/ws/dispatch.py:70-71`
**Measurement:**
```
json.loads small msg: 0.906 us/call
```
**Impact:** `_recv_loop` calls `json.loads(raw)` to peek `sid`/`seq`/`type`, then passes `raw` (string) to `dispatcher.dispatch()` which calls `json.loads(raw)` *again*. Wasted ~0.9 µs per message — at 10000 msg/s that's ~0.9% of one CPU. Pure savings, no correctness change.
**Evidence:**
- `kalshi/ws/client.py:147` `data = json.loads(raw)`
- `kalshi/ws/dispatch.py:71` `data = json.loads(raw)`
**Suggested fix:** Have `_recv_loop` pass the already-parsed `data` dict to `dispatcher.dispatch()` (rename/overload signature). Or: do the snapshot/delta peek inside the dispatcher so the parse happens once.

### F-R-07 — Orderbook `apply_delta` does linear scan over price levels (severity: medium)
**File:** `kalshi/ws/orderbook.py:74-94`
**Measurement:**
```
apply_delta middle of 99 levels: 1.91 us/call
apply_delta worst case (end):    3.06 us/call
```
**Impact:** Each delta walks the list to find the matching price. For ~100 levels per side, this is fine (~2-3 µs). For a deep book (thousands of levels — possible on certain Kalshi multivariate markets), this becomes O(n) per delta and the `levels.sort()` on insert is O(n log n). At HFT-style update rates this dominates.
**Evidence:**
```python
for i, level in enumerate(levels):
    if level.price == price: ...
# ...
levels.append(...); levels.sort(key=lambda lv: lv.price)
```
**Suggested fix:** Replace the side-as-list-of-levels with a `dict[Decimal, Decimal]` (price → quantity) internally; convert to sorted `OrderbookLevel` list only when returning from `get()`. O(1) update, O(n log n) only on read. Cleaner code too.

### F-R-08 — `Page.to_dataframe()` builds intermediate dicts via `model_dump` (severity: medium)
**File:** `kalshi/models/common.py:43-67`
**Measurement:** qualitative — `Orderbook(180 levels) model_dump python: 28.48 us/call` (measured), per-row cost on a flat `Market` row will be smaller but still ~1-5 µs each
**Impact:** For a 5000-row `Page[Market]` the `[item.model_dump(mode='python') for item in self.items]` list comprehension allocates 5000 dicts (each with full keys), then pandas re-parses them into columnar storage. With pandas `DataFrame.from_records(items, columns=...)` or directly building from `model.__dict__` we'd avoid the dict roundtrip. The same applies to polars.
**Evidence:**
```python
records = [item.model_dump(mode="python") for item in self.items]
return pd.DataFrame(records)
```
**Suggested fix:** For polars: `pl.from_dicts([m.__dict__ for m in self.items])` skips Pydantic's serializer. For pandas: same trick. Need to confirm nested models (e.g. nested settlements) flatten correctly — if not, document the perf tradeoff and ship a `to_dataframe(flatten=False)` knob.

### F-R-09 — `RecordingTransport` re-reads and re-writes the entire fixture file per request (severity: medium)
**File:** `kalshi/testing/_recorder.py:34-44` and `:64-73`
**Measurement:** qualitative, not benchmarked
**Impact:** For each recorded request the transport does `load_pairs` (read + JSON parse of every prior pair) → append → `save_pairs` (re-serialize all pairs, write through `.tmp` rename). With N pairs to a single endpoint this is O(N²) over the recording session — for `/markets` with 1000 sequential calls, the last call re-parses 999 pairs and re-writes them. Recording is offline so this is bounded, but the file-rewrite-per-request pattern is also a hazard for slow disks.
**Evidence:** `pairs = load_pairs(...); pairs.append(...); save_pairs(...)` — load + save on every call.
**Suggested fix:** Hold an in-memory `dict[(method, path), list[pair]]` for the session, flush on `close()` or every N pairs. The docstring already warns "Recordings are expected to run sequentially," so a session-scoped buffer is safe.

### F-R-10 — RSA-PSS signature computed on every retry attempt, even when only sleep changes (severity: low)
**File:** `kalshi/_base_client.py:117, 230`
**Measurement:**
```
RSA-PSS sign: 0.786 ms/op
```
**Impact:** ~0.8 ms per request for signing — that's the dominant non-network cost in the SDK. The retry loop *intentionally* re-signs each attempt (timestamp changes, prevents replay rejection), so this is correct, not a bug. But on a 5-attempt retry storm (3 retries + 2 burst), 4 ms is spent re-signing; on async this is sync-blocking the event loop (the `cryptography` library releases the GIL but still blocks the calling coroutine).
**Evidence:** `auth_headers = self._auth.sign_request(method.upper(), sign_path) if self._auth else {}` — inside the retry `for` loop.
**Suggested fix:** Document, don't change. Optionally: in `AsyncTransport`, run `sign_request` via `loop.run_in_executor(None, ...)` to keep the event loop responsive when many concurrent requests are signing simultaneously. Only worth it for high-fanout async workloads.

### F-R-11 — `model_dump(mode='json')` vs `mode='python'` for request bodies is a wash (severity: low)
**File:** `kalshi/resources/orders.py:102, 116, 136, 181, 207` (and similar across all resources)
**Measurement:**
```
mode=json:   0.87 us
mode=python: 0.86 us
ratio: 1.01x
```
**Impact:** No measurable difference. The audit prompt suggested this might be a `2-5x` win — measurement says no, at least for `CreateOrderRequest`. The reason is that pydantic v2's Rust core does both modes equivalently fast when fields are plain strings/ints; the `mode='json'` only matters when a serializer differs between Python and JSON (e.g. `datetime` → ISO string). Since httpx accepts the dict and re-serializes to JSON itself, `mode='json'` here is essentially redundant but harmless.
**Evidence:** see benchmark output above
**Suggested fix:** None — keep `mode='json'` for explicit clarity (DollarDecimal serializes to string in both modes via `PlainSerializer`, which httpx needs).

### F-R-12 — `Order.model_validate` is the per-response hot path; ~3 µs per row (severity: low)
**File:** `kalshi/resources/_base.py:143, 256` (list paths), `kalshi/resources/orders.py:356, 681` (single)
**Measurement:**
```
Order.model_validate:      3.24 us/call
Order.model_validate_json: 3.75 us/call
```
**Impact:** On a 1000-order `list_all` paginate, validation costs ~3.2 ms. `model_validate_json` (which would let pydantic-core parse JSON directly from bytes, skipping the intermediate `dict`) is actually slightly slower here because httpx already gave us a parsed dict. The current ordering — `response.json()` → `model.model_validate(...)` — is correct.
**Evidence:** see benchmark output above
**Suggested fix:** None. If we wanted to squeeze more, we'd thread raw bytes from httpx straight into `model_validate_json` and skip httpx's parse. Not worth the API contortion.

### F-R-13 — `SubscriptionManager._wait_for_response` busy-waits inside `asyncio.wait_for` for non-matching frames (severity: low)
**File:** `kalshi/ws/channels.py:73-101`
**Measurement:** qualitative, not benchmarked
**Impact:** During subscribe, frames that arrive before the subscribe-ack (data frames already in-flight on the wire) are read, parsed, and *discarded*. If a subscribe is issued on a busy channel that's already streaming under a different sid, this can drop many real messages. The recv-loop pause logic in `_do_subscribe` is supposed to prevent this race for the *current* connection, but on `resubscribe_all` after reconnect, the server may already be pushing data for newly-resubscribed channels before we've read all the acks.
**Evidence:** `logger.debug("Discarding non-matching frame during subscribe: type=%s", data.get("type"))`
**Suggested fix:** If `data.get("type")` is a data message (not error/subscribed/ok), route it through the dispatcher rather than discard. Requires `_wait_for_response` to hold a reference to the dispatcher (cycle risk) — alternatively, push such frames onto a "stash" queue that the recv loop drains when it resumes. Correctness/perf tradeoff; current behavior may lose ordered messages on resubscribe.

### F-R-14 — `SequenceTracker._last_seq` grows unbounded across reconnects (severity: low)
**File:** `kalshi/ws/sequence.py:34, 41-75`
**Measurement:** qualitative, not benchmarked
**Impact:** `reset_all()` is called on reconnect, which clears the dict — so in practice this is bounded by active subscription count. Verified clean. Including as a "checked and OK" so a future reader doesn't worry.
**Evidence:** `self._last_seq: dict[int, int] = {}` cleared via `reset_all()` in `_recv_loop` reconnect branch.
**Suggested fix:** None.

### F-R-15 — httpx clients are constructed once per `KalshiClient`, no pool tuning (severity: low)
**File:** `kalshi/_base_client.py:91-96, 202-207`
**Measurement:** qualitative, not benchmarked — verified by code read
**Impact:** httpx defaults to 100 max connections, 20 keepalive, no HTTP/2. For a single-client app this is fine. For users doing burst-fanout (e.g. fetching 50 markets in parallel via `asyncio.gather`), 20 keepalive may force connection churn. Also: `http2=True` would let httpx multiplex requests on a single TCP/TLS connection to `api.elections.kalshi.com`, cutting handshake cost — but it also requires `h2` as an install extra and Kalshi's edge needs to support HTTP/2 (very likely, but unverified).
**Evidence:** `httpx.Client(base_url=..., timeout=..., headers=..., transport=...)` — no `limits=` or `http2=` argument.
**Suggested fix:** Expose `KalshiConfig.http2: bool = False` and `KalshiConfig.limits: httpx.Limits | None = None`. Default off for compat; power users can opt in. Document in the config docstring.
