"""Stage 9.1 board, combined with batch B under D-056's ruling 4: the seam settled, then the writer.

Ruling 4 authorised two batches at once against **one** board while keeping the gate, the tamper proof, the
register rows and the record section **per-batch**. This is that board. Batch A (Stage 9's first
deliverable) is built and measured; batch B (8.8, F-24's confidence band) is measured and **not built**,
because two of its three shapes are migrations and F-27 established that a migration is the one artifact
this repository cannot take back. §12 holds both batches' questions so the owner rules once.

Every transcript here was captured from `backend/.venv/bin/python` runs against a database booted the way
the tests boot one — a single file holding both stores, so all six migrations apply and 0003 is not skipped
— from `pytest` runs, or from the tamper script, and embedded by the generator that built this file rather
than typed into it: a transcript that is transcribed is a transcript that can be improved. Captures:
`/tmp/cap91.py` (BLOCKS A-H), `/tmp/gate91.txt`, `/tmp/tamper91.txt`.

Two of the transcripts here are of this batch being **wrong**. §8.1 is the tamper harness reporting all 21
sites silent because `addopts` already carries `-q`, and §2.3 is a definitions scan that contradicts a
measurement this batch had already recorded. Both are on the board because a board that only shows the runs
that agreed with it is a board nobody can audit.

Run:  cd backend && .venv/bin/python ../design/build_board91.py
"""

from __future__ import annotations

