# Unauthenticated Client Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow the Kalshi Python SDK to be used without RSA credentials for public endpoints (markets, events, exchange, historical).

**Architecture:** Make `KalshiAuth` optional throughout the transport chain. When auth is `None`, requests are sent without signing headers. Private resources (orders, portfolio) guard every method with `AuthRequiredError`. Commit order ensures every intermediate commit is correct: transport first, then guards, then constructor opening.

**Tech Stack:** Python 3.12+, httpx, pydantic v2, pytest + respx

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `kalshi/_base_client.py` | Modify | SyncTransport/AsyncTransport accept `auth: KalshiAuth \| None`, add `is_authenticated` property |
| `kalshi/errors.py` | Modify | Add `AuthRequiredError(KalshiAuthError)` |
| `kalshi/resources/_base.py` | Modify | Add `_require_auth()` to SyncResource/AsyncResource |
| `kalshi/resources/orders.py` | Modify | Add `self._require_auth()` guard at top of every method |
| `kalshi/resources/portfolio.py` | Modify | Add `self._require_auth()` guard at top of every method |
| `kalshi/auth.py` | Modify | Add `KalshiAuth.try_from_env()` classmethod |
| `kalshi/client.py` | Modify | Make auth optional in constructor, update `from_env()` |
| `kalshi/async_client.py` | Modify | Same + guard `.ws` property |
| `kalshi/__init__.py` | Modify | Export `AuthRequiredError` |
| `tests/test_client.py` | Modify | Update existing tests, add unauthenticated tests |
| `tests/test_async_client.py` | Modify | Mirror sync tests + WS guard test |
| `tests/test_auth.py` | Modify | Add `try_from_env()` tests |

---

### Task 1: Transport Layer — Optional Auth + is_authenticated

**Files:**
- Modify: `kalshi/_base_client.py:79-92` (SyncTransport)
- Modify: `kalshi/_base_client.py:178-188` (AsyncTransport)
- Test: `tests/test_client.py`
- Test: `tests/test_async_client.py`

- [ ] **Step 1: Write failing tests for transport with auth=None**

Add to `tests/test_client.py` at the end of the file:

```python
class TestSyncTransportUnauthenticated:
    def test_transport_accepts_none_auth(self) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = SyncTransport(None, config)
        assert transport.is_authenticated is False

    def test_transport_is_authenticated_true(self, test_auth: KalshiAuth) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = SyncTransport(test_auth, config)
        assert transport.is_authenticated is True

    @respx.mock
    def test_unauthenticated_request_sends_no_auth_headers(self) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = SyncTransport(None, config)
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        resp = transport.request("GET", "/markets")
        assert resp.status_code == 200
        sent_headers = route.calls[0].request.headers
        assert "KALSHI-ACCESS-KEY" not in sent_headers
        assert "KALSHI-ACCESS-SIGNATURE" not in sent_headers
        assert "KALSHI-ACCESS-TIMESTAMP" not in sent_headers
```

Add to `tests/test_async_client.py` at the end of the file:

```python
class TestAsyncTransportUnauthenticated:
    @pytest.mark.asyncio
    async def test_transport_accepts_none_auth(self) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = AsyncTransport(None, config)
        assert transport.is_authenticated is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_unauthenticated_request_sends_no_auth_headers(self) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = AsyncTransport(None, config)
        route = respx.get("https://test.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json={"markets": []})
        )
        resp = await transport.request("GET", "/markets")
        assert resp.status_code == 200
        sent_headers = route.calls[0].request.headers
        assert "KALSHI-ACCESS-KEY" not in sent_headers
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_client.py::TestSyncTransportUnauthenticated tests/test_async_client.py::TestAsyncTransportUnauthenticated -v`
Expected: FAIL — `TypeError` because `SyncTransport.__init__` requires `KalshiAuth`, not `None`

- [ ] **Step 3: Implement optional auth in SyncTransport**

In `kalshi/_base_client.py`, change `SyncTransport.__init__`:

