"""Fixture storage and request fingerprinting for the mock transport layer.

Fingerprint rules:
- Match on HTTP method + URL path + sorted query parameters.
- Ignore request body (POST bodies vary by signature/timestamp).
- Ignore the KALSHI-ACCESS-SIGNATURE and KALSHI-ACCESS-TIMESTAMP headers.

Storage layout:
    <dir>/<METHOD>_<sanitized_path>.json

Each file is a JSON list of recorded `{request, response}` pairs so multiple
captures of the same endpoint coexist. On replay, the first matching pair is
returned (FIFO across sequential replays via a per-file index).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def fingerprint(request: httpx.Request) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    """Return a (method, path, sorted_query) tuple that identifies a request.

    Ignores body and auth headers. Query parameters are sorted so order doesn't
    matter. Path includes the full URL path (not just the endpoint suffix).
    """
    parts = urlsplit(str(request.url))
    method = request.method.upper()
    path = parts.path
    query = tuple(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return (method, path, query)


def fixture_filename(method: str, path: str) -> str:
    """Build a filesystem-safe filename from a method and URL path."""
    safe_path = _SANITIZE_RE.sub("_", path).strip("_") or "root"
    return f"{method.upper()}_{safe_path}.json"


def _request_to_dict(request: httpx.Request) -> dict[str, Any]:
    parts = urlsplit(str(request.url))
    return {
        "method": request.method.upper(),
        "url": str(request.url),
        "path": parts.path,
        "query": sorted(parse_qsl(parts.query, keep_blank_values=True)),
    }


def _response_to_dict(response: httpx.Response) -> dict[str, Any]:
    # Try to store JSON bodies as objects for readability; fall back to text.
    body_bytes = response.content
    body: Any
    try:
        body = json.loads(body_bytes) if body_bytes else None
        body_kind = "json"
    except (ValueError, UnicodeDecodeError):
        body = body_bytes.decode("latin-1")
        body_kind = "text"
    return {
        "status_code": response.status_code,
        "headers": [(k, v) for k, v in response.headers.items()],
        "body_kind": body_kind,
        "body": body,
    }


def record_pair(request: httpx.Request, response: httpx.Response) -> dict[str, Any]:
    """Build a serializable pair from a real request/response round-trip."""
    return {
        "request": _request_to_dict(request),
        "response": _response_to_dict(response),
    }


def build_response(stored: dict[str, Any], request: httpx.Request) -> httpx.Response:
    """Reconstruct an httpx.Response from a stored response dict."""
    resp = stored["response"]
    body_kind = resp.get("body_kind", "json")
    body = resp.get("body")
    if body_kind == "json":
        content = b"" if body is None else json.dumps(body).encode("utf-8")
    else:
        content = ("" if body is None else str(body)).encode("latin-1")
    headers = [(str(k), str(v)) for k, v in resp.get("headers", [])]
    return httpx.Response(
        status_code=int(resp["status_code"]),
        headers=headers,
        content=content,
        request=request,
    )


def load_pairs(dir_path: Path, method: str, path: str) -> list[dict[str, Any]]:
    """Load all recorded pairs for a (method, path) fixture file. Empty list if missing."""
    file_path = dir_path / fixture_filename(method, path)
    if not file_path.exists():
        return []
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(
            f"Fixture file {file_path} must contain a JSON list of pairs, got {type(data).__name__}"
        )
    return data


def save_pairs(dir_path: Path, method: str, path: str, pairs: list[dict[str, Any]]) -> None:
    """Atomically write the list of pairs for a (method, path) fixture file."""
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / fixture_filename(method, path)
    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(pairs, f, indent=2, sort_keys=False)
    tmp_path.replace(file_path)
