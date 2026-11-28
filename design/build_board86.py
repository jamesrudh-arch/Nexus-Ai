"""Stage 8.6 board: F-25 alone — the fourth parent is guarded, and a gate that names all four.

D-054's ruling 3 ordered this batch and scoped it: one refusal in `record_evidence`, plus a test that all
four parent references this codebase guards are guarded rather than three of them. §1 shows what that
ruling left out, and §12 counts what therefore did not move.

Every transcript here was captured from `backend/.venv/bin/python` runs against a live post-migration
database, from `pytest` runs, or from the tamper script, and pasted verbatim — including the four-parent
contrast that re-measures §12.9's table and the nine tamper sites, one of which passed silently on the
first run and found a weak assertion rather than a weak guard. Captures: `/tmp/cap86.py` (BLOCKS A–H),
`/tmp/gate86.txt`, `/tmp/tamper86.py`.

Run:  cd backend && .venv/bin/python ../design/build_board86.py
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
   8.3, 8.4 and 8.5 boards recorded. Copied from `build_specimen.py`, the approved visual language. */
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
# Captures. Injected verbatim from /tmp/cap86.txt, /tmp/gate86.txt and /tmp/tamper86.txt by the
# generator that built this file: a transcript that is transcribed is a transcript that can be
# improved, and §12.14 exists because one was.
# ---------------------------------------------------------------------------------------------
# --- CAPTURES ---

BLOCK_A = """
  dossiers in the store: 0   evidence rows: 0   audit entries: 8

  record_evidence(dossier_id='DOS-NOPE')
    dossier 'DOS-NOPE' does not exist, so evidence cannot be attached to it: the row would be orphaned rather than corrupt — it would still verify its own checksum, ix_evidence_dossier would index a value matching nothing, and the route that serves evidence 404s on an id naming no case, so nothing reading through the API could find it again.
    evidence_ref.dossier_id REFERENCES dossier since migration 0002_memory, but PRAGMA foreign_keys is deliberately off, so SQLite would store this dangling parent without comment.
    Open the dossier first, or pass dossier_id=None to record evidence that belongs to no case yet.

  after the refusal: evidence rows 0 (was 0), audit entries 8 (was 8) -> nothing written, not even to the audit log
  store.get_dossier('DOS-NOPE') -> None
  store.evidence_refs(dossier_id='DOS-NOPE') -> 0 row(s)
  audit.verify() -> []   (the chain is intact: a refusal wrote no entry)
"""

BLOCK_B = """
  one real case CASE-783C1D133A694FC9-NKC8VW7X, one real observation EV-B2C15DD531E74918-Y5XN4ZP0

  dossier.instrument_id -> instrument
    dangling  -> REFUSED: instrument 'NOPE:NOPE' is not in the system of record, which holds 3: ['INS-BTC-USDT', 'INS-BTC-USDT-USDT', 'INS-EUR-USD']…
    grounded  -> ACCEPTED: dossier 1 -> 2
  evidence_ref.contradicts -> evidence_ref
    dangling  -> REFUSED: evidence 'EV-NOPE' does not exist, so nothing can be recorded as contradicting it…
    grounded  -> ACCEPTED: evidence_ref 1 -> 2
  evidence_ref.dossier_id -> dossier
    dangling  -> REFUSED: dossier 'DOS-NOPE' does not exist, so evidence cannot be attached to it: the row would be orphaned rather than corrupt — it would still verify its own checksum, ix_evidence_dossier would index a value matching nothing, and the route that serves evidence 404s on an id naming no case, so nothing reading through the API could find it again…
    grounded  -> ACCEPTED: evidence_ref 2 -> 3
  memory_item's evidence_ids (payload, no FK)
    dangling  -> REFUSED: evidence 'EV-INVENTED' does not exist, so nothing can rest on it…
    grounded  -> ACCEPTED: memory_item 1 -> 2

  the same four rows, as a count: 4 guarded, 0 unguarded (§12.9 measured 3 and 1)
"""

BLOCK_C = """
  dossier_id=None       -> ACCEPTED, receipt.dossier_id=None, stored as None
  dossier_id=''         -> REFUSED: dossier_id must name a dossier or be None; an empty string is neither, and None — not '' — is how this writer records evidence that belongs to no case yet
  dossier_id='   '      -> REFUSED: dossier_id must name a dossier or be None; an empty string is neither, and None — not '' — is how this writer records evidence that belongs to no case yet
  dossier_id='DOS-NOPE' -> REFUSED: dossier 'DOS-NOPE' does not exist, so evidence cannot be attached to it: the row would be orphaned rather than corrupt — it would still verify its own checksum, ix_evidence_dossier would index a value matching nothing, and the route that serves evidence 404s on an id naming no case, so nothing reading through the API could find it again. evidence_ref.dossier_id REFERENCES dossier since migration 0002_memory, but PRAGMA foreign_keys is deliberately off, so SQLite would store this dangling parent without comment. Open the dossier first, or pass dossier_id=None to record evidence that belongs to no case yet

  None is not a missing value and '' is not a name: two refusals, two messages, and the
  legitimate state (evidence that belongs to no case yet) still records.
"""

BLOCK_D = """
  ' CASE-A344BE3CC80B4686-PNRM7NDF '           -> REFUSED (dangling)
  'CASE-A344BE3CC80B4686-PNRM7NDF\n'           -> REFUSED (dangling)
  'case-a344be3cc80b4686-pnrm7ndf'             -> REFUSED (dangling)
  'CASE-A344BE3CC80B4686-PNRM7NDF'             -> ACCEPTED
  stored dossier_id 'CASE-A344BE3CC80B4686-PNRM7NDF' == what the caller passed 'CASE-A344BE3CC80B4686-PNRM7NDF': True
  evidence rows in this store: 1 (one, the accepted one)
"""

BLOCK_E = """
  record_snapshot(dossier_id='DOS-NOPE') -> dossier 'DOS-NOPE' does not exist, so evidence cannot be attached to it: the row would be orphaned rather than corrupt — it would still verify its own checksum, ix_evidence_dossier would index a value matching nothing, and the route that serves evidence 404s on an id naming no case, so nothing reading through the API could find it again…
  evidence rows after: 0
  snapshot_payload() still builds the same 11 payload keys —
    ['ask', 'bid', 'delay_seconds', 'delayed', 'instrument_id', 'last', 'mid', 'source', 'spread', 'venue', 'venue_timestamp']
"""

BLOCK_F = """
  store.save_evidence_ref(dossier_id='DOS-NOPE', contradicts='EV-ALSO-NOPE')
    -> stored: dossier_id='DOS-NOPE' contradicts='EV-ALSO-NOPE'
    get_dossier('DOS-NOPE') -> None
  store.save_dossier(instrument_id='NOPE:NOPE') -> stored: 'NOPE:NOPE'
  PRAGMA foreign_keys -> 0   (off by design: docs/13 §2.5, recovery re-projects in chain order)
  Both refusals live in the writers. A check in the store would make boot recovery depend
  on a read and could fail the replay of an event the chain already holds.
"""

BLOCK_G = """
  an orphan written straight past the writer, at the store layer: True
  GET /v1/intelligence/dossiers/DOS-NOPE -> 404 {'detail': 'unknown dossier: DOS-NOPE'}
  evidence_refs(dossier_id='DOS-NOPE') -> 1 row(s): indexed by ix_evidence_dossier, served by nothing
  the same id through the writer -> REFUSED: dossier 'DOS-NOPE' does not exist, so evidence cannot be attached to it: the row would be orphaned rather than corrupt — it would still verify its own checksum, ix_evidence_dossier would index a value matching nothing, and the route that serves evidence 404s on an id naming no case, so nothing reading through the API could find it again…
  rows in the store after the writer refused: 1 (the one the store layer wrote, and no second)
