"""Stage 8.2 board: the schemas converge, the master projects, and evidence gets a writer.

L-A + L-B + L-C, authorised by D-050. L-D and L-E are deferred to 8.3 by the same ruling. This is the
first batch to change `backend/` since `9e70ed3`.

Every transcript in §3, §6, §7 and §9 was captured from `backend/.venv/bin/python` runs against the real
applied DDL while this board was being written, and pasted verbatim — including the two places where the
capture contradicted what this batch had already written down (§4 and §2). Where the batch corrected
itself, the correction is on the board rather than quietly applied: the published F-15 was partly wrong
(§2), the recommended `NUMERIC(6,5)` was executed and rejected (§3), and a claim about TEXT ordering was
falsified by the probe that was meant to illustrate it (§4).

Run:  backend/.venv/bin/python design/build_board82.py
"""

from __future__ import annotations

import html
import pathlib
import re

from build_board71 import CSS as CSS71
from build_specimen import fonts_css

HERE = pathlib.Path(__file__).resolve().parent
CSS = CSS71 + """
.ba { border: 1px solid var(--color-border-subtle); border-radius: var(--radius-card);
  overflow: hidden; margin-top: 12px; }
.ba .hd { font-family: var(--font-family-mono); font-size: var(--font-size-caption);
  letter-spacing: .08em; padding: 6px 12px; background: var(--color-surface-elevated);
  color: var(--color-text-muted); border-bottom: 1px solid var(--color-border-subtle); }
.ba pre { margin: 0; padding: 10px 12px; font-family: var(--font-family-mono);
  font-size: var(--font-size-data); line-height: 1.65; white-space: pre-wrap;
  color: var(--color-text-secondary); font-variant-numeric: tabular-nums; }
.ba.before .hd { color: var(--color-feedback-negative-text); }
.ba.after .hd { color: var(--color-feedback-positive-text); }
.no { color: var(--color-feedback-negative-text); }
.ok { color: var(--color-feedback-positive-text); }
/* `.card` wraps every table here and is undefined in the shared shell (CSS71) — the gap that left the
   7.1 and 7.2 boards with unbordered tables. Definition copied verbatim from `build_specimen.py`, the
   approved visual language, rather than invented. Added to THIS board's extension only. */
.card { background: var(--color-surface-panel); border: 1px solid var(--color-border-subtle);
        border-radius: var(--radius-card); padding: var(--space-panel); }
.card table { width: 100%; }
"""


def rows(items: list[tuple[str, ...]]) -> str:
    return "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in items)


def table(head: list[str], body: list[tuple[str, ...]]) -> str:
    return (
        "<table><thead><tr>"
        + "".join(f"<th>{h}</th>" for h in head)
        + "</tr></thead><tbody>"
        + rows(body)
        + "</tbody></table>"
    )


def verbatim(title: str, body: str, kind: str = "") -> str:
    """A captured transcript. `kind` is `before` or `after` when the block is one side of a comparison."""
    cls = f"ba {kind}".strip()
    return f'<div class="{cls}"><div class="hd">{title}</div><pre>{html.escape(body.strip())}</pre></div>'


# --------------------------------------------------------------------- §1 what was ruled
def ruled_table() -> str:
    return table(
        ["Question put on the 8.1 board", "Answer", "What it authorised"],
        [
            (
                "Is Stage 8.1 approved?",
                "<b>Recommend</b>",
                "<b>D-050</b>. Asked up front rather than assumed from a later <span class='mono'>Proceed</span>, "
                "because Stage 7.1 sat unratified for a day and needed D-047 to fix it.",
            ),
            (
                "What is 8.2?",
                "<b>Recommend</b>",
                "<b>L-A + L-B + L-C</b> — schema fidelity, master projection, first writer. <b>L-D and L-E "
                "deferred to 8.3.</b>",
            ),
            (
                "Does F-15 get fixed by a rebuild migration?",
                "<b>Recommend</b>",
                "Rebuild migration <b>plus a fidelity test</b> — the test is what makes the fix stay fixed.",
            ),
            (
                "F-14 before or alongside L-C?",
                "<b>Recommend</b>",
                "The <b>cheap half inside L-C</b>, with F-14 itself <b>left open</b> and re-asked on its own "
                "merits. Explicitly <i>not</i> a four-adapter receipt-time change inside a batch that is also "
                "rebuilding two tables.",
            ),
        ],
    )


def not_ruled_table() -> str:
    return table(
        ["Left open", "Why it matters"],
        [
            (
                "<b>§8's fourth question was never put.</b> Whether finding ids should be scoped per stage "
                "from Stage 8 onward.",
                "F-19 records that F-1…F-7 are already ambiguous between two approved documents. F-20 (§6) "
                "continues the global sequence, so it is the first id that would move under a prefix scheme — "
                "and the only one. Re-asked in §12.",
            ),
            (
                "<b>F-14 itself</b> (ledger <span class='mono'>O-012</span>).",
                "No adapter was touched. <span class='mono'>observed_at</span> is still venue time in all four "
                "and no receipt time exists anywhere in ingestion, so latency remains unmeasurable. §10 states "
                "exactly what did change.",
            ),
            (
                "<b>F-16's residue.</b> The four seeded mappings carry no economics.",
                "<span class='mono'>margin_rate</span> is NULL and <span class='mono'>fees</span> is "
                "<span class='mono'>{}</span> on all four, because Stage 7.3's seed specs never contained "
                "either word. §8.",
            ),
            (
                "<b>F-17, F-18, F-19</b> — unchanged by this batch.",
                "Nothing constructs a <span class='mono'>DecisionRecord</span>; the design still needs validity "
                "intervals, TTLs, contradiction links and a sufficiency basis; the id collision is recorded, "
                "not resolved.",
            ),
        ],
    )


# --------------------------------------------------------------------- §2 the correction
def drift_table() -> str:
    return table(
        ["Direction", "What was missing", "Consequence"],
        [
            (
                "absent from <b>SQLite</b>",
                "<span class='mono'>venue_instrument_mapping</span> — the <b>entire table</b>, declared in the "
                "target since <span class='cite'>0001_core.sql</span>",
                "The four venue mappings Stage 7.3 seeded had nowhere to be projected. <b>F-16 was unfixable "
                "without L-A.</b> The likeliest reason it was omitted: the target declares "
                "<span class='mono'>BIGINT GENERATED ALWAYS AS IDENTITY</span>, which has no SQLite equivalent.",
            ),
            (
                "absent from the <b>target</b>",
                "<span class='mono'>halt_event.cancel_working_orders</span>",
                "A field <span class='mono'>/v1/status</span> really serves would not exist after a promotion.",
            ),
            (
                "absent from the <b>target</b>",
                "<span class='mono'>halt_event.seq</span>; <span class='mono'>audit_ref</span> on "
                "<span class='mono'>approval</span>, <span class='mono'>decision</span>, "
                "<span class='mono'>fills</span>, <span class='mono'>orders</span>, "
                "<span class='mono'>trade_intent</span>, <span class='mono'>halt_event</span>, "
                "<span class='mono'>venue_instrument_mapping</span>; "
                "<span class='mono'>instrument.payload</span>; "
                "<span class='mono'>trade_intent.payload</span>",
                "<b>11 columns across 8 tables</b>, every one written by "
                "<span class='cite'>store/operational.py</span> today. A promotion following the "
                "<span class='cite'>.sql</span> files would have lost them silently.",
            ),
            (
                "absent from the <b>target</b>",
                "<span class='mono'>schema_migrations</span>, and now "
                "<span class='mono'>schema_migration_skips</span>",
                "A PostgreSQL deploy could not record which migrations it had applied, so it could not refuse a "
                "changed checksum — forward-only would have been unenforceable there.",
            ),
        ],
    )


