# Wave 5 Audit O — Security

Reviewed at commit `0a3fb23580b3497c1e004d1b79f783b2dda38e24` against the v1.1.0 release.

## Summary

Overall the SDK is reasonably hardened for a trading SDK: RSA-PSS signing is implemented
correctly with the cryptography library (no homebrew crypto), POST/DELETE are correctly
excluded from retries, no PEM material or signatures are written to logs at any level,
the record/replay fixture format intentionally omits request headers and bodies so
saved fixtures cannot leak the API key ID or RSA signatures, and the PyPI release
workflow uses tag-pinned OIDC trusted publishing with a `version == tag` guard. The
strongest finding below is that the spec-sync workflow holds `contents: write` +
`pull-requests: write` and operates on untrusted upstream content; auto-merge of that
PR (if a maintainer ever enables it) plus a compromise of `docs.kalshi.com` would
amount to a supply-chain hijack. Other findings are defense-in-depth: unverified
scheme on `KALSHI_API_BASE_URL`, broad `except Exception` swallowing in the WS recv
loop, `exc_info=True` in dispatch that can dump frame contents into logs, missing
dependabot, and a couple of CI workflows on cron / `pull_request_target`-adjacent
triggers that still use mutable major-version tags.

## Findings

### F-O-01 — Spec-sync workflow ingests upstream YAML with write permissions (severity: high)
**File:** `.github/workflows/spec-sync.yml:9-11,53-54,135-216`
**Threat model:** A network attacker who can MITM or compromise `docs.kalshi.com`, or
a malicious party who can get a crafted change merged upstream into the published
OpenAPI/AsyncAPI YAML, can cause arbitrary YAML to be fed into
`scripts/sync_spec.py` and then into `scripts/generate.py` (datamodel-code-generator,
which writes a Python module the test suite imports). The workflow runs on a weekly
cron with `contents: write` and `pull-requests: write`, then opens a PR. If a
maintainer ever switches that PR to auto-merge, or hand-merges without reading
`_generated/models.py`, attacker-controlled Python lands on `main` — and the
release workflow triggers PyPI publish on tag push, propagating downstream.
**Impact:** Supply-chain compromise of `kalshi-sdk` on PyPI.
**Evidence:**
- `spec-sync.yml:9-11` — `permissions: contents: write, pull-requests: write`
- `spec-sync.yml:53-54` — `uv run python scripts/sync_spec.py` (downloads HTTPS YAML)
- `scripts/sync_spec.py:13-17` — `SPECS = {"openapi.yaml": "https://docs.kalshi.com/openapi.yaml", ...}` with no signature/hash pinning
- `spec-sync.yml:135-137` — `scripts/generate.py` runs `datamodel-code-generator`
  on attacker-controlled YAML; resulting Python is consumed by the test step on
  line 147-149 and would be reviewed in the PR diff but only as generated code.
**Suggested mitigation:** (a) Pin a published checksum or signature for the spec
files and verify before regen; or (b) keep auto-PR but require human approval
plus an explicit "I read `_generated/models.py`" check; or (c) gate the PR
generation behind a workflow that has only `contents: read` and posts the diff
as an issue comment, never as a writable branch. The existing SHA pinning of
third-party actions in this workflow is good — extend the principle to the
content being merged.

### F-O-02 — `claude.yml` and `claude-code-review.yml` use mutable major-version tags on broad-permission workflows (severity: medium)
**File:** `.github/workflows/claude.yml:25-26,33,38`, `.github/workflows/claude-code-review.yml:23-24,32`
**Threat model:** `claude.yml` runs on `issue_comment`/`pull_request_review_comment`
events (including from forks via PR review comments) with
`contents: write, pull-requests: write, issues: write, id-token: write` and uses
`actions/checkout@v4` and `anthropics/claude-code-action@v1` — both mutable tags.
A tag retag attack on either action would weaponize a workflow that has full
issue/PR write plus the `CLAUDE_CODE_OAUTH_TOKEN` secret. The spec-sync workflow
already SHA-pins its actions and documents *why* (`spec-sync.yml:22-24`). The
Claude workflows have equivalent or larger blast radius and should follow suit.
**Impact:** If `actions/checkout@v4` or `anthropics/claude-code-action@v1` is
retagged maliciously, attacker code runs with write access to repo contents,
PRs, issues, plus the OAuth token in env. The `id-token: write` permission also
exposes the workflow's OIDC token to any compromised step.
**Evidence:**
- `claude.yml:25-26,33` — `uses: actions/checkout@v4`, `uses: anthropics/claude-code-action@v1`
- `claude.yml:20-24` — `contents: write, pull-requests: write, issues: write, id-token: write`
- `claude-code-review.yml:23-24,32` — same pattern with slightly narrower perms
- `spec-sync.yml:22-24` — comment explicitly noting why this *other* workflow
  pins to SHA, demonstrating the team is aware of the threat model.
