"""Tests for the FIX logon signer."""

from __future__ import annotations

import base64

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from kalshi.auth import KalshiAuth
from kalshi.fix.auth import FixSigner


def _verify(pub: rsa.RSAPublicKey, signature_b64: str, pre_hash: bytes) -> None:
    pub.verify(
        base64.b64decode(signature_b64),
        pre_hash,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )


def test_pre_hash_format(fix_signer: FixSigner) -> None:
    pre = fix_signer.build_pre_hash(
        sending_time="20230809-05:28:18.035", msg_seq_num=1, target_comp_id="KalshiNR"
    )
    assert pre == b"\x01".join(
        [b"20230809-05:28:18.035", b"A", b"1", b"test-api-key-uuid", b"KalshiNR"]
    )


def test_sign_logon_verifies_with_public_key(
    fix_signer: FixSigner, rsa_private_key: rsa.RSAPrivateKey
) -> None:
    sig = fix_signer.sign_logon(
        sending_time="20230809-05:28:18.035", msg_seq_num=1, target_comp_id="KalshiNR"
    )
    pre = fix_signer.build_pre_hash(
        sending_time="20230809-05:28:18.035", msg_seq_num=1, target_comp_id="KalshiNR"
    )
    _verify(rsa_private_key.public_key(), sig, pre)


def test_signature_is_base64(fix_signer: FixSigner) -> None:
    sig = fix_signer.sign_logon(
        sending_time="20230809-05:28:18.035", msg_seq_num=1, target_comp_id="KalshiNR"
    )
    # Decodes cleanly and is the expected length for a 2048-bit key (256 bytes).
    assert len(base64.b64decode(sig)) == 256


def test_tampered_prehash_fails_verification(
    fix_signer: FixSigner, rsa_private_key: rsa.RSAPrivateKey
) -> None:
    sig = fix_signer.sign_logon(
        sending_time="20230809-05:28:18.035", msg_seq_num=1, target_comp_id="KalshiNR"
    )
    wrong = fix_signer.build_pre_hash(
        sending_time="20230809-05:28:18.035", msg_seq_num=2, target_comp_id="KalshiNR"
    )
    with pytest.raises(InvalidSignature):
        _verify(rsa_private_key.public_key(), sig, wrong)


def test_from_auth_reuses_key(rsa_private_key: rsa.RSAPrivateKey) -> None:
    auth = KalshiAuth(key_id="k123", private_key=rsa_private_key)
    signer = FixSigner.from_auth(auth)
    assert signer.sender_comp_id == "k123"
    # Same key object -> a signature over the same pre-hash verifies.
    kw = {"sending_time": "20230809-05:28:18.035", "msg_seq_num": 1, "target_comp_id": "KalshiNR"}
    sig = signer.sign_logon(**kw)
    pre = signer.build_pre_hash(**kw)
    _verify(rsa_private_key.public_key(), sig, pre)


def test_from_pem_loads_key(pem_string: str) -> None:
    signer = FixSigner.from_pem("k456", pem_string)
    assert signer.sender_comp_id == "k456"
    sig = signer.sign_logon(
        sending_time="20230809-05:28:18.035", msg_seq_num=1, target_comp_id="KalshiNR"
    )
    assert len(base64.b64decode(sig)) == 256
