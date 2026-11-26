# 14 — Stage 7: Market & Venue Coverage

Status: **IN PROGRESS**, sub-deliverable 7.1 research (this document §1, board
`design/stage7-1-market-venue-coverage.html`). Started after the Stage 6 stage-level approval
(D-044, 2026-11-26). **7.1 changes no production code**: the authorisation the owner gave for
Stage 6.2 was scoped to that batch, so every finding that needs a code change is recorded here as a
request with its cost, not delivered. Stages 8–23 remain `NOT STARTED`.

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
from source; execute the domain types instead of reasoning about them. Three of the seven findings
below were only findable by running something.

### 1.1 Evidence base, and what could not be read

| Source | Identity | Readable here? |
|--------|----------|----------------|
| live venue run **at HEAD** | run `45756716181`, job `139696937355`, commit `b67ab39`, 2026-11-26T04:41Z, **success** | yes — check annotation |
| the run before it | run `45754638978`, job `139690278846`, commit `a77865e`, 04:21Z, success | yes — check annotation |
| job logs | `gh run view --log-failed`, `gh api …/jobs/<id>/logs` | **no** — EOF against `results-receiver.actions.githubusercontent.com`, not in this sandbox's allowed hosts |
| raw captures + report artifact | `live-verification` (`live-captures/`) | **no** — download dies against `productionresultssa14.blob.core.windows.net` |
| annotation completeness | GitHub caps annotation text and the workflow truncates its own report | **partial** — `…truncated: 807 escaped characters over the cap`; the 5 GEO-BLOCKED rows and 2 PASS rows are past the cut |
| in-process boot of the API | `create_app()` + `TestClient`, `NEXUS_AUDIT_BACKEND=memory` | yes — executed |
| probe of the domain types | `Venue`, `VenueMapping`, `InstrumentRegistry.register/certify`, `coverage_report` | yes — executed |

Both runs were on this branch and neither was dispatched by hand: `venue-verification.yml` also runs
on `pull_request` for changes under `backend/src/nexus/ingestion/**`, so pushing Stage 6's docs
re-triggered live contact with all four sources. That is the luckiest part of this batch — fresh
evidence at HEAD, for free.

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

### 1.3 The verified numbers, per source (run `45756716181`, 04:41Z)

* **OKX — 5/5.** `BTC-USDT-SWAP` contract size 0.01, tick size 0.1, min qty 0.01, qty step 0.01,
  status `live`; bid 61063.2 / ask 61063.3, spread 0.016 bps, uncrossed; 50 trades with both sides,
  61063.2–61064.8; 100 one-minute candles spanning 1.65 h; 40-level book, entitlement `LIVE`.
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

### 1.4 Findings

**F-1 — EVIDENCED, NOT RETIRED: dukascopy's layout check has passed against a real file twice, and
the code still says no real file has ever been downloaded.** `verify_layout`'s docstring states the
bargain — *"Passing these is the evidence required to flip `LAYOUT_VERIFIED` to `True`"*
(`dukascopy.py:219–225`) — and it passed at HEAD and in the run before it, with identical numbers.
Against that, one constant and four written statements are stale: `dukascopy.py:45`
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

**F-5 — DO NOT OVERCLAIM THE 503: two runs twenty minutes apart produced different dukascopy
diagnoses.** Run `45754638978` concluded `verdict="nothing to diagnose: the production User-Agent
works"` after `probe.production_ua outcome=ok bytes=25761 lzma=True`. Run `45756716181` (HEAD) got
`network-IngestFault` for **both** user agents on that hour, succeeded on a different hour
(`10h_ticks.bi5`, 25,313 bytes), and concluded `verdict="the host was never reached
(network-IngestFault), so no cause can be distinguished"`, `action="re-run from a host with egress"`.
The diagnostic behaved exactly as designed — it refused to invent a cause it had not measured, which
is one of the seven logic tests pinning that behaviour. But it means `docs/00`'s claim that the 503
was "characterised" is only partly supported: throttling is *consistent* with the evidence (16
transport calls to land one file; the patience helper exists because this feed answers
intermittently), while no cause has been *established*. What reproduced in both runs is the layout
pass — the evidence O-010 actually demands. The honest state is "intermittent, cause unknown".

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
4. **Two runs gave different dukascopy diagnoses** (F-5), so the 503 is not characterised and no
   cause is claimed.
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