def convention_table() -> str:
    return table(
        ["§3 called this drift", "What the full diff showed"],
        [
            (
                "Four lost <span class='mono'>DEFAULT now()</span> clauses",
                "<b>A house convention.</b> Every timestamp column in the applied schema is "
                "<span class='mono'>TEXT NOT NULL</span> with no default, because the writers stamp them with "
                "<span class='mono'>iso_utc(utc_now())</span>. Nothing in <span class='cite'>src/</span> relies "
                "on a database default.",
            ),
            (
                "<span class='mono'>confidence TEXT</span> against "
                "<span class='mono'>NUMERIC(6,5)</span>",
                "<b>A house convention.</b> <b>26 numeric columns across 8 tables</b> are TEXT in the applied "
                "schema, because SQLite's NUMERIC affinity stores a REAL — a float — and Decimals must travel "
                "as strings. §3 said 19 across 8 tables: <b>the 19 reproduces exactly</b> (it is the count "
                "before 0004 created <span class='mono'>venue_instrument_mapping</span>, whose seven "
                "<span class='mono'>NUMERIC(28,12)</span> columns join them, 19 + 7 = 26), and <b>the table "
                "count was wrong</b> — those 19 sat across 7 tables, not 8.",
            ),
            (
                "<span class='mono'>audit_log</span> and "
                "<span class='mono'>schema_migrations</span> &ldquo;only on one side&rdquo;",
                "<b>Not divergences at all.</b> <span class='mono'>audit_log</span> is created by "
                "<span class='mono'>SqliteAuditStore</span> in <span class='cite'>audit/log.py</span>, because "
                "migration 0003 <i>requires</i> it to exist already; "
                "<span class='mono'>schema_migrations</span> comes from "
                "<span class='mono'>SCHEMA_MIGRATIONS_DDL</span>, which the runner executes before applying "
                "anything.",
            ),
        ],
    )


# --------------------------------------------------------------------- §3 the probes
PROBE_FK = """
PRAGMA foreign_keys              = 1
PRAGMA foreign_key_list(dossier) = [('instrument', 'instrument_id', 'instrument_id')]
dossier with a dangling instrument_id -> REFUSED: FOREIGN KEY constraint failed
dossier with a real instrument_id     -> ACCEPTED
indexes on dossier                    = ['ix_dossier_created', 'sqlite_autoindex_dossier_1']
indexes on memory_item                = ['ix_memory_created', 'ix_memory_kind', 'sqlite_autoindex_memory_item_1']
"""

PROBE_CHECK = """
memory_item.confidence, TEXT affinity plus a CHECK:
   confidence = '0.5'            -> accepted
   confidence = '0.12345'        -> accepted
   confidence = '1'              -> accepted
   confidence = '0'              -> accepted
   confidence = '0.00000'        -> accepted
   confidence = None             -> accepted
   confidence = 'not-a-number'   -> REFUSED (CHECK constraint failed: confidence IS NULL OR CAST(confidence AS REAL) <> 0.0
                              OR confidence IN ('0', '0.0', '0.00', '0.000', '0.0000', '0.00000'))
   confidence = ''               -> REFUSED (CHECK constraint failed: ...)
   confidence = 'abc123'         -> REFUSED (CHECK constraint failed: ...)
   confidence = '0.5abc'         -> accepted
   confidence = '1e-9'           -> accepted
"""

PROBE_RANGE = """
range probes — is a probability bounded?
   '12'         -> accepted
   '9'           -> accepted
   '1'           -> accepted
   '-0.5'        -> accepted
   '99999999'    -> accepted
   '1e-9'        -> accepted
   '0.5abc'      -> accepted
"""

PROBE_TYPE = """
   typeof(confidence) in the applied schema = text
   the rejected alternative: CREATE TABLE t (c NUMERIC(6,5)), INSERT '0.5' -> typeof = real
"""

PROBE_MAPPING = """
venue_instrument_mapping:
   first mapping_id                     = 1
   duplicate (instrument, venue, symbol) -> REFUSED: UNIQUE constraint failed:
       venue_instrument_mapping.instrument_id, venue_instrument_mapping.venue,
       venue_instrument_mapping.venue_symbol
   mapping to an unknown instrument      -> REFUSED: FOREIGN KEY constraint failed

migrations:
   0001_operational           statements= 19 requires=None       checksum=fcfd79161c83
   0002_memory                statements=  8 requires=None       checksum=5e7fafd0673e
   0003_audit_append_only     statements=  4 requires=audit_log  checksum=1e9ec5a5d915
   0004_memory_fidelity       statements= 15 requires=dossier    checksum=4c7368d407bb
"""


def migration_table() -> str:
    return table(
        ["0004 does", "Why it cannot be an <span class='mono'>ALTER</span>"],
        [
            (
                "Rebuilds <span class='mono'>dossier</span> through "
                "<span class='mono'>dossier_0004</span> so "
                "<span class='mono'>instrument_id</span> gains "
                "<span class='mono'>REFERENCES instrument (instrument_id)</span>; copies all 12 columns; "
                "drops; renames; recreates <span class='mono'>ix_dossier_created</span>",
                "SQLite refuses <span class='mono'>ADD CONSTRAINT … FOREIGN KEY</span> outright — "
                "<span class='mono'>near \"CONSTRAINT\": syntax error</span> (§5.3 of "
                "<span class='cite'>docs/15</span>, executed).",
            ),
            (
                "Rebuilds <span class='mono'>memory_item</span> the same way to add the confidence "
                "<span class='mono'>CHECK</span>; recreates <span class='mono'>ix_memory_kind</span> and "
                "<span class='mono'>ix_memory_created</span>",
                "A CHECK cannot be added to an existing table either, and "
                "<span class='mono'>ALTER COLUMN … TYPE</span> is refused — which is why the type was left "
                "alone rather than &ldquo;fixed&rdquo;.",
            ),
            (
                "Creates <span class='mono'>venue_instrument_mapping</span>: "
                "<span class='mono'>INTEGER PRIMARY KEY AUTOINCREMENT</span>, seven "
                "<span class='mono'>NUMERIC(28,12)</span> columns as TEXT, "
                "<span class='mono'>fees</span> as <span class='mono'>TEXT DEFAULT '{}'</span>, plus "
                "<span class='mono'>audit_ref</span>, the "
                "<span class='mono'>UNIQUE (instrument_id, venue, venue_symbol)</span> and "
                "<span class='mono'>ix_mapping_venue</span>",
                "Nothing to alter — the table did not exist. This is the table whose absence made F-16 "
                "unfixable.",
            ),
        ],
    )


