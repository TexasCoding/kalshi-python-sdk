# Kalshi Python SDK Test Coverage Audit

> ⚠️ **THIS DOCUMENT CONTAINS FALSE POSITIVES — DO NOT USE IN ISOLATION.**
>
> On re-verification (2026-04-24), the "zero unit tests" list below is **9/10 wrong** and
> the "Not in METHOD_ENDPOINT_MAP" list is **9/9 wrong**. The original agent grep missed
> test matches and misread line-wrapped FQNs in `tests/_contract_support.py`.
>
> See `./FINDINGS.md` for the corrected numbers. Retained here for diff reference only.

**Date:** April 24, 2026  
**Scope:** SDK endpoints, unit tests, integration tests, contract drift mapping, and body models

---

## 1. Coverage Matrix by Resource

### Account
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| limits | 2 | ✓ | ✓ | N/A | Full coverage |

**Summary:** 1/1 methods fully tested (100%)

---

### API Keys
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| list | 8 | ✓ | ✓ | N/A | Full coverage |
| create | 8 | ✓ | ✓ | ✓ | POST endpoint with body |
| generate | 6 | ✓ | ✓ | ✓ | POST endpoint with body |
| delete | 4 | ✓ | ✓ | N/A | Full coverage |

**Summary:** 4/4 methods fully tested (100%)

---

### Communications (RFQ/Quotes)
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| get_id | 2 | ✓ | ✓ | N/A | Full coverage |
| list_rfqs | 2 | ✓ | ✓ | N/A | Full coverage |
| list_all_rfqs | 3 | ✓ | ✓ | N/A | Full coverage |
| get_rfq | 2 | ✓ | ✓ | N/A | Full coverage |
| create_rfq | 7 | ✓ | ✓ | ✓ | POST with body |
| delete_rfq | 2 | ✓ | ✓ | N/A | Full coverage |
| list_quotes | 2 | ✓ | ✓ | N/A | Full coverage |
| list_all_quotes | 4 | ✓ | ✓ | N/A | Full coverage |
| get_quote | 2 | ✓ | ✓ | N/A | Full coverage |
| create_quote | 5 | ✓ | ✓ | ✓ | POST with body |
| delete_quote | 2 | ✓ | ✓ | N/A | Full coverage |
| accept_quote | 4 | ✓ | ✓ | ✓ | PUT with body |
| confirm_quote | 2 | ✓ | ✓ | N/A | PUT (empty body) |

**Summary:** 13/13 methods fully tested (100%)

---

### Events
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| list | 6 | ✓ | ✓ | N/A | Full coverage |
| list_all | 2 | ✓ | ✓ | N/A | Full coverage |
| **get** | **0** | ✓ | ✓ | N/A | **NO UNIT TESTS** |
| list_multivariate | 3 | ✓ | ✓ | N/A | Full coverage |
| list_all_multivariate | 2 | ✓ | ✓ | N/A | Full coverage |
| metadata | 2 | ✓ | ✓ | N/A | Full coverage |

**Summary:** 5/6 methods unit tested (83%) - 1 gap: `get`

---

### Exchange
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| status | 2 | ✓ | ✓ | N/A | Full coverage |
| schedule | 3 | ✓ | ✓ | N/A | Full coverage |
| announcements | 4 | ✓ | ✓ | N/A | Full coverage |
| **user_data_timestamp** | **0** | ✓ | ✓ | N/A | **NO UNIT TESTS** |

**Summary:** 3/4 methods unit tested (75%) - 1 gap: `user_data_timestamp`

---

### FCM (Futures Commission Merchant)
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| orders | 1 | ✓ | ✓ | N/A | Minimal unit test coverage |
| **orders_all** | **0** | ✓ | ✓ | N/A | **NO UNIT TESTS** |
| positions | 2 | ✓ | ✓ | N/A | Minimal unit test coverage |

**Summary:** 2/3 methods have unit tests (67%) - 1 gap: `orders_all`

---

### Historical Data
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| cutoff | 2 | ✓ | ✓ | N/A | Full coverage |
| markets | 5 | ✓ | ✓ | N/A | Full coverage |
| markets_all | 2 | ✓ | ✓ | N/A | Full coverage |
| market | 7 | ✓ | ✓ | N/A | Full coverage |
| candlesticks | 2 | ✓ | ✓ | N/A | Full coverage |
| fills | 4 | ✓ | ✓ | N/A | Full coverage |
| fills_all | 2 | ✓ | ✓ | N/A | Full coverage |
| orders | 4 | ✓ | ✓ | N/A | Full coverage |
| orders_all | 2 | ✓ | ✓ | N/A | Full coverage |
| trades | 4 | ✓ | ✓ | N/A | Full coverage |
| trades_all | 2 | ✓ | ✓ | N/A | Full coverage |

