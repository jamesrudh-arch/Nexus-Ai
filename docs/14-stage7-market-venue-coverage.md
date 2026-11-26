# 14 — Stage 7: Market & Venue Coverage

Status: **IN PROGRESS** — 7.1 research delivered (§1, board
`design/stage7-1-market-venue-coverage.html`, still `AWAITING REVIEW`), **7.2 delivered** (§2, board
`design/stage7-2-levers-implemented.html`, D-045). Started after the Stage 6 stage-level approval
(D-044, 2026-11-26).

**7.1 changed no production code**: the authorisation the owner gave for Stage 6.2 was scoped to that
batch, so every finding needing a code change was recorded there as a request with its cost, not
delivered. **7.2 did change production code**, on the owner's explicit authorisation of three named
levers (§2.0) — and only those three. Stages 8–23 remain `NOT STARTED`.

Mandate, as recorded in `docs/12` §1.4: *"Stage 7 retires the unverified rows market by market with
evidence per market."* The two rows are bybit's 403 geo-block and dukascopy's
`LAYOUT_VERIFIED = False`.

Binding inputs: `backend/src/nexus/instruments/registry.py` (the capability ladder, `certify`,
`coverage_report`), `backend/src/nexus/domain/instrument.py` (`AssetClass`, `Venue`, `VenueStatus`,
`VenueMapping`), the four adapters in `backend/src/nexus/ingestion/`, `ingestion/pipeline.py`
(the archive gate), `backend/tests/test_live_endpoints.py`, `.github/workflows/venue-verification.yml`,
`docs/05` §5, `docs/06` §4, `docs/00` O-009/O-010; D-007 (venues certified independently), D-019
($0/month), D-021 (deployment host), D-024 (retention; Bybit for Nigeria), D-028 (VM-first),
D-044 (Stage 6 closed).

---

## 1. Sub-deliverable 7.1 — what is actually verified, per venue and per asset class (RESEARCH)

Board: `design/stage7-1-market-venue-coverage.html`. Method: read the live-verification run **at
HEAD** rather than restating the last recorded one; measure the running system instead of inferring
from source; execute the domain types instead of reasoning about them. Three of the nine findings
below were only findable by running something.

### 1.1 Evidence base, and what could not be read

| Source | Identity | Readable here? |
|--------|----------|----------------|
| live venue run **at HEAD** | run `45759709313`, job `139706589069`, commit `25e314e`, 2026-11-26T05:10Z, **success** | yes — check annotation |
| the three runs before it | `45758610197` (`fa74748`, 04:59Z), `45756716181` (`b67ab39`, 04:41Z), `45754638978` (`a77865e`, 04:21Z) — all success | yes — check annotations |
| CI on both commits of this batch | run `45759700949` (`25e314e`) and run `45758603745` (`fa74748`) — **all five jobs success** each (secret scanning, compose config, backend lint/types/tests, runtime smoke in a real container, amd64+arm64 image) | yes — per-job conclusions |
| job logs | `gh run view --log-failed`, `gh api …/jobs/<id>/logs` | **no** — EOF against `results-receiver.actions.githubusercontent.com`, not in this sandbox's allowed hosts |
| raw captures + report artifact | `live-verification` (`live-captures/`) | **no** — download dies against `productionresultssa14.blob.core.windows.net` |
| annotation completeness | GitHub caps annotation text and the workflow truncates its own report | **partial** — `…truncated: 807 escaped characters over the cap`; the 5 GEO-BLOCKED rows and 2 PASS rows are past the cut |
| in-process boot of the API | `create_app()` + `TestClient`, `NEXUS_AUDIT_BACKEND=memory` | yes — executed |
| probe of the domain types | `Venue`, `VenueMapping`, `InstrumentRegistry.register/certify`, `coverage_report` | yes — executed |

All four runs were on this branch and none was dispatched by hand: `venue-verification.yml` also runs
on `pull_request` for changes under `backend/src/nexus/ingestion/**`, so pushing docs re-triggered live
contact with all four sources. That is the luckiest part of this batch — four sets of fresh evidence,
for free, the last two on commits that changed **no code at all**, which is what makes the dukascopy
result below independent of anything in this batch.

### 1.2 The headline overstates coverage by more than half

The published verdict at HEAD is **24 passed / 0 failed / 5 geo-blocked / 0 skipped of 29**,
`PARTIAL - 5 geo-blocked (need a runner outside the restricted region)`. The 29 decompose as
(measured with `NEXUS_LIVE_VERIFY=1 pytest tests/test_live_endpoints.py --collect-only -v`):

| Class | Checks | Network? | At HEAD | Coverage evidence? |
|-------|-------:|----------|---------|--------------------|
| `TestBybitLiveEndpoints` | 5 | yes | 5 GEO-BLOCKED | yes — about bybit, and it says nothing was reachable |
| `TestOkxLiveEndpoints` | 5 | yes | 5 PASS | yes — okx |
| `TestBinanceVisionLiveDumps` | 2 | yes | 2 PASS | yes — binance vision archive |
| `TestDukascopyLiveLayout` | 3 | yes | 3 PASS | yes — URL, layout, price band |
| `TestDukascopyReachabilityDiagnostic` | 1 | yes | 1 PASS | partly — and at HEAD it declined to name a cause (F-5) |
| `TestDukascopyDiagnosisLogic` | 7 | **no** | 7 PASS | **no** — our own verdict logic against fabricated inputs |
| `TestPatienceBehaviour` | 6 | **no** | 6 PASS | **no** — our own retry policy against a fake transport |

**11 of the 29 checks are live evidence about a source.** The other 13 would still pass if every
venue disappeared. Any coverage claim built on "24 passed" would be wrong by more than half, so this
document counts the 11.

### 1.3 The verified numbers, per source (quoted from run `45756716181`, 04:41Z; reproduced by runs `45754638978`, `45758610197` and `45759709313`)

* **OKX — 5/5.** `BTC-USDT-SWAP` contract size 0.01, tick size 0.1, min qty 0.01, qty step 0.01,
  status `live`; bid 61063.2 / ask 61063.3, spread 0.016 bps, uncrossed; 50 trades, in this sample
  carrying both sides, 61063.2–61064.8 (see F-9 — two-sidedness is not asserted, and run 4 returned 50
  buys); 100 one-minute candles spanning 1.65 h; 40-level book, entitlement `LIVE`.
* **Binance Vision — 2/2.** A genuine **71,720-byte ZIP** for 2026-11-19; parsed to 1,440 rows,
  **1,440 accepted, 0 rejected**, `timestamp_units=us`, 1,440 one-minute bars spanning 23.98 h,
  closes 61446.56–64080.80. The `us` field is defect 40's fix observed on real data.
* **Dukascopy — 4/4.** `EURUSD/2026/10/24/12h_ticks.bi5` (0-indexed month segment 10) →
  **25,761 bytes**, reached after **16 transport calls**; `verify_layout` returned
  **`passed=True`, `decompressed_bytes=101480`, `tick_count=5074`, `reasons=-`** — 101,480 is
  5,074 × 20 exactly; parsed ticks 5,074, prices **1.09502–1.0964**, inside EURUSD's real band,
  which is the check that catches a wrong point divisor (the silent 100× error O-010 names).
* **Bybit — 0/5, all GEO-BLOCKED.** 403 at the CloudFront edge on public unauthenticated endpoints.
  Nothing about the adapter is implicated; nothing about it is proven.

Across the four runs the dukascopy layout result is **byte-identical** (`passed=True`, 25,761 →
101,480, 5,074 ticks, `reasons=-`, band 1.09502–1.0964) and so is the binance vision dump (a fixed
historical day, 71,720 bytes, 1,440 rows, 0 rejected, `units=us`); okx prices move as they should
(bid 60960.3 → 61063.2 → 60974.6 → 60925.8) with identical structure each time (depth 40, entitlement
`LIVE`, 0.016 bps); bybit is 5/5 GEO-BLOCKED in all four. What does **not** repeat is the dukascopy
reachability diagnosis — four runs, three patterns (F-5) — nor, as it turns out, okx's trade-side mix
(run 4: all buys) or the agreement between its ticker and its book (F-8, F-9). The transport calls
needed to land one bi5 file were 1, then 16, then 1 and 4, then 1, which is the intermittency measured
rather than described.

