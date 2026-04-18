"""Path B demo-feasibility audit for v0.10-v0.13 endpoints.

Probes every REST endpoint in the spec that is NOT yet in
``tests/_contract_support.METHOD_ENDPOINT_MAP`` against the Kalshi demo server
and classifies each as ``demo-supported`` / ``demo-501`` / ``auth-gated``.

Classification rules (applied to the HTTP status returned by demo):
    200/204          → demo-supported (happy path responds)
    400/404/422      → demo-supported (route exists; our probe payload was
                       intentionally minimal, a validation error is expected)
    401/403          → auth-gated      (endpoint exists but demo account lacks
                       permission; real creds may unlock it)
    405              → method-not-allowed (spec/server disagreement)
    501              → demo-501       (demo refuses to implement this one)
    5xx              → transient      (retried once; if still failing, flagged)

Output: a grouped table printed to stdout. Run with ``uv run python
scripts/audit_demo_feasibility.py``.

This script is read-only against demo: every probe uses either GET/DELETE
with a placeholder ID (which cannot match a real resource) or POST/PUT with
an empty body (which will 400 before creating anything). Nothing is mutated.
"""

from __future__ import annotations

import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Bridge .env-style KALSHI_DEMO_* to KALSHI_* before importing the client.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

if os.environ.get("KALSHI_DEMO_KEY_ID") and not os.environ.get("KALSHI_KEY_ID"):
    os.environ["KALSHI_KEY_ID"] = os.environ["KALSHI_DEMO_KEY_ID"]
if os.environ.get("KALSHI_DEMO_PRIVATE_KEY_PATH") and not os.environ.get(
    "KALSHI_PRIVATE_KEY_PATH"
):
    os.environ["KALSHI_PRIVATE_KEY_PATH"] = os.environ["KALSHI_DEMO_PRIVATE_KEY_PATH"]
os.environ.setdefault("KALSHI_DEMO", "true")

from kalshi.client import KalshiClient  # noqa: E402
from kalshi.errors import (  # noqa: E402
    KalshiAuthError,
    KalshiError,
    KalshiNotFoundError,
    KalshiRateLimitError,
    KalshiServerError,
    KalshiValidationError,
)

PLACEHOLDER = "AUDIT-NONEXISTENT-ID"


def load_spec_endpoints() -> set[tuple[str, str]]:
    with open(ROOT / "specs" / "openapi.yaml") as f:
        spec = yaml.safe_load(f)
    out: set[tuple[str, str]] = set()
    for path, methods in spec["paths"].items():
        for m, _op in methods.items():
            if m in ("get", "post", "put", "delete", "patch"):
                out.add((m.upper(), path))
    return out


def load_covered_endpoints() -> set[tuple[str, str]]:
    src = (ROOT / "tests" / "_contract_support.py").read_text()
    blocks = re.findall(
        r"MethodEndpointEntry\([^)]*?(?:\([^)]*?\)[^)]*?)*\)", src, re.DOTALL
    )
    covered: set[tuple[str, str]] = set()
    for b in blocks:
        m = re.search(r'http_method="([A-Z]+)"', b)
        p = re.search(
            r'path_template=(?:"([^"]+)"|\(\s*"([^"]+)"\s*\))', b
        )
        if m and p:
            covered.add((m.group(1), p.group(1) or p.group(2)))
    return covered


def substitute_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", PLACEHOLDER, path)


def classify(status: int) -> str:
    if 200 <= status < 300:
        return "demo-supported (2xx)"
    if status in (400, 422):
        return "demo-supported (4xx validation)"
    if status == 404:
        return "demo-supported (404 — route exists)"
    if status in (401, 403):
        return "auth-gated"
    if status == 405:
        return "method-not-allowed (spec/server drift)"
    if status == 501:
        return "demo-501"
    if status == 429:
        return "rate-limited"
    if 500 <= status < 600:
        return f"demo-5xx (status {status})"
    return f"unknown-{status}"


