"""Stage 8.5 board: `memory_item` gets a writer, and a point estimate stops being the only column.

D-052's ruling 3 ordered this batch and D-053's ruling 4 re-ordered it against the alternative it
declined (wiring `evidence_ref.retrieved_at` first). Scope as ruled: the writer, F-18's three columns,
and `evidence_ref.contradicts`. §1 shows what was ruled out as absent rather than unmentioned.

Every transcript here was captured from `backend/.venv/bin/python` runs against a live post-migration
database, from `pytest` runs, or from the tamper script, and pasted verbatim — including the four
probes that found F-25 and the twenty tamper sites that prove the gate is load-bearing. Captures:
`/tmp/cap85.py` (BLOCKS A–I), `/tmp/gate85.txt`, `/tmp/tamper85.py`.

Run:  cd backend && .venv/bin/python ../design/build_board85.py
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
.no { color: var(--color-feedback-negative-text); }
.ok { color: var(--color-feedback-positive-text); }
/* `.card` wraps every table here and is undefined in the shared shell (CSS71) — the same gap the 8.2,
   8.3 and 8.4 boards recorded. Copied from `build_specimen.py`, the approved visual language. */
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
# Captures. Pasted from /tmp/cap85.txt, not retyped: a transcript that is transcribed is a
# transcript that can be improved.
# ---------------------------------------------------------------------------------------------

BLOCK_A = """
  0001_operational         statements= 19  requires=None           checksum=fcfd79161c830f40…
  0002_memory              statements=  8  requires=None           checksum=5e7fafd0673e0a60…
  0003_audit_append_only   statements=  4  requires=audit_log      checksum=1e9ec5a5d9154d0a…
  0004_memory_fidelity     statements= 15  requires=dossier        checksum=4c7368d407bb1f18…
  0005_memory_beliefs      statements=  4  requires=memory_item    checksum=4520e5b5e259eb4c…

  the four statements of 0005, verbatim from store/schema.py:
    (4 statements; the comment lines above them are stripped here, not in the migration)
    ALTER TABLE memory_item ADD COLUMN valid_from TEXT;
    ALTER TABLE memory_item ADD COLUMN valid_until TEXT;
    ALTER TABLE memory_item ADD COLUMN change_conditions TEXT NOT NULL DEFAULT '';
    ALTER TABLE evidence_ref ADD COLUMN contradicts TEXT REFERENCES evidence_ref (evidence_id);

  PRAGMA table_info(memory_item) -> 14 columns
    memory_id, kind, scope, subject, body, created_at, superseded_by, cited_by, confidence, payload, audit_ref, valid_from, valid_until, change_conditions
  PRAGMA foreign_key_list(memory_item) -> {} (empty)

  PRAGMA table_info(evidence_ref) -> 12 columns
    evidence_id, dossier_id, source, kind, observed_at, retrieved_at, data_status, locator, checksum, payload, audit_ref, contradicts
  PRAGMA foreign_key_list(evidence_ref) -> {'contradicts': ('evidence_ref', 'evidence_id'), 'dossier_id': ('dossier', 'dossier_id')}

  PRAGMA table_info(dossier) -> 12 columns
    dossier_id, instrument_id, venue, created_at, updated_at, state, summary, stance, uncertainty, sufficiency, payload, audit_ref
  PRAGMA foreign_key_list(dossier) -> {'instrument_id': ('instrument', 'instrument_id')}

  PRAGMA index_list(memory_item) -> ['ix_memory_created', 'ix_memory_kind', 'sqlite_autoindex_memory_item_1']

  the stored DDL's tail, showing where ADD COLUMN put them:
    " DEFAULT '{}',\n    audit_ref     TEXT\n, valid_from TEXT, valid_until TEXT, change_conditions TEXT NOT NULL DEFAULT '')"
