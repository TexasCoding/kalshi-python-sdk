# Kalshi Python SDK

## Commands

```bash
uv sync                         # install dependencies
uv run pytest tests/ -v         # run all tests
uv run ruff check .             # lint
uv run ruff check . --fix       # lint + auto-fix
uv run mypy kalshi/             # type check
```

## Architecture

Spec-First Hybrid SDK: hand-crafted client facade + models, with OpenAPI generation pipeline planned for v0.2.

```
kalshi/
  __init__.py              # Public API exports + __version__
  client.py                # KalshiClient (sync facade)
  async_client.py          # AsyncKalshiClient (async facade)
  _base_client.py          # SyncTransport + AsyncTransport (httpx, retry, error mapping, logging)
  auth.py                  # RSA-PSS signer (standalone, well-tested)
  config.py                # KalshiConfig (base URL, timeouts, retry policy)
  errors.py                # Exception hierarchy (6 classes)
  pagination.py            # (planned) Standalone pagination utilities
  types.py                 # DollarDecimal custom Pydantic type, to_decimal()
  models/
    common.py              # Page[T] generic pagination model
    markets.py             # Market, Orderbook, OrderbookLevel, Candlestick
    orders.py              # Order, Fill, CreateOrderRequest
  resources/
    _base.py               # SyncResource + AsyncResource base classes
    markets.py             # MarketsResource + AsyncMarketsResource
    orders.py              # OrdersResource + AsyncOrdersResource
tests/
  conftest.py              # Shared fixtures (test RSA keys, auth, config)
  test_auth.py             # Auth signing, key loading, env vars
  test_client.py           # Transport, retry, error mapping
  test_markets.py          # Markets resource
  test_orders.py           # Orders resource
  test_models.py           # Decimal handling, model serialization
  test_pagination.py       # Page[T] model
```

## Key conventions

- All prices use `Decimal` via the `DollarDecimal` custom Pydantic type
- Auth signing payload: `str(timestamp_ms) + METHOD + path_only` (path from urlparse, no query params, no trailing slash)
- POST and DELETE are NEVER retried (duplicate order/cancel risk). Only GET/HEAD/OPTIONS retry.
- Retry on 429/502/503/504 with exponential backoff + jitter, capped at retry_max_delay
- Retry-After header is capped at retry_max_delay (prevents server-controlled sleep)
- Both sync and async clients share logic via dual transport abstraction (not sync-wrapping-async)
- Async `list_all()` returns AsyncIterator directly (not coroutine), so `async for item in client.markets.list_all():` works

## Adding a new resource

1. Create `kalshi/models/new_resource.py` with Pydantic models (use `DollarDecimal` for price fields)
2. Create `kalshi/resources/new_resource.py` with both `NewResource(SyncResource)` and `AsyncNewResource(AsyncResource)`
3. Add resource to `KalshiClient.__init__` and `AsyncKalshiClient.__init__`
4. Export models from `kalshi/models/__init__.py` and `kalshi/__init__.py`
5. Add tests in `tests/test_new_resource.py` using `respx.mock`
6. Every public method needs at least: happy path test, error path test, edge case test

## Testing

- pytest + pytest-asyncio + respx (httpx mock)
- 80 tests covering auth, transport, retry, error mapping, pagination, markets, orders, models
- Use `respx.mock` decorator for HTTP mocking
- Generate test RSA keys via conftest.py fixtures
- When writing new functions, write a corresponding test
- When fixing a bug, write a regression test
- When adding error handling, write a test that triggers the error

## API Reference

- OpenAPI spec: https://docs.kalshi.com/openapi.yaml (237KB, v3.13.0, 90+ endpoints)
- AsyncAPI spec: https://docs.kalshi.com/asyncapi.yaml (11 WebSocket channels)
- Base URL: https://api.elections.kalshi.com/trade-api/v2
- Demo URL: https://demo-api.kalshi.co/trade-api/v2
- Auth: RSA-PSS with SHA256, MGF1(SHA256), salt_length=DIGEST_LENGTH, base64-encoded signature

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