# --------------------------------------------------------------------- §4 the ordering correction
def ordering_table() -> str:
    return table(
        ["Values inserted", "<span class='mono'>ORDER BY confidence</span>",
         "<span class='mono'>ORDER BY CAST(confidence AS REAL)</span>", "Differ?"],
        [
            ("<span class='mono'>0.5, 0.05, 0.9, 0.12345</span>",
             "<span class='mono'>0.05, 0.12345, 0.5, 0.9</span>",
             "<span class='mono'>0.05, 0.12345, 0.5, 0.9</span>", "<b class='no'>no</b>"),
            ("<span class='mono'>0.5, 0.50, 0.45</span> (the prefix tie)",
             "<span class='mono'>0.45, 0.5, 0.50</span>",
             "<span class='mono'>0.45, 0.5, 0.50</span>", "<b class='no'>no</b>"),
            ("<span class='mono'>9, 12, 1</span>",
             "<span class='mono'>1, <b>12, 9</b></span>",
             "<span class='mono'>1, <b>9, 12</b></span>", "<b class='ok'>yes</b>"),
        ],
    )


# --------------------------------------------------------------------- §5 the fidelity test
def fidelity_table() -> str:
    return table(
        ["Compared", "Result"],
        [
            ("Tables each side", "<b>17 and 17</b>; <b>16 compared</b> — "
             "<span class='mono'>audit_log</span> is exempt and checked separately against "
             "<span class='mono'>SqliteAuditStore</span>'s own claim that its schema "
             "&ldquo;mirrors the PostgreSQL migration&rdquo;"),
            ("Columns, per table", "<b>0 divergences</b>"),
            ("Nullability, per column", "<b>0 divergences</b>"),
            ("Foreign keys, per column", "<b>0 divergences</b> — including "
             "<span class='mono'>dossier.instrument_id</span>, which is the column 0004 rebuilt for"),
            ("Declared types, after the written-down translations", "<b>0 divergences</b>"),
            ("Types the target declares that the map has no rule for", "<b>none</b> — and a test fails if the "
             "target starts using one, so a new type is a decision rather than a difference absorbed silently"),
        ],
    )


def false_positive_table() -> str:
    return table(
        ["The audit cried wolf", "Why", "What replaced it"],
        [
            (
                "A column named <span class='mono'>checksum</span> reported as missing from SQLite",
                "The constraint filter tested <span class='mono'>line.startswith(\"CHECK\")</span>, which also "
                "swallows a <i>column</i> whose name begins with those letters. The schema was right; the "
                "parser was wrong.",
                "Table-level constraints are matched as grammar — the keyword must be followed by a space or a "
                "paren, as SQL requires.",
            ),
            (
                "<span class='mono'>dossier_0004</span> and "
                "<span class='mono'>memory_item_0004</span> reported as drift",
                "Static parsing of <span class='cite'>schema.py</span> also picks up 0004's staging tables and "
                "the superseded pre-rebuild <span class='mono'>dossier</span> definition.",
                "The test compares the <b>live post-migration</b> schema — it builds the database the way the "
                "app does, then reads it back through "
                "<span class='mono'>PRAGMA table_info</span> and "
                "<span class='mono'>foreign_key_list</span>.",
            ),
            (
                "<span class='mono'>assert payload[\"observed_at\"] not in payload</span> raised "
                "<span class='mono'>KeyError</span>",
                "Subscripting the very key whose absence was being asserted. The test failed exactly when the "
                "property held.",
                "<span class='mono'>assert \"observed_at\" not in payload</span>, with the reason written out: "
                "duplicating the column inside the payload would give a reader two copies that could disagree.",
            ),
        ],
    )


# --------------------------------------------------------------------- §6 F-20
F20_FAIL = """
MigrationError: MIGRATION_INVALID: migration 0003_audit_append_only is pending while later
migrations are already applied; the sequence has a hole and this runner only moves forward
"""

F20_FIXED = """
ephemeral boot -> applied: ['0001_operational', '0002_memory', '0004_memory_fidelity']
                 skipped: ['0003_audit_append_only']
                 schema_migration_skips: [('0003_audit_append_only',)]
                 venue_instrument_mapping exists: True
durable boot   -> applied: ['0003_audit_append_only'] skipped: []
                 recorded: ['0001_operational', '0002_memory', '0003_audit_append_only', '0004_memory_fidelity']
                 skips cleared: 0
"""

F20_TEETH = """
DELETE FROM schema_migrations WHERE version='0002_memory'  -- a bypass, not a deferral
MigrationError: MIGRATION_INVALID: migration 0002_memory is pending while later migrations
are already applied; the sequence has a hole and this runner only moves forward
"""


def f20_table() -> str:
    return table(
        ["Boot sequence", "Before the fix", "After"],
        [
            (
                "Ephemeral audit backend — there is no <span class='mono'>audit_log</span> to protect, so "
                "0003 is legitimately skipped",
                "0001, 0002, <b>0004</b> applied; 0003 skipped and <b>nothing recorded about the skip</b>",
                "The same, plus a row in <span class='mono'>schema_migration_skips</span>",
            ),
            (
                "Then a durable boot over the <b>same file</b>",
                "<b class='no'>fatal</b> — an applicable migration now sits below an applied one, so the "
                "runner refuses to start",
                "<b class='ok'>0003 applies</b>, all four recorded, the deferral cleared in the same "
                "transaction",
            ),
            (
                "A bookkeeping row deleted by hand",
                "refused as a hole",
                "<b>still refused</b> — the refinement did not cost the guard its teeth",
            ),
        ],
    )


# --------------------------------------------------------------------- §7 L-B
LB_BEFORE_AFTER = """
seed_master            -> registered: ('INS-BTC-USDT-USDT', 'INS-BTC-USDT', 'INS-EUR-USD') rungs_climbed: 10
BEFORE project_master  -> counts.instrument = 0 | counts.venue_instrument_mapping = 0
project_master         -> ('INS-BTC-USDT', 'INS-BTC-USDT-USDT', 'INS-EUR-USD') mappings: 4
AFTER                  -> counts.instrument = 3 | counts.venue_instrument_mapping = 4
project_master again   -> projected: () | unchanged: ('INS-BTC-USDT', 'INS-BTC-USDT-USDT', 'INS-EUR-USD')
                          chain grew by: 0
"""

LB_ROWS = """
the four mappings, read back from the system of record:
   INS-BTC-USDT       BINANCE    BTCUSDT        DATA_AVAILABLE  tick=None     contract=None  margin=None fees={}
   INS-BTC-USDT-USDT  BYBIT      BTCUSDT        SUPPORTED       tick=None     contract=None  margin=None fees={}
   INS-BTC-USDT-USDT  OKX        BTC-USDT-SWAP  DATA_AVAILABLE  tick=0.1      contract=0.01  margin=None fees={}
   INS-EUR-USD        DUKASCOPY  EURUSD         DATA_AVAILABLE  tick=0.00001  contract=None  margin=None fees={}

bybit's note survives the projection:
   GEO-BLOCKED and unverified: bybit v5 answers 403 from GitHub-hosted runners on public
   unauthenticated endpoints (run 45724918466; F-2), and reports `5 geo-blocked` in every venue
   run read. The adapter is exercised against public documentation only. Climbing this mapping
   needs the D-021 deployment VM as a self-hosted runner (lever L-D) ...
"""


