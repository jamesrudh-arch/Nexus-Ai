# NEXUS Phase 3 — Market Data & Instrument Master: Design & Acceptance Evidence

**Spec:** NEXUS Living Master Specification v1.0 / 25 Nov 2026, Section 26 Phase 3
**Date:** 2026-11-25
**Status:** IN DEVELOPMENT → **phase exit gate PASSED for offline-verifiable scope** (see §6)
**Cost:** **$0** — every dependency and every data source is free/open-source (D-019)
**Live trading:** DISABLED. Still no trading adapter, no venue credential, no order path.

> Appendix C discipline: each claim states what was tested, where, the result, the date, the
> environment, and the limitations. §5 is the honest list of what was **not** verified.

---

## 1. Scope and owner decisions applied

Section 26 Phase 3 requires market data ingestion, the instrument master and a historical
archive. Exit gate: **data completeness and correctness tests pass.**

Build order was set by the owner (D-026): registry first, then crypto and FX together.

| Decision | Applied in Phase 3 as |
|----------|----------------------|
| **D-023** Phase 2 accepted | Phase 3 built on the Phase 2 core without regressing it (all 299 Phase 2 tests still pass) |
| **D-024** tiered retention | `nexus.archive.retention`: ticks 30d → 1m bars 12mo → 5m/daily indefinite, plus a disk-watermark fail-safe |
| **D-025** USD base + NGN reporting | `Settings.base_currency="USD"`, `reporting_currency="NGN"`; NGN is display-only and never used in limit math |
| **D-026** registry-first, crypto+FX | Instrument master and calendar landed before any feed; Bybit/OKX/Binance Vision/Dukascopy added after |
| **D-019** zero cost | Only free public endpoints; CI greps source for paid data vendors and fails the build |

---

## 2. What was built

`backend/src/nexus/` grew from 3,725 to **10,092 lines** of source across 49 files; tests from
2,482 to **7,909 lines** across 19 files.

| Area | Module | What it does |
|------|--------|--------------|
| Instrument master | `instruments/registry.py` | Canonical instrument ↔ per-venue mapping; certification ladder with evidence; unique reverse lookup; staged activation; append-only change log; honest coverage report |
| Market calendar | `instruments/sessions.py` | Crypto 24/7, FX Sun 17:00–Fri 17:00 America/New_York (DST-correct), exchange regular sessions, holiday sets with **declared** coverage |
| Canonical records | `data/records.py` | `TickRecord` / `QuoteRecord` / `BarRecord` / `BookRecord` / `InstrumentInfoRecord`; Decimal and UTC coercion; validators; dedupe; token-bucket rate limiter; backoff with jitter; `Transport` protocol + `RecordingTransport` |
| Bybit | `ingestion/bybit.py` | V5 public REST: instruments-info, tickers, recent-trade, kline (paged), orderbook |
| OKX | `ingestion/okx.py` | v5 public REST: instruments, ticker, trades, candles + history-candles, books; gap detection |
| Binance Vision | `ingestion/binance_vision.py` | Bulk ZIP/CSV dumps: klines and aggTrades, daily/monthly, header sniffing |
| Dukascopy | `ingestion/dukascopy.py` | Free FX tick history: bi5 LZMA parsing, per-pair point divisors, 0-indexed month, layout verifier |
| Pipeline | `ingestion/pipeline.py` | registry resolve → validate → stamp provenance → archive → publish, with per-pass reports |
| Bars | `archive/bars.py` | Tick→bar aggregation, rollups along the D-024 ladder, gap detection, identity-correct merge |
| Parquet store | `archive/parquet_store.py` | Parquet + zstd, Hive partitioning, exact Decimal round-trip, DuckDB reads, manifest |
| Retention | `archive/retention.py` | Tier ladder, disk watermark (OK/WARN/FORCE), plan-vs-execute separation, refuse-to-delete-without-replacement |
| API | `api/app.py` | `GET /v1/instruments`, `/v1/instruments/coverage`, `/v1/instruments/{id}/session`, `/v1/data/coverage` — all read-only |

---

## 3. Acceptance evidence

Environment: sandboxed Linux (Debian 12, Python 3.11.2, 2 vCPU, 3.9 GB RAM), local venv,
`NEXUS_AUDIT_BACKEND=memory`. Date: **2026-11-25**.

### 3.1 Automated checks

