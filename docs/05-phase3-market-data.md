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
| Tests | `pytest --junitxml` | **868 tests, 0 failures, 0 errors, 1 skipped** |
| Lint | `ruff check src tests` | **All checks passed** (69 files — see §4.1, two packages were previously skipped) |
| Format | `ruff format --check` | clean (69 files) |
| Types | `mypy` (strict) | **Success: no issues found in 49 source files** |
| Repository & CI hygiene | `pytest tests/test_repo_hygiene.py` | **54 passed** — source tree tracked, no artifacts, CI workflow runnable, image scannable, Trivy report readable, secret scanning not weakened |
| CI on GitHub | Actions, `push` + `pull_request` | **All four jobs green** on both events (§3.6) |

Phase 3 added **569 tests** (868 − 299 Phase 2). Per module:

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
| `test_repo_hygiene.py` (source tree tracked; CI runnable; image scannable; findings readable; the Dockerfile's own assertions) | 54 |

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

### 3.5 Fresh-clone verification (defect 12)

Defect 12 meant a clone of the repository could not import the package. Unit tests run
against the working tree, so they cannot detect that — only a clone can. Verified
2026-11-25 against commit `c9e0576`:

```
$ git clone /home/user/Nexus-Ai clone-verify && cd clone-verify
source modules in the clone ............... 49   (working tree: 49)
data/__init__.py .......................... PRESENT
data/freshness.py ......................... PRESENT
data/records.py ........................... PRESENT
secrets/__init__.py ....................... PRESENT
secrets/provider.py ....................... PRESENT
secrets/redaction.py ...................... PRESENT
artifacts wrongly committed ............... none (.pyc/__pycache__/.parquet/.sqlite/.env)
total tracked files ....................... 86

$ PYTHONPATH=clone-verify/backend/src python -c "import nexus, nexus.data.records, \
      nexus.secrets.provider, nexus.archive.retention, nexus.ingestion.pipeline, \
      nexus.instruments.sessions, nexus.api.app"
nexus loaded from : /tmp/clone-verify/backend/src/nexus/__init__.py
version / phase   : 0.2.0 3-market-data
phase gate        : {'phase': 3, 'live_trading': False, 'venue_adapters': False,
                     'real_money_orders_possible': False, 'market_data_sources': True,
                     'order_capability': False}
redaction         : [REDACTED]
CONFIRMED: every import resolved inside the fresh clone

$ cd clone-verify/backend && pytest -q
FRESH CLONE: tests=824 failures=0 errors=0 skipped=1
```

Three things this establishes: the clone holds every module (49 = 49), the imports resolve
*inside the clone* rather than falling back to the development tree, and the whole suite
passes from a clean checkout. The clone was made in `/tmp` and holds no secrets, no archive
data and no `.env`.

The `.gitignore` guard was additionally verified by **negative control**: appending the old
unanchored `data/` and `secrets/` patterns makes `test_repo_hygiene.py` fail and name all six
modules, and restoring the file makes it pass again. A guard that cannot fail is not a guard —
the first version of this test was vacuous, because `git check-ignore` consults the index and
reports an already-tracked path as "not ignored"; it now passes `--no-index`, which asks the
question that actually matters: what would happen to a fresh clone.

**Re-verified 2026-11-25 against `43a8da2`**, cloned from GitHub rather than from the working
tree, after the CI defects in §4 were fixed:

```
$ git clone --branch arena/06913352-nexus-ai https://github.com/jamesrudh-arch/Nexus-Ai.git
HEAD ...................................... 43a8da2   shallow=false (full history)
tracked files ............................. 87
source modules under backend/src/nexus .... 49        (working tree: 49)
test files ................................ 20
artifacts wrongly committed ............... 0  (.pyc/__pycache__/.venv/.db/.parquet/.env)

$ PYTHONPATH=<clone>/backend/src python -c "import nexus; ..."
import OK: version 0.2.0 phase 3-market-data
redact -> {'api_key': '[REDACTED]'}

$ cd <clone>/backend && pytest -q
CLONE 43a8da2: tests=861 failures=0 errors=0 skipped=1
```

The clone is not shallow, so `test_the_excused_commit_exists_in_this_repository` verified the
excused commit for real rather than skipping — see defect 21 for why that distinction exists.

**Re-verified 2026-11-25 against `40e7ed6`** — the first commit whose CI runs are green on both
events with the image scan blocking on HIGH *and* CRITICAL:

```
$ git clone --branch arena/06913352-nexus-ai https://github.com/jamesrudh-arch/Nexus-Ai.git
HEAD ...................................... 40e7ed6   shallow=false (full history)
tracked files ............................. 87
source modules under backend/src/nexus .... 49        (working tree: 49)
test files ................................ 20
artifacts wrongly committed ............... 0  (.pyc/__pycache__/.venv/.db/.parquet/.env)
scan-suppression files .................... 0  (no .trivyignore, no ignore list of any kind)

$ PYTHONPATH=<clone>/backend/src python -c "import nexus; ..."
import OK: version 0.2.0 phase 3-market-data
redact -> {'api_key': '[REDACTED]'}

$ cd <clone>/backend && pytest -q
CLONE 40e7ed6: tests=868 failures=0 errors=0 skipped=1   (54 hygiene)
```

The suppression count is reported because it is the claim most worth checking. The image scan is
green with **no** exception list, no severity split and no deleted manifest: the finding was
removed from the image rather than excused from the report (§4, defects 22–25 and 30).

### 3.6 CI executed on GitHub

Phase 2's record listed "CI workflow committed but never executed" as a limitation. It has now
executed eighteen times on this branch, and it did not pass first time: **eighteen defects were
found only by running it** (§4, defects 13–30). Every one was invisible to the local suite,
because each is a property of the CI environment or of the built image rather than of the code —
an action ref that does not resolve, a variable a compose file requires, an image a scanner cannot
see, a config key the pinned scanner version does not define, an annotation budget that runs out,
a manifest in a package the dev venv does not install.

**Final state, 2026-11-25, commit `40e7ed6`, branch `arena/06913352-nexus-ai`:**

| Run | Event | Result | Jobs |
|-----|-------|--------|------|
| `45621356165` | `push` | **success** | Backend ✓ · Compose ✓ · Secret scanning ✓ · Container image ✓ |
| `45621369995` | `pull_request` | **success** | Backend ✓ · Compose ✓ · Secret scanning ✓ · Container image ✓ |

All four jobs on both events, with the image scan **blocking on HIGH and CRITICAL** and no
exception list of any kind. The scan's own published verdict on the green run:
`no HIGH or CRITICAL fixable vulnerabilities in nexus-core:ci`.

#### Run history, including the failures

The red runs are recorded because they are where the evidence is. Six consecutive image-job
failures separate the first green run from this one, and each produced a finding that changed the
fix.

| Run | Commit | Event | Result | What it established |
|-----|--------|-------|--------|---------------------|
| `45592289431` | `54516c2` | push | success | First successful multi-arch build (defect 16 fixed) |
| `45595563135` | `1f7d17b` | both | mixed | gitleaks path-allowlist worked on `push`, still failed on `pull_request` (defect 20) |
| `45600837707` / `45600847434` | `68d125e` | both | **success** | First all-green pair; singular `[allowlist]` confirmed against gitleaks 8.24.3 |
| `45602895677` / `45602905437` | `edcefb6` | both | **success** | Findings publisher working — and it immediately named CVE-2025-47273, which the previous runs had been reporting non-blockingly |
| `45604686230` / `45604695540` | `43a8da2` | both | failure | The setuptools **upgrade** did not clear the finding (defect 23) |
| `45607464903` / `45607475361` | `97bce9e` | both | failure | Removal + assertion: the assertion tripped on pip's vendored `pkg_resources` (defect 24) |
| `45607576520` / `45607584395` | `9f07537` | both | failure | Same, plus five F811 redefinitions caught by CI that the local gate had let through (defect 29) |
| `45608526720` / `45608543355` | `98f3815` | both | failure | Diagnostic probe published **nothing but docker pull progress** — the 10-annotation cap (defect 27) |
| `45609519876` / `45609528680` | `fbd0657` | both | failure | Packed probe delivered: **no setuptools is installed anywhere**; the scanner reads pip's vendored CycloneDX SBOM (defect 25) |
| `45617637180` / `45617648641` | `1b0e8ce` | both | failure | Exit codes identified check 22; the probe named `psycopg_binary`'s `auditwheel.cdx.json` as a second, unrelated SBOM (defect 30) |
| `45620461764` / `45620475367` | `ebd9f15` | both | failure | Same as above, with the probe rebuilt to publish the entrypoint traceback and the tzdata measurement |
| `45621356165` / `45621369995` | `40e7ed6` | both | **success** | Scan green with pip removed, the SBOM check retargeted, and no suppression |

Both events matter because they scan different things. A `push` run covers only the new commits; a
`pull_request` run covers the whole branch (`--log-opts=--no-merges --first-parent base^..head`,
where base is the PR's first commit). Secret scanning passed on `push` while still failing on
`pull_request` for three consecutive runs, and that asymmetry is defect 20.

#### Reading CI output at all

Job logs, SARIF artifacts and `gh run download` are not reachable from every environment — the log
endpoints return empty and artifact hosts are unreachable. Two channels do work, and the workflow
was built around them:

- **check annotations**, via `gh api repos/<owner>/<repo>/check-runs/<job-id>/annotations`. The
  findings publisher exists to push Trivy's report into this channel, and the temporary probe used
  it to publish filesystem measurements. GitHub allows **10 annotations per level per step**, so
  each report is packed into one annotation with encoded newlines (defect 27).
- **PR review comments**, which is how the gitleaks findings were read.

This is why a failing `RUN` in the Dockerfile now exits with a distinct code per check: the
annotation carries the command line and the exit status, and nothing else (defect 28).

#### What the container image job establishes

- the Dockerfile **builds for `linux/amd64` and `linux/arm64`** (the latter under QEMU), so the
  image is buildable on the Oracle Always Free Ampere A1 host that D-021 approved;
- the `archive`, `streams`, `postgres` and `nats` extras all install;
- the non-root runtime user, the healthcheck and the `CMD` stage build;
- **the module the `CMD` runs imports successfully inside the image**, and `create_app` is callable
  — asserted at build time, which is also what proves `tzdata` is really present (defect 26);
- neither interpreter in the image can import `setuptools` or `pip`, and no manifest in the image
  declares setuptools;
- `docker compose config` validates with all four required variables supplied;
- the image contains **no HIGH or CRITICAL vulnerability with an available fix**, and no secret,
  with the scan blocking on both severities and no ignore list.

#### What CI does not establish

No container has ever been **started**. The image builds and its entrypoint imports; nothing proves
it serves a request, that the healthcheck answers, that the ten compose services come up together,
or that Postgres/TimescaleDB, NATS, MinIO and Valkey accept a connection. The Caddyfile remains
completely unexercised. Runs are on GitHub-hosted `ubuntu-latest` (x86-64), not on the ARM64 host
D-021 approved; the arm64 build is QEMU-emulated, which proves it cross-compiles and not that it
performs; and Trivy scans the **amd64 image only**, because a multi-platform image cannot be loaded
into a daemon — one tag holds one architecture. See §5.

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

Defects 13–30 were found only by executing CI on GitHub. Almost none is a defect in the trading
logic; they are defects in the machinery that is supposed to prove the trading logic works, which
is why they are recorded with the same rigour as the rest. **Defect 26 is the exception and the
most serious of the group**: it is a defect in the deliverable itself — an image that would not
start — and CI surfaced it only because a build-time assertion was added that nobody had thought
to add before.

| # | Defect | Impact if unfixed | Fix |
|---|--------|-------------------|-----|
| 13 | `trivy-action@0.28.0` — the action's tags are `v`-prefixed | Every job died at "Set up job" with an unresolvable ref, before running anything | Corrected the ref. A tag that does not exist fails the whole job, not the step |
| 14 | `trivy-action@v0.28.0` references `setup-trivy@v0.2.1`, which was **never published** (oldest is `v0.2.6`) | The action is permanently broken at its own internal reference. No offline check can find this: the tag exists, its *transitive* refs do not | Pinned `v0.36.0`, which pins setup-trivy by commit hash. A test now refuses any version not known to resolve |
| 15 | The compose step never exported the `${VAR:?}` variables `docker-compose.yml` requires | `docker compose config` aborted immediately, so the compose file was never actually validated in CI | Exported throwaway `ci-only` values, with a comment saying they are for a config parse only |
| 16 | Multi-arch build had `push: false` **and** `load: false`, so no image existed in the daemon | Both Trivy image steps scanned a ref that did not exist. The tell: the step configured `exit-code: "0"` failed too, so it was never a finding — a multi-platform image cannot be loaded, one tag holds one architecture | Second amd64-only build with `load: true` for the scanner; the multi-arch build stays as the cross-compilation proof |
| 17 | `gitleaks-action@v2` accepts **no** inputs at all | `config-path` produced "Unexpected input(s) … valid inputs are ['']" and was discarded; the config was found by auto-discovery or not at all | Removed the `with:` block; the binary auto-discovers `.gitleaks.toml` at the repository root. A test asserts no inputs are passed |
| 18 | The first allowlist reproduced the literals it was allowlisting | Copying the fabricated JWT and PEM into `.gitleaks.toml` and into the guard test created **new** findings and turned a green `push` run red. An allowlist that contains what it excuses defeats itself | Scope by path only; the config and its guard test assemble expected values from fragments and assert they contain no contiguous literal |
| 19 | `permissions: contents: read` alone | gitleaks could not post its findings to the PR: `HttpError: Resource not accessible by integration` | Added `pull-requests: write`, and a test pins the permission set so it cannot widen |
| 20 | **`.gitleaks.toml` used plural `[[allowlists]]`, which gitleaks 8.24.3 does not define** | Viper ignored the unknown key with no error and no warning. Five consecutive runs failed on the same two findings while the config looked correct, my guard tests read the same key back and passed, and nothing anywhere said why | Singular `[allowlist]` (verified against 8.24.3's `ViperConfig` source: only a singular `Allowlist` struct exists; `extend()` appends the default's entries and matching is OR). `GITLEAKS_VERSION` pinned in the workflow, and a test validates every key in the config against that version's schema |
| 21 | `actions/checkout` defaults to `fetch-depth: 1` | A test verifying that an excused commit exists passed locally and failed **only in CI** — a test that passes only on the machine that wrote it is not a test | `fetch-depth: 0` on the backend job, asserted by a test; the verification itself skips only when the object is genuinely absent, not merely when the clone is shallow |
| 22 | The image scan's findings were unreadable, so HIGH was made report-only | A gate whose output cannot be read stays open: the build went green while an untriaged HIGH finding shipped. That was O-011, and splitting the severity was a quieter problem, not a solution | Findings republished as **check annotations**, which the REST API serves from any host (logs are served from a different one). That is what named the finding: CVE-2025-47273, setuptools 70.3.0. HIGH blocks again |
| 23 | The fix committed for defect 22 — `pip install --upgrade "setuptools>=78.1.1"` — did not clear it; the next scan still reported 70.3.0 | A fix argued for instead of measured. The reasoning ("the base image ships 70.3.0, therefore upgrade it") was plausible, and wrong in a way no local check could reveal | Superseded by defect 25. Left in the record because the reasoning is the instructive part |
| 24 | The removal that replaced it deleted nothing, and the assertion written to prove the removal worked then **failed the build on `pip/_vendor/pkg_resources`** | Five consecutive red image jobs. The check meant to prevent a wrong fix was itself wrong: it matched by filename rather than by distribution metadata, so it treated a necessary part of pip as the vulnerability | Match distributions only (`pip`, `pip-*.dist-info`, `setuptools*`) at the only depth a distribution can live. A test enumerates every removal pattern and refuses a bare `pkg_resources` |
| 25 | **The finding is a false positive.** setuptools is not installed anywhere in the image; the scanner reads `pip/_vendor/bom.cdx.json` — pip's own CycloneDX SBOM listing its vendored dependencies — which declares `pkg:pypi/setuptools@70.3.0` | Three fixes could not have worked. Upgrading cannot rewrite a version string inside pip's own SBOM, removal has nothing to remove, and the reading "this image contains vulnerable code" was simply untrue | Remove pip from both interpreters. No ignore file, no deleted manifest, the scan still blocking on HIGH and CRITICAL: the runtime installs no packages, so a package installer in the image is attack surface with no benefit, and pip is the only SBOM carrier in the tree |
| 26 | The runtime image never installed the IANA tz database, and the module the `CMD` runs builds `ZoneInfo("America/New_York")` at import time | **Latent, not live — and first recorded here as worse than it was.** `nexus.instruments.sessions` resolves two zones at module scope and `nexus.api.app` imports it, so a base image without tzdata means ZoneInfoNotFoundError before a port is bound. Measured in CI: `python:3.12-slim-bookworm` *does* ship `/usr/share/zoneinfo`, so startup works today. The real defect is that the image depended on a package it never asked for, and nothing checked — no test anywhere imported the image's own entrypoint | Install `tzdata` explicitly instead of inheriting it, and assert at build time that `nexus.api.app` imports and `create_app` is callable. The commit that introduced this row claimed the container "would not have started"; the probe disproved that, and the claim is corrected in `40e7ed6` rather than rewritten |
| 27 | GitHub Actions allows **10 annotations per level per step** | A diagnostic built to fetch one answer spent its entire budget on docker's image-pull progress and published nothing. The Trivy publisher had the same defect waiting in it: one annotation per finding, capped at 40, would silently have lost everything past the tenth — and a cap that truncates looks exactly like a result | Each report packed into a single annotation with encoded newlines; a test asserts the count stays within budget *and* that packing does not lose findings |
| 28 | Six assertions in one `RUN`, and build logs are not readable from every environment | Eight and a half minutes of build, then an annotation printing all six checks without saying which had tripped. The failure was undiagnosable through the only channel available | Distinct exit codes 21–26 with a legend above the `RUN`; a test asserts the codes and the legend agree, because a legend that has drifted from the checks gets believed |
| 29 | The local gate chained lint, types and tests with newlines instead of `&&` | A non-zero `ruff` exit did not stop the commit and push behind it. Five F811 redefinitions shipped and were caught by CI rather than locally (`9f07537`) | Chained with `&&`. A gate whose failure cannot stop the commit is not a gate |
| 30 | The check that replaced defect 25's asserted "no SBOM survives anywhere in the image" | One more red build, on `psycopg_binary-3.3.9.dist-info/sboms/auditwheel.cdx.json` — a manifest that says nothing about setuptools. The claim it rested on, "pip is the only SBOM carrier in the tree", had been verified against the **local dev venv**, which does not install the `postgres` extra and so does not contain psycopg at all | Grep manifest *contents* for setuptools within `*.cdx.json`/`*.spdx.json`, which is the invariant that matters. A test refuses the blanket form from returning. The general rule: a conclusion drawn from the dev environment about the contents of the image is not a conclusion about the image |

Defects 1–3 and 9–12 are the important ones: all seven produce *plausible-looking wrong
results* rather than an error, which is the failure mode that destroys confidence in a
backtest — or, in defect 12's case, in the repository itself.

Defects 20, 24 and 27 are one failure mode appearing three times: something silently inert, or
silently truncated, while looking exactly like the real thing. A configuration key the pinned
version does not define. A `find` action bound to the wrong branch, so a survivor check matched
nothing and passed. An annotation budget spent before the answer arrived, and a finding list
capped below the number of findings. None of the three produced an error, and none was found by
the check that was supposed to catch it — each was found by reading source or by measurement, and
each now has a test that fails when the inert form returns.

Defects 23, 24 and 25 are a single investigation recorded in full, including the two wrong
answers. The sequence matters more than the outcome: a plausible fix was committed on reasoning
(defect 23), the reasoning was replaced by a measurement that contradicted it (defect 24), and the
measurement eventually showed the finding itself was untrue (defect 25). Had the first fix been
accepted because the command exited zero, the image would carry a scanner exception for a
vulnerability it does not have — and the tzdata defect behind it would still be undiscovered.

One correction to the record, in the same spirit: the commit message for `edcefb6` claimed 860
tests when the gate had reported 859. The number was written before it was measured. The commit
was left unrewritten, consistent with how `72fcbcc` is handled in limitation 8.

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
3. **The image builds and its entrypoint imports; nothing has ever run.** Narrowed twice since
   Phase 2, still not closed. CI builds the Dockerfile for `linux/amd64` **and** `linux/arm64`,
   `docker compose config` validates with every required variable supplied, and the build now
   imports the module the `CMD` executes and checks `create_app` is callable (§3.6). So the Phase 3
   additions — the `archive`/`streams`/`postgres`/`nats` extras, the `archive-data` volume, the new
   env vars, the non-root user — are proven to *install, build and import*, and the IANA tz
   database the entrypoint needs is proven present.

   What remains unverified is everything that needs a **running** container: no service has ever
   started, no healthcheck has ever answered, no request has ever been served, the ten compose
   services have never been brought up together, Postgres/TimescaleDB and NATS have never been
   connected to, and the **Caddyfile is still completely unexercised**. An import assertion proves
   the dependency graph resolves; it does not prove the app binds a port, migrates, or answers
   `/healthz`.

   One consequence specific to this phase: pip is **removed** from the runtime image (§4 defect 25),
   which was verified safe by grepping every installed distribution's metadata and confirming
   nothing under `src/nexus` shells out to pip. That reasoning is sound but was done in the dev
   venv, whose package set differs from the image's — the same mistake as defect 30. If some
   installed package imports pip at runtime, nothing so far would have noticed. First real
   `docker compose up` is the test, and it is a Phase 4 task on the Oracle VM.
4. **CI now executes — and the new limitations are about *where*.** This was open in Phase 2
   ("committed but never executed") and is closed: both `push` and `pull_request` runs are green
   on all four jobs at `40e7ed6` (§3.6), after eighteen runs and defects 13–30. What CI does *not*
   prove:
   - it runs on **GitHub-hosted `ubuntu-latest` (x86-64)**, not on the Oracle Always Free
     Ampere A1 host that D-021 approved. A green run here says nothing about that machine.
   - the `linux/arm64` build is **QEMU-emulated**, so it proves the image cross-compiles, not
     that it performs — or even runs — natively on ARM64.
   - Trivy scans the **amd64 image only**. A multi-platform image cannot be loaded into the
     daemon (one tag, one architecture), so the arm64 variant has never been scanned. Its
     package set can differ.
   - the suite runs against **SQLite** in CI as elsewhere; no CI job has ever touched a real
     Postgres, NATS, MinIO or Valkey process (see limitation 5).
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
| Repository is complete and cloneable | Fresh clone of `40e7ed6` holds 49/49 modules, imports resolve inside the clone, 868 tests pass from a clean checkout; no artifact, credential-shaped file or scan-suppression file tracked (§3.5) | **PASS** |

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