"""

BLOCK_H = """
  MIGRATIONS -> 5 (unchanged): ['0001_operational', '0002_memory', '0003_audit_append_only', '0004_memory_fidelity', '0005_memory_beliefs']
    0001_operational         statements= 19  requires=None           checksum=fcfd79161c830f40…
    0002_memory              statements=  8  requires=None           checksum=5e7fafd0673e0a60…
    0003_audit_append_only   statements=  4  requires=audit_log      checksum=1e9ec5a5d9154d0a…
    0004_memory_fidelity     statements= 15  requires=dossier        checksum=4c7368d407bb1f18…
    0005_memory_beliefs      statements=  4  requires=memory_item    checksum=4520e5b5e259eb4c…
  the pins live in tests/test_schema_fidelity.py, and that file is untouched:
    0005_memory_beliefs still 4520e5b5e259eb4c…, and no migration text moved
  PROJECTABLE -> 15 event types (unchanged)
  CHECKSUMMED_FIELDS -> 10 of 12 stored columns (unchanged)
  evidence.py __all__ -> 9 names (unchanged; _resolve_dossier is private)
  raise ValueError in evidence.py -> 10 (was 8: the two new refusals)
  the three intelligence tables still hold 0 rows in a fresh store (no column added)
  git diff HEAD -- store/schema.py, migrations/, api/app.py -> (empty)
  files changed in backend/: ['backend/src/nexus/intelligence/evidence.py', 'backend/src/nexus/store/operational.py', 'backend/tests/test_evidence_writer.py']
  src files naming _resolve_dossier -> ['src/nexus/intelligence/evidence.py']
"""

BLOCK_GATE = """
$ .venv/bin/python -m pytest
1408 passed, 2 skipped, 1 warning in 29.24s

$ .venv/bin/ruff check src tests
All checks passed!

$ .venv/bin/ruff format --check src tests
93 files already formatted

$ .venv/bin/mypy src
Success: no issues found in 62 source files

per file, each run separately:
  test_evidence_writer.py    68 passed in 3.30s
  test_dossier_writer.py     87 passed in 5.76s
  test_memory_writer.py      77 passed in 3.65s
  test_intelligence_routes.py 44 passed
  test_schema_fidelity.py    41 passed in 1.83s
  test_repo_hygiene.py       88 passed in 5.14s
  test_migrations.py         15 passed in 0.56s