### 1.4 Findings

**F-1 — EVIDENCED, NOT RETIRED: dukascopy's layout check has passed against a real file four times
running, and the code still says no real file has ever been downloaded.** `verify_layout`'s docstring states the
bargain — *"Passing these is the evidence required to flip `LAYOUT_VERIFIED` to `True`"*
(`dukascopy.py:219–225`) — and it passed in four consecutive runs (`a77865e`, `b67ab39`, `fa74748`,
`25e314e`), the last two on commits that changed no code, so the result depends on nothing in this
batch. Against that, one constant and four written statements are stale: `dukascopy.py:45`
`LAYOUT_VERIFIED = False`; `dukascopy.py:113` therefore still tags every tick
`DUKASCOPY_BI5_UNVERIFIED`, visible in the same annotation line as the pass; `dukascopy.py:9` and
`test_live_endpoints.py:10` both claim no real file has ever been downloaded — contradicted by
`test_live_endpoints.py:165`, 40 lines later in the same file; `test_live_endpoints.py:674` and
`docs/06:247, :297` still say `verify_layout` has never run against a real file. Consequence: FX
ticks are filed under D-024's retention as provisional forever unless someone notices CI already
produced the evidence. Closes with lever **L-A**; needs the owner's authorisation for `backend/`.

**F-2 — BLOCKED ON A HOST, NOT ON CODE: bybit cannot be retired from any runner GitHub provides, and
the lever to retire it was built in Phase 4 and has never been used.** `venue-verification.yml`
already takes a `runner` input on dispatch whose own description says to use a self-hosted label once
the deployment VM exists, *because Bybit geo-blocks hosted runners* (`:30–37`, `:73–76`). D-024 chose
bybit for Nigeria, where it is not geo-blocked; D-021's host is an Oracle Always Free ARM64 VM. So
retirement costs $0 and needs no code change — a runner label on the machine the system will run on
anyway. Until then bybit's honest rank is `SUPPORTED` and it must never be shown as data-available or
tradable. Closes with lever **L-D**; cannot be attempted from this sandbox (no egress to bybit, no VM).

**F-3 — THE INSTRUMENT MASTER IS EMPTY IN THE RUNNING SYSTEM, NOTHING EVER POPULATES IT, AND SO THE
ARCHIVE GATE CAN NEVER OPEN.** `api/app.py:135` builds `InstrumentRegistry()` — empty.
`InstrumentRegistry.register` (`registry.py:257`) and `.certify` (`:354`) have **zero callers in
production code**; every call site is a test. The API exposes instruments **GET-only**, so nothing
outside the process can populate it either. A real in-process boot returns:

```
GET /v1/instruments/coverage  200
  total=0 active=0 by_asset_class={} by_venue_status={} missing_contract_size=[]
  missing_tick_size=[] ready_for_research=[] ready_for_paper=[] ready_for_live=[]
  live_trading_enabled=false
  note="readiness_for_live describes certification only; live authority is DENIED"
GET /v1/data/coverage         200
  configured=false files=0 bytes=0 partitions={}
  note="no archive configured; nothing has been persisted"
```

The consequence is functional, not cosmetic: `pipeline.py:50` sets
`MINIMUM_STATUS_FOR_ARCHIVE = VenueStatus.DATA_AVAILABLE`. With an empty master no mapping can hold
that status, so **no source's data can be archived** — including the three CI verified this morning.
The adapters can fetch, normalise and prove; the archive gate then refuses, correctly, because nothing
has been certified. Stage 3.5's System Health screen was designed to show "registry-measured coverage
state": today it renders all zeros, and that rendering is honest. Closes with lever **L-C**, which
depends on L-E.

**F-4 — FAIL-OPEN, THEN A CRASH: the only free FX source is not a member of the venue enum, the
domain accepts it anyway, and registration then dies with an unclassified `AttributeError`.**
`Venue` (`domain/instrument.py:36–47`) has nine members — BYBIT, BINANCE, OKX, MT4, MT5, CTRADER,
IBKR, OANDA, ALPACA. **DUKASCOPY is not among them**, although `ingestion/dukascopy.py:40` sets
`VENUE = "DUKASCOPY"` and it is the only FX source the project has. Executed:

```
Venue('DUKASCOPY')  -> ValueError: 'DUKASCOPY' is not a valid Venue
VenueMapping(venue='DUKASCOPY', venue_symbol='EURUSD')  -> constructed, no complaint
   (a dataclass does not enforce its annotations, so `venue: Venue` is documentation only)
registry.register(that instrument)  -> CRASH
   AttributeError: 'str' object has no attribute 'value'
   at instruments/registry.py:282 -> if self._by_venue_symbol.get((m.venue.value, m.venue_symbol)) …
```

An out-of-scope venue is accepted at construction and then raises an **unhandled `AttributeError`
inside `register()`** — not a `CertificationRejected`, not any `NexusError` reason code. Through the
API that is a 500 in a codebase whose posture everywhere else is a classified refusal.
`RegistryChange.venue` is typed `str | None` (`registry.py:91`), so the audit record could not
distinguish an in-scope venue from an arbitrary string either. This stayed hidden because **every FX
test models EUR/USD at `Venue.MT5`** (`test_instrument_registry.py:403`, `test_api_phase3.py:194,
:225`) — a venue with no adapter, no source and a credential requirement. The FX coverage tests pass
while describing a venue the system cannot reach, and the one it can reach cannot be expressed.
Closes with lever **L-B**.

**F-5 — DO NOT OVERCLAIM THE 503: four runs produced three different dukascopy diagnoses, and the
fourth refutes the third.**

```
run 45754638978 (04:21Z, a77865e)  production_ua=ok bytes=25761 lzma=True
  verdict="nothing to diagnose: the production User-Agent works"
run 45756716181 (04:41Z, b67ab39)  production_ua=network-IngestFault  browser_ua=network-IngestFault
  production_ua_other_hour=ok bytes=25313 lzma=True (10h_ticks.bi5)
  verdict="the host was never reached (network-IngestFault), so no cause can be distinguished"
run 45758610197 (04:59Z, fa74748)  production_ua=network-IngestFault  browser_ua=ok bytes=25761
  production_ua_other_hour=network-IngestFault
  verdict="the host was never reached (network-IngestFault), so no cause can be distinguished"
run 45759709313 (05:10Z, 25e314e = HEAD)  production_ua=ok bytes=25761 lzma=True  <- back to run 1
  verdict="nothing to diagnose: the production User-Agent works"
```

The sequence reads: production works, nothing works, browser works, production works. Run 3 pointed
the opposite way from run 1, and run 4 reverted — eleven minutes later it falsified the only theory run
3 could have supported. Any reading drawn from a single run is refuted by another, and adopting a
browser user agent in the adapters on the strength of run 3 would have been circumvention of a host's
stated preference justified by noise. The diagnostic behaved exactly as designed, returning "no cause
can be distinguished" twice rather than inventing one, which is what the seven offline logic tests
require of it. So `docs/00`'s claim that the 503 was "characterised" is
only partly supported: throttling is *consistent* with the evidence (1, 16, then 4 transport calls to
land one file; the patience helper exists because this feed answers intermittently), while no cause
has been *established* and no user-agent conclusion survives four samples. What reproduced in all four
runs is the layout pass — the evidence O-010 actually demands. The honest state is "intermittent,
cause unknown"; four runs in 49 minutes is a start, not a characterisation.