def lb_decision_table() -> str:
    return table(
        ["Decision", "What it prevents"],
        [
            (
                "<b>The payload is built from the domain objects, not from "
                "<span class='mono'>registry._mapping_to_dict</span></b>",
                "That serialiser is an API read-model and omits "
                "<span class='mono'>margin_rate</span> and <span class='mono'>fees</span> — the two fields "
                "that make a mapping an economic description rather than a symbol translation. Projecting "
                "through it would have written all four mappings with both columns empty and <b>nothing would "
                "have failed</b>, because both are nullable. A test now fails if a field is added to "
                "<span class='mono'>VenueMapping</span> and not to the projection.",
            ),
            (
                "<b>The payload carries no timestamp of its own</b>",
                "A projection stamped at call time has a different digest on every boot, so every boot would "
                "append three audit records for instruments that had not changed — a chain that grows without "
                "describing anything. Digests are compared instead, and only a real change is re-audited. "
                "Verified across process restarts on one durable file: "
                "<span class='mono'>instrument.registered</span> stays at exactly <b>3 over three boots</b>, "
                "while <span class='mono'>api.app_created</span> and "
                "<span class='mono'>boot.recovery</span> legitimately grow by one each.",
            ),
            (
                "<b>A projection that writes several rows marks itself complete once, after all of them</b>",
                "<span class='mono'>op_projection</span> is keyed on "
                "<span class='mono'>audit_ref</span> alone. Handing the ref to each save would book the event "
                "as done the moment the instrument row landed; a crash before the mappings were written would "
                "then leave a hole that boot recovery believes is filled — the exact failure L-2 exists to "
                "prevent. A test simulates that crash and asserts the interrupted mapping is restored from the "
                "chain alone.",
            ),
            (
                "<b>Boot projects only a master the app seeded itself</b>",
                "The same rule that governs seeding: an injected registry is a test fixture and stays one, "
                "which is why <span class='cite'>test_api_phase3.py</span> asserts "
                "<span class='mono'>projected: 0</span>. A boot that cannot write the master into the system "
                "of record does not serve.",
            ),
        ],
    )


# --------------------------------------------------------------------- §9 L-C
LC_TIMESTAMPS = """
a venue timestamp exists     -> observed_at=2026-11-26T12:00:00.000Z retrieved_at=2026-11-26T12:00:01.170Z
                                source=VENUE apparent_latency_seconds=1.17 status=LIVE
                                checksum=a2b2921dacb6a6b508a628d4... dossier_id=None
the venue clock is ahead     -> apparent_latency_seconds=-2.0 (recorded, not refused)
no venue timestamp, declared -> observed_at_source=LOCAL_FALLBACK apparent_latency_seconds=0.0
"""

LC_REFUSALS = """
refusals:
   snapshot with no observed_at, no fallback declared   -> ValueError: the snapshot carries no observed_at, so the venue published no timestamp f...
   LOCAL_FALLBACK claimed with two different timestamps -> ValueError: observed_at_source=LOCAL_FALLBACK means the observation time is our own cl...
   naive observed_at                                    -> ValueError: observed_at must be an aware UTC datetime; got a naive '2026-11-26T12:00:0...
   naive retrieved_at                                   -> ValueError: retrieved_at must be an aware UTC datetime; got a naive '2026-11-26T12:00:...
   data_status='FRESH'                                  -> ValueError: data_status must be one of ['LIVE', 'DELAYED', 'STALE', 'UNAVAILABLE', 'FA...
   source=''                                            -> ValueError: evidence needs a source: an observation from nowhere cannot be audited
   caller overwrites the provenance fields              -> stored: apparent_latency_seconds=1.17 observed_at_source=VENUE
   store given an empty observed_at                     -> PersistenceError: PERSISTENCE_FAILED: evidence needs both observed_at (the ven...

chain: {'migration.applied': 4, 'evidence.recorded': 4} | intact: True
counts.evidence_ref = 4 | counts.dossier = 0
"""


def lc_decision_table() -> str:
    return table(
        ["Choice", "Reason"],
        [
            (
                "<span class='mono'>retrieved_at</span> is a <b>required keyword-only argument with no "
                "default</b>",
                "A default of <span class='mono'>observed_at</span> would manufacture a latency of exactly "
                "zero; a default of &ldquo;now&rdquo; would record <i>write</i> time as <i>receipt</i> time. "
                "Both would look like measurements, which is worse than a gap. Pinned by inspecting the "
                "signature.",
            ),
            (
                "<span class='mono'>observed_at_source</span> records whether the observation time really came "
                "from the venue",
                "A snapshot with no <span class='mono'>observed_at</span> is refused unless the caller declares "
                "<span class='mono'>LOCAL_FALLBACK</span>; and declaring the fallback while passing two "
                "<i>different</i> timestamps is refused too, because a flag that can be contradicted by the row "
                "it qualifies is decoration.",
            ),
            (
                "<span class='mono'>apparent_latency_seconds</span> is stored beside them and is <b>not</b> a "
                "latency measurement",
                "It is <span class='mono'>retrieved_at - observed_at</span>, which contains the offset between "
                "the venue's clock and ours as well as any network delay. A negative value is recorded rather "
                "than refused: run 27 measured 1.089 s of venue time against 0.298 s of wall clock, so venue "
                "clocks run both ways, and a negative interval is evidence about the clock rather than an "
                "error condition.",
            ),
            (
                "The provenance fields are written <b>last</b>",
                "A caller's payload cannot overwrite them. The transcript shows "
                "<span class='mono'>apparent_latency_seconds: 999.0</span> and "
                "<span class='mono'>observed_at_source: \"SOMEBODY_ELSE\"</span> passed in, and the stored row "
                "carrying <span class='mono'>1.17</span> and <span class='mono'>VENUE</span>.",
            ),
            (
                "<span class='mono'>data_status</span> defaults to "
                "<span class='mono'>UNAVAILABLE</span> and is validated against "
                "<span class='mono'>DataStatus</span>",
                "The schema default and the fail-closed value: a writer that assumed "
                "<span class='mono'>LIVE</span> would assert a freshness it has not checked. <b>No vocabulary "
                "was extended</b> — the refusals raise <span class='mono'>ValueError</span>, following "
                "<span class='mono'>core.time.iso_utc</span>, because a "
                "<span class='mono'>RejectReason</span> is consumed by the audit log and the UI both.",
            ),
            (
                "<span class='mono'>kind</span> is passed through as free text",
                "<b>No vocabulary for it is declared anywhere in the repository</b> — the schema says only "
                "<span class='mono'>DEFAULT 'DATA'</span>. Inventing an enum here would put a "
                "plausible-looking controlled list in front of a distinction nobody has yet drawn.",
            ),
            (
                "<span class='mono'>dossier_id</span> is nullable and the writer needs no dossier",
                "The first writer must not depend on the one 8.3 has not built. The transcript shows "
                "<span class='mono'>counts.dossier = 0</span> beside four evidence rows.",
            ),
        ],
    )