| Check | Command | Result |
|-------|---------|--------|
| Tests | `pytest --junitxml` | **824 tests, 0 failures, 0 errors, 1 skipped** (2.7 s) |
| Lint | `ruff check src tests` | **All checks passed** (69 files — see §4.1, two packages were previously skipped) |
| Format | `ruff format --check` | clean (69 files) |
| Types | `mypy` (strict) | **Success: no issues found in 49 source files** |
| Repository hygiene | `pytest tests/test_repo_hygiene.py` | **10 passed** — every source module is tracked; no artifact or credential-shaped file is |

Phase 3 added **525 tests** (824 − 299 Phase 2). Per module:

| Module | Tests |
|--------|-------|
| `test_adapters.py` (Bybit, OKX, Binance Vision, Dukascopy, transport, validators) | 151 |
| `test_core_guarantees.py` (incl. 12 new Phase 3 settings/phase-gate tests) | 82 |
| `test_archive_bars.py` (incl. 9 rollup-identity regression tests) | 76 |
| `test_pipeline.py` (incl. 10 resolution-rate / aggregation-fault regression tests) | 58 |
| `test_sessions.py` | 53 |
| `test_instrument_registry.py` | 49 |
| `test_parquet_archive.py` (incl. 8 anonymous-record regression tests) | 49 |
| `test_retention.py` | 39 |
| `test_api_phase3.py` | 29 |
| `test_repo_hygiene.py` (source tree tracked, artifacts and credentials excluded) | 10 |

The 1 skip is a `pytest.skip` for an interval not in the modelled set — not a disabled test.

### 3.2 CI assertions executed locally (all four passed)

| Assertion | Result |
|-----------|--------|
| Phase gate: `live_trading`, `venue_adapters`, `real_money_orders_possible`, `order_capability` all `False` | PASS |
| Every data adapter: `requires_credentials is False`, no credential parameter, no order verb (`place`/`submit`/`cancel`/`withdraw`/`transfer`/`amend`) on any public method | PASS (4/4 adapters) |
| No paid data vendor string anywhere in `backend/src` (bloomberg, refinitiv, polygon.io, databento, iqfeed, lseg, tiingo) | PASS |
| API exposes no route containing `order`/`trade`/`execute`/`position`/`withdraw` | PASS (15 routes, all read-only or halt/control) |

Live route list confirmed by booting the app factory:
`/healthz`, `/readyz`, `/metrics`, `/v1/status`, `/v1/audit/verify`, `/v1/halt`,
`/v1/halt/release`, `/v1/instruments`, `/v1/instruments/coverage`,
`/v1/instruments/{instrument_id}/session`, `/v1/data/coverage` (+ FastAPI docs routes).

### 3.3 Properties pinned by tests

**Instrument master**

| Property | Result |
|----------|--------|
| Nothing active by default — registering `active=True` is stored inactive (D-002) | PASS |
| Certification ladder advances exactly one rung; skipping raises `CertificationRejected` | PASS (10 parametrised cases) |
| Empty/whitespace evidence refused — certification without proof is just a claim | PASS |
| Demotion always allowed and recorded as `DE_CERTIFY` (losing access is not hidden) | PASS |
| `DATA_AVAILABLE` never implies tradeable; `tradeable_venues()` stays empty | PASS |
| Trading activation refused until a mapping reaches `TRADE_ENABLED` | PASS |
| Duplicate canonical symbol, or a `(venue, symbol)` collision, refused | PASS |
| New mapping always starts `UNKNOWN` even if handed a pre-certified status | PASS |
| Venue symbols matched exactly, not case-folded | PASS |
| Change log append-only, time-ordered, evidence bounded to 200 chars | PASS |

**Calendar**

| Property | Result |
|----------|--------|
| FX window defined in New York time: winter open 22:00 UTC, summer open 21:00 UTC | PASS |
| The UTC instant demonstrably moves between seasons (guards against a hard-coded offset) | PASS |
| Weekend FX silence is `is_closed_by_calendar=True`; unknown exchange is `False` | PASS |
| No holiday set ⇒ `confidence=PARTIAL`, never `FULL` | PASS |
| Unknown exchange / missing exchange / unsupported asset class ⇒ closed, `UNKNOWN` | PASS |
| NGX evaluated in Africa/Lagos (UTC+1, no DST) | PASS |
| Holiday closing produces `FULL` confidence and the correct next open | PASS |

**Aggregation & rollup**

