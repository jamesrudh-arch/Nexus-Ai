# Stage 11 — The paper trading platform, and deployment readiness

**Status: AWAITING REVIEW** · Branch `arena/06913352-nexus-ai` · Commit `0994b29`
**Decision recorded: D-059** · **Findings raised: F-41 … F-44** · **Questions for the owner: Q-6 … Q-10**
**Next finding id after this document: F-45**

---

## 1. What was asked for

> "I need this to be ready and it should have its own paper trading machine or platform where it can
> run its trades and do analysis real time before actual trading. Make sure it's ready but front end
> and back end just codes."

Four requirements, read separately because they constrain each other:

| # | Requirement | What it turned out to mean |
|---|---|---|
| 1 | *ready* | Deployable as a process. Three specific blockers existed and are fixed (§6). |
| 2 | *its own paper trading machine* | Not a backtest and not a mock: an engine that executes decisions and keeps books. |
| 3 | *analysis real time before actual trading* | Analysis on the observation, not on a timer, and ahead of any real order. |
| 4 | *front end and back end just codes* | Source for both, runnable locally, with no dependency on a paid host (§7). |

Requirement 3 is the one that decides the architecture. "Before actual trading" means the paper path
must rehearse the real one, which means it consumes real market data and real governance checks —
and that in turn collides with a law the owner already wrote down.

---

## 2. The collision with docs/03 §3.5, and how it is resolved

`docs/03` §3.5 states, as product law:

> Real data only. No fake balances, invented P&L, fabricated confidence, or simulated live feed in
> production.

Paper trading is simulation by definition. Read carelessly, the two cannot coexist, and the easy
resolutions are both wrong: either the paper platform is forbidden, or §3.5 is quietly relaxed to
permit it. Neither was done. The distinction that reconciles them is between a simulated
**execution** and a simulated **price**:

| | Permitted | Forbidden |
|---|---|---|
| Execution | A fill modelled against a real quote — spread, slippage, commission, latency | A fill at a price nobody quoted |
| Balance | Simulated capital, labelled `simulated: true` on every response | A balance presented without its label |
| P&L | Realised from real fills; unrealised from a real last price | Unrealised from an invented mark |
| Feed | Real quotes from a free public source, analysed as they arrive | A generated feed standing in for a market |

This is recorded as **D-059** (§8) rather than treated as an implementation detail, because it is a
ruling about what the product is allowed to show, and the next person to add a feature here needs it
written down rather than inferred from the code.

Three consequences are enforced structurally, not by convention:

1. **A missing price is a refusal.** `NoFillReason` has seven members; every one is a fact about the
   data (`NO_QUOTE`, `NO_EXECUTABLE_SIDE`, `STALE_QUOTE`, `CROSSED_OR_LOCKED`,
   `LIMIT_NOT_MARKETABLE`, `NO_LIQUIDITY`, `DELAYED_DATA_REFUSED`). There is no branch anywhere in
   `nexus.paper` that produces a price from nothing.
2. **The label cannot be omitted.** `PaperSnapshot.simulated` and `.environment` are required fields
   with defaults, and `lib/types.ts` declares `simulated` and `environment` as *required* members of
   a `Simulated` interface that every paper response type extends. A component that forgets to ask
   does not compile.
3. **A delayed feed is refused, not traded.** Filling on delayed data would credit the strategy with
   an edge that belongs to whoever is not delayed. `refuse_delayed_data` defaults to `True`.

---

## 3. What was already there, and what was missing

Measured before writing anything, because the alternative is building a rung that already exists:

| Already present | Where |
|---|---|
| `EnvironmentState.PAPER = 4`, "simulated execution against live data" | `core/environment.py` |
| `_PRE_LIVE_MAX = EnvironmentState.PAPER`, and a ladder that forbids PAPER→LIVE without PILOT | `core/environment.py:28`, `:62` |
| Seven governance checks, terminating at step 7 only because no adapter exists | `execution/gateway.py` |
| `OrderState` with `PARTIALLY_FILLED`, `WORKING`, `EXPIRED`, `UNKNOWN` | `execution/orders.py` |
| `HaltScope.NEW_ENTRIES` / `ALL_TRADING`, and `allows_risk_reducing()` | `execution/halt.py` |
| `DecisionVerb` — ACCEPT / REJECT / WAIT / REDUCE / EXIT / ESCALATE / ABSTAIN | `domain/decision.py` |
| `QuoteRecord` with bid/ask/sizes/last/delayed/source and `is_crossed_or_locked` | `data/records.py:256` |
| Archive-first ingestion with validation, provenance and rejection reasons | `ingestion/pipeline.py` |
| The ruled UI stack and fifteen pages, with tokens | `docs/03` §2, §3.1–§3.5 |