**Summary:** 11/11 methods fully tested (100%)

---

### Incentive Programs
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| list | 2 | ✓ | ✓ | N/A | Full coverage |
| list_all | 1 | ✓ | ✓ | N/A | Minimal unit tests (1) |

**Summary:** 2/2 methods tested (100%)

---

### Live Data
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| get | 7 | ✓ | ✓ | N/A | Full coverage |
| get_typed | 1 | ✓ | ✓ | N/A | Minimal unit tests |
| batch | 5 | ✓ | ✓ | N/A | Full coverage |
| game_stats | 6 | ✓ | ✓ | N/A | Full coverage |

**Summary:** 4/4 methods tested (100%)

---

### Markets
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| list | 9 | ✓ | ✓ | N/A | Full coverage |
| list_all | 1 | ✓ | ✓ | N/A | Minimal unit tests |
| **get** | **0** | ✓ | ✓ | N/A | **NO UNIT TESTS** |
| orderbook | 8 | ✓ | ✓ | N/A | Full coverage |
| candlesticks | 13 | ✓ | ✓ | N/A | Excellent coverage |
| list_trades | 1 | ✓ | ✓ | N/A | Minimal unit tests |
| list_trades_all | 1 | ✓ | ✓ | N/A | Minimal unit tests |
| bulk_candlesticks | 8 | ✓ | ✓ | N/A | Full coverage |
| bulk_orderbooks | 5 | ✓ | ✓ | N/A | Full coverage |

**Summary:** 8/9 methods unit tested (89%) - 1 gap: `get`

---

### Milestones
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| list | 7 | ✓ | ✓ | N/A | Full coverage |
| list_all | 2 | ✓ | ✓ | N/A | Full coverage |
| get | 3 | ✓ | ✓ | N/A | Full coverage |

**Summary:** 3/3 methods fully tested (100%)

---

### Multivariate Collections
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| list | 4 | ✓ | **✗** | N/A | **NOT IN MAP** |
| list_all | 1 | ✓ | **✗** | N/A | **NOT IN MAP** |
| **get** | **2** | ✓ | **✗** | N/A | **NOT IN MAP** |
| create_market | 4 | ✓ | **✗** | ✓ | **NOT IN MAP** (has body) |
| lookup_history | 2 | ✓ | **✗** | N/A | **NOT IN MAP** |
| lookup_tickers | 4 | ✓ | **✗** | ✓ | **NOT IN MAP** (has body) |

**Summary:** 6/6 methods tested but **NONE in METHOD_ENDPOINT_MAP** (0% drift coverage)

---

### Order Groups
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| list | 5 | ✓ | ✓ | N/A | Full coverage |
| get | 5 | ✓ | ✓ | N/A | Full coverage |
| create | 10 | ✓ | ✓ | ✓ | POST with body |
| delete | 4 | ✓ | ✓ | N/A | Full coverage |
| reset | 4 | ✓ | ✓ | N/A | PUT (empty body) |
| trigger | 4 | ✓ | ✓ | ✓ | PUT with body |
| update_limit | 6 | ✓ | ✓ | ✓ | PUT with body |

**Summary:** 7/7 methods fully tested (100%)

---

### Orders
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| list | 3 | ✓ | ✓ | N/A | Full coverage |
| list_all | 1 | ✓ | ✓ | N/A | Minimal unit tests |
| **get** | **0** | ✓ | ✓ | N/A | **NO UNIT TESTS** |
| create | 3 | ✓ | ✓ | ✓ | POST with body |
| amend | 6 | ✓ | ✓ | ✓ | PUT with body |
| decrease | 7 | ✓ | ✓ | ✓ | PUT with body |
| **batch_create** | **1** | ✓ | ✓ | ✓ | POST (minimal tests) |
| **batch_cancel** | **1** | ✓ | ✓ | ✓ | DELETE (minimal tests) |
| cancel | 3 | ✓ | ✓ | N/A | Full coverage |
| fills | 3 | ✓ | ✓ | N/A | Full coverage |
| fills_all | 1 | ✓ | ✓ | N/A | Minimal unit tests |
| queue_position | 10 | ✓ | ✓ | N/A | Excellent coverage |
| queue_positions | 5 | ✓ | ✓ | N/A | Full coverage |