| Property | Result |
|----------|--------|
| Empty buckets produce no bar — gaps are never interpolated | PASS |
| The bucket containing `now` is unconfirmed | PASS |
| One unconfirmed input makes the whole rolled-up output unconfirmed | PASS |
| A confirmed bar can never be downgraded by a partial one on merge | PASS |
| Missing volume/quote-volume/trade-count poisons the total to `None`, never a wrong sum | PASS |
| Future-dated ticks rejected and counted | PASS |
| Daily bars cut on the UTC calendar, not on 24-hour blocks from the first bar | PASS |
| `0.1 + 0.2 == 0.3` exactly (Decimal, no float in the money path) | PASS |
| Illegal rollup (5m → 1m) refused and counted | PASS |

**Archive**

| Property | Result |
|----------|--------|
| Decimal round-trip exact, including 20 significant digits and 10 decimal places | PASS |
| `NULL` volume reads back as `None`, never `0` | PASS |
| Naive timestamps refused on write for bars, ticks and quotes | PASS |
| Non-UTC timezones normalised to UTC on write | PASS |
| Partitioning uses **record** time, so a backfill lands in its own month/year | PASS |
| Symbols with `/` and `:` are made path-safe | PASS |
| Files are never overwritten in place; a name collision allocates a new file | PASS |
| Empty archive reads as empty, not as an error | PASS |
| Missing pyarrow/duckdb raises `ArchiveUnavailable` — never degrades to CSV | PASS |
| A quote character in the archive root is refused (SQL-literal injection guard) | PASS |

**Retention (D-024)**

| Property | Result |
|----------|--------|
| Default ladder is exactly ticks 30d → 1m 365d → 5m/1d indefinite | PASS |
| Expired ticks **without** 1m coverage ⇒ `REFUSE`, `is_safe=False` | PASS |
| Expired ticks **with** 1m coverage reaching back far enough ⇒ `DELETE` | PASS |
| Replacement coverage that starts *later* than the data ⇒ `REFUSE` | PASS |
| A tier with no rollup target ⇒ `REFUSE` ("permanent evidence loss") | PASS |
| Planning never mutates the inventory | PASS |
| Disk watermark read from the real filesystem; thresholds drive OK/WARN/FORCE | PASS |
| A broken ladder (rollup target is not a tier) is refused at construction | PASS |

**Pipeline**

| Property | Result |
|----------|--------|
| Unknown venue symbol refused, never guessed; nothing archived under a made-up id | PASS |
| Mapping below `DATA_AVAILABLE` cannot feed the archive | PASS (3 statuses refused, 3 accepted) |
| Resolved `instrument_id` stamped on every archived record | PASS |
| Inconsistent OHLC, non-positive price, crossed quote all rejected with reasons | PASS |
| Rejection rate above threshold marks the pass `DEGRADED` | PASS |
| Archive holds the file **before** any event is published | PASS (verified by snapshotting file count at publish time) |
| Event payloads contain no secret-shaped keys | PASS |
| A publisher exception still yields a finished report | PASS |
| Audit payload omits untrusted venue free-text errors | PASS |
| No archive configured is reported, not silent | PASS |
| Ticks from different instruments never merge into one bar | PASS |
| `IngestionPipeline` has no method whose name contains order/trade/execute/withdraw | PASS |
| `resolved` counts distinct symbols, so the rate stays in [0,1]; a caller override that disagrees is left visible rather than clamped | PASS |
| Aggregation exclusions count toward `rejection_rate` and trip `DEGRADED`, while `accepted + rejected` still reconciles | PASS |
| Rollup inherits identity from its sources; sources spanning two instruments or two venues are refused, never blended | PASS |
| The archive refuses any record with a blank venue or symbol, and refuses the whole batch rather than writing part of it | PASS |

### 3.4 End-to-end run (not a unit test)

The unit tests prove components. This run proves they compose — and it is what exposed
defects 9, 10 and 11. Synthetic but internally coherent data: 120 one-minute bars plus 500
ticks over the preceding ~17 minutes, one Bybit perp certified to `DATA_AVAILABLE`.