import html
import pathlib

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
.no { color: var(--color-feedback-negative-text); }
.ok { color: var(--color-feedback-positive-text); }
.warn { color: var(--color-feedback-caution-text, #b26a00); }
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


def verbatim(title: str, body: str) -> str:
    return f'<div class="ba"><div class="hd">{title}</div><pre>{html.escape(body.strip())}</pre></div>'


# ---------------------------------------------------------------------------------------------
# Captures, embedded by the generator from the files named in this module's docstring.
# ---------------------------------------------------------------------------------------------
CAP91 = """\
==============================================================================
BLOCK A — the seam: three domain doors, and the six signatures
==============================================================================

SqliteOperationalStore.save_decision  —  4 statement(s)
    payload = asdict(record)
    payload['state'] = record.state.value
    payload['verb'] = record.verb.value
    self.save_decision_payload(payload, audit_ref=audit_ref)

SqliteOperationalStore.save_intent  —  3 statement(s)
    payload = asdict(intent)
    payload['digest'] = intent.digest()
    self.save_intent_payload(payload, audit_ref=audit_ref)

SqliteOperationalStore.save_approval  —  1 statement(s)
    self.save_approval_payload(asdict(approval), audit_ref=audit_ref)

  save_decision            (self, record: 'DecisionRecord', *, audit_ref: 'str | None' = None) -> 'None'
  save_decision_payload    (self, payload: 'Mapping[str, Any]', *, audit_ref: 'str | None' = None) -> 'None'
  save_intent              (self, intent: 'TradeIntent', *, audit_ref: 'str | None' = None) -> 'None'
  save_intent_payload      (self, payload: 'Mapping[str, Any]', *, audit_ref: 'str | None' = None) -> 'None'
  save_approval            (self, approval: 'ApprovalRecord', *, audit_ref: 'str | None' = None) -> 'None'
  save_approval_payload    (self, payload: 'Mapping[str, Any]', *, audit_ref: 'str | None' = None) -> 'None'

  PROJECTABLE["decision.recorded"] = 'decision'

==============================================================================
BLOCK B — the definitions scan across every class in src/ and tests/
==============================================================================
files scanned: 95
  save_decision            2   OperationalStore (operational.py), SqliteOperationalStore (operational.py)
  save_decision_payload    3   OperationalStore (operational.py), SqliteOperationalStore (operational.py), FlakyStore (test_boot_recovery.py)
  save_intent              2   OperationalStore (operational.py), SqliteOperationalStore (operational.py)
  save_intent_payload      2   OperationalStore (operational.py), SqliteOperationalStore (operational.py)
  save_approval            2   OperationalStore (operational.py), SqliteOperationalStore (operational.py)
  save_approval_payload    2   OperationalStore (operational.py), SqliteOperationalStore (operational.py)
  get_decision             2   OperationalStore (operational.py), SqliteOperationalStore (operational.py)
  FlakyStore     defines ['__getattr__', '__init__', 'save_decision_payload']  -> forwards the other 35 protocol methods via __getattr__
  HaltBlindStore defines ['__getattr__', '__init__', 'halt_events']  -> forwards the other 35 protocol methods via __getattr__

==============================================================================
BLOCK C — what thesis.py touches on the store
==============================================================================
  store attributes read: ['get_decision', 'get_evidence_ref', 'instruments']
  any of them a save_*: none
  record_thesis parameters: 16
  ThesisReceipt fields: 19
  thesis.py raise ValueError sites: 17
  thesis.py lines: 521
  parameters absent on purpose: ['intent_id', 'risk_check', 'expires_at', 'payload', 'uncertainty']

==============================================================================
BLOCK D — F-28: two producers of decision.recorded, replayed
==============================================================================
  asdict(DecisionRecord()) carries 18 fields
  DecisionRecord().to_audit_payload() carries 14 keys
  withheld but read by save_decision_payload: ['rationale', 'risk_check', 'created_at', 'updated_at']

  payload = to_audit_payload()
    first projection : rationale='' created_at=2026-11-28T11:30:42.202Z
    after replay     : rationale='' created_at=2026-11-28T11:30:43.264Z
    columns differing: 2  ['created_at', 'updated_at']

  payload = record_thesis(...)  [DEC-15971810A68D40FF-82BEG699]
    first projection : rationale='Perp basis on INS-BTC-USDT runs wide into th'... created_at=2026-11-28T11:30:43.336Z
    replayed events  : 5
    after replay     : rationale='Perp basis on INS-BTC-USDT runs wide into th'... created_at=2026-11-28T11:30:43.336Z
    columns differing: 0  (byte-identical)
    row columns: 19   intent_id=None risk_check='{}' expires_at=None

==============================================================================
BLOCK E — F-29: the protocol's single-row getters
==============================================================================
  OperationalStore declares 37 methods
    get_intent         declared: True
    get_decision       declared: True
    get_dossier        declared: True
    get_evidence_ref   declared: True
    get_memory_item    declared: True
  __protocol_attrs__ on this interpreter: 0 (empty on 3.11, which is why the test reads the source)

==============================================================================
BLOCK F — the verb and state partitions
==============================================================================
  DecisionVerb  : 7 members
    permitted 4: ['ABSTAIN', 'REJECT', 'WAIT', 'ESCALATE']
    refused   3: ['ACCEPT', 'REDUCE', 'EXIT']
    partition exact: True
  DecisionState : 12 members
    permitted 6: ['PROPOSED', 'WAITING_DATA', 'REJECTED', 'CANCELLED', 'ABSTAINED', 'FAILED']
    refused   6: ['WAITING_APPROVAL', 'APPROVED', 'REDUCED', 'EXECUTED', 'PARTIALLY_EXECUTED', 'EXPIRED']
    partition exact: True

  refusals, each with its own message:
    verb=ACCEPT   verb=ACCEPT is refused at Stage 9: ACCEPT is the verb by which intelligence reaches execution, a...
    verb=REDUCE   verb=REDUCE is refused at Stage 9: REDUCE proposes a smaller size, and sizing is the risk engine...
    verb=EXIT     verb=EXIT is refused at Stage 9: EXIT closes an open position, and nothing is open — this writer...
    state=APPROVED  state=APPROVED is refused at Stage 9. Five of the six gated states are past A-08's three gates ...
    state=EXPIRED   state=EXPIRED is refused at Stage 9. Five of the six gated states are past A-08's three gates o...

==============================================================================
BLOCK G — F-30: where the stage map's 'uncertainty' could live
==============================================================================
  decision       19 cols  uncertainty=False payload=False TEXT cols=['decision_id', 'created_at', 'updated_at', 'state', 'verb', 'instrument_id', 'venue', 'strategy_id', 'model_id', 'horizon', 'confidence', 'rationale', 'reason_codes', 'evidence_refs', 'counter_evidence_refs', 'intent_id', 'risk_check', 'expires_at', 'audit_ref']
  dossier        12 cols  uncertainty=True  payload=True  TEXT cols=['dossier_id', 'instrument_id', 'venue', 'created_at', 'updated_at', 'state', 'summary', 'stance', 'uncertainty', 'sufficiency', 'payload', 'audit_ref']
  trade_intent   30 cols  uncertainty=False payload=True  TEXT cols=['intent_id', 'decision_id', 'created_at', 'expires_at', 'environment', 'instrument_id', 'venue', 'account_id', 'side', 'order_type', 'quantity', 'limit_price', 'stop_price', 'protective_stop', 'take_profit', 'time_in_force', 'quote_currency', 'max_loss_usd', 'estimated_cost_usd', 'strategy_id', 'model_id', 'evidence_summary', 'counter_case', 'exit_plan', 'idempotency_key', 'digest', 'payload', 'audit_ref']

  build_board52.py:73 asks for: ("Candidate thesis", "intelligence dossier (stage 9) · evidence set + uncertainty · ABSTAIN is the default record"),

==============================================================================
BLOCK H — batch B measured: which band shape is more expressive
==============================================================================
  confidence_text is memory_item's NUMERIC(6,5) boundary check; decision.confidence declares the same
    migrations/0001_core.sql:112 -> confidence    NUMERIC(6, 5),
    0.3      -> ACCEPTED 0.3
    1.1      -> ACCEPTED 1.1
    0.7      -> ACCEPTED 0.7
    0.4      -> ACCEPTED 0.4
    -0.4     -> ACCEPTED -0.4
    0.2      -> ACCEPTED 0.2
    -9.9     -> ACCEPTED -9.9
    9.9      -> ACCEPTED 9.9
    19.8     -> REFUSED
    10       -> REFUSED
    1e-6     -> REFUSED
    -0.1     -> ACCEPTED -0.1
    0.6      -> ACCEPTED 0.6

  shape (a) confidence_low + confidence_high:
    0.7 +/- 0.4   -> low=0.3 high=1.1   expressible
    -9.9 ... 9.9  -> low=-9.9 high=9.9  expressible (19.8 across)
  shape (b) confidence + confidence_width:
    0.7 +/- 0.4   -> value=0.7 width=0.4   expressible
    -9.9 ... 9.9  -> width 19.8 REFUSED: 2 digits before the decimal point
  what a band would touch:
    memory_item columns 15 | record_memory_item params 15 | MemoryReceipt fields 17
"""
GATE91 = """\
### gate: pytest

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1527 passed, 2 skipped, 1 warning in 43.12s

### gate: ruff check src tests
All checks passed!

### gate: ruff format --check src tests
95 files already formatted

### gate: mypy src/nexus
Success: no issues found in 63 source files

### tree
src: 63 files, 16903 lines
tests: 32 files, 20843 lines
"""
TAMPER91 = """\
baseline: 1527 passed, 0 failed
  T01 ACCEPT refusal removed                                 CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheGatedVerbsAreRefusedSeparately:
  T02 REDUCE refusal removed                                 CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheGatedVerbsAreRefusedSeparately:
  T03 EXIT refusal removed                                   CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheGatedVerbsAreRefusedSeparately:
  T04 gated-state refusal removed                            CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheGatedStatesAreRefused::test_the
  T05 rationale no longer required                           CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestAbstainIsTheDefaultRecordAndNotAFa
  T06 ABSTAIN needs no reason code                           CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestAbstainIsTheDefaultRecordAndNotAFa
  T07 dangling instrument accepted                           CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheParentGuardsAreInTheWriter::tes
  T08 empty instrument_id accepted                           CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheParentGuardsAreInTheWriter::tes
  T08b empty citation accepted                               CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheParentGuardsAreInTheWriter::tes
  T09 dangling evidence accepted                             CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheParentGuardsAreInTheWriter::tes
  T10 one source on both sides accepted                      CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheParentGuardsAreInTheWriter::tes
  T11 venue no longer validated                              CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheParentGuardsAreInTheWriter::tes
  T12 F-28's remedy: created_at dropped from the event       CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestThePayloadCarriesWhatTheProjection
  T13 rationale dropped from the event                       CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestThePayloadCarriesWhatTheProjection
  T14 an existing decision_id may be re-recorded             CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheParentGuardsAreInTheWriter::tes
  T15 the NUMERIC(6,5) boundary check bypassed               CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestConfidenceIsAnInputAndNeverAGate::
  T16 intent_id becomes a parameter                          CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheColumnsThisWriterIsNotRuledInto
  T17 F-29 undone: get_decision undeclared on the protocol   CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheSeamIsSettledAndNothingMoved::t
  T18 the writer writes the store directly                   CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheSeamIsSettledAndNothingMoved::t
  T20 an empty reason code accepted                          CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheParentGuardsAreInTheWriter::tes
  T21 intent_id dropped from the event                       CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestThePayloadCarriesWhatTheProjection
  T19 the three verb refusals folded into one reason         CAUGHT (1 failed) FAILED tests/test_thesis_writer.py::TestTheGatedVerbsAreRefusedSeparately:

sites: 22   caught: 22   silent: 0
restore verified (SHA-256 identical to pre-sweep): True
post-sweep baseline: 1527 passed, 0 failed
"""


def block(letter: str) -> str:
    """One BLOCK from the capture file, split on the rule lines the capture script printed."""
    marker = f"BLOCK {letter} —"
    start = CAP91.index(marker)
    start = CAP91.rindex("=" * 78, 0, start)
    rest = CAP91[start + len("=" * 78) + len(marker) :]
    end = rest.find("=" * 78)
    tail = rest[end:] if end != -1 else ""
    nxt = tail.find("BLOCK")
    stop = (end + nxt) if nxt != -1 else len(rest)
    return rest[:stop].rstrip().rstrip("=" * 78).rstrip()


# ---------------------------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------------------------
def cadence_table() -> str:
    return table(
        ["Per-batch, as ruling 4 requires", "Batch A — Stage 9.1", "Batch B — 8.8"],
        [
            ("Delivered", "<b>yes</b> — <span class='mono'>thesis.py</span> 521 lines, "
                          "<span class='mono'>test_thesis_writer.py</span> 986 lines and 99 tests",
             "<b class='no'>no</b> — measured in §11, blocked on question 2"),
            ("Gate", "<b>1,527</b> passed / <b>2</b> skipped / <b>0</b> failed",
             "shares the gate; contributes no test of its own"),
            ("Tamper proof", "<b>22</b> sites / <b>22</b> caught / <b>0</b> silent", "none — nothing to reverse"),
            ("Register rows", "<b>3</b> rows in <span class='mono'>docs/07</span>", "<b>0</b> — no deliverable"),
            ("Record section", "<span class='mono'>docs/16</span>, a new document",
             "<span class='mono'>docs/16</span> §10, inside batch A's document and labelled as batch B's"),
            ("Migration", "<b class='ok'>none</b> — <span class='mono'>MIGRATIONS</span> stays at 6, "
                          "no checksum moves", "<b class='warn'>2 of 3 shapes are one</b>"),
            ("Findings", "F-26 answered, F-28 found, F-29 <b>closed</b>, F-30 found", "F-24, unchanged"),
        ],
    )


def door_table() -> str:
    return table(
        ["domain door", "statements", "what it does before delegating", "payload door"],
        [
            ("<span class='mono'>save_decision</span>", "<b>4</b>",
             "<span class='mono'>asdict(record)</span>, then <span class='mono'>state</span> and "
             "<span class='mono'>verb</span> as <span class='mono'>.value</span>",
             "<span class='mono'>save_decision_payload</span>"),
            ("<span class='mono'>save_intent</span>", "<b>3</b>",
             "<span class='mono'>asdict(intent)</span>, then <span class='mono'>digest</span>",
             "<span class='mono'>save_intent_payload</span>"),
            ("<span class='mono'>save_approval</span>", "<b>1</b>",
             "inlines <span class='mono'>asdict(approval)</span> into the call itself",
             "<span class='mono'>save_approval_payload</span>"),
        ],
    )


def fk_table() -> str:
    return table(
        ["declared foreign key", "written by", "guarded in a writer?", "since"],
        [
            ("<span class='mono'>decision.instrument_id &rarr; instrument</span>",
             "<b><span class='mono'>thesis.py</span></b> — this batch",
             "<b class='ok'>yes</b> — <span class='mono'>_resolve_instrument</span> against "
             "<span class='mono'>store.instruments()</span>", "<b>9.1</b>"),
            ("<span class='mono'>trade_intent.decision_id &rarr; decision</span>", "nothing",
             "<b class='no'>no writer exists</b>", "&mdash;"),
            ("<span class='mono'>approval.intent_id &rarr; trade_intent</span>", "nothing",
             "<b class='no'>no writer exists</b>", "&mdash;"),
            ("<span class='mono'>orders.intent_id &rarr; trade_intent</span>",
             "projection only, <span class='mono'>operational.py:734</span>",
             "<b class='warn'>upstream</b>, in whatever emits <span class='mono'>order.state</span>", "&mdash;"),
            ("<span class='mono'>fills.order_id &rarr; orders</span>",
             "projection only, <span class='mono'>operational.py:826</span>",
             "<b class='warn'>upstream</b>, in whatever emits <span class='mono'>fill.recorded</span>", "&mdash;"),
        ],
    )


def f28_table() -> str:
    return table(
        ["payload written through <span class='mono'>write_with_audit</span>", "keys",
         "<span class='mono'>rationale</span> lands", "columns differing after replay"],
        [
            ("<span class='mono'>asdict(record)</span>, via <span class='mono'>save_decision</span>",
             "<b>18</b>", "<b class='ok'>yes</b>", "not reachable — the domain door does not audit"),
            ("<span class='mono'>DecisionRecord.to_audit_payload()</span>", "<b>14</b>",
             "<b class='no'>no &mdash; projects <span class='mono'>''</span></b>",
             "<b class='no'>2</b> — <span class='mono'>created_at</span>, <span class='mono'>updated_at</span>"),
            ("<b><span class='mono'>record_thesis(...)</span></b> — this batch", "<b>19</b> of 19 columns",
             "<b class='ok'>yes</b>", "<b class='ok'>0 &mdash; byte-identical</b>"),
        ],
    )


def verb_table() -> str:
    return table(
        ["verb", "Stage 9", "the reason, which is not shared with the others"],
        [
            ("<span class='mono'>ABSTAIN</span>", "<b class='ok'>permitted</b> — the default",
             "<span class='mono'>build_board52.py:73</span> makes it the default record and P-2's failure "
             "text makes it &ldquo;a complete outcome, not an error state&rdquo;"),
            ("<span class='mono'>REJECT</span>", "<b class='ok'>permitted</b>",
             "a proposal about research; reaches no gate"),
            ("<span class='mono'>WAIT</span>", "<b class='ok'>permitted</b>",
             "a proposal about research; reaches no gate"),
            ("<span class='mono'>ESCALATE</span>", "<b class='ok'>permitted</b>",
             "asks the owner, which is not execution"),
            ("<span class='mono'>ACCEPT</span>", "<b class='no'>refused</b>",
             "<b>A-08</b> — ACCEPT is the verb by which intelligence reaches execution, and "
             "<span class='mono'>docs/10</span> §3.2 puts the three gates' definitions at Stage 11"),
            ("<span class='mono'>REDUCE</span>", "<b class='no'>refused</b>",
             "<b>A-02</b> — sizing is the risk engine's; <span class='mono'>DecisionState.REDUCED</span>'s "
             "own comment is &ldquo;risk engine cut size to fit limits&rdquo;, and P-2's law keeps model I/O "
             "out of it"),
            ("<span class='mono'>EXIT</span>", "<b class='no'>refused</b>",
             "<b>nothing is open</b> — EXIT closes a position, this writer writes no "
             "<span class='mono'>trade_intent</span> row, and A-08 is why"),
        ],
    )


def state_table() -> str:
    return table(
        ["state", "Stage 9", "why"],
        [
            ("<span class='mono'>PROPOSED</span>", "<b class='ok'>permitted</b> — the default", "a proposal"),
            ("<span class='mono'>WAITING_DATA</span>", "<b class='ok'>permitted</b>", "evidence insufficient"),
            ("<span class='mono'>REJECTED</span>", "<b class='ok'>permitted</b>", "pairs with verb=REJECT"),
            ("<span class='mono'>CANCELLED</span>", "<b class='ok'>permitted</b>", "withdrawn by its author"),
            ("<span class='mono'>ABSTAINED</span>", "<b class='ok'>permitted</b>", "a complete outcome"),
            ("<span class='mono'>FAILED</span>", "<b class='ok'>permitted</b>", "the thesis could not be formed"),
            ("<span class='mono'>WAITING_APPROVAL</span>", "<b class='no'>refused</b>", "past A-08's gates"),
            ("<span class='mono'>APPROVED</span>", "<b class='no'>refused</b>", "past A-08's gates"),
            ("<span class='mono'>REDUCED</span>", "<b class='no'>refused</b>", "the risk engine's own outcome"),
            ("<span class='mono'>EXECUTED</span>", "<b class='no'>refused</b>", "past A-08's gates"),
            ("<span class='mono'>PARTIALLY_EXECUTED</span>", "<b class='no'>refused</b>", "past A-08's gates"),
            ("<span class='mono'>EXPIRED</span>", "<b class='no'>refused</b>",
             "<b>a different reason, with its own sentence</b> — it needs an expiry reader, and 8.7 added "
             "<span class='mono'>memory_item.expires_at</span> with none and published it as inert"),
        ],
    )


def f30_table() -> str:
    return table(
        ["table", "columns", "<span class='mono'>uncertainty</span>",
         "<span class='mono'>payload</span>", "what a band of prose could ride in"],
        [
            ("<b><span class='mono'>decision</span></b>", "<b>19</b>", "<b class='no'>no</b>",
             "<b class='no'>no</b>",
             "<span class='mono'>rationale</span> only — <span class='mono'>risk_check</span> is the risk "
             "engine's, and A-02 keeps intelligence out of it"),
            ("<span class='mono'>dossier</span>", "12", "<b class='ok'>yes</b>", "<b class='ok'>yes</b>",
             "both, and 8.3 pinned two keys into the payload"),
            ("<span class='mono'>trade_intent</span>", "30", "<b class='no'>no</b>", "<b class='ok'>yes</b>",
             "<span class='mono'>payload</span>, <span class='mono'>evidence_summary</span>, "
             "<span class='mono'>counter_case</span>"),
        ],
    )


def gate_table() -> str:
    return table(
        ["", "before 9.1 (at 8.7)", "after 9.1"],
        [
            ("gate", "1,428 passed / 2 skipped / 0 failed", "<b>1,527</b> passed / <b>2</b> skipped / <b>0</b> failed"),
            ("<span class='mono'>ruff check src tests</span>", "clean", "clean"),
            ("<span class='mono'>ruff format</span>", "93 files", "<b>95</b> files"),
            ("<span class='mono'>mypy src/nexus</span> strict", "62 files", "<b>63</b> files"),
            ("<span class='mono'>src</span>", "62 files / 16,347 lines", "<b>63</b> files / <b>16,903</b> lines"),
            ("<span class='mono'>tests</span>", "31 files / 19,857 lines", "<b>32</b> files / <b>20,843</b> lines"),
            ("<span class='mono'>OperationalStore</span> declared methods", "36", "<b>37</b> — F-29"),
            ("writers in <span class='mono'>intelligence/</span>", "3", "<b>4</b> — plus <span class='mono'>decision</span>"),
            ("<span class='mono'>MIGRATIONS</span>", "6", "<b class='ok'>6 — unchanged</b>"),
            ("checksums", "&mdash;", "<b class='ok'>none moved</b>"),
        ],
    )


def tamper_table() -> str:
    return table(
        ["sites", "what is reversed", "caught by"],
        [
            ("<b>T01&ndash;T03</b>", "the ACCEPT / REDUCE / EXIT refusal removed",
             "<span class='mono'>TestTheGatedVerbsAreRefusedSeparately</span>"),
            ("<b>T04</b>", "the gated-state refusal removed", "<span class='mono'>TestTheGatedStatesAreRefused</span>"),
            ("<b>T05, T06</b>", "<span class='mono'>rationale</span> no longer required; ABSTAIN needs no code",
             "<span class='mono'>TestAbstainIsTheDefaultRecordAndNotAFallback</span>"),
            ("<b>T07&ndash;T11</b>", "dangling instrument; empty instrument; dangling citation; empty "
                                    "citation; unvalidated venue",
             "<span class='mono'>TestTheParentGuardsAreInTheWriter</span>"),
            ("<b>T12, T13</b>", "<b>F-28's remedy undone</b> — <span class='mono'>created_at</span> dropped "
                                "from the event; <span class='mono'>rationale</span> emptied",
             "<span class='mono'>TestThePayloadCarriesWhatTheProjectionReads</span>"),
            ("<b>T14</b>", "an existing <span class='mono'>decision_id</span> may be re-recorded",
             "<span class='mono'>TestTheParentGuardsAreInTheWriter</span>"),
            ("<b>T15</b>", "the <span class='mono'>NUMERIC(6,5)</span> boundary check bypassed",
             "<span class='mono'>TestConfidenceIsAnInputAndNeverAGate</span>"),
            ("<b>T16, T21</b>", "<span class='mono'>intent_id</span> becomes a parameter; "
                                "<span class='mono'>intent_id</span> dropped from the event",
             "<span class='mono'>TestTheColumnsThisWriterIsNotRuledInto</span> and <span class='mono'>&hellip;PayloadCarries&hellip;</span>"),
            ("<b>T17</b>", "<b>F-29 undone</b> — <span class='mono'>get_decision</span> undeclared on the protocol",
             "<span class='mono'>TestTheSeamIsSettledAndNothingMoved</span>"),
            ("<b>T18</b>", "the writer writes the store directly",
             "<span class='mono'>TestTheSeamIsSettledAndNothingMoved</span>"),
            ("<b>T19</b>", "the three verb refusals folded into one shared reason",
             "<span class='mono'>TestTheGatedVerbsAreRefusedSeparately</span>"),
            ("<b>T20</b>", "an empty reason code accepted", "<span class='mono'>TestTheParentGuardsAreInTheWriter</span>"),
        ],
    )


def limitation_table() -> str:
    return table(
        ["#", "limitation, published beside the delivery"],
        [
            ("1", "A dangling instrument is <b>still representable and still storable</b>. "
                  "<span class='mono'>record_thesis</span> refuses one; "
                  "<span class='mono'>store.save_decision(record)</span> accepts one, because the store is a "
                  "projection and <span class='mono'>PRAGMA foreign_keys</span> is off. "
                  "<span class='mono'>docs/15</span> §13.7 limitation 3 stands."),
            ("2", "<b>Four of the five keys F-26 named are still unguarded by any writer</b>, and three have "
                  "no writer at all. Closing F-26 on <span class='mono'>decision.instrument_id</span> does "
                  "not close it on the trading path."),
            ("3", "<b>The uncertainty a thesis carries is a reason code, which is a label.</b> Nothing in the "
                  "row states what is unresolved, and no test can assert what a column cannot hold."),
            ("4", "<span class='mono'>decision.confidence</span>'s <b>&ldquo;0..1, calibrated&rdquo; comment "
                  "is unenforced</b> on both tables, and D-054's unbounded ruling was made about "
                  "<span class='mono'>memory_item</span> and has not been re-made about "
                  "<span class='mono'>decision</span>."),
            ("5", "<b>The verb and state boundaries are a derivation from five sources, not a quotation from "
                  "any one of them.</b> No document says &ldquo;Stage 9 may carry these four verbs&rdquo;. "
                  "The sets are pinned and enumerated so the derivation can be argued with — question 1."),
            ("6", "<span class='mono'>risk_check</span> stays <span class='mono'>'{}'</span> for every thesis, "
                  "so it is as inert on <span class='mono'>decision</span> as "
                  "<span class='mono'>expires_at</span> is on <span class='mono'>memory_item</span> — with the "
                  "difference that A-02 says it <b>should</b> stay empty until the risk engine writes it."),
            ("7", "<span class='mono'>thesis.py</span> is <b>not wired</b>, so nothing in a running system "
                  "produces a thesis. The row this batch can write is a row nothing yet asks for."),
            ("8", "<span class='mono'>FlakyStore</span> and <span class='mono'>HaltBlindStore</span> conform "
                  "<b>by forwarding</b>, which is why F-29 broke nothing. That is a property of those two "
                  "wrappers and not of the suite: a future fake that enumerated the protocol would need "
                  "updating, and nothing would say so offline."),
        ],
    )


def finding_table() -> str:
    return table(
        ["id", "status", "batch", "one line"],
        [
            ("<b>F-24</b>", "<span class='mono'>OPEN</span>", "<b>8.8 — batch B</b>",
             "the confidence band; shape un-ruled, measured in §11"),
            ("<b>F-26</b>", "<span class='mono'>OPEN</span>", "none",
             "<b>answered and due <span class='mono'>CORRECTED</span></b>, not closed. Residue: the domain "
             "object stays unvalidated, and four of the five keys it named are still unguarded"),
            ("<b>F-27</b>", "<span class='mono'>OPEN</span>", "none",
             "<span class='mono'>Migration.statements</span> counts prose semicolons; the inflated counts "
             "stay pinned at 0003&nbsp;&rarr;&nbsp;4 and 0004&nbsp;&rarr;&nbsp;15"),
            ("<b>F-28</b>", "<span class='mono'>OPEN</span> — <b>new</b>", "none",
             "<span class='mono'>decision.recorded</span>'s two producers disagree; the fourteen-key one "
             "cannot reproduce its own row, and the omission it turns on is <b>pinned by a test</b>"),
            ("<b>F-29</b>", "<b class='ok'><span class='mono'>CLOSED</span></b> — <b>new</b>", "<b>9.1</b>",
             "<span class='mono'>get_decision</span> was the one single-row getter the protocol never "
             "declared; declared here, 36&nbsp;&rarr;&nbsp;37, moving no signature"),
            ("<b>F-30</b>", "<span class='mono'>OPEN</span> — <b>new</b>", "none",
             "<span class='mono'>decision</span> has no <span class='mono'>uncertainty</span> and no "
             "<span class='mono'>payload</span> column, so the stage map's own ask for Stage 9 cannot be "
             "stored — and every remedy is a migration"),
            ("F-18", "<span class='mono'>NARROWED</span>", "none",
             "gaps 1&ndash;3 closed; gap 4, the sufficiency meter, alone open and stage 10's by "
             "<span class='mono'>docs/12</span> §1.3"),
            ("F-22 / <span class='mono'>O-014</span>, F-17, F-19", "<span class='mono'>OPEN</span>", "none",
             "unchanged"),
        ],
    )


def band_table() -> str:
    return table(
        ["band", "(a) <span class='mono'>confidence_low</span> + <span class='mono'>confidence_high</span>",
         "(b) <span class='mono'>confidence</span> + <span class='mono'>confidence_width</span>",
         "(c) a distribution in <span class='mono'>payload</span>"],
        [
            ("<span class='mono'>0.7 &plusmn; 0.4</span>", "<b class='ok'>0.3 and 1.1 &mdash; both store</b>",
             "<b class='ok'>0.7 and 0.4 &mdash; both store</b>", "unconstrained"),
            ("<span class='mono'>-0.4 &hellip; 0.2</span>", "<b class='ok'>both store</b>",
             "<b class='ok'>-0.1 and 0.6 &mdash; both store</b>", "unconstrained"),
            ("<span class='mono'>-9.9 &hellip; 9.9</span> (19.8 across)", "<b class='ok'>both store</b>",
             "<b class='no'>width 19.8 REFUSED</b> — 2 digits before the decimal point", "unconstrained"),
            ("columns added by a migration", "<b>2</b>", "<b>1</b>", "<b>0</b>"),
            ("a second ruling needed", "<b class='ok'>no</b>",
             "<b class='no'>yes</b> — is <span class='mono'>width</span> a half-width or a full width?",
             "<b class='no'>yes</b> — what may a distribution claim?"),
            ("what happens to <span class='mono'>confidence</span>",
             "<b class='warn'>redundant, or the midpoint &mdash; a third question nobody has asked</b>",
             "<b class='ok'>keeps its meaning</b>", "<b class='ok'>keeps its meaning</b>"),
            ("constrainable by a reader", "<b class='ok'>yes</b>", "<b class='ok'>yes</b>",
             "<b class='no'>no</b> — nothing can bound a JSON blob"),
        ],
    )


def ruling_table() -> str:
    """The four questions **as put**. Deliberately a separate function from any table that records what was
    ruled — `build_board87.py` keeps the two apart for the same reason, because one helper serving both
    would let a ruling silently rewrite the question it answered."""
    return table(
        ["#", "question", "options", "recommendation, and what it rests on"],
        [
            ("1", "<b>Batch A &mdash; is the verb and state boundary right?</b> Four verbs and six states "
                  "permitted, three and six refused, derived in §5 from five approved sources and quoted by "
                  "none of them.",
             "(a) approve as built &middot; (b) the full seven-word vocabulary and all twelve states now "
             "&middot; (c) ABSTAIN and PROPOSED only, everything else refused",
             "<b>(a)</b>. The refusals are fail-closed, which is A-02's own posture, and widening later is "
             "additive while narrowing after a row exists is not — the same asymmetry F-27 made "
             "irreversible. (b) would let intelligence ACCEPT before the gates that A-08 requires exist; "
             "(c) would refuse REJECT, WAIT and ESCALATE, which reach no gate and which "
             "<span class='mono'>docs/10</span> §3.1's decision-state strip already carries."),
            ("2", "<b>Batch B &mdash; which shape is the confidence band?</b> F-24, and the one thing "
                  "<span class='mono'>migrations/0002_memory.sql</span>'s header names as deliberately "
                  "absent since 8.7. D-054's unbounded confidence and 8.5's ordering precedent are "
                  "<b>applied, not re-asked</b>.",
             "(a) two columns, <span class='mono'>confidence_low</span> + "
             "<span class='mono'>confidence_high</span> &middot; (b) one column, "
             "<span class='mono'>confidence_width</span> &middot; (c) a distribution in "
             "<span class='mono'>payload</span>, no migration",
             "<b>(a)</b>, on §11's measurement: a <i>width</i> is a magnitude, so it inherits "
             "<span class='mono'>NUMERIC(6,5)</span>'s one-digit ceiling even though confidence itself is "
             "unbounded, and a band wider than <span class='mono'>9.99999</span> becomes unrepresentable "
             "while its two endpoints are not. (a) is strictly more expressive under the target that "
             "already exists and needs no second ruling. (c) is the only shape with no migration, and is "
             "offered for that reason alone."),
            ("3", "<b>Batch A &mdash; what becomes of <span class='mono'>DecisionRecord</span>?</b> Two "
                  "descriptions of one decision now exist: an 18-field dataclass nothing in "
                  "<span class='mono'>src/</span> constructs, and a 19-column row written by a function "
                  "that never mentions the dataclass. F-28 is the visible edge of that.",
             "(a) leave both, record the divergence beside F-28 &middot; (b) make "
             "<span class='mono'>record_thesis</span> build and return a "
             "<span class='mono'>DecisionRecord</span> &middot; (c) retire the dataclass",
             "<b>(a)</b>. A reader does not exist yet, and choosing now would be choosing for it. (b) would "
             "put a domain object in the receipt and invite the next writer to audit "
             "<span class='mono'>to_audit_payload()</span>, which is F-28; (c) would delete a Phase-2 type "
             "five tests construct, inside a batch whose scope a ruling named."),
            ("4", "<b>What runs next under ruling 4's cadence?</b> Two batches at a time, one board.",
             "(a) stage 10 — knowledge sufficiency &middot; (b) the expiry reader, making "
             "<span class='mono'>expires_at</span> do something &middot; (c) F-27, making the recorded "
             "statement count honest &middot; (d) F-30's column, if question 2's answer wants it first",
             "<b>(a)</b>. Stage 10 is <b>three</b> recorded items in one batch: it is the stage map's step 2, "
             "it is F-18's gap 4 (the sufficiency meter), and it is two of the nine "
             "<span class='mono'>DOSSIER_VIEW_GAPS</span> D-051 deferred to it by name. (b) is the "
             "alternative if the owner would rather make an inert column do something than add a meter — "
             "it retires <span class='mono'>docs/15</span> §14.8 limitation 1, which D-056's ruling 1 left "
             "standing."),
        ],
    )


def main() -> pathlib.Path:
    stage_map = (
        'P2 = [\n'
        '    ("Candidate thesis", "intelligence dossier (stage 9) · evidence set + uncertainty · ABSTAIN is the default record"),\n'
        '    ("Knowledge sufficiency", "stage 10 · does the dossier meet the sufficiency bar for this instrument/session? planned"),\n'
        '    ("Verification gates", "stage 11 · three gates between thesis and execution (A-08) · planned"),\n'
        ']\n'
        'P2_FAIL = ("no gate can be satisfied by a confidence value — confidence is an input the risk "\n'
        '           "engine may ignore; a missing input denies; an expired or changed intent invalidates "\n'
        '           "the approval and re-asks (4.1 friction ladder); ABSTAIN is a complete outcome, not an "\n'
        '           "error state.")\n'
        'P2_LAW = ("Law (A-02 + A-08): the path from intelligence to execution passes every gate in order "\n'
        '          "and the risk engine sees no model I/O. Steps 2–3 are planned and drawn dashed in the "\n'
        '          "diagram until Stage 11 delivers them.")'
    )
    adrs = (
        "docs/12 §1.3\n\n"
        "A-02 risk-engine isolation as architectural law: deterministic, fail-closed on missing inputs,\n"
        "confidence never a satisfied requirement — existing, formalised.\n"
        "A-08 intelligence reaches execution only through the verification engine's three gates; no agent\n"
        "holds an execution credential — new law."
    )
    gap9 = (
        "app.py, DOSSIER_VIEW_GAPS — 9 elements; element 9 verbatim:\n\n"
        "· disposition with reason code\n"
        "    asked_by       docs/10 §3.1\n"
        "    why_not_servable the disposition is served as stance, but dossier has no reason-code column.\n"
        "                     Reason codes live on DecisionRecord, and a dossier is not a decision.\n"
        "    deferred_by    None\n\n"
        "record_thesis now writes reason codes onto a DecisionRecord, so this element's cause is unchanged\n"
        "and its remedy is now reachable. Not built, not wired, not claimed."
    )
    band_header = (
        "migrations/0002_memory.sql:29 — the band, in the schema's own words\n\n"
        "-- confidence band: `confidence` stays one NUMERIC(6,5) point, while `docs/10` §3.1 asks for it \"as\n"
        "-- a band with validity interval and change conditions; a point estimate without them is a defect\"."
    )
    pinned = (
        "tests/test_core_guarantees.py:498 — why F-28 cannot simply be fixed\n\n"
        "    def test_audit_payload_has_no_free_text_model_output(self) -> None:\n"
        "        record = DecisionRecord(rationale=\"long narrative from the model\", confidence=0.42)\n"
        "        payload = record.to_audit_payload()\n"
        "        assert \"rationale\" not in payload\n"
        "        assert payload[\"confidence\"] == 0.42\n"
        "        assert payload[\"decision_id\"].startswith(\"DEC-\")"
    )
    remedy = (
        "src/nexus/intelligence/memory.py:456 — the remedy, already written down where the first writer\n"
        "learned it, and carried by thesis.py verbatim\n\n"
        "    # The timestamp rides in the event, so a replay reproduces the row it first wrote instead of\n"
        "    # restamping it with the replay's clock.\n"
        "    now = iso_utc(utc_now())"
    )
    f26 = (
        "docs/15 §13 — F-26 as recorded, the question this batch answers\n\n"
        "either those writers gain a store in the seam so a parent can be checked before a row is written,\n"
        "or the trading path accepts that its parents are checked upstream in whatever produces a\n"
        "DecisionRecord and says so in a document instead of leaving it to be inferred from five unguarded\n"
        "REFERENCES clauses."
    )

    parts: list[str] = []
    add = parts.append

    add("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>NEXUS &middot; Stage 9.1 &mdash; the candidate thesis, and the seam settled first</title>"
        f"<style>{fonts_css()}{CSS}</style></head><body><div class='page'>")

    add("<header class='page-head'><p class='eyebrow'>Stage 9 &middot; sub-deliverable 9.1 &middot; "
        "batch A of two &middot; combined board per D-056 ruling 4</p>"
        "<h1>The candidate thesis: the seam settled before the writer that needed it</h1>"
        "<p class='lede'><span class='mono'>decision</span> was built in Stage 6 with nineteen columns and "
        "never written to. <span class='mono'>PROJECTABLE</span> has carried "
        "<span class='mono'>&quot;decision.recorded&quot;: &quot;decision&quot;</span> since the write-ahead "
        "path was built and nothing ever emitted the event &mdash; a projection looking for a producer for "
        "eight stages. D-056&rsquo;s ruling 3 opened Stage 9 and ordered F-26&rsquo;s seam settled inside it "
        "<i>as its first deliverable</i>, so §2 answers the seam and §5 builds the writer that needed the "
        "answer. Batch B &mdash; 8.8, F-24&rsquo;s confidence band &mdash; is measured in §11 and "
        "<b>not built</b>, and §1 says why that is a consequence of ruling 4 rather than a shortfall "
        "against it.</p></header>")

    # ---- 1 ----
    add("<section><h2>1 &middot; Two batches, one board, and what each one is</h2>"
        "<div class='card'>" + cadence_table() + "</div>"
        "<p>Ruling 4&rsquo;s sentence was that the gate, the tamper proof, the register rows and the record "
        "section stay <b>per-batch</b> so nothing becomes unattributable. Batch A contributes three rows to "
        "<span class='mono'>docs/07</span> and a new document, <span class='mono'>docs/16</span>. Batch B "
        "contributes no row and no deliverable, and its measurement lives in §10 of batch A&rsquo;s document "
        "labelled as batch B&rsquo;s &mdash; because a measurement recorded in a document that also delivers "
        "code is a measurement a reader can check against that code, and a measurement recorded nowhere is "
        "an assertion.</p>"
        "<p>Batch B is not built for one reason, and it is the reason F-27 exists. Two of the three shapes "
        "in question 2 are migrations, and F-27 established that a migration is the one artifact this "
        "repository cannot take back: <span class='mono'>checksum = sha256(sql)</span>, so a fix moves no "
        "checksum, but the recorded statement count is a row written at apply time and never rewritten, "
        "which would split production into two populations reporting different numbers for the same version "
        "and checksum with nothing able to tell which a row carries. D-056&rsquo;s ruling 2 applied that "
        "argument to F-27&rsquo;s own fix and declined it. The same argument governs a shape chosen here and "
        "ruled differently later, so §11 measures the shapes and question 2 asks.</p></section>")

    # ---- 2 ----
    add("<section><h2>2 &middot; What Stage 9 is, and what authorised it</h2>"
        "<p>Two sources, and they agree. <span class='mono'>design/build_board52.py:73</span> is the only "
        "stage map in the repository:</p>"
        + verbatim("design/build_board52.py:72-87 — P-2, verbatim", stage_map)
        + verbatim("docs/12 §1.3 — the two ADRs the path is built under", adrs)
        + "<p>D-056&rsquo;s ruling 3 is what makes this batch Stage 9 rather than another 8.x: "
        "<i>&ldquo;Stage 9 opens, and F-26&rsquo;s seam is settled inside it as its first deliverable &mdash; "
        "Stage 9 is the first code that would write <span class='mono'>decision</span> or "
        "<span class='mono'>trade_intent</span> rows, so the seam is answered before that writer "
        "exists.&rdquo;</i> The ruling <b>schedules</b> the decision and does not make it, so F-26 was still "
        "<span class='mono'>OPEN</span> when this batch started, and §3 makes it.</p>"
        "<p>The writer lives at <span class='mono'>src/nexus/intelligence/thesis.py</span> and not beside "
        "<span class='mono'>domain/decision.py</span>, for two checkable reasons: "
        "<span class='mono'>intelligence/__init__.py:1</span> already claims <i>stages 8&ndash;10</i>, and a "
        "thesis is step 1 of P-2&rsquo;s intelligence-to-execution path. The domain dataclass is the shape of "
        "the record; this package is the discipline around writing one.</p></section>")

    # ---- 3 ----
    add("<section><h2>3 &middot; F-26 answered: one seam, two doors, and nothing to move</h2>"
        + verbatim("docs/15 §13 — the question as recorded", f26)
        + "<p>The measurement says the question as posed offered a choice that does not exist. "
        "<span class='mono'>save_decision</span>&rsquo;s <b>last</b> statement <i>is</i> the payload door; "
        "the three before it only turn a <span class='mono'>DecisionRecord</span> into the mapping that call "
        "takes.</p><div class='card'>" + door_table() + "</div>"
        "<p>The three doors are <b>not one shape</b> &mdash; 4 statements, 3, and 1 &mdash; and pinning one "
        "body for all three would have been a false measurement. What all three share, and all the "
        "seam&rsquo;s answer rests on, is that the domain object is flattened with "
        "<span class='mono'>asdict</span> and the write happens in the payload sibling. "
        "<span class='mono'>project()</span> has called the three payload siblings since the write-ahead path "
        "was built, so it never touched the domain doors at all.</p>"
        "<p><b>Answer: the second of F-26&rsquo;s two options, at no cost.</b> Parents are checked upstream, "
        "in the writer, and <span class='mono'>docs/16</span> says so. No store signature moves.</p>"
        + verbatim("BLOCK A — the three bodies and all six signatures, captured", block("A"))
        + "<h3>3.1 &middot; The five foreign keys F-26 named, and where each is guarded now</h3>"
        "<div class='card'>" + fk_table() + "</div>"
        "<p><span class='mono'>PRAGMA foreign_keys</span> remains deliberately off "
        "(<span class='mono'>docs/13</span> §2.5), so every one of those guards is a writer guard or "
        "nothing. F-25&rsquo;s precedent is followed exactly: <b>two</b> separate refusals, because an empty "
        "string is neither an instrument nor <span class='mono'>None</span> and a name the master has never "
        "held is a dangling parent &mdash; different mistakes, different messages, and the second names what "
        "the master <i>does</i> hold rather than saying only &ldquo;not found&rdquo;.</p>"
        "<h3>3.2 &middot; F-26 becomes a CORRECTION, and stays OPEN</h3>"
        "<p>F-26 is answered and <b>stays <span class='mono'>OPEN</span></b>, for two reasons: ruling 3 "
        "scheduled the decision and did not make it, so the finding closes on the owner&rsquo;s ruling and "
        "not on this batch&rsquo;s measurement; and a batch does not declare its own finding closed. The "
        "precedent for the label is <b>F-15 CORRECTED</b> at <span class='mono'>docs/07:379</span>, because "
        "the finding as recorded was partly wrong &mdash; it described three seams needing a store in the "
        "signature, and they are one seam with two doors reachable without moving anything.</p>"
        "<p>What survives of F-26 is narrower and still true: "
        "<span class='mono'>DecisionRecord.instrument_id</span> is <span class='mono'>str | None</span> with "
        "no validation, so a dangling instrument stays <i>representable</i> and "
        "<span class='mono'>store.save_decision(record)</span> still accepts one. That is "
        "<span class='mono'>docs/15</span> §13.7 limitation 3 unchanged, and it is limitation 1 in §9.</p>"
        "<h3>3.3 &middot; A measurement this batch had already recorded, and got wrong</h3>"
        "<p>F-23 was the finding that a protocol growing a method silently breaks implementations in modules "
        "the offline suite cannot import. An earlier pass of this batch reported <i>&ldquo;no structural "
        "fakes anywhere in <span class='mono'>src/</span> or <span class='mono'>tests/</span>, so F-23&rsquo;s "
        "blind spot does not apply&rdquo;</i>. That is <b class='no'>wrong</b>, and wrong in the direction "
        "that flatters the change. The scan counts <i>definitions across all classes</i> rather than "
        "searching for subclasses &mdash; a <span class='mono'>Protocol</span> is conformed to structurally, "
        "so a fake implementing every method never appears in a subclass search &mdash; and over all 95 "
        "Python files it finds two:</p>"
        + verbatim("BLOCK B — the definitions scan, captured", block("B"))
        + "<p>They do not bite, but for a reason that has to be stated rather than assumed: each overrides "
        "exactly <b>one</b> method and forwards every other attribute through "
        "<span class='mono'>__getattr__</span> to a real <span class='mono'>SqliteOperationalStore</span>, so "
        "a method the protocol grows resolves through them unedited. A fake that <i>enumerated</i> the "
        "protocol would have to be updated, and a batch that forgot to would have failed in a module this "
        "suite skips &mdash; F-23 exactly. Both halves are pinned: the count, and that each wrapper defines "
        "<span class='mono'>__getattr__</span> plus exactly one override. That is limitation 8 in §9.</p>"
        "<h3>3.4 &middot; What the writer touches on the store</h3>"
        "<p>Asserted against <span class='mono'>thesis.py</span>&rsquo;s own AST rather than by patching the "
        "store, because patching cannot tell the writer&rsquo;s call from the projection&rsquo;s &mdash; "
        "<span class='mono'>project()</span> calls <span class='mono'>save_decision_payload</span> on "
        "purpose, and that call is the seam working rather than being bypassed. An early draft of this test "
        "patched the store and reported the projection&rsquo;s own call as the writer bypassing it.</p>"
        + verbatim("BLOCK C — the store attributes thesis.py reads, captured", block("C"))
        + "</section>")

    # ---- 4 ----
    add("<section><h2>4 &middot; F-29 &mdash; the getter the protocol never declared</h2>"
        "<p><span class='mono'>OperationalStore</span> declared <b>36</b> methods, and one asymmetry in them "
        "was invisible until a writer needed it: every entity the protocol serves declares its single-row "
        "getter &mdash; <span class='mono'>get_intent</span>, <span class='mono'>get_dossier</span>, "
        "<span class='mono'>get_evidence_ref</span>, <span class='mono'>get_memory_item</span> &mdash; and "
        "<span class='mono'>decision</span> did not, although "
        "<span class='mono'>SqliteOperationalStore.get_decision</span> has existed since Phase 2. Nothing "
        "noticed because nothing wrote a decision: it is a <i>writer</i> that has to ask whether an id is "
        "already taken, and <span class='mono'>record_thesis</span> is the first. A fake conforming to the "
        "protocol would have passed <span class='mono'>mypy</span> and raised "
        "<span class='mono'>AttributeError</span> on that guard &mdash; F-23&rsquo;s blind spot "
        "<b>inverted</b>: there the protocol grew a method an implementation lacked, here the implementation "
        "had one the protocol never declared.</p>"
        "<p><b>F-29 is closed here, and closing it moves no signature:</b> the method already existed with "
        "exactly the declared shape. The protocol now declares <b>37</b>.</p>"
        + verbatim("BLOCK E — the protocol's getters, captured", block("E"))
        + "<p>The test reads the declaration from source with <span class='mono'>ast</span> rather than from "
        "<span class='mono'>__protocol_attrs__</span>, which arrived in Python 3.12 and is an <b>empty "
        "set</b> on the 3.11 this suite runs on. A check built on it does not fail loudly: it passes, by "
        "asserting that nothing is declared. It did, on the first run of this batch&rsquo;s suite.</p></section>")

    # ---- 5 ----
    add("<section><h2>5 &middot; F-28 &mdash; two producers of one event, and one cannot reproduce its own row</h2>"
        + verbatim("tests/test_core_guarantees.py:498 — why F-28 cannot simply be fixed", pinned)
        + "<p><span class='mono'>decision.recorded</span> has two ways to build its payload in this "
        "repository, and they produce different payloads. The first is deliberate and <b>pinned</b>, so "
        "F-28 cannot be closed by adding the four keys and this batch does not try. The method has "
        "<b>zero</b> call sites in <span class='mono'>src/</span> or <span class='mono'>tests/</span> other "
        "than that one assertion, which is why the disagreement survived eight stages.</p>"
        "<div class='card'>" + f28_table() + "</div>"
        "<p><span class='mono'>write_with_audit</span> audits and projects <i>the same</i> payload, so a "
        "caller that audits the fourteen-key one has written an audit entry that cannot reproduce its own "
        "row. The mechanism is the projection&rsquo;s own fallback, "
        "<span class='mono'>_text(payload.get(&quot;created_at&quot;)) or now</span>: a payload without the "
        "key gets the <i>projection&rsquo;s</i> clock, and on a replay that clock is later than the "
        "write&rsquo;s. Measured, not inferred &mdash; both halves, in one run:</p>"
        + verbatim("BLOCK D — both payloads written, dropped, and replayed after 1.05 s", block("D"))
        + verbatim("src/nexus/intelligence/memory.py:456 — the remedy, already written down", remedy)
        + "<p><b>F-28 is recorded, <span class='mono'>OPEN</span>, no batch, and not fixed.</b> What this "
        "batch does is <i>not have it</i>: <span class='mono'>thesis.py</span> carries the same sentence and "
        "the same behaviour, and both are pinned &mdash; the comment in both files, the behaviour by the "
        "byte-identical replay above. Tamper <b>T12</b> drops <span class='mono'>&quot;created_at&quot;: "
        "now</span> from the event and the suite catches it; <b>T13</b> empties "
        "<span class='mono'>rationale</span> and the suite catches it.</p>"
        "<p><span class='mono'>rationale</span> riding in the event is <b>not</b> a relaxation of the pinned "
        "refusal. <span class='mono'>docs/03</span> §7 permits <i>&ldquo;Auditable evidence + structured "
        "findings + concise rationale only&rdquo;</i> and forbids hidden chain-of-thought, and "
        "<span class='mono'>open_dossier</span> has audited free-form <span class='mono'>summary</span> and "
        "<span class='mono'>uncertainty</span> since Stage 8.3 &mdash; its own docstring draws the line this "
        "writer follows: prose belongs in a named field, and <i>&ldquo;no prose reasoning is smuggled into "
        "<span class='mono'>payload</span>&rdquo;</i>. <span class='mono'>decision</span> has no "
        "<span class='mono'>payload</span> column at all (§7), so there is nowhere to smuggle into.</p></section>")

    # ---- 6 ----
    add("<section><h2>6 &middot; What the writer refuses, and the one law behind each refusal</h2>"
        "<p>Five approved sources say the same thing about a record written at step 1 of the path: "
        "<b>A-02</b> and <b>A-08</b>; P-2&rsquo;s failure text, quoted in §2; J-04&rsquo;s exit condition in "
        "<span class='mono'>docs/03</span>, ending <i>&ldquo;Research completion &ne; trade signal&rdquo;</i>; "
        "and <span class='mono'>docs/10</span> §3.2, <i>&ldquo;any FAIL ends the candidate with a reason "
        "code; confidence never overrides a failed stage&rdquo;</i>, with the three stages&rsquo; "
        "<i>&ldquo;definitions finalise at Stage 11&rdquo;</i>.</p>"
        "<h3>6.1 &middot; Four verbs permitted, three refused</h3>"
        "<p><span class='mono'>decision.verb</span> is free <span class='mono'>TEXT</span> with <b>no "
        "<span class='mono'>CHECK</span> and no <span class='mono'>DEFAULT</span> in either DDL</b>, so the "
        "boundary is enforced nowhere below this writer. Every <span class='mono'>DEFAULT "
        "'ABSTAIN'</span> in the repository is on a <span class='mono'>stance</span> column &mdash; "
        "<span class='mono'>schema.py:291</span>, <span class='mono'>schema.py:373</span> and "
        "<span class='mono'>migrations/0002_memory.sql:50</span> &mdash; and the ABSTAIN default comes from "
        "<span class='mono'>DecisionRecord.verb</span>, a Phase-2 domain default, not from the schema.</p>"
        "<div class='card'>" + verb_table() + "</div>"
        "<h3>6.2 &middot; Six states permitted, six refused</h3>"
        "<div class='card'>" + state_table() + "</div>"
        + verbatim("BLOCK F — both partitions, and the refusals as a caller receives them", block("F"))
        + "<p>Both sets partition their vocabulary <b>exactly</b> &mdash; 4 + 3 = 7 verbs, 6 + 6 = 12 "
        "states, disjoint and exhaustive &mdash; and both partitions are pinned, so a seventh word or a "
        "thirteenth state cannot arrive silently. Tamper <b>T19</b> folds the three verb refusals into one "
        "shared message and the suite catches it, which is the point of asserting three <i>distinct "
        "messages</i> rather than three refusals.</p>"
        "<h3>6.3 &middot; Three columns absent from the signature, not accepted and ignored</h3>"
        "<p><span class='mono'>intent_id</span>, <span class='mono'>risk_check</span> and "
        "<span class='mono'>expires_at</span> are columns on <span class='mono'>decision</span> and are "
        "<b>not parameters</b>. Each is left at what the projection&rsquo;s own defaults produce, and "
        "<span class='mono'>ThesisReceipt</span> echoes all three so the omission is visible to the caller "
        "and not only to a reader of the source. The absence is pinned <b>against the signature</b> &mdash; a "
        "parameter added later is a scope change and shows up there first &mdash; following "
        "<span class='mono'>docs/15</span> §12&rsquo;s discipline that an absence should be a decision a "
        "reader can argue with.</p>"
        "<p>One claim in that justification was <b>narrowed by measurement</b> rather than left as written. "
        "Expiry readers <i>do</i> exist in <span class='mono'>src/</span>: "
        "<span class='mono'>execution/intent.py:115</span> and <span class='mono'>:146</span> both compare "
        "<span class='mono'>parse_iso(self.expires_at) &lt;= reference</span>. What does not exist is any "
        "comparison of an expiry <b>read back from the store</b> against a clock, so "
        "<span class='mono'>memory_item.expires_at</span> is inert as <span class='mono'>docs/15</span> "
        "§14.8 limitation 1 says and D-056&rsquo;s ruling 1 re-affirmed, and "
        "<span class='mono'>decision.expires_at</span> would be too. The test scans for <i>ordering</i> "
        "comparisons only, because <span class='mono'>memory.py:380</span>&rsquo;s "
        "<span class='mono'>expires_at is not None</span> is a writer deciding whether an expiry was "
        "supplied and not a reader deciding whether one has passed &mdash; counting it would have made the "
        "test pass for the wrong reason.</p>"
        "<h3>6.4 &middot; Confidence is an input and never a gate</h3>"
        "<p><span class='mono'>decision.confidence</span> is <span class='mono'>TEXT</span> on SQLite and "
        "<span class='mono'>NUMERIC(6, 5)</span> in the portable target at "
        "<span class='mono'>migrations/0001_core.sql:112</span> &mdash; the same pair "
        "<span class='mono'>memory_item.confidence</span> has &mdash; so the boundary check is <b>imported</b> "
        "from Stage 8.5 rather than reimplemented. One opinion about one type, not two. It refuses a "
        "magnitude PostgreSQL would reject and a scale it would silently round, and &mdash; as <b>D-054</b> "
        "ruled &mdash; it bounds <b>no range</b>. That confidence is never a gate is asserted directly: the "
        "lowest and the highest value the target can hold both record "
        "<span class='mono'>verb=ABSTAIN, state=PROPOSED</span>.</p>"
        "<p><span class='mono'>domain/decision.py:59</span> comments this column <i>&ldquo;0..1, "
        "calibrated&rdquo;</i> and <b>nothing in the repository enforces that comment on either table</b>. "
        "This writer does not start. It is limitation 4 in §9.</p>"
        "<h3>6.5 &middot; ABSTAIN is the default record and not a fallback</h3>"
        "<p><span class='mono'>verb=ABSTAIN</span> requires at least one reason code, on "
        "<span class='mono'>docs/10</span> §3.1&rsquo;s <i>&ldquo;disposition + reason code&rdquo;</i> and "
        "§3.2&rsquo;s <i>&ldquo;any FAIL ends the candidate with a reason code&rdquo;</i>. The three "
        "non-ABSTAIN permitted verbs require none, and that permissiveness is asserted too &mdash; a gate "
        "nobody has tested for permissiveness is a gate nobody can tell from a bug. No vocabulary for these "
        "codes exists yet, because §3.2 puts their definitions at Stage 11, so they are free text for the "
        "same reason <span class='mono'>evidence_ref.kind</span> was left free text in Stage 8.2: where no "
        "vocabulary is declared anywhere, inventing one is the larger mistake.</p>"
        "<p><b>The writer asks for a reason code and not for an uncertainty, and says so in the refusal</b> "
        "&mdash; because <span class='mono'>decision</span> has no uncertainty column (§7). A code is a "
        "label, not a statement of what is unresolved.</p>"
        "<h3>6.6 &middot; One integrity rule of this writer&rsquo;s own</h3>"
        "<p>An evidence id may not appear in both <span class='mono'>evidence_refs</span> and "
        "<span class='mono'>counter_evidence_refs</span>. <span class='mono'>docs/10</span> §3.1 asks for "
        "contradictions <i>&ldquo;highlighted and linked&rdquo;</i>, and a source listed on both sides "
        "renders as a source arguing with itself, which tells a reviewer less than either citation alone. "
        "The refusal names <b>every</b> such id and not just the first, and points at "
        "<span class='mono'>evidence_ref.contradicts</span>, which has existed since Stage 8.6, as the way to "
        "record a real disagreement. A duplicate on <i>one</i> side is kept: a source cited twice is a claim "
        "the caller made twice.</p></section>")

    # ---- 7 ----
    add("<section><h2>7 &middot; F-30 &mdash; the stage map&rsquo;s &ldquo;uncertainty&rdquo; has nowhere to live</h2>"
        "<p><span class='mono'>build_board52.py:73</span> asks Stage 9 for <i>&ldquo;evidence set + "
        "uncertainty&rdquo;</i>. The evidence set has two columns. The uncertainty has none, and "
        "<span class='mono'>decision</span> is the only one of the three tables on this path with no "
        "<span class='mono'>payload</span> column to pin a key into &mdash; which is also why "
        "<span class='mono'>rationale</span> is the only home for a thesis&rsquo;s prose and why §6.5 "
        "requires it.</p><div class='card'>" + f30_table() + "</div>"
        + verbatim("BLOCK G — the three tables' columns, captured", block("G"))
        + "<p>The gap is between <b>two approved artifacts</b>, not between an artifact and an invention: "
        "the stage map asks for it and the schema built in Stage 6 has nowhere to put it.</p>"
        "<p><b>F-30 is recorded, <span class='mono'>OPEN</span>, and asked rather than decided</b>, for one "
        "reason: every remedy is a migration, and §1 gives the argument for why that makes it the "
        "owner&rsquo;s. Until it is ruled, this writer stores what <span class='mono'>decision</span> can "
        "hold and publishes the rest &mdash; the reason-code requirement of §6.5 is a <b>substitute</b>, not "
        "a fulfilment, and the refusal message says so. That is limitation 3 in §9, and question 2&rsquo;s "
        "shape is what would retire it.</p>"
        + verbatim("app.py DOSSIER_VIEW_GAPS element 9 — the gap Stage 9 touches without closing", gap9)
        + "</section>")

    # ---- 8 ----
    add("<section><h2>8 &middot; The gate, the tamper proof, and the harness that lied</h2>"
        "<div class='card'>" + gate_table() + "</div>"
        + verbatim("gate — pytest, ruff check, ruff format, mypy strict, and the tree", GATE91)
        + "<h3>8.1 &middot; 22 sites, 22 caught, 0 silent &mdash; on the second run</h3>"
        "<div class='card'>" + tamper_table() + "</div>"
        + verbatim("tamper sweep — every site, its verdict, and the restore", TAMPER91)
        + "<p><b>The first run of this sweep reported 21 sites, 0 caught, 21 silent</b> &mdash; every "
        "decision in the batch apparently unpinned, which would have been the most consequential result of "
        "the batch. It was not a result. The tell was the baseline line, which read "
        "<span class='mono'>? passed</span>: <span class='mono'>pyproject.toml</span>&rsquo;s "
        "<span class='mono'>addopts</span> already carries <span class='mono'>-q</span>, so the "
        "harness&rsquo;s own <span class='mono'>-q</span> made it <span class='mono'>-qq</span> and "
        "suppressed the summary line both verdicts are parsed from. Every site &ldquo;passed&rdquo; because "
        "nothing was ever counted.</p>"
        "<p>This is the same trap <span class='mono'>docs/15</span> §14 recorded for Stage 8.7 &mdash; "
        "recorded there, in writing, and repeated here anyway. The generalisation is worth more than the "
        "instance: <b>a sweep that reports every site silent is a broken sweep until the baseline is proven "
        "green <i>and parsed</i></b>, and a harness must abort rather than report when it cannot read its own "
        "baseline. One bad anchor went with it &mdash; <span class='mono'>if not wanted.strip():</span> "
        "occurs in both <span class='mono'>_resolve_instrument</span> and "
        "<span class='mono'>_resolve_evidence</span>, so a sweep that replaced the first match would have "
        "tampered with a guard it was not testing. Each anchor is now asserted to match exactly once before "
        "the sweep runs.</p></section>")

    # ---- 9 ----
    add("<section><h2>9 &middot; Eight limitations, and four costs this batch accepts</h2>"
        "<div class='card'>" + limitation_table() + "</div>"
        "<p><b>Four costs, published rather than defended.</b> <b>1.</b> <span class='mono'>_aware</span> is "
        "now copied a <b>third</b> time &mdash; <span class='mono'>evidence.py</span>, "
        "<span class='mono'>memory.py</span>, <span class='mono'>thesis.py</span>. "
        "<span class='mono'>memory.py</span>&rsquo;s docstring gives the reason and it still holds: a "
        "private helper is not a shared one, and promoting it to <span class='mono'>core.time</span> would "
        "touch a Phase-2 module inside a batch whose scope a ruling named. <b>2.</b> "
        "<span class='mono'>thesis.py</span>&rsquo;s copy is <b>dead on purpose</b> &mdash; no parameter is a "
        "datetime, because the one it would serve is deliberately absent (§6.3). It is there so the "
        "parameter cannot be added later without the naive-datetime refusal coming with it, and it is named "
        "here so it is not mistaken for an oversight. <b>3.</b> This is a <b>fourth unwired</b> writer: no "
        "caller in <span class='mono'>src/nexus</span> invokes <span class='mono'>record_thesis</span>, "
        "asserted by an AST scan for <i>calls</i> and not for the word, because "
        "<span class='mono'>operational.py</span>&rsquo;s F-29 comment names "
        "<span class='mono'>record_thesis</span> to say which writer needed the getter and a substring scan "
        "reported that comment as a caller. <b>4.</b> <span class='mono'>DecisionRecord</span> is still not "
        "what this writer writes &mdash; question 3.</p></section>")

    # ---- 10 ----
    add("<section><h2>10 &middot; Findings after this batch</h2>"
        "<div class='card'>" + finding_table() + "</div>"
        "<p>The next finding id is <b>F-31</b>. None of F-28, F-29 or F-30 is an "
        "<span class='mono'>O-</span> row, on D-054&rsquo;s reasoning &mdash; re-applied by D-056 to F-26 and "
        "F-27 &mdash; that recording a finding is not opening an obligation. "
        "<span class='mono'>docs/00</span> still holds <span class='mono'>O-001</span>&hellip;"
        "<span class='mono'>O-014</span>, fourteen rows, unchanged.</p>"
        "<h3>10.1 &middot; What Stage 9 did not do</h3>"
        "<p><b>No migration, no schema change, no checksum moved</b> &mdash; "
        "<span class='mono'>MIGRATIONS</span> stays at 6 and nothing in "
        "<span class='mono'>store/schema.py</span> or <span class='mono'>migrations/*.sql</span> was touched, "
        "which is the property that lets question 2 stay open without this batch having pre-empted it. "
        "<b>No <span class='mono'>trade_intent</span> row is written by anything</b>, A-08 being why. "
        "<b>No route</b> &mdash; <span class='mono'>app.py</span> gained no reference to "
        "<span class='mono'>thesis</span>. <b>No expiry policy</b> on either table, and "
        "<span class='mono'>docs/15</span> §14.8 limitation 1 stands exactly as published. <b>No confidence "
        "band</b> &mdash; F-24 is untouched. <b>No sufficiency meter</b> &mdash; F-18&rsquo;s gap 4 stays "
        "open and belongs to stage 10. <b>F-27 untouched</b>, its inflated counts still pinned. <b>No stage "
        "beyond 11 is named.</b> <b>F-26 not closed and not re-labelled by this batch</b> &mdash; §3.2 "
        "states the case for <span class='mono'>CORRECTED</span>; the label is the owner&rsquo;s.</p></section>")

    # ---- 11 ----
    add("<section><h2>11 &middot; Batch B, measured and not built &mdash; F-24&rsquo;s confidence band</h2>"
        + verbatim("migrations/0002_memory.sql:29 — the band in the schema's own words", band_header)
        + "<p><span class='mono'>docs/10</span> §3.1 asks for confidence <i>&ldquo;as a band with validity "
        "interval and change conditions&rdquo;</i> and calls a point estimate without them <i>&ldquo;a "
        "defect&rdquo;</i>. Stage 8.5 supplied the interval and the change conditions; the band is what is "
        "left, and it is the one open finding whose subject is Stage 8&rsquo;s own tables &mdash; which is "
        "why D-056 §14.10 derived 8.8 as F-24 rather than retro-fitting a scope to a label that carried "
        "none.</p>"
        "<h3>11.1 &middot; What D-054 already rules, so it is not re-asked</h3>"
        "<p><b>D-054 ruled confidence unbounded</b>, and that ruling is <b>applied</b> here rather than "
        "reopened. What &ldquo;unbounded&rdquo; means precisely, measured through "
        "<span class='mono'>confidence_text</span>: there is <b>no range rule</b>, so "
        "<span class='mono'>-0.4</span>, <span class='mono'>0</span> and "
        "<span class='mono'>9.99999</span> all store; but the portable target&rsquo;s own magnitude ceiling "
        "still refuses <span class='mono'>10</span> and <span class='mono'>47</span>, and its scale still "
        "refuses <span class='mono'>1e-6</span> and <span class='mono'>0.999999</span>. A band inherits "
        "exactly that. An <i>ordering</i> rule &mdash; high not below low &mdash; is not a range rule, and "
        "Stage 8.5 already established the precedent: <span class='mono'>valid_until &lt;= valid_from</span> "
        "is refused including equality. So <b>the band&rsquo;s bounds are settled and its shape is "
        "not</b>, which is why question 2 asks one thing.</p>"
        "<h3>11.2 &middot; Which shape is more expressive, measured</h3>"
        "<div class='card'>" + band_table() + "</div>"
        + verbatim("BLOCK H — every band-relevant input through the existing boundary check", block("H"))
        + "<p>(a) is <b>strictly more expressive</b> under the target that already exists: a width is a "
        "magnitude, so it inherits the one-digit-before-the-point ceiling even though confidence itself is "
        "unbounded, and a band wider than <span class='mono'>9.99999</span> becomes unrepresentable while its "
        "two endpoints are not. (b) also needs a <b>second ruling</b> that (a) does not &mdash; whether "
        "<span class='mono'>width</span> is a half-width or a full width &mdash; and an unruled ambiguity in "
        "a column is the thing <span class='mono'>docs/15</span> §12.8 was opened for. (c) is the only shape "
        "with no migration and is offered for that reason alone; nothing could bound a JSON blob.</p>"
        "<p>What a band would touch, measured: <span class='mono'>memory_item</span> has <b>15</b> columns, "
        "<span class='mono'>record_memory_item</span> <b>15</b> parameters, "
        "<span class='mono'>MemoryReceipt</span> <b>17</b> fields, <span class='mono'>memory.py</span> "
        "<b>17</b> <span class='mono'>raise ValueError</span> sites, <span class='mono'>validity_of</span> "
        "returns <b>5</b> keys, and <span class='mono'>evidence_ref</span>&rsquo;s "
        "<span class='mono'>CHECKSUMMED_FIELDS</span> holds <b>10</b> of its 12 columns.</p></section>")

    # ---- 12 ----
    add("<section><h2>12 &middot; The four questions, on one board</h2>"
        "<p>Ruling 4&rsquo;s shape: both batches&rsquo; questions together, so the owner rules once. Batch A "
        "contributes questions 1 and 3, batch B question 2, and question 4 is about what runs next under the "
        "new cadence. Each is recorded here <b>as put</b>, in a table of its own and built by a function of "
        "its own, because a ruling table and a question table that share a helper are a ruling that can "
        "silently rewrite the question it answered &mdash; the reason "
        "<span class='mono'>build_board87.py</span> keeps "
        "<span class='mono'>ruling_table()</span> and <span class='mono'>decision_table()</span> apart.</p>"
        "<div class='card'>" + ruling_table() + "</div></section>")

    add("<footer class='page-foot'><p>Stage 9.1 &middot; batch A of two, on one combined board per D-056 "
        "ruling 4 &middot; F-26&rsquo;s seam <b>answered</b> and due <span class='mono'>CORRECTED</span>, "
        "still <span class='mono'>OPEN</span> &middot; F-28 and F-30 <b>found and recorded</b>, no batch "
        "&middot; F-29 <b>found and closed</b>, the protocol 36&nbsp;&rarr;&nbsp;37 &middot; "
        "<span class='mono'>thesis.py</span> 521 lines and <span class='mono'>test_thesis_writer.py</span> "
        "986 lines with 99 tests &middot; <b>no migration, no schema change, no checksum moved</b> &middot; "
        "gate <b>1,527 passed / 2 skipped / 0 failed</b>, tamper <b>22/22/0</b> with the baseline parsed "
        "green before and after and SHA-256 restore verified &middot; ruff clean, format <b>95</b>, mypy "
        "strict on <b>63</b> &middot; <span class='mono'>src</span> <b>63</b> files and <b>16,903</b> lines, "
        "<span class='mono'>tests</span> <b>32</b> and <b>20,843</b> &middot; <b>eight</b> limitations and "
        "<b>four</b> costs published in full, including that the verb boundary is a derivation and not a "
        "quotation, and that a third copy of <span class='mono'>_aware</span> ships dead on purpose "
        "&middot; two of this batch&rsquo;s own measurements are corrected on the board rather than quietly "
        "replaced &mdash; the &ldquo;no structural fakes&rdquo; claim in §3.3 and the "
        "&ldquo;no expiry reader exists&rdquo; claim in §6.3 &middot; batch B measured in §11 and <b>not "
        "built</b>, because two of its three shapes are migrations &middot; next finding id "
        "<b>F-31</b></p></footer>")

    add("</div></body></html>")

    out = HERE / "stage9-1-the-candidate-thesis.html"
    out.write_text("".join(parts))
    return out


if __name__ == "__main__":
    path = main()
    print(f"wrote {path} ({path.stat().st_size // 1024} KB)")