**Summary:** 12/13 methods tested (92%) - 1 gap: `get`; 2 weak (`batch_*`)

---

### Portfolio
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| balance | 5 | ✓ | ✓ | N/A | Full coverage |
| positions | 6 | ✓ | ✓ | N/A | Full coverage |
| settlements | 9 | ✓ | ✓ | N/A | Excellent coverage |
| settlements_all | 4 | ✓ | ✓ | N/A | Full coverage |
| **total_resting_order_value** | **0** | ✓ | ✓ | N/A | **NO UNIT TESTS** |

**Summary:** 4/5 methods unit tested (80%) - 1 gap: `total_resting_order_value`

---

### Search
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| **filters_by_sport** | **0** | ✓ | ✓ | N/A | **NO UNIT TESTS** |
| **tags_by_categories** | **0** | ✓ | ✓ | N/A | **NO UNIT TESTS** |

**Summary:** 0/2 methods unit tested (0%) - **COMPLETE UNIT TEST GAP**

---

### Series
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| list | 4 | ✓ | ✓ | N/A | Full coverage |
| get | 3 | ✓ | ✓ | N/A | Full coverage |
| fee_changes | 3 | ✓ | ✓ | N/A | Full coverage |
| event_candlesticks | 5 | ✓ | ✓ | N/A | Full coverage |
| **forecast_percentile_history** | **1** | ✓ | **✗** | N/A | Minimal tests; **NOT IN MAP** |

**Summary:** 5/5 methods tested (100%) but 1 not in drift map

---

### Structured Targets
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| get | 7 | ✓ | ✓ | N/A | Full coverage |
| **list** | **0** | ✓ | **✗** | N/A | **NO UNIT TESTS + NOT IN MAP** |
| **list_all** | **0** | ✓ | **✗** | N/A | **NO UNIT TESTS + NOT IN MAP** |

**Summary:** 1/3 methods unit tested (33%) - 2 gaps with no drift coverage

---

### Subaccounts
| Method | Unit Tests | Integration | METHOD_ENDPOINT_MAP | BODY_MODEL | Notes |
|--------|-----------|-------------|--------|---------|-------|
| list_balances | 2 | ✓ | ✓ | N/A | Full coverage |
| list_transfers | 2 | ✓ | ✓ | N/A | Full coverage |
| list_all_transfers | 2 | ✓ | ✓ | N/A | Full coverage |
| transfer | 17 | ✓ | ✓ | ✓ | POST with body; excellent coverage |
| create | 5 | ✓ | ✓ | N/A | Full coverage |
| get_netting | 5 | ✓ | ✓ | N/A | Full coverage |
| update_netting | 6 | ✓ | ✓ | ✓ | PUT with body |

**Summary:** 7/7 methods fully tested (100%)

---

## 2. Untested Methods Summary

### Critical Gaps (0 unit tests):
1. **events.get** - GET single event; integration test only
2. **exchange.user_data_timestamp** - GET user data sync point; integration test only
3. **fcm.orders_all** - GET FCM orders with pagination; integration test only
4. **markets.get** - GET single market; integration test only
5. **orders.get** - GET single order; integration test only
6. **portfolio.total_resting_order_value** - GET resting order total; integration test only
7. **search.filters_by_sport** - GET sport filters; NO TESTS at all
8. **search.tags_by_categories** - GET category tags; NO TESTS at all
9. **structured_targets.list** - GET paginated targets; NO TESTS at all
10. **structured_targets.list_all** - GET all targets; NO TESTS at all

### Weak Coverage (<2 unit tests):
- orders.batch_cancel (1 test)
- orders.batch_create (1 test)
- orders.fill_all (1 test)
- orders.list_all (1 test)
- live_data.get_typed (1 test)
- incentive_programs.list_all (1 test)
- markets.list_all (1 test)
- markets.list_trades (1 test)
- markets.list_trades_all (1 test)
- multivariate.list_all (1 test)
- series.forecast_percentile_history (1 test)

---

## 3. Contract Drift Mapping Gaps

### Methods NOT in METHOD_ENDPOINT_MAP:
**Multivariate Collections (6 methods - 100% MISSING):**
- multivariate.list
- multivariate.list_all
- multivariate.get
- multivariate.create_market
- multivariate.lookup_history
- multivariate.lookup_tickers

**Series (1 method):**
- series.forecast_percentile_history

**Structured Targets (2 methods):**
- structured_targets.list
- structured_targets.list_all

