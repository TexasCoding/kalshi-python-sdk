"""eBattle scores channel message models (``ebattle_scores``).

The auth-required ``ebattle_scores`` channel streams live eSoccer/eFootball
and eBasketball score updates. Other sports and esports feeds are excluded.
Public access is temporary and can return to individual approval.

A new subscription is empty until ``subscribe_matches`` is sent. There is no
initial snapshot or replay. Two inbound message types arrive on the same
subscription (both carry ``sid``): ``ebattle_scores`` (data) and
``ebattle_scores_matchlist`` (the response to a ``matchlist``
``update_subscription`` action).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class EbattleScoresPayload(BaseModel):
    """``ebattle_scores.msg`` — one match's current full score state.

    ``data`` is a JSON-encoded string of the full score state (upstream-defined
    and sport-specific, so it is left unparsed — call ``json.loads(msg.data)``
    to read it). ``match_id`` is a Kalshi milestone ID. ``received_at`` is the
    publication timestamp in milliseconds.
    """

    event_id: str
    match_id: str
    received_at: int
    data: str
    model_config = {"extra": "allow", "populate_by_name": True}


class EbattleScoresMessage(BaseModel):
    """``ebattle_scores`` data message envelope."""

    type: Literal["ebattle_scores"] = "ebattle_scores"
    id: int | None = None
    sid: int
    seq: int | None = None
    msg: EbattleScoresPayload
    model_config = {"extra": "allow", "populate_by_name": True}


class EbattleScoresMatchlistPayload(BaseModel):
    """``ebattle_scores_matchlist.msg`` — match IDs seen in the past two hours."""

    match_ids: list[str]
    model_config = {"extra": "allow", "populate_by_name": True}


class EbattleScoresMatchlistMessage(BaseModel):
    """``ebattle_scores_matchlist`` — response to the ``matchlist`` action.

    ``id`` echoes the command id that requested the list; it is absent on
    unsolicited frames, so it is optional. ``match_ids`` is not a complete
    fixture catalog — only IDs seen within the past two hours.
    """

    type: Literal["ebattle_scores_matchlist"] = "ebattle_scores_matchlist"
    id: int | None = None
    sid: int
    seq: int | None = None
    msg: EbattleScoresMatchlistPayload
    model_config = {"extra": "allow", "populate_by_name": True}