```python
class SyncTransport:
    """Synchronous HTTP transport using httpx.Client."""

    def __init__(self, auth: KalshiAuth | None, config: KalshiConfig) -> None:
        self._auth = auth
        self._config = config
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
            headers=config.extra_headers,
        )

    @property
    def is_authenticated(self) -> bool:
        """Whether this transport has auth credentials."""
        return self._auth is not None
```

In `SyncTransport.request()`, change the auth header line. Replace:

```python
            auth_headers = self._auth.sign_request(method.upper(), sign_path)
```

With:

```python
            auth_headers = self._auth.sign_request(method.upper(), sign_path) if self._auth else {}
```

- [ ] **Step 4: Implement optional auth in AsyncTransport**

Same changes in `AsyncTransport.__init__`:

```python
    def __init__(self, auth: KalshiAuth | None, config: KalshiConfig) -> None:
        self._auth = auth
        self._config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
            headers=config.extra_headers,
        )

    @property
    def is_authenticated(self) -> bool:
        """Whether this transport has auth credentials."""
        return self._auth is not None
```

In `AsyncTransport.request()`, same change:

```python
            auth_headers = self._auth.sign_request(method.upper(), sign_path) if self._auth else {}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_client.py::TestSyncTransportUnauthenticated tests/test_async_client.py::TestAsyncTransportUnauthenticated -v`
Expected: PASS

- [ ] **Step 6: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All existing tests PASS (authenticated paths unchanged)

- [ ] **Step 7: Run mypy**

Run: `uv run mypy kalshi/`
Expected: PASS with no errors

- [ ] **Step 8: Commit**

```bash
git add kalshi/_base_client.py tests/test_client.py tests/test_async_client.py
git commit -m "feat: make auth optional in SyncTransport/AsyncTransport

Add is_authenticated property. When auth is None, requests are sent
without signing headers. No behavior change for authenticated transports."
```

---

### Task 2: AuthRequiredError + Resource Guards

**Files:**
- Modify: `kalshi/errors.py`
- Modify: `kalshi/resources/_base.py`
- Modify: `kalshi/resources/orders.py`
- Modify: `kalshi/resources/portfolio.py`
- Modify: `kalshi/async_client.py` (`.ws` property guard)
- Modify: `kalshi/__init__.py`
- Test: `tests/test_client.py`
- Test: `tests/test_async_client.py`

- [ ] **Step 1: Write failing test for AuthRequiredError**

Add to `tests/test_client.py`:

```python
from kalshi.errors import AuthRequiredError


class TestAuthRequiredError:
    def test_is_kalshi_auth_error(self) -> None:
        err = AuthRequiredError("auth required")
        assert isinstance(err, KalshiAuthError)
        assert isinstance(err, KalshiError)

    def test_message(self) -> None:
        err = AuthRequiredError("Please provide credentials")
        assert str(err) == "Please provide credentials"
```

Add this import at the top of `tests/test_client.py`:

```python
from kalshi.errors import KalshiError
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_client.py::TestAuthRequiredError -v`
Expected: FAIL — `ImportError: cannot import name 'AuthRequiredError'`

- [ ] **Step 3: Add AuthRequiredError to errors.py**

In `kalshi/errors.py`, add after the `KalshiAuthError` class:

```python
class AuthRequiredError(KalshiAuthError):
    """Raised when an unauthenticated client calls a private endpoint."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "This endpoint requires authentication. "
            "Provide key_id + private_key_path, or use KalshiClient.from_env().",
            status_code=None,
        )
```

- [ ] **Step 4: Export from kalshi/__init__.py**

Add `AuthRequiredError` to the imports and `__all__` in `kalshi/__init__.py`:

```python
from kalshi.errors import (
    AuthRequiredError,
    KalshiAuthError,
    # ... rest unchanged
)

__all__ = [
    "AsyncKalshiClient",
    "AuthRequiredError",
    # ... rest unchanged
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_client.py::TestAuthRequiredError -v`
Expected: PASS

- [ ] **Step 6: Write failing test for _require_auth guard**

Add to `tests/test_client.py`:

```python
class TestUnauthenticatedResourceGuards:
    def test_orders_create_raises_auth_required(self) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = SyncTransport(None, config)
        from kalshi.resources.orders import OrdersResource
        resource = OrdersResource(transport)
        with pytest.raises(AuthRequiredError):
            resource.create(ticker="TEST", side="yes")

    def test_orders_list_raises_auth_required(self) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = SyncTransport(None, config)
        from kalshi.resources.orders import OrdersResource
        resource = OrdersResource(transport)
        with pytest.raises(AuthRequiredError):
            resource.list()

    def test_portfolio_balance_raises_auth_required(self) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = SyncTransport(None, config)
        from kalshi.resources.portfolio import PortfolioResource
        resource = PortfolioResource(transport)
        with pytest.raises(AuthRequiredError):
            resource.balance()

    def test_markets_list_does_not_raise(self) -> None:
        """Public resources should NOT have auth guards."""
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = SyncTransport(None, config)
        from kalshi.resources.markets import MarketsResource
        resource = MarketsResource(transport)
        # Should not raise AuthRequiredError (will fail with network error, not auth)
        with pytest.raises(Exception) as exc_info:
            resource.list()
        assert not isinstance(exc_info.value, AuthRequiredError)
```

Add to `tests/test_async_client.py`:

```python
from kalshi.errors import AuthRequiredError


class TestAsyncUnauthenticatedResourceGuards:
    @pytest.mark.asyncio
    async def test_orders_create_raises_auth_required(self) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = AsyncTransport(None, config)
        from kalshi.resources.orders import AsyncOrdersResource
        resource = AsyncOrdersResource(transport)
        with pytest.raises(AuthRequiredError):
            await resource.create(ticker="TEST", side="yes")

    @pytest.mark.asyncio
    async def test_portfolio_balance_raises_auth_required(self) -> None:
        config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
            max_retries=0,
        )
        transport = AsyncTransport(None, config)
        from kalshi.resources.portfolio import AsyncPortfolioResource
        resource = AsyncPortfolioResource(transport)
        with pytest.raises(AuthRequiredError):
            await resource.balance()

    def test_ws_property_raises_auth_required(self) -> None:
        client = AsyncKalshiClient.__new__(AsyncKalshiClient)
        client._auth = None
        client._config = KalshiConfig(
            base_url="https://test.kalshi.com/trade-api/v2",
            timeout=5.0,
        )
        with pytest.raises(AuthRequiredError):
            _ = client.ws
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `uv run pytest tests/test_client.py::TestUnauthenticatedResourceGuards tests/test_async_client.py::TestAsyncUnauthenticatedResourceGuards -v`
Expected: FAIL — guards don't exist yet

- [ ] **Step 8: Add _require_auth() to resource base classes**

In `kalshi/resources/_base.py`, add the import and method:

```python
from kalshi.errors import AuthRequiredError
```

Add to `SyncResource`:

```python
class SyncResource:
    """Base class for sync resource modules."""

    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def _require_auth(self) -> None:
        """Raise AuthRequiredError if transport has no auth credentials."""
        if not self._transport.is_authenticated:
            raise AuthRequiredError()
```

Add to `AsyncResource`:

```python
class AsyncResource:
    """Base class for async resource modules."""

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    def _require_auth(self) -> None:
        """Raise AuthRequiredError if transport has no auth credentials."""
        if not self._transport.is_authenticated:
            raise AuthRequiredError()
```

- [ ] **Step 9: Add guards to OrdersResource**

In `kalshi/resources/orders.py`, add `self._require_auth()` as the first line in every method of `OrdersResource`:

```python
    def create(self, *, ticker: str, side: str, **kwargs) -> Order:
        self._require_auth()
        # ... rest unchanged

    def get(self, order_id: str) -> Order:
        self._require_auth()
        # ... rest unchanged

    def cancel(self, order_id: str) -> None:
        self._require_auth()
        # ... rest unchanged

    def list(self, *, ticker=None, status=None, limit=None, cursor=None) -> Page[Order]:
        self._require_auth()
        # ... rest unchanged

    def list_all(self, *, ticker=None, status=None, limit=None) -> Iterator[Order]:
        self._require_auth()
        # ... rest unchanged

    def batch_create(self, orders) -> builtins.list[Order]:
        self._require_auth()
        # ... rest unchanged

    def batch_cancel(self, order_ids) -> None:
        self._require_auth()
        # ... rest unchanged

    def fills(self, *, ticker=None, order_id=None, limit=None, cursor=None) -> Page[Fill]:
        self._require_auth()
        # ... rest unchanged

    def fills_all(self, *, ticker=None, order_id=None, limit=None) -> Iterator[Fill]:
        self._require_auth()
        # ... rest unchanged
