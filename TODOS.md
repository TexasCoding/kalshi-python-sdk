# TODOS

## Auth path canonicalization edge cases
**What:** Add explicit path canonicalization to the auth signer: strip trailing slashes, normalize percent-encoding, ensure path params are substituted before signing.
**Why:** Silent 401 errors are the worst UX for an SDK. One wrong canonicalization detail and nothing works. Codex flagged this during eng review.
**Depends on:** Auth module implementation (Step 2).
**Added:** 2026-04-12 via /plan-eng-review

## Verify Kalshi price format (cents vs dollars) across all endpoints
**What:** During the spike phase, test actual API responses from the demo environment to verify price field formats. The OpenAPI spec field names use `_dollars` suffix (e.g., `yes_price_dollars`, `price_dollars`), which may mean the API returns dollar amounts, not integer cents.
**Why:** If the API returns dollar values (not cents), CentsToDecimal is wrong and the entire price handling layer needs adjustment. This is a foundational assumption.
**Depends on:** Spike phase (Step 0).
**Added:** 2026-04-12 via /plan-eng-review

## Add py.typed marker for PEP 561 compliance
**What:** Add empty `kalshi/py.typed` file and configure pyproject.toml to include it in the distribution.
**Why:** Without PEP 561 compliance, downstream users running mypy won't get type information from the SDK. The SDK's biggest selling point (full type safety) doesn't work for consumers without this.
**Depends on:** Project skeleton (Step 1).
**Added:** 2026-04-12 via /plan-eng-review