| Missing | Now |
|---|---|
| Any fill model | `paper/fill_model.py` |
| Any account or position book | `paper/account.py` |
| Any execution engine for PAPER | `paper/engine.py` |
| Any signal/analysis producing a verb | `paper/analysis.py` |
| Any real-time loop | `paper/realtime.py` |
| Anything that actually *calls* the loop | `paper/runner.py` |
| Any frontend at all | `frontend/`, 24 tracked files |

`execution/` contained `gateway.py`, `halt.py`, `intent.py`, `orders.py` and no simulator. Five
files mentioned paper or simulation; none implemented either.

---

## 4. What was built

### 4.1 Backend — `backend/src/nexus/paper/`

| Module | Lines | What it is |
|---|---|---|
| `fill_model.py` | 448 | Simulated execution against real quotes; seven refusal reasons; seeded, reproducible |
| `account.py` | 339 | Immutable account and position book; Decimal throughout; rebuildable from its ledger |
| `engine.py` | 558 | The machine: governance checks, side resolution, fill, book update, idempotency |
| `analysis.py` | 420 | Real-time analysis: momentum, spread, size imbalance → `DecisionVerb` + confidence |
| `realtime.py` | 487 | The loop: observe → analyse → maybe trade; throttling, cooldown, position limit |
| `runner.py` | 469 | Composition root: fetch → validate → archive → analyse → simulate, until stopped |
| `__init__.py` | 68 | Exports plus `CAPABILITY`, the claim the package makes about itself |
| **total** | **2,789** | measured with `wc -l` |

`api/paper.py` adds ten routes. `IngestionPipeline` grew a `RecordObserver` hook.

### 4.2 The three things that are deliberately *not* there

- **No venue adapter.** `PHASE_GATE["venue_adapters"]` stays `False` and
  `PHASE_GATE["order_capability"]` stays `False`. Nothing registers with `ExecutionGateway`, so its
  step-7 refusal is untouched and CI's phase-gate assertion still measures the truth.
- **No consultation of `LiveAuthority`.** That gate answers "may we spend real money". Asking it from
  a simulator would either be meaningless or would imply that a `GRANTED` from the paper path means
  something about live trading. It does not, and the code does not suggest otherwise.
- **No socket, no HTTP client, no credential in the package.** Asserted by a test that parses the
  modules with `ast` and inspects imports and attribute access — not by grepping text, because these
  docstrings say "there is no socket" in so many words, and a text search for `socket` reports the
  sentence that denies it as an offence.

### 4.3 Frontend — `frontend/`

The stack ruled in `docs/03` §3.5 rather than one chosen here. Four of the fifteen ruled pages are
built against real endpoints, plus governance:

| Route | docs/03 §2 page | Serves |
|---|---|---|
| `/` | 1 — Command Centre | Equity, realised/unrealised P&L, exposure, live risk, system health, positions, decision queue |
| `/paper` | 7 — Strategy Laboratory (bench) | Start/stop/reset the loop, live analysis feed, the cost model, the confidence band |
| `/execution` | 9 — Execution Room | Blotter, order states, fills, **slippage as a first-class column**, venue health, kill switch |
| `/portfolio` | 8 — Portfolio & Risk | Consolidated account, positions, concentration, limits |
| `/governance` | 15 — Settings & Governance | Every gate, read from the running process; paper authority beside live authority |

The other ten pages are listed in the navigation as *staged* rather than hidden. A navigation that
shows only what exists implies the product is complete; one that lists what is missing says where the
work is.

Four values are rendered **UNAVAILABLE with the reason** rather than approximated:

| Value | Why it is not shown |
|---|---|
| Market regime | No regime model exists. A guessed label would be the most believed thing on the page. |
| Factor exposures | No factor model. A column of invented betas looks exactly like the real thing. |
| Drawdown | Needs an equity *series*; the API serves one point. A session-only series would understate every drawdown that happened before the page was opened — so it is left out rather than shown half-right. |
| Stress scenarios | Scenario Studio (§2 page 11) is not built. |

Margin is shown as *inapplicable*, not unavailable: the paper account is a cash account with no
leverage, so nothing is missing. The two imply different work and are labelled differently.

---

## 5. Measurements

### 5.1 The gates

| Gate | Before this batch | After |
|---|---|---|
| `pytest` | 1,587 passed / 2 skipped | **1,668 passed / 2 skipped** (+81) |
| `tests/test_paper_trading.py` | did not exist | **81 passed** |
| `ruff check src tests` | clean | clean |
| `ruff format --check` | clean | clean (107 files) |
| `mypy --strict src/nexus` | Success, 65 files | **Success, 73 files** |
| `PHASE_GATE` | phase 3, all live flags False | **unchanged, byte for byte** |
| API routes | 17, none trading-capable | **27**; the ten under `/v1/paper` proven inert |
| Frontend `tsc --noEmit` | n/a | clean under `strict` + `noUncheckedIndexedAccess` |
| Frontend `next build` | n/a | compiles, lints, prerenders all five routes |

The two skips are pre-existing and unchanged (`test_live_endpoints.py` needs egress;
`test_archive_bars.py` models no 7m interval). No pre-existing test was weakened: `test_api.py` and
`test_api_phase3.py` each gained assertions rather than losing them (§9).

### 5.2 The machine, end to end

Driven with a rising market of 30 quotes, 25 bp per tick, fresh timestamps, through the loop:

| Measured | Value |
|---|---|
| Analyses run | 30 |
| Actionable verdicts | 27 |
| Trades simulated **without** a cooldown | 27 — one idea repeated, pyramiding into a curve that flatters the strategy |
| Trades simulated **with** a 10 s cooldown | **3**, with 24 held back and counted |
| Every fill price vs the ask | strictly above it, on 200 draws at 25 bp — slippage never favourable |
| Commission | booked, with a floor so small fills are not free |
| Equity, marked with the real last price | 101,654.75 on 100,000 (+1.65 %) |
| Equity, with no mark | 99,972.99, position carried at entry **and named in `positions_carried_at_entry`** |

The cooldown is the row that matters. Without it the loop added to the same position on every tick
that still showed momentum, and the resulting curve was built out of one idea repeated thirty times.
That is the shape of a backtest that gets a strategy funded and then loses money.

### 5.3 The lesson the platform exists to teach

Buying 10 units at an ask of 101 and closing at a bid of 99, on a book with a 2-point spread:

```
realized_pnl = -20.02
```

The idea was not wrong — the market did not move against the position at all. The spread, the
slippage and the commission took 20.02. This is the number that decides whether a strategy survives
contact with a real venue, and it is the reason the Execution Room shows slippage as a column rather
than a footnote.

### 5.4 The runner against a live venue

Run from this sandbox, which has no egress to market endpoints:

```
[16:34:46] paper runner starting: 1 feed(s), poll every 2.0s, account PAPER-MAIN,
           capital 100000 USD (simulated)
[16:34:56] cycle 1 | bybit-public: ⚠ IngestFault: DATA_UNAVAILABLE:
           https://api.bybit.com/v5/market/tickers failed: ConnectError(...) |
           analyses 0 · actionable 0 · simulated 0 · unfilled 0
[16:34:56] stopped after 1 cycle(s), 0 quote(s) observed. Simulated equity 100000.00 USD,
           net P&L 0.00, 0 fills, 0 open position(s).
```

The runner reached the real endpoint, made a real HTTPS request, and reported the failure as
`DATA_UNAVAILABLE` with its cause. Nothing was invented: 0 quotes observed, equity unchanged, 0
fills. An honest flat line, which is what a refusal looks like when it is done properly.

Exit codes measured: `2` for a malformed or historical-source feed spec, `4` for a bounded run that
observed nothing, `0` for a clean bounded run. A bounded run that exits 0 having observed nothing
would report success for an outage, which is the shape a compose healthcheck or a cron entry sees.

### 5.5 Served through the dashboard's own path

Backend on 8091, `next dev` on 3000, browser-facing requests relative:

| Request | Result |
|---|---|
| `GET /` | 200, 26,386 bytes |
| `GET /paper`, `/execution`, `/portfolio`, `/governance` | 200 each |
| `GET /api/v1/paper/account` | 200 — `simulated: true`, `environment: "PAPER"`, `simulated_cash: "100000"` |
| `GET /api/v1/status` | 200 — `paper.can_place_live_orders: false`, `live_authority: DENIED`, `persistence: sqlite` |

The rewrite is the load-bearing part: the browser requests `/api/v1/paper/account` and never learns
where the API is. A page that fetched `http://localhost:8000` would fail in exactly the sandboxed
preview it is meant to be demonstrated in, because there the browser and the API are different hosts.

---

## 6. Deployment readiness — three blockers, measured then fixed

These were found by reading the deployment surface rather than by assuming it, and each was a
failure that would have presented as something else entirely.

### 6.1 F-41 `CLOSED` — the container ignored `$PORT`

`backend/Dockerfile` ended with
`CMD ["uvicorn", ..., "--port", "8000"]` and a healthcheck probing `127.0.0.1:8000`. Nothing in the
repository read `$PORT`.

A PaaS (Railway, Render, Fly, Cloud Run) injects `$PORT` and routes to *that* port. The container
therefore boots, passes its own healthcheck, and never receives a request — presenting to an operator
as a healthy service that returns nothing. The healthcheck was wrong in the same direction, so it
could not catch it: probing the wrong port reports an unhealthy service that is serving, or a
healthy one that is not.

Fixed to shell form with `--port "${PORT:-8000}"` and `CMD-SHELL` expanding the same variable in the
healthcheck. 8000 remains the documented default for compose and local runs, where nothing injects a
port.

### 6.2 F-42 `CLOSED` — a dropped PostgreSQL connection was permanent

`store/pg.py` held one connection for the life of the process and had no re-open path. Managed
PostgreSQL fails over; a serverless plan suspends an idle database. Either closes that connection,
and the failure then **outlives its cause**: the next statement fails, and every statement after it
fails, until an operator restarts the process. `grep -rniE 'reconnect|retry|OperationalError'` over
`store/*.py` found only `OperationalStoreError(retryable=True)` and docstrings promising a retry that
nothing implemented.

Fixed with `_reopen()`: bounded attempts, exponential-ish backoff, the catalog caches cleared so a
fresh connection cannot serve a stale shape after a provider restart or a migration another process
applied. The re-open **never re-runs the failed statement**. The fault may have arrived while the
server was acknowledging a commit, in which case the write is already durable and running it again
would double it. Recovering the connection and reporting the operation as failed — through the
store's existing retryable `PersistenceError` path — is the only answer that cannot invent a second
side effect. `commit()`, `rollback()` and `close()` were also unwrapped and could raise a raw driver
fault; the third would raise a second fault over the first when rolling back an already-dead
connection, hiding the real cause.

Still **not** implemented, and still stated in §13 of `docs/17`: TLS. `?sslmode=require` survives
`_postgres_dsn` because query parameters are preserved verbatim, but no TLS path has been exercised
against a managed provider.

### 6.3 F-43 `CLOSED` (documentation defect) — the archive volume's rationale was unstated

`docker-compose.yml` already mounted `archive-data:/app/data/archive` inside `core-data:/app/data`.
The mount was right and unexplained, which is how a correct line gets deleted by someone who cannot
see why it is there. `archive_root` defaults to `./data/archive` and the Parquet archive is the
system of record R-1 reconciles against; on an ephemeral container filesystem a redeploy would
discard every archived bar, so a restart would recover its audit chain from PostgreSQL and its market
history from nothing.

Recorded beside the mount. The first draft of this note claimed the volume was *missing*; measuring
the file showed it was present, and the note was corrected before commit rather than shipped wrong.

### 6.4 The runner is now a compose service, opt-in by profile

`paper-runner` joins `docker-compose.yml` (11 services) on the same `nexus-core:0.2.0` image with
`command: ["python", "-m", "nexus.paper.runner"]`, which replaces the Dockerfile's `CMD` — there is no
`ENTRYPOINT` to fight. Two choices in it are deliberate and worth stating because both could be
"fixed" by someone who cannot see the reason:

- **`profiles: [paper, full]`, so it is not started by default.** The loop polls a public endpoint on a
  rate budget this project shares across every endpoint (P-9/F-8, accumulating), and spending it should
  be an operator's choice rather than a consequence of `docker compose up`. It also means
  `infra/smoke-test.sh` is untouched: that script names its services explicitly, and a profiled service
  is not started by a default `up`.
- **It mounts `archive-data` only, not `core-data`.** The runner constructs no store and writes no
  database, so mounting the data volume would advertise a shared store that does not exist (§7.1). F-44
  is the finding that would change this, and the comment beside the mount says so.

There is **no healthcheck**, and that is a gap stated rather than hidden: the loop exposes no port, so
there is nothing to curl. Its per-cycle logs carry `quotes_accepted` and the stack's Loki collects them,
so a dead feed is *readable*; alerting on one would need a heartbeat file. An unbounded run keeps
polling through an outage, which is correct for a service under `restart: unless-stopped`, and the
bounded form (`--cycles N`) exits 4 when it observed nothing — that is the form a cron entry or a CI
step should use, because exit 0 during an outage is how a supervisor learns to trust nothing.

---

## 7. Findings raised by this batch

### 7.1 F-44 `OPEN` — the paper ledger is not durable, and the platform does not yet persist it

`InMemoryPaperLedger` is the only ledger implementation. It is bounded, thread-safe, and honest about
itself (`describe()` returns `durable: false`, and the dashboard renders `⚠ not durable`), but the
consequence is real: **a restart of the paper runner loses the blotter.** The audit chain keeps its
record of each simulated trade, so nothing is concealed — but the account cannot be rebuilt, because
`rebuild_from_fills` needs the fills and the fills lived in the process.

A paper result is only worth anything if it can be inspected after the run, and today it cannot be
unless the process stays up. This is the largest gap between what is built and what "ready" implies
for the paper platform specifically.

**The consequence is larger than durability, and was found by reading what the runner actually
constructs rather than what its docstring claimed.** The runner builds settings, feeds, an in-memory
registry, a `ParquetArchive` and the engine — **no operational store and no audit log**. The API's ten
`/v1/paper` routes serve *its own* in-process platform with its own ledger. So the standalone runner
and the API are two independent paper machines that share their archived quotes and nothing else, and
**the dashboard does not show what the runner is doing**. The first draft of `runner.py`'s docstring
asserted the opposite — "both processes read the same settings and write the same store, so the
dashboard served by the API shows what this runner is doing" — and that sentence was false in its
second half. It is corrected in the module and in `README.md`, and the correction is recorded here
because a docstring that promises a connection which does not exist is worse than one that says
nothing: it is how the next person spends a day looking for a bug in the dashboard.

Until a persistent ledger lands, the runner prints a full report on every cycle and on exit, because
nothing else will read its state later. That is the honest shape of the gap: visible, narrated, and
not papered over by a dashboard that appears to work.

Migration `0003_paper.sql` and a `SqlPaperLedger` implementing the same `PaperLedger` protocol are
the fix, and the protocol exists precisely so that adding them does not touch the engine. Not done in
this batch: the `PaperLedger` protocol was written as the seam, and the seam is unexercised by a
second implementation, which is a design claim not yet proven.

### 7.2 What was found and fixed while building

Three defects that would have shipped, each caught by measuring rather than by reading:

1. **The runner's default feed accepted nothing.** `okx-public` is a *source* label; the instrument
   registry resolves symbols against a *venue* name. Passing one where the other was needed makes
   every record `INSTRUMENT_UNKNOWN:okx-public:BTC-USDT-SWAP`. The failure mode is silent and
   total: the runner polls a live feed, receives real quotes, accepts none, and reports a healthy
   flat curve — indistinguishable from a strategy that made no mistakes. `SOURCE_VENUE` now maps
   source to venue, and a test asserts the two are never equal.
2. **The default feed was the wrong source anyway.** The seeded Bybit `BTCUSDT` mapping sits at
   `VenueStatus.SUPPORTED`, below `MINIMUM_STATUS_FOR_ARCHIVE` (`DATA_AVAILABLE`), so every quote
   from it is rejected before the loop sees one. F-2 separately records that bybit v5 answers 403 from
   GitHub-hosted runners. OKX's `BTC-USDT-SWAP` mapping is `DATA_AVAILABLE`. Default changed, with the
   reason recorded in both `config.py` and `runner.py` so it is not silently changed back.