**Suggested mitigation:** Pin both actions to a specific commit SHA (matching
the spec-sync.yml comment's rationale). Subscribe to release notifications and
bump the SHA in PRs the way `spec-sync.yml` does.

### F-O-03 — No scheme/host validation on `KALSHI_API_BASE_URL`; HTTP base URL silently accepted (severity: medium)
**File:** `kalshi/client.py:137-138`, `kalshi/async_client.py:153-154`, `kalshi/config.py:18-44`
**Threat model:** Anyone who can write to a process's environment
(`docker run -e ...`, CI variable, `.env` checked into a different repo,
shell history) can set `KALSHI_API_BASE_URL=http://attacker.example/trade-api/v2`
or `https://attacker.example/...`. The SDK accepts the URL with no validation —
no scheme check, no host allowlist, no warning. The RSA-PSS signature is still
computed and sent (with the API key ID header) to the attacker's endpoint, then
the attacker proxies on to the real API. This is not a "process memory access"
class of attack; setting env vars is a normal deployment plane, and operators
mis-configuring `KALSHI_API_BASE_URL` (e.g., copy-paste from a forum) is a real
failure mode.
**Impact:** API key ID leakage (the key ID is not as sensitive as the private
key, but is identifying), live signature capture (each is single-use and bound
to method+path+timestamp, so it doesn't let the attacker forge arbitrary
requests — but it does identify the account and confirm the key is active),
and silent MITM of all trading activity. With `http://`, even passive network
observers downstream of the env-var setter capture everything.
**Evidence:**
- `client.py:137` — `base_url = os.environ.get("KALSHI_API_BASE_URL")`
- `config.py:18-44` — `KalshiConfig` accepts any string; only trailing-slash
  normalization happens in `__post_init__`.
- `_base_client.py:91-96` — `httpx.Client(base_url=config.base_url, ...)`
  consumes the URL directly.
**Suggested mitigation:** In `KalshiConfig.__post_init__`, reject `base_url`
that doesn't start with `https://` (allow `http://` only for `localhost`/
`127.0.0.1`/`::1` for testing), and log a `logger.warning` if the host is
neither `api.elections.kalshi.com` nor `demo-api.kalshi.co`. This is one-time
work and doesn't break legitimate proxy use cases (operators can still set
their own HTTPS proxy host).

### F-O-04 — WebSocket `recv_loop` swallows all exceptions with `except Exception` (severity: medium)
**File:** `kalshi/ws/client.py:204-207`
**Threat model:** A misbehaving (or malicious) server that injects malformed
frames, schema-violating payloads, or oversized strings into the WS stream
will cause any exception during dispatch / orderbook apply / sequence track /
backpressure to be logged at `warning` and silently swallowed. This includes
exceptions raised by callbacks the user registered (`MessageDispatcher.dispatch`
awaits `self._callbacks[sub.channel](parsed)`), which means a callback that
performs auth checks or trade-rejection logic cannot fail-fast — it gets logged
and skipped, leaving the consumer ignorant. There's no rate limiter on this
log line either, so an attacker that can inject 1k+ bad frames/sec will fill
disk with log noise.
**Impact:** Defense-in-depth gap. Combined with `KalshiBackpressureError` being
defined but caught here (it should propagate to the consumer per its docstring),
this masks the security-relevant signal "the queue is overflowing, drop the
stream." Also masks any future cryptographic verification logic someone might
add to messages.
**Evidence:**
- `kalshi/ws/client.py:204-207` —
  ```python
  except Exception as e:
      logger.warning("Error processing message: %s", e)
      continue
  ```
- `kalshi/errors.py:80-82` — `KalshiBackpressureError` exists for this exact case
  and is supposed to escape to the caller; here it is swallowed.
