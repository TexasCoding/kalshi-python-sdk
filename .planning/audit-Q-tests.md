# Wave 5 Audit Q — Test Coverage Gaps

Reviewed at commit `0a3fb23580b3497c1e004d1b79f783b2dda38e24` against the v1.1.0 release.

## Summary

Surface coverage at 1455 tests is genuinely strong: every public resource has a respx-mocked happy path plus an error path, sync and async transports mirror each other, and the contract/drift infrastructure is itself unit-tested (`tests/test_contract_support.py`). The biggest real gaps are concentrated in three areas. First, the **retry/backoff state machine** has good coverage of "does this status retry?" but no test exercises the safety properties that protect callers when the server misbehaves: `Retry-After` cap to `retry_max_delay`, HTTP-date `Retry-After` fallback, or `httpx.TimeoutException` retry on idempotent methods. Second, **pagination edge cases** miss the `max_pages` safety cap (cursor-loop detection is tested, but the bare numeric cap isn't) and `Page.to_dataframe`/`to_polars` only handle flat models — nested-model and Decimal-column behavior beyond the smoke test is unpinned. Third, **WebSocket** routing has a coverage hole around callback+queue collision on the same channel and "reconnect lost a sid mapping" scenarios beyond the happy resubscribe. Smaller issues: `KalshiConfig` trailing-slash stripping isn't tested, `KalshiConfig.extra_headers` is plumbed but never asserted, the `TypeError` fallback in `_to_decimal_dollars`/`_to_decimal_fp` is unreachable in tests, the recorder's non-JSON `body_kind="text"` branch is unexercised (HTML 502 bodies are the realistic case), and `KalshiAuth.from_key_path`'s `PermissionError` + passphrase-protected `TypeError` branches have no tests.

## Findings

### F-Q-01 — `Retry-After` is not capped to `retry_max_delay` in any test (severity: high)
**Coverage gap:** `_base_client.py:165-166` and `:278-279` apply `min(error.retry_after, config.retry_max_delay)` so a hostile/misconfigured server returning `Retry-After: 86400` cannot park the SDK for a day. `test_429_rate_limit` only asserts that `retry_after == 2.5` survives the error mapper; no test exercises the transport's clamp inside the retry loop.
**Why it matters:** A regression that drops the `min(...)` (or flips `retry_max_delay` argument order) would silently introduce unbounded sleeps in production. The whole point of `retry_max_delay` is to be a server-untrusted ceiling and that property is unverified.
**Affected code:** `kalshi/_base_client.py:163-179` (sync) and `kalshi/_base_client.py:277-292` (async).
**Suggested test(s):** Mock a `429` with `Retry-After: "9999"` and `retry_max_delay=0.05`, then a `200`. Patch `time.sleep`/`asyncio.sleep` with a recording stub. Assert the recorded delay equals `0.05`, not `9999`. Mirror in both sync and async.

### F-Q-02 — HTTP-date `Retry-After` fallback to computed backoff is untested (severity: medium)
**Coverage gap:** `_map_error` catches `ValueError` on `float(retry_after)` and sets `retry_after_val = None` — the comment says "HTTP-date format, fall back to computed backoff." No test passes a date string ("Wed, 21 Oct 2026 07:28:00 GMT") and confirms the SDK still retries via `_compute_backoff` rather than crashing or skipping retry.
**Why it matters:** Most upstream gateways (Cloudflare, AWS ALB) emit HTTP-date Retry-After when stalling, not seconds. A regression that re-raised on `ValueError` would convert every rate-limit retry into a hard failure in front of those gateways.
**Affected code:** `kalshi/_base_client.py:57-66`.
**Suggested test(s):** Mock `429` with `Retry-After: "Wed, 21 Oct 2026 07:28:00 GMT"`. Assert: (a) `_map_error` returns `KalshiRateLimitError` with `retry_after is None`, (b) the transport still retries via exponential backoff and eventually gets the 200.

### F-Q-03 — `httpx.TimeoutException` retry path is unexercised (severity: high)
**Coverage gap:** The transport catches `TimeoutException` separately from `HTTPError` and retries it (only for `RETRYABLE_METHODS`). `_base_client.py:135-142` (sync) and `:248-255` (async) are entirely uncovered. A search for `TimeoutException` in `tests/` finds zero hits.
**Why it matters:** Read timeouts are routine in real usage; the SDK ships a retry behavior for them with no regression test. A refactor that converted the second `except` into `raise` would silently break list/get paths on flaky networks, while POST/DELETE timeouts would suddenly trigger spurious retries (the safety check `method.upper() in RETRYABLE_METHODS` is also untested).
**Affected code:** `kalshi/_base_client.py:135-142`, `:248-255`.
**Suggested test(s):** Use `respx.mock` with `side_effect=httpx.TimeoutException("read timed out")` then a 200 — assert GET retries and succeeds; assert POST raises a wrapped `KalshiError` on the first timeout with `route.call_count == 1`. Mirror sync/async.

### F-Q-04 — `_list_all` `max_pages` safety cap has no regression test (severity: medium)
**Coverage gap:** Cursor-loop detection is well tested (`tests/test_base_helpers.py:135-209`), but `max_pages: int = 1000` is also a safety net for the "server never repeats a cursor but never returns empty either" case — and no test passes a small `max_pages` to confirm the iterator terminates after exactly N pages. Note that `_list_all` is not currently called anywhere with a non-default `max_pages`, so users can't even pass a smaller value externally, but the cap is still load-bearing.
**Why it matters:** If the cursor-loop check is ever bypassed (e.g., server gives `cursor="A1", "A2", "A3", …` forever), only `max_pages` prevents an infinite generator. A refactor turning the `for _ in range(max_pages)` into `while page.cursor` would compile, ship, and hang.
**Affected code:** `kalshi/resources/_base.py:147-185` (sync), `:260-291` (async).
**Suggested test(s):** Mock an endpoint returning a fresh unique cursor on every call (`f"cursor-{counter}"`). Call `_list_all` with `max_pages=3`. Assert exactly 3 requests fired and 3 items yielded (no exception). Mirror sync/async.

### F-Q-05 — `KalshiConfig` trailing-slash stripping is untested (severity: medium)
**Coverage gap:** `KalshiConfig.__post_init__` rstrips trailing slashes from `base_url` and `ws_base_url` — the comment says "trailing slash is stripped automatically … to prevent double-slash in auth signing paths." Auth signing strips trailing slash from the *path* (covered by `test_strips_trailing_slash`), but the config-level normalization that prevents the bug at construction time has no test.
**Why it matters:** A user passing `base_url="https://api.elections.kalshi.com/trade-api/v2/"` would otherwise produce double-slash paths and break RSA signing — exactly the failure mode the post-init is supposed to prevent. If `__post_init__` gets removed during a dataclass refactor, the regression slips through.
**Affected code:** `kalshi/config.py:39-44`.
**Suggested test(s):** Construct `KalshiConfig(base_url="https://x/y/")` and `KalshiConfig(ws_base_url="wss://x/y/")`. Assert both end without `/`. Add a transport-level integration test that constructs with a trailing slash and verifies a signed GET still hits `/y/markets` (no `//markets`).

### F-Q-06 — `KalshiConfig.extra_headers` is plumbed but never asserted (severity: medium)
**Coverage gap:** `KalshiConfig.extra_headers: dict[str, str]` is passed to `httpx.Client(headers=...)` and `httpx.AsyncClient(headers=...)` in `_base_client.py:94` and `:205`. No test verifies that user-supplied extras (e.g., `{"X-Trace-Id": "abc"}`) are actually sent on each request, nor that they don't conflict with the auth headers added per-request.
**Why it matters:** Users who set custom headers for distributed tracing or routing have no regression coverage. A refactor that moved `headers=config.extra_headers` from the client constructor to per-request would silently break them if collision/precedence weren't preserved.
**Affected code:** `kalshi/config.py:35`, `kalshi/_base_client.py:94`, `kalshi/_base_client.py:205`.
**Suggested test(s):** Build a config with `extra_headers={"X-Trace-Id": "trace-1", "User-Agent": "kalshi-sdk/test"}`, fire a respx-mocked GET, and assert both headers were on the wire. Also assert per-request auth headers (`KALSHI-ACCESS-KEY`) are still present (verifies they don't get overwritten).

### F-Q-07 — Callback + queue collision on the SAME channel is untested (severity: medium)
**Coverage gap:** `test_callback_and_iterator_coexist` (`tests/ws/test_integration.py:422`) covers callback-on-channel-A + iterator-on-channel-B, which is the easy case. The interesting case is: register a callback for `"ticker"` AND call `subscribe_ticker()` to get an iterator. Per `dispatch.py:108-113`, the callback wins and the iterator's queue receives nothing — but this isn't documented and isn't tested. Users who do both will silently see empty iterators.
**Why it matters:** This is a real-world footgun. The dispatcher's "check for callback first" routing means a stale registered callback can silently swallow all messages from a later `async for ... in stream` loop. Either the behavior should be tested as intentional, or a warning should fire — neither happens today.
**Affected code:** `kalshi/ws/dispatch.py:108-113`.
**Suggested test(s):** Register a `@session.on("ticker")` callback, then `await session.subscribe_ticker()`. Push a `ticker` frame. Assert the callback received it and the iterator's queue is empty (or, if behavior changes, vice versa). Pin the current routing decision so a refactor doesn't silently flip it.

### F-Q-08 — Recorder's `body_kind="text"` branch is unexercised (severity: medium)
**Coverage gap:** `kalshi/testing/_fixtures.py:62-66` falls back to `body_kind = "text"` when `json.loads` raises (`ValueError`/`UnicodeDecodeError`), which is exactly what happens when a Cloudflare/ALB 502 returns `<html>...</html>`. Tests at `tests/test_mock_transport.py` only ever record JSON bodies (`{"exchange_active": True, ...}` etc.). The build_response path for `body_kind="text"` (`_fixtures.py:91-92`) likewise has zero coverage.
**Why it matters:** Recording a real session against the demo or production API will eventually capture an HTML error page. If the text branch silently corrupts the payload (e.g., latin-1 vs utf-8 mismatch, missing content-type preservation), the recording becomes a landmine that explodes the first time someone replays it. The transport claims to handle this; the tests don't prove it.
**Affected code:** `kalshi/testing/_fixtures.py:58-73` and `:84-99`.
**Suggested test(s):** Wire a `_make_stub_transport` that returns `httpx.Response(502, content=b"<html><body>502 Bad Gateway</body></html>", headers={"content-type": "text/html"})`. Record once, assert the JSON fixture has `"body_kind": "text"` and the body string round-trips. Replay and assert the client surfaces a `KalshiServerError` with the HTML body in the error message.

### F-Q-09 — `KalshiAuth.from_key_path` `PermissionError` branch and passphrase-protected key `TypeError` branch are untested (severity: low)
**Coverage gap:** Two specific exception-handler branches in `auth.py` have no test:
- `auth.py:72-73`: `except PermissionError` when reading a key file the user lacks permission for.
- `auth.py:83-87`: `except TypeError` from `load_pem_private_key` when the key is passphrase-protected (the helpful "remove the passphrase" message).
**Why it matters:** Both are user-facing error messages with operational guidance. A refactor that lost the helpful messaging or re-raised the underlying cryptography error would degrade UX for the very users most likely to hit these paths (locked-down production deployments). Both branches are short and trivially testable.
**Affected code:** `kalshi/auth.py:72-73` (PermissionError); `kalshi/auth.py:83-87` (passphrase TypeError).
**Suggested test(s):** For PermissionError: `chmod 000` a tempfile, attempt `from_key_path`, assert the wrapped `KalshiAuthError` contains "Permission denied". For passphrase: generate an RSA key encrypted with `BestAvailableEncryption(b"pw")`, write to disk, call `from_key_path` / `from_pem`, assert error message includes "Passphrase-protected" and the openssl hint.

### F-Q-10 — `_to_decimal_dollars` / `_to_decimal_fp` `TypeError` fallback is unreachable from tests (severity: low)
**Coverage gap:** `kalshi/types.py:27` raises `TypeError(f"Cannot convert {type(value).__name__} to Decimal")` for unexpected types (e.g., `list`, `dict`, `bool`, `None` when the field isn't `Optional`). Same mirror at `:60` for `FixedPointCount`. Search for that error string in `tests/` returns nothing.
**Why it matters:** Pydantic v2 will usually intercept type mismatches before this validator runs, but a model declared with a `DollarDecimal` field plus an upstream `BeforeValidator` that doesn't strictly type-check could pass a `bool` or `list` through. Without a regression test, the friendly error message could be silently replaced by a less helpful Pydantic stack trace.
**Affected code:** `kalshi/types.py:27`, `:60`.
**Suggested test(s):** Define a tiny test model `class M(BaseModel): x: DollarDecimal` and call `M.model_validate({"x": [1, 2]})`; assert the `ValidationError` wraps `TypeError("Cannot convert list to Decimal")`. Mirror for `FixedPointCount`.

### F-Q-11 — `Page.to_dataframe` / `to_polars` don't pin nested-model serialization behavior (severity: medium)
**Coverage gap:** `test_page_dataframe.py` uses a flat `_Row` (str, Decimal, int). Real SDK pages return models with nested structures: `Market` has `OrderbookLevel` sub-objects when constructed locally; `Candlestick` has nested `OHLCBar`; `Multivariate` results have lists of dicts. `model_dump(mode="python")` on these produces nested dicts in the DataFrame column, which has DataFrame-engine-specific behavior (pandas: object column with dicts; polars: struct column). Neither is asserted.
**Why it matters:** Users who run `client.markets.list().to_dataframe()` and try to query a nested column will hit subtle behavior they need to know about. If a future refactor flips `mode="python"` to `mode="json"`, nested Decimals become strings and silently break `.sum()` on price columns. The smoke tests don't catch this — they assert Decimal stays Decimal, but only for top-level fields.
**Affected code:** `kalshi/models/common.py:43-54`, `:56-67`.
**Suggested test(s):** Add a `_NestedRow(BaseModel)` with a nested `_Inner` BaseModel field plus a `list[Decimal]` field. Assert `to_dataframe()` produces an object-dtype column containing the nested dict (not a string), `to_polars()` produces a struct/list column, and a top-level Decimal column still has Decimal values (not str). This pins the `mode="python"` contract that's only commented today.

### F-Q-12 — `is_authenticated` property is asserted on the transport but not on the client facades (severity: low)
**Coverage gap:** `KalshiClient.is_authenticated` and `AsyncKalshiClient.is_authenticated` are public properties (`client.py:119`, `async_client.py:117`) but no test in `test_client.py`/`test_async_client.py` exercises them. Only `tests/integration/test_client_construction.py` uses them, and those tests skip without live credentials.
**Why it matters:** This is a documented public API surface (used in user code like `if client.is_authenticated: client.orders.list()`). A refactor that lost the property (e.g., during a constructor cleanup) wouldn't fail unit CI; it'd only fail the integration suite that runs nightly.
**Affected code:** `kalshi/client.py:119`, `kalshi/async_client.py:117`.
**Suggested test(s):** In `test_client.py`/`test_async_client.py`: assert `KalshiClient(auth=test_auth).is_authenticated is True` and `KalshiClient().is_authenticated is False`. Mirror for async.

### F-Q-13 — WS timing-dependent assertions use bare `asyncio.sleep` rather than awaiting a deterministic signal (severity: low)
**Coverage gap:** Several WS tests use `await asyncio.sleep(0.1)` / `sleep(0.2)` / `sleep(0.3)` and then assert on a list (e.g., `test_callback_and_iterator_coexist`, `test_on_decorator_registers`, `test_on_error_called`, run_forever tests). On a loaded CI runner with GIL contention, these will be flaky. Counted 7+ instances in `tests/ws/test_client.py` and `tests/ws/test_integration.py`.
**Why it matters:** Slow CI = false-fail. The pattern `sleep then assert` is also pedagogically harmful: it teaches readers that the dispatcher is "eventually consistent" when it's actually deterministic on the recv loop. The fix is to await a deterministic completion event (e.g., an `asyncio.Event` set inside the callback).
**Affected code:** `tests/ws/test_client.py:212, 260, 297`; `tests/ws/test_integration.py:408, 464, 553, 582`.
**Suggested test(s):** Replace the sleep-then-assert pattern with an `asyncio.Event` that the callback `set()`s. `await asyncio.wait_for(event.wait(), timeout=2.0)` instead of `await asyncio.sleep(0.3)`. No flake, faster passes.

### F-Q-14 — Server-initiated unsubscribe (`type: "unsubscribed"`) routing is unverified for sid cleanup (severity: medium)
**Coverage gap:** `dispatch.py:79-83` treats `"unsubscribed"` as a CONTROL_TYPE — it's logged and dropped, but `SubscriptionManager._sid_to_client` is NOT cleaned up when the server unilaterally unsubscribes a sid (e.g., due to an admin action or session expiry). Subsequent messages with that sid will silently hit `get_subscription_by_sid` → returns `None` → dispatcher logs "Message for unknown sid". No test exercises this.
**Why it matters:** This is a slow leak. If the server unilaterally drops 100 subscriptions over a long-running session, `_sid_to_client` keeps growing because only client-initiated `unsubscribe()` calls clean up (`channels.py:163-164`). The user-facing symptom is stale subscriptions sticking around in `active_subscriptions`. Either the dispatcher should reap on server-initiated unsubscribe, or this should be tested as intentional and documented.
**Affected code:** `kalshi/ws/dispatch.py:79-83`; `kalshi/ws/channels.py:230-235`.
**Suggested test(s):** Subscribe to `ticker`, snapshot `active_subscriptions`. Have the fake server send `{"type": "unsubscribed", "msg": {"sid": <sid>}}`. Assert: pin current behavior (subscription stays / leaks) OR assert the manager reaps it. Either way, the test forces a deliberate choice rather than the current silent gap.

### F-Q-15 — Multiple sids for the same channel on the same connection is untested (severity: low)
**Coverage gap:** The audit prompt called this out specifically. The fake WS server (`tests/ws/conftest.py`) appears to assign sequential sids per subscribe call, but no test subscribes to `orderbook_delta` twice for two different ticker lists and verifies that messages for sid=1 vs sid=2 route to distinct queues. `test_two_channels_on_same_connection` covers two *different* channels (ticker + fill), not two subscriptions to the same channel.
**Why it matters:** Real usage: a user wants two orderbook subscriptions sharded by ticker. If `_sid_to_client` somehow collapsed both onto the second client_id (lookup bug, dict overwrite), one of the queues would silently never receive messages. The bug class is "shared map collision" and is exactly the kind of thing a unit test catches.
**Affected code:** `kalshi/ws/channels.py:103-150` (subscribe), `:230-235` (lookup).
**Suggested test(s):** Subscribe twice to `orderbook_delta` (or `ticker`) with different `market_tickers` params. Capture both `sub.server_sid` values, assert they differ. Push two messages with the two sids, read both iterators with `wait_for`, assert each gets exactly its own message.

### F-Q-16 — `_join_tickers` test coverage doesn't pin behavior for non-string elements (severity: low)
**Coverage gap:** `_join_tickers` (`resources/_base.py:47-67`) validates empty and comma-containing strings. No test covers what happens when the caller passes `[1, 2, 3]` (ints) or `[True, "ABC"]` (bool) — the function would either coerce silently or raise a less-helpful error at the `"," in elem` step. The function's type signature is `list[str] | tuple[str, ...] | str | None`, so runtime type abuse is the caller's fault, but the failure mode isn't pinned.
**Why it matters:** Mostly a Python typing-hygiene issue. The current code does no `isinstance(elem, str)` check, so a `bool` element would crash at `"," in True` with a `TypeError: argument of type 'bool' is not iterable`. A `1` element would crash similarly. The error message is unhelpful — fix or pin.
**Affected code:** `kalshi/resources/_base.py:47-67`.
**Suggested test(s):** Either add `isinstance(elem, str)` validation and test it, OR pin the current crash behavior with `pytest.raises(TypeError, match="argument of type 'bool'")` so future readers know it's intentionally a duck-type failure.

### F-Q-17 — `Page` cursor empty-string vs None equivalence is asserted on `has_next`, but not on `_list_all` continuation (severity: low)
**Coverage gap:** `test_has_next_false_empty` (`tests/test_pagination.py:35`) confirms `cursor=""` makes `has_next` False at the model level. But `_list_all` reads `page.cursor` directly: `if not page.cursor: break`. The `_list` factory normalizes cursor via `cursor if cursor else None` (`_base.py:145`). So an empty-string cursor in the response envelope becomes `None`, and `_list_all` terminates. This whole chain works, but no test starts from "server returns `cursor: \"\"`" and verifies `_list_all` stops cleanly after that page. The cursor-loop tests use `cursor: ""` only as the terminator in their HEALTHY case (`test_normal_pagination_does_not_trip`), but they don't explicitly assert "an empty-string cursor must not be treated as a sentinel of 'continue with empty cursor param'".
**Why it matters:** Borderline pinned. If `_list_all` were ever refactored to forward the cursor unconditionally (`current_params["cursor"] = page.cursor` without the `if not page.cursor: break` guard), an empty-string cursor would loop forever, hitting the same first page. Cursor-loop detection would eventually catch it, but only after `max_pages` of "same first page" — wasting bandwidth. A direct test of "cursor: '' → stop" makes the intent explicit.
**Affected code:** `kalshi/resources/_base.py:175-176`, `:282-283`.
**Suggested test(s):** Mock a single-page response with `{"items": [{"id": "a"}], "cursor": ""}` and explicitly assert `route.call_count == 1` after `list(_list_all(...))`. Already similar to existing tests but make the assertion explicit.

### F-Q-18 — `_recv_loop` "reconnect failed" sentinel-broadcast path is untested (severity: medium)
**Coverage gap:** `ws/client.py:197-203`: when `_connection.reconnect()` raises in the recv loop, the code broadcasts a sentinel to every active queue so iterators don't hang forever, then breaks out of the loop. Search for this branch in tests returns nothing — `test_reconnect_max_retries_exceeded` (`tests/ws/test_connection.py:352`) tests the underlying connection manager's failure, but not the higher-level KalshiWebSocket consumer's "iterator gets sentinel and exits cleanly" promise.
**Why it matters:** If reconnect permanently fails (network partition, expired credentials), users running `async for msg in stream:` need the loop to exit, not hang. This is the "don't deadlock the user" property, and it's the kind of thing that breaks silently on refactor. The path also `break`s out of `_recv_loop` — if that `break` were removed, the loop would tight-loop on the dead connection.
**Affected code:** `kalshi/ws/client.py:197-203`.
**Suggested test(s):** Connect via `KalshiWebSocket`, subscribe to ticker, get an iterator. Cause the fake server to close uncleanly (forcing reconnect) AND configure `ws_max_retries=1` with the fake server permanently rejecting. Assert `async for msg in stream:` exits via `StopAsyncIteration` within a bounded timeout rather than hanging.

---

End of audit Q. 18 findings total.