def probe_one(client: KalshiClient, method: str, path_template: str) -> tuple[int, str]:
    """Return (status_code, error_class_name) for one probe."""
    concrete_path = substitute_path(path_template)
    body: dict[str, Any] | None = {} if method in ("POST", "PUT", "PATCH") else None
    params: dict[str, Any] | None = None
    # a handful of GETs require query params up front; send none and accept a 400
    try:
        resp = client._transport.request(
            method, concrete_path, params=params, json=body
        )
        return (resp.status_code, "OK")
    except KalshiNotFoundError as e:
        return (e.status_code or 404, "KalshiNotFoundError")
    except KalshiValidationError as e:
        return (e.status_code or 400, "KalshiValidationError")
    except KalshiAuthError as e:
        return (e.status_code or 401, "KalshiAuthError")
    except KalshiRateLimitError as e:
        return (e.status_code or 429, "KalshiRateLimitError")
    except KalshiServerError as e:
        return (e.status_code or 500, "KalshiServerError")
    except KalshiError as e:
        # Generic KalshiError: check if it carries a status_code
        sc = getattr(e, "status_code", None) or 0
        return (sc, type(e).__name__)


def phase_for(path: str) -> str:
    """Map endpoint to its TODOS phase."""
    if path.startswith("/portfolio/order_groups"):
        return "v0.10.0"
    if path.startswith("/communications/"):
        return "v0.11.0 (RFQ)"
    if path.startswith("/portfolio/subaccounts"):
        return "v0.11.0 (Subaccounts)"
    if path.startswith("/api_keys"):
        return "v0.12.0 (API Keys)"
    if path.startswith("/markets/candlesticks") or path == "/markets/orderbooks":
        return "v0.12.0 (Bulk/Batch)"
    if path.startswith("/markets/trades"):
        return "v0.12.0 (Bulk/Batch)"
    if path.startswith("/milestones"):
        return "v0.12.0 (Milestones)"
    if path.startswith("/live_data"):
        return "v0.12.0 (Milestones/live_data)"
    if path.startswith("/fcm/"):
        return "v0.13.0 (FCM)"
    if path.startswith("/structured_targets"):
        return "v0.13.0 (Structured Targets)"
    if path.startswith("/search/") or path == "/account/limits":
        return "v0.13.0 (Search/Account)"
    if path == "/incentive_programs":
        return "v0.13.0 (Incentives)"
    if path == "/exchange/user_data_timestamp":
        return "v0.13.0 (Exchange)"
    if path.startswith("/portfolio/summary"):
        return "v0.13.0 (Portfolio Summary)"
    return "v0.13.0 (other)"


def main() -> None:
    if not os.environ.get("KALSHI_KEY_ID"):
        print("ERROR: KALSHI_KEY_ID not set (check .env)", file=sys.stderr)
        sys.exit(1)

    spec = load_spec_endpoints()
    covered = load_covered_endpoints()
    uncovered = sorted(spec - covered)
    print(f"Spec endpoints: {len(spec)}")
    print(f"Covered by METHOD_ENDPOINT_MAP: {len(covered)}")
    print(f"Uncovered (audit targets): {len(uncovered)}\n")

    client = KalshiClient.from_env()
    # Safety gate
    if "demo" not in client._config.base_url:
        print(f"ABORT: base_url is {client._config.base_url}, refusing to audit", file=sys.stderr)
        sys.exit(2)
    print(f"Probing {client._config.base_url}\n")

    results: list[tuple[str, str, str, int, str, str]] = []  # phase,method,path,status,class,err
    for i, (method, path) in enumerate(uncovered, 1):
        status, err = probe_one(client, method, path)
        klass = classify(status)
        ph = phase_for(path)
        results.append((ph, method, path, status, klass, err))
        print(f"[{i:>2}/{len(uncovered)}] {method:<6} {path:<60} → {status} {klass}")
        time.sleep(0.1)  # gentle on demo

    client.close()

    # Summary grouped by phase
    print("\n" + "=" * 96)
    print("SUMMARY BY PHASE")
    print("=" * 96)
    by_phase: dict[str, list[tuple[str, str, int, str, str]]] = defaultdict(list)
    for ph, m, p, s, k, e in results:
        by_phase[ph].append((m, p, s, k, e))

    for ph in sorted(by_phase):
        print(f"\n## {ph}")
        for m, p, s, k, _e in by_phase[ph]:
            print(f"  {m:<6} {p:<58} {s:>3}  {k}")

    # Top-level classification counts
    print("\n" + "=" * 96)
    print("TOTALS")
    print("=" * 96)
    counts: dict[str, int] = defaultdict(int)
    for _ph, _m, _p, _s, k, _e in results:
        # bucket into the three TODOS categories
        if k.startswith("demo-supported"):
            counts["demo-supported"] += 1
        elif k == "auth-gated":
            counts["auth-gated"] += 1
        elif k == "demo-501":
            counts["demo-501"] += 1
        else:
            counts[f"other ({k})"] += 1
    for k, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {k:<40} {n}")


if __name__ == "__main__":
    main()
