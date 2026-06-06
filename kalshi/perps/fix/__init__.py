"""Margin (perps) FIX client surface.

A thin facade over the shared FIX core in :mod:`kalshi.fix` — see
:class:`MarginFixClient`. The codec, session engine, and message models are
shared; this package only specializes product, endpoints, dollar pricing, and
credential source. See GH #402.
"""

from __future__ import annotations

from kalshi.perps.fix.client import MarginFixClient

__all__ = ["MarginFixClient"]
