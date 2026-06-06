"""Reassembly of paginated market-settlement reports (GH #429).

A large settlement batch is delivered as several :class:`MarketSettlementReport`
(35=UMS) fragments: each non-final fragment carries ``LastFragment=N`` and a
subset of the parties, the final one ``LastFragment=Y`` (or omitted). Fragments
of one batch are correlated by ``Symbol`` — the ``MarketSettlementReportID``
differs per page, so it cannot be used as the key.

:class:`SettlementReassembler` accumulates each symbol's party entries across
fragments and, on the terminal fragment, returns a single
:class:`MarketSettlementReport` carrying every party.
"""

from __future__ import annotations

import logging

from kalshi.fix.messages.components import MarketSettlementParty
from kalshi.fix.messages.settlement import MarketSettlementReport

logger = logging.getLogger("kalshi.fix")


class SettlementReassembler:
    """Reassemble paginated UMS fragments into one report per settlement batch.

    Usage::

        reasm = SettlementReassembler()
        complete = reasm.add(decode_app_message(raw))  # MarketSettlementReport | None
        if complete is not None:
            ...  # all parties for the batch are in complete.parties

    Assumptions / limitations. ``Symbol`` is the only correlation field (the report
    id differs per page), so this keys solely on it and assumes a batch's fragments
    arrive as one contiguous run terminated by ``LastFragment=Y`` (or a standalone
    report). It does **not** reconcile against ``TotNumMarketSettlementReports``
    (20106). Consequences:

    * Two batches for the *same* symbol must not interleave — a second batch's
      terminal arriving while the first is still buffered would coalesce both into
      one report. A well-formed gateway sends a symbol's fragments contiguously
      (each batch ends with ``LastFragment=Y`` before the next begins), so this
      does not occur in practice; sequential same-symbol batches reassemble
      independently because the buffer clears on each terminal.
    * If a terminal fragment never arrives (mid-batch disconnect), the partial
      parties stay buffered — see :meth:`pending_symbols` — until :meth:`clear`
      (call it on reconnect).
    * A re-delivered terminal fragment re-emits its report, so consumers should
      handle emitted reports idempotently.
    """

    def __init__(self) -> None:
        self._pending: dict[str, list[MarketSettlementParty]] = {}

    def add(self, report: MarketSettlementReport) -> MarketSettlementReport | None:
        """Feed one fragment; return the assembled report on the terminal fragment.

        Returns ``None`` while more fragments are expected (``LastFragment=N``).
        A terminal fragment (``LastFragment`` ``True`` or absent) returns the
        report with every accumulated party; a standalone report is returned
        unchanged. The assembled report carries the *terminal* fragment's
        ``MarketSettlementReportID`` (each page has its own — there is no canonical
        batch id), so key any dedup off ``Symbol`` + clearing date, not that id.
        """
        if report.last_fragment is False:
            # Non-final page: must have a Symbol to correlate the batch.
            if report.symbol is None:
                logger.warning(
                    "settlement fragment without Symbol; dropping %d parties",
                    len(report.parties),
                )
                return None
            self._pending.setdefault(report.symbol, []).extend(report.parties)
            return None

        # Terminal fragment (True or None).
        if report.symbol is not None and report.symbol in self._pending:
            parties = self._pending.pop(report.symbol)
            parties.extend(report.parties)
            return report.model_copy(update={"parties": parties})
        return report

    def pending_symbols(self) -> set[str]:
        """Symbols with buffered fragments still awaiting their terminal page."""
        return set(self._pending)

    def clear(self) -> None:
        """Drop all buffered fragments (e.g. on reconnect).

        Warns when discarding non-empty buffers so silently-dropped partial
        settlement data is observable.
        """
        if self._pending:
            logger.warning(
                "SettlementReassembler.clear() dropping buffered settlement fragments for %s",
                sorted(self._pending),
            )
        self._pending.clear()
