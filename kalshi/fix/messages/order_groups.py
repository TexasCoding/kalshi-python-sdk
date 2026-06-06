"""Order-group FIX messages (GH #427).

Order groups ride the order-entry session (no dedicated session type) and manage
automatic position limits: an ``OrderGroupRequest`` (35=UOG) creates / resets /
deletes / triggers / updates a group, and the gateway replies with an
``OrderGroupResponse`` (35=UOH). ``OrderGroupID`` (20130) is then carried on
``NewOrderSingle`` / ``OrderCancelReplaceRequest`` to bind orders to the group.

Groups are scoped per subaccount: a follow-up action (reset/delete/trigger/
update) must pass the same ``AllocAccount`` (79) the group was created under, or
the exchange returns a ``BusinessMessageReject`` (35=j). Build requests via the
:meth:`~OrderGroupRequest.create` / :meth:`~OrderGroupRequest.reset` /
:meth:`~OrderGroupRequest.delete` / :meth:`~OrderGroupRequest.trigger` /
:meth:`~OrderGroupRequest.update` helpers, which encode each action's required
fields (Create omits ``OrderGroupID`` — the server generates it).
"""

from __future__ import annotations

from kalshi.fix.enums import MsgType, OrderGroupAction
from kalshi.fix.messages.base import FixMessage, FixType, fixfield
from kalshi.fix.tags import Tag


class OrderGroupRequest(FixMessage):
    """OrderGroupRequest (35=UOG) — create/reset/delete/trigger/update a group.

    Field order follows the docs examples (action, id, contracts-limit, account);
    FIX scalar field order is not significant, so the helpers below are the
    intended construction path.
    """

    MSG_TYPE = MsgType.ORDER_GROUP_REQUEST

    order_group_action: OrderGroupAction = fixfield(Tag.ORDER_GROUP_ACTION, FixType.INT)
    order_group_id: str | None = fixfield(Tag.ORDER_GROUP_ID, FixType.STRING, default=None)
    order_group_contracts_limit: int | None = fixfield(
        Tag.ORDER_GROUP_CONTRACTS_LIMIT, FixType.INT, default=None
    )
    # Kalshi types AllocAccount (79) as INT — the subaccount number (0 primary,
    # 1-32). Scopes the action to the group owned by that subaccount.
    alloc_account: int | None = fixfield(Tag.ALLOC_ACCOUNT, FixType.INT, default=None)

    @classmethod
    def create(
        cls, contracts_limit: int, *, alloc_account: int | None = None
    ) -> OrderGroupRequest:
        """Create a group with a contracts limit (the server assigns the id)."""
        return cls(
            order_group_action=OrderGroupAction.CREATE,
            order_group_contracts_limit=contracts_limit,
            alloc_account=alloc_account,
        )

    @classmethod
    def reset(cls, order_group_id: str, *, alloc_account: int | None = None) -> OrderGroupRequest:
        """Reset a group's rolling contract count."""
        return cls(
            order_group_action=OrderGroupAction.RESET,
            order_group_id=order_group_id,
            alloc_account=alloc_account,
        )

    @classmethod
    def delete(cls, order_group_id: str, *, alloc_account: int | None = None) -> OrderGroupRequest:
        """Delete a group (cancels all resting orders in it)."""
        return cls(
            order_group_action=OrderGroupAction.DELETE,
            order_group_id=order_group_id,
            alloc_account=alloc_account,
        )

    @classmethod
    def trigger(cls, order_group_id: str, *, alloc_account: int | None = None) -> OrderGroupRequest:
        """Trigger a group — immediately cancel all its orders (TriggerCancel=4)."""
        return cls(
            order_group_action=OrderGroupAction.TRIGGER_CANCEL,
            order_group_id=order_group_id,
            alloc_account=alloc_account,
        )

    @classmethod
    def update(
        cls, order_group_id: str, contracts_limit: int, *, alloc_account: int | None = None
    ) -> OrderGroupRequest:
        """Update a group's contracts limit."""
        return cls(
            order_group_action=OrderGroupAction.UPDATE,
            order_group_id=order_group_id,
            order_group_contracts_limit=contracts_limit,
            alloc_account=alloc_account,
        )


class OrderGroupResponse(FixMessage):
    """OrderGroupResponse (35=UOH) — the gateway's reply to an OrderGroupRequest.

    ``order_group_contracts_limit`` is echoed only on Create and Update responses.
    Fields are optional for inbound robustness; business-logic errors arrive as a
    ``BusinessMessageReject`` (35=j), malformed fields as a session Reject (35=3).
    """

    MSG_TYPE = MsgType.ORDER_GROUP_RESPONSE

    order_group_id: str | None = fixfield(Tag.ORDER_GROUP_ID, FixType.STRING, default=None)
    order_group_contracts_limit: int | None = fixfield(
        Tag.ORDER_GROUP_CONTRACTS_LIMIT, FixType.INT, default=None
    )
    alloc_account: int | None = fixfield(Tag.ALLOC_ACCOUNT, FixType.INT, default=None)
