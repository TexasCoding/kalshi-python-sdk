"""Download latest Kalshi OpenAPI + AsyncAPI specs."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path

import httpx

SPECS = {
    "openapi.yaml": "https://docs.kalshi.com/openapi.yaml",
    "asyncapi.yaml": "https://docs.kalshi.com/asyncapi.yaml",
}
SPEC_DIR = Path(__file__).parent.parent / "specs"


def sync_specs(*, retries: int = 3, backoff: float = 2.0) -> dict[str, bool]:
    """Download specs, return {filename: changed} map. Retries on failure."""
    SPEC_DIR.mkdir(exist_ok=True)
    results: dict[str, bool] = {}
    for filename, url in SPECS.items():
        dest = SPEC_DIR / filename
        old_hash = _file_hash(dest) if dest.exists() else None
        for attempt in range(retries):
            try:
                resp = httpx.get(url, timeout=30.0)
                resp.raise_for_status()
                # Atomic write: temp file + rename to prevent partial writes
                fd, tmp = tempfile.mkstemp(dir=SPEC_DIR, suffix=".tmp")
                try:
                    os.write(fd, resp.content)
                    os.close(fd)
                    os.replace(tmp, dest)
                except BaseException:
                    os.close(fd)
                    os.unlink(tmp)
                    raise
                break
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                if attempt == retries - 1:
                    raise RuntimeError(
                        f"Failed to download {url} after {retries} attempts: {e}"
                    ) from e
                time.sleep(backoff * (attempt + 1))
        new_hash = _file_hash(dest)
        results[filename] = old_hash != new_hash
    return results


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    changes = sync_specs()
    for name, changed in changes.items():
        status = "UPDATED" if changed else "unchanged"
        print(f"{name}: {status}")