# --------------------------------------------------------------------- §11 the gate
def gate_table() -> str:
    return table(
        ["Check", "Command", "At 8.1", "At 8.2"],
        [
            ("<span class='mono'>ruff format</span>",
             "<span class='mono'>ruff format --check src tests</span>", "82 files",
             "<b>88 files already formatted</b>"),
            ("<span class='mono'>ruff check</span>", "<span class='mono'>ruff check src tests</span>",
             "clean", "<b>clean</b>"),
            ("<span class='mono'>mypy</span> strict",
             "<span class='mono'>mypy</span> (<span class='mono'>files = [\"src/nexus\"]</span>)",
             "57 files", "<b>60 files, no issues</b>"),
            ("the suite", "<span class='mono'>pytest</span>", "1036 passed, 2 skipped",
             "<b>1117 passed, 2 skipped, 0 failed</b>"),
            ("repository hygiene", "<span class='mono'>pytest tests/test_repo_hygiene.py</span>",
             "83 passed", "<b>83 passed</b>"),
            ("live checks", "<span class='mono'>pytest tests/test_live_endpoints.py --collect-only</span>",
             "49", "<b>49</b> — unchanged, nothing here touches ingestion"),
            ("offline subset of the live module",
             "<span class='mono'>-k \"DiagnosisLogic or PatienceBehaviour or TradeSideRuling or "
             "CrossEndpoint\"</span>", "32", "<b>32 passed, 17 deselected</b>"),
        ],
    )


def delta_table() -> str:
    return table(
        ["New tests", "Count", "What they pin"],
        [
            ("<span class='cite'>tests/test_schema_fidelity.py</span>", "<b>35</b>",
             "The two schemas agree; 0004's checksums and its rebuild; the confidence CHECK, its leak and its "
             "unbounded range; the dossier FK enforced and not enforced"),
            ("<span class='cite'>tests/test_evidence_writer.py</span>", "<b>27</b>",
             "Both timestamps; every refusal; audit-first and recovery; the checksum; reads and filters"),
            ("<span class='cite'>tests/test_master_projection.py</span>", "<b>16</b>",
             "The master lands; idempotence at call level and across restarts; payload faithfulness; the "
             "crash-between-writes hole"),
            ("<span class='cite'>tests/test_migrations.py</span>", "12 → <b>15</b>",
             "A deferral is recorded; a deferral behind an applied migration is not a hole; a genuine hole is "
             "still refused"),
            ("<b>total</b>", "<b>+81</b>", "1036 → <b>1117</b> passed"),
        ],
    )


def batch_table() -> str:
    return table(
        ["", "Number"],
        [
            ("Files changed, insertions, deletions (<span class='mono'>git diff --stat</span>, "
             "<span class='cite'>backend/</span>)", "<b>17 files, 2,236 insertions(+), 23 deletions(-)</b>"),
            ("Source LOC / test LOC", "<b>14,162</b> / <b>14,760</b>"),
            ("Packages under <span class='cite'>src/nexus/</span>",
             "14 → <b>15</b> (<span class='mono'>nexus/intelligence/</span> is new; verified by "
             "<span class='mono'>git ls-files 'backend/src/nexus/*/__init__.py'</span>)"),
            ("Migrations applied", "3 → <b>4</b>; <span class='mono'>0004_memory_fidelity</span> is "
             "<b>15 statements</b>, <span class='mono'>requires=\"dossier\"</span>, checksum "
             "<span class='mono'>4c7368d407bb…</span>"),
            ("Columns added to the Postgres target", "<b>11 across 8 tables</b>, plus 2 bookkeeping tables"),
            ("Numeric columns stored as TEXT in the applied schema", "<b>26 across 8 tables</b> (19 before "
             "0004, +7 with <span class='mono'>venue_instrument_mapping</span>)"),
            ("Schema divergences remaining after the batch", "<b>0</b> across 16 compared tables"),
        ],
    )


def limits_table() -> str:
    return table(
        ["Limitation", "What it means for whoever comes next"],
        [
            (
                "<b>1. The CHECK on <span class='mono'>confidence</span> bounds nothing but &ldquo;is it a "
                "number&rdquo;.</b>",
                "It accepts <span class='mono'>'0.5abc'</span> (which casts to 0.5) and "
                "<span class='mono'>'1e-9'</span>, but also <span class='mono'>'12'</span>, "
                "<span class='mono'>'-0.5'</span> and <span class='mono'>'99999999'</span>. It is a floor, not "
                "a validation, and the range is unguarded — which is the only reason TEXT ordering can diverge "
                "from numeric ordering at all (§4). Whoever writes "
                "<span class='mono'>memory_item.confidence</span> in stage 10 must validate the value itself.",
            ),
            (
                "<b>2. Foreign keys are declared and still not enforced.</b>",
                "<span class='mono'>PRAGMA foreign_keys</span> stays off, for the reason "
                "<span class='cite'>docs/13</span> §2.5 gives: boot recovery re-projects in chain order, which "
                "is not always parent-first, and a hard FK failure mid-recovery would be worse than the "
                "inconsistency it prevents. 0004 moved "
                "<span class='mono'>dossier.instrument_id</span> <i>inside</i> that limitation; it did not lift "
                "it. A test pins that a dangling dossier is still accepted at runtime, so nobody reads the new "
                "FK as protection that does not exist.",
            ),
            (
                "<b>3. The target has never been executed by anything.</b>",
                "There is no PostgreSQL server or driver in this sandbox. The fidelity test compares declared "
                "types; every statement about the target is a property of the file, not a measurement of a "
                "database.",
            ),
            (
                "<b>4. The four seeded mappings carry no economics.</b>",
                "<span class='mono'>margin_rate</span> NULL and <span class='mono'>fees</span> "
                "<span class='mono'>{}</span> on all four; "
                "<span class='mono'>contract_size</span> on one of four. The projection is faithful — neither "
                "word appears in <span class='cite'>instruments/seed.py</span>. Filling them in would mean "
                "inventing a margin rate and a fee schedule with nothing behind them.",
            ),
            (
                "<b>5. Nothing calls <span class='mono'>record_evidence</span> yet.</b>",
                "L-C delivered the writer and its contract; wiring it into the four adapters is F-14's "
                "expensive half and is unauthorised. Until something calls it, "
                "<span class='mono'>evidence_ref</span> stays empty in production exactly as "
                "<span class='mono'>dossier</span> and <span class='mono'>memory_item</span> do.",
            ),
            (
                "<b>6. <span class='mono'>/v1/status</span> gained one key.</b>",
                "<span class='mono'>instrument_master.projected</span>. Two tests asserted that block by exact "
                "equality and were updated; an external consumer doing the same would see the change.",
            ),
            (
                "<b>7. The rebuild was proven against rows, but both tables are empty today.</b>",
                "<span class='mono'>test_the_rebuild_preserves_existing_rows</span> writes into the "
                "<b>pre-0004</b> schema first and then rebuilds over it, because a migration that is only safe "
                "on an empty table will be run against a non-empty one someday. That both tables happen to be "
                "empty now is luck, not a property.",
            ),
        ],
    )