"""

BLOCK_TAMPER = """
evidence: a dangling dossier accepted (F-25 back again) | 6 failed, 270 passed, 1 warning in 15.68s | 6 | ['test_a_parent_the_store_has_never_held_is_refused_by_the_write', 'test_a_dossier_the_store_has_never_held_is_refused', 'test_an_empty_dossier_id_is_refused_and_is_not_the_same_claim_']
evidence: an empty dossier_id accepted | 2 failed, 274 passed, 1 warning in 15.44s | 2 | ['test_an_empty_dossier_id_is_refused_and_is_not_the_same_claim_', 'test_an_empty_dossier_id_is_refused_and_is_not_the_same_claim_']
evidence: the refusal does not name the value | 4 failed, 272 passed, 1 warning in 15.76s | 4 | ['test_a_parent_the_store_has_never_held_is_refused_by_the_write', 'test_a_dossier_the_store_has_never_held_is_refused', 'test_an_id_is_stored_as_given_and_padding_makes_it_dangling']
evidence: the id normalised before the lookup | 1 failed, 275 passed, 1 warning in 15.49s | 1 | ['test_an_id_is_stored_as_given_and_padding_makes_it_dangling']
evidence: None refused too (the guard over-reaches) | 83 failed, 193 passed, 1 warning in 14.86s | 83 | ['test_observed_and_retrieved_land_in_their_own_columns', 'test_the_apparent_interval_is_recorded_and_labelled', 'test_a_venue_clock_ahead_of_ours_is_recorded_not_refused']
evidence: a dangling contradicts accepted | 2 failed, 274 passed, 1 warning in 16.05s | 2 | ['test_a_row_that_does_not_exist_cannot_be_contradicted', 'test_a_parent_the_store_has_never_held_is_refused_by_the_write']
dossier: an unmapped instrument accepted | 3 failed, 273 passed, 1 warning in 16.14s | 3 | ['test_a_parent_the_store_has_never_held_is_refused_by_the_write', 'test_a_dangling_instrument_is_refused_by_the_writer_anyway', 'test_nothing_can_be_opened_against_an_instrument_before_the_ma']
memory: a dangling evidence id accepted | 3 failed, 273 passed, 1 warning in 16.20s | 3 | ['test_a_parent_the_store_has_never_held_is_refused_by_the_write', 'test_an_evidence_id_the_store_has_never_held_is_refused', 'test_one_real_id_beside_one_fake_one_is_refused_too']
store: the guard moved into save_evidence_ref | 1 failed, 275 passed, 1 warning in 16.65s | 1 | ['test_the_guard_is_in_the_writer_and_not_in_the_store']
"""


def scope_table() -> str:
    return table(
        ["File", "What moved in it"],
        [
            ("<span class='mono'>intelligence/evidence.py</span>",
             "444 &rarr; <b>516</b> lines: one private resolver "
             "(<span class='mono'>_resolve_dossier</span>), <b>two</b> refusals, one call site, and the "
             "module docstring&rsquo;s block on <span class='mono'>dossier_id</span>. "
             "<span class='mono'>raise ValueError</span> in the file goes <b>8 &rarr; 10</b>"),
            ("<span class='mono'>store/operational.py</span>",
             "1,351 &rarr; <b>1,355</b> lines: <b>four lines of docstring</b> on "
             "<span class='mono'>save_evidence_ref</span>, saying that "
             "<span class='mono'>dossier_id</span> is stored as given on the same terms as "
             "<span class='mono'>contradicts</span>. <b>No code</b>"),
            ("<span class='mono'>tests/test_evidence_writer.py</span>",
             "840 &rarr; <b>1,101</b> lines: <b>42 &rarr; 49</b> test functions, <b>54 &rarr; 68</b> "
             "tests, one test <b>re-aimed and none deleted</b>"),
        ],
    )


def parent_table() -> str:
    return table(
        ["Parent reference", "Dangling &rarr;", "Grounded &rarr;", "Guarded since"],
        [
            ("<span class='mono'>dossier.instrument_id &rarr; instrument</span>",
             "refused, naming the id and how many the master holds",
             "<span class='mono'>dossier</span> +1", "8.3"),
            ("<span class='mono'>evidence_ref.contradicts &rarr; evidence_ref</span>",
             "refused, naming the row", "<span class='mono'>evidence_ref</span> +1", "8.5"),
            ("<span class='mono'>evidence_ref.dossier_id &rarr; dossier</span>",
             "<b>refused</b>, naming the case and the orphan it would have become",
             "<span class='mono'>evidence_ref</span> +1", "<b>this batch</b>"),
            ("<span class='mono'>memory_item</span>&rsquo;s <span class='mono'>evidence_ids</span> "
             "(payload, no FK)",
             "refused, naming the id", "<span class='mono'>memory_item</span> +1", "8.5"),
        ],
    )


def fk_table() -> str:
    return table(
        ["Declared foreign key", "Guarded by a writer?"],
        [
            ("<span class='mono'>dossier.instrument_id &rarr; instrument</span>",
             "<span class='ok'><b>yes</b></span> &mdash; <span class='mono'>open_dossier</span>, "
             "since 8.3"),
            ("<span class='mono'>evidence_ref.contradicts &rarr; evidence_ref</span>",
             "<span class='ok'><b>yes</b></span> &mdash; <span class='mono'>record_evidence</span>, "
             "since 8.5"),
            ("<span class='mono'>evidence_ref.dossier_id &rarr; dossier</span>",
             "<span class='ok'><b>yes</b></span> &mdash; <span class='mono'>record_evidence</span>, "
             "since <b>this batch</b>"),
            ("<span class='mono'>venue_instrument_mapping.instrument_id &rarr; instrument</span> "
             "(<span class='mono'>ON DELETE CASCADE</span>)",
             "<b>by construction</b> &mdash; <span class='mono'>project_master</span> writes parents "
             "and children from one registry, so there is no id to dangle"),
            ("<span class='mono'>decision.instrument_id &rarr; instrument</span>",
             "<span class='no'>no writer calls it</span>"),
            ("<span class='mono'>trade_intent.decision_id &rarr; decision</span>",
             "<span class='no'>no writer calls it</span>"),
            ("<span class='mono'>orders.intent_id &rarr; trade_intent</span>",
             "<span class='no'>projection only</span> (<span class='mono'>writeahead.py:178</span>)"),
            ("<span class='mono'>fills.order_id &rarr; orders</span>",
             "<span class='no'>projection only</span> (<span class='mono'>writeahead.py:93</span>)"),
            ("<span class='mono'>approval.intent_id &rarr; trade_intent</span>",
             "<span class='no'>no writer calls it</span>"),
        ],
    )


def gate_table() -> str:
    return table(
        ["Attempt", "What it asserts", "Why one half alone proves nothing"],
        [
            ("<b>dangling</b>: each of the four parents named something the store has never held",
             "the writer raises <span class='mono'>ValueError</span>; the refusal text names the value; "
             "the table count is <b>unchanged</b>; <span class='mono'>audit.length</span> is "
             "<b>unchanged</b>",
             "a writer that refuses <b>everything</b> passes this half &mdash; including the three "
             "parents it has guarded since 8.3 and 8.5"),
            ("<b>grounded</b>: each of the four parents named something the store really holds",
             "the write succeeds; the table count is <b>+1</b>; the stored value is the one passed; "
             "<span class='mono'>audit.length</span> is <b>+1</b>",
             "a writer with <b>no guard at all</b> passes this half &mdash; which is exactly what F-25 "
             "was before this batch"),
        ],
    )


def tamper_table() -> str:
    return table(
        ["Tampered site", "Result", "What it proves"],
        [
            ("the dangling-<span class='mono'>dossier_id</span> branch deleted (F-25 back again)",
             "<b>6 failed</b>, 270 passed", "the refusal is load-bearing, and so is its message"),
            ("the empty-string branch deleted", "<b>2 failed</b>, 274 passed",
             "<b>passed silently on the first run</b> &mdash; the test was weak, not the tamper (&sect;10)"),
            ("the refusal no longer names the value", "<b>4 failed</b>, 272 passed",
             "a message that does not name the id is a different refusal"),
            ("the id stripped before the lookup", "<b>1 failed</b>, 275 passed",
             "&ldquo;stored as given&rdquo; is pinned, not merely intended"),
            ("<span class='mono'>None</span> refused too (the guard over-reaches)",
             "<b>83 failed</b>, 193 passed",
             "the legitimate state is load-bearing: refusing it breaks nearly every evidence test here"),
            ("the dangling-<span class='mono'>contradicts</span> branch deleted",
             "<b>2 failed</b>, 274 passed", "<b>a guard that predates this batch</b> now fails a test "
             "that names the parent"),
            ("<span class='mono'>open_dossier</span>&rsquo;s instrument guard deleted",
             "<b>3 failed</b>, 273 passed", "<b>a second pre-existing guard</b>, in another module"),
            ("<span class='mono'>record_memory_item</span>&rsquo;s "
             "<span class='mono'>evidence_ids</span> guard deleted",
             "<b>3 failed</b>, 273 passed", "<b>a third</b>, in a third module"),
            ("the guard moved into <span class='mono'>save_evidence_ref</span>",
             "<b>1 failed</b>, 275 passed",
             "the layering is pinned: hardening the store breaks boot recovery&rsquo;s contract and now "
             "says so in a test name"),
        ],
    )


def limitation_table() -> str:
    return table(
        ["#", "Limitation"],
        [
            ("1", "<b>The guard is a read.</b> One <span class='mono'>get_dossier</span> per write, so a "
                  "caller attaching a hundred observations to one case pays a hundred lookups for one "
                  "answer. Invisible at Stage 8&rsquo;s volumes and recorded rather than optimised, "
                  "because a cache in front of it would be a second copy of the truth about what exists"),
            ("2", "<b>The check and the write are not atomic.</b> A dossier removed between the lookup "
                  "and the insert would still orphan the row. Nothing in "
                  "<span class='mono'>src/</span> deletes a dossier &mdash; the only "
                  "<span class='mono'>DELETE FROM</span> in the package is "
                  "<span class='mono'>migrations.py:246</span>, against "
                  "<span class='mono'>schema_migration_skips</span> &mdash; so the window is theoretical "
                  "today and stops being one the day a deletion path is built"),
            ("3", "<b>An orphan is still writable at the store layer</b>, and a replay of a pre-8.6 event "
                  "carrying a dangling <span class='mono'>dossier_id</span> would project one. Nothing "
                  "scans for orphans and nothing removes them. Both intelligence tables are empty in "
                  "production, so there is nothing to find"),
            ("4", "<b>The gate names four parents in a tuple, and the tuple is extended by hand.</b> A "
                  "fifth guarded parent &mdash; or a fifth unguarded one &mdash; does not turn the gate "
                  "red by existing; &sect;11&rsquo;s inventory is what would catch it, and it is a "
                  "measurement in a document, not a test. A scan deriving the table from "
                  "<span class='mono'>PRAGMA foreign_key_list</span> was considered and not built: it "
                  "would have to decide what &ldquo;guarded&rdquo; means for a projection-only writer, "
                  "and inventing that rule here would be a judgement dressed as a gate"),
            ("5", "<b>The refusal message describes another module&rsquo;s behaviour</b> &mdash; the "
                  "route&rsquo;s 404. If the route changes, the message goes stale and nothing asserts "
                  "the two against each other. The alternative names only the rule and tells a caller "
                  "less about why it exists"),
            ("6", "<b>The gate lives in <span class='mono'>test_evidence_writer.py</span></b>, a file "
                  "named for one writer, while it asserts behaviour of three. A reader looking for "
                  "cross-writer invariants would look in "
                  "<span class='mono'>test_repo_hygiene.py</span> and not find it. &sect;15 question 2"),
            ("7", "<b>The check order is not gated.</b> The parent before the contradiction is a decision "
                  "recorded in a comment and in &sect;3, and no test fails if the two are swapped"),
            ("8", "<b>Nothing else this record already published moved.</b> "
                  "<span class='mono'>subject</span> is still not validated against the instrument master "
                  "and <span class='mono'>kind</span> and <span class='mono'>scope</span> are still free "
                  "text (&sect;12.12&rsquo;s limitation 5), and F-24 still stands: a belief carries one "
                  "confidence number where <span class='mono'>docs/10</span> &sect;3.1 asks for a band"),
        ],
    )


def decision_table() -> str:
    return table(
        ["#", "Question", "Recommendation"],
        [
            ("1", "Is Stage 8.6 approved, and is F-25 closed?",
             "<b>Approve, recorded as D-055, and close F-25</b> on the defect &sect;12.9 named &mdash; a "
             "dangling <span class='mono'>evidence_ref.dossier_id</span> refused by nothing &mdash; and "
             "<b>not</b> on orphans in general, which limitation 3 says are still writable at the store "
             "layer and still unscanned. That is D-053&rsquo;s ruling 1 distinction for "
             "<span class='mono'>O-012</span> applied again: close on the defect, leave the limitation "
             "published beside the closure rather than retired by it. The alternative holds F-25 open "
             "until the store refuses too, which would make boot recovery depend on a read"),
            ("2", "Should the four-parent gate stay in "
                  "<span class='mono'>test_evidence_writer.py</span>, or move?",
             "<b>Keep it where it is.</b> It sits beside the refusal it was ordered beside, so removing "
             "either shows up in the same file, and it is the file whose writer gained the fourth guard. "
             "Moving it to <span class='mono'>test_repo_hygiene.py</span> would put a behavioural test "
             "that builds three stores among source scans; a new "
             "<span class='mono'>tests/test_parent_references.py</span> would take the file count from "
             "<b>31</b> to 32 for thirteen tests and separate the gate from the writer it guards. The "
             "cost of keeping it is limitation 6 &mdash; the file&rsquo;s name understates what it holds, "
             "which is a naming problem and not a coverage one"),
            ("3", "Are &sect;11&rsquo;s five unguarded trading-path foreign keys a finding now, or a note "
                  "for Stage 9?",
             "<b>Record F-26 now</b>, as a finding about the <b>seam</b> and not about a defect in "
             "shipped behaviour. <span class='mono'>save_decision</span>, "
             "<span class='mono'>save_intent</span> and <span class='mono'>save_approval</span> take "
             "domain objects with no store in the signature, so the guard the three intelligence writers "
             "have <b>cannot be added there without changing the seam</b> &mdash; and "
             "<span class='mono'>DecisionRecord.instrument_id</span> is an unvalidated optional string, "
             "so a dangling instrument is representable today. Nothing writes those tables, so nothing is "
             "orphaned today. Recording it now costs one row and keeps Stage 9 from rediscovering it five "
             "times; waiting is what F-17 and F-19 did, and it leaves the seam question unasked until "
             "somebody is mid-batch with a reason to answer it quickly"),
            ("4", "Does 8.7 still mean <span class='mono'>expires_at</span>, and on which table?",
             "<b>Yes, unchanged, and on <span class='mono'>memory_item</span> only.</b> D-054&rsquo;s "
             "ruling 4 ordered it and nothing here changes the reason: it is F-18&rsquo;s remaining cheap "
             "half, &sect;5.3 lists <span class='mono'>ADD COLUMN expires_at TEXT</span> as "
             "<span class='mono'>OK</span> with no rebuild, and &ldquo;expiring TTLs&rdquo; is the one "
             "approved sentence in F-18 that still has no column at all. "
             "<span class='mono'>memory_item</span> only, because that is the table the sentence is "
             "about: <span class='mono'>valid_until</span> says until when a claim holds <b>in the "
             "world</b> while an expiry says when <b>this system</b> should stop serving the row, and the "
             "disagreement between the two is a property of a belief, not of an observation. "
             "<span class='mono'>evidence_ref</span> gains nothing &mdash; its freshness is already two "
             "columns and a <span class='mono'>data_status</span>, and adding a third clock to a table "
             "whose two clocks F-14 spent a batch separating would be the wrong kind of company. The "
             "precedent exists in the domain model "
             "(<span class='mono'>DecisionRecord.expires_at</span>) and "
             "<span class='mono'>docs/10</span> &sect;3.2&rsquo;s V1&ndash;V3 gates are what would "
             "consume it, so the writer should store it and nothing should act on it yet"),
        ],
    )


def ruling_table() -> str:
    return table(
        ["#", "Question as put", "Ruled", "What it changes"],
        [
            ("1", "Is Stage 8.6 approved, and is F-25 closed?",
             "<b>Approved, recorded as D-055</b>, and <b>F-25 <span class='mono'>CLOSED</span></b> &mdash; "
             "on the defect &sect;12.9 named, <i>not</i> on orphans in general",
             "Both 8.6 rows in <span class='mono'>docs/07</span> move to <span class='mono'>REVIEWED "
             "&mdash; APPROVED 2026-11-28</span>. &sect;14&rsquo;s <b>limitation 3 stands as published "
             "beside the closure</b> rather than being retired by it: an orphan is still writable at the "
             "store layer and still unscanned. That is D-053&rsquo;s ruling 1 distinction for "
             "<span class='mono'>O-012</span> applied a second time &mdash; close on the defect the finding "
             "named, and leave the limitation visible next to the closure so a reader who sees "
             "&ldquo;F-25 closed&rdquo; cannot take &ldquo;orphans impossible&rdquo; with it. The "
             "alternative, holding F-25 open until <span class='mono'>save_evidence_ref</span> refuses too, "
             "would make boot recovery depend on a read and put the replay of a chained event at the mercy "
             "of a parent not yet projected"),
            ("2", "Should the four-parent gate stay in "
                  "<span class='mono'>test_evidence_writer.py</span>, or move?",
             "<b>It stays where it is</b>",
             "No file moves, so <span class='mono'>tests</span> stays at <b>31</b> files and the gate stays "
             "beside the refusal it was ordered beside &mdash; removing either one shows up in the same "
             "file. &sect;14&rsquo;s <b>limitation 6 stays published</b>: the file&rsquo;s name understates "
             "what it holds, and this ruling accepts that cost rather than paying a 32nd file for thirteen "
             "tests or putting a behavioural test that builds three stores among "
             "<span class='mono'>test_repo_hygiene.py</span>&rsquo;s source scans"),
            ("3", "Are &sect;11&rsquo;s five unguarded trading-path foreign keys a finding now, or a note "
                  "for Stage 9?",
             "<b>Recorded now as <span class='mono'>F-26</span>, "
             "<span class='no'>OPEN</span></b> &mdash; a finding about the <b>seam</b>, not about a defect "
             "in shipped behaviour",
             "F-26 joins F-17, F-19, F-22 (<span class='mono'>O-014</span>) and F-24 as an open finding "
             "with no batch behind it. It is <b>not</b> an <span class='mono'>O-</span> row: D-054 "
             "established that scheduling a batch is not opening an obligation row, and recording a finding "
             "is not either &mdash; <span class='mono'>O-014</span> exists for F-22 only because "
             "D-052&rsquo;s ruling 4 said so in terms. <b>The next finding id is F-27</b>"),
            ("4", "Does 8.7 still mean <span class='mono'>expires_at</span>, and on which table?",
             "<b>Yes, unchanged, and on <span class='mono'>memory_item</span> only</b>",
             "8.7 is ordered and scoped: one nullable <span class='mono'>ADD COLUMN expires_at TEXT</span> "
             "&mdash; &sect;5.3&rsquo;s executed survey lists it <span class='mono'>OK</span>, so <b>no "
             "rebuild and no row copied</b>, unlike <span class='mono'>0004</span> &mdash; one writer "
             "argument, and <b>nothing acting on it</b>, because "
             "<span class='mono'>docs/10</span> &sect;3.2&rsquo;s V1&ndash;V3 gates are what would consume "
             "it. <span class='mono'>evidence_ref</span> gains nothing: its freshness is already two "
             "columns and a <span class='mono'>data_status</span>, and a third clock on the table whose two "
             "clocks F-14 spent a batch separating would be the wrong kind of company"),
        ],
    )


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())

    body = "".join([
        # -- 1 ------------------------------------------------------------------
        "<h3>1 &middot; What ruling 3 authorised, and what this batch therefore did not do"
        "<span class='tag'>D-054 r3 &middot; docs/15 &sect;13.0</span></h3>"
        "<p>D-054&rsquo;s ruling 3 asked for <b>one refusal in "
        "<span class='mono'>record_evidence</span></b> plus <b>a test that all four parent references this "
        "codebase guards are guarded, rather than three of them</b>. That is the whole batch. Three files "
        "changed, <b>+339 / &minus;2</b>, and one of the three is four lines of docstring.</p>"
        + "<div class='card'>" + scope_table() + "</div>"
        + "<p>Every absence below was <b>measured rather than assumed</b>, because &ldquo;nothing else "
          "moved&rdquo; is the claim a small batch lives or dies on: <span class='mono'>git diff HEAD -- "
          "store/schema.py migrations/ api/app.py</span> is <b>empty</b>, so there is <b>no migration, no "
          "column, no route, no gap text and no schema text</b> here. "
          "<span class='mono'>MIGRATIONS</span> is still <b>5</b> with the same five checksums "
          "(<span class='mono'>0005_memory_beliefs</span> still "
          "<span class='mono'>4520e5b5e259eb4c&hellip;</span>, its pin in "
          "<span class='mono'>test_schema_fidelity.py</span> untouched), "
          "<span class='mono'>PROJECTABLE</span> is still <b>15</b>, "
          "<span class='mono'>CHECKSUMMED_FIELDS</span> is still <b>10 of 12</b>, "
          "<span class='mono'>app.py</span> still declares <b>13</b> routes and "
          "<span class='mono'>DOSSIER_VIEW_GAPS</span> is still <b>9</b>. The two writers D-052 and D-054 "
          "approved were <b>read, not edited</b>: <span class='mono'>open_dossier</span> and "
          "<span class='mono'>record_memory_item</span> appear here only as two of the four parents the "
          "new gate names.</p>",

        # -- 2 ------------------------------------------------------------------
        "<h3>2 &middot; F-25 as 8.5 measured it, re-measured here with the fourth row filled in"
        "<span class='tag'>docs/15 &sect;12.9 &rarr; &sect;13.3</span></h3>"
        "<p>&sect;12.9 found this by <b>executing the contrast</b>: 8.5 added a refusal for a dangling "
        "<span class='mono'>contradicts</span>, which made &ldquo;which parents does this codebase "
        "actually check?&rdquo; answerable by running it &mdash; and the answer was three guarded and one "
        "refused by nothing. The same four calls, run again against this batch&rsquo;s tree:</p>"
        + verbatim("BLOCK B &mdash; captured: four parents, both halves, one store", BLOCK_B)
        + "<p><b>4 guarded, 0 unguarded.</b> The table below is the test&rsquo;s data, not a summary of "
          "it: one module-level tuple holds all four and <b>both halves are derived from that one "
          "tuple</b>, so a parent cannot be dropped from one test and kept in the other.</p>"
        + "<div class='card'>" + parent_table() + "</div>",

        # -- 3 ------------------------------------------------------------------
        "<h3>3 &middot; The refusal: one branch, and what the store holds after it"
        "<span class='tag'>docs/15 &sect;13.1</span></h3>"
        "<p><span class='mono'>evidence_ref.dossier_id</span> has carried "
        "<span class='mono'>REFERENCES dossier</span> since "
        "<span class='mono'>0002_memory</span>, and <span class='mono'>PRAGMA foreign_keys</span> is "
        "<b>deliberately off</b> (<span class='mono'>docs/13</span> &sect;2.5: recovery re-projects in "
        "chain order, which is not always parent-first, and a hard FK failure mid-recovery would be worse "
        "than the inconsistency it prevents). So the writer is the only place this can be refused &mdash; "
        "the reasoning that produced the other three guards. &sect;12.9 wrote the shape of the check down "
        "before it existed, and it is what shipped. The parent is checked <b>before</b> the contradiction, "
        "because it is the wider claim of the two: a row that belongs to no case that exists has no "
        "business recording a disagreement inside one.</p>"
        + verbatim("BLOCK A &mdash; captured: the refusal, and the store and chain after it", BLOCK_A)
        + "<p>Nothing was written &mdash; <b>not even an audit entry</b>, which is what L-2 means when a "
          "write is refused: the audit entry goes first, so a refusal that got as far as auditing would "
          "leave a chain entry describing a row that does not exist.</p>",

        # -- 4 ------------------------------------------------------------------
        "<h3>4 &middot; Three claims, three outcomes: <span class='mono'>None</span>, "
        "<span class='mono'>''</span>, and a name that resolves"
        "<span class='tag'>two branches, two messages</span></h3>"
        "<p>Two refusals rather than one, because two mistakes are not one. "
        "<span class='mono'>None</span> is the <b>legitimate</b> state &mdash; evidence that belongs to no "
        "case yet, which <span class='mono'>0002_memory</span> makes possible by declaring the column "
        "nullable, and refusing it would make the first writer depend on the second. "
        "<span class='mono'>''</span> is <b>no name at all</b>: telling that caller "
        "&ldquo;dossier <span class='mono'>''</span> does not exist&rdquo; would report a failed lookup "
        "when what happened is that it named nothing. The third refusal is F-25&rsquo;s, and its message "
        "carries the consequence rather than only the rule.</p>"
        + verbatim("BLOCK C &mdash; captured: four values, one accepted and three refused", BLOCK_C),

        # -- 5 ------------------------------------------------------------------
        "<h3>5 &middot; Stored as given: padding makes an id dangling rather than being stripped"
        "<span class='tag'>&sect;12.12 limitation 12, applied to an id</span></h3>"
        "<p>The value is <b>not</b> stripped, case-folded or normalised. Stripping would rewrite what a "
        "caller said into something it did not say, which is the choice &sect;12.12&rsquo;s limitation 12 "
        "records for a confidence &mdash; <span class='mono'>'0.72'</span> and "
        "<span class='mono'>'0.720000'</span> stay different stored strings for one number &mdash; applied "
        "here to an identifier, where the cost is concrete: a padded id is refused as dangling instead of "
        "quietly resolving to a case the caller never named.</p>"
        + verbatim("BLOCK D &mdash; captured: four spellings of one id, three refused", BLOCK_D),

        # -- 6 ------------------------------------------------------------------
        "<h3>6 &middot; <span class='mono'>record_snapshot</span> inherits the refusal by forwarding"
        "<span class='tag'>one guard, two entry points</span></h3>"
        "<p>The snapshot writer is a thin forwarder, so it needed no branch of its own &mdash; and the "
        "capture checks that the forwarding did not change anything else about it either: the payload it "
        "builds still has the same eleven keys.</p>"
        + verbatim("BLOCK E &mdash; captured: the same id through the second entry point", BLOCK_E),

        # -- 7 ------------------------------------------------------------------
        "<h3>7 &middot; The layer: the writer refuses, the store does not &mdash; and now a test says so"
        "<span class='tag'>docs/15 &sect;13.2</span></h3>"
        "<p><span class='mono'>store.save_evidence_ref</span> <b>still accepts</b> a dangling parent, on "
        "purpose, and this batch made that explicit in its docstring rather than leaving it to be inferred "
        "from <span class='mono'>save_dossier</span>&rsquo;s. The store is the <b>projection target</b>: a "
        "check there would make boot recovery depend on a read, and could fail the replay of an event the "
        "chain already holds. Measured rather than argued &mdash; both dangling values store, "
        "<span class='mono'>save_dossier</span> accepts an unmapped instrument on the same terms, and "
        "<span class='mono'>PRAGMA foreign_keys</span> reads <b>0</b>.</p>"
        + verbatim("BLOCK F &mdash; captured: the store layer, still check-free by design", BLOCK_F)
        + "<p><span class='mono'>test_the_guard_is_in_the_writer_and_not_in_the_store</span> pins the "
          "layering, so a future reader who &ldquo;hardens&rdquo; the store gets a red gate and an "
          "explanation instead of a silently broken recovery. Tampering proved it load-bearing: adding the "
          "check to <span class='mono'>save_evidence_ref</span> fails <b>exactly that test and nothing "
          "else</b> (&sect;10). The consequence is stated rather than hidden &mdash; an orphan row is "
          "still writable at the store layer, and a replay of a pre-8.6 event carrying a dangling "
          "<span class='mono'>dossier_id</span> would still project one. Nothing scans for orphans and "
          "nothing removes them; both intelligence tables are empty in production, so there is nothing to "
          "scan today.</p>",

        # -- 8 ------------------------------------------------------------------
        "<h3>8 &middot; The route: the orphan this batch removes was unreachable, and now cannot exist"
        "<span class='tag'>docs/15 &sect;12.9&rsquo;s consequence, measured</span></h3>"
        "<p>The reason F-25 mattered is not that a row could be written &mdash; it is that the row could "
        "be written and then <b>never found again</b>. An orphan pushed straight past the writer, at the "
        "store layer, is what the API does with it:</p>"
        + verbatim("BLOCK G &mdash; captured: a 404 for a case, and a row indexed against it", BLOCK_G)
        + "<p>The row is not corrupt &mdash; it verifies against its own checksum &mdash; it is "
          "<b>orphaned</b>, and <span class='mono'>ix_evidence_dossier</span> indexes a value that "
          "matches nothing. After this batch the writer cannot create one, so the 404 and the indexed row "
          "can no longer disagree by accident; they can still disagree by design, at the store layer, "
          "which limitation 3 carries.</p>",

        # -- 9 ------------------------------------------------------------------
        "<h3>9 &middot; The gate: one tuple, both halves, and why one half alone proves nothing"
        "<span class='tag'>docs/15 &sect;13.3</span></h3>"
        "<p>A test asserting only <i>&ldquo;a dangling parent is refused&rdquo;</i> passes on a writer "
        "that refuses <b>everything</b>. A test asserting only <i>&ldquo;a real parent is "
        "accepted&rdquo;</i> passes on a writer with <b>no guard at all</b>. That is the shape of the "
        "mistake Stage 8.4&rsquo;s receipt-time gate was built to avoid, where asserting one clock passed "
        "on either the pre-8.4 code or the same defect with the two clocks swapped. So each of the four "
        "parents is attempted <b>twice</b>, and each attempt also asserts what landed: a refusal leaves "
        "the table count <b>and</b> <span class='mono'>audit.length</span> unchanged, an acceptance adds "
        "exactly one row.</p>"
        + "<div class='card'>" + gate_table() + "</div>"
        + "<p>Both halves come from <b>one</b> module-level tuple "
          "(<span class='mono'>_PARENTS</span>), with "
          "<span class='mono'>DANGLING_PARENTS</span> and "
          "<span class='mono'>GROUNDED_PARENTS</span> derived from it by two comprehensions. The "
          "derivation is the point: a parent removed from the tuple disappears from <b>both</b> tests at "
          "once, so the gate cannot be narrowed by editing one of them, and the four rows above are the "
          "tuple&rsquo;s contents rather than a description of them.</p>",

        # -- 10 -----------------------------------------------------------------
        "<h3>10 &middot; Nine tampered sites, nine caught &mdash; and the one that passed silently first"
        "<span class='tag'>docs/15 &sect;13.4</span></h3>"
        "<p>Baseline <b>276</b> collected over the four test files that exercise these writers, each site "
        "applied to a backup-and-restore copy of one source file, the suite re-run, and the file restored. "
        "The middle three rows are ruling 3&rsquo;s actual ask: deleting a guard that <b>predates this "
        "batch</b> now fails a test that names the parent.</p>"
        + "<div class='card'>" + tamper_table() + "</div>"
        + verbatim("captured: nine sites, four files, every one restored afterwards", BLOCK_TAMPER)
        + "<p><b>The silent pass is the finding of this batch&rsquo;s own gate.</b> Deleting the "
          "empty-string branch left <b>275 passing</b>: with the branch gone, "
          "<span class='mono'>''</span> fell through to the lookup and was refused by the "
          "<i>dangling</i> message, and the assertion as drafted &mdash; "
          "<span class='mono'>str(empty.value) != str(dangling.value)</span> plus "
          "<span class='mono'>\"None\" in str(empty.value)</span> &mdash; was satisfied by that folded "
          "message, because it interpolates the value and ends by naming "
          "<span class='mono'>None</span> as the alternative. Two mistakes in one assertion: it compared "
          "two messages without pinning either, and it accepted a message that was true of a "
          "<b>different condition</b>. The test now pins each refusal with "
          "<span class='mono'>match=</span> against text only that branch produces "
          "(<span class='mono'>\"an empty string is neither\"</span> / "
          "<span class='mono'>\"does not exist\"</span>), asserts the empty-string message does <b>not</b> "
          "contain the dangling one&rsquo;s phrase, and is parametrised over "
          "<span class='mono'>''</span> and <span class='mono'>'   '</span> on the model of the "
          "contradiction test beside it. The site now fails <b>2 of 68</b>. Its docstring records that "
          "tampering found it, because an assertion strengthened after a silent pass is the only kind "
          "whose weakness is documented rather than inherited.</p>",

        # -- 11 -----------------------------------------------------------------
        "<h3>11 &middot; All nine declared foreign keys, because four parents is not the whole map"
        "<span class='tag'>docs/15 &sect;13.5 &middot; F-26 requested</span></h3>"
        "<p>&ldquo;Which parents does this codebase check?&rdquo; is only answerable against the whole "
        "map and not against the three intelligence tables &mdash; which is how F-25 was missed in the "
        "first place, since a batch that looks at its own table finds its own table&rsquo;s guards. This "
        "is <span class='mono'>PRAGMA foreign_key_list</span> over <b>every</b> table in a live "
        "post-migration database:</p>"
        + "<div class='card'>" + fk_table() + "</div>"
        + "<p>Plus one reference that is not a foreign key at all: "
          "<span class='mono'>memory_item</span>&rsquo;s <span class='mono'>evidence_ids</span>, inside "
          "<span class='mono'>payload</span>, guarded by "
          "<span class='mono'>record_memory_item</span> since 8.5 &mdash; which is why the gate names "
          "<b>four</b> parents and not three. The five unguarded rows are the trading path, and they are "
          "unguarded for a <b>structural</b> reason rather than an oversight: "
          "<span class='mono'>save_decision</span> takes a "
          "<span class='mono'>DecisionRecord</span>, <span class='mono'>save_intent</span> a "
          "<span class='mono'>TradeIntent</span>, <span class='mono'>save_approval</span> an "
          "<span class='mono'>ApprovalRecord</span> &mdash; domain objects, with <b>no store in the "
          "seam</b> &mdash; and nothing in <span class='mono'>src/</span> calls them, so there is no "
          "writer to put a guard in. <span class='mono'>DecisionRecord.instrument_id</span> is an "
          "unvalidated optional string, so a dangling instrument is <b>representable</b> today; it is not "
          "<b>writable</b> by any code path, because no code path writes it. Whether that is a finding now "
          "or a note for Stage 9 is &sect;15 question 3, and this table measures it either way.</p>",

        # -- 12 -----------------------------------------------------------------
        "<h3>12 &middot; What this batch did not touch, counted rather than claimed"
        "<span class='tag'>docs/15 &sect;13.0</span></h3>"
        + verbatim("BLOCK H &mdash; captured: migrations, checksums, projections, routes, and the diff",
                   BLOCK_H),

        # -- 13 -----------------------------------------------------------------
        "<h3>13 &middot; The full gate, and the per-file arithmetic behind &ldquo;+14 in one file&rdquo;"
        "<span class='tag'>docs/15 &sect;13.6</span></h3>"
        "<p><b>1,408 passed / 2 skipped / 0 failed</b> &mdash; +14 over 8.5&rsquo;s 1,394, and both skips "
        "are the pre-existing ones (<span class='mono'>test_live_endpoints.py:84</span>, "
        "<span class='mono'>test_archive_bars.py:117</span>). Every one of the fourteen is in "
        "<span class='mono'>test_evidence_writer.py</span> (<b>54 &rarr; 68</b>), and the other six files "
        "are unchanged in count, which is the arithmetic check on &ldquo;one file&rsquo;s worth of tests "
        "were added&rdquo;: <b>+7 test functions for +14 tests</b> &mdash; two four-parent gates "
        "parametrised over the derived halves (<b>4 + 4</b> cases), one empty-string test parametrised "
        "over <span class=\'mono\'>\'\'</span> and <span class=\'mono\'>\'   \'</span> (<b>2</b>), "
        "and four single tests: the refusal, the id stored as given, "
        "<span class=\'mono\'>record_snapshot</span>\'s inheritance, and the layering pin. "
        "<b>42 + 7 = 49</b> functions and <b>54 + 14 = 68</b> tests, and this one file\'s diff reads "
        "<b>261 insertions and 0 deletions</b> &mdash; the re-aimed test gained its parent, its assertion "
        "and a docstring saying why, without losing a line. No adapter changed, so <b>no live endpoint was "
        "called</b> and no venue run speaks to this batch.</p>"
        + verbatim("captured: the four gates and the seven per-file counts", BLOCK_GATE),

        # -- 14 -----------------------------------------------------------------
        "<h3>14 &middot; Limitations of this batch<span class='tag'>docs/15 &sect;13.7</span></h3>"
        "<p>Eight, published in full rather than summarised. Limitations 3 and 4 are the two a reviewer is "
        "most likely to ask about: an orphan is still writable where the writer is not, and the gate&rsquo;s "
        "four parents are a hand-extended tuple.</p>"
        + "<div class='card'>" + limitation_table() + "</div>",

        # -- 15 -----------------------------------------------------------------
        "<h3>15 &middot; Decision requested, and answered &mdash; four questions, each with one marked "
        "recommendation"
        "<span class='tag'>docs/15 &sect;13.8 &middot; answered as D-055, &sect;16</span></h3>"
        + "<div class='card'>" + decision_table() + "</div>"
        + "<p>No <span class='mono'>D-0nn</span> row is written in "
          "<span class='mono'>docs/07</span> and no finding is closed in "
          "<span class='mono'>docs/00</span> until the owner rules: <b>approval is never inferred</b>, and "
          "a stage that is complete is not a stage that is approved. F-25 was <b>fixed in code</b> with its "
          "closure <b>requested</b> by question 1 rather than assumed. <b>Answered 2026-11-28 as "
          "D-055</b> (&sect;16): all four questions <span class='ok'>Recommend</span>, each against exactly "
          "one marked recommendation, and both rows in the register now read "
          "<span class='mono'>REVIEWED &mdash; APPROVED 2026-11-28</span>.</p>",

        # -- 16 -----------------------------------------------------------------
        "<h3>16 &middot; D-055 &mdash; the four rulings, what F-26 records, and what the ruling does not do"
        "<span class='tag'>answered 2026-11-28 &middot; docs/15 &sect;13.9</span></h3>"
        "<p>All four questions in &sect;15 were answered <span class='ok'>Recommend</span>, each against "
        "exactly one marked recommendation, and are recorded as <b>D-055</b>. &sect;15 is left as it was "
        "put; this section is the ruling. <b>No code changed</b> &mdash; <span class='mono'>git diff "
        "f15eb43 HEAD -- backend/</span> is empty &mdash; and the gate re-ran anyway, because this section "
        "quotes what it produces: <b>1,408 passed / 2 skipped / 0 failed</b>, "
        "<span class='mono'>ruff check src tests</span> clean, <span class='mono'>ruff format --check</span> "
        "unchanged on <b>93</b> files, mypy strict clean on <b>62</b>.</p>"
        + "<div class='card'>" + ruling_table() + "</div>"
        + "<p><b>F-26, in the terms &sect;11 measured it.</b> Five of the nine declared foreign keys in the "
          "live schema have no writer that <i>could</i> guard them: "
          "<span class='mono'>decision.instrument_id</span>, "
          "<span class='mono'>trade_intent.decision_id</span>, "
          "<span class='mono'>orders.intent_id</span>, <span class='mono'>fills.order_id</span> and "
          "<span class='mono'>approval.intent_id</span>. The reason is structural rather than an oversight "
          "&mdash; <span class='mono'>save_decision</span> takes a "
          "<span class='mono'>DecisionRecord</span>, <span class='mono'>save_intent</span> a "
          "<span class='mono'>TradeIntent</span>, <span class='mono'>save_approval</span> an "
          "<span class='mono'>ApprovalRecord</span>, domain objects with <b>no store in the signature</b>, "
          "and nothing in <span class='mono'>src/</span> calls any of the three; "
          "<span class='mono'>orders</span> and <span class='mono'>fills</span> are written only by "
          "projection. So the guard the three intelligence writers have <b>cannot be added there without "
          "changing the seam</b>. Beside it, <span class='mono'>DecisionRecord.instrument_id</span> is an "
          "unvalidated optional string, so a dangling instrument is <b>representable</b> in the domain model "
          "today &mdash; and not <b>writable</b>, because no code path writes one. Nothing is orphaned "
          "today, which is why this is a finding about a decision and not a defect in code that runs. "
          "<b>The decision Stage 9 will have to make</b> is which of two postures the trading path takes: "
          "either those writers gain a store in the seam, so a parent can be checked before a row is written "
          "the way <span class='mono'>open_dossier</span>, "
          "<span class='mono'>record_evidence</span> and "
          "<span class='mono'>record_memory_item</span> each do; or the trading path accepts that its "
          "parents are checked <b>upstream</b>, in whatever produces a "
          "<span class='mono'>DecisionRecord</span>, and says so in a document instead of leaving it to be "
          "inferred from five unguarded <span class='mono'>REFERENCES</span> clauses. F-26 exists so that "
          "question is asked <b>before</b> a writer is written, and not after.</p>"
        + "<p><b>What this ruling does not do</b>, stated so nobody has to infer it. It does <b>not</b> "
          "close <b>F-18</b>: gap 2 (<span class='mono'>expires_at</span>) is ordered as 8.7 and gap 4 (the "
          "sufficiency meter) stays open with <b>no batch behind it</b>, declined at D-054 and not offered "
          "again here. It does <b>not</b> retire any of &sect;14&rsquo;s eight limitations, including "
          "limitation 3 &mdash; the one F-25&rsquo;s closure could most easily have been read to retire. It "
          "does <b>not</b> harden the store: "
          "<span class='mono'>save_evidence_ref</span> still accepts a dangling "
          "<span class='mono'>dossier_id</span> by design, "
          "<span class='mono'>save_dossier</span> still accepts an unmapped instrument on the same terms, "
          "and <span class='mono'>PRAGMA foreign_keys</span> still reads <b>0</b>, because a check in the "
          "projection target would make boot recovery depend on a read and could fail the replay of an event "
          "the chain already holds. It does <b>not</b> wire either writer: nothing in "
          "<span class='mono'>src/</span> calls <span class='mono'>record_memory_item</span> or "
          "<span class='mono'>record_evidence</span>, no route serves "
          "<span class='mono'>memory_item</span>, and a belief stays <b>recordable</b> and still not "
          "<b>readable over HTTP</b>. It does <b>not</b> close &sect;11.12&rsquo;s limitation 1 &mdash; "
          "<span class='mono'>evidence_ref.retrieved_at</span> still has no caller, offered at D-053, "
          "offered again at D-054 and declined both times. It does <b>not</b> touch <b>F-22</b> "
          "(<span class='mono'>O-014</span>), which D-052&rsquo;s ruling 4 recorded precisely so it would "
          "not be closed by accident, and it does not touch F-17 or F-19. And it does <b>not</b> change a "
          "single number in this board: the gate, the tamper proof, the inventory and the file counts are "
          "all quoted here as measured at <span class='mono'>f15eb43</span>.</p>"
        + "<p><b>Finding ids after this ruling.</b> <b>F-25 "
          "<span class='ok'>CLOSED</span></b> 2026-11-28 (D-055), on the defect &sect;12.9 named. "
          "<b>F-26 <span class='no'>OPEN</span></b>, recorded by this ruling, no batch behind it. "
          "<b>F-24 stays <span class='no'>OPEN</span></b> with no batch behind it, because the shape of a "
          "band has no ruling: 8.5 delivered the time axis and the confidence axis is still one number where "
          "<span class='mono'>docs/10</span> &sect;3.1 asks for a band. <b>F-18 is NARROWED</b> &mdash; gaps "
          "1 and 3 <span class='ok'>CLOSED</span>, gap 2 ordered as 8.7, gap 4 "
          "<span class='no'>OPEN</span> with no batch. <b>F-22/<span class='mono'>O-014</span> stays "
          "<span class='no'>OPEN</span></b>. <b>The next finding id is F-27.</b> <b>Next: 8.7 = "
          "<span class='mono'>expires_at</span> on <span class='mono'>memory_item</span> only</b>, ordered "
          "by ruling 4 and <b>not started</b> &mdash; no migration, no column and no writer argument exists "
          "in the tree at <span class='mono'>f15eb43</span>.</p>",
    ])

    html_out = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Nexus-AI &middot; Stage 8.6 Intelligence Memory &mdash; The Fourth Parent</title>"
        "<style>" + tokens + "\n" + fonts_css() + "\n" + CSS + "</style></head><body><div class='wrap'>"
        "<div class=\"lede\">Nexus-AI &middot; Stage 8 of 23 &middot; sub-deliverable 8.6 &middot; "
        "ordered by D-054&rsquo;s ruling 3 as <b>F-25 alone</b> &middot; "
        "<b>APPROVED 2026-11-28 (D-055)</b> &middot; <b>F-25 CLOSED</b> on the defect &sect;12.9 "
        "named, <b>not</b> on orphans in general &middot; <b>F-26 OPEN</b>, recorded against the "
        "trading-path seam &middot; next finding id <b>F-27</b> &middot; next <b>8.7 = "
        "<span class=\"mono\">expires_at</span> on <span class=\"mono\">memory_item</span> only</b>, "
        "ordered and not started</div>"
        "<h1 style=\"font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);"
        "margin:6px 0 0\">The fourth parent is guarded &mdash; and a gate that names all four, both halves, "
        "from one tuple</h1>"
        "<div class=\"ribbon\">This batch changes <b>three files</b>, <b>+339 / &minus;2</b>, and one of the three is four "
        "lines of docstring. "
        "<span class=\"mono\">intelligence/evidence.py</span> 444&nbsp;&rarr;&nbsp;<b>516</b>, "
        "<span class=\"mono\">store/operational.py</span> +4 <b>docstring only</b>, "
        "<span class=\"mono\">tests/test_evidence_writer.py</span> 840&nbsp;&rarr;&nbsp;<b>1,101</b> "
        "(<b>54 &rarr; 68</b> tests, <b>42 &rarr; 49</b> functions, one re-aimed and none deleted). Gate "
        "<b>1,408 passed / 2 skipped / 0 failed</b>, mypy strict clean on <b>62</b>, ruff and format clean "
        "on <b>93</b>, hygiene <b>88</b> unchanged. <b>No migration, no column, no route, no schema "
        "text</b>: <span class=\"mono\">git diff HEAD -- store/schema.py migrations/ api/app.py</span> is "
        "empty, <span class=\"mono\">MIGRATIONS</span> still <b>5</b> with the same checksums, "
        "<span class=\"mono\">PROJECTABLE</span> still <b>15</b>, "
        "<span class=\"mono\">CHECKSUMMED_FIELDS</span> still <b>10 of 12</b>, routes still <b>13</b>, gaps "
        "still <b>9</b>. <b>Two refusals, two messages</b>: <span class=\"mono\">None</span> is the "
        "legitimate &ldquo;belongs to no case yet&rdquo; and <span class=\"mono\">''</span> is no name at "
        "all, so neither is told the other&rsquo;s reason. The id is stored <b>as given</b> &mdash; "
        "padding, a trailing newline and a case-fold all make it dangling rather than being normalised into "
        "something the caller did not say. The guard is in the <b>writer</b> and not in "
        "<span class=\"mono\">save_evidence_ref</span>, because a check in the store would make boot "
        "recovery depend on a read and could fail the replay of an event the chain already holds &mdash; "
        "and a test now pins that layering. <span class=\"mono\">record_snapshot</span> inherits the "
        "refusal by forwarding. The gate holds <b>one tuple</b> as its source of truth and derives "
        "<b>both halves</b> from it, a dangling parent refused <i>and</i> a real one accepted, because "
        "either half alone passes on a writer that refuses everything or on one with no guard at all "
        "&mdash; the mistake 8.4&rsquo;s receipt-time gate was built to avoid. Proven load-bearing at "
        "<b>nine</b> tampered sites with <b>zero</b> silent passes <b>after one was found</b>: deleting the "
        "empty-string branch passed <b>275</b> tests on the first run because the assertion compared two "
        "messages without pinning either, and the dangling message interpolates the value and names "
        "<span class=\"mono\">None</span> as the alternative; the test now pins each branch with "
        "<span class=\"mono\">match=</span> and fails <b>2 of 68</b>. <b>Three of the nine sites delete a "
        "guard that predates this batch</b> (<span class=\"mono\">contradicts</span>, "
        "<span class=\"mono\">instrument_id</span>, <span class=\"mono\">evidence_ids</span>) and each "
        "fails a test that names the parent &mdash; ruling 3&rsquo;s &ldquo;the fourth cannot go missing "
        "again without a red gate&rdquo; measured rather than promised. The widest site is refusing "
        "<span class=\"mono\">None</span> too, at <b>83</b> failures. <b>All nine declared foreign keys "
        "inventoried</b> from the live schema: <b>3</b> guarded by a writer, <b>1</b> by construction, "
        "<b>5</b> on the trading path with no writer to guard them &mdash; "
        "<span class=\"mono\">save_decision</span>, <span class=\"mono\">save_intent</span> and "
        "<span class=\"mono\">save_approval</span> take domain objects with no store in the seam and "
        "<span class=\"mono\">DecisionRecord.instrument_id</span> is an unvalidated optional string, so a "
        "dangling instrument is representable though nothing writes one &mdash; put to the owner as "
        "<b>F-26</b>. <span class=\"mono\">src</span> stays at <b>62</b> files (16,181&nbsp;&rarr;&nbsp;"
        "<b>16,257</b> lines) and <span class=\"mono\">tests</span> at <b>31</b> "
        "(19,121&nbsp;&rarr;&nbsp;<b>19,382</b>), both baselines re-derived from "
        "<span class=\"mono\">git archive HEAD</span> into a scratch tree. No adapter changed, so no live "
        "endpoint was called and no venue run speaks to this batch &middot; <b>eight</b> limitations "
        "published in full &middot; <b>APPROVED 2026-11-28 as D-055</b> "
        "(&sect;16): <b>F-25 CLOSED</b> on the defect, not on orphans; the gate stays; <b>F-26 OPEN</b> "
        "against the trading-path seam; next finding id <b>F-27</b>; next <b>8.7 = "
        "<span class=\"mono\">expires_at</span></b> on <span class=\"mono\">memory_item</span> "
        "<b>only</b>, ordered and not started</div>"
        + body
        + "<footer>Stage 8.6 &middot; <b>F-25 alone</b>, as D-054&rsquo;s ruling 3 ordered &middot; "
          "<b>APPROVED 2026-11-28 (D-055)</b>, all four questions in &sect;15 answered "
          "<b>Recommend</b> and ruled in &sect;16 &middot; <b>F-25 CLOSED</b> on the defect &sect;12.9 "
          "named and <b>not</b> on orphans in general, so &sect;14&rsquo;s limitation 3 stays published "
          "beside the closure &middot; <b>F-26 OPEN</b> against the trading-path seam, a finding about the "
          "seam rather than a defect in shipped behaviour and <b>not</b> an "
          "<span class=\"mono\">O-</span> row &middot; the gate <b>stays</b> in "
          "<span class=\"mono\">test_evidence_writer.py</span>, limitation 6 accepted as the cost "
          "&middot; <b>the next finding id is F-27</b> &middot; <b>three files, +339 / &minus;2</b>, one of them four lines of docstring "
          "&middot; <b>no migration, no column, no route, no schema text</b> &middot; "
          "<span class=\"mono\">record_evidence</span> refuses a "
          "<span class=\"mono\">dossier_id</span> the store has never held, with <b>two branches and two "
          "messages</b>, and <span class=\"mono\">None</span> stays the legitimate &ldquo;belongs to no "
          "case yet&rdquo; &middot; the id is stored <b>as given</b>: padding, a newline and a case-fold "
          "are dangling, not normalised &middot; the guard is in the <b>writer</b>, the store stays "
          "check-free so boot recovery never depends on a read, and a test pins the layering &middot; "
          "<span class=\"mono\">record_snapshot</span> inherits by forwarding &middot; the four-parent gate "
          "holds <b>one tuple</b> and derives <b>both halves</b> from it &middot; <b>nine</b> tampered "
          "sites, <b>nine</b> caught, <b>zero</b> silent passes after <b>one</b> was found and a weak "
          "assertion strengthened rather than a guard relaxed &middot; <b>three</b> of the nine delete a "
          "guard that predates this batch &middot; all <b>nine</b> declared foreign keys inventoried: 3 "
          "guarded, 1 by construction, <b>5</b> with no writer to guard them &rarr; <b>F-26</b> requested "
          "&middot; gate <b>1,408 passed / 2 skipped / 0 failed</b> (+14, all in one file: 54 &rarr; 68), "
          "mypy strict clean on <b>62</b>, ruff and format clean on <b>93</b> &middot; "
          "<span class=\"mono\">src</span> <b>62</b> files and <b>16,257</b> lines, "
          "<span class=\"mono\">tests</span> <b>31</b> and <b>19,382</b>, both re-derived from "
          "<span class=\"mono\">git archive HEAD</span> &middot; <b>eight</b> limitations published in "
          "full, including that an orphan is still writable at the store layer and that the tuple is "
          "extended by hand &middot; F-24 still open with no batch, F-18 still narrowed with gaps 2 and 4 "
          "open, <span class=\"mono\">O-014</span>/F-22 untouched &middot; no adapter changed, so no live "
          "run speaks to this batch &middot; next: <b>8.7 = "
          "<span class=\"mono\">expires_at</span></b> on <span class=\"mono\">memory_item</span> "
          "<b>only</b>, ordered by ruling 4 and <b>not started</b> &mdash; one nullable "
          "<span class=\"mono\">ADD COLUMN</span> with no rebuild, one writer argument, and nothing "
          "acting on it until <span class=\"mono\">docs/10</span> &sect;3.2&rsquo;s "
          "V1&ndash;V3 gates consume it</footer>"
          "</div></body></html>"
    )

    out = HERE / "stage8-6-the-fourth-parent.html"
    out.write_text(html_out)
    return out


if __name__ == "__main__":
    path = main()
    print(f"wrote {path} ({path.stat().st_size // 1024} KB)")
