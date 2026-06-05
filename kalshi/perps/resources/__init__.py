"""Kalshi Perps (margin) API resource modules.

Each module defines a sync ``*Resource`` and an ``Async*Resource`` pair that
reuse the prediction-API :class:`kalshi.resources._base.SyncResource` /
``AsyncResource`` bases bound to a perps-configured transport. The foundation
issue ships these as minimal stubs; the per-resource perps issues fill in the
endpoint methods.
"""