**Suggested mitigation:** Narrow the except clause: re-raise
`KalshiBackpressureError`, `KalshiSubscriptionError`, and `asyncio.CancelledError`;
log+continue only for `pydantic.ValidationError`, `json.JSONDecodeError`, and
`KeyError`. Add a counter (in-memory, no persistence) and break the loop after
N consecutive failures — that's the canonical fail-fast signal for a corrupted
server stream.

### F-O-05 — `dispatch.py:94` logs full parse exceptions with `exc_info=True`, dumping frame contents into the log (severity: medium)
**File:** `kalshi/ws/dispatch.py:91-95`
**Threat model:** When a Pydantic model fails to parse a message (e.g., a `fill`
message has an unexpected schema), `logger.warning("Failed to parse %s message",
msg_type, exc_info=True)` dumps the full Pydantic `ValidationError`, which
includes the *input dict* in its repr. For private channels like `fill`,
`user_order`, `market_positions`, that dict contains user-identifiable trade
data: order IDs, sizes in USD, side, ticker, fill prices, and the user's
client_order_id. Operators running with default `WARNING` log level (or any
log shipper that ingests warnings into a SIEM/Splunk/Datadog) will write
financial PII to log infrastructure that's typically lower-trust than the
trading environment.
**Impact:** Trade data leakage into logs and downstream log aggregators.
Distinct from the documented record/replay fixture risk; this affects normal
production runs.
**Evidence:**
- `kalshi/ws/dispatch.py:88,94` — `Unknown message type: %s` (logs only the type
  string, OK) and `Failed to parse %s message", msg_type, exc_info=True` (the
  exc_info flag is the problem — Pydantic includes the input in its error repr).
- `kalshi/ws/dispatch.py:73` — `logger.warning("Received non-JSON frame: %s",
  raw[:100])` — bounded to 100 chars but still includes arbitrary frame content.
**Suggested mitigation:** Drop `exc_info=True` from the parse-failure log, or
replace with a sanitized message like `logger.warning("Failed to parse %s
message (validation error)", msg_type)` and only emit the full traceback under
an opt-in `KALSHI_DEBUG_WS=1` env flag. For the non-JSON frame log, log only
the length and first/last 16 bytes, not 100 chars of payload.

### F-O-06 — Reconnect path does not refresh signatures, but signature is generated per-connect, so timing OK — informational (severity: informational)
**File:** `kalshi/ws/connection.py:122-172`
**Threat model:** N/A.
**Impact:** None.
**Evidence:** `connection.py:156` re-calls `self._build_auth_headers()` on every
reconnect attempt, which re-signs with a fresh timestamp via
`KalshiAuth.sign_request` (auth.py:175-176, `timestamp_ms = int(time.time() * 1000)`).
This is correct — old timestamps would be rejected by the server. Noting it
because the pattern is easy to get wrong in an auto-reconnect loop.
**Suggested mitigation:** None. Leaving as informational documentation.

### F-O-07 — No dependabot / no automated dependency CVE scanning (severity: medium)
**File:** `.github/` (no `dependabot.yml`), `pyproject.toml:19-24`
**Threat model:** The SDK depends on `httpx>=0.27,<1`, `pydantic>=2.0,<3`,
`cryptography>=43,<45`, `websockets>=14,<17`. `cryptography` in particular
has had repeated CVEs (2024 OpenSSL bundling, 2023 NULL deref). Without
dependabot or `pip-audit` in CI, a CVE in any of these floors the SDK
indefinitely without prompting a release. `cryptography>=43,<45` excludes
v45+ which means the upper bound is conservative but also stale.
**Impact:** Downstream consumers transitively pull whatever `cryptography`
their resolver picks within `>=43,<45`. If a CVE lands in 43.x or 44.x, no
automation flags it.
**Evidence:**
- `pyproject.toml:19-24` — dependency block, no constraints file, no `pip-audit`.
- `.github/workflows/` — no scanning step, no dependabot config.
**Suggested mitigation:** Add `.github/dependabot.yml` with weekly Python and
GitHub-Actions ecosystems. Add a `uv run pip-audit` step (or `safety check`)
to `ci.yml`. The ws upper bound at `<17` is reasonable; the `cryptography<45`
bound should be re-evaluated since v45 is current.

