"""Stage 8.3 board: a dossier can be opened, and the route that serves it names what it cannot.

L-D + L-E, authorised by D-051. F-18's columns and F-14's expensive half are ruled out of this batch and
are shown absent rather than merely unmentioned.

Every transcript here was captured from `backend/.venv/bin/python` runs against the real applied DDL and a
real `create_app()` while this board was being written, and pasted verbatim — including the one that
falsified a claim Stage 8.2 published (§9, F-21) and the one that re-derived a count three copies of which
had gone stale (§10). Captures: `/tmp/cap83.py` (BLOCKS A–F) and `/tmp/cap83b.py` (BLOCKS G–K).

Run:  backend/.venv/bin/python design/build_board83.py
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
/* `.card` wraps every table here and is undefined in the shared shell (CSS71) — the same gap the 8.2
   board recorded. Definition copied verbatim from `build_specimen.py`, the approved visual language,
   rather than invented, and added to THIS board's extension only. */
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


# ------------------------------------------------------------------ §1 what was ruled
def ruled_table() -> str:
    return table(
        ["Question put on the 8.2 board", "Answer", "What it authorised, and what this batch did with it"],
        [
            (
                "Is Stage 8.2 approved?",
                "<b>Recommend</b>",
                "<b>D-051</b>, with §9.2's deviation (TEXT kept, CHECK added, range unbounded) and §9.3's "
                "runner change (F-20) disclosed. The offered alternative — bound the range before 8.3 — was "
                "<b>not</b> taken, so no range guard on <span class='mono'>memory_item.confidence</span> "
                "appears here and limitation 1 of §9.7 still stands as published.",
            ),
            (
                "What is 8.3?",
                "<b>Recommend</b>",
                "<b>L-D + L-E only.</b> The read-only route and the dossier writer at "
                "<span class='mono'>stance=ABSTAIN</span>. Both are here; nothing else is (§2).",
            ),
            (
                "F-14's expensive half: authorise it, and when?",
                "<b>Recommend</b>",
                "<b>Its own batch, 8.4</b>, with its own gate and its own live runs. Not started: no adapter "
                "changed, no third timestamp exists, <span class='mono'>O-012</span> stays "
                "<b>OPEN</b>. §7 shows the route naming that absence instead of hiding it.",
            ),
            (
                "Should finding ids be scoped per stage?",
                "<b>Recommend</b>",
                "<b>Global numbering continues</b>, so this batch's one new finding is <b>F-21</b> (§9), not a "
                "scoped <span class='mono'>S8-F-1</span>. No renumbering of the recorded F-1…F-7 collision.",
            ),
        ],
    )


def not_done_table() -> str:
    return table(
        ["Ruled out of 8.3", "How its absence is shown, not asserted", "Where it goes"],
        [
            (
                "<b>F-18's cheap half</b> — three <span class='mono'>ADD COLUMN</span>s on "
                "<span class='mono'>memory_item</span> (<span class='mono'>valid_from</span>, "
                "<span class='mono'>valid_until</span>, <span class='mono'>change_conditions</span>) plus "
                "<span class='mono'>contradicts</span> on <span class='mono'>evidence_ref</span>.",
                "No migration exists beyond <span class='mono'>0004_memory_fidelity</span>, so no migration "
                "checksum moved and <span class='mono'>test_schema_fidelity.py</span> still collects "
                "<b>35</b> tests with its three pinned checksums. A test asserts "
                "<span class='mono'>persistence.counts.memory_item == 0</span> and that the column set of "
                "<span class='mono'>dossier</span> is exactly the twelve names the schema declares — so an "
                "invented <span class='mono'>counter_thesis</span> or <span class='mono'>tier</span> column "
                "would fail the suite.",
                "The stage-10 batch that writes <span class='mono'>memory_item</span>. Columns no writer "
                "populates are columns no test can exercise.",
            ),
            (
                "<b>F-14's expensive half</b> — a real receipt time in <span class='mono'>okx</span>, "
                "<span class='mono'>bybit</span>, <span class='mono'>binance_vision</span> and "
                "<span class='mono'>dukascopy</span>.",
                "No file under <span class='mono'>ingestion/</span> is in this batch's diff (11 files, all "
                "in <span class='mono'>store/</span>, <span class='mono'>intelligence/</span>, "
                "<span class='mono'>api/</span>, <span class='mono'>migrations/</span> and "
                "<span class='mono'>tests/</span>). Live checks still collect <b>49</b> and the offline "
                "subset still passes <b>32</b>, so nothing that asserts on "
                "<span class='mono'>observed_at</span> moved.",
                "<b>8.4</b>, authorised by D-051 and not started. Its evidence is the seven measured skews of "
                "&sect;10 &mdash; 0.80&times; to 3.97&times; across runs 24&ndash;30, every pair re-read "
                "from its own CI annotation.",
            ),
            (
                "<b>Anything that decides what the system researches.</b> No caller of "
                "<span class='mono'>open_dossier</span> and no caller of "
                "<span class='mono'>record_evidence</span>.",
                "A test greps <span class='mono'>src/nexus</span> for callers of both and fails if one "
                "appears, so the unwired state is pinned rather than incidental. The route therefore serves "
                "an honest empty in every environment and says so (§6).",
                "Unruled. §13 puts it to the owner: wiring a writer means choosing the system's research "
                "agenda, which no document authorises.",
            ),
        ],
    )


# ------------------------------------------------------------------ §2 the writer
OPEN_ROW = """
dossier_id: CASE-0CB572D89F5247D1-MPCJ26KZ   (prefix CASE, which core.ids.new_id has declared
                                              for a research case since Phase 2 and nothing had spent)
