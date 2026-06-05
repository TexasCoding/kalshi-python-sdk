"""Fixtures for FIX tests: an in-memory mock acceptor + signer/config helpers.

The :class:`MockAcceptor` is a plain-TCP asyncio server (loopback, no TLS) that
speaks just enough FIX to drive :class:`kalshi.fix.session.FixSession` through
its state machine: it answers Logon with Logon (or Logout to simulate
rejection), echoes TestRequest with Heartbeat, records everything it receives,
and lets a test ``push`` arbitrary server->client messages with chosen
sequence numbers.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi.fix.auth import FixSigner
from kalshi.fix.codec import FixParser, RawMessage, encode
from kalshi.fix.config import FixConfig, FixEnvironment
from kalshi.fix.tags import Tag

_FIXED_SENDING_TIME = "20250101-00:00:00.000"


class MockAcceptor:
    """A minimal scriptable FIX acceptor for driving FixSession in tests."""

    def __init__(self) -> None:
        self.received: list[RawMessage] = []
        self.client_comp_id: str = ""
        self.reject_logon: bool = False
        self.reject_text: str = "logon rejected by mock"
        # When set, the Logon response carries this MsgSeqNum instead of the
        # auto-incremented one (used to drive logon-time sequence-gap paths).
        self.logon_resp_seq: int | None = None
        self._server: asyncio.AbstractServer | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._out_seq = 1
        self.port = 0
        self.connection_count = 0
        self._connected = asyncio.Event()

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        # Abort any live client connection so the handler task can exit, then
        # bound wait_closed() — it can otherwise block indefinitely waiting on a
        # connection handler that is parked in reader.read().
        if self._writer is not None and not self._writer.is_closing():
            self._writer.close()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self._server.wait_closed(), timeout=1.0)

    async def wait_connected(self) -> None:
        await asyncio.wait_for(self._connected.wait(), timeout=2.0)

    def drop_connection(self) -> None:
        """Forcibly close the current client connection (simulate a disconnect)."""
        if self._writer is not None and not self._writer.is_closing():
            self._writer.close()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connection_count += 1
        # NB: _out_seq persists across connections. The acceptor only resets it
        # when a Logon carries ResetSeqNumFlag=Y (see _respond) — mirroring a real
        # server so RT reconnect/resume (no reset flag) continues the sequence.
        self._writer = writer
        self._connected.set()
        parser = FixParser()
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                parser.append(data)
                for msg in parser.messages():
                    self.received.append(msg)
                    await self._respond(msg, writer)
        except (ConnectionResetError, asyncio.CancelledError, OSError):
            pass
        finally:
            # Clear so wait_connected() blocks until the *next* connection after a
            # drop/reconnect, rather than returning on the stale prior connect.
            self._connected.clear()

    async def _respond(self, msg: RawMessage, writer: asyncio.StreamWriter) -> None:
        mt = msg.msg_type
        if mt == "A":  # Logon
            self.client_comp_id = msg.get(Tag.SENDER_COMP_ID) or ""
            # A real acceptor resets its own sequence only when the client asks
            # (ResetSeqNumFlag=Y on NR/DC/first logon); RT resume keeps continuity.
            if msg.get(Tag.RESET_SEQ_NUM_FLAG) == "Y":
                self._out_seq = 1
            if self.reject_logon:
                await self._send(writer, "5", [(int(Tag.TEXT), self.reject_text)])
            else:
                await self._send(
                    writer,
                    "A",
                    [
                        (int(Tag.ENCRYPT_METHOD), "0"),
                        (int(Tag.HEART_BT_INT), "30"),
                        (int(Tag.DEFAULT_APPL_VER_ID), "9"),
                        (int(Tag.RESET_SEQ_NUM_FLAG), "Y"),
                    ],
                    seq=self.logon_resp_seq,
                )
        elif mt == "1":  # TestRequest -> Heartbeat echo
            trid = msg.get(Tag.TEST_REQ_ID)
            body = [(int(Tag.TEST_REQ_ID), trid)] if trid else []
            await self._send(writer, "0", body)
        # everything else is recorded only

    async def _send(
        self,
        writer: asyncio.StreamWriter,
        msg_type: str,
        body: list[tuple[int, str]],
        *,
        seq: int | None = None,
        poss_dup: bool = False,
    ) -> None:
        s = seq if seq is not None else self._out_seq
        if seq is None:
            self._out_seq += 1
        header: list[tuple[int, str]] = [
            (int(Tag.MSG_TYPE), msg_type),
            (int(Tag.SENDER_COMP_ID), "Kalshi"),
            (int(Tag.TARGET_COMP_ID), self.client_comp_id or "client"),
            (int(Tag.MSG_SEQ_NUM), str(s)),
        ]
        if poss_dup:
            header.append((int(Tag.POSS_DUP_FLAG), "Y"))
        header.append((int(Tag.SENDING_TIME), _FIXED_SENDING_TIME))
        if poss_dup:
            header.append((int(Tag.ORIG_SENDING_TIME), _FIXED_SENDING_TIME))
        writer.write(encode(header + body))
        await writer.drain()

    async def push(
        self,
        msg_type: str,
        body: list[tuple[int, str]] | None = None,
        *,
        seq: int | None = None,
        poss_dup: bool = False,
    ) -> None:
        """Send a server->client message on the current connection."""
        assert self._writer is not None, "no client connected"
        await self._send(self._writer, msg_type, body or [], seq=seq, poss_dup=poss_dup)

    def received_types(self) -> list[str | None]:
        return [m.msg_type for m in self.received]

    def first(self, msg_type: str) -> RawMessage | None:
        for m in self.received:
            if m.msg_type == msg_type:
                return m
        return None


@pytest.fixture
async def acceptor() -> AsyncIterator[MockAcceptor]:
    a = MockAcceptor()
    await a.start()
    try:
        yield a
    finally:
        await a.stop()


@pytest.fixture
def fix_signer(rsa_private_key: rsa.RSAPrivateKey) -> FixSigner:
    return FixSigner("test-api-key-uuid", rsa_private_key)


@pytest.fixture
def fix_config(acceptor: MockAcceptor) -> FixConfig:
    """Prediction config pointed at the loopback mock acceptor (plain TCP)."""
    return FixConfig.prediction(
        environment=FixEnvironment.DEMO,
        host="127.0.0.1",
        port=acceptor.port,
        use_tls=False,
        heartbeat_interval=4,
        connect_timeout=2.0,
        retry_base_delay=0.01,
        retry_max_delay=0.05,
        max_retries=5,
    )


@pytest.fixture
def until() -> Callable[..., Awaitable[None]]:
    """Return an async poller that waits until ``predicate()`` is truthy."""

    async def _until(
        predicate: Callable[[], bool], *, timeout: float = 2.0, interval: float = 0.01
    ) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if predicate():
                return
            await asyncio.sleep(interval)
        raise AssertionError("condition not met within timeout")

    return _until