### F-O-08 — `Retry-After` numeric parser accepts negative values and `inf` (severity: low)
**File:** `kalshi/_base_client.py:57-66`, `kalshi/_base_client.py:165-167` (sync) and `:278-279` (async)
**Threat model:** A malicious or buggy server sending `Retry-After: -1` or
`Retry-After: 1e308` makes `float(retry_after)` succeed; the code then does
`min(error.retry_after, self._config.retry_max_delay)`. For `-1`, `min(-1, 30)`
is `-1`, and `time.sleep(-1)` is fine on POSIX but unintuitive — effectively
no backoff, so the client busy-loops the server-controlled retry. For `inf`,
`min(inf, 30) == 30`, OK. For `NaN`, `min(nan, 30)` returns `nan`,
`time.sleep(nan)` raises `ValueError` and bubbles up unexpectedly.
**Impact:** Server-controlled retry storm against the SDK user (CPU/network),
or unexpected exception type on `NaN`. The cap is documented in CLAUDE.md as
"prevents server-controlled sleep" but actually only caps the upper end.
**Evidence:**
- `_base_client.py:60-63` — `try: retry_after_val = float(retry_after)` with no
  range check.
- `_base_client.py:165-167` — `delay = min(error.retry_after, retry_max_delay)`.
**Suggested mitigation:** Add `if retry_after_val < 0 or not math.isfinite(
retry_after_val): retry_after_val = None`. Five lines, removes the lower-bound
gap and the NaN crash.

### F-O-09 — `KalshiError` exception messages may include full URLs from httpx (severity: low)
**File:** `kalshi/_base_client.py:136,144,249,257`, `kalshi/ws/connection.py:117-120`
**Threat model:** `KalshiError(f"Request timed out: {e}")` and
`KalshiError(f"HTTP error: {e}")` interpolate the str of the httpx exception,
which typically contains the full URL including any query string. For private
endpoints (e.g., `GET /portfolio/positions?ticker=...`), the query string
itself isn't sensitive, but if a user constructs a URL with a token-like value
in a query param the exception message will land in any uncaught-exception
sink (Sentry, stderr, log aggregator). Same applies to WS:
`KalshiConnectionError(f"WebSocket connection failed: {e}")`.
**Impact:** Low-grade info leakage into logs. Not a path to key extraction
because auth headers are not in the URL.
**Evidence:**
- `_base_client.py:136` — `KalshiError(f"Request timed out: {e}")`
- `_base_client.py:144` — `KalshiError(f"HTTP error: {e}") from e`
- `ws/connection.py:119` — `KalshiConnectionError(f"WebSocket connection failed: {e}")`
**Suggested mitigation:** Strip the URL from `e` before interpolation, or use
a fixed message and rely on the `__cause__` (`raise ... from e`) for the
detail. Most error trackers serialize `__cause__` anyway.

### F-O-10 — `from_env`/`try_from_env` do not zero out PEM strings after loading (severity: informational)
**File:** `kalshi/auth.py:101-156`
**Threat model:** `KALSHI_PRIVATE_KEY` env var content is read into `pem_string`,
passed to `from_pem`, which `encode("utf-8")`s and hands to
`serialization.load_pem_private_key`. The original string remains in
`os.environ` for the process lifetime. This is standard practice for
env-based secret loading and is not realistically a finding — process-local
secrets in env are the deployment plane this SDK targets. Noting for
completeness.
**Impact:** None beyond the normal env-var threat model. A `/proc/<pid>/environ`
read would already give the attacker the secret regardless of what the SDK does.
**Evidence:** `kalshi/auth.py:115-126` reads env vars and never unsets them.
**Suggested mitigation:** None recommended. If extreme hardening is wanted,
`os.environ.pop("KALSHI_PRIVATE_KEY", None)` after construction, but that
breaks reload-from-env flows.

### F-O-11 — `integration-nightly.yml` writes the private key with `chmod 600` but does not shred it on exit (severity: low)
**File:** `.github/workflows/integration-nightly.yml:51-65`
**Threat model:** The workflow writes `secrets.KALSHI_PRIVATE_KEY` to
`$RUNNER_TEMP/kalshi_private_key.pem`. GitHub-hosted runners are ephemeral
and `RUNNER_TEMP` is wiped between jobs, so persistence is not the issue.
However, if a later step in the *same job* is compromised (e.g., a malicious
test or installed package), the PEM is still on disk for the duration of
`pytest`. The PEM is also implicitly exposed to anything that can read
`$RUNNER_TEMP` for the rest of the job.
**Impact:** Low. Self-hosted runners would change the risk model but the
guard `if: github.repository == 'TexasCoding/kalshi-python-sdk'` on
`integration-nightly.yml:11` keeps this off forks.
**Evidence:** `integration-nightly.yml:55-65` writes via `printenv` (good — no
heredoc/shell-expansion risk), `chmod 600`, then exports
`KALSHI_PRIVATE_KEY_PATH`. No cleanup step.
**Suggested mitigation:** Add a final `if: always()` step that `shred -u
"${KALSHI_PRIVATE_KEY_PATH}"` (or `rm -f` since GitHub-hosted is ephemeral).
Mostly cosmetic on hosted runners; matters if you ever flip to self-hosted.

