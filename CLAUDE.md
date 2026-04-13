# Kalshi Python SDK

## Commands

```bash
uv run pytest tests/ -v         # run all tests
uv run ruff check .             # lint
uv run ruff check . --fix       # lint + auto-fix
uv run mypy kalshi/             # type check
```

## Architecture

Spec-First Hybrid SDK: hand-crafted client facade + models, with OpenAPI generation pipeline planned.

- `kalshi/auth.py` — RSA-PSS signer (standalone, well-tested)
- `kalshi/_base_client.py` — SyncTransport + AsyncTransport (httpx, retry, error mapping)
- `kalshi/resources/_base.py` — _BaseResource with _get/_post/_delete/_list helpers
- `kalshi/resources/markets.py` — Markets resource (sync + async)
- `kalshi/resources/orders.py` — Orders resource (sync + async)
- `kalshi/models/` — Pydantic v2 models with DollarDecimal custom type
- `kalshi/client.py` — KalshiClient (sync facade)
- `kalshi/async_client.py` — AsyncKalshiClient (async facade)

## Key conventions

- All prices use `Decimal` via the `DollarDecimal` custom Pydantic type
- Auth signing: `str(timestamp_ms) + METHOD + full_path` (no query params, no trailing slash)
- POST requests are NEVER retried (duplicate order risk)
- GET/DELETE retry on 429/502/503/504 with exponential backoff + jitter
- Both sync and async clients share logic via transport abstraction

## Testing

- pytest + pytest-asyncio + respx (httpx mock)
- 80 tests covering auth, transport, retry, error mapping, pagination, markets, orders, models
- Use `respx.mock` decorator for HTTP mocking
- Generate test RSA keys via conftest.py fixtures

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