**F-6 — 3 OF 14: fourteen asset classes are declared; three have a free source, one more is
plausible, ten have nothing.** `AssetClass` (`domain/instrument.py:19–33`) declares 14. Implemented
free sources cover `CRYPTO_PERP`, `CRYPTO_SPOT` and `FX_SPOT`. `METALS` is plausible at $0 and
unproven — XAUUSD (divisor 100) and XAGUSD (1000) are already in the same `POINT_DIVISORS` table
(`dukascopy.py:54–67`), so the same bi5 path could serve them, but neither has ever been downloaded
and a divisor is a claim, not evidence. The remaining **ten** (`CRYPTO_FUTURES`, `CRYPTO_OPTIONS`,
`FX_CFD`, `EQUITIES`, `ETF`, `INDICES`, `FUTURES`, `OPTIONS`, `FIXED_INCOME`, `COMMODITIES`) have no
source of any kind, and the six venues that would serve them are enum members with no adapter, all
credentialed and mostly paid — outside D-019's $0/month constraint. Those ten must render
`UNSUPPORTED`, greyed with their registry state, never offered as tradable (the capability-honesty law
from Stage 3.1). That is a design obligation Stage 7 states now and Stage 8+ must honour, not a gap
to fill by invention.

**F-7 — THE LADDER HAS A RUNG FREE SOURCES CANNOT OCCUPY: `CONNECTED` means "auth verified", the four
sources we have use no auth, and nothing refuses a certification whose evidence says so.** The ladder
(`registry.py:12–13`) is `UNKNOWN → SUPPORTED → CONNECTED → DATA_AVAILABLE → TRADE_ENABLED →
LIVE_VERIFIED`, and `is_certification_advance` (`:62`) requires exactly one rung, so `certify` (`:392`)
refuses to skip. `CONNECTED` is documented `# auth verified` (`domain/instrument.py:55`); all four
adapters are credential-free by construction (`requires_credentials = False`). Executed against the
real registry:

```
1. register an OKX BTC-USDT-SWAP mapping
   -> id INS-BTC-USDT-USDT | mapping status UNKNOWN | active False
2. certify straight to DATA_AVAILABLE, evidence = the run id
   -> REFUSED: cannot move UNKNOWN -> DATA_AVAILABLE; the ladder advances one step at a time
3. climb one rung at a time, each with the evidence it actually has
   -> SUPPORTED       evidence 'adapter exists: src/nexus/ingestion/okx.py'
   -> CONNECTED       evidence 'public UNAUTHENTICATED endpoints answered; no credential exists,
                       none was used, so no auth was verified'      <- accepted, without complaint
   -> DATA_AVAILABLE  evidence 'run 45756716181: instruments/quotes/trades/candles/book all
                       normalised from real responses'
4. coverage_report
   -> total=1 active=0 by_venue_status={'DATA_AVAILABLE': 1}
      ready_for_research=('INS-BTC-USDT-USDT',) ready_for_paper=() ready_for_live=()
      archive gate DATA_AVAILABLE satisfied: True
```

Three consequences. **(a)** A freshly registered mapping starts at `UNKNOWN`, not `SUPPORTED`, so
recording what CI proved takes **four** rungs, each needing its own evidence label. **(b)** The
`CONNECTED` rung accepted evidence that **contradicts its own definition** — `certify` requires only a
non-empty string (`:371`) and cannot judge its content, so the ladder's honesty rests entirely on
whoever writes the label. **(c)** Once climbed, the archive gate opens — proof that F-3, not the
adapters, is what stands between verified data and an archive.

Also worth correcting: `docs/12` §1.4 calls okx "connected + live-verified". In this codebase
`LIVE_VERIFIED` means *"live pilot verified + reconciliation proven"* (`domain/instrument.py:58`),
which needs credentials and orders. What okx has is `DATA_AVAILABLE`. The phrase "live-verified" there
means "verified against live data" — the same words, two different meanings, in the document Stage 7
is told to work from. Closes with lever **L-E**, an owner ruling.

**F-8 — EACH ENDPOINT IS CHECKED ALONE: nothing asserts that two endpoints from the same venue agree
with each other, and run 3 shows the gap is measurable.** In run `45758610197` okx's ticker check
recorded `bid=60974.6 ask=60974.7` while the order-book check, sampled seconds later in the same run,
recorded `best_bid=60965.8 best_ask=60965.9` — a difference of **8.8 USD, about 1.4 bps**. Both are
internally sound (each uncrossed at 0.016 bps) and both passed. In a moving market that is entirely
plausible; the point is that the suite **could not distinguish it from a venue serving inconsistent
data across endpoints**, because every check validates one endpoint in isolation. A cross-endpoint
assertion — ticker best bid/ask against the top of the book, sampled together, with a tolerance stated
in bps and the timestamp gap recorded — is cheap and offline-testable against fixtures, and belongs
with the verification module rather than the adapters. It is not required to retire either honesty row,
and nothing here claims it is.

**F-9 — A CLAIMED INVARIANT THAT IS NOT ONE: "50 trades with both sides present" was a property of
one sample, and run 4 returned 50 buys and passed.** `docs/06:234` records okx's first live
verification as *"50 trades with both sides present and prices inside the quoted band"*, and the same
phrase appears in `docs/00`'s first-contact row. Reading the check: `_assert_ticks` asserts that trades
came back, that each `observed_at` is timezone-aware, that each `source` matches, that prices and
quantities are positive, and that each `side` is inside the vocabulary `(None, "BUY", "SELL")` — it
never asserts that **both** sides appear; `sides=[…]` is recorded as evidence only. Run 4 makes the
difference visible: `okx.trades count=50 price_min=60920.7 price_max=60925.9 sides=['BUY']` — all
fifty buys — and the check **passed**, correctly, because a 50-trade window in a quiet minute can
legitimately be one-sided. Note the asymmetry with the very next helper: `_assert_book` *does* fail a
one-sided book (`assert book.bids and book.asks, "one-sided book"`). So two-sidedness is an invariant
for the book and an observation for trades. No defect in the code — the assertion set is defensible —
but the **documentation overstates what is verified**, which is the class of error this stage exists to
correct. Closes with a wording correction in `docs/06` and `docs/00` (docs only, no authorisation
needed) plus an owner decision on whether one-sidedness in trades should ever be a failure.

Two smaller observations from the same probe, recorded rather than acted on: the generated id
`INS-BTC-USDT-USDT` for canonical symbol `BTC/USDT:USDT` is ugly and near-ambiguous (`registry.py:656`
replaces both `/` and `:` with `-`), and ids are the UI's primary key, so the seeding work in L-C
should choose canonical symbols whose slugs stay readable. And `register()` forces `active=False`
(activation is a separate decision, D-002), so a seeded master reports `active=0` until instruments
are explicitly activated — coverage and activation are two different numbers and the UI must not
conflate them.

### 1.5 Coverage matrix

Per venue — full table on the board; in short: **okx** nothing recorded, evidence supports
`DATA_AVAILABLE` for one instrument; **bybit** nothing recorded, evidence supports `SUPPORTED` only;
**binance vision** nothing recorded, evidence supports `DATA_AVAILABLE` for spot daily dumps (an
archive, not a venue — no quotes, book or orders, so no trade rung is meaningful); **dukascopy**
nothing recorded *and cannot be*, evidence supports `DATA_AVAILABLE` for EURUSD bi5 ticks once F-1 and
F-4 close; **MT4/MT5/CTRADER/IBKR/OANDA/ALPACA** no adapter, no source, `UNKNOWN`, outside D-019.

Per asset class: 3 of 14 sourced (F-6), `METALS` plausible and unproven, 10 with nothing and
therefore `UNSUPPORTED` and greyed.

Nothing anywhere is `TRADE_ENABLED` or `LIVE_VERIFIED`: both need credentials, an order lifecycle and
a pilot with reconciliation, which is Stage 9 and later. No claim on this board implies otherwise.

### 1.6 What retiring the two rows requires — five levers, all $0