### F-O-12 — PyPI release: tag-to-version check is good, but no provenance / sigstore signing (severity: informational)
**File:** `.github/workflows/release.yml:21-31,41-58`
**Threat model:** The release workflow has the `version == tag` guard which
prevents the simple "push a tag with a different version" attack. It uses
OIDC trusted publishing (`permissions: id-token: write` + no
`PYPI_API_TOKEN`), which is the right pattern. It does *not* upload sigstore
bundles or PEP 740 attestations alongside the artifacts.
**Impact:** None today. Downstream consumers verifying via sigstore would not
get a signal. Noting because the upcoming default of attestations is
opt-in-now / default-later and the project is otherwise well-set-up to take
advantage.
**Evidence:**
- `release.yml:22-29` — tag/version match guard.
- `release.yml:48-50` — `permissions: id-token: write`.
- `release.yml:57-58` — `pypa/gh-action-pypi-publish@release/v1` — supports
  `attestations: true` but the workflow does not set it.
**Suggested mitigation:** Add `with: attestations: true` to the
`gh-action-pypi-publish` step. Free, no maintainer action required.

### F-O-13 — Recorded fixture format does NOT save request headers/body, so the documented "scrub fixtures" warning is well-supported (severity: informational — clean finding)
**File:** `kalshi/testing/_fixtures.py:48-55,76-81`, `kalshi/testing/__init__.py:11-17`
**Threat model:** N/A — verifying the docstring claim in `testing/__init__.py:11-17`
that recorded fixtures might leak sensitive *response* bodies but not auth
headers.
**Impact:** None — confirmed `_request_to_dict` only persists
`method/url/path/query`, never `request.headers` or `request.content`. The
`KALSHI-ACCESS-SIGNATURE` and `KALSHI-ACCESS-TIMESTAMP` headers cannot end up
in fixtures. The module docstring's `.. warning::` block correctly scopes the
risk to response bodies (balances, positions, PII).
**Evidence:**
- `_fixtures.py:48-55` — `_request_to_dict` returns only
  `{method, url, path, query}`. No header serialization anywhere.
- `_fixtures.py:76-81` — `record_pair` uses only `_request_to_dict` /
  `_response_to_dict`.
- `__init__.py:11-17` — the existing warning is adequate; the audit prompt
  asked us to flag only if it's insufficient.
**Suggested mitigation:** None. This is a clean finding confirming the design
is correct. The team may want to add a unit test that asserts no header keys
are ever present in serialized fixtures, as a regression guard against future
edits.

---

## Categories examined with no findings

- **Auth signing payload formation** (`auth.py:162-207`) — correct: timestamp +
  METHOD + path-only, percent-encoding normalized to uppercase per RFC 3986,
  trailing slash stripped (with `/` exception), query parameters stripped.
- **PEM string logging** — verified by `grep -rn "logger\." kalshi/` plus
  reading each match. No PEM content is ever logged. The only sensitive-ish
  log is the `from_env` warning that doesn't include any key material.
- **POST/DELETE retry exclusion** (`_base_client.py:31-32,155-159`) — correct:
  `RETRYABLE_METHODS = {"GET", "HEAD", "OPTIONS"}`, DELETE explicitly excluded
  with a comment about cancel idempotency. Retry only fires on transient 5xx /
  429 / timeout *and* method in the safe set.
- **Retry-After upper-bound capping** — capped at `retry_max_delay` correctly;
  see F-O-08 for the negative/NaN gap.
- **httpx defaults** — TLS verify on by default (httpx default; not overridden),
  no `verify=False` anywhere.
- **`.gitignore` coverage** — `.env`, `*.pem`, `*.key`, `.env.*` all present;
  verified `.env` and `.keys/*.pem` are actually ignored.
- **SecretStr on `private_key` API response** (`models/api_keys.py:92`) — used
  correctly, ensures `repr()` masks the value.