```

Do the same for every method in `AsyncOrdersResource` (create, get, cancel, list, list_all, batch_create, batch_cancel, fills, fills_all). Note: for async methods, `self._require_auth()` is NOT awaited (it's a sync method).

- [ ] **Step 10: Add guards to PortfolioResource**

In `kalshi/resources/portfolio.py`, add `self._require_auth()` as the first line in every method of `PortfolioResource` (balance, positions, settlements, settlements_all) and `AsyncPortfolioResource` (balance, positions, settlements, settlements_all).

- [ ] **Step 11: Guard the .ws property on AsyncKalshiClient**

In `kalshi/async_client.py`, modify the `.ws` property:

```python
    @property
    def ws(self) -> KalshiWebSocket:
        """WebSocket client for real-time streaming."""
        if self._auth is None:
            from kalshi.errors import AuthRequiredError
            raise AuthRequiredError(
                "WebSocket connections require authentication. "
                "Provide key_id + private_key_path, or use AsyncKalshiClient.from_env()."
            )
        from kalshi.ws.client import KalshiWebSocket as _KalshiWebSocket
        return _KalshiWebSocket(auth=self._auth, config=self._config)
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `uv run pytest tests/test_client.py::TestUnauthenticatedResourceGuards tests/test_async_client.py::TestAsyncUnauthenticatedResourceGuards tests/test_client.py::TestAuthRequiredError -v`
Expected: PASS

- [ ] **Step 13: Run full suite + mypy**

Run: `uv run pytest tests/ -v --tb=short && uv run mypy kalshi/`
Expected: All PASS

- [ ] **Step 14: Commit**

```bash
git add kalshi/errors.py kalshi/resources/_base.py kalshi/resources/orders.py kalshi/resources/portfolio.py kalshi/async_client.py kalshi/__init__.py tests/test_client.py tests/test_async_client.py
git commit -m "feat: add AuthRequiredError and guard private resources

AuthRequiredError extends KalshiAuthError so except KalshiAuthError
catches both server-side 401s and local auth-required errors.
Guards on all OrdersResource, PortfolioResource methods, and .ws property."
```

---

### Task 3: Client Constructor — Auth Optional + try_from_env()

**Files:**
- Modify: `kalshi/auth.py`
- Modify: `kalshi/client.py`
- Modify: `kalshi/async_client.py`
- Test: `tests/test_auth.py`
- Test: `tests/test_client.py`
- Test: `tests/test_async_client.py`

- [ ] **Step 1: Write failing tests for try_from_env()**

Add to `tests/test_auth.py`:

```python
class TestTryFromEnv:
    def test_returns_auth_when_env_vars_set(
        self, monkeypatch: pytest.MonkeyPatch, pem_string: str
    ) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "test-key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        auth = KalshiAuth.try_from_env()
        assert auth is not None
        assert auth.key_id == "test-key"

    def test_returns_none_when_key_id_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KALSHI_KEY_ID", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        auth = KalshiAuth.try_from_env()
        assert auth is None

    def test_returns_none_when_key_id_set_but_no_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("KALSHI_KEY_ID", "test-key")
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        auth = KalshiAuth.try_from_env()
        assert auth is None
```

You need to add the `pem_string` fixture import — it's already available from `conftest.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth.py::TestTryFromEnv -v`
Expected: FAIL — `AttributeError: type object 'KalshiAuth' has no attribute 'try_from_env'`

- [ ] **Step 3: Implement try_from_env()**

In `kalshi/auth.py`, add after the `from_env()` classmethod:

```python
    @classmethod
    def try_from_env(cls) -> KalshiAuth | None:
        """Load auth from environment variables, returning None if not configured.

        Unlike from_env(), this never raises on missing variables.
        Returns None if KALSHI_KEY_ID is not set, or if neither
        KALSHI_PRIVATE_KEY nor KALSHI_PRIVATE_KEY_PATH is set.
        """
        key_id = os.environ.get("KALSHI_KEY_ID")
        if not key_id:
            return None

        pem_string = os.environ.get("KALSHI_PRIVATE_KEY")
        if pem_string:
            return cls.from_pem(key_id, pem_string)

        key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
        if key_path:
            return cls.from_key_path(key_id, key_path)

        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auth.py::TestTryFromEnv -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for unauthenticated client construction**

Add to `tests/test_client.py`, update `TestKalshiClientConstructor`:

```python
class TestKalshiClientUnauthenticated:
    def test_no_auth_constructs(self) -> None:
        client = KalshiClient()
        assert client._auth is None
        client.close()

    def test_demo_no_auth(self) -> None:
        client = KalshiClient(demo=True)
        assert client._auth is None
        assert client._config.base_url == DEMO_BASE_URL
        client.close()

    def test_has_all_resources(self) -> None:
        client = KalshiClient(demo=True)
        assert hasattr(client, "markets")
        assert hasattr(client, "orders")
        assert hasattr(client, "exchange")
        assert hasattr(client, "events")
        assert hasattr(client, "historical")
        assert hasattr(client, "portfolio")
        client.close()

    @respx.mock
    def test_public_endpoint_works(self) -> None:
        respx.get("https://demo-api.kalshi.co/trade-api/v2/exchange/status").mock(
            return_value=httpx.Response(200, json={
                "exchange_active": True,
                "trading_active": True,
            })
        )
        client = KalshiClient(demo=True)
        status = client.exchange.status()
        assert status.exchange_active is True
        client.close()

    def test_private_endpoint_raises(self) -> None:
        client = KalshiClient(demo=True)
        with pytest.raises(AuthRequiredError):
            client.orders.list()
        client.close()
```

Update `TestKalshiClientFromEnv` — change the test that expected a raise:

```python
class TestKalshiClientFromEnvUnauthenticated:
    def test_from_env_no_credentials_returns_unauthenticated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KALSHI_KEY_ID", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.delenv("KALSHI_DEMO", raising=False)
        monkeypatch.delenv("KALSHI_API_BASE_URL", raising=False)
        client = KalshiClient.from_env()
        assert client._auth is None
        client.close()
```

Also update the existing `test_raises_without_auth` in `TestKalshiClientConstructor` — it should now expect success instead of ValueError:

Change this test:
```python
    def test_raises_without_auth(self) -> None:
        with pytest.raises(ValueError, match="Provide auth"):
            KalshiClient()
```

To:
```python
    def test_no_auth_constructs_unauthenticated(self) -> None:
        client = KalshiClient()
        assert client._auth is None
        client.close()
```

- [ ] **Step 6: Write failing async tests**

Add to `tests/test_async_client.py`:

```python
class TestAsyncKalshiClientUnauthenticated:
    def test_no_auth_constructs(self) -> None:
        client = AsyncKalshiClient()
        assert client._auth is None

    def test_demo_no_auth(self) -> None:
        client = AsyncKalshiClient(demo=True)
        assert client._auth is None
        assert client._config.base_url == DEMO_BASE_URL

    @pytest.mark.asyncio
    async def test_private_endpoint_raises(self) -> None:
        client = AsyncKalshiClient(demo=True)
        with pytest.raises(AuthRequiredError):
            await client.orders.list()

    def test_ws_raises_without_auth(self) -> None:
        client = AsyncKalshiClient(demo=True)
        with pytest.raises(AuthRequiredError):
            _ = client.ws
```

Update `test_raises_without_auth` in `TestAsyncKalshiClientConstructor`:

Change:
```python
    def test_raises_without_auth(self) -> None:
        with pytest.raises(ValueError, match="Provide auth"):
            AsyncKalshiClient()
```

To:
```python
    def test_no_auth_constructs_unauthenticated(self) -> None:
        client = AsyncKalshiClient()
        assert client._auth is None
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `uv run pytest tests/test_client.py::TestKalshiClientUnauthenticated tests/test_client.py::TestKalshiClientFromEnvUnauthenticated tests/test_async_client.py::TestAsyncKalshiClientUnauthenticated -v`
Expected: FAIL — constructor still raises ValueError