| Lever | Closes | Cost | Authorisation | Possible from here? |
|-------|--------|------|---------------|---------------------|
| **L-A** flip `LAYOUT_VERIFIED`, switch the source tag, correct the four stale statements | F-1 (the dukascopy row) | $0 — one constant at `dukascopy.py:45`, the tag at `:113`, text at `dukascopy.py:9/:14`, `test_live_endpoints.py:10/:674`, `docs/06:247/:297` | **the owner's** — production code | yes, immediately |
| **L-B** add `DUKASCOPY` to `Venue`; refuse an out-of-scope venue at the domain boundary with a classified error instead of crashing | F-4 | $0 — one enum member plus validation raising a `NexusError` | **the owner's** — production code, and it changes D-007's venue scope | yes, immediately |
| **L-C** seed the master from evidence: register only the instruments the sources really serve, each at the rank its evidence supports and no higher, citing the run id | F-3 | $0 — a bootstrap module plus tests | **the owner's** — production code, and it decides what the whole UI shows | yes, immediately |
| **L-D** dispatch `venue-verification.yml` with `runner` set to a self-hosted label on the deployment host | F-2 (the bybit row) | $0 — the input already exists | nobody's — no code change, but the VM must exist | **no** — needs D-021/D-028 |
| **L-E** rule on what `CONNECTED` means for a credential-free source, or add a rung for it | F-7 | $0 — a definition and possibly one enum rung | **the owner's** — changes the certification vocabulary every later stage cites | yes, immediately |

Order matters: L-E settles the vocabulary, L-B makes FX representable, L-A retires the dukascopy row,
L-C makes coverage real, L-D waits on a machine.

### 1.7 Limitations of this batch

1. **No production code changed.** Everything needing a change is a request with a cost, not a
   delivery. The files touched are `docs/` and `design/` only.
2. **The live numbers come from GitHub's runner, not this sandbox**, which has egress only to
   github.com, npm and PyPI. Every market figure is quoted from a check annotation with its run and
   job id.
3. **The report is truncated at GitHub's annotation cap and the artifact is undownloadable.** 807
   characters of the HEAD report are past the cut, including all five GEO-BLOCKED rows. The claim
   "the 5 geo-blocked checks are the 5 bybit checks" is an **inference** from the local collection
   (`TestBybitLiveEndpoints` has exactly 5) plus the headline count — not a quoted row.
4. **Four runs gave three different dukascopy diagnoses** (F-5), so the 503 is not characterised, no
   cause is claimed, and no user-agent conclusion is drawn from any single run.
5. **okx numbers are a snapshot at 04:41Z**; bid 61063.2 will be wrong by the time this is read. The
   durable claims are structural: uncrossed book, both trade sides, contiguous candles, entitlement
   `LIVE`.
6. **Verification proves data parsed inside asserted bands, not that it is correct.** A venue serving
   plausible-but-wrong prices would pass. Reconciliation against a second source would catch that and
   is not built.
7. **Dukascopy was verified for one pair, one hour.** 13 pairs carry divisors; 12 are unverified, and
   a wrong divisor is a silent 100× error — so "FX covered" would badly overstate it.
8. **No instrument is `active` and none can be traded**: `register()` forces `active=False` (D-002),
   trade authority needs `TRADE_ENABLED`, and the environment is `DISABLED` with
   `NEXUS_LIVE_TRADING_ENABLED=false`.
9. **No cross-endpoint consistency is asserted** (F-8), so okx's ticker and its book were 1.4 bps
   apart in run 3 and nothing in the suite would notice a larger disagreement.
10. **Only four runs were observed, within 49 minutes.** That is enough to show the layout result
    reproducing and the diagnosis not reproducing; it is not enough to characterise a feed's
    availability, which needs runs over days — the weekly schedule will accumulate them.
11. **Two claims in `docs/05`/`docs/06` describe sample properties as if they were invariants** —
    okx's trade sides (F-9). They are corrected in wording here; the underlying documents still carry
    the original phrasing until the owner rules, since `docs/06` is a closed Phase 4 record.

### 1.8 Corrections made to the record in this batch

Found while re-reading the approved artifacts for this stage, and corrected here rather than left to
contradict the register:

* `docs/07` — the Stage 3 narrative header still read `IN PROGRESS` with "batch 3.2 in progress"
  although Stage 3 was approved at stage level by D-037, and it carried a fragment of the Stage 2
  paragraph spliced into it. Replaced with the real state of Stages 3–6 and a note that it was
  corrected, since a register whose prose disagrees with its own decision rows cannot be used to tell
  what is approved.
* `docs/12`, `docs/13` — both status headers read `IN PROGRESS` after their approvals (D-041, D-044).
* `design/index.html` — every entry from 3.1 to 6.2 read "awaiting review"; the page header still said
  "STAGE 3 IN PROGRESS".
* `design/build_board62.py` and the built Stage 6.2 board — the footer said gate **975/2/0** after the
  verified number became **976/2/0** (the body of the same board was already correct). The board was
  rebuilt; the published artifact had carried the wrong number since `a77865e`.

### 1.9 Decision requested

Stage 7 cannot retire either honesty row without touching `backend/`, and the authorisation for that
was scoped to Stage 6.2. Four questions, in dependency order:

1. **Authorise the Stage 7.2 code changes?** The smallest useful batch is **L-A + L-B + L-E**: flip
   `LAYOUT_VERIFIED` on evidence CI already produced, make `DUKASCOPY` a venue and refuse
   out-of-scope venues with a classified error, and settle what `CONNECTED` means for a
   credential-free source. All $0, all testable offline, no new dependency.
2. **The `CONNECTED` ruling (L-E).** Either (a) redefine it as "the endpoint answered and normalised;
   auth not applicable for public data", or (b) insert a rung for credential-free sources. (a) is one
   comment and no enum change; (b) is more honest but touches every rank comparison and the audit
   vocabulary. **Recommendation: (a)**, with the evidence label required to state *why* auth is not
   applicable — the registry cannot judge the label, so the label must carry the reason.
3. **Seed the master (L-C) in 7.2 or as its own 7.3?** It is what makes coverage non-zero and the
   archive gate reachable (F-3), but it decides what the whole UI shows, and it must be seeded only
   with instruments whose evidence exists — okx `BTC-USDT-SWAP`, binance vision spot dumps, dukascopy
   `EURUSD` — each citing its run id. It is a larger batch than L-A/L-B/L-E.
4. **Bybit (L-D) stays open, recorded as blocked on the VM** rather than dropped from sight — confirm
   the row stays `GEO-BLOCKED / SUPPORTED` until D-021's host exists.

---

## 2. Sub-deliverable 7.2 — three levers implemented (L-A, L-B, L-E)

Status: **DELIVERED, AWAITING REVIEW.** Authorised by the owner 2026-11-26 (**D-045**), implemented
across the batch's commits — `bc4a718` (the three levers), `41aca23` (a citation correction),
`354b95c` (F-10 and the run count), `f675582` (the run count again, because two more runs landed
while it was being written), `500ac36` (**F-11**, found by the first run to exercise the F-10 fix
live, plus the counts corrected to twelve runs), `88af6f4` (runs 13–14, the corrected branch
exercised live) and the correction commits that follow. Board:
`design/stage7-2-levers-implemented.html`.

This is the first `backend/` production change since Stage 6.2. Scope held to the three levers and
the two findings they exposed: **6 production files and 5 test files in `backend/` — 790 insertions,
50 deletions** (`git diff --stat 8d8f6f2 -- backend/`), plus 4 documents and 3 design files. Nothing
else in `backend/` was touched — no API route, no store module, no migration, no adapter other than
dukascopy's constants and docstrings.

### 2.0 What the owner authorised, verbatim in effect

Three questions were put (§1.9); the owner answered `Recommend` to all three, which adopts the
recommendations as written:

| Question | Answer adopted | What it bound this batch to |
|----------|----------------|------------------------------|
| Authorise Stage 7.2 code changes? | **L-A + L-B + L-E now**; L-C deferred to 7.3; L-D waits on the D-021 VM | Three levers, no more. The master stays empty (F-3 open) and bybit stays blocked (F-2 open) |
| The `CONNECTED` ruling | **Redefine it** (option (a)): one comment, **no enum change, no new rung** | The ladder, `CERTIFICATION_ORDER`, `coverage_report` thresholds and the audit vocabulary had to stay byte-identical in meaning. Verified in §2.3 |
| Bybit's row | **Stays open and visible** as `GEO-BLOCKED / SUPPORTED`, reported every run | No row removed, no status invented. It appears as `5 geo-blocked` in the headline of all twelve runs below |

### 2.1 L-A — the dukascopy row is retired (F-1 → CLOSED for EURUSD)

`LAYOUT_VERIFIED` is now `True` (`dukascopy.py:70`) and every parsed record carries
`source="DUKASCOPY_BI5"` instead of `DUKASCOPY_BI5_UNVERIFIED`. The evidence is **twelve consecutive
CI runs on 2026-11-26**, all `conclusion=success`, all fetching the same hour, all returning
byte-identical results:

| # | Run | Job | Commit | Created (UTC) | `LAYOUT_VERIFIED` | `verify_layout` | Checks |
|---|-----|-----|--------|---------------|-------------------|-----------------|--------|
| 1 | `45754638978` | `139690278846` | `a77865e` | 04:21:01 | `False` | `passed=True` | 24/0/5/0 of 29 |
| 2 | `45756716181` | `139696937355` | `b67ab39` | 04:40:38 | `False` | `passed=True` | 24/0/5/0 of 29 |
| 3 | `45758610197` | `139703054396` | `fa74748` | 04:59:09 | `False` | `passed=True` | 24/0/5/0 of 29 |
| 4 | `45759709313` | `139706589069` | `25e314e` | 05:09:21 | `False` | `passed=True` | 24/0/5/0 of 29 |
| 5 | `45782533635` | `139781214750` | `bc4a718` | 08:21:55 | **`True`** | `passed=True` | 24/0/5/0 of 29 |
| 6 | `45782540670` | `139781237726` | `bc4a718` | 08:21:58 | **`True`** | `passed=True` | 24/0/5/0 of 29 |
| 7 | `45784665370` | `139788299846` | `41aca23` | 08:36:56 | **`True`** | `passed=True` | 24/0/5/0 of 29 |
| 8 | `45784657260` | `139788273040` | `41aca23` | 08:36:53 | **`True`** | `passed=True` | 24/0/5/0 of 29 |
| 9 | `45786440060` | `139794273725` | `354b95c` | 08:49:32 | **`True`** | `passed=True` | 27/0/5/0 of **32** |
| 10 | `45786447356` | `139794299438` | `354b95c` | 08:49:35 | **`True`** | `passed=True` | 27/0/5/0 of **32** |
| 11 | `45787390006` | `139797515877` | `f675582` | 08:56:10 | **`True`** | `passed=True` | 27/0/5/0 of **32** |
| 12 | `45787399434` | `139797547309` | `f675582` | 08:56:14 | **`True`** | `passed=True` | 27/0/5/0 of **32** |

