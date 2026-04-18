# BACKLOG

Items parked here are valuable but **not on the north-star path to 100% endpoint coverage**. They stay in backlog until the coverage goal is closed, or until one of them directly blocks active work. Promote back to `TODOS.md` deliberately, not by drift.

See `TODOS.md` for the active coverage plan and the north-star definition.

---

## Code quality / architecture

### P3: Reduce sync/async duplication tax (v0.8+)
**What:** Every resource file has near-identical sync and async classes (~95% duplication of method bodies). Each new kwarg must be added in two places; mismatch is a real risk. Possible approaches: (a) shared params-builder helpers, (b) sync-wrapping-async architecture, (c) code-gen from a single source. Out of scope for v0.7.0 because the audit alone added ~32 kwargs × 2 = ~64 method signatures touched.
**Why:** Maintenance tax keeps growing as the SDK adds resources. v0.7.0 doubled the kwarg surface; future additions get more painful.
**Pros:** Single source of truth. Half the maintenance.
**Cons:** Potentially big architectural change. Risk of breaking the `async for` ergonomics that `list_all` enables.
**Depends on:** v0.7.0 shipped (done).
**Added:** 2026-04-16 via /plan-eng-review round 2 (flagged but not bundled).

### P3: Async/sync `_delete_with_body` parity (v0.9)
**What:** Sync `OrdersResource.batch_cancel` goes through `self._delete_with_body(...)`; async `AsyncOrdersResource.batch_cancel` calls `self._transport.request("DELETE", ...)` directly. If `_delete_with_body` ever gains error-mapping or retry behavior, the async path silently diverges. Add an `async_delete_with_body` helper (or equivalent on the async transport) and route async batch_cancel through it.
**Why:** The project's stated sync/async parity via dual transport abstraction has a one-method gap. Fine today (`_delete_with_body` is a thin shim), but tempting to drop extra logic into the sync helper without remembering the async path bypasses it.
**Depends on:** v0.8.0 shipped (done).
**Added:** 2026-04-18 via PR #31 claude[bot] review (finding m4).

### P3: Verify public resource endpoint auth requirements
**What:** Check the OpenAPI spec for which GET endpoints in public resources (MarketsResource, EventsResource, ExchangeResource, HistoricalResource) actually require auth headers. If any public resource method routes to an auth-requiring endpoint, add a per-method `_require_auth()` guard to that specific method.
**Why:** The unauthenticated client guards private resources (orders, portfolio) at the resource level, but some public resource endpoints might require auth (e.g., if Kalshi adds a `/markets/{ticker}/my-position` endpoint). Without guards on those specific methods, users get a confusing 401 from Kalshi instead of a clear `AuthRequiredError`.
**Depends on:** Unauthenticated client path shipped.
**Added:** 2026-04-14 via /plan-eng-review (Codex outside voice identified the gap)

---

## Type system polish

### P3: Enum typing sweep — adopt Literal across enum kwargs (v0.9)
**What:** Replace `str | None` with `Literal[...]` for fixed-enum kwargs: `time_in_force`, `self_trade_prevention_type`, `side`, `action`, `status` filters on list methods. Single-sweep release.
**Why:** v0.7.0 and v0.8.0 both deferred `Literal` adoption to avoid scoping-in a typing sweep during feature work. A dedicated sweep lets mypy catch invalid enum values at user-code authoring time.
**Depends on:** v0.8.0 shipped (done).
**Added:** 2026-04-18 via /plan-eng-review (scope decision deferred from v0.8.0).