3. **A partial close realised no P&L.** `apply_fill` booked realised P&L only when a position closed
   or flipped. Selling 4 of 10 units at a 20-point profit reported `realized_pnl == 0`, which
   understates every strategy that scales out of a position. Realised P&L is now booked on the
   quantity actually closed whenever a fill trades against the position held.

Two more were caught by the type checker and the linter before they could run:

4. **`HaltManager.state` is a property, not a method.** The engine called `self._halt.state()`, which
   would raise `TypeError` on the first quote to arrive with a halt engaged — precisely the moment
   that branch exists for. `app.py` uses it correctly without parentheses; reading the callee rather
   than the caller is what caught it.
5. **`state` was bound to two unrelated types in one function** — `HaltState` in the halt branch and
   `OrderState` in the unfilled branch. Runtime-correct, and exactly the shape that produces a wrong
   value six months later. Renamed to `order_state`.

### 7.3 A trap worth recording for the next person

`IngestionPipeline.persist()` returns early when no archive is configured, *before* any observer is
called. That is correct — rule 4 says a consumer must never see a record the archive does not hold —
but it means an observer wired to an archive-less pipeline is silently never invoked. There is no
warning, and the pipeline reports `accepted 1` while the consumer receives nothing. The runner
therefore configures a `ParquetArchive`, and the reason is written at the construction site. This cost
two diagnostic rounds to find and will cost the next person the same unless it stays written down.

---

## 8. D-059 — what the paper platform is, and what it is forbidden from being

**Ruling.** The paper trading platform is a rehearsal of the real path, permitted to simulate
*execution* and forbidden to simulate *data*. Concretely:

1. It executes against real observed quotes and never manufactures a price. Seven refusal reasons
   cover every case where there is nothing real to trade against.
2. Every value it produces is labelled `simulated: true` with `environment: "PAPER"`, in the API, in
   the audit payload, in the TypeScript types, and on every screen.
3. It is not a venue adapter, holds no adapter, opens no connection, reads no credential, and never
   consults `LiveAuthority`.
4. `PHASE_GATE` is unchanged by its existence: phase 3, `venue_adapters` False, `order_capability`
   False, `real_money_orders_possible` False, `live_trading` False.
5. Running it confers no live authority whatsoever. `EnvironmentState`'s ladder still requires PILOT
   between PAPER and LIVE.
6. Costs are modelled adversely by default — spread, slippage, commission, latency — and a
   configuration that would flatter the simulation is refused at construction.

Points 3–5 are the ones that make this safe, and they are asserted rather than documented: a test
parses the package with `ast` for network imports and environment reads, a test asserts the phase
gate, and the smoke checker asks the *running process* whether it can place an order.

---

## 9. Questions for the owner

None of these has been self-ruled. Each is a choice with a real alternative, and the recommendation
is given so a decision can be made quickly rather than so it can be avoided.

### Q-6 — CI's "no order endpoint" assertion was relaxed for one namespace

Three gates banned the substrings `order`, `trade`, `execute`, `position`, `withdraw` from every API
path: the CI workflow step, `infra/smoke_check.py`, and two tests. `/v1/paper/orders` and
`/v1/paper/positions` trip all of them.

The options were: (a) rename the routes to `/v1/paper/blotter` and `/v1/paper/holdings`; (b) exempt
the namespace and prove it inert; (c) leave the paper platform unexposed.

(a) was rejected because it makes the gate weaker than it looks: a lexical ban on the word `order` is
satisfied by a route that really does send orders and is merely named something else. (c) was
rejected because a dashboard that cannot read the blotter cannot show what the machine did.

(b) is implemented: the paper namespace is exempt from the *word* check, and in its place all three
gates now ask the running process — `can_place_live_orders`, `is_venue_adapter`, `adapter_count`,
`network_access`, `credentials_required`, plus `simulated`/`environment` on every paper body. A build
that could send an order would have to lie in several separate responses to pass, and the phase-gate
assertions would have to lie with it.

**This is a change to a safety gate the build has relied on, so it is surfaced rather than applied
quietly. Recommendation: ratify (b).** If the owner prefers the lexical ban to stay absolute, the
paper routes must be renamed and the semantic checks kept anyway — the rename would then cost
readability and buy nothing.

