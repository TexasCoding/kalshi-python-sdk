"""Low-level async TCP/TLS transport for FIX, with frame reassembly.

Wraps :func:`asyncio.open_connection` and a :class:`~kalshi.fix.codec.FixParser`
so callers read whole :class:`~kalshi.fix.codec.RawMessage` frames and write raw
bytes. TLS is on by default (Kalshi requires TLS 1.2+); ``use_tls=False`` is for
loopback mock servers in tests. The session state machine
(:mod:`kalshi.fix.session`) layers logon/heartbeat/sequencing on top.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import ssl

from kalshi.fix.codec import FixParser, RawMessage
from kalshi.fix.errors import FixConnectionError

logger = logging.getLogger("kalshi.fix")

_READ_CHUNK = 65536


class FixConnection:
    """A single FIX TCP/TLS connection with incremental frame reassembly."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        use_tls: bool = True,
        connect_timeout: float = 10.0,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._use_tls = use_tls
        self._connect_timeout = connect_timeout
        self._ssl_context = ssl_context
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._parser = FixParser()

    @property
    def is_open(self) -> bool:
        """True when the writer exists and is not closing."""
        return self._writer is not None and not self._writer.is_closing()

    async def open(self) -> None:
        """Establish the TCP (+TLS) connection.

        Raises:
            FixConnectionError: on connect timeout, refusal, DNS, or TLS failure.
        """
        ssl_arg: ssl.SSLContext | None
        if self._use_tls:
            ssl_arg = (
                self._ssl_context if self._ssl_context is not None else ssl.create_default_context()
            )
        else:
            ssl_arg = None
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port, ssl=ssl_arg),
                timeout=self._connect_timeout,
            )
        except (OSError, ssl.SSLError, TimeoutError) as e:
            # Don't interpolate the raw exception (it can carry the full address);
            # the cause is preserved via __cause__.
            raise FixConnectionError(
                f"FIX connect failed to {self._host}:{self._port}"
            ) from e

    async def send_bytes(self, data: bytes) -> None:
        """Write a complete encoded message to the socket and flush it."""
        if self._writer is None or self._writer.is_closing():
            raise FixConnectionError("cannot send on a closed FIX connection")
        try:
            self._writer.write(data)
            await self._writer.drain()
        except (OSError, ssl.SSLError) as e:
            raise FixConnectionError("FIX send failed") from e

    async def read_message(self) -> RawMessage:
        """Return the next complete message, reading from the socket as needed.

        Raises:
            FixConnectionError: on EOF (peer closed) or a transport error.
            FixCodecError: if the bytes received are malformed framing.
        """
        if self._reader is None:
            raise FixConnectionError("cannot read on an unopened FIX connection")
        while True:
            msg = self._parser.get_message()
            if msg is not None:
                return msg
            try:
                chunk = await self._reader.read(_READ_CHUNK)
            except (OSError, ssl.SSLError) as e:
                raise FixConnectionError("FIX read failed") from e
            if not chunk:
                raise FixConnectionError("FIX connection closed by peer (EOF)")
            self._parser.append(chunk)

    async def close(self) -> None:
        """Close the connection. Idempotent and never raises."""
        writer = self._writer
        self._writer = None
        self._reader = None
        if writer is not None and not writer.is_closing():
            writer.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
