"""FIX tag numbers for the Kalshi dialect (FIX Dictionary v1.03).

A single :class:`Tag` ``IntEnum` is the canonical name<->number mapping used by
the codec and the typed message models. Because :class:`Tag` subclasses ``int``,
members are usable anywhere a raw tag number is expected.

Also exposes :data:`DATA_LENGTH_FIELDS` — the length-prefixed binary/data fields
whose value may legally contain the SOH delimiter and must therefore be read by
byte count (using the immediately-preceding length field) rather than by
scanning for the next SOH.
"""

from __future__ import annotations

from enum import IntEnum


class Tag(IntEnum):
    """FIX field tag numbers (Kalshi dictionary v1.03)."""

    # --- Standard header / trailer ---
    BEGIN_STRING = 8
    BODY_LENGTH = 9
    MSG_TYPE = 35
    SENDER_COMP_ID = 49
    TARGET_COMP_ID = 56
    MSG_SEQ_NUM = 34
    SENDING_TIME = 52
    SENDER_SUB_ID = 50
    SENDER_LOCATION_ID = 142
    TARGET_SUB_ID = 57
    TARGET_LOCATION_ID = 143
    ON_BEHALF_OF_COMP_ID = 115
    DELIVER_TO_COMP_ID = 128
    POSS_DUP_FLAG = 43
    POSS_RESEND = 97
    ORIG_SENDING_TIME = 122
    APPL_VER_ID = 1128
    CSTM_APPL_VER_ID = 1129
    SIGNATURE_LENGTH = 93
    SIGNATURE = 89
    CHECK_SUM = 10

    # --- Session / admin ---
    TEST_REQ_ID = 112
    BEGIN_SEQ_NO = 7
    END_SEQ_NO = 16
    REF_SEQ_NUM = 45
    REF_TAG_ID = 371
    REF_MSG_TYPE = 372
    SESSION_REJECT_REASON = 373
    GAP_FILL_FLAG = 123
    NEW_SEQ_NO = 36
    ENCRYPT_METHOD = 98
    HEART_BT_INT = 108
    RAW_DATA_LENGTH = 95
    RAW_DATA = 96
    RESET_SEQ_NUM_FLAG = 141
    NEXT_EXPECTED_MSG_SEQ_NUM = 789
    MAX_MESSAGE_SIZE = 383
    TEST_MESSAGE_INDICATOR = 464
    USERNAME = 553
    PASSWORD = 554
    DEFAULT_APPL_VER_ID = 1137
    TEXT = 58

    # --- Logon options (Kalshi custom) ---
    CANCEL_ORDERS_ON_DISCONNECT = 8013
    SKIP_PENDING_EXEC_REPORTS = 21011
    USE_DOLLARS = 21005
    CANCEL_ORDER_ON_PAUSE = 21006
    ENABLE_IOC_CANCEL_REPORT = 21007
    LISTENER_SESSION = 20126
    RECEIVE_SETTLEMENT_REPORTS = 20127
    MESSAGE_RETENTION_PERIOD = 20200
    PRESERVE_ORIGINAL_ORDER_QTY = 21008
    USE_EXPIRED_ORD_STATUS = 21012
    ALWAYS_EMIT_NEW_BEFORE_TRADE = 21026

    # --- Order entry ---
    CL_ORD_ID = 11
    ORIG_CL_ORD_ID = 41
    SECONDARY_CL_ORD_ID = 526
    ORDER_ID = 37
    EXEC_INST = 18
    ORDER_QTY = 38
    ORD_TYPE = 40
    PRICE = 44
    SIDE = 54
    SYMBOL = 55
    SECURITY_ID = 48
    TIME_IN_FORCE = 59
    EXPIRE_TIME = 126
    SELF_TRADE_PREVENTION_TYPE = 2964
    ORDER_GROUP_ID = 20130
    MAX_EXECUTION_COST = 21009
    ALLOC_ACCOUNT = 79
    TRANSACT_TIME = 60

    # --- Execution report ---
    EXEC_ID = 17
    EXEC_TYPE = 150
    ORD_STATUS = 39
    LEAVES_QTY = 151
    CUM_QTY = 14
    AVG_PX = 6
    LAST_PX = 31
    LAST_QTY = 32
    ORD_REJ_REASON = 103
    EXEC_RESTATEMENT_REASON = 378
    TRD_MATCH_ID = 880
    AGGRESSOR_INDICATOR = 1057
    LONG_QTY = 704
    SHORT_QTY = 705

    # --- Cancel reject / mass cancel / business reject ---
    CXL_REJ_REASON = 102
    CXL_REJ_RESPONSE_TO = 434
    MASS_CANCEL_REQUEST_TYPE = 530
    MASS_CANCEL_RESPONSE = 531
    MASS_CANCEL_REJECT_REASON = 532
    BUSINESS_REJECT_REF_ID = 379
    BUSINESS_REJECT_REASON = 380

    # --- Parties group ---
    NO_PARTY_IDS = 453
    PARTY_ID = 448
    PARTY_ROLE = 452

    # --- Misc fees group ---
    NO_MISC_FEES = 136
    MISC_FEE_AMT = 137
    MISC_FEE_CURR = 138
    MISC_FEE_TYPE = 139
    MISC_FEE_BASIS = 891

    # --- Collateral changes group ---
    NO_COLLATERAL_AMOUNT_CHANGES = 1703
    COLLATERAL_AMOUNT_CHANGE = 1704
    COLLATERAL_AMOUNT_TYPE = 1705

    # --- RFQ / quoting ---
    QUOTE_ID = 117
    QUOTE_REQ_ID = 131
    BID_PX = 132
    OFFER_PX = 133
    BID_SIZE = 134
    OFFER_SIZE = 135
    NO_RELATED_SYM = 146
    CASH_ORDER_QTY = 152
    QUOTE_STATUS = 297
    QUOTE_CANCEL_STATUS = 298
    QUOTE_REQUEST_TYPE = 303
    QUOTE_REQUEST_REJECT_REASON = 658
    QUOTE_CONFIRM_STATUS = 21010
    RFQ_CANCEL_STATUS = 21013
    REST_REMAINDER = 21015
    REPLACE_EXISTING = 21016
    PREFER_BETTER_QUOTE = 21022
    RFQ_ID = 21023
    ACCEPTED_QUOTE_ID = 21024
    ACCEPT_QUOTE_STATUS = 21025

    # --- Multivariate legs group ---
    MULTIVARIATE_COLLECTION_TICKER = 20180
    NO_MULTIVARIATE_SELECTED_LEGS = 20181
    MULTIVARIATE_SELECTED_EVENT_TICKER = 20182
    MULTIVARIATE_SELECTED_MARKET_TICKER = 20183
    MULTIVARIATE_SELECTED_SIDE = 20184

    # --- Market settlement (post trade) ---
    MARKET_SETTLEMENT_REPORT_ID = 20105
    TOT_NUM_MARKET_SETTLEMENT_REPORTS = 20106
    MARKET_RESULT = 20107
    NO_MARKET_SETTLEMENT_PARTY_IDS = 20108
    MARKET_SETTLEMENT_PARTY_ID = 20109
    MARKET_SETTLEMENT_PARTY_ROLE = 20110
    CLEARING_BUSINESS_DATE = 715
    SETTLEMENT_PRICE = 730
    LAST_FRAGMENT = 893

    # --- Order groups ---
    ORDER_GROUP_ACTION = 20131
    ORDER_GROUP_CONTRACTS_LIMIT = 20132

    # --- Drop copy (event resend) ---
    BEGIN_EXEC_ID = 21001
    END_EXEC_ID = 21002
    RESEND_EVENT_COUNT = 21003
    EVENT_RESEND_REJECT_REASON = 21004

    # --- Market data --- (NoRelatedSym/Symbol/Text reuse the tags above)
    SUBSCRIPTION_REQUEST_TYPE = 263
    NO_MD_ENTRIES = 268
    MD_ENTRY_TYPE = 269
    MD_ENTRY_PX = 270
    MD_ENTRY_SIZE = 271
    MD_UPDATE_ACTION = 279
    MD_REQ_REJ_REASON = 281
    SECURITY_TRADING_STATUS = 326


# Length-prefixed data fields: ``length_tag -> data_tag``. The data field's value
# may legally contain the SOH (\x01) delimiter, so the decoder reads exactly
# ``<length>`` bytes for it instead of scanning to the next SOH. Per FIXT.1.1 the
# length field always immediately precedes its data field.
DATA_LENGTH_FIELDS: dict[int, int] = {
    Tag.RAW_DATA_LENGTH: Tag.RAW_DATA,
    Tag.SIGNATURE_LENGTH: Tag.SIGNATURE,
}