### Q-7 — should the paper ledger be persisted (F-44)?

**Recommendation: yes, as the next batch**, with migration `0003_paper.sql` and a `SqlPaperLedger`
behind the existing `PaperLedger` protocol. Until then a paper run is only inspectable while its
process lives, which limits it to interactive use and makes a multi-day rehearsal impossible.

### Q-8 — which sources should the runner watch by default?

The default is now `okx-public:BTC-USDT-SWAP`, the one free real-time source whose seeded mapping is
at `DATA_AVAILABLE`. Bybit is refused by the archive floor and geo-blocked from hosted runners (F-2);
`binance-vision` and `dukascopy` are historical and are refused *by name* with an explanation, because
feeding an archive to a real-time loop produces analysis of a market that has already moved.

**Question:** is one instrument the right default, or should the runner ship watching the full seeded
universe? One symbol keeps a rehearsal cheap and legible; the full universe is what a real paper run
needs. **Recommendation: keep one as the default and let `NEXUS_PAPER_FEED` name more**, because a
default that polls every mapping would be rejected on the two that cannot serve data and would report
a `DEGRADED` rejection rate on every cycle.

### Q-9 — does the dashboard's four-page scope match the owner's expectation of "front end"?

`docs/03` §2 rules fifteen pages. Five are built (four ruled pages plus governance); ten are listed
as staged. Each unbuilt page needs data the backend does not yet serve — a regime model, a factor
model, an equity series, an evidence graph — so building the screens first would mean populating them
with placeholders, which is the dead scaffolding the standing requirement forbids.

**Recommendation: build the remaining pages behind their data, one stage at a time**, rather than
ahead of it.

### Q-10 — should the loop write into the audit chain, and if so which of its records?

`PaperTradingLoop._publish` already calls `_audit_record(...)` before publishing, and both hooks are
inert because the runner passes neither `audit=` nor `events=`. Wiring them is a small change with a
large consequence, so it is a question rather than a default.

Measured, with the shipped configuration: one analysis verdict serialises to **695 bytes**. At
`paper_min_analysis_interval_seconds=1` that is 86,400 verdicts per instrument per day, so **57 MiB/day
for one instrument** and **458 MiB/day — 3.1 GiB/week — at the eight** `paper_max_open_positions`
allows. The audit chain is append-only and hash-linked with no pruning operation, and `docs/02`'s Z-3
records a 200 GB storage cap on the free VM. Recording every verdict would therefore consume the
deployment's disk in roughly a year at one instrument, or weeks at eight. Trades are a different
matter: the 60-second cooldown bounds them at **1,440 per instrument per day**, which is trivial.

The options are (a) record trades only, (b) record both, (c) record neither and rely on the runner's
cycle report, which is what ships today.

**Recommendation: (a) — record simulated trades in the audit chain and leave verdicts out**, because a
trade is a decision the system made and belongs in the record of decisions, while a verdict is a
per-second observation whose durable form is the archived quote it was derived from. (b) needs a
retention or sampling ruling first, and (c) leaves the rehearsal un-auditable after the process exits,
which is most of what a rehearsal is for. Note that (a) partially mitigates F-44 — the audit chain
would hold the trades — but does not close it, because `rebuild_from_fills` needs the *fills* and the
audit chain is not a fill ledger.

---

## 10. What this document does not claim

1. **No strategy has been validated.** The reference analyzer is a momentum-and-imbalance heuristic
   whose parameters are defaults, not fitted values. It exists to make the machine run and to be
   replaced; `Analyzer` is a Protocol for exactly that reason. Nothing here is evidence that any
   approach makes money.
2. **No live market data was analysed.** This sandbox has no egress to venue endpoints. The runner was
   proven to reach a real endpoint, fail honestly, and report zero observations; the quote flow in
   every test is constructed. The first run against a live feed has not happened.
3. **The fill model has not been calibrated against real executions.** Its slippage and commission
   are plausible defaults chosen to be adverse. Calibrating them needs real fill data from a venue,
   which needs the live phase this build cannot enter. Every P&L it produces is therefore a lower
   bound in intent and an estimate in fact.
