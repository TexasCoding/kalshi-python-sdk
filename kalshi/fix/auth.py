"""RSA-PSS logon signer for the Kalshi FIX gateway.

FIX reuses the **same RSA key pair as the REST API**. The Logon (35=A) message
authenticates by placing a base64 RSA-PSS signature in ``RawData`` (tag 96) over
a pre-hash string built from session fields::

    PreHashString = SendingTime + SOH + MsgType + SOH + MsgSeqNum
                                 + SOH + SenderCompID + SOH + TargetCompID

The signature scheme is identical to the REST signer in :mod:`kalshi.auth`
(RSA-PSS, SHA-256, MGF1(SHA-256), salt length = digest length); only the signed
payload differs. ``SenderCompID`` is the API key UUID; ``TargetCompID`` is the
session (e.g. ``KalshiNR``). ``SendingTime`` must be byte-identical to tag 52 in
the Logon and within 30 s of the server clock.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from kalshi.auth import KalshiAuth
from kalshi.fix.codec import SOH
from kalshi.fix.enums import MsgType

# These MUST match the REST signer in kalshi.auth (RSA-PSS / SHA-256 /
# MGF1(SHA-256) / salt_length = digest length). Kept as a local copy rather than
# importing kalshi.auth's private module constants so the scheme is explicit at
# the FIX call site; if kalshi.auth ever changes its padding, update both.
# ``hashes.SHA256()`` is a stateless algorithm *descriptor* (not a live hashing
# context), so a single module-level instance is safe to reuse for both MGF1 and
# the outer sign() call — the same pattern kalshi.auth uses.
_FIX_SHA256 = hashes.SHA256()
_FIX_PSS_PADDING = padding.PSS(
    mgf=padding.MGF1(_FIX_SHA256),
    salt_length=padding.PSS.DIGEST_LENGTH,
)

# The FIX pre-hash uses the SOH delimiter as a string separator.
_SOH_STR = SOH.decode("ascii")


class FixSigner:
    """Signs FIX Logon messages with the account's RSA private key.

    Construct from an existing :class:`~kalshi.auth.KalshiAuth` (the common
    case — the FIX client takes the same auth object as the REST/WS clients) via
    :meth:`from_auth`, or load a key directly with :meth:`from_pem` /
    :meth:`from_key_path` / :meth:`from_env` (which delegate to ``KalshiAuth``'s
    loaders, so PEM handling, OpenSSH detection, and passphrase support are
    shared).
    """

    def __init__(self, sender_comp_id: str, private_key: rsa.RSAPrivateKey) -> None:
        self._sender_comp_id = sender_comp_id
        self._private_key = private_key

    @classmethod
    def from_auth(cls, auth: KalshiAuth) -> FixSigner:
        """Build a signer from an existing :class:`KalshiAuth` (reuses its key)."""
        return cls(auth.key_id, auth.private_key)

    @classmethod
    def from_pem(
        cls,
        key_id: str,
        pem_data: str | bytes,
        *,
        password: bytes | str | Callable[[], bytes | str] | None = None,
    ) -> FixSigner:
        """Load a signer from PEM-encoded private-key content."""
        return cls.from_auth(KalshiAuth.from_pem(key_id, pem_data, password=password))

    @classmethod
    def from_key_path(
        cls,
        key_id: str,
        key_path: str | Path,
        *,
        password: bytes | str | Callable[[], bytes | str] | None = None,
    ) -> FixSigner:
        """Load a signer from a PEM private-key file (``~`` is expanded)."""
        return cls.from_auth(KalshiAuth.from_key_path(key_id, key_path, password=password))

    @classmethod
    def from_env(
        cls,
        *,
        password: bytes | str | Callable[[], bytes | str] | None = None,
    ) -> FixSigner:
        """Load a signer from the ``KALSHI_*`` environment variables.

        Same variables as the REST signer (``KALSHI_KEY_ID`` +
        ``KALSHI_PRIVATE_KEY`` / ``KALSHI_PRIVATE_KEY_PATH``), since FIX shares
        the REST key. For the margin product (separate ``KALSHI_PERPS_*`` key),
        construct via :meth:`from_auth` from the perps auth instead.
        """
        return cls.from_auth(KalshiAuth.from_env(password=password))

    @property
    def sender_comp_id(self) -> str:
        """The API key UUID used as ``SenderCompID`` (tag 49) and in the pre-hash."""
        return self._sender_comp_id

    def build_pre_hash(self, *, sending_time: str, msg_seq_num: int, target_comp_id: str) -> bytes:
        """Build the SOH-joined Logon pre-hash string as bytes (exposed for tests)."""
        parts = [
            sending_time,
            MsgType.LOGON.value,
            str(msg_seq_num),
            self._sender_comp_id,
            target_comp_id,
        ]
        return _SOH_STR.join(parts).encode("utf-8")

    def sign_logon(self, *, sending_time: str, msg_seq_num: int, target_comp_id: str) -> str:
        """Return the base64 RSA-PSS signature for a Logon's ``RawData`` (tag 96).

        ``sending_time`` must equal the Logon's ``SendingTime`` (tag 52) exactly.
        """
        pre_hash = self.build_pre_hash(
            sending_time=sending_time,
            msg_seq_num=msg_seq_num,
            target_comp_id=target_comp_id,
        )
        signature = self._private_key.sign(pre_hash, _FIX_PSS_PADDING, _FIX_SHA256)
        return base64.b64encode(signature).decode("ascii")
