"""Tests for the FIX client facades (FixClient / MarginFixClient)."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi.auth import KalshiAuth
from kalshi.fix import FixClient, FixConfig, FixEnvironment, FixSessionType
from kalshi.perps.fix import MarginFixClient


def test_from_auth_returns_concrete_subclass(rsa_private_key: rsa.RSAPrivateKey) -> None:
    auth = KalshiAuth(key_id="k", private_key=rsa_private_key)

    class Sub(FixClient):
        pass

    assert type(Sub.from_auth(auth)) is Sub  # -> Self, not _BaseFixClient
    assert type(FixClient.from_auth(auth)) is FixClient


def test_from_env_returns_concrete_subclass(
    monkeypatch: pytest.MonkeyPatch, pem_string: str
) -> None:
    monkeypatch.setenv("KALSHI_KEY_ID", "k")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY", pem_string)
    monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)

    class Sub(FixClient):
        pass

    assert type(Sub.from_env(environment=FixEnvironment.DEMO)) is Sub
    assert type(FixClient.from_env(environment=FixEnvironment.DEMO)) is FixClient


def test_prediction_client_exposes_all_sessions(rsa_private_key: rsa.RSAPrivateKey) -> None:
    client = FixClient.from_auth(
        KalshiAuth(key_id="k", private_key=rsa_private_key), environment=FixEnvironment.DEMO
    )
    assert client.order_entry().session_type is FixSessionType.ORDER_ENTRY_NR
    assert client.order_entry(retransmission=True).session_type is FixSessionType.ORDER_ENTRY_RT
    assert client.drop_copy().session_type is FixSessionType.DROP_COPY
    assert client.market_data().session_type is FixSessionType.MARKET_DATA
    assert client.post_trade().session_type is FixSessionType.POST_TRADE
    assert client.rfq().session_type is FixSessionType.RFQ


def test_margin_client_has_no_prediction_only_helpers(
    rsa_private_key: rsa.RSAPrivateKey,
) -> None:
    client = MarginFixClient.from_auth(
        KalshiAuth(key_id="k", private_key=rsa_private_key), environment=FixEnvironment.DEMO
    )
    assert client.order_entry().session_type is FixSessionType.ORDER_ENTRY_NR
    assert not hasattr(client, "rfq")
    assert not hasattr(client, "post_trade")
    # The shared session() path still rejects a prediction-only session for margin.
    with pytest.raises(ValueError, match="not available for product"):
        client.session(FixSessionType.RFQ)


def test_product_config_mismatch_rejected(rsa_private_key: rsa.RSAPrivateKey) -> None:
    auth = KalshiAuth(key_id="k", private_key=rsa_private_key)
    with pytest.raises(ValueError, match="does not match this client's product"):
        FixClient.from_auth(auth, config=FixConfig.margin())
