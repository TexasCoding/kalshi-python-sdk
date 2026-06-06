"""Tests for FIX connectivity config."""

from __future__ import annotations

import pytest

from kalshi.fix.config import (
    FixConfig,
    FixEnvironment,
    FixProduct,
    FixSessionType,
)


def test_prediction_production_hosts_and_ports() -> None:
    c = FixConfig.prediction(environment=FixEnvironment.PRODUCTION)
    assert c.host_for(FixSessionType.ORDER_ENTRY_NR) == "mm.fix.elections.kalshi.com"
    assert c.port_for(FixSessionType.ORDER_ENTRY_NR) == 8228
    assert c.port_for(FixSessionType.ORDER_ENTRY_RT) == 8230
    assert c.port_for(FixSessionType.DROP_COPY) == 8229
    assert c.port_for(FixSessionType.POST_TRADE) == 8231
    assert c.port_for(FixSessionType.RFQ) == 8232
    assert c.port_for(FixSessionType.MARKET_DATA) == 8233


def test_prediction_demo_splits_market_data_host() -> None:
    c = FixConfig.prediction(environment=FixEnvironment.DEMO)
    assert c.host_for(FixSessionType.ORDER_ENTRY_NR) == "fix.demo.kalshi.co"
    assert c.host_for(FixSessionType.MARKET_DATA) == "marketdata.fix.demo.kalshi.co"


def test_margin_hosts() -> None:
    prod = FixConfig.margin(environment=FixEnvironment.PRODUCTION)
    assert prod.host_for(FixSessionType.ORDER_ENTRY_NR) == "margin-fix-api.fix.elections.kalshi.com"
    demo = FixConfig.margin(environment=FixEnvironment.DEMO)
    assert demo.host_for(FixSessionType.ORDER_ENTRY_NR) == "margin-fix.demo.kalshi.co"
    assert demo.host_for(FixSessionType.MARKET_DATA) == "margin-marketdata.fix.demo.kalshi.co"


def test_target_comp_id_is_session_value() -> None:
    c = FixConfig.prediction()
    assert c.target_comp_id(FixSessionType.ORDER_ENTRY_NR) == "KalshiNR"
    assert c.target_comp_id(FixSessionType.MARKET_DATA) == "KalshiMD"


def test_retransmission_only_on_rt_and_pt() -> None:
    c = FixConfig.prediction()
    assert c.supports_retransmission(FixSessionType.ORDER_ENTRY_RT)
    assert c.supports_retransmission(FixSessionType.POST_TRADE)
    assert not c.supports_retransmission(FixSessionType.ORDER_ENTRY_NR)
    assert not c.supports_retransmission(FixSessionType.DROP_COPY)
    assert not c.supports_retransmission(FixSessionType.MARKET_DATA)


def test_margin_disallows_post_trade_and_rfq() -> None:
    c = FixConfig.margin()
    assert FixSessionType.POST_TRADE not in c.allowed_sessions
    assert FixSessionType.RFQ not in c.allowed_sessions
    with pytest.raises(ValueError, match="not available for product"):
        c.host_for(FixSessionType.RFQ)


def test_margin_forces_use_dollars() -> None:
    assert FixConfig.margin().effective_use_dollars is True
    # Even constructing margin directly without the factory enforces dollars.
    assert FixConfig(product=FixProduct.MARGIN).effective_use_dollars is True


def test_prediction_defaults_to_cents() -> None:
    assert FixConfig.prediction().effective_use_dollars is False
    assert FixConfig.prediction(use_dollars=True).effective_use_dollars is True


def test_host_port_override() -> None:
    c = FixConfig.prediction(host="127.0.0.1", port=9999, use_tls=False)
    assert c.host_for(FixSessionType.ORDER_ENTRY_NR) == "127.0.0.1"
    assert c.port_for(FixSessionType.MARKET_DATA) == 9999


def test_rejects_low_heartbeat() -> None:
    with pytest.raises(ValueError, match="heartbeat_interval"):
        FixConfig.prediction(heartbeat_interval=2)


def test_per_product_heartbeat_floor() -> None:
    # Prediction requires > 3; margin requires >= 3.
    with pytest.raises(ValueError, match="heartbeat_interval"):
        FixConfig.prediction(heartbeat_interval=3)
    assert FixConfig.prediction(heartbeat_interval=4).heartbeat_interval == 4
    assert FixConfig.margin(heartbeat_interval=3).heartbeat_interval == 3


def test_rejects_bad_port() -> None:
    with pytest.raises(ValueError, match="port"):
        FixConfig.prediction(port=70000)


def test_rejects_plaintext_to_remote_host() -> None:
    with pytest.raises(ValueError, match="use_tls"):
        FixConfig.prediction(host="evil.example.com", use_tls=False, allow_unknown_host=True)


def test_rejects_unknown_host_without_optin() -> None:
    with pytest.raises(ValueError, match="not a known Kalshi FIX endpoint"):
        FixConfig.prediction(host="evil.example.com")


def test_allows_unknown_host_with_optin() -> None:
    c = FixConfig.prediction(host="proxy.internal", allow_unknown_host=True)
    assert c.host_for(FixSessionType.ORDER_ENTRY_NR) == "proxy.internal"


def test_loopback_plaintext_allowed() -> None:
    c = FixConfig.prediction(host="127.0.0.1", port=8228, use_tls=False)
    assert c.host_for(FixSessionType.ORDER_ENTRY_NR) == "127.0.0.1"


def test_rejects_plaintext_without_host_override() -> None:
    # No host override resolves to the real gateway, which mandates TLS.
    with pytest.raises(ValueError, match="use_tls"):
        FixConfig.prediction(use_tls=False)
    with pytest.raises(ValueError, match="use_tls"):
        FixConfig.margin(use_tls=False)