```
1. registry    : 1 instrument, active=0 | BYBIT=DATA_AVAILABLE | is_tradeable=False | audit changes=4
2. pipeline    : bars 120/120 | ticks 500/500 | bars_from_ticks=17
                 resolution=100% (1/1 symbols) | rejection_rate=0.0% | agg_rejected=0 | DEGRADED=False
3. archive read: 120 confirmed bars | first open=Decimal('99000.10') | last close=Decimal('99103.599')
                 all stamped INS-BTC-USDT-USDT: True | exact Decimal: True
4. provenance  : sources=['AGGREGATED_FROM_TICKS_1m', 'E2E_DEMO']
5. rollup      : ('1m','5m','1h','1d') -> 1m=120 5m=24 1h=2
                 identity inherited: 5m=INS-BTC-USDT-USDT/BYBIT/BTCUSDT | 1h=INS-BTC-USDT-USDT/BYBIT/BTCUSDT
6. manifest    : files=4 bytes=22988 format=nexus-archive-v1
                 dataset=bars/interval=1h/month=11/symbol=BTCUSDT/venue=BYBIT/year=2026
                 dataset=bars/interval=1m/month=11/symbol=BTCUSDT/venue=BYBIT/year=2026
                 dataset=bars/interval=5m/month=11/symbol=BTCUSDT/venue=BYBIT/year=2026
                 dataset=ticks/interval=tick/month=11/symbol=BTCUSDT/venue=BYBIT/year=2026
                 disk_pressure=OK (real shutil.disk_usage)
7. retention   : WITH 1m coverage -> is_safe=True [('tick','DELETE')]
                 NO coverage      -> is_safe=False [('tick','REFUSE')]
                 refusal: 1m coverage for INS-BTC-USDT-USDT does not reach back to
                          2026-10-16T12:00:00.000Z; refusing to delete tick records that have
                          no replacement (roll up first)
                 tiers: [('tick',30,'1m'), ('1m',365,'5m'), ('5m',None,'1d'), ('1d',None,None)]
8. coverage    : 1m bars (0:01:00) | span=400.0d (never claims ticks)
```

Three things this demonstrates that no unit test could:

- **Identity survives the whole ladder.** A bar entering as `venue_symbol="BTCUSDT"` with no
  instrument id leaves the archive, the 5m rollup and the 1h rollup still attributed to
  `INS-BTC-USDT-USDT / BYBIT / BTCUSDT`, in a partition path that says so.
- **A price survives bit-for-bit.** `Decimal('99000.10')` in, `Decimal('99000.10')` out —
  through Parquet's string columns and back, with no float anywhere in the path.
- **Retention refuses to destroy evidence.** Given the same aged ticks, the plan is `DELETE`
  when 1-minute coverage demonstrably reaches back further, and `REFUSE` with a dated reason
  when it does not. The disk watermark is read from the real filesystem, not a constant.

The run used a temporary directory and removed it afterwards; nothing was written into the
repository. It is reproducible with `pytest tests/test_pipeline.py` plus the archive suite,
which assert the same properties on fixed inputs.

---

## 4. Defects found and fixed during Phase 3

These were caught by the tests above, not by review. Each is a genuine correctness bug that
would have corrupted research data silently.