def lever_table() -> str:
    return table(
        ["Lever", "Status after 8.2"],
        [
            ("<b>L-A</b> — schema fidelity plus a DDL-parsing fidelity test", "<b class='ok'>DONE</b> — 0004, "
             "both <span class='cite'>.sql</span> files corrected, 35 tests"),
            ("<b>L-B</b> — the seeded master projects", "<b class='ok'>DONE</b> — emitter, store writer, boot "
             "wiring, <span class='mono'>projected: 3</span> on <span class='mono'>/v1/status</span>"),
            ("<b>L-C</b> — first writer, <span class='mono'>evidence_ref</span> only, the two timestamps "
             "separate", "<b class='ok'>DONE</b> — <span class='cite'>nexus/intelligence/evidence.py</span>, "
             "27 tests"),
            ("<b>L-D</b> — read-only <span class='mono'>/v1/intelligence/dossiers</span>",
             "<b>DEFERRED to 8.3</b> by D-050"),
            ("<b>L-E</b> — the dossier writer at <span class='mono'>stance=ABSTAIN</span>",
             "<b>DEFERRED to 8.3</b> by D-050"),
            ("<b>F-20</b> — the migration runner could not tell a deferral from a bypass",
             "<b class='ok'>FOUND AND FIXED in this batch</b>, by the existing suite"),
        ],
    )


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())

    html_out = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI &middot; Stage 8.2 Intelligence Memory &mdash; First Writers</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 8 of 23 &middot; sub-deliverable 8.2 &middot; authorised by
D-050 &middot; L-A + L-B + L-C</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
The two schemas now agree, the seeded master reaches the system of record, and evidence has a writer</h1>
<div class="ribbon">This is the first batch to change <span class="mono">backend/</span> since
<span class="mono">9e70ed3</span>: <b>17 files, 2,236 insertions</b>, gate <b>1,117 passed / 2 skipped / 0
failed</b> (+81 tests), mypy strict clean on <b>60</b> files, ruff clean on <b>88</b>. It closes <b>F-15</b>
and <b>F-16</b>, found and fixed <b>F-20</b> on the way, and leaves <b>F-14 open</b> by ruling. Two things
this batch wrote down turned out to be wrong and are corrected here rather than quietly fixed: the approved
finding <b>F-15 was partly wrong</b> (&sect;2), and a claim about TEXT ordering was <b>falsified by the probe
that was meant to illustrate it</b> (&sect;4). The remedy D-050 approved was also <b>executed and rejected</b>
in one particular &mdash; <span class="mono">confidence NUMERIC(6,5)</span> (&sect;3).</div>

<h3>1 &middot; What was ruled, and what was not<span class="tag">D-050 &middot; docs/15 §9.0</span></h3>
<p>Four questions were put on the 8.1 board and all four were answered <b>Recommend</b>, each against
exactly one marked recommendation, so the reading is unambiguous.</p>
<div class="card">{ruled_table()}</div>
<p class="cap">Three of the four are discharged by this board. The fourth is discharged only in its cheap
half, which is what was authorised.</p>
<div class="card">{not_ruled_table()}</div>
<div class="blocked"><b>One question was never put.</b> §8 of <span class="cite">docs/15</span> asked four
things; the board asked four things; they were not the same four. The finding-id scoping question was
displaced by the question about 8.2's scope, so it is still unanswered and is re-asked in §12 rather than
being treated as settled by silence.</div>

<h3>2 &middot; Correction: the approved F-15 was partly wrong<span class="tag">docs/15 §9.1</span></h3>
<p>§3 of <span class="cite">docs/15</span> was written from <b>one hand-picked pair of tables</b> —
<span class="mono">dossier</span> in both DDLs — and reported six divergences. Fixing the finding required
parsing both DDLs and diffing <b>every table and every column</b>, and the systematic diff disagreed with
the published finding in three ways. The published text is annotated, not rewritten: it is what D-050 was
ruled on.</p>
<div class="card">{convention_table()}</div>
<p class="cap">Two of the six &ldquo;divergences&rdquo; are conventions with reasons, and two apparent ones
are not divergences at all. Presenting a convention as drift implies a defect where there is a decision
somebody already made.</p>
<p><b>And the real drift is larger than §3 said, and runs in both directions.</b> §3 described SQLite losing
columns the target had. It never looked the other way.</p>
<div class="card">{drift_table()}</div>
<div class="blocked"><b>What survives is the load-bearing part.</b>
<span class="mono">dossier.instrument_id</span> carried <b>no <span class="mono">REFERENCES</span> at
all</b>, so <span class="cite">docs/13</span> §2.5's &ldquo;foreign keys declared but not enforced&rdquo;
could not reach it — it was never declared. That is what 0004 fixed. <b>The lesson costs a batch to
learn and is worth writing down:</b> a divergence finding from one hand-picked table pair is a guess about
the whole schema. §3 diffed two tables and reported six divergences; the full diff found eleven columns and
three tables of drift in the direction §3 never looked, and reclassified two of its six as conventions.</div>

<h3>3 &middot; L-A: migration 0004, and the remedy that was executed and rejected<span class="tag">docs/15 §9.2</span></h3>
<p>D-050 approved &ldquo;<span class="mono">confidence NUMERIC(6,5)</span> plus a
<span class="mono">CHECK</span>&rdquo;. Writing it that way and then <b>executing</b> it showed the type
change is wrong, so 0004 keeps TEXT and adds only the CHECK. <b>This is a deviation from the approved
option and is disclosed as one.</b></p>
{verbatim("NUMERIC affinity, probed — the reason the type was left alone", PROBE_TYPE, "before")}
<p class="cap">Declaring <span class="mono">NUMERIC(6,5)</span> in SQLite would have made this the only
float-backed numeric column in the applied schema, breaking the rule that Decimals travel as strings — and
it would not have fixed acceptance anyway, because NUMERIC affinity happily stores
<span class="mono">'not-a-number'</span> as text when it cannot coerce.</p>
{verbatim("the CHECK that replaced it, probed value by value", PROBE_CHECK)}
<div class="card">{migration_table()}</div>
{verbatim("foreign key, indexes, mapping identity — probed on a fresh database after all four migrations",
          PROBE_FK + PROBE_MAPPING, "after")}
<p class="cap">The three earlier checksums are <b>unchanged</b>, and all four are now pinned literally in a
test — because <span class="cite">store/migrations.py</span> refuses a moved checksum only for a database
that <i>already applied it</i>. A fresh checkout, a CI runner and a new host apply whatever the file says, so
a literal list is the only thing that makes &ldquo;forward-only&rdquo; checkable offline.</p>

<h3>4 &middot; The second self-correction: a probe falsified the claim it was captured for<span class="tag">docs/15 §9.2</span></h3>
<p>This batch first wrote that a bare <span class="mono">ORDER BY confidence</span> remains lexicographic and
therefore wrong, and that <span class="mono">CAST</span> is what fixes it. Capturing the transcript for this
board said otherwise.</p>
<div class="card">{ordering_table()}</div>
{verbatim("the range probe that explains why — captured while building this board", PROBE_RANGE, "before")}
<p class="cap">For values in <span class="mono">[0,1)</span> — the only range a probability may occupy — TEXT
ordering and numeric ordering <b>coincide</b>, because every value shares the
<span class="mono">'0.'</span> prefix and digit-by-digit comparison then agrees with magnitude. They diverge
only at ten and above, and <b>ten and above is reachable only because the CHECK does not bound the
range</b>: it asks whether a value casts to a nonzero number, not whether it is a probability, so
<span class="mono">'12'</span>, <span class="mono">'-0.5'</span> and
<span class="mono">'99999999'</span> are all accepted.</p>
<div class="blocked"><b>So the correction replaced a smaller claim with a larger gap.</b>
<span class="mono">CAST</span> is still the right way to order the column, but not for the reason first
written — and the real defect is that <b>nothing bounds a confidence value to
<span class="mono">[0,1]</span></b>. That is recorded as limitation 1 (§11) and pinned by
<span class="mono">test_the_check_does_not_bound_the_range_and_that_is_recorded</span> rather than quietly
fixed here: bounding the range belongs to whoever writes
<span class="mono">memory_item.confidence</span> in stage 10, and a constraint that <i>pretended</i> to bound
it would be worse than one that says it does not.</div>