- [ ] **Step 8: Update KalshiClient constructor**

In `kalshi/client.py`, replace the auth-building block in `__init__()`:

```python
        # Build auth (optional — None means unauthenticated)
        if auth is not None:
            self._auth = auth
        elif key_id and private_key_path:
            self._auth = KalshiAuth.from_key_path(key_id, private_key_path)
        elif key_id and private_key:
            self._auth = KalshiAuth.from_pem(key_id, private_key)
        else:
            self._auth = None
```

Update `from_env()`:

```python
    @classmethod
    def from_env(cls, **kwargs: object) -> KalshiClient:
        """Create client from environment variables.

        Reads:
            KALSHI_KEY_ID (optional — omit for unauthenticated access)
            KALSHI_PRIVATE_KEY (PEM string) or KALSHI_PRIVATE_KEY_PATH (file path)
            KALSHI_API_BASE_URL (optional, overrides base_url)
            KALSHI_DEMO (optional, "true" for demo environment)

        Returns an unauthenticated client if no credentials are configured.
        """
        auth = KalshiAuth.try_from_env()
        demo = os.environ.get("KALSHI_DEMO", "").lower() == "true"
        base_url = os.environ.get("KALSHI_API_BASE_URL")
        return cls(auth=auth, demo=demo, base_url=base_url, **kwargs)  # type: ignore[arg-type]
    ```

- [ ] **Step 9: Update AsyncKalshiClient constructor**

Same changes in `kalshi/async_client.py` — replace the auth-building block and update `from_env()` identically.

- [ ] **Step 10: Run tests to verify they pass**

Run: `uv run pytest tests/test_client.py::TestKalshiClientUnauthenticated tests/test_client.py::TestKalshiClientFromEnvUnauthenticated tests/test_async_client.py::TestAsyncKalshiClientUnauthenticated tests/test_auth.py::TestTryFromEnv -v`
Expected: PASS

- [ ] **Step 11: Run full suite + mypy + ruff**

Run: `uv run pytest tests/ -v --tb=short && uv run mypy kalshi/ && uv run ruff check .`
Expected: All PASS

- [ ] **Step 12: Commit**

```bash
git add kalshi/auth.py kalshi/client.py kalshi/async_client.py tests/test_auth.py tests/test_client.py tests/test_async_client.py
git commit -m "feat: allow unauthenticated KalshiClient construction

KalshiClient() and KalshiClient(demo=True) now work without
credentials for public endpoints. from_env() returns unauthenticated
client when KALSHI_KEY_ID is not set. Add KalshiAuth.try_from_env()."
```

---

### Task 4: Final Verification + Cleanup

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS, including new unauthenticated tests

- [ ] **Step 2: Run mypy strict**

Run: `uv run mypy kalshi/`
Expected: PASS with no errors

- [ ] **Step 3: Run ruff**

Run: `uv run ruff check .`
Expected: No issues

- [ ] **Step 4: Verify test count increased**

Run: `uv run pytest tests/ --co -q | tail -1`
Expected: Test count should be ~16 higher than the previous count

- [ ] **Step 5: Manual smoke test (optional)**

Verify the DX by running in a Python REPL:

```python
from kalshi import KalshiClient
client = KalshiClient(demo=True)
print(client.exchange.status())  # Should work
try:
    client.orders.list()
except Exception as e:
    print(f"Expected: {type(e).__name__}: {e}")
```

---

## Decisions Log

| # | Decision | Rationale | Source |
|---|----------|-----------|--------|
| 1 | Per-method guards, not transport-level | Explicit > clever, user preference | Eng review |
| 2 | AuthRequiredError extends KalshiAuthError | except KalshiAuthError catches both | Codex outside voice |
| 3 | Commit order: transport → guards → constructor | Bisectable intermediate commits | Codex outside voice |
| 4 | from_env() behavior change (returns unauth) | Pre-1.0, old behavior not useful | Eng review |
| 5 | .ws property gets auth guard | Clear error vs cryptic crash | Eng review |
| 6 | try_from_env() additive (from_env stays strict) | Backwards compatible KalshiAuth API | Design doc |