audit_ref:  AUD-19285A24053F45CA-HVBA9CPD    PROJECTABLE["dossier.opened"] = dossier
stance: ABSTAIN | state: DRAFT | sufficiency: INSUFFICIENT | venue_maps_instrument: True
created_at: 2026-11-26T20:59:51.934Z | updated_at: 2026-11-26T20:59:51.934Z
stored row: {
  "dossier_id": "CASE-0CB572D89F5247D1-MPCJ26KZ",
  "instrument_id": "INS-BTC-USDT-USDT",
  "venue": "OKX",
  "created_at": "2026-11-26T20:59:51.934Z",
  "updated_at": "2026-11-26T20:59:51.934Z",
  "state": "DRAFT",
  "summary": "Perp basis widening into the US session; watching for a funding flip.",
  "stance": "ABSTAIN",
  "uncertainty": "Sixty seconds of ticker data only, so the regime is unknown.",
  "sufficiency": "INSUFFICIENT",
  "payload": {
    "sufficiency_basis": "one okx ticker and one order-book snapshot, both LIVE, 0.3s apart",
    "sufficiency_target": "V1 evidence and data sufficiency for a research case, not for a trade",
    "venue_maps_instrument": true
  },
  "audit_ref": "AUD-19285A24053F45CA-HVBA9CPD"
}
sufficiency_of(row): {
  "sufficiency": "INSUFFICIENT",
  "sufficiency_basis": "one okx ticker and one order-book snapshot, both LIVE, 0.3s apart",
  "sufficiency_target": "V1 evidence and data sufficiency for a research case, not for a trade"
}
"""


def decisions_table() -> str:
    return table(
        ["Decision the writer makes", "What points at it", "Why the alternative was not taken"],
        [
            (
                "<b><span class='mono'>stance</span> is validated against "
                "<span class='mono'>DecisionVerb</span></b> — seven words, case-sensitive.",
                "The schema's own default <span class='mono'>'ABSTAIN'</span> is a "
                "<span class='mono'>DecisionVerb</span> member and belongs to no other enum in the "
                "repository; <span class='cite'>docs/03</span> §7 and <span class='cite'>docs/10</span> "
                "§3.1 both name exactly this list for the intelligence layer's disposition.",
                "Stage 8.2 left <span class='mono'>evidence_ref.kind</span> as free text <i>because no "
                "vocabulary for it is declared anywhere</i>. Where one exists and the column's default is "
                "in it, using it is not invention — and leaving the column open invites an eighth word for "
                "ABSTAIN. The column stays <span class='mono'>TEXT</span>: the writer enforces this, the "
                "schema does not, and a test pins which of the two is doing the work. Lower case is refused "
                "too, because a vocabulary that silently normalises case is one nobody has to learn.",
            ),
            (
                "<b><span class='mono'>sufficiency</span> stays a string, and a claim must carry its basis "
                "and its target.</b>",
                "<span class='cite'>docs/15</span> §6's L-E: sufficiency stays a string until stage 10 "
                "defines the meter. <span class='cite'>docs/10</span> §3.1's rail asks for a "
                "&ldquo;knowledge-sufficiency meter with stated basis and what it is sufficient for&rdquo;; "
                "§3.2 warns a bare enum &ldquo;leaves nowhere for V1's outcome to live&rdquo;.",
                "No scale is invented, so <span class='mono'>INSUFFICIENT</span> is the default and needs "
                "neither key — it claims nothing. Anything above it needs <b>both</b> pinned payload keys. "
                "A <b>numeric</b> value is refused outright under <span class='cite'>docs/12</span> §1.3's "
                "law (A-02+A-08) that no gate can be satisfied by a confidence value: "
                "<span class='mono'>'0.85'</span> in this column is a confidence value wearing a "
                "judgement's name, and the meter stage 10 defines will read this string, not the reverse.",
            ),
            (
                "<b>A venue the instrument is not mapped on is <i>recorded</i>, not refused</b> — "
                "<span class='mono'>venue_maps_instrument</span>, computed from the master and pinned.",
                "The seeded master maps four pairs (§5). <span class='mono'>INS-EUR-USD</span> on "
                "<span class='mono'>OANDA</span> is unmapped and is a legitimate research case today.",
                "Refusing it would block the gap research the Intelligence Centre exists to hold. The two "
                "cases mean different things to a reviewer — a mapped pair is about something this system "
                "can observe, an unmapped one is about a gap — so the flag is written down and the reader "
                "decides. It is a snapshot: nothing re-checks it if the master moves (§12, limitation 4).",
            ),
            (
                "<b>Opening is not editing</b> — a caller-supplied id that already exists is refused.",
                "<span class='cite'>docs/15</span> §5.1: memory is superseded, never edited in place, which "
                "is why <span class='mono'>memory_item.superseded_by</span> exists.",
                "<span class='mono'>save_dossier</span> uses <span class='mono'>INSERT OR REPLACE</span> "
                "because it is a <i>projection</i> and a replay must be able to restate a row. A second "
                "&ldquo;open&rdquo; through the writer would silently rewrite the first case's stance and "
                "summary; the chain would hold both events, so nothing is lost durably, but the row a "
                "reviewer reads would no longer be the row that was opened. A test pins that the store "
                "<i>would</i> have replaced it, so the refusal reads as a decision and not an accident. "
                "Changing a stance is a later batch's verb with its own audit event.",
            ),
            (
                "<b>Both timestamps ride inside the audited event.</b>",
                "The applied schema has no <span class='mono'>DEFAULT now()</span> for "
                "<span class='mono'>created_at</span> or <span class='mono'>updated_at</span> — two of the "
                "four defaults §9.1 classifies as a house convention.",
                "A projection that filled them at write time would restamp a replayed event with the "
                "replay's clock, and boot recovery would quietly rewrite the chronology "
                "<span class='cite'>docs/10</span> §3.1 asks the view to show. §4 tests it across a real "
                "1.05 s gap.",
            ),
        ],
    )


# ------------------------------------------------------------------ §3 the refusals
REFUSALS = """
  summary='' (whitespace)      -> ValueError: a dossier needs a summary: it is the thesis in one line, the 'concise rationale' docs/03 §7 permits ...
  stance='MAYBE'               -> ValueError: stance must be one of ['ACCEPT', 'REJECT', 'WAIT', 'REDUCE', 'EXIT', 'ESCALATE', 'ABSTAIN']; got 'MAYBE' ...
  stance='abstain' (case)      -> ValueError: stance must be one of [...]; got 'abstain' ...
  venue='NASDAQ'               -> ValueError: venue must be one of ['BYBIT', 'BINANCE', 'OKX', 'DUKASCOPY', 'MT4', 'MT5', 'CTRADER', 'IBKR', 'OANDA', 'ALPACA'] or None ...
  venue='okx' (case)           -> ValueError: venue must be one of [...] or None; got 'okx' ...
  sufficiency='0.85'           -> ValueError: sufficiency must be a judgement, not a number; got '0.85'. docs/12 §1.3's law (A-02+A-08) ...
  sufficiency='12'             -> ValueError: sufficiency must be a judgement, not a number ...
  sufficiency='1e-9'           -> ValueError: sufficiency must be a judgement, not a number ...
  SUFFICIENT, no basis         -> ValueError: sufficiency='SUFFICIENT_FOR_REVIEW' claims a judgement, so it needs both sufficiency_basis ... and sufficiency_target ...
  SUFFICIENT, no target        -> ValueError: sufficiency='SUFFICIENT_FOR_REVIEW' claims a judgement, so it needs both ...
  ABSTAIN, no uncertainty      -> ValueError: stance=ABSTAIN needs a non-empty uncertainty: the schema's comment is that ABSTAIN is the default and not a fallback ...
  instrument_id='INS-NOPE'     -> ValueError: instrument 'INS-NOPE' is not in the system of record, which holds 3: [...] ...
  instrument_id=''             -> ValueError: instrument_id must be a real id or None; an empty string is neither
  re-open the same id          -> ValueError: dossier 'CASE-0CB572...' already exists, and opening is not editing ...
  payload={'api_secret': ...}  -> SecretMaterialDetected: SECRET_UNAVAILABLE: refused to audit secret material: forbidden key at payload.api_secret
chain length before: 10 after: 10 | dossiers: 1
"""

REFUSAL_FULL = """
### summary
a dossier needs a summary: it is the thesis in one line, the 'concise rationale' docs/03 §7 permits and the first thing J-04 step 1 renders. A case that cannot say what it is about cannot be reviewed, and state='DRAFT' means not yet dispositioned, not not yet described

### stance
stance must be one of ['ACCEPT', 'REJECT', 'WAIT', 'REDUCE', 'EXIT', 'ESCALATE', 'ABSTAIN']; got 'MAYBE'. The schema's own default 'ABSTAIN' is a DecisionVerb member, and docs/03 §7 and docs/10 §3.1 both name that vocabulary for the intelligence layer's disposition

### venue
venue must be one of ['BYBIT', 'BINANCE', 'OKX', 'DUKASCOPY', 'MT4', 'MT5', 'CTRADER', 'IBKR', 'OANDA', 'ALPACA'] or None; got 'NASDAQ'. None means the case is not about one venue, which is a statement — an unrecognised string is not one

### numeric sufficiency
sufficiency must be a judgement, not a number; got '0.85'. docs/12 §1.3's law (A-02+A-08) is that no gate can be satisfied by a confidence value, and a numeric sufficiency is a confidence value in a judgement's column — the meter stage 10 defines will read this string, not the other way round

### claim without basis and target
sufficiency='SUFFICIENT_FOR_REVIEW' claims a judgement, so it needs both sufficiency_basis (what it rests on) and sufficiency_target (what it is sufficient FOR) — docs/10 §3.1's rail carries 'stated basis and what it is sufficient for', and §3.2's warning is that a bare enum leaves nowhere for V1's outcome to live. 'INSUFFICIENT' needs neither, because it claims nothing

### ABSTAIN without uncertainty
stance=ABSTAIN needs a non-empty uncertainty: the schema's comment is that ABSTAIN is the default and not a fallback, and an abstention that does not say what is unresolved is a fallback. J-04's exit condition is that the owner learns what would invalidate the thesis