<h3>5 &middot; L-A: the test that keeps the fix fixed<span class="tag">tests/test_schema_fidelity.py · 35 tests</span></h3>
<p><span class="cite">0001_core.sql</span> claimed <i>&ldquo;the two are kept column-for-column
compatible&rdquo;</i>. Nothing checked that claim: no test read the <span class="cite">.sql</span> files, and
the runner applies <span class="mono">schema.MIGRATIONS</span>, so the target was executed by neither the app
nor the suite. It is enforced now.</p>
<div class="card">{fidelity_table()}</div>
<p class="cap">Two properties are deliberate. The comparison is against the <b>live post-migration</b>
schema, not the SQL text. And the legitimate translations —
<span class="mono">TIMESTAMPTZ</span>, <span class="mono">JSONB</span>,
<span class="mono">BOOLEAN</span>, <span class="mono">TEXT[]</span>, and every numeric as
<span class="mono">TEXT</span> — are a written-down map a reader can argue with, which is what makes the
remaining differences readable as defects.</p>
<p>Building it produced three false positives. They are recorded because <b>an audit that cries wolf gets its
findings acted on</b>, which is worse than no audit — this project has now patched a correct document, chased
a phantom &ldquo;lost indexes&rdquo; report, and nearly shipped a self-contradictory assertion, all from its
own tooling.</p>
<div class="card">{false_positive_table()}</div>

<h3>6 &middot; F-20: a fourth migration broke the migration runner<span class="tag">docs/15 §9.3 · found and fixed</span></h3>
<p><b>Found by the existing suite, not by a new test.</b> Adding 0004 made
<span class="mono">test_a_skipped_migration_applies_once_its_table_exists</span> fail:</p>
{verbatim("the failure, reproduced against the state the database was in before the fix", F20_FAIL, "before")}
<p>The scenario is one this repository <b>deliberately supports and tests</b>: boot once with an ephemeral
audit backend, where there is no <span class="mono">audit_log</span> to protect so 0003 is
<i>skipped</i>, then boot the same file with a durable one. Until 0004, 0003 was the last migration, so
nothing could ever move past it. Adding a migration <b>behind a skippable one</b> made the combination fatal:
the ephemeral boot applies 0004 while 0003 waits, and the next durable boot finds an applicable migration
below an applied one.</p>
<div class="blocked"><b>The refusal was correct.</b> &ldquo;No holes&rdquo; is how a permanently bypassed
migration gets noticed, and a bypass is fatal. What the runner could not do was tell a <b>hole</b> from a
<b>deferral it had itself reported one boot earlier</b> — in
<span class="mono">schema_migrations</span> the two look identical, because in both cases the version is
simply absent. That is F-20: a defect in the Stage 6 runner that only a fourth migration could expose.</div>
<p>The fix is <span class="mono">schema_migration_skips (version, reason, skipped_at)</span>, created by
<span class="mono">SCHEMA_MIGRATIONS_DDL</span> — which is <b>not</b> a versioned migration, so this needed no
new version and moved no checksum. The runner records a skip when it reports one, and clears it <b>in the same
transaction</b> as the application, so a version is never recorded as applied while a stale skip row still
claims it is waiting.</p>
{verbatim("the same sequence, now that a deferral is recorded", F20_FIXED, "after")}
{verbatim("and the guard keeps its teeth", F20_TEETH)}
<div class="card">{f20_table()}</div>
<p class="cap"><b>A consequence worth stating plainly.</b> Because 0004 now applies in memory mode too,
<span class="mono">venue_instrument_mapping</span> exists under CI's
<span class="mono">NEXUS_AUDIT_BACKEND=memory</span>. Had the fix gone the other way — stopping the runner at
the first migration it cannot apply, which is what most migration runners do — memory mode would have had no
such table, <span class="mono">counts()</span> would have failed on it, and <b>L-B could not have been wired
into boot at all</b>. Two defensible runner semantics; only one left the rest of this batch possible.</p>
<p>Three stale expectations were updated, and two were made <b>derived</b> rather than re-hardcoded: a status
test asserted a literal three-version list and a skip test a literal two-version list, and both now derive
from <span class="mono">MIGRATIONS</span>, so adding 0005 will not break them. This is the third time the
project has had to repair a test that hardcoded a total which grows — the standing rule about publishing
floors rather than totals applies to test expectations as well as to documents.</p>

<h3>7 &middot; L-B: the seeded master reaches the system of record<span class="tag">F-16 · docs/15 §9.4</span></h3>
<p>The mechanism already existed. <span class="mono">instrument.registered</span> was in
<span class="mono">PROJECTABLE</span>, the dispatcher routed it to
<span class="mono">save_instrument</span>, and <span class="mono">reproject_missing</span> would have replayed
it from the chain. <b>Nothing emitted the event</b>, so there was nothing to replay. L-B is therefore an
emitter and not a mechanism: <span class="cite">instruments/projection.py</span>, 168 lines.</p>
{verbatim("F-16's observable, inverted — captured against a real durable store", LB_BEFORE_AFTER, "after")}
<div class="card">{lb_decision_table()}</div>
{verbatim("what the four mappings look like once they are rows", LB_ROWS)}
<p class="cap"><span class="mono">/v1/status</span> gained one key so the fix is visible where the defect was
found: <span class="mono">instrument_master</span> now reads
<span class="mono">count 3, active 0, projected 3</span> beside
<span class="mono">persistence.counts.venue_instrument_mapping = 4</span>. Reporting only the registry side
would have left F-16's remedy invisible in the one place F-16 was visible.</p>

<h3>8 &middot; What the projection faithfully records as empty<span class="tag">F-16's residue</span></h3>
<p>All four mappings project <span class="mono">margin_rate = NULL</span> and
<span class="mono">fees = {{}}</span>, and <span class="mono">contract_size</span> on one of four. That is not
the writer dropping fields — it is Stage 7.3's seed specs never having carried them. <b>Neither word appears
in <span class="cite">instruments/seed.py</span></b> (verified by
<span class="mono">grep -c</span>: 0). Filling them in would mean inventing a margin rate and a fee schedule
with nothing behind them, so they stay empty and
<span class="mono">test_the_seeded_mappings_have_no_margin_rate_or_fees_to_project</span> pins that they are
empty <i>for that reason</i> rather than by accident.</p>
<div class="blocked"><b>The bybit row survives with its reason attached.</b>
<span class="mono">status = SUPPORTED</span> and a note beginning
<span class="mono">GEO-BLOCKED</span>, naming F-2 and the D-021 VM. The owner's Stage 7 ruling was that the row
stays open <i>and visible</i> — and a projection that dropped the note would have made it invisible again in
the system of record while remaining visible in the registry, which is the same defect wearing a different
hat.</div>