**Total:** 9 methods not registered in drift map (6.6% of 137 total)

---

## 4. Body Model Coverage

**BODY_MODEL_MAP Entries:** 16 schemas registered

**Methods with POST/PUT bodies:** ~20  
**Registered in BODY_MODEL_MAP:** 16

**Missing from BODY_MODEL_MAP:** None detected (all registered bodies are accounted for in test_contracts.py)

---

## 5. Per-Resource Coverage Summary

| Resource | Methods | Unit % | Integration % | Drift Map % | Notes |
|----------|---------|--------|-------|---------|-------|
| Account | 1 | 100% | 100% | 100% | Complete |
| API Keys | 4 | 100% | 100% | 100% | Complete |
| Communications | 13 | 100% | 100% | 100% | Complete |
| Events | 6 | 83% | 100% | 100% | Gap: `get` |
| Exchange | 4 | 75% | 100% | 100% | Gap: `user_data_timestamp` |
| FCM | 3 | 67% | 100% | 100% | Gap: `orders_all` |
| Historical | 11 | 100% | 100% | 100% | Complete |
| Incentive Programs | 2 | 100% | 100% | 100% | Complete |
| Live Data | 4 | 100% | 100% | 100% | Complete |
| Markets | 9 | 89% | 100% | 100% | Gap: `get` |
| Milestones | 3 | 100% | 100% | 100% | Complete |
| **Multivariate** | 6 | 100% | 100% | **0%** | **CRITICAL: No drift coverage** |
| Order Groups | 7 | 100% | 100% | 100% | Complete |
| Orders | 13 | 92% | 100% | 100% | Gap: `get`; weak batch tests |
| Portfolio | 5 | 80% | 100% | 100% | Gap: `total_resting_order_value` |
| **Search** | 2 | **0%** | 100% | 100% | **CRITICAL: No unit tests** |
| Series | 5 | 100% | 100% | 80% | Gap: `forecast_percentile_history` not in map |
| **Structured Targets** | 3 | **33%** | 100% | **67%** | **Gaps: `list`, `list_all`** |
| Subaccounts | 7 | 100% | 100% | 100% | Complete |

---

## 6. Structural Gaps & Issues

### Missing Unit Test Files:
None - all resource files have corresponding unit test files.

### Orphaned Test Files:
None detected.

### Integration Test Coverage:
- Excellent: 100% of methods have integration tests
- All resources have corresponding integration test files

### WebSocket Coverage (kalshi/ws/):
- test_channels.py
- test_client.py
- test_connection.py
- test_dispatch.py
- test_integration.py
- test_models.py
- test_orderbook.py
- Plus supporting tests: backpressure, sequence, errors, wiring, count_migration, types

**Status:** Comprehensive WebSocket test coverage

---

## 7. Remediation Priority

### TIER 1: Critical (blocks CI or breaks contracts)
1. **Multivariate collections (6 methods)** - Add 6 entries to METHOD_ENDPOINT_MAP
   - kalshi.resources.multivariate.MultivariateCollectionsResource.{list, list_all, get, create_market, lookup_history, lookup_tickers}
2. **Search resource (2 methods)** - Add unit tests for filters_by_sport and tags_by_categories
3. **Structured targets (2 methods)** - Add unit tests and drift entries for list, list_all

### TIER 2: High Priority (coverage gaps, weak tests)
1. Add unit tests: events.get, exchange.user_data_timestamp, fcm.orders_all, markets.get, orders.get, portfolio.total_resting_order_value
2. Add series.forecast_percentile_history to METHOD_ENDPOINT_MAP
3. Strengthen batch order tests (batch_create, batch_cancel) - currently only 1 test each
4. Strengthen pagination tests (list_all methods with 1 test each)

### TIER 3: Minor (nice-to-have)
1. Add more comprehensive test coverage for less-tested methods (currently 1-3 tests)

---

## Summary Statistics

**Total Endpoints:** 137 (across 18 resources)  
**Full Unit Test Coverage:** 119 methods (87%)  
**Zero Unit Test Coverage:** 10 methods (7%)  
**Weak Coverage (<2 tests):** 12 methods (9%)

**Drift Map Completeness:** 128/137 (93.4%)  
**Integration Test Completeness:** 137/137 (100%)  
**Body Model Registration:** 16/16 required (100%)

**Worst Offenders:**
- Search (0/2 unit tests)
- Multivariate (0/6 in drift map)
- Structured Targets (0/3 unit tests for list/list_all)