### P3: Typed `Exclusion.kind` enum instead of free-text reason matching (v0.9)
**What:** Replace string-heuristic classification in `test_exclusion_map_is_current` (substring match on `"body param"`, `"not query/path"`, etc.) with a typed `kind: Literal["body_param", "spec_deprecated", "paginator_handled", "wire_normalization"]` field on `Exclusion`. Update all 25 existing entries to set `kind` explicitly.
**Why:** Current staleness checker in `tests/test_contracts.py` branches on free-text `reason` substrings. A future exclusion with slightly different wording (e.g. `"request body field"` instead of `"body param"`) would silently misclassify. A typed enum makes intent explicit and prevents classification drift.
**Pros:** Unambiguous; IDE autocomplete; mypy catches typos.
**Cons:** Requires updating 25 existing entries. Low risk but touches most of `_contract_support.py`.
**Depends on:** v0.8.0 shipped (done).
**Added:** 2026-04-18 via PR #31 claude[bot] review (finding n2).

---

## Test infrastructure polish

### P3: Nested request-body schema $ref recursion (only if needed)
**What:** Extend `_resolve_request_body_schema` in `tests/_contract_support.py` to recurse into nested `$ref` pointers inside body schemas. Today all 7 POST/PUT/DELETE body schemas have flat properties — verified at v0.8.0. Only implement when a nested ref lands in the spec.
**Why:** Drift detection breaks silently if nested property refs are introduced without resolver support.
**Depends on:** v0.8.0 shipped (done). Activation trigger: first spec update that introduces a nested `$ref` in a POST/PUT/DELETE body schema.
**Added:** 2026-04-18 via /plan-eng-review.

### P3: TestRequestBodyDrift should cover nested Pydantic models (v0.9)
**What:** `_model_aliases()` in `tests/test_contracts.py` iterates one level deep only. Nested models like `TickerPair` (inside `CreateMarketInMultivariateEventCollectionRequest.selected_markets`) have no `BODY_MODEL_MAP` entry and are not checked for drift. `TickerPair` has `extra="allow"` so phantom fields flow to the wire silently.
**Why:** False confidence in drift coverage. Not a production bug today (TickerPair fields are correct) but a future schema change to the nested type would silently bypass the drift test.
**Pros:** Closes a genuine gap in the scanner; surfaces any drift on nested models.
**Cons:** Requires deciding whether TickerPair should gain `extra="forbid"` (could be breaking for callers who pass extra keys). Design decision + test expansion.
**Depends on:** v0.8.0 shipped (done).
**Added:** 2026-04-18 via /review adversarial pass (Finding INFORMATIONAL-3).

### P3: Integration test — from_env() and constructor variant coverage
**What:** Add integration tests that verify KalshiClient can be constructed via all supported paths: `from_env()`, `key_id + private_key_path`, `key_id + private_key` (PEM string), `auth=KalshiAuth(...)`, and `demo=True` flag. Currently only `from_env()` is tested by the integration suite.
**Why:** Users construct the client in different ways. A signing bug that only manifests with `from_key_path()` vs `from_pem()` would go undetected.
**Depends on:** Integration test suite shipped (done).
**Added:** 2026-04-14

### P3: Integration test — CI pipeline with scheduled runs
**What:** Add a GitHub Actions workflow that runs `pytest tests/integration/ -v` on a schedule (nightly or weekly). Store KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH as GitHub Actions secrets. Report failures via PR comment or Slack notification.
**Why:** Integration tests only catch drift if they run regularly. Currently they only run when a developer manually runs them locally with credentials configured.
**Depends on:** Integration test suite stable (done). GitHub Actions secrets configured.
**Added:** 2026-04-14

---

## DX / API expansion

### P3: Model-first request API overload (v0.9)
**What:** Add optional model-first signatures alongside existing kwarg-based signatures: `orders.amend(request: AmendOrderRequest)`, etc. Runtime dispatch on argument type. Existing kwarg-based callers unaffected.
**Why:** Advanced users (programmatic order construction, serialization layers) benefit from passing a fully-formed request model. Current API forces them to unpack into kwargs and re-pack.
**Depends on:** v0.8.0 shipped (done). Request models all exist.
**Added:** 2026-04-18 via /plan-eng-review.