<h3>9 &middot; L-C: the first <span class="mono">evidence_ref</span> writer<span class="tag">docs/15 §9.5</span></h3>
<p><span class="cite">src/nexus/intelligence/</span> is a new package — the fifteenth under
<span class="cite">src/nexus/</span> — holding <span class="cite">evidence.py</span>, 279 lines.
<span class="mono">dossier</span> and <span class="mono">memory_item</span> remain writer-less by ruling. The
writer follows the contract §5.1 of <span class="cite">docs/15</span> derived from the existing writers:
validate the identity column, <span class="mono">assert_no_secrets</span>, write inside a transaction, then
<span class="mono">_mark</span> into <span class="mono">op_projection</span>. It is audited as
<span class="mono">evidence.recorded</span>, so it is recoverable from the chain like every other write.</p>
{verbatim("the two timestamps — the content of this batch", LC_TIMESTAMPS, "after")}
<div class="card">{lc_decision_table()}</div>
{verbatim("every refusal, captured; and the chain afterwards", LC_REFUSALS)}
<p class="cap">One defect was found while testing the writer and fixed: a naive
<span class="mono">observed_at</span> raised a bare <span class="mono">TypeError</span> from the timestamp
subtraction, because <span class="mono">iso_utc</span>'s own refusal runs <i>after</i> the arithmetic. An
unclassified crash at a boundary names nothing — the failure mode F-4 was about — so both timestamps are now
gated before they are used.</p>

<h3>10 &middot; What F-14's cheap half does, and what it does not do<span class="tag">O-012 stays OPEN</span></h3>
<div class="card">{table(["", "After 8.2"], [
    ("<b>Changed</b>", "The evidence graph no longer <i>imports</i> the defect. A row written from now on says "
     "which of its two timestamps came from the venue, keeps them in separate required columns, and carries the "
     "interval beside the qualification that it conflates network delay with clock offset."),
    ("<b>Not changed</b>", "<b>No adapter was touched.</b> <span class='mono'>observed_at</span> is still venue "
     "time in all four, and no receipt time exists anywhere in ingestion, so <b>latency remains "
     "unmeasurable</b>. Nothing in this batch measures anything it could not measure before."),
    ("<b>Why the cheap half was the right half here</b>", "The expensive half changes what a persisted field "
     "means across four adapters, every record type and every test asserting on those fields. Doing that inside "
     "a batch that is also rebuilding two tables and changing the migration runner would have made any "
     "regression ambiguous between three causes."),
    ("<b>What it now costs to leave open</b>", "Run 29 measured the wall-clock rate at <b>3.95&times;</b> the "
     "venue-time rate, so using <span class='mono'>observed_at</span> as a denominator biases a rate "
     "<i>downward</i> by the skew factor rather than merely adding noise. Re-asked as its own batch in §12."),
])}</div>

<h3>11 &middot; The gate, and what this batch cannot claim<span class="tag">docs/15 §9.6, §9.7</span></h3>
<div class="card">{gate_table()}</div>
<p class="cap">Every number above was produced by the command beside it and re-verified before being written
here. <b>No live endpoint was called</b> and nothing in this batch touches ingestion, so the live-check count
is unchanged at 49 and <b>no run number is published on this board</b> — there is nothing new to re-trigger.</p>
<div class="card">{delta_table()}</div>
<div class="card">{batch_table()}</div>
<div class="card">{limits_table()}</div>

<h3>12 &middot; Decision requested<span class="tag">docs/15 §9.8</span></h3>
<div class="card">{lever_table()}</div>
<div class="ask">
<p><b>Recommendation: approve Stage 8.2 as delivered, and authorise 8.3 as L-D + L-E only.</b> The dossier
writer is what makes the intelligence layer observable, and the read-only route is what makes it checkable;
both now stand on a schema that agrees with its target, a system of record that holds the instruments, and an
evidence table with a writer that cannot conflate two timestamps.</p>
<ol>
<li><b>Is Stage 8.2 approved?</b> L-A + L-B + L-C as described, with two disclosures: the deviation from the
approved remedy in §3 (TEXT kept, CHECK added, because
<span class="mono">NUMERIC(6,5)</span> stores a float) and the migration-runner change in §6 (F-20, which the
existing suite found and which had to be fixed for 0004 to be bootable at all).
<b>Recommendation: approve</b>, recorded as <b>D-051</b>.</li>
<li><b>What is 8.3?</b> L-D is the read-only <span class="mono">/v1/intelligence/dossiers</span> route; L-E is
the dossier writer at <span class="mono">stance=ABSTAIN</span>; F-18's cheap half is three
<span class="mono">ADD COLUMN</span>s on <span class="mono">memory_item</span> plus
<span class="mono">contradicts</span> on <span class="mono">evidence_ref</span>.
<b>Recommendation: L-D + L-E only</b>, and defer F-18's columns to the batch that writes
<span class="mono">memory_item</span> in stage 10 — columns no writer populates are columns no test can
exercise, and §8 is evidence that a nullable column nobody fills is indistinguishable from one that was
dropped.</li>
<li><b>F-14's expensive half: authorise it, and when?</b> The merits are now quantified — run 29's
3.95&times; skew means <span class="mono">observed_at</span> as a denominator biases rates downward, not just
noisily. <b>Recommendation: authorise it as its own batch (8.4), not folded into 8.3.</b> It gives four
adapters a receipt time, which changes what a persisted field means, and it deserves its own gate and its own
live runs; folding it into a batch that also writes the dossier would make any regression ambiguous between
the two.</li>
<li><b>§8's fourth question, still unanswered: should finding ids be scoped per stage from Stage 8
onward?</b> F-19 records that F-1…F-7 are already ambiguous between two approved documents, and F-20
continues the global sequence. <b>Recommendation: continue global numbering</b>, as §8 recommended — a prefix
scheme introduced halfway creates a second convention to remember, and the collision is now recorded where a
reader will find it.</li>
</ol>
</div>

<footer>Stage 8.2 &middot; L-A + L-B + L-C &middot; D-050 &middot; first batch to change
<span class="mono">backend/</span> since 9e70ed3: 17 files, 2,236 insertions, gate 1,117 passed / 2 skipped /
0 failed (+81 tests), mypy strict clean on 60, ruff + format clean on 88 &middot; F-15 and F-16 closed, F-20
found and fixed, F-14 left open by ruling &middot; migration 0004_memory_fidelity: 15 statements, three
earlier checksums unchanged, all four now pinned &middot; 0 schema divergences across 16 compared tables
&middot; the seeded master projects: count 3, projected 3, four venue mappings, nothing appended on restart
&middot; two claims this batch wrote down were falsified by execution and are corrected here in §2 and §4
&middot; no live endpoint called, so no run number is published</footer>
</div></body></html>"""
    out = HERE / "stage8-2-intelligence-memory.html"
    out.write_text(html_out)
    return out


if __name__ == "__main__":
    path = main()
    print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB)")