4. **The dashboard does not display the standalone runner's activity.** §7.1 states why: two
   in-process ledgers, no shared store. The five pages read the API's own platform, which trades when
   `POST /v1/paper/start` is called against it. Demonstrating the runner and the dashboard together
   shows two machines, not one pipeline, and any claim otherwise would be false.
5. **No concurrency measurement.** The account is replaced under a lock and never mutated, and the
   tests exercise one thread. Two runners writing one account is untested, and unsupported by design
   until F-44 gives them a shared ledger.
6. **The frontend has not been exercised in a browser by a human.** It compiles, type-checks under
   `strict`, prerenders, and serves 200 on all five routes through the proxy; no claim is made about
   its usability, its responsive behaviour on a real device, or its accessibility beyond the
   structural properties implemented deliberately (glyph-plus-word semantics, `aria-current`,
   `role="alert"`, a skip link, `prefers-reduced-motion`).
7. **SSE has not been observed streaming.** `EventSource` reconnect behaviour and the frame cadence
   are implemented and typed, and the stream endpoint returns the right media type and headers, but a
   test client cannot consume a never-ending response without hanging. The builder is asserted; the
   stream is not.
8. **`$PORT` has not been verified on a real PaaS.** The expansion is standard shell parameter
   expansion in a `CMD` and a `CMD-SHELL` healthcheck, and no container runtime exists in this
   sandbox to run it in.

---

## 11. Drift and corrections

| Where | What changed |
|---|---|
| `docs/03` §3.5 | Not contradicted. §2 above records how the paper platform satisfies it rather than relaxing it. |
| `docs/04` §65, `docs/06` §175, `docs/12` §131 | Cite port 8000. Still true as the *default*; F-41's fix makes it `${PORT:-8000}`. Not rewritten — historical stage documents are amended beside, not edited. |
| `docker-compose.yml` | 10 services → **11**: `paper-runner`, opt-in under `profiles: [paper, full]` (§6.4). |
| `docs/07` | D-059 added; register row added; next finding id moves **F-41 → F-45**. |
| `docs/00` | Change-log row added for this batch. |
| `docs/17` drift tail | Its *"the next finding id is F-41"* is now spent: F-41…F-44 are used by this batch and **the next finding id is F-45**. That row is a historical statement of what was true when `docs/17` shipped and is not edited, for the same reason a stage document is never rewritten. |
| `docs/17` §13 | Still accurate. Its "no reconnect" line is now **false** — F-42 closed it — and its "no TLS" line remains true. §13 of that document is not edited here; the correction is recorded in §6.2 above and belongs in the next amendment to `docs/17`. |
| `.env.example` | Updated in this batch: all **25** `NEXUS_PAPER_*` variables with their real defaults, generated from `Settings.model_fields` rather than transcribed, and verified 1:1 — no documented variable that is not a setting and no setting left undocumented. The three comments that carry a ruling say why: the cost model is adverse by construction, `refuse_delayed_data` stays true, and the default feed is the one free source whose seeded mapping clears the archive floor. |
| `README.md` | Updated in this batch. Its `## Docs` index stopped at `docs/06` and did not mention the frontend at all; its status line read *868 tests* and *mypy strict clean (49 files)*. It now carries `docs/07`…`docs/18`, a `frontend/` row, a **Running it** section documenting the two-process shape and the `archive` extra, and gate rows through Stage 11. One claim was corrected rather than merely refreshed: *"No order endpoint"* is now stated precisely — no endpoint can place a **real** order, and the ten under `/v1/paper` are proven inert by the same CI job — because written flatly it would be a falsehood the moment a reader curls `/v1/paper/orders`. Phase 3's marker stays 🔶 rather than being promoted to ✅: its two egress-dependent items (P3-A, P3-B) are still open and listed directly beneath it, and a green tick would contradict the bullets under it. |

The first of those rows is a correction belonging to the next amendment of `docs/17`, not to this one. The
other two were work outstanding when this section was drafted and were closed inside the batch rather than
left for the next one — listed here with what was done, so that a reader can see the omission was found and
not merely that it existed.

---

**AWAITING REVIEW** — D-059 is recorded for ratification, F-44 is open, and Q-6 … Q-9 are unanswered.
Nothing in this batch closes a finding it raised, and no ruling the owner has not made has been
applied.