"""

BLOCK_B = """
  '0.5'        SQLite stored it as '0.5' (text)               | writer accepts -> '0.5'
  '0'          SQLite stored it as '0' (text)                 | writer accepts -> '0'
  '-0.5'       SQLite stored it as '-0.5' (text)              | writer accepts -> '-0.5'
  '9.99999'    SQLite stored it as '9.99999' (text)           | writer accepts -> '9.99999'
  'abc'        SQLite REFUSED: CHECK constraint failed: confidence IS NULL OR CAST( | writer REFUSES: confidence 'abc' is not a number. The applied column is TEXT and migra
  ''           SQLite REFUSED: CHECK constraint failed: confidence IS NULL OR CAST( | writer REFUSES: confidence must be a number or None; an empty string is neither
  '0.5abc'     SQLite stored it as '0.5abc' (text)            | writer REFUSES: confidence '0.5abc' is not a number. The applied column is TEXT and mi
  '1e400'      SQLite stored it as '1e400' (text)             | writer REFUSES: confidence '1e400' needs 401 digits before the decimal point and the p
"""

BLOCK_C = """
  confidence alone         -> ValueError
      confidence='0.72' is a point estimate, and docs/10 §3.1 is explicit that 'a point estimate without them is a defect': it needs change_conditions, the statement of what would make this stop being true
      docs/03 §7 asks the Intelligence Centre to show beliefs with 'confidence, validity interval, change conditions', and J-04's exit condition is that the owner learns what would invalidate the thesis — which a number alone cannot say
  + change_conditions      -> ValueError
      confidence='0.72' needs valid_from: docs/10 §3.1 asks for confidence 'with validity interval', and an interval with no start is not one
      created_at is not a substitute and is not used as one — it says when this system wrote the row, not from when the claim holds, and collapsing the two is F-14's mistake in a different pair of columns
  + valid_from             -> ValueError
      confidence='0.72' needs at least one evidence_ids entry: docs/03 §7 asks for 'memory updates with provenance', and a confidence with nothing behind it is exactly the fabricated confidence the owner requirements forbid
      docs/12 §1.3's law (A-02+A-08) is that no gate can be satisfied by a confidence value, which only holds if the value itself rests on something a reviewer can read
  + one real evidence id   -> ACCEPTED  MEM-DA17CED466794E20-VCFYTW5W  confidence='0.72'
"""

BLOCK_D = """
  accept '0'            -> '0'
  accept '0.72'         -> '0.72'
  accept '1'            -> '1'
  accept '-0.5'         -> '-0.5'
  accept '9.99999'      -> '9.99999'
  accept '0.00001'      -> '0.00001'
  accept '9.999990'     -> '9.999990'
  accept '0.5'          -> '0.5'
  REFUSE '10'           -> confidence '10' needs 2 digits before the decimal point and the portable target declares
  REFUSE '123'          -> confidence '123' needs 3 digits before the decimal point and the portable target declare
  REFUSE '1E+2'         -> confidence '1E+2' needs 3 digits before the decimal point and the portable target declar
  REFUSE '-10'          -> confidence '-10' needs 2 digits before the decimal point and the portable target declare
  REFUSE '99.99999'     -> confidence '99.99999' needs 2 digits before the decimal point and the portable target de
  REFUSE '0.123456'     -> confidence '0.123456' carries 6 decimal places and the portable target declares NUMERIC(
  REFUSE '0.000001'     -> confidence '0.000001' carries 6 decimal places and the portable target declares NUMERIC(
  REFUSE '1.0000009'    -> confidence '1.0000009' carries 7 decimal places and the portable target declares NUMERIC
  REFUSE ''             -> confidence must be a number or None; an empty string is neither
  REFUSE 'abc'          -> confidence 'abc' is not a number. The applied column is TEXT and migration 0004's CHECK 
  REFUSE '0.7.2'        -> confidence '0.7.2' is not a number. The applied column is TEXT and migration 0004's CHEC
  REFUSE 'NaN'          -> confidence must be finite; got 'NaN'. NaN and Infinity are Decimal values, so the CHECK 
  REFUSE 'Infinity'     -> confidence must be finite; got 'Infinity'. NaN and Infinity are Decimal values, so the C
  REFUSE '-Infinity'    -> confidence must be finite; got '-Infinity'. NaN and Infinity are Decimal values, so the 
  accept Decimal('0.7') -> '0.7'
  accept Decimal('1E-5') -> '0.00001'
  accept int 1          -> '1'
  REFUSE bool True      -> confidence must be a number, not True: a bool is an int in Python and Decimal accepts it
  REFUSE float 0.5      -> confidence must be a Decimal or its exact string form, not a float (0.5). store/serialis

  TOTAL 27 inputs: 11 accepted, 16 refused
  CONFIDENCE_PRECISION=6 CONFIDENCE_SCALE=5  -> digits before the point allowed = 1
"""

BLOCK_E = """
  no interval at all                 -> ACCEPTED  valid_from=None valid_until=None  open_ended=True
  open-ended from T                  -> ACCEPTED  valid_from=2026-11-25T12:00:00.000Z valid_until=None  open_ended=True
  ends before it starts              -> ValueError: valid_until (2026-11-25T11:00:00.000Z) must follow valid_from (2026-11-25T12:00:00.000Z): the pair bounds the period a claim is asserted to hold over, and an interval that ends before or exa
  zero length                        -> ValueError: valid_until (2026-11-25T12:00:00.000Z) must follow valid_from (2026-11-25T12:00:00.000Z): the pair bounds the period a claim is asserted to hold over, and an interval that ends before or exa
  already expired                    -> ACCEPTED  valid_from=2025-10-21T12:00:00.000Z valid_until=2026-01-29T12:00:00.000Z  open_ended=False
  starts in the future               -> ACCEPTED  valid_from=2026-12-25T12:00:00.000Z valid_until=2027-01-24T12:00:00.000Z  open_ended=False
  naive valid_from                   -> ValueError: valid_from must be an aware UTC datetime; got a naive '2026-11-25T12:00:00'

  created_at is NOT the default for either end:
    created_at  = 2026-11-27T16:59:50.663Z
    valid_from  = 2026-11-25T12:00:00.000Z   (the caller's, not created_at)
    valid_until = None   (None means no end was stated)
    payload['validity_open_ended'] = True
"""

BLOCK_F = """
  A = EV-9D97FC86A01547DF-5WNDVNWW   contradicts = None
  B = EV-E3898B7E3532492D-Q8M9XKXW   contradicts = EV-9D97FC86A01547DF-5WNDVNWW  -> A
  store.get_evidence_ref(A)['contradicts'] = None
  A's row was NOT edited by B's write: A.contradicts is still None
  a dangling contradicts         -> ValueError: evidence 'EV-NOPE' does not exist, so nothing can be recorded as contradicting it. evidence_ref.contradicts REFERENCES evidence_ref since migration 0005_memory_beliefs, but PRAGMA foreign_keys is deli
  a row contradicting itself     -> ValueError: evidence 'EV-9D97FC86A01547DF-5WNDVNWW' cannot contradict itself: a contradiction is a disagreement between two observations, and a row pointing at its own id records neither. Record the second observ

  a contradiction ACROSS two cases: C in CASE-498AB2D6A4744FAB-236FYMYM -> A in CASE-A7F5481A78BC4530-F86TD1D3
    C.contradicts = EV-9D97FC86A01547DF-5WNDVNWW
  CHECKSUMMED_FIELDS = 10 of 12 stored columns
    ('evidence_id', 'dossier_id', 'source', 'kind', 'observed_at', 'retrieved_at', 'data_status', 'locator', 'payload', 'contradicts')
    NOT covered: ['checksum', 'audit_ref']
  verify_evidence_checksum(B's row) = True
  PROJECTABLE has 15 keys; 'memory.recorded' -> 'memory_item'
"""

BLOCK_G = """
  dossier.instrument_id -> instrument        refused -> instrument 'NOPE:NOPE' is not in the system of record, which holds 0: []. dossier.instrument_id REFERENCES instrument since migration 0004_memory_fidelity, but PRAGMA for
  evidence_ref.contradicts -> evidence_ref   refused -> evidence 'EV-NOPE' does not exist, so nothing can be recorded as contradicting it. evidence_ref.contradicts REFERENCES evidence_ref since migration 0005_memory_beliefs, b
  memory_item's evidence_ids (no FK at all)  refused -> evidence 'EV-INVENTED' does not exist, so nothing can rest on it. docs/03 §7 asks the Intelligence Centre to show 'memory updates with provenance', and a pointer at a row
  evidence_ref.dossier_id -> dossier         ACCEPTED -> EV-315336B5694142E8-84AJVTF0

  store.get_dossier('DOS-NOPE') = None
  len(store.evidence_refs(dossier_id='DOS-NOPE')) = 1
  len(store.dossiers()) = 2  (neither invented id is among them)
  PRAGMA foreign_keys = 0 (off by design, docs/13 §2.5)
"""

BLOCK_H = """
  recorded MEM-12ECA3E5E5D44CC9-HAVRAKFW  confidence='0.68'  cited_by=()  superseded_by=None
  evidence_ids = ('EV-9D97FC86A01547DF-5WNDVNWW', 'EV-E3898B7E3532492D-Q8M9XKXW')
  created_at   = 2026-11-27T16:59:50.679Z
  after DELETE FROM memory_item and DELETE FROM op_projection:
    get_memory_item -> None
    store.counts()['memory_item'] = 0
  reproject_missing() -> 15 ref(s) reapplied; this one among them: True
  created_at identical after replay: True  (2026-11-27T16:59:50.679Z)
  confidence identical: True  ('0.68')
  whole row identical: True
"""

BLOCK_I = """
  src files naming record_memory_item:
    src/nexus/intelligence/__init__.py           the package __init__ that exports it
    src/nexus/intelligence/memory.py             the writer itself
    src/nexus/store/operational.py               a docstring only

  routes declared in app.py: 13
  'memory_items('              present in app.py: False
  'get_memory_item('           present in app.py: False
  '/v1/intelligence/memory'    present in app.py: False
  view_gaps served by the route: 9
  core/ids.py mentions 'MEM': False   new_id('MEM') -> MEM-AAC6E4960ADB4E04-WX49NABT
"""

BLOCK_GATE = """
$ .venv/bin/python -m pytest
1394 passed, 2 skipped, 1 warning in 31.40s

$ .venv/bin/ruff check src tests
All checks passed!

$ .venv/bin/ruff format --check src tests
93 files already formatted

$ .venv/bin/mypy src
Success: no issues found in 62 source files

per file, each run separately:
  test_memory_writer.py       77 passed in 4.05s     (NEW, 854 lines, 55 test functions)
  test_evidence_writer.py     54 passed in 2.78s     (was 42)
  test_intelligence_routes.py 44 passed in 2.84s     (was 39)
  test_schema_fidelity.py     41 passed in 1.91s     (was 35; six for 0005)
  test_dossier_writer.py      87 passed in 6.50s     (unchanged; one test REPLACED)
  test_repo_hygiene.py        88 passed in 5.21s     (unchanged)
  test_migrations.py          15 passed in 0.59s     (unchanged)

  run bare, not with -q: pyproject.toml already sets addopts="-q --strict-markers", and a second -q
  suppresses the summary line every count in this board comes from.
"""

BLOCK_TAMPER = """
memory: no change_conditions requirement | 3 failed, 315 passed | test_a_confidence_with_no_change_conditions_is_refused, test_whitespace_only_conditions_are_the_same_as_none, test_the_three_refusals_are_three_messages_not_one
memory: no valid_from requirement | 2 failed, 316 passed | test_a_confidence_with_no_valid_from_is_refused, test_the_three_refusals_are_three_messages_not_one
memory: no provenance requirement | 2 failed, 316 passed | test_a_confidence_with_no_provenance_is_refused, test_the_three_refusals_are_three_messages_not_one
memory: scale not checked against NUMERIC(6,5) | 3 failed, 315 passed | test_a_scale_the_target_would_round_is_refused[0.123456|0.000001|1.0000009]
memory: magnitude not checked against NUMERIC(6,5) | 5 failed, 313 passed | test_a_magnitude_the_target_would_overflow_is_refused[10|123|1E+2|-10]
memory: a float confidence accepted | 1 failed, 317 passed | test_a_float_is_refused_because_a_decimal_never_becomes_one
memory: a dangling evidence id accepted | 2 failed, 316 passed | test_an_evidence_id_the_store_has_never_held_is_refused, test_one_real_id_beside_one_fake_one_is_refused_too
memory: a repeated id becomes an edit | 1 failed, 317 passed | test_a_second_record_under_the_same_id_is_refused
memory: an inverted interval accepted | 2 failed, 316 passed | test_an_interval_that_ends_before_it_starts_is_refused, test_an_interval_of_zero_length_is_refused_too
memory: open-ended validity not reported | 1 failed, 317 passed | test_an_open_ended_interval_says_so_instead_of_leaving_a_hole
memory: a caller can forge cited_by | 1 failed, 317 passed | test_cited_by_is_always_empty_because_an_item_cannot_cite_itself
evidence: a dangling contradicts accepted | 1 failed, 317 passed | test_a_row_that_does_not_exist_cannot_be_contradicted
evidence: a self-contradiction accepted | 1 failed, 317 passed | test_a_row_cannot_contradict_itself
evidence: contradicts dropped from the checksum | 3 failed, 314 passed | test_the_covered_set_is_derived_from_the_live_table, test_the_new_column_joined_the_covered_set, test_the_route_does_not_mutate_the_row_it_verifies
route: the reverse direction is not derived | 2 failed, 316 passed | test_both_directions_of_one_recorded_disagreement_are_served, test_two_rows_pointing_at_one_are_one_pair_each
route: the pair count is always zero | 3 failed, 315 passed | test_both_directions_of_one_recorded_disagreement_are_served, test_two_rows_pointing_at_one_are_one_pair_each, test_a_contradiction_across_two_cases_appears_in_neither_scan
schema: change_conditions never added | 45 failed, 273 passed | test_the_row_lands_with_the_least_claiming_defaults, test_a_belief_stores_all_three_of_the_columns_this_batch_adds, test_the_event_is_audited_and_projectable, test_created_at_rides_inside_the_event
schema: contradicts never added | 96 failed, 222 passed | test_a_belief_stores_all_three_of_the_columns_this_batch_adds, test_the_event_is_audited_and_projectable, test_created_at_rides_inside_the_event, test_a_replay_reproduces_the_row_including_its_clock
store: contradicts not persisted | 7 failed, 311 passed | test_a_recorded_disagreement_is_stored_and_reads_back, test_a_mutual_disagreement_takes_two_calls_and_neither_row_is_edited, test_a_contradiction_survives_a_replay_from_the_chain_alone, test_both_directions_of_one_recorded_disagreement_are_served
writeahead: memory.recorded not projectable | 33 failed, 285 passed | test_the_row_lands_with_the_least_claiming_defaults, test_a_belief_stores_all_three_of_the_columns_this_batch_adds, test_a_replay_reproduces_the_row_including_its_clock, test_the_payload_reads_back_as_a_dict_not_as_text

  20 sites, 20 caught, 0 silent passes, 0 "ANCHOR COUNT" failures. The six source files are backed up
  to /tmp/t85/*.bak before the run and restored after it; the full suite was re-run green afterwards
  (1394 passed / 2 skipped) and `git diff` confirms the tree holds only this batch's work.
"""


def scope_tables() -> str:
    ruled = table(
        ["Ruled into this batch", "Where it landed"],
        [
            ("the <span class='mono'>memory_item</span> writer",
             "<span class='mono'>intelligence/memory.py</span>, <b>471</b> lines, audited as "
             "<span class='mono'>memory.recorded</span>"),
            ("F-18's <span class='mono'>valid_from</span>, <span class='mono'>valid_until</span>, "
             "<span class='mono'>change_conditions</span>",
             "migration <span class='mono'>0005_memory_beliefs</span>, three "
             "<span class='mono'>ADD COLUMN</span>s on <span class='mono'>memory_item</span>"),
            ("<span class='mono'>evidence_ref.contradicts</span>",
             "the same migration's fourth statement, a self-referencing foreign key"),
            ("the refusal that makes <span class='mono'>docs/10</span> &sect;3.1's sentence true",
             "<b>seventeen</b> <span class='mono'>raise ValueError</span> sites in the writer, "
             "<b>not</b> a <span class='mono'>CHECK</span> in the schema"),
        ],
    )
    not_ruled = table(
        ["Explicitly <b>not</b> ruled in, and not done", "Why it is stated rather than left absent"],
        [
            ("wiring <span class='mono'>evidence_ref.retrieved_at</span>",
             "offered at &sect;11.13 question 4 and <b>declined</b> by ruling 4; &sect;11.12's "
             "limitation 1 stands unchanged"),
            ("an <span class='mono'>expires_at</span> column",
             "F-18's second gap. Not one of &ldquo;the three columns&rdquo;. "
             "<span class='mono'>valid_until</span> is not a substitute &mdash; &sect;4"),
            ("a confidence band (<span class='mono'>confidence_low</span>/<span class='mono'>high</span>)",
             "two more columns, not this batch's ruling either. Recorded as <b>F-24</b>, &sect;13"),
            ("the sufficiency meter's definition",
             "<span class='mono'>docs/10</span> &sect;3.2 finalises V1&ndash;V3 at stage 11; the route "
             "still serves basis and target as strings"),
            ("F-22 / <span class='mono'>O-014</span>, the periodic checksum audit",
             "recorded by D-052's ruling 4 precisely so a later batch would not close it by accident"),
            ("any rewrite of a text an earlier ruling approved",
             "pointers only. &sect;10.8's eleven-pair range, &sect;9's and &sect;10's disclosures and "
             "<span class='mono'>docs/07</span>'s approved rows are untouched"),
        ],
    )
    return (f"<div class='card'><h4>Ruled in</h4>{ruled}</div>"
            f"<div class='card' style='margin-top:12px'><h4>Ruled out</h4>{not_ruled}</div>")


def column_table() -> str:
    return table(
        ["Table", "Columns before", "Columns after", "Foreign keys after"],
        [
            ("<span class='mono'>memory_item</span>", "11", "<b>14</b>",
             "<b>none</b> &mdash; <span class='mono'>cited_by</span> and "
             "<span class='mono'>superseded_by</span> are <span class='mono'>TEXT</span> lists, not "
             "references, which is why the writer checks <span class='mono'>evidence_ids</span> itself"),
            ("<span class='mono'>evidence_ref</span>", "11", "<b>12</b>",
             "<b>two</b>: <span class='mono'>dossier_id &rarr; dossier</span> and "
             "<span class='mono'>contradicts &rarr; evidence_ref</span>"),
            ("<span class='mono'>dossier</span>", "12", "12",
             "<span class='mono'>instrument_id &rarr; instrument</span> (from "
             "<span class='mono'>0004</span>)"),
        ],
    )


def refusal_table() -> str:
    return table(
        ["Refusal", "What it says", "Document cited"],
        [
            ("confidence without <span class='mono'>change_conditions</span>",
             "&ldquo;is a point estimate, and <span class='mono'>docs/10</span> &sect;3.1 is explicit "
             "that a point estimate without them is a defect&rdquo;",
             "<span class='mono'>docs/10</span> &sect;3.1"),
            ("confidence without <span class='mono'>valid_from</span>",
             "&ldquo;needs <span class='mono'>valid_from</span> &hellip; an interval with no start is "
             "not one&rdquo;, and <span class='mono'>created_at</span> is named as not a substitute",
             "<span class='mono'>docs/10</span> &sect;3.1"),
            ("confidence without &ge;1 <span class='mono'>evidence_ids</span>",
             "&ldquo;a confidence with nothing behind it is exactly the fabricated confidence the owner "
             "requirements forbid&rdquo;",
             "<span class='mono'>docs/03</span> &sect;7"),
        ],
    )


def f24_table() -> str:
    return table(
        ["Axis", "What the approved design asks for", "What exists after 8.5"],
        [
            ("time", "validity interval, change conditions",
             "<span class='ok'><b>delivered</b></span> &mdash; "
             "<span class='mono'>valid_from</span>, <span class='mono'>valid_until</span>, "
             "<span class='mono'>change_conditions</span>, and the writer refuses a confidence that has "
             "neither of the first two"),
            ("provenance", "corroborating / contradictory sources",
             "<span class='ok'><b>delivered</b></span> &mdash; "
             "<span class='mono'>evidence_ids</span> checked against the store, "
             "<span class='mono'>contradicts</span> on the evidence row"),
            ("<b>confidence</b>", "<b>&ldquo;confidence as a band&rdquo;</b> "
             "(<span class='mono'>docs/10</span> &sect;3.1); D-035 approved &ldquo;beliefs as "
             "bands&rdquo;",
             "<span class='no'><b>one number</b></span> &mdash; "
             "<span class='mono'>confidence</span> is a single <span class='mono'>TEXT</span> column "
             "holding a single value. <b>F-24</b>"),
            ("expiry", "&ldquo;expiring TTLs&rdquo; (<span class='mono'>docs/10</span> &sect;3.1)",
             "<span class='no'><b>no column</b></span> &mdash; F-18's second gap stays open; "
             "<span class='mono'>valid_until</span> is about the world, not about this system"),
            ("sufficiency", "&ldquo;meter with stated basis and what it is sufficient for&rdquo;",
             "basis and target served as strings; the meter is stage 10's to define and stage 11's to "
             "finalise"),
        ],
    )


def f25_table() -> str:
    return table(
        ["Parent reference", "Refused in the writer?", "Since"],
        [
            ("<span class='mono'>dossier.instrument_id &rarr; instrument</span>",
             "<span class='ok'><b>yes</b></span>", "8.3"),
            ("<span class='mono'>evidence_ref.contradicts &rarr; evidence_ref</span>",
             "<span class='ok'><b>yes</b></span>", "<b>this batch</b>"),
            ("<span class='mono'>memory_item</span>'s <span class='mono'>evidence_ids</span> "
             "(payload; <b>no FK at all</b>)", "<span class='ok'><b>yes</b></span>", "<b>this batch</b>"),
            ("<span class='mono'>evidence_ref.dossier_id &rarr; dossier</span>",
             "<span class='no'><b>NO</b></span> &mdash; <b>F-25</b>", "never"),
        ],
    )


def gap_table() -> str:
    return table(
        ["<span class='mono'>view_gap</span>", "What it said at 8.3", "What it says now"],
        [
            ("&ldquo;contradictions highlighted and linked&rdquo;", "no column to come from",
             "<b>partly served</b>: the linking half exists and is served in both directions. Three "
             "things are still not servable &mdash; nothing <i>detects</i> a disagreement, the derived "
             "reverse direction is scoped to one dossier, and nothing decides which side is wrong "
             "(A-02+A-08)"),
            ("&ldquo;beliefs with confidence band, validity interval and change conditions&rdquo;",
             "<span class='mono'>memory_item</span> schema-only, no writer, F-18's three columns "
             "deferred",
             "<b>two of the three now exist and none of the three is served here</b>: there is no "
             "<span class='mono'>memory_item</span> route, so a belief is recordable and not readable "
             "over HTTP. The third &mdash; a band &mdash; is <b>F-24</b>"),
            ("the other seven", "unchanged", "unchanged. The count is still <b>nine</b>"),
        ],
    )


def limitation_table() -> str:
    return table(
        ["#", "Limitation"],
        [
            ("1", "<b>Nothing calls the writer.</b> No <span class='mono'>memory_item</span> row has "
                  "ever been written outside a test and no route serves one. Every claim here is about "
                  "what the writer <i>refuses</i>, which is testable, not about what it will be asked "
                  "to record, which is not decided"),
            ("2", "<b>F-25</b>: a dangling <span class='mono'>evidence_ref.dossier_id</span> is refused "
                  "by nothing. The row is orphaned, unreachable through the route, and not reported"),
            ("3", "<b>F-24</b>: no confidence band. A belief carries one number on the confidence axis "
                  "and <span class='mono'>docs/10</span> &sect;3.1 calls a point estimate a defect"),
            ("4", "<b>No expiry.</b> <span class='mono'>expires_at</span> is absent and "
                  "<span class='mono'>valid_until</span> is not a substitute, so &ldquo;expiring "
                  "TTLs&rdquo; is still unservable"),
            ("5", "<span class='mono'>subject</span> is <b>not</b> validated against the instrument "
                  "master, and <span class='mono'>kind</span>/<span class='mono'>scope</span> are free "
                  "text. A belief about an instrument the system of record has never heard of is "
                  "recordable &mdash; the defect F-16 named for dossiers, which "
                  "<span class='mono'>open_dossier</span> refuses and this writer does not"),
            ("6", "A <b>negative confidence is accepted</b> and pinned by a test, with no "
                  "<span class='mono'>[0, 1]</span> bound anywhere. Deliberate; question 2 asks "
                  "whether it should stay that way"),
            ("7", "The reverse contradiction direction is derived <b>per dossier</b>. A disagreement "
                  "across two cases appears in neither view, and a reader who wants it from the "
                  "database alone has to scan"),
            ("8", "The checksum now covers <b>ten</b> fields, so pre-8.5 rows verify "
                  "<span class='mono'>False</span>. Nothing to backfill &mdash; both intelligence "
                  "tables are empty in production &mdash; but it changes what an approved batch "
                  "stored, and is disclosed as &sect;10.3 disclosed F-21's"),
            ("9", "Column <b>order</b> diverges between the two DDLs. Safe today because every "
                  "<span class='mono'>INSERT</span> names its columns and every "
                  "<span class='mono'>SELECT *</span> read is indexed by name; an "
                  "<span class='mono'>INSERT</span> without a column list would break it and nothing "
                  "refuses one being added"),
            ("10", "<span class='mono'>new_id</span>'s docstring lists neither "
                   "<span class='mono'>MEM</span> nor <span class='mono'>EV</span>. The prefixes work "
                   "&mdash; <span class='mono'>core/ids.py</span> does not validate them &mdash; but "
                   "the docstring lags by two writers, which is the F-12 defect class"),
            ("11", "<b>No live evidence.</b> No adapter changed, so no venue run speaks to this batch, "
                   "and the run this commit triggers is unread by &sect;10.8's rule"),
            ("12", "A confidence is stored in the <b>caller's own spelling</b>: "
                   "<span class='mono'>'0.72'</span> and <span class='mono'>'0.720000'</span> are "
                   "different stored strings for one number, and nothing normalises or compares them"),
        ],
    )


def decision_table() -> str:
    return table(
        ["#", "Question", "Recommendation"],
        [
            ("1", "Is Stage 8.5 approved, and how is F-18's partial closure recorded?",
             "<b>Approve, recorded as D-054</b>, with F-24 and F-25 disclosed as opened here, and with "
             "F-18 <b>narrowed rather than closed</b> &mdash; its first and third gaps closed, its "
             "second and fourth left open in the same row. The alternative closes F-18 outright, which "
             "retires a finding whose expiry and sufficiency halves have no column and no batch behind "
             "them: the error D-053's ruling 1 avoided by closing <span class='mono'>O-012</span> on "
             "the defect F-14 named and not on the system"),
            ("2", "Should a confidence outside <span class='mono'>[0, 1]</span> &mdash; including a "
                  "negative one &mdash; be refused?",
             "<b>Leave it unbounded</b>, keep the test that pins <span class='mono'>-0.5</span> "
             "storing, and publish the absence as limitation 6. No document states a range; the target's "
             "<span class='mono'>NUMERIC(6,5)</span> bounds magnitude and not sign; and inventing "
             "<span class='mono'>[0, 1]</span> puts a number in front of a judgement no ruling has "
             "made, which is what &sect;10.1 declined to do for "
             "<span class='mono'>sufficiency</span>. Bounding it needs three rulings the code cannot "
             "make: what <span class='mono'>1</span> means, whether "
             "<span class='mono'>9.99999</span> (currently accepted, and the target's own ceiling) is a "
             "defect, and whether a belief can legitimately carry a negative confidence as "
             "disconfirmation"),
            ("3", "Should F-25 be its own batch, or folded into the next one?",
             "<b>Its own small batch &mdash; 8.6 = F-25 alone</b>, in the shape 8.4 took for F-14's "
             "expensive half. The fix is one branch in "
             "<span class='mono'>record_evidence</span>, the refusal already has three precedents in "
             "this codebase to copy its wording from, and a batch of one attributable change is what "
             "makes a regression attributable &mdash; the reason D-052's ruling 2 scoped 8.4 to F-14 "
             "alone. Folding it in is cheaper in commits and worse in attribution, and is how a refusal "
             "ships beside an unrelated change nobody re-reads"),
            ("4", "What comes after that?",
             "<b><span class='mono'>expires_at</span>, as 8.7</b> &mdash; and not the sufficiency "
             "meter. It is F-18's remaining cheap half: &sect;5.3 already established that a nullable "
             "<span class='mono'>ADD COLUMN</span> needs no rebuild, so it is one migration statement, "
             "one writer argument and one refusal, and &ldquo;expiring TTLs&rdquo; is the one approved "
             "sentence in F-18 that still has no column at all. The meter should not be attempted "
             "before stage 10 defines it and stage 11 finalises V1&ndash;V3: a meter invented here "
             "would be a number in front of a judgement, which is why "
             "<span class='mono'>sufficiency</span> is still a string. The alternative worth naming is "
             "wiring <span class='mono'>retrieved_at</span> (&sect;11.12's limitation 1) &mdash; "
             "smaller, and it would make 8.4's number durable, but it writes evidence rows for data "
             "nobody has decided to collect, the step ruling 3 declined and ruling 4 declined again"),
        ],
    )


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())

    body = "".join([
        # -- 1 ------------------------------------------------------------------
        "<h3>1 &middot; What ruling 4 authorised, and what this batch therefore did not do"
        "<span class='tag'>D-052 r3 &middot; D-053 r4 &middot; docs/15 &sect;12.0</span></h3>"
        "<p>D-052's ruling 3 ordered <i>stage 10's <span class='mono'>memory_item</span> writer</i> as the "
        "batch after 8.4. D-053's ruling 4 re-ordered it against the alternative &mdash; wiring "
        "<span class='mono'>evidence_ref.retrieved_at</span> first &mdash; and declined that alternative, "
        "because it &ldquo;writes evidence rows for data nobody has decided to collect&rdquo;. &sect;11.14's "
        "row 4 states what the batch carries: <i>&ldquo;F-18's three columns plus "
        "<span class='mono'>evidence_ref.contradicts</span>&rdquo;</i>. That is what was built. Both "
        "tables below are published so a reviewer can check the second one against the tree rather than "
        "take the first on trust.</p>"
        + scope_tables()
        + "<div class='blocked'><b>Nothing calls the writer, by ruling.</b> A test "
          "(<span class='mono'>test_nothing_in_src_calls_it_yet</span>) <span class='mono'>rglob</span>s "
          "over <span class='mono'>src/nexus</span> and keeps saying so. No route serves "
          "<span class='mono'>memory_item</span>. A belief is now <b>recordable</b> and still not "
          "<b>readable over HTTP</b>, and the route's own gap text says that in those words.</div>"
        + verbatim("BLOCK I &mdash; captured: what names the writer, and what does not", BLOCK_I),

        # -- 2 ------------------------------------------------------------------
        "<h3>2 &middot; Migration 0005: four <span class='mono'>ADD COLUMN</span>s, no rebuild, no row "
        "copied<span class='tag'>docs/15 &sect;12.1 &middot; &sect;5.3</span></h3>"
        "<p><span class='mono'>0005_memory_beliefs</span> is <b>four</b> statements, "
        "<span class='mono'>requires=&quot;memory_item&quot;</span>, checksum "
        "<span class='mono'>4520e5b5e259eb4c868b70d1bfdc5ebdbac58f32d7083ea00cc4e980ac789c28</span>, "
        "pinned in <span class='mono'>test_schema_fidelity.py::CHECKSUMS</span>. It is the fifth entry in "
        "<span class='mono'>MIGRATIONS</span> and the <b>third</b> to name a "
        "<span class='mono'>requires</span> table &mdash; so it is the third that can be <i>deferred and "
        "reported</i> rather than silently bypassed, which is F-20's fix doing its job on a batch that "
        "never had to think about it.</p>"
        "<p>All four are <span class='mono'>ADD COLUMN</span>, which is what &sect;5.3's <b>executed</b> "
        "survey made cheap: SQLite permits a nullable column, a <span class='mono'>NOT NULL</span> column "
        "with a constant default, a self-referencing foreign key and a "
        "<span class='mono'>CHECK</span> on a new column, and refuses only "
        "<span class='mono'>ALTER COLUMN &hellip; TYPE</span> and <span class='mono'>ADD "
        "CONSTRAINT</span>. <b>Nothing here needs the create-copy-drop-rename rebuild "
        "<span class='mono'>0004</span> needed</b>, and no row is copied, because none of the four changes "
        "what an existing column means. Both intelligence tables are empty in production anyway "
        "(&sect;9.7 limitation 7, restated by D-052's ruling 4), so a rebuild would have cost nothing "
        "either &mdash; the reason it was not needed is structural, not fortunate.</p>"
        + "<div class='card'>" + column_table() + "</div>"
        + verbatim("BLOCK A &mdash; captured against a live post-migration database", BLOCK_A)
        + "<p>Two of those lines are the ones a reader should not skip. "
          "<span class='mono'>PRAGMA foreign_key_list(memory_item)</span> is <b>empty</b>: the table "
          "declares no foreign key at all, so <span class='mono'>cited_by</span> and "
          "<span class='mono'>superseded_by</span> are unenforced text and the writer is the only thing "
          "standing between a belief and a citation of evidence that does not exist (&sect;6). And "
          "<span class='mono'>ix_memory_created</span>, <span class='mono'>ix_memory_kind</span> and "
          "<span class='mono'>0004</span>'s <span class='mono'>CHECK</span> on "
          "<span class='mono'>confidence</span> all survive the append &mdash; executed, because "
          "&ldquo;an <span class='mono'>ADD COLUMN</span> cannot drop a "
          "<span class='mono'>CHECK</span>&rdquo; is exactly the kind of sentence that should not be "
          "published unverified.</p>",

        # -- 3 ------------------------------------------------------------------
        "<h3>3 &middot; Why the Postgres target grows inline, and what that costs"
        "<span class='tag'>F-15 &middot; test_schema_fidelity.py</span></h3>"
        "<p>The four columns are declared <b>inline</b> in <span class='mono'>migrations/0002_memory.sql</span>'s "
        "existing <span class='mono'>CREATE TABLE</span>s. There is no "
        "<span class='mono'>0005_memory_beliefs.sql</span>, and the reason is a hole in the gate rather "
        "than a preference: the fidelity test parses <span class='mono'>CREATE TABLE IF NOT EXISTS</span> "
        "<b>only</b> &mdash; a limitation &sect;9.2 recorded when it was written &mdash; so an ALTER-only "
        "target migration would be <b>invisible</b> to it. The four columns would exist in SQLite and be "
        "unasserted in the mirror, which is precisely the defect F-15 named.</p>"
        "<p>The cost is that column <b>order</b> now differs between the two DDLs, visible in the stored "
        "DDL's own tail: <span class='mono'>&hellip; audit_ref TEXT\\n, valid_from TEXT, valid_until TEXT, "
        "change_conditions TEXT NOT NULL DEFAULT ''</span>. That was checked rather than assumed, and all "
        "three checks were run:</p>"
        + table(["What could break on a column-order divergence", "Measured"],
                [
                    ("an <span class='mono'>INSERT</span> without a column list",
                     "<b>none exists.</b> A grep for <span class='mono'>INSERT INTO &lt;table&gt; "
                     "VALUES</span> returns nothing anywhere in <span class='mono'>src/nexus</span>"),
                    ("a <span class='mono'>SELECT *</span> read indexed by position",
                     "<span class='mono'>SELECT *</span> <b>is</b> used &mdash; "
                     "<span class='mono'>dossiers</span>, <span class='mono'>evidence_refs</span>, "
                     "<span class='mono'>memory_items</span>, <span class='mono'>get_memory_item</span> "
                     "&mdash; but every one converts with <span class='mono'>dict(row)</span> and is then "
                     "indexed <b>by name</b>"),
                    ("positional row indexing anywhere in <span class='mono'>src/</span>",
                     "one place: <span class='mono'>archive/parquet_store.py:517+</span>, over a duckdb "
                     "result whose <span class='mono'>SELECT</span> lists its fifteen columns explicitly. "
                     "A different store, an explicit order, unaffected by anything SQLite appends"),
                    ("the fidelity test itself",
                     "compares names, types, nullability and foreign keys and <b>not</b> order, which is "
                     "what makes the divergence assertable rather than merely tolerated"),
                ])
        + "<div class='blocked'><b>A correction to this board's own first draft.</b> An earlier version of "
          "&sect;12.1 claimed &ldquo;<span class='mono'>SELECT *</span> is used nowhere in "
          "<span class='mono'>src/</span>&rdquo;. It is used in at least ten places. The claim that "
          "survives is the narrower and true one &mdash; nothing depends on <i>position</i> &mdash; and it "
          "is only true because every read goes through <span class='mono'>dict(row)</span>. The grep that "
          "falsified the draft is the reason the board carries the corrected sentence.</div>",

        # -- 4 ------------------------------------------------------------------
        "<h3>4 &middot; Three things 0005 deliberately does not add"
        "<span class='tag'>written into the migration's own comment</span></h3>"
        "<p>Each omission is argued inside <span class='mono'>_MEMORY_BELIEFS</span> in "
        "<span class='mono'>store/schema.py</span>, so a reader who meets the migration without this board "
        "still meets the reason.</p>"
        + table(["Not added", "Why"],
                [
                    ("<span class='mono'>expires_at</span>",
                     "F-18's second gap is that no expiry column exists anywhere, and &sect;5.3 lists it "
                     "among the cheap additions &mdash; but it is not one of &ldquo;the three "
                     "columns&rdquo; ruling 4 named. <b><span class='mono'>valid_until</span> is not a "
                     "substitute and the difference is the whole point</b>: "
                     "<span class='mono'>valid_until</span> says until when a claim holds <b>in the "
                     "world</b>, while an expiry says when <b>this system</b> should stop serving the row. "
                     "A belief valid until 2027 whose evidence went stale yesterday is exactly the row the "
                     "two columns disagree about, and only one of them exists. "
                     "<span class='mono'>docs/10</span> &sect;3.1's &ldquo;expiring TTLs&rdquo; asks for "
                     "the second. <b>The gap stays open.</b>"),
                    ("<span class='mono'>confidence_low</span> / "
                     "<span class='mono'>confidence_high</span>",
                     "<b>F-24</b>, &sect;13. Two more columns are not this batch's ruling either, and the "
                     "<i>shape</i> of a band has no ruling behind it."),
                    ("an index on <span class='mono'>valid_until</span>",
                     "Nothing queries by validity yet, so <span class='mono'>memory_items()</span> scans. "
                     "An index with no reader behind it is machinery nobody reads &mdash; the reasoning "
                     "D-052's ruling 4 used to decline a periodic checksum audit, applied to a cheaper "
                     "object. The scan is written down in the store's docstring instead of being left for "
                     "whoever hits it to discover, which is what "
                     "<span class='mono'>dossiers()</span> does for its own scan."),
                ]),

        # -- 5 ------------------------------------------------------------------
        "<h3>5 &middot; The writer's shape, and why no "
        "<span class='mono'>RejectReason</span> is spent"
        "<span class='tag'>intelligence/memory.py &middot; 471 lines</span></h3>"
        "<p><span class='mono'>intelligence/memory.py</span> follows the shape "
        "<span class='mono'>dossier.py</span> and <span class='mono'>evidence.py</span> established: a "
        "grounded module docstring, <span class='mono'>__all__</span> of <b>12</b> names, constants before "
        "code, a frozen <span class='mono'>slots=True</span> receipt with "
        "<span class='mono'>to_dict()</span>, and one public keyword-only function whose every default sits "
        "on the side that claims least.</p>"
        + verbatim("the signature, verbatim", """
record_memory_item(*, audit, store, body, kind="OBSERVATION", scope="GLOBAL", subject="",
                   confidence=None, valid_from=None, valid_until=None, change_conditions="",
                   evidence_ids=(), payload=None, memory_id=None, actor="MEMORY") -> MemoryReceipt
""")
        + table(["Property", "Value", "Why it is that value"],
                [
                    ("parameters", "<b>14</b>, all keyword-only",
                     "a positional call to a writer with this many optional arguments is a call nobody can "
                     "read back"),
                    ("<span class='mono'>MemoryReceipt</span> fields", "<b>16</b>",
                     "three of which a caller cannot influence at all: "
                     "<span class='mono'>superseded_by</span> is always <span class='mono'>None</span>, "
                     "<span class='mono'>cited_by</span> always <span class='mono'>()</span>, "
                     "<span class='mono'>validity_open_ended</span> always derived"),
                    ("refusals", "<b>17</b> <span class='mono'>raise ValueError</span> sites",
                     "each citing the document that requires the thing refused"),
                    ("<span class='mono'>RejectReason</span> members spent", "<b>0</b>",
                     "these are programmer errors at an internal boundary, not operational conditions, and "
                     "a reason code is vocabulary the audit log and the UI both consume. A test asserts the "
                     "module neither imports <span class='mono'>nexus.core.errors</span> nor names a "
                     "<span class='mono'>RejectReason.</span> member"),
                    ("timestamps", "<b>inside</b> the audited event",
                     "so a replay after a gap reproduces the row byte-identically instead of restamping it "
                     "with the replay's clock &mdash; &sect;12, measured at 1.05 s"),
                    ("pinned payload keys", "written <b>last</b>",
                     "so a caller's <span class='mono'>payload</span> cannot overwrite "
                     "<span class='mono'>evidence_ids</span>, "
                     "<span class='mono'>validity_open_ended</span> or "
                     "<span class='mono'>cited_by</span>: a claim that can be talked out of its own "
                     "qualifications is a claim that will be"),
                    ("write order", "<span class='mono'>write_with_audit(&hellip;)</span> is the last "
                     "statement", "L-2: audit entry first, projection second"),
                    ("<span class='mono'>PROJECTABLE</span>", "<b>14 &rarr; 15</b> keys",
                     "<span class='mono'>memory.recorded &rarr; memory_item</span>, so a replay from the "
                     "chain alone reproduces the row"),
                ])
        + "<div class='blocked'><b>A test that failed on the writer's own docstring.</b> The first form of "
          "the no-<span class='mono'>RejectReason</span> assertion was "
          "<span class='mono'>assert &quot;RejectReason&quot; not in source</span>, and it failed &mdash; "
          "because the docstring legitimately <i>names</i> the vocabulary it does not spend. A source-text "
          "guard has to assert the import line and the attribute use, not the word. Recorded here because "
          "the same shape of guard exists in three other test files.</div>",

        # -- 6 ------------------------------------------------------------------
        "<h3>6 &middot; A confidence is not a claim by itself: three refusals, three messages"
        "<span class='tag'>docs/10 &sect;3.1 &middot; docs/03 &sect;7</span></h3>"
        "<p><span class='mono'>docs/10</span> &sect;3.1, approved at <b>D-035</b>: <i>&ldquo;confidence as "
        "a band with validity interval and change conditions; a point estimate without them is a "
        "defect.&rdquo;</i> The sentence is about <b>three columns at once</b>, so no single "
        "<span class='mono'>CHECK</span> can express it. That is why the three new columns are nullable or "
        "defaulted while the <b>writer</b> refuses the combination &mdash; and why the refusal lives in "
        "<span class='mono'>intelligence/memory.py</span> rather than in "
        "<span class='mono'>store/schema.py</span>. A column cannot refuse a row that fills it badly.</p>"
        + "<div class='card'>" + refusal_table() + "</div>"
        + verbatim("BLOCK C &mdash; captured: one refusal at a time, each naming exactly one missing thing",
                   BLOCK_C)
        + "<p><b>Three refusals, three messages, never one.</b> A test calls the writer with a confidence "
          "and all three omitted and asserts the message names <i>exactly one</i> of them, then repeats for "
          "each. Folding three conditions into one string tells a caller that something is wrong without "
          "telling them what to change, and this batch's whole subject matter is records a reviewer cannot "
          "act on. A confidence of <span class='mono'>None</span> requires <b>none</b> of the three: an "
          "<span class='mono'>OBSERVATION</span> has no validity interval and needs none, which is why the "
          "columns are nullable rather than <span class='mono'>NOT NULL</span>.</p>",

        # -- 7 ------------------------------------------------------------------
        "<h3>7 &middot; Confidence as text: enforcing "
        "<span class='mono'>NUMERIC(6,5)</span> at the boundary"
        "<span class='tag'>D-050 &middot; D-051 &sect;9.2 &middot; 27 probed inputs</span></h3>"
        "<p>D-050 accepted <span class='mono'>NUMERIC(6,5)</span> for the target and D-051 disclosed that "
        "the applied SQLite column stays <span class='mono'>TEXT</span> plus a "
        "<span class='mono'>CHECK</span>, because SQLite's NUMERIC affinity stores "
        "<span class='mono'>'0.5'</span> as a <span class='mono'>real</span> and that would make it the "
        "only float-backed numeric column in the schema. The consequence this batch had to handle is that "
        "<b>the applied column accepts things the target would reject or silently round</b>, and a writer "
        "that stores only what SQLite accepts would write rows a PostgreSQL deploy refuses.</p>"
        "<p><span class='mono'>NUMERIC(6,5)</span> means six significant digits of which five are after the "
        "point &mdash; i.e. <b>exactly one digit before it</b>. The corrected rule, from the "
        "<b>normalised</b> <span class='mono'>Decimal</span>:</p>"
        + verbatim("the rule, and the draft that got it wrong first", """
  decimal places      = max(0, -exponent)          must not exceed CONFIDENCE_SCALE              (5)
  digits before point = len(digits) + exponent     must not exceed PRECISION - SCALE        (6-5 = 1)

  The first implementation compared SIGNIFICANT DIGITS against CONFIDENCE_PRECISION (6), which would have
  accepted '10.0000' — six significant digits, and a value the target cannot store. The axis that matters
  is digits before the point, because that is what PRECISION minus SCALE buys.

  Decimal.normalize().as_tuple() types the exponent as Literal['n','N','F'] | int, so the arithmetic needs
  an explicit isinstance(exponent, int) guard. It is unreachable from confidence_text, which refuses
  non-finite values first, and mypy is right to want it anyway.
""")
        + verbatim("BLOCK D &mdash; captured: 27 inputs, 11 accepted, 16 refused", BLOCK_D)
        + "<p>Two parametrisation traps are worth naming because both produced a test that passed while "
          "asserting the wrong thing. <b>Magnitude and scale are different axes</b>: a first draft used "
          "<span class='mono'>9.9999999</span> as a magnitude case, but that value has one digit before the "
          "point and fails on <i>scale</i> &mdash; the magnitude case is "
          "<span class='mono'>99.99999</span>. And <b>a <span class='mono'>bool</span> is an "
          "<span class='mono'>int</span> in Python</b>, so <span class='mono'>confidence=True</span> would "
          "have stored <span class='mono'>1</span>: a certainty nobody asserted.</p>",

        # -- 8 ------------------------------------------------------------------
        "<h3>8 &middot; The applied <span class='mono'>CHECK</span> still leaks, and the writer catches "
        "what it leaks<span class='tag'>D-051 limitation 1 &middot; measured</span></h3>"
        "<p>D-051 disclosed that the <span class='mono'>CHECK</span> <span class='mono'>0004</span> added "
        "is <i>&ldquo;a floor and not validation&rdquo;</i> because it leaks "
        "<span class='mono'>'0.5abc'</span>. This batch needed to know whether a second check was "
        "redundant, so both were run against the same eight values on a live post-0005 database.</p>"
        + verbatim("BLOCK B &mdash; captured: the database and the writer, side by side", BLOCK_B)
        + "<p>The two rows that matter are the last two. D-051 disclosed that <span class=\"mono\">0004</span>&rsquo;s <span class=\"mono\">CHECK</span> is &ldquo;a floor and not validation&rdquo; because it leaks <span class=\"mono\">&lsquo;0.5abc&rsquo;</span>. It still leaks it, and it also stores <span class=\"mono\">&lsquo;1e400&rsquo;</span> &mdash; a value the portable target would reject outright. <span class=\"mono\">confidence_text</span> refuses both. That is the only justification for having two checks, and it is measured here rather than argued.</p>",

        # -- 9 ------------------------------------------------------------------
        "<h3>9 &middot; The interval is about the world, not about this system's clock"
        "<span class='tag'>docs/15 &sect;12.2 decision 2</span></h3>"
        "<p><span class='mono'>valid_from</span> and <span class='mono'>valid_until</span> never default to "
        "<span class='mono'>created_at</span>, in either direction. Collapsing the two would be F-14's "
        "mistake in a different pair of columns: one field is ours and one is not, and a reader who cannot "
        "tell them apart cannot measure anything.</p>"
        + verbatim("BLOCK E &mdash; captured: seven intervals, four accepted and three refused", BLOCK_E)
        + table(["Decision", "Why"],
                [
                    ("an interval that already ended is <b>dated, not refused</b>",
                     "a belief whose validity lapsed is a fact about the past, and refusing to record it "
                     "would be the system editing history"),
                    ("an interval that starts in the future is accepted",
                     "the same reasoning on the other side of the clock"),
                    ("<span class='mono'>valid_until &lt;= valid_from</span> is refused, "
                     "<b>including equality</b>",
                     "a zero-length interval asserts a belief that held for no time at all, which is a "
                     "different statement from an open-ended one and is not this system's to make on a "
                     "caller's behalf"),
                    ("naive datetimes are refused <b>before</b> any comparison",
                     "so the refusal is about the value and not about an ordering computed across two "
                     "clocks"),
                    ("<span class='mono'>validity_open_ended</span> is derived and pinned",
                     "<i>&ldquo;no end was stated&rdquo;</i> and <i>&ldquo;no end exists&rdquo;</i> are "
                     "different claims, and only the first is knowable here"),
                ]),

        # -- 10 -----------------------------------------------------------------
        "<h3>10 &middot; Provenance is checked against the store, and recording is not editing"
        "<span class='tag'>docs/15 &sect;12.2 decisions 3 and 4</span></h3>"
        "<p>Every <span class='mono'>evidence_ids</span> entry must name a row "
        "<span class='mono'>evidence_ref</span> actually holds. An id the store has never held is refused, "
        "and so is a list mixing one real id with one invented one. This is the posture "
        "<span class='mono'>open_dossier</span> takes toward <span class='mono'>instrument_id</span> "
        "(&sect;10.1) and the reason is the same: <span class='mono'>PRAGMA foreign_keys</span> is "
        "deliberately <b>off</b> for chain-order recovery (<span class='mono'>docs/13</span> &sect;2.5), so "
        "SQLite accepts a dangling parent without comment and the writer is the only place that can refuse "
        "one. <span class='mono'>memory_item</span> declares <b>no</b> foreign keys at all, so without this "
        "check a belief could rest on evidence that does not exist and nothing anywhere would say so.</p>"
        "<p>A caller-supplied <span class='mono'>memory_id</span> that already exists is refused: "
        "<i>&ldquo;the store writes with <span class='mono'>INSERT OR REPLACE</span> because it is a "
        "projection, so a second record would restate the first row's body and confidence. The audit chain "
        "would keep both events, but the row a reviewer reads would no longer be the row that was "
        "written.&rdquo;</i> Memory is superseded, never edited in place (&sect;5.1); "
        "<span class='mono'>superseded_by</span> stays <span class='mono'>None</span> because setting it is "
        "a second verb this batch was not ruled into.</p>"
        "<div class='blocked'><b>The asymmetry with <span class='mono'>evidence_ref</span> is deliberate "
        "and measured.</b> Re-recording under an existing <span class='mono'>evidence_id</span> "
        "<b>replaces</b> the projection row &mdash; one row, two chain entries &mdash; and the new row "
        "still verifies against its own checksum. That is a restatement of one observation: same id, same "
        "subject, corrected values. &sect;5.1's supersede-don't-edit rule is about <i>beliefs</i>, whose "
        "whole content is the claim. Tests pin both sides so the difference cannot drift into an "
        "accident.</div>",

        # -- 11 -----------------------------------------------------------------
        "<h3>11 &middot; <span class='mono'>contradicts</span>: one direction stored, the other derived"
        "<span class='tag'>docs/10 &sect;3.1 &middot; docs/03 &sect;8 &middot; F-21</span></h3>"
        "<p><span class='mono'>docs/10</span> &sect;3.1 asks the dossier view for <i>&ldquo;contradictions "
        "highlighted and linked&rdquo;</i> and <span class='mono'>docs/03</span> &sect;8 asks the evidence "
        "graph for the same. Before this batch nothing recorded that two sources disagree, so nothing could "
        "be linked and nothing could be highlighted.</p>"
        "<p>It points <b>one way</b> and there is no back-link column, which is a shape and not an "
        "omission: a mutual disagreement is <b>two calls</b>, each recording one row's own claim, and "
        "neither row is edited by the other. A second column would double every write and create two places "
        "for one fact to disagree with itself. <span class='mono'>None</span> means <i>no disagreement was "
        "claimed</i>, which is not the same as claiming that none exists &mdash; nothing in this system can "
        "establish that, and the column does not pretend to.</p>"
        + verbatim("BLOCK F &mdash; captured: the stored direction, the two refusals, and the checksum",
                   BLOCK_F)
        + "<p><b>The checksum widened from nine covered fields to ten.</b> "
          "<span class='mono'>contradicts</span> joined <span class='mono'>CHECKSUMMED_FIELDS</span>, "
          "because a stored column outside that tuple is a column that can change undetected &mdash; which "
          "is F-21, and F-21's lesson was that the tuple and the table must move together. "
          "<span class='mono'>evidence_ref</span> now has <b>12</b> stored columns and the tuple covers "
          "<b>10</b>; the two outside it are <span class='mono'>checksum</span> (excluded by definition) "
          "and <span class='mono'>audit_ref</span> (excluded because the audit entry is written first and "
          "its ref does not exist yet when the hash is computed). A test derives the covered set from the "
          "live table via <span class='mono'>PRAGMA table_info</span> and asserts the complement is exactly "
          "those two, so a thirteenth column cannot arrive without a decision.</p>"
        "<div class='blocked'><b>Consequence, published rather than buried:</b> "
        "<span class='mono'>verify_evidence_checksum</span> now reports "
        "<span class='mono'>False</span> for any row written before this change, because the hash input "
        "changed. There is nothing to backfill &mdash; both intelligence tables are empty in production "
        "(D-052's ruling 4) &mdash; and this is the same disclosure &sect;10.3 made for F-21. A row with no "
        "checksum at all also verifies <span class='mono'>False</span>, which is the fail-closed side.</div>",

        # -- 12 -----------------------------------------------------------------
        "<h3>12 &middot; The route, and the honest scope of what it derives"
        "<span class='tag'>13 routes, unchanged &middot; view_gaps still nine</span></h3>"
        "<p><span class='mono'>GET /v1/intelligence/dossiers</span> and "
        "<span class='mono'>&hellip;/{dossier_id}</span> gained three things and <b>no</b> new route: "
        "<span class='mono'>evidence[].contradicts</span> (the stored direction), "
        "<span class='mono'>evidence[].contradicted_by</span> (the reverse, <b>derived by a scan of the "
        "served dossier's own rows</b>, sorted) and <span class='mono'>contradiction_count</span> (how many "
        "distinct unordered pairs the case holds).</p>"
        + table(["Counting rule", "Why"],
                [
                    ("two rows pointing at one common row are <b>one pair each</b>",
                     "not one pair between them &mdash; the pairs are (A,C) and (B,C)"),
                    ("a mutual disagreement is <b>one</b> pair, not two",
                     "counting it from both directions would double every honest disagreement and halve "
                     "the meaning of the number"),
                    ("pairs are de-duplicated as sorted tuples",
                     "<span class='mono'>mypy</span> wanted an explicit "
                     "<span class='mono'>tuple[str, str]</span>, so the sorted pair is indexed rather than "
                     "splatted &mdash; a two-line fix to a type error that would otherwise have been "
                     "silenced"),
                ])
        + "<div class='blocked'>The derivation's scope is stated <b>in the response</b> rather than left to "
          "be discovered, because serving a partial fact silently is the F-13 defect class: <i>the reverse "
          "direction is derived inside this dossier only. A contradiction recorded between rows in two "
          "different cases appears in neither scan.</i> That is asserted by "
          "<span class='mono'>test_a_contradiction_across_two_cases_appears_in_neither_scan</span>, which "
          "opens two dossiers, records the disagreement across them, and checks that <b>both</b> views "
          "report nothing.</div>"
        + "<p><b>Nothing detects a disagreement and nothing decides a winner.</b> "
          "<span class='mono'>contradicts</span> records a claim made by whoever wrote the row, so two "
          "sources that contradict each other and were never linked stay unlinked; and "
          "<span class='mono'>docs/12</span> &sect;1.3's law (A-02+A-08) is that <b>no gate can be "
          "satisfied by a confidence value</b>, so the higher-confidence row does not win here and no code "
          "computes one. <span class='mono'>contradiction_count</span> is a count, not a verdict, and the "
          "gap text says so in those words.</p>"
        + "<div class='card'>" + gap_table() + "</div>"
        + "<p>Two tests pin gap prose by equality plus a list of literals "
          "(<span class='mono'>&quot;has now landed&quot;</span>, "
          "<span class='mono'>&quot;Nothing is scheduled&quot;</span>, "
          "<span class='mono'>&quot;receipt time&quot;</span>, "
          "<span class='mono'>&quot;re-evaluates&quot;</span>, "
          "<span class='mono'>&quot;stays LIVE&quot;</span>, and now "
          "<span class='mono'>&quot;contradicts&quot;</span>, "
          "<span class='mono'>&quot;A-02+A-08&quot;</span>, "
          "<span class='mono'>&quot;memory.recorded&quot;</span>, "
          "<span class='mono'>&quot;no memory_item route&quot;</span>, "
          "<span class='mono'>&quot;F-24&quot;</span>). They were <b>re-aimed, not deleted</b>: a test "
          "that asserts a future batch has not happened yet must be pointed at the next thing that has not "
          "happened, or the route's honesty becomes unasserted the moment one gap closes.</p>",

        # -- 13 -----------------------------------------------------------------
        "<h3>13 &middot; F-24 &mdash; a belief still carries exactly one confidence number "
        "<span class='tag'>NEW &middot; docs/15 &sect;12.8</span></h3>"
        "<p><span class='mono'>docs/10</span> &sect;3.1, approved at <b>D-035</b>, asks for "
        "<i>&ldquo;confidence as a band with validity interval and change conditions; a point estimate "
        "without them is a defect&rdquo;</i>. This batch delivered the <b>time axis</b> and left the "
        "<b>confidence axis</b> alone. So the sentence is now half satisfied in a way that is easy to "
        "misread as fully satisfied: the point estimate has its interval and its conditions, and it is "
        "<b>still a point estimate</b>.</p>"
        + "<div class='card'>" + f24_table() + "</div>"
        + "<p><b>Why it is recorded and not fixed.</b> Two more columns are not this batch's ruling &mdash; "
          "&sect;11.14 row 4 names <i>&ldquo;three columns plus "
          "<span class='mono'>evidence_ref.contradicts</span>&rdquo;</i> &mdash; and the <b>shape</b> of a "
          "band is a design decision with no ruling behind it: "
          "<span class='mono'>confidence_low</span>/<span class='mono'>confidence_high</span>, one value "
          "plus a width, or a distribution. Each implies different refusals in a writer whose whole posture "
          "is that a default nobody argued for is a claim nobody made. "
          "<span class='mono'>NUMERIC(6,5)</span>'s one-digit-before-the-point ceiling constrains the "
          "answer too: a band whose bounds are both <span class='mono'>NUMERIC(6,5)</span> cannot express "
          "&ldquo;0.7 &plusmn; 0.4&rdquo; without deciding what the bounds mean.</p>"
        "<div class='blocked'><b>What is true today, measured:</b> a belief records as "
        "<span class='mono'>confidence=&quot;1&quot;</span> &mdash; the ceiling of the target's magnitude "
        "&mdash; with an interval and change conditions, and <b>nothing anywhere in the system can express "
        "that the recorder was uncertain about the number itself</b>. "
        "<span class='mono'>docs/10</span> &sect;3.1 calls that a defect. It is <b>F-24</b>, and the next "
        "finding id after it is <b>F-25</b>.</div>",

        # -- 14 -----------------------------------------------------------------
        "<h3>14 &middot; F-25 &mdash; a dangling <span class='mono'>dossier_id</span> is refused by nothing"
        "<span class='tag'>NEW &middot; docs/15 &sect;12.9 &middot; found by executing</span></h3>"
        "<p>Found by <b>executing the contrast</b> this batch created, not by reading: 8.5 added a refusal "
        "for a dangling <span class='mono'>contradicts</span>, which makes &ldquo;which parents does this "
        "codebase actually check?&rdquo; answerable by running it. Four probes, one per parent reference, "
        "in one process against one store.</p>"
        + "<div class='card'>" + f25_table() + "</div>"
        + verbatim("BLOCK G &mdash; captured: three refusals and one acceptance, in one run", BLOCK_G)
        + "<p>So an evidence row can be written against a case that does not exist. The consequences are "
          "concrete rather than theoretical: <span class='mono'>GET "
          "/v1/intelligence/dossiers/{id}</span> returns <b>404</b> for that id, so the row is unreachable "
          "through the route that serves evidence; "
          "<span class='mono'>evidence_refs(dossier_id=&hellip;)</span> finds it only if a caller already "
          "knows the invented id; and <span class='mono'>ix_evidence_dossier</span> indexes a value that "
          "matches nothing. The row is not corrupt &mdash; it verifies against its own checksum &mdash; it "
          "is <b>orphaned</b>, and nothing reports it.</p>"
        "<p>The reason it is missing is ordinary and is stated rather than excused: "
        "<span class='mono'>dossier_id</span> is <b>optional</b> on "
        "<span class='mono'>record_evidence</span> &mdash; <span class='mono'>None</span> means the "
        "evidence belongs to no case yet, which is a legitimate state &mdash; so the check is "
        "<span class='mono'>if dossier_id is not None and store.get_dossier(dossier_id) is None: "
        "refuse</span>, one more branch than the others. And 8.2 wrote that writer before any dossier "
        "existed to point at. <span class='mono'>PRAGMA foreign_keys</span> is off by design "
        "(<span class='mono'>docs/13</span> &sect;2.5: recovery re-projects in chain order, which is not "
        "always parent-first, and a hard FK failure mid-recovery would be worse than the inconsistency it "
        "prevents), so the writer is the only place any of these can be refused &mdash; which is the same "
        "reasoning that produced the other three.</p>"
        "<div class='blocked'><b>Recorded, not fixed.</b> Fixing it inside this batch would have changed a "
        "writer <b>D-052 approved</b>, in a batch ruled to be about "
        "<span class='mono'>memory_item</span>. &sect;12.13 question 3 recommends <b>8.6 = F-25 alone</b>, "
        "in the shape 8.4 took for F-14's expensive half.</div>",

        # -- 15 -----------------------------------------------------------------
        "<h3>15 &middot; A replay from the chain alone reproduces the row, including its clock"
        "<span class='tag'>L-2 &middot; reproject_missing</span></h3>"
        "<p>The audit chain is the record and the operational tables are a projection of it (R-1). That is "
        "only true if deleting the projection and replaying reproduces the row &mdash; including "
        "<span class='mono'>created_at</span>, which is why the timestamp rides <b>inside</b> the audited "
        "event rather than being stamped by the projection.</p>"
        + verbatim("BLOCK H &mdash; captured: DELETE both tables, wait 1.05 s, reproject from the chain",
                   BLOCK_H),

        # -- 16 -----------------------------------------------------------------
        "<h3>16 &middot; The gate, and the numbers re-derived rather than remembered"
        "<span class='tag'>docs/15 &sect;12.10</span></h3>"
        + verbatim("captured: the four gates and the seven per-file counts", BLOCK_GATE)
        + table(["Measure", "At 8.4 (<span class='mono'>c0bfaea</span>)", "Now", "How it was derived"],
                [
                    ("offline tests", "1294 passed, 2 skipped", "<b>1394 passed, 2 skipped</b>",
                     "<span class='mono'>.venv/bin/python -m pytest</span>, run <b>bare</b>"),
                    ("new test functions", "&mdash;", "<b>+76</b>",
                     "a regex count of <span class='mono'>def test_</span> per file, diffed against "
                     "<span class='mono'>git show HEAD:&lt;file&gt;</span>"),
                    ("new executed cases", "&mdash;", "<b>+100</b>",
                     "1394 &minus; 1294. The gap between 76 and 100 is parametrisation &mdash; the "
                     "confidence table alone is 27 inputs across three axes"),
                    ("<span class='mono'>src</span>", "61 files / 15,312 lines",
                     "<b>62 files / 16,181 lines</b>",
                     "<span class='mono'>git archive HEAD backend/src backend/tests</span> into a scratch "
                     "directory for the baseline, then a script summing "
                     "<span class='mono'>len(read_text().splitlines())</span> over "
                     "<span class='mono'>rglob('*.py')</span>"),
                    ("<span class='mono'>tests</span>", "30 files / 17,725 lines",
                     "<b>31 files / 19,121 lines</b>", "the same script"),
                    ("<span class='mono'>mypy src</span>", "61 files", "<b>62 files</b>",
                     "<span class='mono'>intelligence/memory.py</span> is the new one"),
                    ("<span class='mono'>ruff format --check</span>", "91 files", "<b>93 files</b>",
                     "both new files are formatted"),
                    ("migrations", "4", "<b>5</b>",
                     "<span class='mono'>[(m.version, m.statements, m.requires, m.checksum) for m in "
                     "MIGRATIONS]</span>"),
                    ("working tree", "&mdash;", "<b>14 files, +2,343 / &minus;39</b> in "
                     "<span class='mono'>backend/</span>", "<span class='mono'>git diff HEAD --stat</span>"),
                ])
        + "<div class='blocked'><b>Why every one of those has a command beside it.</b> &sect;10.4 exists "
          "because <b>sixteen</b> numbers published in 8.4 were stale &mdash; counts written from memory or "
          "from one partial read. <span class='mono'>bc</span> is not installed in this sandbox, so the line "
          "counts are summed in Python rather than in shell arithmetic, and the 8.4 baseline is read out of "
          "<span class='mono'>git archive</span> rather than out of this board's predecessor.</div>"
        + "<p><span class='mono'>test_dossier_writer.py</span>'s change is a <b>replacement</b> and is "
          "worth stating because it is the only test this batch deleted. The test that asserted opening a "
          "dossier writes no <span class='mono'>memory_item</span> row asserted it against the "
          "<i>schema</i>, and 0005 changed the schema. It is now "
          "<span class='mono'>test_opening_a_dossier_still_writes_no_memory_item</span>, which asserts "
          "against the <i>writer</i>: the fact under test is that one verb does not perform another, and "
          "pinning that to a column list would make it fail for the wrong reason every time a column "
          "arrives.</p>",

        # -- 17 -----------------------------------------------------------------
        "<h3>17 &middot; Twenty tampered sites, twenty caught, zero silent passes"
        "<span class='tag'>/tmp/tamper85.py &middot; docs/15 &sect;12.11</span></h3>"
        "<p>Every load-bearing decision in this batch was falsified by editing the source and re-running "
        "the six affected test files (318 tests). Each site is applied to a fresh copy of the original, "
        "asserted to match <b>exactly once</b> before it is written, and restored afterwards &mdash; the "
        "shape defect 35 was: an earlier negative-control loop backed up each file <i>after</i> mutating it "
        "and left six mutations in the tree.</p>"
        + verbatim("captured: all twenty sites, the failure count each produced, and the tests that caught "
                   "it", BLOCK_TAMPER)
        + "<p>Two of the twenty are the ones a reviewer would expect to be <b>unfalsifiable</b>:</p>"
        + table(["Tamper", "Why it should have been invisible", "Why it was not"],
                [
                    ("dropping <span class='mono'>contradicts</span> from "
                     "<span class='mono'>CHECKSUMMED_FIELDS</span>",
                     "no test asserts on that column's presence in a hash input",
                     "<span class='mono'>test_the_covered_set_is_derived_from_the_live_table</span> "
                     "computes the <b>complement</b> of the tuple against "
                     "<span class='mono'>PRAGMA table_info</span> and asserts it is exactly "
                     "<span class='mono'>checksum</span> and <span class='mono'>audit_ref</span>. A "
                     "narrowed tuple changes the complement, so the failure names the mechanism rather "
                     "than the field"),
                    ("removing one <span class='mono'>ALTER</span> from the migration",
                     "the migration is a string in a Python file; nothing executes it in isolation",
                     "caught <b>45</b> and <b>96</b> times over, because the migration's own checksum is "
                     "pinned in <span class='mono'>CHECKSUMS</span> <i>and</i> the columns are used by "
                     "every writer test"),
                    ("forcing <span class='mono'>contradiction_count</span> to 0",
                     "a count of zero looks like an honest empty",
                     "three tests fail, including the cross-case one &mdash; which is the test that would "
                     "<i>pass</i> on a naive implementation and <b>fail</b> on an honest one, so it is "
                     "written the other way round on purpose"),
                ])
        + "<div class='blocked'><b>The checksum moved during this batch, twice, from formatting.</b> "
          "Editing anything inside a migration's SQL string changes its checksum &mdash; including "
          "rewrapping a <span class='mono'>--</span> comment, which is what an E501 fix and then "
          "<span class='mono'>ruff format</span> did to 0005. It went "
          "<span class='mono'>8f0adee4&hellip;</span> &rarr; "
          "<span class='mono'>4520e5b5&hellip;</span> with no semantic change at all. The new value was "
          "<b>re-derived from <span class='mono'>MIGRATIONS</span></b> and republished, not restored by "
          "hand, and <span class='mono'>CHECKSUMS</span> now also asserts "
          "<span class='mono'>counts[&quot;0005_memory_beliefs&quot;] == 4</span> so the statement count "
          "is pinned beside the hash.</div>",

        # -- 18 -----------------------------------------------------------------
        "<h3>18 &middot; Limitations of this batch<span class='tag'>docs/15 &sect;12.12</span></h3>"
        "<p>Twelve, published in full rather than summarised. Limitations 2 and 3 are the two findings; 1, "
        "4, 5 and 6 are the four things a reviewer is most likely to ask about.</p>"
        + "<div class='card'>" + limitation_table() + "</div>",

        # -- 19 -----------------------------------------------------------------
        "<h3>19 &middot; Decision requested &mdash; four questions, each with one marked recommendation"
        "<span class='tag'>docs/15 &sect;12.13 &middot; D-054</span></h3>"
        + "<div class='card'>" + decision_table() + "</div>"
        + "<p>No <span class='mono'>D-0nn</span> row is written in "
          "<span class='mono'>docs/07</span> and no finding is closed in "
          "<span class='mono'>docs/00</span> until the owner rules: <b>approval is never inferred</b>, and "
          "a stage that is complete is not a stage that is approved. Both rows in the register read "
          "<span class='mono'>BUILT &mdash; AWAITING REVIEW</span>.</p>",
    ])

    html_out = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Nexus-AI &middot; Stage 8.5 Intelligence Memory &mdash; A Belief Needs a Basis</title>"
        "<style>" + tokens + "\n" + fonts_css() + "\n" + CSS + "</style></head><body><div class='wrap'>"
        "<div class=\"lede\">Nexus-AI &middot; Stage 8 of 23 &middot; sub-deliverable 8.5 &middot; "
        "ordered by D-052&rsquo;s ruling 3, re-ordered by D-053&rsquo;s ruling 4 &middot; "
        "<b>BUILT &mdash; AWAITING REVIEW</b>, approval requested as <b>D-054</b> &middot; opens "
        "<b>F-24</b> and <b>F-25</b> &middot; next finding id <b>F-26</b></div>"
        "<h1 style=\"font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);"
        "margin:6px 0 0\"><span class='mono'>memory_item</span> gets a writer, F-18&rsquo;s three columns "
        "land, a contradiction becomes recordable &mdash; and a belief still carries exactly one "
        "confidence number</h1>"
        "<div class=\"ribbon\">This batch changes <b>9 source files</b> and <b>5 test files</b>, one of "
        "each new &mdash; <span class=\"mono\">intelligence/memory.py</span> (<b>471</b> lines) and "
        "<span class=\"mono\">tests/test_memory_writer.py</span> (<b>854</b> lines, <b>77</b> tests) "
        "&mdash; <b>14 files, +2,343 / &minus;39</b> in <span class=\"mono\">backend/</span>. Gate "
        "<b>1,394 passed / 2 skipped / 0 failed</b> (+100 tests, +76 test functions), mypy strict clean on "
        "<b>62</b> files, ruff and format clean on <b>93</b>, hygiene <b>88</b> unchanged. Migration "
        "<span class=\"mono\">0005_memory_beliefs</span> is <b>four</b> "
        "<span class=\"mono\">ADD COLUMN</span>s and needs <b>no rebuild and copies no row</b> "
        "(&sect;2); <span class=\"mono\">memory_item</span> goes 11&nbsp;&rarr;&nbsp;<b>14</b> columns and "
        "<span class=\"mono\">evidence_ref</span> 11&nbsp;&rarr;&nbsp;<b>12</b>. The refusal that makes "
        "<span class=\"mono\">docs/10</span> &sect;3.1&rsquo;s sentence true lives in the <b>writer</b> and "
        "not in a <span class=\"mono\">CHECK</span>, because &ldquo;a point estimate without them is a "
        "defect&rdquo; is about <b>three columns at once</b> &mdash; three refusals, three messages, never "
        "one (&sect;6). <span class=\"mono\">confidence_text</span> enforces the target&rsquo;s "
        "<span class=\"mono\">NUMERIC(6,5)</span> over <b>27 probed inputs, 11 accepted and 16 "
        "refused</b>, and catches exactly what the applied <span class=\"mono\">CHECK</span> still leaks: "
        "<span class=\"mono\">'0.5abc'</span> and <span class=\"mono\">'1e400'</span> are both "
        "<b>stored</b> by SQLite and both refused by the writer (&sect;8). "
        "<span class=\"mono\">contradicts</span> points <b>one way</b>, refuses a dangling parent and a "
        "self-contradiction, and joined <span class=\"mono\">CHECKSUMMED_FIELDS</span> &mdash; the covered "
        "set widening <b>nine &rarr; ten</b>, so pre-8.5 rows now verify "
        "<span class=\"mono\">False</span>, disclosed as &sect;10.3 disclosed F-21&rsquo;s (&sect;11). The "
        "route gained <span class=\"mono\">contradicted_by</span> and "
        "<span class=\"mono\">contradiction_count</span> and <b>no</b> new route: the reverse direction is "
        "<b>derived per dossier</b> and the response says so, because a disagreement across two cases "
        "appears in <b>neither</b> scan (&sect;12). <b>Nothing calls the writer</b> and no route serves "
        "<span class=\"mono\">memory_item</span>, by ruling (&sect;1). Proven load-bearing at <b>twenty</b> "
        "tampered sites with <b>zero</b> silent passes, from 1 failure to 96 (&sect;17). Two findings "
        "recorded rather than fixed: <b>F-24</b>, a belief still carries one confidence number while "
        "<span class=\"mono\">docs/10</span> &sect;3.1 asks for it &ldquo;as a band&rdquo; and D-035 "
        "approved &ldquo;beliefs as bands&rdquo; (&sect;13); and <b>F-25</b>, found by executing the "
        "contrast this batch created &mdash; <span class=\"mono\">evidence_ref.dossier_id</span> is refused "
        "by <b>nothing</b>, while the same codebase refuses three other dangling parents (&sect;14). No "
        "adapter changed, so no live run speaks to this batch.</div>"
        + body
        + "<footer>Stage 8.5 &middot; stage 10&rsquo;s <span class=\"mono\">memory_item</span> writer "
          "&middot; ordered by D-052&rsquo;s ruling 3, re-ordered by D-053&rsquo;s ruling 4 which declined "
          "wiring <span class=\"mono\">retrieved_at</span> first &middot; <b>BUILT &mdash; AWAITING "
          "REVIEW</b>, approval requested as <b>D-054</b> with four questions in &sect;19 &middot; opens "
          "<b>F-24</b> (no confidence band) and <b>F-25</b> (a dangling "
          "<span class=\"mono\">dossier_id</span> is refused by nothing), both recorded rather than fixed, "
          "next finding id <b>F-26</b> &middot; <b>F-18 narrowed, not closed</b>: gaps 1 and 3 close, gaps "
          "2 (no <span class=\"mono\">expires_at</span>) and 4 (the sufficiency meter) stay open &middot; "
          "F-22/<span class=\"mono\">O-014</span> untouched and &sect;11.12&rsquo;s limitation 1 stands "
          "&middot; migration <span class=\"mono\">0005_memory_beliefs</span>, <b>4</b> statements, "
          "checksum <span class=\"mono\">4520e5b5&hellip;</span>, <b>no rebuild and no row copied</b>, and "
          "the third migration that can be deferred and reported rather than bypassed &middot; "
          "<span class=\"mono\">memory_item</span> 11&nbsp;&rarr;&nbsp;<b>14</b> columns, "
          "<span class=\"mono\">evidence_ref</span> 11&nbsp;&rarr;&nbsp;<b>12</b>, "
          "<span class=\"mono\">dossier</span> unchanged &middot; the Postgres target declares all four "
          "<b>inline</b> because the fidelity gate parses <span class=\"mono\">CREATE TABLE IF NOT "
          "EXISTS</span> only, and an ALTER-only target would be <b>invisible</b> to it &mdash; the cost is "
          "a column-order divergence that was <b>checked</b>: no "
          "<span class=\"mono\">INSERT</span> without a column list, every "
          "<span class=\"mono\">SELECT *</span> read keyed by name &middot; "
          "<span class=\"mono\">intelligence/memory.py</span> <b>471</b> lines, <b>14</b> keyword-only "
          "parameters, a <b>16</b>-field frozen receipt, <b>17</b> refusals and <b>no</b> "
          "<span class=\"mono\">RejectReason</span> spent &middot; three refusals are <b>three "
          "messages</b>, and a test asserts each names exactly one missing thing &middot; "
          "<span class=\"mono\">confidence_text</span>: <b>27</b> inputs probed, <b>11</b> accepted, "
          "<b>16</b> refused, <b>one</b> digit before the point and <b>five</b> after, a "
          "<span class=\"mono\">float</span> and a <span class=\"mono\">bool</span> both refused, "
          "<span class=\"mono\">NaN</span>/<span class=\"mono\">Infinity</span> refused, "
          "<b>negative accepted deliberately</b> &middot; the applied "
          "<span class=\"mono\">CHECK</span> still leaks <span class=\"mono\">'0.5abc'</span> and "
          "<span class=\"mono\">'1e400'</span> and the writer refuses both, which is the only "
          "justification for having two &middot; the interval is about <b>the world</b>: never defaulted to "
          "<span class=\"mono\">created_at</span>, already-expired <b>dated not refused</b>, zero-length "
          "refused, naive refused <b>before</b> comparison, <span class=\"mono\">validity_open_ended</span> "
          "derived and pinned &middot; provenance checked against the store, "
          "<span class=\"mono\">cited_by</span> always empty, "
          "<span class=\"mono\">superseded_by</span> always <span class=\"mono\">None</span>, a repeated "
          "<span class=\"mono\">memory_id</span> refused while a repeated "
          "<span class=\"mono\">evidence_id</span> <b>replaces</b> the row &mdash; the asymmetry measured "
          "and pinned on both sides &middot; <span class=\"mono\">contradicts</span> one-way with the "
          "reverse <b>derived per dossier</b>, a mutual disagreement is <b>one</b> pair, and "
          "<span class=\"mono\">contradiction_count</span> is a count and never a verdict because "
          "A-02+A-08 says no gate can be satisfied by a confidence value &middot; "
          "<span class=\"mono\">CHECKSUMMED_FIELDS</span> <b>nine &rarr; ten</b> of twelve stored columns, "
          "the complement derived from <span class=\"mono\">PRAGMA table_info</span> and asserted to be "
          "exactly <span class=\"mono\">checksum</span> and <span class=\"mono\">audit_ref</span> &middot; "
          "<span class=\"mono\">PROJECTABLE</span> <b>14 &rarr; 15</b> keys, and a replay after "
          "<span class=\"mono\">DELETE</span> from both tables reproduces the row <b>byte-identically "
          "including its clock</b>, after a 1.05 s sleep &middot; <span class=\"mono\">view_gaps</span> "
          "still <b>nine</b>, two changed kind, their pins <b>re-aimed not deleted</b>, and "
          "<span class=\"mono\">app.py</span> still declares <b>13</b> routes &middot; gate <b>1,394 passed "
          "/ 2 skipped / 0 failed</b> (+100), <b>+76</b> test functions, mypy strict clean on <b>62</b>, "
          "ruff and format clean on <b>93</b>, hygiene <b>88</b> &middot; <span class=\"mono\">src</span> "
          "61&nbsp;&rarr;&nbsp;<b>62</b> files and 15,312&nbsp;&rarr;&nbsp;<b>16,181</b> lines, "
          "<span class=\"mono\">tests</span> 30&nbsp;&rarr;&nbsp;<b>31</b> and "
          "17,725&nbsp;&rarr;&nbsp;<b>19,121</b>, both baselines re-derived from "
          "<span class=\"mono\">git archive HEAD</span> rather than remembered, because &sect;10.4 exists: "
          "<b>sixteen</b> numbers published in 8.4 were stale &middot; <b>twenty</b> tampered sites, "
          "<b>twenty</b> caught, <b>zero</b> silent passes, from <b>1</b> failure to <b>96</b>, all six "
          "source files restored and the full suite re-run green &middot; the migration checksum moved "
          "<b>twice from formatting alone</b> and was re-derived from "
          "<span class=\"mono\">MIGRATIONS</span>, not restored by hand &middot; <b>twelve</b> limitations "
          "published in full &middot; no adapter changed, so no live endpoint was called and no venue run "
          "speaks to this batch &middot; next: <b>8.6 = F-25 alone</b> and <b>8.7 = "
          "<span class=\"mono\">expires_at</span></b>, both recommended and neither authorised</footer>"
          "</div></body></html>"
    )

    out = HERE / "stage8-5-a-belief-needs-a-basis.html"
    out.write_text(html_out)
    return out


if __name__ == "__main__":
    path = main()
    print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB)")