*(passed / failed / geo-blocked / skipped. Runs 1–4 produced the evidence for the flip; runs 5–12 are
the flip's falsifiability test — **eight** runs with the flag on, all still green.)*

**Twelve is a floor, not a final count.** Every push that touches `backend/src/nexus/ingestion/**`
re-triggers this workflow, and `pull_request` events are not suppressed by that path filter, so two
more runs appear per commit — including the commit that carries this section. The claim is therefore
stated as a floor that no run has ever broken: `verify_layout` has passed on a real file in every
venue run since 2026-11-25, and a future failure means `LAYOUT_VERIFIED` goes back to `False` rather
than the check being relaxed. Reproduce with the loop in §2.6.

Every one of the twelve reported, identically:

```
dukascopy.url    hour=2026-11-24T12:00:00+00:00  bytes=25761  month_segment=10
dukascopy.layout passed=True payload_bytes=25761 decompressed_bytes=101480 tick_count=5074 reasons=-
dukascopy.ticks  count=5074 price_min=1.09502 price_max=1.0964
                 source=DUKASCOPY_BI5 layout_verified=True      <- runs 5-12; runs 1-4 read _UNVERIFIED/False
```

101,480 = 5,074 × 20 exactly, so the record size is confirmed against a real file, and
`reasons=-` means no check failed. Prices 1.09502–1.0964 sit inside EURUSD's real band, which is the
assertion that exists to catch a wrong point divisor — the silent 100× error.

**The hour is `2026-11-24T12:00Z`, a Tuesday**, which is what `_recent_weekday_hour()` selects. Its
path is `EURUSD/2026/10/24/12h_ticks.bi5`: the `10` is **November**, because the month segment is
0-indexed. See §2.4 for how this nearly entered the record wrongly.

**What the flag now claims, and what it does not.** The record *layout* is the same for every pair,
so `LAYOUT_VERIFIED` legitimately generalises. The *point divisor* is pair-specific, so it does not:
`LAYOUT_VERIFIED_PAIRS = ("EURUSD",)` (`dukascopy.py:78`) and `summarise()` now emits
`layout_verified_pairs` and `divisor_unverified_pairs` (`dukascopy.py:428-429`), which names the
**twelve other pairs** — GBPUSD, AUDUSD, NZDUSD, USDCAD, USDCHF, EURGBP, EURJPY, USDJPY, GBPJPY, AUDJPY, XAUUSD,
XAGUSD. Pinned by `test_the_verified_scope_is_machine_readable`. Also unchanged: layout verification
is not price verification (§2.5), and the feed is intermittent (§1.4 F-5, restated over twelve runs in
the module docstring, which now records **five** distinct probe patterns rather than four).

**Stale statements corrected.** `dukascopy.py` module docstring (rewritten, including the invented
`{BID|ASK}` URL segment that defect 39 removed), the `LAYOUT_VERIFIED` comment, `source_label()`'s
docstring, `verify_layout()`'s docstring (kept, with the reason it survives its own flag);
`test_adapters.py` module docstring, `test_dukascopy_layout_is_declared_unverified` →
`..._is_declared_verified` (now citing the twelve runs), `test_source_is_labelled_unverified` →
`..._with_the_layout_state`, the fetch-report and summary assertions;
`test_live_endpoints.py` module docstring, the layout-gate assertion message, and the reachability
diagnostic's history paragraph; `docs/06:245-251` and `:297` (superseded in place, history kept).

### 2.2 L-B — the venue vocabulary is enforced at the boundary (F-4 → CLOSED)

`Venue` gained `DUKASCOPY` (`instrument.py:67`) — **10 members** now — so the only free FX source is
representable and FX coverage can be recorded at all. New `InstrumentDefinitionError`
(`instrument.py:21`) carrying a new reason code `RejectReason.INSTRUMENT_DEFINITION_INVALID`
(`errors.py:37`). Validation moved to the boundary, where the bad value arrives:

| Boundary | Refuses | Was |
|----------|---------|-----|
| `VenueMapping.__post_init__` (`instrument.py:118`) | a `venue` that is not a `Venue`; a `status` that is not a `VenueStatus` | constructed silently |
| `CanonicalInstrument.__post_init__` (`instrument.py:162`) | an `asset_class` that is not an `AssetClass`; a `mappings` entry that is not a `VenueMapping` | constructed silently |
| `InstrumentRegistry.certify` (`registry.py:379`) | a bare-string `venue` or `to_status` | `AttributeError` later |

The F-4 transcript, re-run against the fixed code:

```
VenueMapping(venue="DUKASCOPY", venue_symbol="EURUSD")
  -> InstrumentDefinitionError  reason=INSTRUMENT_DEFINITION_INVALID
     detail: a venue mapping's venue must be a Venue member (D-007 scope); got 'DUKASCOPY' of type str
VenueMapping(venue="NOT_A_VENUE", ...)      -> INSTRUMENT_DEFINITION_INVALID
Venue("DUKASCOPY")                          -> Venue.DUKASCOPY   (enum members: 10)
register(EUR/USD on Venue.DUKASCOPY)        -> INS-EUR-USD, venue DUKASCOPY
certify("INS-BTC-USDT-USDT", "BYBIT", ...)  -> InstrumentDefinitionError: certification needs a Venue member
```

Before this batch the same first line constructed happily and then died at the first `m.venue.value`
inside `register()` — an unclassified `AttributeError`, which through an API would have been a 500
where every comparable condition is a named refusal. `RegistryChange.venue` stays `str | None`, but
its docstring now records why that is safe: only a `Venue` member's value can reach it.

**What L-B does not close.** There is no HTTP endpoint that registers or certifies anything
(`api/app.py` instruments routes are GET-only), so this refusal cannot yet be exercised through the
API — it protects the domain boundary and every future caller, including Stage 8+'s. And the master
is still empty at boot (F-3), which is L-C's job in 7.3. Pinned by
`TestVenueVocabularyIsEnforced` (9 tests), including `test_fx_coverage_is_recordable_end_to_end`,
which walks EUR/USD on `Venue.DUKASCOPY` from register to `DATA_AVAILABLE` and asserts
`ready_for_research == ("INS-EUR-USD",)` with `ready_for_paper == ()` and `is_tradeable is False` —
data still is not permission.

### 2.3 L-E — `CONNECTED` declares its authentication case (F-7 → CLOSED as a definition)

The ruling as adopted: **`CONNECTED` means "the venue answered and its responses normalised", not
"auth verified"**. Certifying to it now requires an explicit declaration
(`AUTH_VERIFIED` / `AUTH_NOT_APPLICABLE`, `registry.py:62-64`), which is recorded as
`RegistryChange.auth_state` (`registry.py:121`) and surfaced in `to_audit_payload()`.

What the ruling deliberately did **not** touch, because the owner's answer forbade it:

| Untouched | Verified by |
|-----------|-------------|
| `VenueStatus` — still 6 members, no new rung | `len(VenueStatus) == 6` |
| `CERTIFICATION_ORDER` — same six rungs, same order | `len(CERTIFICATION_ORDER) == 6`; `test_order_is_the_documented_ladder` |
| Ladder arithmetic — `certification_rank`, `is_certification_advance`, one-step-at-a-time | `test_cannot_skip_rungs` still passes unchanged |
| `coverage_report` thresholds — research / paper / live | `test_readiness_follows_certification` unchanged |
| Audit vocabulary — change kinds `REGISTER/ACTIVATE/DEACTIVATE/CERTIFY/DE_CERTIFY/REMAP` | `auth_state` is an added field, not a new kind; `test_payload_is_bounded` still passes |

Behaviour, measured:

```
certify(..., CONNECTED, evidence="it answered")                     -> CertificationRejected
   "certifying CONNECTED requires an explicit auth declaration — AUTH_VERIFIED (a credential was
    presented and accepted) or AUTH_NOT_APPLICABLE (public, credential-free, and the evidence label
    must say why). CONNECTED no longer assumes auth was verified"
certify(..., CONNECTED, auth="PROBABLY_AUTHENTICATED")              -> CertificationRejected: must be one of
certify(..., CONNECTED, auth=AUTH_NOT_APPLICABLE)                   -> accepted
   change log: [('CERTIFY','SUPPORTED',None), ('CERTIFY','CONNECTED','AUTH_NOT_APPLICABLE'),
                ('CERTIFY','DATA_AVAILABLE',None)]
certify(..., SUPPORTED, auth=AUTH_NOT_APPLICABLE)                   -> CertificationRejected
   "an auth declaration belongs to the CONNECTED rung only"
certify(..., CONNECTED) when already CONNECTED                      -> no-op, needs no declaration
demotion DATA_AVAILABLE -> CONNECTED without a declaration          -> CertificationRejected
```

A restatement records nothing, so it claims nothing and needs no declaration; a *demotion* to
`CONNECTED` does record, so it does. The refusal text names both options and why the rung changed,
because a refusal that does not say how to comply just produces the same mistake again.

**Why this mattered more than a comment.** §1.4 F-7 measured that a credential-free source could not
occupy `CONNECTED` honestly, and since the ladder does not skip, `DATA_AVAILABLE` was unreachable for
all four sources this system uses — which made `MINIMUM_STATUS_FOR_ARCHIVE = DATA_AVAILABLE`
(`ingestion/pipeline.py:50`) unsatisfiable by any free source. `test_a_credential_free_source_can_now_reach_the_archive_gate`
pins the whole chain: `AUTH_NOT_APPLICABLE` at `CONNECTED`, then `DATA_AVAILABLE`, then
`certification_rank(status) >= certification_rank(MINIMUM_STATUS_FOR_ARCHIVE)`, with
`ready_for_paper == ()` and `is_tradeable is False`. **The archive gate is now reachable in
principle; it is still not reachable in production, because the master is empty (F-3, L-C, 7.3).**

**Ten pre-existing certification sites** across three test modules had to state their case (18 `auth=`
sites in total once the 8 inside the new tests are counted — both figures recomputed from the files,
not estimated). Every venue in them is a public feed, so every declaration is `AUTH_NOT_APPLICABLE`,
threaded through a local `_auth_for(status)` helper (one per module) rather than hardcoded, so a test
that climbs to a different rung cannot silently mis-declare.

### 2.4 F-10 — a diagnostic verdict contradicted by its own probes (NEW, found and fixed here)

Found by reading run 7's evidence lines rather than its headline. `_diagnose_dukascopy`
(`test_live_endpoints.py`) tested `baseline.startswith("network-")` **before** testing whether either
variant had succeeded, so a production-UA network fault published *"the host was never reached, so no
cause can be distinguished"* even when the same run's probes had reached it. Four runs did that, and
each is refuted by the line printed next to it:

| Run | production UA | browser UA | other hour | published verdict |
|-----|---------------|------------|------------|-------------------|
| `45756716181` | `network-IngestFault` | `network-IngestFault` | **`ok` 25,313 bytes, `lzma=True`** | "never reached" ✗ |
| `45758610197` | `network-IngestFault` | **`ok` 25,761 bytes, `lzma=True`** | `network-IngestFault` | "never reached" ✗ |
| `45784665370` | `network-IngestFault` | **`ok` 25,761 bytes, `lzma=True`** | `network-IngestFault` | "never reached" ✗ |
| `45784657260` | `network-IngestFault` | **`ok` 25,761 bytes** | **`ok` 25,313 bytes** | "never reached" ✗✗ |

The branch now checks both variants first and reports what was measured: the production attempt got
no reply, the host *did* answer a browser User-Agent on the same hour and/or the production
User-Agent on a different hour, so this is not an unreachable host, and one attempt per variant
cannot separate a transient fault from a rejection. "Never reached" survives for the only case where
it is true — nothing answered. The action text keeps the User-Agent question as an **OWNER DECISION**,
never an automatic workaround.

Three offline tests pinned the shapes that had occurred and were pinned by nothing:
`test_a_browser_success_refutes_never_reached`, `test_another_hour_answering_also_refutes_never_reached`,
`test_never_reached_still_holds_when_nothing_answered`. Runs 9–12 report
`27 passed / 0 failed / 5 geo-blocked / 0 skipped of 32`, and the three new checks appear by name in
those annotations. The live-source count is unchanged at 11; the denominator moved, the coverage did
not.

Runs 9 and 10 both had `production_ua=ok`, so the corrected branch was not exercised live by them.
**Run 12 did exercise it** — and showed the fix was incomplete.

#### F-11 — an HTTP reply is also proof the host was reached (NEW, found and fixed here)

Run `45787399434` (12 in the table above, at `f675582`) is the first run since the F-10 fix in which
the production User-Agent faulted. Its three probes recorded:

| Probe | Outcome | What it proves |
|-------|---------|----------------|
| production UA, requested hour | `network-IngestFault` | the attempt got no reply |
| browser UA, same hour | `network-IngestFault` | that attempt got no reply either |
| production UA, different hour | **`http-503`** | **the host answered** — a status code is a reply |

and it published `verdict=the host was never reached (network-IngestFault), so no cause can be
distinguished`. That is the same false claim as F-10, from the branch that was supposed to have
removed it. The fix counted only `ok` outcomes as proof of reach; it did not count an HTTP status.
The function's own comment already said why that is wrong — *"a host that never answered is a
different fact from a host that answered 503"* — and the code contradicted its own comment whenever
the 503 came from a *variant* rather than from the baseline.

**Why it was missed, recorded because it is the second instance of the same shape:** the F-10 tests
pinned one case per branch that had actually occurred. No combination with a network baseline and an
`http-*` variant had occurred in the runs available at the time, so nothing pinned it, and the gap
only appeared when CI produced that combination. This is precisely the failure mode the project has
already been bitten by twice — a branch-order bug invisible until a rare combination occurs live — so
the remedy is the one that should have been applied the first time: **enumerate the cross-product.**

`reached` now counts an `http-*` reply from either variant, names the status it measured, and adds
that the host is reachable but not serving when no variant retrieved a file. Four tests were added:
`test_an_http_reply_from_a_variant_also_refutes_never_reached` (run 12's exact inputs),
`test_a_browser_http_reply_refutes_never_reached_too` (the same gap on the other probe),
`test_a_variant_that_returned_a_file_is_not_described_as_not_serving` (the new clause must not fire
when a file came back), and
`test_never_reached_is_claimed_only_when_all_three_probes_got_no_reply`, which iterates all
**5³ = 125** combinations of five outcomes and asserts that "never reached" appears **if and only if**
all three probes faulted at the network layer. That last test is the one that makes a third instance
of this bug class impossible to commit silently.

**The live module now collects 36 checks** (29 → 32 in `354b95c` → 36 here); the offline subset run
in this batch is 20 (was 13, then 16). Live-source checks are still **11** — both increases were tests
of our own diagnosis logic against fabricated inputs, and neither adds coverage evidence.

**Runs 13 and 14 confirm it live.** The commit carrying the F-11 fix triggered two more venue runs —
`45796096183` (push) and `45796115693` (pull request), both `conclusion=success`, and the first to
collect 36: `30 passed / 0 failed / 5 geo-blocked / 1 skipped of 36` and
`31 passed / 0 failed / 5 geo-blocked / 0 skipped of 36`. All four new checks appear by name in both
annotations. `verify_layout` passed again in both, making that the thirteenth and fourteenth
consecutive passes.

Run 13 is also **the first live exercise of the corrected branch**, and it published the corrected
wording rather than the false claim:

```
dukascopy.probe.production_ua              outcome=network-IngestFault
dukascopy.probe.browser_ua                 outcome=ok  bytes=25761  lzma=True
dukascopy.probe.production_ua_other_hour   outcome=ok  bytes=25313  lzma=True
dukascopy.diagnosis verdict=the production attempt got no reply (network-IngestFault) but the host
  did answer a browser User-Agent on the same hour (a valid file came back) and the production
  User-Agent on a different hour (a valid file came back) in the same minute, so this is not an
  unreachable host; one attempt per variant cannot separate a transient network fault from a
  rejection   action=re-run: … a repeat failure while a variant keeps working is an OWNER DECISION
```

**Run 15 exercised it a second time.** `45797880440`, triggered by `88af6f4`, reported
`31 passed / 0 failed / 5 geo-blocked / 0 skipped of 36` with `production_ua=network-IngestFault`,
`browser_ua=ok` (25,761 bytes) and `other_hour=network-IngestFault` — a *different* combination from
run 13 — and published the corrected verdict again, naming the one variant that answered. So the
corrected branch has now been exercised live twice, on two different input shapes. `verify_layout`
has passed in **every venue run since 2026-11-25** — fifteen consecutive passes were read for this
batch, and each commit since has added two more attempts, none of which has failed.

Run 13's single skip is the designed behaviour, not a regression: its ticks fetch did not answer, so
the check skipped rather than failed (`test_live_endpoints.py:153`, *"did not answer, so nothing is
verified either way"*), and the headline says so — `1 could not reach their source`. The layout check
in the same run used the patient fetch and passed. Note what this run therefore demonstrates and what
it does not: runs 13 and 15 both exercise the branch that reports a **succeeded** variant. The
F-11-specific combination — a network baseline beside an `http-*` reply — has still not recurred, so
that half of the fix remains offline-evidenced by the 125-combination test.

**Two corrections to this batch's own record.**

1. **A path that does not exist was nearly published as the evidence citation.** The verified file
   was first written up as `EURUSD/2026-10-24/12h_ticks.bi5`. The real path is slash-separated with
   a 0-indexed month — `hour_url("EURUSD", 2026-11-24T12:00Z)` emits
   `…/datafeed/EURUSD/2026/10/24/12h_ticks.bi5`; for 24 October it would emit `…/2026/09/24/…`. Two
   genuine hyphenated errors were committed in `bc4a718`, both in `test_adapters.py`: a docstring, and
   a fixture URL that would 404 if anything ever fetched it — it passed only because `summarise()`
   never validates a URL against its hour. Both fixed in `41aca23`, and the fixture now uses the hour
   the runs really fetched.
   **Cause, recorded because it will recur:** this environment's output rendering displays `/` as `-`
   inside date-like sequences, so a *correct* path reads as a wrong one and a wrong one reads as
   correct. Every path claim in this batch is now either generated by `hour_url()` or verified by
   character-level comparison, never by eye. `docs/06` still contains four hyphenated paths in
   historical rows; a correction note there says so and gives the generated forms.
2. **`41aca23`'s commit message overclaimed.** It said the citation committed in `bc4a718` was
   hyphenated; in `dukascopy.py` the path was already slash-correct. The error was real but narrower
   than the message said. Corrected here rather than by rewriting a pushed commit.

### 2.5 F-8 measured across twelve runs — quantified, not fixed

F-8 said nothing asserts that two endpoints from one venue agree, and that a fix needs a stated
tolerance plus a recorded timestamp gap. The twelve runs' recorded evidence now sizes the problem.
Comparing `okx.quotes` (ticker) against `okx.book` (order book) in the same run:

Convention, stated because it changes the third decimal: `gap_bps = |mid_quotes − mid_book| /
mid_quotes × 10⁴`. Dividing by the book mid instead gives 2.224 rather than 2.223 for run 6 and the
same mean — so no conclusion below depends on the choice, but the number quoted must say which it used.

| # | quote bid/ask | book bid/ask | mid gap | # | quote bid/ask | book bid/ask | mid gap |
|---|---------------|--------------|---------|---|---------------|--------------|---------|
| 1 | 60960.3/60960.4 | 60960.3/60960.4 | 0.000 bps | 7 | 60692.3/60692.4 | 60692.3/60692.4 | 0.000 bps |
| 2 | 61063.2/61063.3 | 61063.2/61063.3 | 0.000 bps | 8 | 60692.3/60692.4 | 60692.3/60692.4 | 0.000 bps |
| 3 | 60974.6/60974.7 | 60965.8/60965.9 | **1.443 bps** | 9 | 60989.2/60989.3 | 60995.3/60995.4 | **1.000 bps** |
| 4 | 60925.8/60925.9 | 60925.8/60925.9 | 0.000 bps | 10 | 60990.0/60990.1 | 60988.6/60988.7 | 0.230 bps |
| 5 | 60721.9/60722.0 | 60726.7/60726.8 | **0.790 bps** | 11 | 60912.6/60912.7 | 60912.6/60912.7 | 0.000 bps |
| 6 | 60726.7/60726.8 | 60713.2/60713.3 | **2.223 bps** | 12 | 60900.0/60900.1 | 60897.0/60897.1 | **0.493 bps** |

Exactly zero in **6 of 12**; min 0.000, max **2.223**, mean **0.515 bps**; above the 0.016 bps quoted
spread in **6 of 12**. (Over the first ten runs the same computation gave max 2.223 and mean 0.569;
adding runs 11 and 12 moved the mean, not the max.) Two facts make a tolerance unchoosable today: the
`okx.book` evidence line records **no timestamp** (verified across all twelve), so a gap cannot be
attributed to elapsed time or to disagreement; and the two endpoints are fetched sequentially, not
atomically, so some gap is expected. Choosing a number now would be inventing one — F-8 stays open,
with its magnitude measured.

**A false finding this measurement nearly produced, recorded so nobody repeats it.** A natural
cross-check is "every trade price lies inside the current book". It fails in **12 of 12 runs** — and
it is not a defect. Trades are historical prints; the book has moved since. Asserting containment
would have manufactured a finding out of normal market behaviour, which is the same error class as
F-9 (an invariant that is not one) in the opposite direction.

### 2.6 Gate evidence

| Gate | Result | Command |
|------|--------|---------|
| Suite | **997 passed, 2 skipped, 0 failed** (was 976 + 2) | `pytest` with CI's env (`NEXUS_AUDIT_BACKEND=memory NEXUS_ENVIRONMENT=DISABLED DO_NOT_TRACK=1`) |
| New tests | **+21 to the gate total**: 20 in `test_instrument_registry.py` (`TestVenueVocabularyIsEnforced` 9, `TestConnectedDeclaresItsAuthCase` 11), 1 in `test_adapters.py`. A further **7 offline checks** live in `test_live_endpoints.py` — 3 for F-10, 4 for F-11 — which the default gate skips as a module, so they move the collection count (29 → 36) and not 997 |
| Live module offline subset | **20 passed** (was 13, then 16) | `NEXUS_LIVE_VERIFY=1 pytest tests/test_live_endpoints.py -k "DiagnosisLogic or PatienceBehaviour"` |
| Live module collected | **36** (was 29, then 32); live-source checks still **11** | `--collect-only -q` |
| Lint / format | clean | `ruff check src tests`, `ruff format --check src tests` (80 files) |
| Types | **Success: no issues found in 56 source files** | `mypy` (strict, `src/nexus`) |
| Repo hygiene | **80 passed** | `pytest tests/test_repo_hygiene.py` (run after `git add -A`) |
| CI | all jobs green on `bc4a718`, `41aca23`, `354b95c` and `f675582` — 5 `ci` jobs × 2 triggers + 1 venue job × 2 triggers per commit; the commit carrying this section is checked the same way before the owner is asked to review it | `gh api …/actions/runs?head_sha=…` |

Every run id and job id above is re-readable with the same three calls, because CI job logs and
artifacts are not retrievable from this environment but check-run annotations are:

```bash
for r in 45754638978 45756716181 45758610197 45759709313 45782533635 45782540670 \
         45784665370 45784657260 45786440060 45786447356 45787390006 45787399434; do
  gh api "repos/:owner/:repo/actions/runs/$r" --jq '.head_sha[0:7] + " " + .created_at + " " + .conclusion'
  j=$(gh api "repos/:owner/:repo/actions/runs/$r/jobs" --jq '.jobs[0].id')
  gh api "repos/:owner/:repo/check-runs/$j/annotations" --jq '.[].message' \
    | grep -E 'dukascopy\.(url|layout|ticks|probe)|geo-blocked'
done
```

### 2.7 What 7.2 did not close

| Finding | State after 7.2 | Why |
|---------|-----------------|-----|
| **F-2** bybit geo-block | **OPEN** — `5 geo-blocked` in the headline of all twelve runs; the 403-from-CloudFront characterisation on public unauthenticated endpoints is run `45724918466` (`docs/06:314`), not these twelve | L-D needs the D-021 deployment VM; the `runner` dispatch input already exists |
| **F-3** empty master | **OPEN** — `/v1/instruments/coverage` still returns `total=0 active=0` at boot | L-C deferred to 7.3 by the owner's answer. L-E removed the *definition* blocker; the *seed* is still missing |
| **F-5** intermittent feed | **OPEN, and better evidenced** — twelve runs, **five** probe patterns, production UA worked outright in seven | No cause established; a user-agent conclusion would still be adopted on noise |
| **F-6** 3 of 14 asset classes | **OPEN** — `DUKASCOPY` makes FX_SPOT recordable, not covered | The other ten must render `UNSUPPORTED` per D-019 |
| **F-8** cross-endpoint agreement | **OPEN, now quantified** (§2.5) | Needs a stated bps tolerance + a recorded timestamp gap; both are design choices, not measurements |
| **F-9** "both sides present" | **Documentation corrected** (`docs/06:234`, `:300` now say the run *happened* to contain both sides and that `_assert_ticks` accepts one) — **the owner ruling is still outstanding**: should a one-sided trade list ever fail? Runs 1–3 and 5–10 returned both sides; run 4 returned 50 buys and passed, correctly |
| **F-10** self-refuting verdict | **CLOSED** (§2.4) | Found, fixed and pinned in this batch |
| **F-11** the fix refuted "never reached" only on success | **CLOSED** (§2.4) | Found in run 12, the first run to exercise the F-10 branch live; an `http-503` reply is also proof the host was reached. Pinned by all 125 combinations of the probe cross-product |

### 2.8 Limitations of this batch

1. **EURUSD only.** Twelve of thirteen point divisors have never met a real file, and a wrong divisor
   is a silent 100× error. `LAYOUT_VERIFIED_PAIRS` exists so no report can imply otherwise.
2. **One hour.** All twelve runs fetched the same hour (`2026-11-24T12:00Z`, chosen by
   `_recent_weekday_hour()`), so twelve passes are twelve readings of *one file*, not twelve samples
   of the feed's shape. A weekend hour, a holiday, a month boundary and a JPY pair are all untested
   against real data.
3. **Half of the F-11 fix is offline-evidenced only.** Run 12 exposed F-11; runs 13 and 15 then
   exercised the corrected branch live on two different input shapes, publishing the corrected verdict
   verbatim both times (§2.4). But both took the *succeeded-variant* path. The
   `http-*`-beside-a-network-fault path that F-11 actually added has not recurred in any run, so its
   only evidence is the 125-combination cross-product test.
4. **No production caller.** `certify(..., auth=...)` and the new refusals are exercised by tests, not
   by any running code path: there is no write endpoint and the master is empty. Their first real
   caller arrives with L-C in 7.3.
5. **Nothing was reconciled against a second source.** Layout verification is not price verification.
6. **Bybit's five checks remain unrun anywhere.** Its adapter is still exercised against public
   documentation only; `SUPPORTED` is its honest rank and stays its recorded status.

### 2.9 Decision requested

Stage 7.2 delivered the three authorised levers. Three questions before 7.3:

1. **Is Stage 7.1 approved?** Its row in `docs/07` still reads `AWAITING REVIEW / PENDING` with no
   decision id: the owner authorised 7.2 *on the strength of* the 7.1 research but never ruled on
   7.1 as a deliverable. Recording **D-046** for it would close the gap; leaving it open is also a
   legitimate answer.
2. **Authorise Stage 7.3 = L-C, seed the master?** The batch that makes coverage non-zero: register
   only instruments whose evidence exists — okx `BTC-USDT-SWAP` (twelve runs), binance vision
   `BTCUSDT` 1m (twelve runs, 1,440 bars, 0 rejected), dukascopy `EURUSD` (twelve runs, layout
   verified) —
   each at the rank its evidence supports and no higher, each citing its run ids, with
   `AUTH_NOT_APPLICABLE` at `CONNECTED`. It decides what every screen shows, so it wants its own
   review. Cost $0, no new dependency, offline-testable. **Recommendation: yes, as 7.3.**
3. **The F-9 ruling.** Should a trade list containing only one side ever *fail* a live check? The
   documentation now says what the check does; only the owner can say what it should do.
   **Recommendation: no — record the side distribution as evidence and never fail on it**, because a
   one-sided window is normal in a quiet market, and `_assert_book` already fails a one-sided *book*,
   which is the case that actually indicates a broken feed.