### dangling parent
instrument 'INS-NOPE' is not in the system of record, which holds 3: ['INS-BTC-USDT', 'INS-BTC-USDT-USDT', 'INS-EUR-USD']. dossier.instrument_id REFERENCES instrument since migration 0004_memory_fidelity, but PRAGMA foreign_keys is deliberately off, so SQLite would accept this dangling parent without comment — project the instrument first (Stage 8.2's L-B) or open the case with instrument_id=None
"""

PARENT = """
PRAGMA foreign_keys on a fresh connection: 0
PRAGMA foreign_key_list(dossier): [(0, 0, 'instrument', 'instrument_id', 'instrument_id',
                                    'NO ACTION', 'NO ACTION', 'NONE')]
dangling parent, pragma OFF -> accepted, rows: 1
pragma ON                   -> refused: FOREIGN KEY constraint failed
"""

BEFORE_PROJECTION = """
instruments in store before projection: 0
open_dossier(instrument_id="INS-BTC-USDT") ->
  ValueError: instrument 'INS-BTC-USDT' is not in the system of record, which holds 0: [].
  dossier.instrument_id REFERENCES instrument since migration 0004_memory_fidelity, but
  PRAGMA foreign_keys is deliberately off, so SQLite would accept this dangling parent
  without comment — project the instrument first (Stage 8.2's L-B) or open the case with
  instrument_id=None
"""


def refusal_table() -> str:
    return table(
        ["Refusal", "Class", "Why it is a refusal and not a normalisation"],
        [
            ("empty or whitespace <span class='mono'>summary</span>", "<span class='mono'>ValueError</span>",
             "It is the thesis in one line and the first thing J-04 step 1 renders. "
             "<span class='mono'>state='DRAFT'</span> means not yet dispositioned, not not yet described."),
            ("<span class='mono'>stance</span> outside the seven verbs, including lower case",
             "<span class='mono'>ValueError</span>",
             "A vocabulary that silently normalises case is a vocabulary nobody has to learn, and an "
             "eighth word for ABSTAIN is how a disposition column becomes free text again."),
            ("<span class='mono'>venue</span> outside the ten members, including lower case",
             "<span class='mono'>ValueError</span>",
             "<span class='mono'>None</span> is how a case says &ldquo;not one venue&rdquo;, which is a "
             "statement; an unrecognised string is not one."),
            ("numeric <span class='mono'>sufficiency</span> — <span class='mono'>'0.85'</span>, "
             "<span class='mono'>'12'</span>, <span class='mono'>'0'</span>, "
             "<span class='mono'>'1.0'</span>, <span class='mono'>'-0.5'</span>, "
             "<span class='mono'>'1e-9'</span>", "<span class='mono'>ValueError</span>",
             "<span class='cite'>docs/12</span> §1.3's law: no gate can be satisfied by a confidence "
             "value. This is the refusal the whole batch exists to make."),
            ("a claim above <span class='mono'>INSUFFICIENT</span> missing basis <i>or</i> target",
             "<span class='mono'>ValueError</span>",
             "Both are required, because &ldquo;sufficient&rdquo; without &ldquo;sufficient <i>for</i>&rdquo; "
             "is the bare enum §3.2 warns leaves nowhere for V1's outcome to live."),
            ("<span class='mono'>ABSTAIN</span> with empty <span class='mono'>uncertainty</span>",
             "<span class='mono'>ValueError</span>",
             "The schema's own comment is that ABSTAIN is the default and <b>not a fallback</b>. Scoped by "
             "a test asserting the other six verbs need none, so this reads as a rule about abstention and "
             "not a demand for prose."),
            ("<span class='mono'>instrument_id</span> absent from the system of record, or "
             "<span class='mono'>''</span>", "<span class='mono'>ValueError</span>",
             "The message names the id <b>and how many the store holds</b>, because &ldquo;not in the "
             "system of record, which holds 0&rdquo; is a different failure from &ldquo;which holds 3&rdquo; "
             "and only the first says &ldquo;run the projection&rdquo;."),
            ("re-opening an existing id", "<span class='mono'>ValueError</span>",
             "The store's <span class='mono'>INSERT OR REPLACE</span> is projection semantics; the verb is "
             "&ldquo;open&rdquo;. §2 decision 4."),
            ("secret material anywhere in the payload",
             "<span class='mono'>SecretMaterialDetected</span>",
             "Not this writer's rule — the audit log's, inherited. The refusal happens before the event is "
             "written, so the chain length does not move."),
        ],
    )


# ------------------------------------------------------------------ §4 replay
REPLAY = """
after wipe: dossier = 0 evidence_ref = 0
reapplied refs: 14
created_at before wipe:  2026-11-26T20:59:51.934Z
created_at after replay: 2026-11-26T20:59:51.934Z
identical: True | payload identical: True
evidence row restored: 1 with checksum verifying: True
"""


# ------------------------------------------------------------------ §5 the venue flag
VENUE = """
  master maps INS-BTC-USDT         on BINANCE    as BTCUSDT        DATA_AVAILABLE
  master maps INS-BTC-USDT-USDT    on BYBIT      as BTCUSDT        SUPPORTED
  master maps INS-BTC-USDT-USDT    on OKX        as BTC-USDT-SWAP  DATA_AVAILABLE
  master maps INS-EUR-USD          on DUKASCOPY  as EURUSD         DATA_AVAILABLE
  open(INS-BTC-USDT-USDT , OKX      ) -> venue_maps_instrument=True
  open(INS-BTC-USDT-USDT , BYBIT    ) -> venue_maps_instrument=True
  open(INS-BTC-USDT      , BINANCE  ) -> venue_maps_instrument=True
  open(INS-BTC-USDT      , MT4      ) -> venue_maps_instrument=False
  open(INS-EUR-USD       , DUKASCOPY) -> venue_maps_instrument=True
  open(INS-EUR-USD       , OANDA    ) -> venue_maps_instrument=False   <- a gap, not an error
  open(None              , OKX      ) -> venue_maps_instrument=None
  open(INS-EUR-USD       , None     ) -> venue_maps_instrument=None
  caller tried to forge the flag True -> False
"""


# ------------------------------------------------------------------ §6 the honest empty
EMPTY = """
GET /v1/intelligence/dossiers -> 0 dossiers, 9 named gaps
{ "meaning": "no dossier has been opened at all",
  "writer": "nexus.intelligence.open_dossier exists since Stage 8.3 and is audited as dossier.opened",
  "callers": "none yet — nothing in src/ opens a dossier, which is the same limitation Stage 8.2
              recorded for record_evidence. The writer is built and unwired on purpose: wiring it
              means deciding what the system should research, and that is not this batch's ruling",
  "not_a_fault": "the route works and the table exists; an empty list here is an honest empty, the
              distinction /v1/data/coverage draws between 'no archive' and 'archive holds nothing'" }
served_from: operational projection of the audit chain (R-1); the chain is the record
note: a stance is a research disposition and never a trade signal — docs/03 J-04's exit condition is
      'Research completion ≠ trade signal', and live authority is DENIED
vocabularies.stance.values:      ['ACCEPT', 'REJECT', 'WAIT', 'REDUCE', 'EXIT', 'ESCALATE', 'ABSTAIN']
vocabularies.stance.enforced_by: the writer (intelligence/dossier.py); the column is TEXT and the schema does not
vocabularies.sufficiency.values: None
vocabularies.state.values:       None
"""


def gaps_table() -> str:
    return table(
        ["Element the approved view asks for", "Asked by", "Why this route cannot serve it", "Moved by"],
        [
            ("contradictions highlighted and linked", "<span class='cite'>docs/10</span> §3.1; J-04 step 4",
             "needs <span class='mono'>evidence_ref.contradicts</span>; no such column, so nothing records "
             "that two sources disagree", "<b>D-051</b> deferred F-18's columns to the stage-10 writer"),
            ("counter-thesis", "J-04 step 1; <span class='cite'>docs/10</span> §3.1",
             "no column. <span class='mono'>uncertainty</span> is served and is the nearest thing, but "
             "&ldquo;what is unresolved&rdquo; is not &ldquo;the case against&rdquo;, and the route does not "
             "present one as the other", "&mdash;"),
            ("publication time in the evidence table", "J-04 step 2",
             "<span class='mono'>evidence_ref</span> holds <span class='mono'>observed_at</span> (the venue's "
             "stamp) and <span class='mono'>retrieved_at</span> (our clock at receipt); a source's own "
             "publication moment has no column, and F-14 is still open",
             "F-14/O-012 open; its expensive half authorised as <b>8.4</b> by D-051"),
            ("research depth Tier 0&ndash;4", "<span class='cite'>docs/03</span> §7; "
             "<span class='cite'>docs/10</span> §3.1",
             "no column, and no tier is defined anywhere in the repository", "&mdash;"),
            ("freshness", "J-04 step 4; <span class='cite'>docs/10</span> §3.1",
             "partly served, and the part that is not matters: each row's <span class='mono'>data_status</span> "
             "is what its writer was told at record time and nothing re-evaluates it against the current "
             "clock, so a row recorded <span class='mono'>LIVE</span> stays "
             "<span class='mono'>LIVE</span> in the projection forever", "&mdash;"),
            ("quant result with run id", "<span class='cite'>docs/10</span> §3.1",
             "the run id <i>is</i> served — every dossier and evidence row carries "
             "<span class='mono'>audit_ref</span> — but no quantitative result is computed anywhere in "
             "<span class='mono'>src/</span>, so there is nothing to attach it to", "&mdash;"),
            ("knowledge-sufficiency meter", "<span class='cite'>docs/10</span> §3.1 rail",
             "the basis and the target are served as strings; the meter is not. §6's L-E keeps sufficiency a "
             "string until stage 10 defines the meter", "stage 10"),
            ("beliefs with confidence band, validity interval and change conditions",
             "<span class='cite'>docs/03</span> §7; <span class='cite'>docs/10</span> §3.1",
             "that is <span class='mono'>memory_item</span>: schema-only, no writer, and F-18's three columns "
             "do not exist", "<b>D-051</b> deferred to the stage-10 writer"),
            ("disposition with reason code", "<span class='cite'>docs/10</span> §3.1",
             "the disposition is served as <span class='mono'>stance</span>, but "
             "<span class='mono'>dossier</span> has no reason-code column; reason codes live on "
             "<span class='mono'>DecisionRecord</span>, and a dossier is not a decision", "&mdash;"),
        ],
    )


# ------------------------------------------------------------------ §8 what the route serves
SERVED = """
store order  (evidence_refs): ['okx.ticker', 'okx.books']
route order  (chronology)   : ['okx.books', 'okx.ticker']
   2026-11-26T12:00:00.300Z okx.books   observed=2026-11-26T12:00:00.000Z src=VENUE latency=0.3 status=LIVE checksum_ok=True
   2026-11-26T12:00:02.300Z okx.ticker  observed=2026-11-26T12:00:02.000Z src=VENUE latency=0.3 status=LIVE checksum_ok=True
evidence_count: 2 | evidence_checksums_verify: True
dossier keys served: ['audit_ref', 'chronology', 'created_at', 'dossier_id', 'evidence_checksums_verify',
  'evidence_count', 'instrument_id', 'payload', 'stance', 'state', 'sufficiency', 'sufficiency_basis',
  'sufficiency_target', 'summary', 'uncertainty', 'updated_at', 'venue', 'venue_maps_instrument']
invented keys absent: none
"""

READONLY = """
  POST   /v1/intelligence/dossiers -> 405      PUT -> 405   PATCH -> 405   DELETE -> 405
  methods registered on both paths: ['GET']
  GET unknown id -> 404 {'detail': 'unknown dossier: CASE-NOPE'}
  GET known id   -> 200
  limit=   1 -> 200     limit= 200 -> 200     limit=   0 -> 422     limit= 201 -> 422
  openapi paths: ['/v1/intelligence/dossiers', '/v1/intelligence/dossiers/{dossier_id}']
"""

STATUS = """
  top-level keys (14): unchanged
  any key mentioning intelligence or dossier: none
  persistence.counts.dossier      = 1
  persistence.counts.evidence_ref = 2
  persistence.counts.memory_item  = 0
  instrument_master               = {'count': 3, 'active': 0, 'projected': 3}
"""


def route_table() -> str:
    return table(
        ["Behaviour", "Value", "Why that value and not the convenient one"],
        [
            ("Application routes before &rarr; after", "11 &rarr; <b>13</b>",
             "17 handler routes once FastAPI's own four are counted; the OpenAPI schema publishes <b>12</b> "
             "because <span class='mono'>/metrics</span> is "
             "<span class='mono'>include_in_schema=False</span>. Three different counts of the same app, so "
             "all three are stated rather than one being called &ldquo;the&rdquo; count."),
            ("Write verbs on either path", "<b>405</b>",
             "Read-only at the router, not only by convention. A route that accepted "
             "<span class='mono'>POST</span> and ignored it would be worse than one that refuses."),
            ("<span class='mono'>limit</span>", "<span class='mono'>Query(default=50, ge=1, le=200)</span>",
             "Bounded so a caller cannot ask for the whole table, and <b>422</b> rather than a silent clamp "
             "so a typo is visible. The bounds are in the OpenAPI schema, so the Intelligence Centre chrome "
             "can read them instead of hardcoding them."),
            ("Unknown dossier id", "<b>404</b> with the id in the detail",
             "A typo and a case that holds nothing must not look the same. The 200-with-empty-body shape is "
             "reserved for the list, where empty is a fact about the system and not an error."),
            ("Chronology order", "oldest first",
             "<span class='mono'>store.evidence_refs</span> returns newest first, which is right for "
             "&ldquo;what did we lately rely on&rdquo; and wrong for a chronology "
             "(<span class='cite'>docs/10</span> §3.1). The route re-sorts by "
             "(<span class='mono'>retrieved_at</span>, <span class='mono'>evidence_id</span>) so ties are "
             "deterministic, and a test pins that the two orders differ."),
            ("<span class='mono'>evidence_checksums_verify</span>",
             "<span class='mono'>None</span> with no evidence, else <span class='mono'>all(...)</span>",
             "<span class='mono'>all(())</span> is <span class='mono'>True</span>, so a case holding no "
             "evidence would otherwise report itself verified. <span class='mono'>None</span> says "
             "&ldquo;nothing to verify&rdquo;, which is the honest-empty distinction again."),
            ("Provenance keys", "lifted <b>beside</b> the payload",
             "<span class='mono'>sufficiency_basis</span>, <span class='mono'>sufficiency_target</span> and "
             "<span class='mono'>venue_maps_instrument</span> are served at the top level as well as inside "
             "<span class='mono'>payload</span>, so a reader does not have to know where the writer put "
             "F-14's qualifications and §10's basis to see them."),
            ("Empty, filtered", "&ldquo;no dossier has been opened <b>for this instrument</b>&rdquo;",
             "The empty is scoped, so a filter that matches nothing does not read as a system that has "
             "researched nothing."),
            ("<span class='mono'>/v1/status</span>", "<b>no new key</b> (14 top-level)",
             "<span class='mono'>counts()</span> has listed <span class='mono'>dossier</span> since Stage 6, "
             "so an empty Intelligence Centre was always observable there. §9.7 recorded the one key 8.2 "
             "<i>did</i> add as a limitation; this batch adds none."),
        ],
    )


# ------------------------------------------------------------------ §9 F-21
F21 = """
two rows, no caller payload:
  EV-F34AF48F352 source=okx.books   observed_at=2026-11-26T12:00:00.000Z retrieved_at=...T12:00:00.300Z locator=.../books
  EV-BE947D99BD4 source=okx.ticker  observed_at=2026-11-26T12:00:02.000Z retrieved_at=...T12:00:02.300Z locator=.../ticker
  payload of both: {'apparent_latency_seconds': 0.3, 'observed_at_source': 'VENUE'}
  payloads equal: True
  what 8.2 hashed  sha256(dumps_canonical(payload)):
     row A: 4e3f2bafa9e22a8a429f4a33b07d6bdf
     row B: 4e3f2bafa9e22a8a429f4a33b07d6bdf
     IDENTICAL: True <- the defect: different rows, one checksum
  what 8.3 hashes  evidence_checksum(row), covering 9 fields:
     row A: dab6a4e92c70a081a6583b2e5711d6c5
     row B: 98403ebaf87436adb41dc331f3605e8d
     DIFFER: True
  covered fields: ('evidence_id', 'dossier_id', 'source', 'kind', 'observed_at', 'retrieved_at',
                   'data_status', 'locator', 'payload')
  excluded: checksum (by definition) and audit_ref (it does not exist yet when the writer hashes;
            the chain's own hash linkage covers that link)
  recomputable from the row alone: True | verifies: True
  a reader adding a top-level key cannot change it: True
  a reader changing the payload can: False
"""

TAMPER = """
    altered observed_at   -> verify=False      altered kind          -> verify=False
    altered source        -> verify=False      altered dossier_id    -> verify=False
    altered retrieved_at  -> verify=False      altered evidence_id   -> verify=False
    altered data_status   -> verify=False      altered payload       -> verify=False
    altered locator       -> verify=False      restored              -> verify=True
    checksum set NULL     -> verify=False  (absence of evidence of tampering is not integrity)
"""


def f21_table() -> str:
    return table(
        ["", "Before (Stage 8.2, as published)", "After (this batch)"],
        [
            ("what is hashed", "<span class='mono'>dumps_canonical(payload)</span> — the caller's payload "
             "plus the two provenance keys the writer adds, and nothing else",
             "<span class='mono'>evidence_checksum(row)</span> over "
             "<b><span class='mono'>CHECKSUMMED_FIELDS</span></b>, nine named fields"),
            ("what the docs said", "&ldquo;an <b>integrity</b> checksum over the recorded row&rdquo;, "
             "&ldquo;computed by the writer over exactly what is stored&rdquo; "
             "(<span class='cite'>docs/15</span> §9.5)",
             "the same sentence, now true — and §9.5 carries an inserted correction pointer rather than "
             "being rewritten, because D-051 was ruled on the text as published"),
            ("fields that could change undetected", "<b>9 of 11</b> stored fields, "
             "<span class='mono'>observed_at</span> among them — the field F-14 exists because of",
             "<b>0</b> of the nine covered; <span class='mono'>checksum</span> and "
             "<span class='mono'>audit_ref</span> are outside it by construction and by decision"),
            ("two rows differing in everything but the payload", "<b>one checksum</b>, "
             "<span class='mono'>4e3f2baf…</span>", "<b>two checksums</b>"),
            ("who reads it", "nobody — the value was written and never recomputed, so it was a decoration",
             "the L-D route, on every row it serves: <span class='mono'>checksum_ok</span> per row and "
             "<span class='mono'>evidence_checksums_verify</span> per dossier"),
            ("what a <span class='mono'>NULL</span> checksum means", "untested",
             "<span class='mono'>False</span> — an absence of evidence of tampering is not evidence of "
             "integrity"),
            ("the test that pinned it",
             "<span class='mono'>test_the_checksum_is_over_exactly_what_was_stored</span>, whose docstring "
             "said &ldquo;over the recorded row&rdquo; while its assertion read "
             "<span class='mono'>sha256_hex(dumps_canonical(row[\"payload\"]))</span> — the defect was "
             "<b>enshrined, not caught</b>",
             "replaced by <span class='mono'>TestTheChecksumCoversTheRow</span> (8 methods), whose column "
             "coverage is derived from the live <span class='mono'>table_info(evidence_ref)</span> so a new "
             "column fails until somebody rules on it"),
        ],
    )


# ------------------------------------------------------------------ §10 the stale counts
NUMERIC = """
  target NUMERIC/DECIMAL columns      : 26 across 8 tables
  of those TEXT in the applied schema : 26 across 8 tables     not TEXT: none
  per table: {'decision': 1, 'fills': 3, 'instrument': 1, 'memory_item': 1, 'orders': 4,
              'risk_limit_change': 2, 'trade_intent': 7, 'venue_instrument_mapping': 7}
  without venue_instrument_mapping    : 19 across 7 tables
  venue_instrument_mapping's numeric columns: ['contract_size', 'margin_rate', 'max_order_qty',
              'min_order_qty', 'qty_step', 'tick_size', 'tick_value']
"""


def stale_table() -> str:
    return table(
        ["Where", "What it said", "What it says now"],
        [
            ("<span class='mono'>migrations/0002_memory.sql</span> header",
             "&ldquo;19 numeric columns across 8 tables are TEXT&rdquo; — the exact wrong pairing "
             "<span class='cite'>docs/15</span> §9.1 had already corrected",
             "both numbers, with the scopes named: <b>26 across 8</b> today and <b>19 across 7</b> before "
             "0004 added <span class='mono'>venue_instrument_mapping</span>'s seven, plus a pointer to the "
             "test that re-derives the count"),
            ("<span class='mono'>tests/test_schema_fidelity.py</span>, "
             "<span class='mono'>TYPE_TRANSLATIONS</span> comment",
             "&ldquo;19 columns across 8 tables do this&rdquo;",
             "26 across 8 and 19 across 7, <b>and</b> a note that the count is re-derived from both DDLs by "
             "the comparison in that module rather than trusted from the comment — a total in a comment is a "
             "total nobody re-measures"),
            ("<span class='mono'>tests/test_schema_fidelity.py</span>, "
             "<span class='mono'>test_the_column_stays_text_on_purpose</span> docstring",
             "&ldquo;19 numeric columns across 8 tables&rdquo;", "both numbers, scopes named"),
            ("<span class='cite'>docs/15</span> §2, the inventory row listing &ldquo;the 11 routes&rdquo;",
             "no route serves dossiers", "annotated with a pointer to §10: the count is 13 and two of them "
             "serve <span class='mono'>dossier</span>. Left as the 8.1 inventory it is"),
            ("<span class='cite'>docs/13</span> §2.5, &ldquo;tables have no writers&rdquo;",
             "superseded for one of the three by 8.2", "superseded for <b>two</b> of the three, with "
             "<span class='mono'>memory_item</span> named as the one that is not, and D-051's deferral of "
             "F-18's columns recorded beside it"),
        ],
    )


SKEW_SERIES = [
    ("24", "<span class='mono'>7929a96</span>", "0.439", "0.300", "<b>1.46&times;</b>"),
    ("25", "<span class='mono'>7929a96</span>", "0.739", "0.294", "<b>2.51&times;</b>"),
    ("26", "<span class='mono'>ab841c7</span>", "0.238", "0.298",
     "<b>0.80&times;</b> &mdash; the smallest, and below 1"),
    ("27", "<span class='mono'>4fef432</span>", "1.089", "0.298", "<b>3.65&times;</b>"),
    ("28", "<span class='mono'>f5e6201</span>", "0.937", "0.358", "<b>2.62&times;</b>"),
    ("29", "<span class='mono'>9e70ed3</span>", "1.170", "0.295", "<b>3.97&times;</b> &mdash; the largest"),
    ("30", "<span class='mono'>11d6db3</span>", "0.385", "0.249", "<b>1.55&times;</b>"),
    ("31", "<span class='mono'>ffc4128</span>", "0.590", "0.251",
     "<b>2.35&times;</b> &mdash; CI&rsquo;s own run on this commit"),
]


def skew_table() -> str:
    return table(["Run", "Commit", "<span class='mono'>dt_observed_s</span>",
                  "<span class='mono'>dt_wall_s</span>", "skew"], SKEW_SERIES)


# ------------------------------------------------------------------ §11 the gate
def gate_table() -> str:
    return table(
        ["Check", "Command", "Result"],
        [
            ("Full suite", "<span class='mono'>.venv/bin/python -m pytest -p no:warnings</span>",
             "<b>1,258 passed / 2 skipped / 0 failed</b> &mdash; <b>+141</b> on 8.2's 1,117. Both skips are "
             "pre-existing and unrelated: the live module's egress guard and "
             "<span class='mono'>test_archive_bars.py</span>'s &ldquo;7m is not a modelled interval&rdquo;."),
            ("New: dossier writer", "<span class='mono'>pytest tests/test_dossier_writer.py</span>",
             "<b>87 tests</b> in 10 classes (682 lines)"),
            ("New: intelligence routes", "<span class='mono'>pytest tests/test_intelligence_routes.py</span>",
             "<b>39 tests</b> in 6 classes (425 lines)"),
            ("Changed: evidence writer (F-21)", "<span class='mono'>pytest tests/test_evidence_writer.py</span>",
             "<b>42</b>, was <b>27</b> &mdash; +15, one class replacing the test that pinned the defect"),
            ("Unchanged: fidelity", "<span class='mono'>pytest tests/test_schema_fidelity.py</span>",
             "<b>35</b> &mdash; no DDL moved, so no migration checksum moved and the three pinned values "
             "still hold"),
            ("Repository hygiene", "<span class='mono'>pytest tests/test_repo_hygiene.py</span>",
             "<b>83 passed</b>"),
            ("Live checks collect",
             "<span class='mono'>NEXUS_LIVE_VERIFY=1 pytest tests/test_live_endpoints.py --collect-only -q</span>",
             "<b>49</b> &mdash; unchanged, because nothing here touches ingestion"),
            ("Offline live subset",
             "<span class='mono'>-k \"DiagnosisLogic or PatienceBehaviour or TradeSideRuling or "
             "CrossEndpoint\"</span>", "<b>32 passed / 17 deselected</b>"),
            ("Lint and format", "<span class='mono'>ruff check src tests</span> &middot; "
             "<span class='mono'>ruff format --check src tests</span>",
             "clean &middot; <b>91 files already formatted</b>, was 88"),
            ("Types", "<span class='mono'>mypy</span> (strict)",
             "<b>Success: no issues found in 61 source files</b>, was 60"),
            ("Diff", "<span class='mono'>git diff --stat HEAD -- backend/</span>",
             "<b>11 files, +2,079 / &minus;24</b>"),
            ("Size", "<span class='mono'>find src -name '*.py' | xargs wc -l</span>",
             "<b>14,938</b> source lines / <b>16,074</b> test lines"),
            ("Line length", "<span class='mono'>awk 'length&gt;110'</span> on every touched file",
             "no output"),
        ],
    )


def limits_table() -> str:
    return table(
        ["#", "Limitation", "Why it is published rather than fixed here"],
        [
            ("1", "<b>Nothing calls <span class='mono'>open_dossier</span>.</b> The route serves an honest "
             "empty in every environment and says so.",
             "Deciding <i>what</i> the system should research was not this batch's ruling. The same "
             "limitation §9.7 recorded for <span class='mono'>record_evidence</span>, which still has no "
             "caller either. A test greps <span class='mono'>src/nexus</span> for callers of both, so the "
             "state cannot change silently."),
            ("2", "<b>A stance is recorded, never produced.</b> Nothing derives a stance from evidence.",
             "<span class='mono'>DecisionRecord</span> is still never constructed in "
             "<span class='mono'>src/</span> (F-17). A dossier's stance is whatever a caller passed, "
             "validated against a vocabulary and nothing more."),
            ("3", "<b><span class='mono'>sufficiency</span> is a string with no meter.</b>",
             "The basis and target are pinned and required above <span class='mono'>INSUFFICIENT</span>, but "
             "the value itself is not validated against any list, because no list exists. Stage 10 defines "
             "the meter; until then a caller can write "
             "<span class='mono'>SUFFICIENT_FOR_ANYTHING</span>."),
            ("4", "<b><span class='mono'>venue_maps_instrument</span> is a snapshot taken at open.</b>",
             "If the master later maps that venue the row still says <span class='mono'>False</span>. "
             "Nothing re-checks it, and a dossier is not re-projected when an instrument is."),
            ("5", "<b>Foreign keys are still declared and still not enforced.</b>",
             "The writer refuses a dangling parent and the database would not (§3). With the pragma off, a "
             "row written by anything other than this writer can still point at an instrument that does not "
             "exist. §9.7's limitation 2 is unchanged."),
            ("6", "<b>The checksum proves integrity, not authenticity, and nothing verifies it on a "
             "schedule.</b>",
             "F-21's fix makes the value cover the row and gives the route a recomputation, but there is no "
             "periodic audit, no alert on a <span class='mono'>False</span>, and no signature over the bytes "
             "a venue actually sent. Question 4 in §13."),
            ("7", "<b>The route reads the projection, not the chain.</b>",
             "A row the projection lost and recovery has not yet restored is invisible here. "
             "<span class='mono'>served_from</span> says so in every response, and "
             "<span class='mono'>reproject_missing</span> is what closes the gap."),
            ("8", "<b>The dossier view's nine gaps are named, not filled.</b>",
             "Two (contradictions, beliefs with validity intervals) are deferred by D-051 to stage 10; one "
             "(publication time) waits on 8.4; the other six have no ruling behind them at all and no "
             "column, and this batch added none."),
        ],
    )


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())

    html_out = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI &middot; Stage 8.3 Intelligence Memory &mdash; The Dossier Opens</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 8 of 23 &middot; sub-deliverable 8.3 &middot; authorised by
D-051 as <b>L-D + L-E only</b> &middot; <b>approved 2026-11-26 (D-052)</b></div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
A dossier can be opened at ABSTAIN, the route that serves it names nine things it cannot, and one of
Stage 8.2&rsquo;s published claims turns out to have been false</h1>
<div class="ribbon">This batch adds one module
(<span class="mono">intelligence/dossier.py</span>, 357 lines), three store members, one audited event type,
two read-only routes and <b>141 tests</b>: <b>11 files, +2,079 / &minus;24</b> in
<span class="mono">backend/</span>, gate <b>1,258 passed / 2 skipped / 0 failed</b>, mypy strict clean on
<b>61</b> files, ruff and format clean on <b>91</b>. It found and fixed <b>F-21</b> &mdash; the evidence
checksum Stage 8.2 published as &ldquo;an integrity checksum over the recorded row&rdquo; hashed the
<span class="mono">payload</span> alone, so two different rows shared one value and nine of eleven stored
fields could change undetected (&sect;9). That is a correction to an approved batch and is disclosed rather
than applied quietly. Re-reading the CI annotations for this board also falsified a second published number
&mdash; &sect;9.9&rsquo;s &ldquo;fourth measured skew and the smallest&rdquo; counted four runs where the
record held seven, and two of them are smaller (&sect;10); CI&rsquo;s own run 31 on this commit then made it
eight &mdash; so this batch carries two corrections to approved text, both as inserted pointers, and states
the series as a range rather than a count. <b>Nothing calls either writer</b>, by ruling and by design (&sect;12). No live endpoint
was called; F-14 and F-18 are untouched, both because D-051 said so.</div>

<h3>1 &middot; What D-051 authorised, and what this batch therefore did not do<span class="tag">D-051 &middot; docs/15 §10.0</span></h3>
<p>Four questions were put on the 8.2 board and all four were answered <b>Recommend</b>, each against exactly
one marked recommendation. Two of them scope this batch and two constrain it.</p>
<div class="card">{ruled_table()}</div>
<p class="cap">The three things D-051 ruled <i>out</i> are shown absent rather than merely unmentioned,
because &ldquo;we did not do it&rdquo; is the claim most easily made and least easily checked.</p>
<div class="card">{not_done_table()}</div>

<h3>2 &middot; L-E: the writer, and four decisions it makes on the record&rsquo;s behalf<span class="tag">docs/15 §10.1</span></h3>
<p>A writer&rsquo;s defaults are its politics. Everything here defaults to the ABSTAIN side, because this
package&rsquo;s own rule &mdash; written in 8.2, before a dossier existed &mdash; is that an intelligence
record which can be created without a basis is a record that will be. The id is the first spend of the
<span class="mono">CASE</span> prefix <span class="mono">core.ids.new_id</span> has declared for a research
case since Phase 2.</p>
{verbatim("CAPTURED — one open_dossier() against the real applied DDL, and the row it produces", OPEN_ROW, "after")}
<div class="card">{decisions_table()}</div>

<h3>3 &middot; L-E: fifteen refusals, and why the parent check is in the writer<span class="tag">docs/15 §10.1</span></h3>
<p>Each is a <span class="mono">ValueError</span> at an internal boundary except the last, which is the audit
log&rsquo;s own guard; none spends a <span class="mono">RejectReason</span>, for the reason 8.2 recorded. Every
one of them left the row count and the chain length unchanged &mdash; the last two lines of the capture are the
check, not decoration.</p>
{verbatim("CAPTURED — the refusals, verbatim, with the chain length before and after", REFUSALS)}
<div class="card">{refusal_table()}</div>
<p class="cap">Seven of them in full, because the message is the artefact: a refusal that does not say which
document it is obeying is a refusal the next reader will remove.</p>
{verbatim("CAPTURED — seven refusal messages in full", REFUSAL_FULL)}
<div class="blocked"><b>The parent check is in the writer because the database would not do it.</b> Migration
<span class="mono">0004_memory_fidelity</span> gave <span class="mono">dossier.instrument_id</span> its
<span class="mono">REFERENCES</span> clause back, but <span class="mono">PRAGMA foreign_keys</span> is
deliberately off (<span class="cite">store/schema.py</span>&rsquo;s module docstring: recovery re-projects in
chain order, which is not always parent-first, and a hard FK failure mid-recovery would be worse than the
inconsistency it prevents). Executed rather than assumed from the docs:</div>
{verbatim("CAPTURED — SQLite accepts the dangling parent with the pragma off, and refuses it with the pragma on", PARENT, "before")}
<p>This is what makes 8.2&rsquo;s L-B load-bearing rather than decorative. Before the seeded master was
projected there was no parent row for a dossier to point at, and the honest failure would have been silent:</p>
{verbatim("CAPTURED — the same open against a store with no projected instruments", BEFORE_PROJECTION)}
<p class="cap">The message names the id <b>and how many the store holds</b>, because &ldquo;which holds
0&rdquo; is a different failure from &ldquo;which holds 3&rdquo; and only the first says &ldquo;run the
projection&rdquo;.</p>

<h3>4 &middot; L-E: a replay reproduces the row, clock included<span class="tag">docs/15 §10.1</span></h3>
<p>The applied schema has no <span class="mono">DEFAULT now()</span> for <span class="mono">created_at</span>
or <span class="mono">updated_at</span> &mdash; two of the four defaults &sect;9.1 classifies as a house
convention &mdash; so a projection that filled them at write time would restamp a replayed event with the
replay&rsquo;s clock, and boot recovery would quietly rewrite the chronology <span class="cite">docs/10</span>
&sect;3.1 asks the view to show. Both timestamps therefore ride <b>inside</b> the audited event. Tested across
a real gap, not asserted from the design:</p>
{verbatim("CAPTURED — DELETE from three tables, wait 1.05 s, reproject from the chain", REPLAY, "after")}
<p class="cap">Fourteen refs reapplied, and the arithmetic is checked rather than assumed: the capture
opened ten dossiers (one in &sect;2, nine in &sect;5) and recorded one evidence row against the first, so 10
<span class="mono">dossier.opened</span> + 1 <span class="mono">evidence.recorded</span> + the 3
<span class="mono">instrument.registered</span> events the seed projects = 14. A control run with one dossier
and one evidence row returns <b>5</b> from the same call, and a boot chain of <b>9</b> events holds exactly
<span class="mono">migration.applied</span>&times;4, <span class="mono">boot.recovery</span>,
<span class="mono">instrument.registered</span>&times;3 and <span class="mono">api.app_created</span> &mdash;
three of them projectable, which is where the 3 comes from. The evidence row comes back with a checksum that
verifies.</p>

<h3>5 &middot; L-E: the venue flag is recorded, not refused<span class="tag">docs/15 §10.1</span></h3>
<p>A probe written to demonstrate that an invalid venue is refused found something else instead: the enum
accepts <span class="mono">MT4</span> and <span class="mono">MT5</span>, so
<span class="mono">INS-BTC-USDT</span> on <span class="mono">MT4</span> was silently accepted though the
master maps nothing of the sort. Refusing it would block legitimate gap research &mdash;
<span class="mono">INS-EUR-USD</span> on <span class="mono">OANDA</span> is a real case today and the master
maps EUR/USD at <span class="mono">DUKASCOPY</span> only &mdash; so the fact is <b>written down</b> instead.
Every seeded pair, both absent sides, and a caller trying to forge the flag:</p>
{verbatim("CAPTURED — venue_maps_instrument for all four seeded mappings and four negative cases", VENUE)}

<h3>6 &middot; L-D: the route, and the honest empty<span class="tag">docs/15 §10.2</span></h3>
<p><span class="cite">docs/15</span> &sect;6 scoped this lever as &ldquo;read-only, serving what exists and
rendering empty honestly&rdquo;, because the Intelligence Centre chrome has been reserved since D-035 with
nothing behind it. The interesting part is not that a 200 comes back. It is that an empty list explains
itself, following the distinction <span class="mono">/v1/data/coverage</span> already draws between &ldquo;no
archive&rdquo; and &ldquo;archive holds nothing&rdquo;:</p>
{verbatim("CAPTURED — GET /v1/intelligence/dossiers against a store nothing has written to", EMPTY, "before")}
<p class="cap">With one dossier open, <span class="mono">?instrument_id=INS-EUR-USD</span> answers
&ldquo;no dossier has been opened <b>for this instrument</b>&rdquo;: the empty is scoped, so a filter that
matches nothing does not read as a system that has researched nothing.
<span class="mono">vocabularies.sufficiency.values</span> is <span class="mono">None</span> on purpose &mdash;
no list of judgements exists anywhere in the repository, and inventing one to make the schema look complete is
how a string column becomes an enum nobody ruled on.</p>

<h3>7 &middot; L-D: nine gaps the route names instead of hiding<span class="tag">docs/15 §10.2 · DOSSIER_VIEW_GAPS</span></h3>
<p><span class="cite">docs/03</span> J-04 and <span class="cite">docs/10</span> &sect;3.1 fix what the dossier
view must show. Nine of those elements have no column to come from, or only partly. A route that served what it
can and stayed silent about the rest would render as complete &mdash; which is the F-13 defect class, a claim
that looks verified because nothing says otherwise. <span class="mono">view_gaps</span> is part of the
response, not a comment in the source:</p>
<div class="card">{gaps_table()}</div>
<div class="blocked"><b>And the response invents none of them.</b> A test asserts the served dossier carries no
<span class="mono">counter_thesis</span>, <span class="mono">contradictions</span>,
<span class="mono">tier</span> or <span class="mono">publication_time</span> key, because naming a gap is only
honest if the response does not also fake filling it. The column set of <span class="mono">dossier</span> is
pinned to exactly the twelve names the schema declares, so a column invented to serve one of these gaps fails
the suite.</div>

<h3>8 &middot; L-D: what a served dossier carries<span class="tag">docs/15 §10.2</span></h3>
<p>The chronology runs <b>forwards</b> while the store returns newest first, and F-14&rsquo;s two
qualifications are lifted out of the evidence payload so a reader does not have to know where 8.2 put them:</p>
{verbatim("CAPTURED — store order against route order, and every key the route serves", SERVED, "after")}
<div class="card">{route_table()}</div>
{verbatim("CAPTURED — read-only at the router, bounded, and 404 rather than an empty 200", READONLY)}
{verbatim("CAPTURED — /v1/status gained no key; the counts were already there", STATUS)}

<h3>9 &middot; F-21: the evidence checksum covered the payload, not the row<span class="tag">NEW · found and fixed here · docs/15 §10.3</span></h3>
<div class="blocked"><b>Found by this batch&rsquo;s own route probe, and it falsifies a claim Stage 8.2
published.</b> &sect;9.5 says the checksum &ldquo;is computed by the writer over exactly what is stored&rdquo;
and is &ldquo;an <b>integrity</b> checksum over the recorded row&rdquo;. It was not. Two evidence rows recorded
with different <span class="mono">source</span>, <span class="mono">observed_at</span>,
<span class="mono">retrieved_at</span> and <span class="mono">locator</span> values and no caller payload
produced the <b>same</b> checksum, so nine of the row&rsquo;s eleven stored fields could change undetected
&mdash; and <span class="mono">observed_at</span> was one of them, the field F-14 exists because of.</div>
{verbatim("CAPTURED — two rows, one checksum under 8.2; two checksums under 8.3", F21, "before")}
<div class="card">{f21_table()}</div>
<p class="cap">Tampering written straight into SQLite, past every writer, addressed by
<span class="mono">rowid</span> because tampering the primary key orphans a
<span class="mono">WHERE evidence_id = ?</span> restore:</p>
{verbatim("CAPTURED — nine fields altered and restored, plus a NULL checksum", TAMPER, "after")}
<div class="blocked"><b>Disclosure.</b> This changes what an approved batch stored. Both tables are empty in
production &mdash; &sect;9.7&rsquo;s limitation 7 records that the rebuild was proven against rows the tables do
not yet hold &mdash; so there is nothing to backfill and no stored value changes meaning under a reader. It is
disclosed here rather than applied quietly, in the same way &sect;9.2 disclosed the
<span class="mono">NUMERIC(6,5)</span> deviation, and it is put to the owner in &sect;13.
<b>No schema change and no migration checksum moved</b>: the fidelity suite still collects 35 tests and its
three pinned checksums still hold.</div>
<p class="cap">The root cause is worth more than the fix. A single-row integrity test cannot see a hash that
ignores the fields differing between rows &mdash; it needs <b>two rows differing in everything but the hashed
material</b>. And when a test&rsquo;s name and its assertion disagree, the assertion is the claim.</p>

<h3>10 &middot; Stale numbers: three copies of one count, and a skew series missing three of its seven runs<span class="tag">docs/15 §10.4</span></h3>
<p>Writing this batch&rsquo;s record required the numeric-as-TEXT count again, so it was re-derived from both
DDLs rather than copied. The result confirms &sect;9.1&rsquo;s correction and exposes three places still
carrying the wrong pairing of &ldquo;19&rdquo; with &ldquo;8 tables&rdquo;, all three written in 8.2:</p>
{verbatim("CAPTURED — the census, re-derived from migrations/*.sql against the live post-migration schema", NUMERIC, "after")}
<div class="card">{stale_table()}</div>
<div class="blocked"><b>And re-reading the CI annotations for this board falsified a number in a section
D-051 was ruled on.</b> &sect;9.9 calls run 30&rsquo;s skew &ldquo;the fourth measured skew and the smallest:
1.55&times;&rdquo;. <b>Every run from 24 onward has published both intervals</b> &mdash;
<span class="cite">docs/14</span> &sect;4.1&rsquo;s table holds runs 24&ndash;29, &sect;9.9 holds run 30, and
&sect;10.8 holds run 31, which is CI&rsquo;s own measurement of <i>this</i> commit &mdash; and <b>two of them
are smaller than 1.55&times;</b>. The count is stated as a property and not as a total on purpose: the push
that carried the correction produced an eighth pair, which is exactly the trap the record&rsquo;s own rule
names. A range does not go stale. Every pair below was re-read from its own check annotation on 2026-11-26 and the
ratio recomputed rather than copied:</div>
<div class="card">{skew_table()}</div>
<p class="cap">Run 26&rsquo;s <b>0.80&times;</b> is the smallest and sits <b>below 1</b>, which is the
bidirectionality <span class="cite">docs/14</span> &sect;4.1 already recorded; run 24&rsquo;s
<b>1.46&times;</b> is also below 1.55&times;. Two further details &sect;9.9 conflated: the
<b>3.95&times;</b> it attributes to run 29 is that run&rsquo;s <i>rate</i> ratio
(<span class="mono">bps_per_s_wall=0.557</span> against <span class="mono">bps_per_s_observed=0.141</span>),
not its interval ratio, which is 3.97&times;; and <span class="cite">docs/14</span> publishes run 27 as
&ldquo;a 3.7&times; skew&rdquo; where 1.089/0.298 = 3.65.</p>
<p><b>What survives is the conclusion, strengthened.</b> The factor spans <b>0.80&times;&ndash;3.97&times;</b>
across every run that has published both intervals, a 5.0&times; spread, and one run is below 1, so it is
bidirectional as well as non-constant:
it cannot be divided out after the fact, which is exactly the evidence D-051&rsquo;s ruling 3 rests on. A
smaller series would have supported that conclusion less well, so the ruling does not move &mdash; but the
number was wrong, and the wrong number is what &sect;9.9 published. Correction pointers are inserted in
&sect;9.9, in <span class="cite">docs/07</span>&rsquo;s 8.2 register row and on board 8.2, and every
ruled-on sentence is left intact.</p>
<p class="cap">This is the fifth instance of one defect class in this repository: a plausible number published
before anything re-measured it. The first four are the <span class="mono">ORDER BY confidence</span> claim
(&sect;9.2, three correction pointers), the <span class="mono">NUMERIC(6,5)</span> remedy execution rejected
(&sect;9.3), and F-21 itself (&sect;9). A total written in a comment is a total nobody re-measures, so the
fidelity module now says where the number comes from instead of only what it is.</p>

<h3>11 &middot; The gate<span class="tag">docs/15 §10.5</span></h3>
<p>Every number below was produced by the command beside it and re-run before being written down. <b>No live
endpoint was called by this batch.</b> CI ran on <span class="mono">ffc4128</span> anyway: three runs, all
<span class="mono">conclusion=success</span>, and the <span class="mono">pull_request</span> one carries
<span class="mono">Live public endpoints (O-009 / O-010)</span> &mdash; <b>run 31</b>: <b>44 passed / 0 failed
/ 5 geo-blocked / 0 skipped of 49</b>, <span class="mono">gap_bps=0.0</span> so both rates are
<span class="mono">0.0</span> and it yields no rate comparison, skew <b>2.35&times;</b>
(<span class="mono">dt_observed_s=0.59</span> against <span class="mono">dt_wall_s=0.251</span>),
<span class="mono">layout_flag=True</span> with 0 skips so it is live-evidenced in a seventh run, and
<span class="mono">sides=['BUY'] buy=50 sell=0</span> &mdash; a fully one-sided list passing live for the
third time and in the opposite direction to runs 24 and 25, which vindicates P-7 again. That run is
CI&rsquo;s evidence and not this batch&rsquo;s: <b>no check in those 49 exercises the dossier writer, the
route, the projection, migration 0004 or F-21&rsquo;s checksum</b> &mdash; the 1,258 offline tests do.
Recorded in <span class="cite">docs/15</span> &sect;10.8.</p>
<div class="card">{gate_table()}</div>

<h3>12 &middot; Limitations of this batch<span class="tag">docs/15 §10.6</span></h3>
<div class="card">{limits_table()}</div>

<h3>13 &middot; Decision requested &mdash; and ruled<span class="tag">docs/15 §10.7 &middot; D-052 in §10.9</span></h3>
<div class="ribbon"><b>Ruled 2026-11-26 &mdash; D-052.</b> All four questions below were answered
<span class="mono">Recommend</span>, each against exactly one marked recommendation, and the questions are left
here exactly as they were asked. <b>(1) Stage 8.3 is approved</b>, with both disclosures standing &mdash; the
F-21 correction to what an approved batch stored (&sect;9) and the skew-series correction (&sect;10) &mdash; and
the offered alternatives, bounding <span class="mono">sufficiency</span> against a list now or reworking the
checksum fix, were <b>not</b> taken, so limitation 3 stays published as written. <b>(2) 8.4 is F-14&rsquo;s
expensive half alone</b>: a real receipt time in the four adapters and nothing else &mdash; no dossier work, no
new tables, no writer wiring &mdash; with its own gate and its own live runs before and after, so a regression
is attributable to it and to nothing else; <span class="mono">O-012</span> stays <b>OPEN</b> until it lands.
<b>(3) Nothing opens a dossier or records evidence yet</b>: both writers stay unwired, the test that greps
<span class="mono">src/nexus</span> for callers keeps saying so, and the next thing built is <b>stage
10&rsquo;s <span class="mono">memory_item</span> writer</b>, which carries F-18&rsquo;s three columns and
<span class="mono">evidence_ref.contradicts</span> that D-051 deferred to exactly there. <b>(4) No periodic
checksum audit yet, but the gap is recorded as F-22</b> (&sect;14, ledger row
<span class="mono">O-014</span>) &mdash; global numbering continues, so the next id is <b>F-23</b>.</div>
<div class="ask">
<p><b>Recommendation: approve Stage 8.3 as delivered, with F-21 disclosed, and take 8.4 as F-14&rsquo;s
expensive half alone.</b> The dossier writer is what makes the intelligence layer able to hold a case, and the
route is what makes it checkable &mdash; including checkable about what it cannot yet show. Both stand on a
schema that agrees with its target, a system of record that holds the instruments, and an evidence table whose
checksum now covers the row it claims to cover.</p>
<ol>
<li><b>Is Stage 8.3 approved?</b> L-D + L-E as described, with the <b>F-21 correction to an approved batch</b>
disclosed in &sect;9 &mdash; the evidence checksum now covers nine stored fields instead of the payload alone,
which changes what <span class="mono">record_evidence</span> stores. Nothing to backfill, because both tables
are empty in production. <b>Recommendation: approve</b>, and record as <b>D-052</b>.</li>
<li><b>What is 8.4?</b> D-051 authorised F-14&rsquo;s expensive half as its own batch: a real receipt time in
<span class="mono">okx</span>, <span class="mono">bybit</span>, <span class="mono">binance_vision</span> and
<span class="mono">dukascopy</span>, which changes what <span class="mono">observed_at</span> means in every
record type and every test asserting on it. <b>Recommendation: 8.4 = F-14&rsquo;s expensive half alone</b>
&mdash; no dossier work, no new tables &mdash; because its whole value is that a regression can be attributed
to it and to nothing else. Its evidence is the measured skew series of &sect;10 &mdash; <b>every
run from 24 onward, spanning 0.80&times;&ndash;3.97&times; with one run below 1</b>, and stated as a range
because the count grows with every push &mdash; and it needs its own live runs before and after.</li>
<li><b>Should anything open a dossier yet?</b> &sect;12&rsquo;s first limitation is that nothing calls the
writer. Wiring it means deciding what the system researches, which no ruling has covered.
<b>Recommendation: not yet</b> &mdash; leave both writers unwired until the verification stages exist (stage 11
defines V1&ndash;V3), and let stage 10&rsquo;s <span class="mono">memory_item</span> writer be the next thing
built, since a dossier with no beliefs beside it is a case file with no conclusions in it.</li>
<li><b>F-21&rsquo;s verification: should it run anywhere other than on a read?</b> Today
<span class="mono">verify_evidence_checksum</span> runs when the route serves a row.
<b>Recommendation: no periodic audit yet</b>, but record the gap as a finding so it is not discovered later as
an absence &mdash; an integrity check that only runs when somebody looks cannot catch a change nobody looks at.
That finding would be <b>F-22</b>, continuing the global sequence D-051 ruled on.</li>
</ol>
</div>

<h3>14 &middot; F-22 &mdash; the finding ruling 4 opened on purpose<span class="tag">NEW · docs/15 §10.10 · ledger O-014</span></h3>
<div class="blocked"><b>Status <span class="mono">OPEN</span>, recorded by ruling rather than discovered by
accident &mdash; which is the point of it.</b> <span class="mono">verify_evidence_checksum</span> exists, is
tested against nine tampered fields and a <span class="mono">NULL</span> value, and runs in exactly one place:
<span class="mono">_dossier_view</span>, when a route serves a row. So the system can tell whether an evidence
row still matches what its writer hashed &mdash; but only if somebody asks for that row.</div>
<p>Nothing in <span class="mono">src/</span> writes <span class="mono">evidence_ref</span> except
<span class="mono">record_evidence</span>, so a change can only come from outside the application: a restored
backup, a hand-edited database file, a migration gone wrong, a disk fault, or a future writer nobody has
reviewed. <b>Every one of those happens whether or not a reader asks.</b> An integrity check that runs on read
therefore reports tampering only for rows somebody happened to request, and reports nothing at all for the
rest &mdash; including the whole table on a day nobody opens the Intelligence Centre.</p>
<p><b>What F-22 is not.</b> Not a claim that the checksum is wrong: F-21 fixed what it covers and the fix is
tested. Not a claim that a periodic audit is needed now: ruling 4 says it is not, and with both tables empty in
production there is nothing to sweep. It is the gap between those two facts, written down so that it is a known
absence rather than an unnoticed one &mdash; because an unrecorded gap is discovered later as an absence
somebody has to explain.</p>
<p><b>What would close it</b>, for whoever picks it up: a verification pass that recomputes every
<span class="mono">evidence_ref.checksum</span> outside a request &mdash; at boot, on a schedule, or inside
<span class="mono">audit/chain.py</span>&rsquo;s existing verification &mdash; <b>plus</b> a decision about where
a mismatch goes. That decision is the hard part and the reason this is not a one-line fix: a mismatch can be
reported into <span class="mono">/v1/status</span>, which the owner reads; into the audit chain, which is
append-only and cannot retract a false alarm; or into an alert channel, and D-020 fixed that set as Telegram +
Web Push + Brevo + in-app with none of them wired yet. F-22 stays open until both halves exist.</p>

<footer>Stage 8.3 &middot; L-D + L-E &middot; authorised by D-051, <b>approved as D-052</b> &middot;
11 files in <span class="mono">backend/</span>, +2,079 / &minus;24, gate <b>1,258 passed / 2 skipped / 0
failed</b> (+141 tests: dossier writer 87, routes 39, F-21 15), mypy strict clean on 61, ruff and format clean
on 91 &middot; 13 application routes, 2 of them read-only <span class="mono">GET</span>s on
<span class="mono">/v1/intelligence/dossiers</span>, writes answered 405 &middot; nine
<span class="mono">view_gaps</span> named in every response and none of them faked &middot; <b>F-21 found and
fixed</b>: the evidence checksum covered the payload, not the row &middot; F-14 and F-18 untouched, both by
ruling &middot; nothing calls either writer &middot; no live endpoint called by the batch and no migration
checksum moved &middot; CI on <span class="mono">ffc4128</span>: three runs, all <span class="mono">success</span>,
the <span class="mono">pull_request</span> one carrying <b>run 31</b> &mdash; 44/0/5/<b>0</b> of 49, skew
<b>2.35&times;</b>, <span class="mono">layout_flag=True</span>, <span class="mono">buy=50 sell=0</span>
&middot; two published numbers corrected as inserted pointers: the checksum&rsquo;s coverage (&sect;9) and the
skew series, now a <b>range</b> rather than a count (&sect;10) &middot; <b>F-22 opened by ruling 4</b>
(&sect;14, ledger <span class="mono">O-014</span>), so the next finding id is <b>F-23</b> &middot; 8.4 =
F-14&rsquo;s expensive half alone, then stage 10&rsquo;s <span class="mono">memory_item</span> writer</footer>
</div></body></html>"""
    out = HERE / "stage8-3-dossier-opened.html"
    out.write_text(html_out)
    return out


if __name__ == "__main__":
    path = main()
    print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB)")
