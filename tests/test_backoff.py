"""Tests for the REST retry backoff calculation.

Regression coverage for #104 — AWS "Full Jitter" replaces the prior
``base * 2**attempt + uniform(0, 0.5)`` additive-jitter formula.
"""
from __future__ import annotations

from kalshi._base_client import _compute_backoff
from kalshi.config import KalshiConfig


def _config(base: float = 0.5, cap: float = 30.0) -> KalshiConfig:
    return KalshiConfig(retry_base_delay=base, retry_max_delay=cap)


def test_full_jitter_stays_within_capped_window() -> None:
    """Every sample must fall in ``[0, min(cap, base * 2**attempt)]``."""
    cfg = _config(base=0.5, cap=4.0)
    for attempt in range(8):
        upper = min(cfg.retry_base_delay * (2**attempt), cfg.retry_max_delay)
        for _ in range(200):
            delay = _compute_backoff(attempt, cfg)
            assert 0.0 <= delay <= upper


def test_full_jitter_spreads_parallel_retries_across_window() -> None:
    """At attempt 0 with base=0.5, additive jitter forced every client into
    [0.5, 1.0] — a 0.5s window. Full Jitter spreads across [0, 0.5], so the
    sample spread should comfortably exceed the legacy 0.5s ceiling-anchored band.
    Specifically: the minimum across many samples must drop well below the legacy
    minimum of 0.5s."""
    cfg = _config(base=0.5, cap=30.0)
    samples = [_compute_backoff(0, cfg) for _ in range(500)]
    assert min(samples) < 0.1, "Full Jitter must allow near-zero delays"
    assert max(samples) <= 0.5
    # Distinct samples — sanity that we're actually randomizing.
    assert len(set(samples)) > 100


def test_full_jitter_respects_retry_max_delay_cap() -> None:
    """Cap must clamp the exponential term before jitter is applied."""
    cfg = _config(base=1.0, cap=2.0)
    # attempt=10 → uncapped would be 1024s; capped to 2s.
    for _ in range(200):
        delay = _compute_backoff(10, cfg)
        assert 0.0 <= delay <= 2.0