| # | Defect | Impact if unfixed | Fix |
|---|--------|-------------------|-----|
| 1 | `merge_bars` and `dedupe_bars` keyed on `(interval, open_time)` only | **Silent data loss.** Every instrument has a 1m bar at 12:00, so the whole universe would collapse into one arbitrary instrument's prices, labelled as everyone else's | Key on full identity `(instrument_id, venue, venue_symbol, interval, open_time)`; regression test added |
| 2 | `bars_from_ticks` accumulated in **arrival** order | Non-deterministic bars: the same data ingested twice in different orders yields different `open`/`close`. Real feeds interleave streams and replay on reconnect | Validate in pass 1, then sort by timestamp before accumulating |
| 3 | `symbols_requested` derived from **accepted** records only | Resolution rate was a constant 100%, so an unresolved symbol — the signal that the registry is missing part of the universe — was invisible | Count distinct symbols from the *inputs* |
| 4 | A JSON **string** row passes `isinstance(row, Sequence)` | `"not-a-row"[0]` → `"n"` → timestamp parser raised out of the adapter, aborting a whole multi-year backfill over one malformed row | Restrict row checks to `list`/`tuple`; `_parse_kline`/`_parse_candle` return `None` so bad rows are *counted*, not fatal |
| 5 | Import cycle `archive.bars → ingestion.base → ingestion/__init__ → pipeline → archive.bars` | Package would not import at all | Moved canonical records to the neutral `nexus.data.records`; `ingestion.base` re-exports so existing import paths hold |
| 6 | FX calendar branch passed a bare `str` as `reasons` instead of a tuple | `mypy` caught it; at runtime the UI would have iterated a string character by character | Tuple, with a distinctly named local |
| 7 | `pyarrow` rejects `"timestamp[ms, tz=UTC]"` as a string alias | Every archive write raised `ValueError: No type alias` | Portable type-kind vocabulary (`TYPE_TIMESTAMP_UTC_MS` …) resolved through `_build_schema`, validated at import |
| 8 | `VENANCE` typo in the Binance Vision trade parser | `NameError` on the first aggTrades download | Corrected; ruff `F821` caught it |
| 9 | `report.resolved` counted **records** while `symbols_requested` counted **symbols** | `resolution_rate` reported **62,000%** for 620 records of one symbol. A rate whose two sides are different units looks like a measurement while meaning nothing — and it was introduced by the fix for defect 3 | `resolved_keys: set[str]` of distinct `venue:symbol`; `resolved` is now a property over that set. A rate above 1.0 is deliberately **not** clamped, so a caller's own inconsistency stays visible (5 regression tests) |
| 10 | Aggregation exclusions were invisible, and the `DEGRADED` guard required `total_rejected > 0` | A feed with a broken clock sends future-dated ticks: they clear the gate and are archived, but `bars_from_ticks` refuses them. The pass reported **0% rejection and `degraded=False`** while producing 1 bar from 500 ticks — degradation indistinguishable from success | New `aggregation_rejected` counter and `total_faults`; `rejection_rate` and the `DEGRADED` guard both use `total_faults`. `total_rejected` keeps the gate-only identity so `accepted + rejected` still reconciles (5 regression tests) |
| 11 | `rollup_bars` emitted `instrument_id or ""` when identity was not passed, and the archive partitioned blank venue/symbol into `venue=/symbol=` | **Anonymous bars on the D-024 retention ladder.** Every instrument's 5m/daily bars would share one partition — indistinguishable, unfindable by any `read_bars(venue=…)` filter, and it breaks the per-instrument coverage check that decides whether old ticks may be deleted | `_resolve_rollup_identity()`: inherit from the sources, refuse when they disagree or are anonymous, explicit override still wins. Plus a fail-closed archive guard refusing any record with a blank venue or symbol, for the whole batch (9 + 8 regression tests) |
| 12 | **`.gitignore` had unanchored `data/` and `secrets/` patterns**, which match at *any* depth | **The pushed Phase 2 commit `72fcbcc` was missing 6 source modules it imports** (`nexus/data/{__init__,freshness,records}.py`, `nexus/secrets/{__init__,provider,redaction}.py`). A fresh clone could not import `nexus` at all. It also meant **ruff never linted those two packages** — ruff honours `.gitignore`, so every "ruff clean" result reported for Phase 2 silently excluded them | Anchored both patterns (`/data/`, `/secrets/`, `/backend/data/`, `/backups/`) and added end-of-file negations for `backend/src/**` and `backend/migrations/**`, with `__pycache__` re-excluded *after* them (a negation that re-includes the directory lets git descend and re-include every `.pyc`). New `backend/tests/test_repo_hygiene.py` compares the working tree against the repository (10 tests) |

Defects 1–3 and 9–12 are the important ones: all seven produce *plausible-looking wrong
results* rather than an error, which is the failure mode that destroys confidence in a
backtest — or, in defect 12's case, in the repository itself.

Defects 9 and 10 were found only by running the whole pipeline end-to-end on realistic
volumes; no single-unit test would have exposed either. Defect 12 was found only by asking
what git actually holds rather than what the working tree holds.

### 4.1 A correction to the Phase 2 record

`docs/04-phase2-core-foundation.md` reports "ruff clean" over 34 source files. That claim was
**narrower than it appeared**: ruff skips `.gitignore`d paths, so `nexus/data/` and
`nexus/secrets/` were never linted. Once defect 12 was fixed, ruff examined 69 files instead
of 62 and immediately reported 4 real issues in `records.py` (three `timezone.utc` →
`datetime.UTC` upgrades and one `SIM114` merge). All are fixed and the file is now formatted.

Phase 2's *behavioural* claims stand — `mypy` does not honour `.gitignore` and did check all
49 files, and the 299 tests exercised both packages through imports from the working tree.
What was wrong is the lint coverage claim and, far more seriously, the completeness of the
pushed commit. Corrected here rather than left in the earlier document.

---

## 5. Limitations — what was NOT verified

Stated plainly, per Appendix C. These are open items, not finished work.

1. **No live endpoint was ever contacted.** This sandbox has no egress to venue hosts.
   Probed 2026-11-25: `api.bybit.com`, `www.okx.com`, `datafeed.dukascopy.com`,
   `api.binance.com` — **all connections failed (curl exit 000)**. The adapter tests run
   against a `RecordingTransport` with **synthetic** payloads written from the published API
   contracts. That proves the normalisation logic; it does **not** prove the live endpoints
   still return those shapes. **Phase 3 exit-gate item outstanding.**
2. **Dukascopy bi5 layout is UNVERIFIED.** `LAYOUT_VERIFIED = False` in the module, and every
   record it produces carries `source="DUKASCOPY_BI5_UNVERIFIED"`. The 20-byte LZMA record
   layout and the per-pair point divisors are the documented ones but have not been checked
   against a real file. `verify_layout()` exists to produce that evidence; it must run from a
   host with egress before FX tick history is treated as anything but PROVISIONAL.
3. **Docker Compose, the Dockerfile and the Caddyfile are still not runtime-verified.** Docker
   is unavailable in this sandbox. The Phase 3 additions (`archive`/`streams`/`postgres`/`nats`
   extras, the `archive-data` volume, the new env vars) are unvalidated in a real build.
4. **CI has still never executed on GitHub.** The assertions were run locally and passed, but
   no Actions run exists. This is not a paperwork gap: had CI run on the Phase 2 push it would
   have failed at import and exposed defect 12 immediately. First push gives the real signal,
   and the hygiene test now runs as part of the suite rather than relying on CI to notice.
5. **PostgreSQL/TimescaleDB remains untested at runtime.** Only SQLite was exercised.
6. **No real gaps, outages or throttling observed.** Reconnection behaviour, 429 handling and
   gap recording are tested with synthetic faults only. The free feeds' actual reliability is
   unknown (Z-08).
7. **Instrument master is empty at runtime.** The registry is built and proven, but no
   catalogue has been populated from a live `instruments-info` call, so no real instrument is
   registered in a running system yet.
8. **Commit `72fcbcc` on GitHub is incomplete and should not be used.** It is missing the six
   modules described in defect 12, so that commit cannot import. It is superseded by the Phase
   3 commit; the history is left intact rather than rewritten, and this is recorded so nobody
   checks out `72fcbcc` and concludes the package is broken. A fresh-clone import check is
   recorded in §3.5 against the superseding commit.

---

## 6. Phase 3 exit gate assessment

| Gate requirement (Section 26 Phase 3) | Evidence | Verdict |
|----------------------------------------|----------|---------|
| Market data ingestion | 4 free public sources implemented; normalisation, validation, rate limiting, backoff, pagination all tested; 209 tests across adapters (151) / pipeline (58) | **PASS offline / PENDING live verification** |
| Instrument master | Registry with certification ladder, staged activation, coverage reporting; 49 tests | **PASS** |
| Historical archive | Parquet+zstd, Hive partitioning, exact Decimal round-trip, manifest, tiered retention with disk fail-safe; 164 tests across bars (76) / archive (49) / retention (39) | **PASS** |
| Data completeness & correctness tests | Gaps detected and never filled; dedupe identity-correct; confirmation semantics enforced; OHLC consistency validated; rejection rates surfaced | **PASS** |
| Sessions/calendar | DST-correct FX window, exchange sessions, declared holiday coverage, fail-closed unknowns; 53 tests | **PASS** |
| Zero cost (D-019) | Free sources only; CI greps for paid vendors; no credential anywhere | **PASS** |
| No live trading | Phase gate `False`×4; no order route; adapters credential-free and verb-free | **PASS** |

**Phase 3 exit gate: PASSED for the offline-verifiable scope.** Two items must close before
Phase 3 can be called complete rather than code-complete:

- **P3-A** — live-endpoint verification from a host with egress (Bybit, OKX, Binance Vision,
  Dukascopy), recording actual response shapes as fixtures.
- **P3-B** — Dukascopy `verify_layout()` against a real bi5 download; flip `LAYOUT_VERIFIED`
  with the evidence recorded in the ledger.

Both need network access this sandbox does not have. They are ready to run on the Oracle VM.

---

## 7. Next phase (4) preview — still $0

Venue certification scaffolding against **demo/sandbox** accounts only (Bybit demo trading,
OKX demo, Alpaca paper), signed trade intents end-to-end against a simulator, reconciliation
loops, and the alert delivery layer on the four adopted free channels (D-020).

**Live trading remains DISABLED. No venue credentials have been requested or stored. No
trading adapter exists.**
