"""Stage 8.7 board: the fourth clock — `expires_at` on `memory_item`, stored and acted on by nothing.

D-055's ruling 4 ordered this batch and scoped it in one sentence: `expires_at` on `memory_item` only — one
nullable `ADD COLUMN`, one writer argument, and nothing acting on it, because the gates that would consume an
expiry are `docs/10` §3.2's V1–V3, which finalise at Stage 11. §1 lists what that ruling therefore left out,
and §10 counts what did not move.

Every transcript here was captured from `backend/.venv/bin/python` runs against a database booted the way the
tests boot one — a single file holding both stores, so all six migrations apply and 0003 is not skipped — from
`pytest` runs, or from the tamper script, and pasted verbatim. That includes the thirteen tamper sites, one of
which passed silently on the first run and found a missing test rather than a weak one; the three versions of
the "nothing acts on it" scan, two of which failed against prose; and F-27, measured over all six migrations.
Captures: `/tmp/cap87.py` (BLOCKS A–H), `/tmp/gate87.txt`, `/tmp/tamper87.py`.

Run:  cd backend && .venv/bin/python ../design/build_board87.py
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
   8.3, 8.4, 8.5 and 8.6 boards recorded. Copied from `build_specimen.py`, the approved visual language. */
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
# Captures. Injected verbatim from /tmp/cap87_out.txt, /tmp/gate87.txt and /tmp/tamper87b.txt by
# the generator that built this file: a transcript that is transcribed is a transcript that can be
# improved, and §12.14 exists because one was.
# ---------------------------------------------------------------------------------------------
# --- CAPTURES ---
BLOCK_A = """
  migrations applied: 6, skipped: 0
  last two: ['0005_memory_beliefs', '0006_memory_expiry']
  memory_item columns before 0006: 14
  memory_item columns after  0006: 15
  the difference: ['expires_at']
  0006 checksum: f54eecd2c3f6c2c633223a6c531d63be50bc4d1867f3815a2ce8b1821c43fedb
  0006 statements (recorded): 1   (ALTER/CREATE, comments stripped): 1
  0006 requires: 'memory_item'
  0005 checksum unchanged: 4520e5b5e259eb4c868b70d1bfdc5ebdbac58f32d7083ea00cc4e980ac789c28
  index_list before 0006: ['ix_memory_created', 'ix_memory_kind', 'sqlite_autoindex_memory_item_1']
  index_list after  0006: ['ix_memory_created', 'ix_memory_kind', 'sqlite_autoindex_memory_item_1']
  the two sets are equal: True
"""

BLOCK_B = """
  one belief, four clocks, each a different question:
    created_at   2026-11-28T09:51:31.660Z   when this system wrote the row
    valid_from   2026-11-27T06:00:00.000Z   from when the claim holds in the world
    valid_until  2026-12-04T06:00:00.000Z   until when the claim holds in the world
    expires_at   2027-01-03T06:00:00.000Z   when this system should stop serving the row

  the claim holds until 2026-12-04T06:00:00.000Z but expires 2027-01-03T06:00:00.000Z:
    the two disagree, and the disagreement is stored rather than resolved
  validity_of(row) keys: ['change_conditions', 'evidence_ids', 'valid_from', 'valid_until', 'validity_open_ended']
    -> the expiry is NOT among them: validity is the world's axis, expiry is this system's
  receipt.expires_at == row['expires_at']: True
  receipt.to_dict()['expires_at']: 2027-01-03T06:00:00.000Z
"""

BLOCK_C = """
  an item recorded with no expiry: row=None receipt=None
    created_at on the same row: '2026-11-28T09:51:31.705Z'  <- not used as a default
  PRAGMA: type='TEXT' notnull=0 default=None
  a raw INSERT naming no expiry stores: None
    NULL means 'no expiry was stated', which is not the claim 'never expires'
"""

BLOCK_D = """
  seven expiries through one writer:
    naive datetime                     -> REFUSED: expires_at must be an aware UTC datetime; got a naive '2027-01-03T06:00:00'…
    already expired (400 days past)    -> ACCEPTED, stored '2025-10-23T06:00:00.000Z'
    one day BEFORE valid_from          -> ACCEPTED, stored '2026-11-26T06:00:00.000Z'
    exactly valid_from                 -> ACCEPTED, stored '2026-11-27T06:00:00.000Z'
    exactly valid_until                -> ACCEPTED, stored '2026-12-04T06:00:00.000Z'
    a decade AFTER valid_until         -> ACCEPTED, stored '2036-12-01T06:00:00.000Z'
    not stated (None)                  -> ACCEPTED, stored None

  the one refusal is about the datetime's own awareness, not about its position on a
  timeline: expires_at is never compared with valid_from, valid_until or created_at,
  because those are different clocks on different axes and a refusal built on ordering
  them would assert a relationship the schema deliberately does not have.
"""

BLOCK_E = """
  migration                   recorded  applied   prose ;
  0001_operational                  19       19         0
  0002_memory                        8        8         0
  0003_audit_append_only             4        4         0
  0004_memory_fidelity              15       13         2  <-- disagree
  0005_memory_beliefs                4        4         0
  0006_memory_expiry                 1        1         0

  `Migration.statements` is `len([p for p in self.sql.split(';') if p.strip()])`: it does
  not strip `--` comment lines, and it does not know that a trigger body is one statement
  with semicolons inside it. So a semicolon in a migration's own prose is counted as a
  statement. The number is bookkeeping — stored in `schema_migrations` and served by the
  API — so nothing misbehaves, but it is not a count of what was applied, and
  `test_the_runner_records_what_it_applied` pins the inflated values. 0006's comment
  carries no semicolons, deliberately, so this batch does not add to the tally.
"""

BLOCK_F = """
  one item expired 400 days ago, one expiring in a year: memory_items() serves 2 of 2
    the expired one is in the list: True
  memory_items() parameters: kind, scope, limit — no expiry, no 'currently valid'
  app.py mentions memory_item: True
  app.py mentions expires_at: False
  PROJECTABLE: 15 event types, memory.recorded among them: True
  the column is stored and acted on by nothing: no filter, no route, no policy. A
  `WHERE expires_at > now()` in the store would be an expiry policy decided in a query,
  invisible to a caller, hiding rows a reader has no way to ask for.
"""

BLOCK_G = """
  rows after DELETE FROM memory_item: 0
  reproject_missing() reapplied 3 event(s); this one among them: True
  created_at   before=2026-11-28T09:51:31.860Z  after=2026-11-28T09:51:31.860Z  identical=True
  expires_at   before=2027-01-03T06:00:00.000Z  after=2027-01-03T06:00:00.000Z  identical=True
  whole row byte-identical: True
  the expiry rides inside the audited event, so a replay reproduces it instead of
  restamping it with the replay's clock — the defect created_at was moved inside the
  event to avoid.
"""

BLOCK_H = """
  git diff --stat -- backend/:
    backend/migrations/0002_memory.sql       |  33 ++++-
     backend/src/nexus/intelligence/memory.py |  43 ++++--
     backend/src/nexus/store/operational.py   |  28 ++--
     backend/src/nexus/store/schema.py        |  55 +++++++
     backend/tests/test_memory_writer.py      | 238 +++++++++++++++++++++++++++++--
     backend/tests/test_migrations.py         |  52 +++++++
     backend/tests/test_schema_fidelity.py    | 213 ++++++++++++++++++++++++++-
     7 files changed, 623 insertions(+), 39 deletions(-)

  files in api/, evidence.py, dossier.py that this batch changed: (none)
  MIGRATIONS: 6 (was 5)  |  PROJECTABLE: 15 (unchanged)
  evidence_ref columns: 12 — 'expires_at' among them: False
  migrations/*.sql files: ['0001_core.sql', '0002_memory.sql']
  ALTER TABLE memory_item in any migrations/*.sql: (none)


wrote /tmp/cap87.txt (8 blocks)
"""

BLOCK_GATE = """
$ .venv/bin/python -m pytest
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1428 passed, 2 skipped, 1 warning in 32.47s
$ .venv/bin/ruff check src tests
All checks passed!
$ .venv/bin/ruff format --check src tests
93 files already formatted
$ .venv/bin/mypy src
Success: no issues found in 62 source files
"""

BLOCK_TAMPER = """
baseline: 0 failed / 197 passed | 197 passed, 1 warning in 11.16s
CAUGHT    53 failed /  144 passed | migration: the ALTER removed, so the column never arrives
CAUGHT     5 failed /  192 passed | migration: evidence_ref gains one too, against ruling 4's scope
CAUGHT     6 failed /  191 passed | migration: a NOT NULL default invented for an unstated expiry
CAUGHT     4 failed /  193 passed | migration: an index built for a column nothing queries
CAUGHT     1 failed /  196 passed | migration: 0006's requires dropped, so it is no longer deferrable
CAUGHT     1 failed /  196 passed | writer: the aware-datetime refusal removed
CAUGHT    46 failed /  151 passed | writer: the expiry no longer rides in the audited event
CAUGHT     2 failed /  195 passed | writer: the expiry folded into validity_of, collapsing the two axes
CAUGHT     4 failed /  193 passed | writer: an over-reach added, comparing two clocks on different axes
CAUGHT    46 failed /  151 passed | writer: the receipt stops carrying the expiry
CAUGHT     6 failed /  191 passed | store: the projection writes NULL instead of the value it was given
CAUGHT     1 failed /  196 passed | store: an unstated expiry defaulted to the write clock
CAUGHT     3 failed /  194 passed | store: the forbidden expiry filter added to memory_items()
silent passes / bad anchors: 0
tree restored: 3 files, hashes match, suite back to 0 failed / 197 passed
EXIT 0
"""


def scope_table() -> str:
    """§1 — what ruling 4's scope left out, with the reason for each absence."""
    return table(
        ["Not done", "Why it is not done"],
        [
            ("<b>No expiry filter</b> anywhere — not in <span class='mono'>memory_items()</span>, not in a "
             "route",
             "A <span class='mono'>WHERE expires_at &gt; now()</span> in the store would be an expiry "
             "<b>policy decided in a query</b>: invisible to a caller, hiding rows a reader has no way to ask "
             "for, and arriving before the V1–V3 gates that are supposed to decide it. §5 is the scan that "
             "says so"),
            ("<b>No <span class='mono'>is_expired()</span>-style reader</b> on "
             "<span class='mono'>memory_item</span>",
             "<span class='mono'>execution/intent.py:109-146</span> has exactly that shape, and it is the "
             "precedent for a <b>trading</b> deadline where an unfilled intent must stop being fillable. A "
             "belief is not an order: deciding when this system stops trusting one is Stage 11's business, "
             "and writing the reader now would put that decision in a property nobody ruled on"),
            ("<b>No expiry on <span class='mono'>evidence_ref</span> or "
             "<span class='mono'>dossier</span></b>",
             "Ruling 4 in terms. Evidence's freshness is already two columns and a "
             "<span class='mono'>data_status</span>; a third clock on the table whose two clocks F-14 spent a "
             "batch separating would be the wrong kind of company"),
            ("<b>No new refusal for a past expiry</b>",
             "§4. An item whose expiry has passed is legitimate to have recorded; refusing it would make the "
             "writer the arbiter of which beliefs should never have existed. F-18's gap 2 asked for a column, "
             "not a purge"),
            ("<b>No comparison between <span class='mono'>expires_at</span> and "
             "<span class='mono'>valid_from</span> / <span class='mono'>valid_until</span> / "
             "<span class='mono'>created_at</span></b>",
             "The two axes answer different questions (§3). A refusal built on ordering them would assert a "
             "relationship the schema deliberately does not have — <b>F-14's lesson read in reverse</b>: "
             "clocks kept apart in the columns have to stay apart in the rules too"),
            ("<b>No route, no view, no gap text</b>",
             "<span class='mono'>git diff</span> over <span class='mono'>src/nexus/api/</span>, "
             "<span class='mono'>intelligence/evidence.py</span> and "
             "<span class='mono'>intelligence/dossier.py</span> is <b>empty</b>. "
             "<span class='mono'>app.py</span> does not contain the string "
             "<span class='mono'>expires_at</span> at all; its only mentions of "
             "<span class='mono'>memory_item</span> are gap prose that already says <i>&ldquo;there is no "
             "memory_item route&rdquo;</i>"),
            ("<b>No rebuild, no row copied</b>",
             "§5.3's executed survey lists <span class='mono'>ADD COLUMN</span> as <span class='ok'>OK</span> "
             "on SQLite, so this is <span class='mono'>0005</span>'s shape and not "
             "<span class='mono'>0004</span>'s: one statement against a live table, and the rows stay where "
             "they are"),
        ],
    )


def migration_table() -> str:
    """§2 — measured on a database the runner booted, before and after 0006."""
    return table(
        ["", "before <span class='mono'>0006</span>", "after <span class='mono'>0006</span>"],
        [
            ("<span class='mono'>memory_item</span> columns", "14", "<b>15</b>"),
            ("the difference", "&mdash;", "<span class='mono'>expires_at</span>"),
            ("<span class='mono'>evidence_ref</span> columns", "12",
             "<b>12</b> — unchanged, <span class='mono'>expires_at</span> absent"),
            ("<span class='mono'>PRAGMA index_list(memory_item)</span>",
             "<span class='mono'>ix_memory_created</span>, <span class='mono'>ix_memory_kind</span>, "
             "<span class='mono'>sqlite_autoindex_memory_item_1</span>",
             "<b>the same three, asserted equal</b>"),
            ("<span class='mono'>MIGRATIONS</span>", "5", "<b>6</b>"),
            ("<span class='mono'>PROJECTABLE</span>", "15",
             "<b>15</b> — <span class='mono'>memory.recorded</span> was already projectable since 8.5"),
            ("checksum <span class='mono'>0005_memory_beliefs</span>",
             "<span class='mono'>4520e5b5e259eb4c&hellip;</span>",
             "<span class='mono'>4520e5b5e259eb4c&hellip;</span> — <b>unchanged</b>"),
            ("checksum <span class='mono'>0006_memory_expiry</span>", "&mdash;",
             "<span class='mono'>f54eecd2c3f6c2c6&hellip;</span>"),
        ],
    )


def not_table() -> str:
    """§2 — the five things the one statement deliberately is not."""
    return table(
        ["The statement is not&hellip;", "Measured", "Why it matters"],
        [
            ("<b><span class='mono'>NOT NULL</span></b>",
             "<span class='mono'>PRAGMA table_info</span> &rarr; <span class='mono'>notnull=0</span>",
             "A belief recorded before this batch has no expiry, and one recorded after may still have none. "
             "<span class='mono'>NULL</span> is the honest value for <i>&ldquo;no expiry was stated&rdquo;</i>, "
             "which is not the claim <i>&ldquo;never expires&rdquo;</i>. <span class='mono'>NOT NULL</span> "
             "would have forced the second claim onto every existing row"),
            ("<b>defaulted</b>",
             "<span class='mono'>default=None</span>, and a raw <span class='mono'>INSERT</span> naming no "
             "expiry stores <span class='mono'>NULL</span>",
             "A default computed from <span class='mono'>created_at</span> would turn an unstated expiry into a "
             "stated one, silently, in the schema — the collapse "
             "<span class='mono'>validity_open_ended</span> avoids by deriving rather than defaulting"),
            ("<b><span class='mono'>CHECK</span>ed</b>",
             "no constraint relates <span class='mono'>expires_at</span> to anything",
             "See §4 for what that permits, measured: six of seven expiries are accepted, including four that "
             "look like errors"),
            ("<b>indexed</b>",
             "the index set is equal on both sides of the migration",
             "An index is a bet that something queries the column. Nothing does, and a bet made in DDL is "
             "invisible to every reader who is looking at queries"),
            ("<b>on a second table</b>",
             "<span class='mono'>evidence_ref</span> stays at 12 columns",
             "Ruling 4 scoped the column to <span class='mono'>memory_item</span> alone"),
        ],
    )


def clock_table() -> str:
    """§3 — four clocks on one row, each a different question."""
    return table(
        ["column", "value on the captured row", "the question it answers"],
        [
            ("<span class='mono'>created_at</span>", "<span class='mono'>2026-11-28T09:39:25.580Z</span>",
             "when <b>this system</b> wrote the row"),
            ("<span class='mono'>valid_from</span>", "<span class='mono'>2026-11-27T06:00:00.000Z</span>",
             "from when the claim holds <b>in the world</b>"),
            ("<span class='mono'>valid_until</span>", "<span class='mono'>2026-12-04T06:00:00.000Z</span>",
             "until when the claim holds <b>in the world</b>"),
            ("<span class='mono'>expires_at</span>", "<span class='mono'>2027-01-03T06:00:00.000Z</span>",
             "when <b>this system</b> should stop serving the row"),
        ],
    )


def permit_table() -> str:
    """§4 — seven expiries through one writer."""
    return table(
        ["expiry given", "result", "stored"],
        [
            ("naive <span class='mono'>datetime(2027, 1, 3, 6, 0, 0)</span>",
             "<span class='no'><b>REFUSED</b></span>",
             "<span class='mono'>expires_at must be an aware UTC datetime; got a naive "
             "'2027-01-03T06:00:00'</span>"),
            ("400 days in the past", "<span class='ok'>accepted</span>",
             "<span class='mono'>2025-10-23T06:00:00.000Z</span>"),
            ("one day <b>before</b> <span class='mono'>valid_from</span>", "<span class='ok'>accepted</span>",
             "<span class='mono'>2026-11-26T06:00:00.000Z</span>"),
            ("exactly <span class='mono'>valid_from</span>", "<span class='ok'>accepted</span>",
             "<span class='mono'>2026-11-27T06:00:00.000Z</span>"),
            ("exactly <span class='mono'>valid_until</span>", "<span class='ok'>accepted</span>",
             "<span class='mono'>2026-12-04T06:00:00.000Z</span>"),
            ("a decade <b>after</b> <span class='mono'>valid_until</span>",
             "<span class='ok'>accepted</span>", "<span class='mono'>2036-12-01T06:00:00.000Z</span>"),
            ("not stated (<span class='mono'>None</span>)", "<span class='ok'>accepted</span>",
             "<span class='mono'>None</span>"),
        ],
    )


def f27_table() -> str:
    """§6 — the recorded statement count against the applied one, over all six migrations."""
    return table(
        ["migration", "recorded", "applied", "prose <span class='mono'>;</span>", ""],
        [
            ("<span class='mono'>0001_operational</span>", "19", "19", "0", ""),
            ("<span class='mono'>0002_memory</span>", "8", "8", "0", ""),
            ("<span class='mono'>0003_audit_append_only</span>", "<b>4</b>", "<b>2</b>", "0",
             "two triggers, each <b>one</b> statement with <span class='mono'>;</span> inside its body"),
            ("<span class='mono'>0004_memory_fidelity</span>", "<b>15</b>", "<b>13</b>", "2",
             "a semicolon in each of two comment blocks"),
            ("<span class='mono'>0005_memory_beliefs</span>", "4", "4", "0", ""),
            ("<span class='mono'>0006_memory_expiry</span>", "1", "1", "0",
             "deliberately: this batch adds nothing to the tally"),
        ],
    )


def tamper_table() -> str:
    """§8 — thirteen sites, and what caught each one."""
    body = [
        ("1", "the <span class='mono'>ALTER TABLE</span> removed, so the column never arrives", "53"),
        ("2", "<span class='mono'>evidence_ref</span> gains an expiry too, against ruling 4's scope", "5"),
        ("3", "<span class='mono'>NOT NULL DEFAULT ''</span> invented for an unstated expiry", "6"),
        ("4", "an index built for a column nothing queries", "4"),
        ("5", "<span class='mono'>0006</span>'s <span class='mono'>requires=\"memory_item\"</span> dropped",
         "<b>1</b> — <span class='no'>silent on the first run</span>, see below"),
        ("6", "the aware-datetime refusal removed from the writer", "1"),
        ("7", "the expiry no longer rides in the audited event", "46"),
        ("8", "the expiry folded into <span class='mono'>validity_of</span>, collapsing the two axes", "2"),
        ("9", "an over-reach added: <span class='mono'>expires_at &lt;= valid_until</span> refused", "4"),
        ("10", "the receipt stops carrying the expiry", "46"),
        ("11", "the projection writes <span class='mono'>NULL</span> instead of the value it was given", "6"),
        ("12", "an unstated expiry defaulted to the write clock in the store", "1"),
        ("13", "the forbidden expiry filter added to <span class='mono'>memory_items()</span>", "3"),
    ]
    return table(["#", "tamper", "tests that failed"], body)


def gate_table() -> str:
    """§9 — where the twenty new tests went."""
    return table(
        ["file", "before", "after", ""],
        [
            ("<span class='mono'>test_memory_writer.py</span>", "77", "<b>88</b>",
             "+11: the expiry class, the two re-aimed assertions, <span class='mono'>validity_of</span>"),
            ("<span class='mono'>test_schema_fidelity.py</span>", "41", "<b>49</b>",
             "+8: <span class='mono'>TestMigration0006</span>"),
            ("<span class='mono'>test_migrations.py</span>", "15", "<b>16</b>",
             "+1: the deferral branch §8 needed"),
            ("<span class='mono'>test_evidence_writer.py</span>", "68", "68", "unchanged"),
            ("<span class='mono'>test_dossier_writer.py</span>", "87", "87", "unchanged"),
            ("<span class='mono'>test_intelligence_routes.py</span>", "44", "44", "unchanged"),
            ("<span class='mono'>test_repo_hygiene.py</span>", "88", "88", "unchanged"),
        ],
    )


def limitation_table() -> str:
    """§11 — eight limitations, published in full rather than summarised."""
    return table(
        ["#", "Limitation"],
        [
            ("1", "<b>The column is inert by design.</b> Nothing in <span class='mono'>src/</span> reads "
                  "<span class='mono'>expires_at</span> on <span class='mono'>memory_item</span>, so a row "
                  "that should have stopped being served is still served. That is ruling 4, not an oversight "
                  "— but it means the expiry delivers <b>no behaviour</b> until Stage 11's V1–V3 gates consume "
                  "it. A reader who sees &ldquo;8.7 delivered expiring TTLs&rdquo; would be wrong: 8.7 "
                  "delivered the <b>column</b> <span class='mono'>docs/10</span> §3.1's &ldquo;expiring "
                  "TTLs&rdquo; needs, and the TTL itself is still unwritten"),
            ("2", "<b><span class='mono'>memory_items()</span> cannot ask for &ldquo;currently "
                  "valid&rdquo;.</b> Its three parameters are <span class='mono'>kind</span>, "
                  "<span class='mono'>scope</span> and <span class='mono'>limit</span>. A caller that wants "
                  "only live beliefs must filter in Python, reading both clocks itself. §5 argues why that is "
                  "the honest version; it is still a limitation for whoever builds the view"),
            ("3", "<b>Both writers remain unwired.</b> No route serves a "
                  "<span class='mono'>memory_item</span>, so an expiry is recordable and not readable over "
                  "HTTP. <span class='mono'>app.py</span>'s own gap prose has said so since 8.5 and still "
                  "says it"),
            ("4", "<b>F-18 is not closed, and its status word is not "
                  "<span class='mono'>OPEN</span>.</b> Gap 2 is what this batch delivers, and whether it "
                  "counts as <i>closed</i> is Q1 — a finding's status is the owner's to set, not the batch's "
                  "to assume. Gap 4 (the sufficiency meter) is open with no batch. D-054 recorded F-18 as "
                  "<span class='mono'>NARROWED</span> for exactly this reason, and nothing here changes that "
                  "word: three of four gaps delivered is still not four"),
            ("5", "<b>F-24 and F-26 are untouched</b>, and neither has a batch. <b>F-27</b> joins them"),
            ("6", "<b>F-27's inflated numbers stay in the tree.</b> "
                  "<span class='mono'>schema_migrations</span> records <span class='mono'>0003 &rarr; 4</span> "
                  "and <span class='mono'>0004 &rarr; 15</span>, and "
                  "<span class='mono'>test_the_runner_records_what_it_applied</span> pins both, with the "
                  "discrepancy stated in a helper's docstring rather than corrected. A reader of the API gets "
                  "a number that is <b>not</b> a count of what ran"),
            ("7", "<b>No <span class='mono'>0006</span> mirror file</b>, so the Postgres target and the "
                  "SQLite migrations express the column differently — inline in one DDL versus "
                  "<span class='mono'>ALTER</span> in the other. The fidelity gate compares the resulting "
                  "schemas and so catches a divergence in the column itself, but it <b>cannot</b> catch a "
                  "divergence in <i>when</i> the column arrives: a PostgreSQL deploy following "
                  "<span class='mono'>0002_memory.sql</span> gets it at creation and a SQLite deploy gets it "
                  "at <span class='mono'>0006</span>"),
            ("8", "<b>§13.7's eight limitations all still stand</b>, including limitation 3 — an orphan is "
                  "still writable at the store layer and still unscanned, published beside F-25's closure by "
                  "D-055's ruling 1"),
        ],
    )


def decision_table() -> str:
    """§12 — the four questions, each with exactly one marked recommendation."""
    return table(
        ["#", "Question", "Options"],
        [
            ("1", "Is Stage 8.7 approved, and is F-18's gap 2 closed?",
             "<b>(a) <span class='ok'>Recommend</span></b> — approve 8.7 as delivered, and close gap 2 "
             "<b>on the column and not on the TTL</b>, with limitation 1 published beside the closure. That is "
             "D-053's ruling 1 distinction for <span class='mono'>O-012</span>, re-drawn by D-055 for F-25, "
             "applied a <b>third</b> time: close on the defect the finding named and leave the limitation "
             "visible next to it. <b>F-18 itself stays <span class='mono'>NARROWED</span></b> &nbsp;·&nbsp; "
             "(b) approve but leave gap 2 open until something reads the column — stricter, and it would make "
             "gap 2 uncloseable by any batch that obeys ruling 4, since ruling 4 forbids the reader "
             "&nbsp;·&nbsp; (c) request changes"),
            ("2", "F-27 — the recorded statement count is not the applied one. Recorded, or given a batch?",
             "<b>(a) <span class='ok'>Recommend</span></b> — record F-27 "
             "<span class='mono'>OPEN</span> with <b>no batch</b>, and leave the inflated numbers pinned where "
             "they are. §6's measurement is why: fixing the property moves <b>no</b> checksum "
             "(<span class='mono'>sha256(sql)</span> alone), but the recorded value is a row written at apply "
             "time and never rewritten, so a fix splits production into <b>two populations</b> reporting "
             "different counts for the same version and checksum, with nothing able to tell which a row "
             "carries &nbsp;·&nbsp; (b) give it a batch now: change the property, accept the split, re-aim the "
             "pin to the honest counts &nbsp;·&nbsp; (c) give it a batch that also repairs the recorded rows — "
             "a data migration against <span class='mono'>schema_migrations</span> &nbsp;·&nbsp; (d) decline "
             "to record it: the number is bookkeeping and nobody acts on it"),
            ("3", "Which stage opens next, given the directive to run several at once?",
             "<b>(a) <span class='ok'>Recommend</span></b> — open <b>Stage 9</b> and settle <b>F-26</b> inside "
             "it as its first deliverable. F-26 was recorded as <i>&ldquo;the decision Stage 9 will have to "
             "make&rdquo;</i>, and Stage 9's candidate-thesis work is the first code that would write "
             "<span class='mono'>decision</span> or <span class='mono'>trade_intent</span> rows, so the seam "
             "question has to be answered <b>before</b> that writer exists rather than after — and answering "
             "it first means Stage 9's own writers get the four-parent treatment from the start instead of "
             "inheriting five unguarded keys &nbsp;·&nbsp; (b) open Stage 9 but defer F-26 again, writing "
             "against five unguarded foreign keys &nbsp;·&nbsp; (c) open Stage 10's sufficiency work first — "
             "F-18's gap 4 and F-24's band are both there and neither needs the trading path's seam decided "
             "&nbsp;·&nbsp; (d) name a different stage"),
            ("4", "Does the cadence change, given &ldquo;begin with multiple stages at once … we are way "
                  "behind on production&rdquo;?",
             "<b>(a) <span class='ok'>Recommend</span></b> — <b>batch the rulings, not the work</b>: run 8.8 "
             "and Stage 9's first deliverable in parallel and put <b>one combined board</b> covering both. The "
             "gate, the tamper proof and the register rows stay per-batch, so nothing becomes unattributable; "
             "what changes is that the owner rules on two batches at once instead of sequentially, and the work "
             "does not stop between them &nbsp;·&nbsp; (b) keep one batch per ruling and accept the throughput "
             "&nbsp;·&nbsp; (c) go further: authorise a run of batches against a standing scope — for example "
             "all of Stage 9 — with a single ruling at the end and an explicit list of what would still stop "
             "and ask &nbsp;·&nbsp; (d) something else"),
        ],
    )



def ruling_table() -> str:
    """§13 — what was ruled. Deliberately not the same helper as §12's decision table: §12 asserts the
    questions as they were put, and a table that rendered both would let a ruling silently rewrite a
    question. The two are separate functions asserting separate things."""
    return table(
        ["#", "Question as put", "Ruled", "What it changes"],
        [
            ("1", "Is Stage 8.7 approved, and is F-18&rsquo;s gap 2 closed?",
             "<b>Approved, recorded as D-056</b>, and <b>F-18&rsquo;s gap 2 "
             "<span class='ok'>CLOSED</span></b> — on the <b>column</b>, <i>not</i> on the TTL",
             "Both 8.7 rows in <span class='mono'>docs/07</span> become <span class='mono'>REVIEWED — "
             "APPROVED 2026-11-28</span>. §11&rsquo;s <b>limitation 1 stands as published beside the "
             "closure</b> rather than being retired by it: the column is inert, nothing in "
             "<span class='mono'>src/</span> reads it, and a row that should have stopped being served is "
             "still served. D-053&rsquo;s ruling 1 distinction for <span class='mono'>O-012</span>, re-drawn "
             "by D-055 for F-25, applied a <b>third</b> time. <b>F-18&rsquo;s status word stays "
             "<span class='mono'>NARROWED</span></b>, now with gaps 1, 2 and 3 closed and <b>gap 4 alone "
             "open</b> with no batch — three of four is still not four, and limitation 4 said so <i>before</i> "
             "the ruling rather than after it"),
            ("2", "F-27 — the recorded statement count is not the applied one. Recorded, or given a batch?",
             "<b>Recorded as F-27, <span class='no'>OPEN</span>, with no batch</b>",
             "The inflated numbers <b>stay pinned where they are</b>: "
             "<span class='mono'>schema_migrations</span> still records <span class='mono'>0003 &rarr; 4</span> "
             "and <span class='mono'>0004 &rarr; 15</span>, "
             "<span class='mono'>test_the_runner_records_what_it_applied</span> still asserts both, and "
             "<span class='mono'>applied_statements()</span> still carries the finding in its docstring so the "
             "next person to touch a migration reads it first. The reason the ruling gives is §6&rsquo;s "
             "measured one: a fix moves <b>no</b> checksum, but the value is a row written at apply time and "
             "never rewritten, so it would split production into <b>two populations</b> reporting different "
             "counts for the same version and checksum. F-27 is <b>not</b> an <span class='mono'>O-</span> "
             "row, so <span class='mono'>docs/00</span> still ends at <span class='mono'>O-014</span>. "
             "<b>The next finding id is F-28</b>"),
            ("3", "Which stage opens next, given the directive to run several at once?",
             "<b>Stage 9 opens, and F-26&rsquo;s seam is settled inside it as its first deliverable</b>",
             "Stage 9 is the candidate-thesis / intelligence-dossier stage "
             "(<span class='mono'>design/build_board52.py:73-87</span>), and its work is the <b>first code "
             "that would write <span class='mono'>decision</span> or "
             "<span class='mono'>trade_intent</span> rows</b> — so F-26&rsquo;s question (do those writers "
             "gain a store in the seam, or does the trading path document that its parents are checked "
             "upstream?) is answered <b>before</b> that writer exists rather than after. Answering it first "
             "also means Stage 9&rsquo;s own writers get the four-parent treatment from the start instead of "
             "inheriting five unguarded <span class='mono'>REFERENCES</span> clauses. <b>F-26 stays "
             "<span class='no'>OPEN</span> until that choice is made and recorded</b>: this ruling schedules "
             "the decision, it does not make it"),
            ("4", "Does the cadence change, given &ldquo;begin with multiple stages at once … we are way "
                  "behind on production&rdquo;?",
             "<b>Yes — batch the rulings, not the work</b>",
             "Two batches run concurrently and go to the owner on <b>one combined board</b>. What stays "
             "<b>per-batch</b>, so nothing becomes unattributable: the gate, the tamper proof, the "
             "<span class='mono'>docs/07</span> register rows and the <span class='mono'>docs/15</span> record "
             "section. What changes is that the owner rules on two batches at once instead of sequentially, and "
             "the work does not stop between them. <b>The first authorisation of concurrency in this "
             "project&rsquo;s history</b>, recorded as a change of cadence rather than a relaxation of "
             "evidence: every claim on a combined board is still measured in-tree, per batch"),
        ],
    )

def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())

    body = "".join([
        # -- 1 ------------------------------------------------------------------
        "<h3>1 &middot; What ruling 4 authorised, and what this batch therefore did not do"
        "<span class='tag'>D-055 r4 &middot; docs/15 &sect;14.0</span></h3>"
        "<p>D-055&rsquo;s ruling 4 ordered this batch and scoped it in one sentence: "
        "<b><span class='mono'>expires_at</span> on <span class='mono'>memory_item</span> only</b> &mdash; one "
        "nullable <span class='mono'>ADD COLUMN</span>, one writer argument, and <b>nothing acting on it</b>, "
        "because the gates that would consume an expiry are <span class='mono'>docs/10</span> &sect;3.2&rsquo;s "
        "V1&ndash;V3, which finalise at Stage 11. Seven files changed, <b>+623 / &minus;39</b>, and four of the "
        "seven are tests.</p>"
        + "<div class='card'>" + scope_table() + "</div>"
        + "<p>Three findings are untouched by this batch and none of them has a batch: <b>F-24</b> (a belief "
          "carries one confidence number where <span class='mono'>docs/10</span> &sect;3.1 asks for a band), "
          "<b>F-26</b> (five of nine declared foreign keys have no writer that could guard them, which is "
          "Stage 9&rsquo;s decision) and <b>F-18&rsquo;s gap 4</b> (the sufficiency meter, declined at D-054 "
          "and not offered again here). This batch adds one column and one finding of its own, &sect;6&rsquo;s "
          "<b>F-27</b>.</p>",

        # -- 2 ------------------------------------------------------------------
        "<h3>2 &middot; The migration: one statement, and the five things it deliberately is not"
        "<span class='tag'>docs/15 &sect;14.1</span></h3>"
        "<p><span class='mono'>0006_memory_expiry</span>, appended to <span class='mono'>MIGRATIONS</span> "
        "(5&nbsp;&rarr;&nbsp;<b>6</b>), with <span class='mono'>requires=\"memory_item\"</span>:</p>"
        + verbatim("the whole migration", "ALTER TABLE memory_item ADD COLUMN expires_at TEXT;")
        + verbatim("BLOCK A &mdash; captured: a database the runner booted, measured before and after 0006",
                   BLOCK_A)
        + "<div class='card'>" + migration_table() + "</div>"
        + "<p><b>0005&rsquo;s checksum being unchanged is the measurement that matters most in that table.</b> "
          "Editing the SQL of an applied migration moves its checksum and the runner refuses the result "
          "(<span class='mono'>migrations.py:191</span>), so a batch that had &ldquo;tidied up&rdquo; "
          "0005&rsquo;s comment while adding 0006 would have made <b>every existing database "
          "unbootable</b>. This one appends, and nothing before it moves.</p>"
        + "<div class='card'>" + not_table() + "</div>"
        + verbatim("BLOCK C &mdash; captured: an unstated expiry is NULL, and nothing defaults it", BLOCK_C)
        + "<p><b>The Postgres target.</b> <span class='mono'>backend/migrations/</span> stays at <b>two</b> "
          "files. <span class='mono'>0002_memory.sql</span> declares <span class='mono'>expires_at "
          "TIMESTAMPTZ</span> <b>inline</b> in its <span class='mono'>memory_item</span>, and its header now "
          "says <b>one</b> thing rather than two things are deliberately absent from it &mdash; the confidence "
          "band, F-24 &mdash; because the expiry is no longer absent. It is inline and not a new "
          "<span class='mono'>0006_memory.sql</span> because the fidelity gate compares the concatenated "
          "target to the live SQLite schema table-by-table and reads <span class='mono'>CREATE TABLE IF NOT "
          "EXISTS</span> only: an <span class='mono'>ALTER</span> in the target would be invisible to the gate "
          "while still shipping to a PostgreSQL deploy. BLOCK H below confirms no mirror file contains "
          "<span class='mono'>ALTER TABLE memory_item</span>.</p>",

        # -- 3 ------------------------------------------------------------------
        "<h3>3 &middot; Four clocks on one row, and why the fourth is not a correction of the other three"
        "<span class='tag'>docs/15 &sect;14.2</span></h3>"
        + verbatim("BLOCK B &mdash; captured: one belief, four clocks", BLOCK_B)
        + "<div class='card'>" + clock_table() + "</div>"
        + "<p>The third and fourth are the pair that needed a reason to exist separately, and on the captured "
          "row they <b>disagree on purpose</b>: the claim stops holding in the world on 4 December and the "
          "system keeps serving it to 3 January. That is not an inconsistency to be repaired &mdash; it is the "
          "ordinary case, where a belief&rsquo;s usefulness outlives its validity (a narrow basis that ended is "
          "still the right thing to cite when the basis returns) or, more often, ends before it (a stale quote "
          "nobody should be shown again even though it was true when taken). Collapsing the two would make one "
          "of those cases unrepresentable, and the <b>schema</b> would decide which.</p>"
        + "<p>This is why <span class='mono'>validity_of</span> is <b>unchanged</b>: it still returns exactly "
          "<b>five</b> keys &mdash; <span class='mono'>change_conditions</span>, "
          "<span class='mono'>evidence_ids</span>, <span class='mono'>valid_from</span>, "
          "<span class='mono'>valid_until</span>, <span class='mono'>validity_open_ended</span>. An expiry is "
          "not part of the validity interval, and folding it in would hand every reader of that helper a "
          "collapsed pair of clocks with nothing in the signature to show for it. Tamper site 8 adds the field "
          "and the suite catches it.</p>"
        + "<p><b>The receipt and the event.</b> <span class='mono'>MemoryReceipt</span> grows one field "
          "(<span class='mono'>expires_at: str | None</span>, between "
          "<span class='mono'>change_conditions</span> and <span class='mono'>evidence_ids</span>) to "
          "<b>17</b>, carried in both <span class='mono'>to_dict()</span> and "
          "<span class='mono'>from_event</span>. <span class='mono'>record_memory_item</span> grows one "
          "parameter to <b>15</b>. <span class='mono'>raise ValueError</span> stays at <b>17</b> and "
          "<span class='mono'>__all__</span> stays at <b>12</b>: this batch adds a column, not a rule.</p>",

        # -- 4 ------------------------------------------------------------------
        "<h3>4 &middot; What the writer refuses, and what it deliberately permits"
        "<span class='tag'>docs/15 &sect;14.3</span></h3>"
        + verbatim("BLOCK D &mdash; captured: seven expiries through one writer", BLOCK_D)
        + "<div class='card'>" + permit_table() + "</div>"
        + "<p><b>One refusal</b>, and it is the refusal <b>every</b> clock in this codebase gets: "
          "<span class='mono'>_aware</span> rejects a naive datetime <i>before</i> anything is compared with "
          "it, so the caller is told the value was naive rather than handed a bare "
          "<span class='mono'>TypeError</span> from an aware/naive comparison &mdash; an unclassified crash at "
          "a point where nothing names the condition, which is the failure mode F-4 was about. Nothing is "
          "written and nothing is audited: the test captures <span class='mono'>audit.length</span> "
          "<b>before</b> the call and asserts it unchanged, which is L-2&rsquo;s other half.</p>"
        + "<p><b>The six acceptances are the substance of this section</b>, because each one looks like a "
          "missing validation:</p>"
        + "<ul>"
          "<li><b>A past expiry is a date on a row, not a reason to reject it.</b> Refusing an expired belief "
          "would make the writer the arbiter of which beliefs should never have been recorded, and the caller "
          "would have to <b>lie about the date</b> to store a true one. 8.5 made the same call for the "
          "interval: a belief whose validity has already ended is dated, not deleted.</li>"
          "<li><b><span class='mono'>expires_at &lt; valid_from</span> is not an error.</b> A belief can be due "
          "for retirement before the world even starts to bear it out &mdash; a short-lived quote about a "
          "regime nobody has confirmed yet. Ordering the two would assert that serving-life contains "
          "validity-life, which nothing in <span class='mono'>docs/10</span> or "
          "<span class='mono'>docs/13</span> says.</li>"
          "<li><b>A decade after <span class='mono'>valid_until</span> is not an error either.</b> That is the "
          "common case from &sect;3.</li>"
          "<li><b><span class='mono'>expires_at == valid_until</span> is not refused, unlike the "
          "interval&rsquo;s own equality.</b> <span class='mono'>valid_until &lt;= valid_from</span> is refused "
          "<i>including</i> equality, because an interval of zero length says the claim never held and cannot "
          "be cited. Two clocks <b>coinciding on one axis</b> says nothing at all about either, so the same "
          "comparison in the other pair would be a rule borrowed from a place it does not apply.</li>"
          "</ul>"
        + "<p>A test parametrised over all four orderings pins them, with the reason for each in the parameter "
          "id, so a future reader who decides one of them <i>should</i> be refused finds the argument already "
          "written down instead of having to reconstruct why the code permits it.</p>",

        # -- 5 ------------------------------------------------------------------
        "<h3>5 &middot; Nothing acts on it: the scan that says so, and why it had to become an AST walk"
        "<span class='tag'>docs/15 &sect;14.4</span></h3>"
        + verbatim("BLOCK F &mdash; captured: an expired row is still served", BLOCK_F)
        + "<p>The ruling&rsquo;s second half is a <b>negative claim</b> &mdash; <i>stored, and acted on by "
          "nothing</i> &mdash; and a negative claim is worth exactly as much as the scan that would fail if it "
          "became false. There is one, over every <span class='mono'>.py</span> file in "
          "<span class='mono'>src/nexus</span>: it parses each file, collects string literals that look like "
          "SQL, and fails if any executable one mentions <span class='mono'>expires_at</span>. It also fails if "
          "it inspected fewer than <b>20</b> such literals, because a scan that sees nothing passes &mdash; the "
          "silent-pass shape 8.6 had to fix in its own gate.</p>"
        + "<p><b>Getting there took three versions, and the two that failed are the reason the assertion is "
          "written this way.</b> The first <b>grepped lines</b> for <span class='mono'>WHERE expires_at</span> "
          "and failed against a <i>docstring continuation line</i> in "
          "<span class='mono'>store/operational.py</span> &mdash; the sentence explaining why there is no such "
          "clause, which names it in order to refuse it. The second <b>parsed but did not strip SQL "
          "comments</b>, and failed against <span class='mono'>store/schema.py</span> twice: migrations "
          "<span class='mono'>0004</span> and <span class='mono'>0005</span>, because 0005&rsquo;s comment "
          "names <span class='mono'>expires_at</span> in its list of what it deliberately did not add. A "
          "<span class='mono'>--</span> line inside a SQL literal is prose exactly as much as a docstring is. "
          "<b>Prose that names a thing is not code that does it</b>, whether the prose is Python&rsquo;s or "
          "SQL&rsquo;s, and only a parse plus a comment strip can tell the two apart. That is F-23&rsquo;s "
          "lesson about a protocol growing a method, applied to a column growing a reader.</p>"
        + "<p>The scan is also checked not to be <b>blind</b>: <span class='mono'>execution/intent.py</span> "
          "genuinely contains both <span class='mono'>expires_at</span> and <span class='mono'>def "
          "is_expired</span> &mdash; the trading path&rsquo;s real reader, which is what an actual policy looks "
          "like in this codebase. And <span class='mono'>memory_items()</span> still binds exactly <b>three</b> "
          "parameters with base SQL <span class='mono'>SELECT * FROM memory_item</span> and no "
          "<span class='mono'>WHERE</span> at all, so a caller gets an expired row <b>and can see that it is "
          "expired</b>.</p>",

        # -- 6 ------------------------------------------------------------------
        "<h3>6 &middot; F-27 &mdash; the recorded statement count is not the applied one"
        "<span class='tag'>NEW &middot; docs/15 &sect;14.5</span></h3>"
        "<p>Found while writing 0006&rsquo;s test, <b>by measuring rather than reading</b>. "
        "<span class='mono'>Migration.statements</span> is:</p>"
        + verbatim("store/schema.py:57-58", 'return len([part for part in self.sql.split(";") if part.strip()])')
        + "<p>It does not strip <span class='mono'>--</span> comment lines, and it does not know that a trigger "
          "body is <b>one</b> statement with semicolons inside it. So a semicolon in a migration&rsquo;s own "
          "prose is counted as a statement:</p>"
        + verbatim("BLOCK E &mdash; captured: all six migrations, recorded against applied", BLOCK_E)
        + "<div class='card'>" + f27_table() + "</div>"
        + "<p><b>Nothing misbehaves.</b> The number is bookkeeping, stored in "
          "<span class='mono'>schema_migrations.statements</span> and served by the API. But "
          "<span class='mono'>migrations.py:11</span> describes that row as carrying &ldquo;the version, its "
          "checksum and its statement count, so <i>when did the schema change</i> is answerable from the "
          "chain&rdquo; &mdash; and a reader who takes <span class='mono'>statements</span> as &ldquo;how many "
          "statements ran&rdquo; is <b>wrong by two on 0003 and by two on 0004</b>. The assertion message on "
          "0004 in <span class='mono'>test_the_runner_records_what_it_applied</span> reads <i>&ldquo;0004 "
          "rebuilds two tables and creates one&rdquo;</i>, which is the inflated reading written down as though "
          "it were a count of statements.</p>"
        + "<p><b>Why this is recorded rather than fixed inside 8.7</b>, and the reason is measured, not "
          "asserted:</p>"
        + "<ul>"
          "<li>Fixing the property does <b>not</b> move any checksum. <span class='mono'>checksum</span> is "
          "<span class='mono'>sha256(self.sql)</span> &mdash; the statement count is not an input &mdash; so "
          "the forward-only refusal at <span class='mono'>migrations.py:191</span> would not fire and no "
          "existing database would become unbootable.</li>"
          "<li>But the recorded number is a <b>row written at apply time and never rewritten</b>. A fix "
          "therefore produces <b>two populations that nothing can tell apart</b>: a database booted before the "
          "fix says <span class='mono'>0004 &rarr; 15</span>, one booted after says <span class='mono'>0004 "
          "&rarr; 13</span>, for the identical version and checksum. Correcting history is exactly what a "
          "forward-only migration system refuses to do, and the two readings would coexist in production with "
          "no way to know which a given row carries.</li>"
          "<li>So the honest options are a data migration against "
          "<span class='mono'>schema_migrations</span> (which the forward-only rule was built to avoid), or "
          "accepting the split and documenting it, or leaving the number alone and <b>stopping calling it a "
          "count of what was applied</b>. That is a decision, not a one-line patch, and D-055 scoped this batch "
          "to <span class='mono'>expires_at</span>.</li>"
          "</ul>"
        + "<p><b>What 8.7 did instead, in two parts.</b> 0006&rsquo;s comment carries <b>no</b> semicolons "
          "&mdash; deliberately, and that is a constraint on the comment&rsquo;s <i>punctuation</i> rather than "
          "on its content, which is itself an argument for recording F-27 rather than working around it "
          "silently forever. And <span class='mono'>test_schema_fidelity.py</span> gains one helper, "
          "<span class='mono'>applied_statements()</span>, which strips comment lines before splitting and "
          "carries this whole finding in its docstring, so the two tests that need an honest count get one and "
          "the inflated values stay pinned where they were pinned &mdash; with the discrepancy stated next to "
          "them instead of hidden. <b>F-27 is not an <span class='mono'>O-</span> row</b>: D-054 established "
          "that scheduling a batch is not opening an obligation row and D-055 re-applied that to F-26, so "
          "<span class='mono'>docs/00</span> still ends at <span class='mono'>O-014</span>. <b>The next finding "
          "id is F-28.</b></p>",

        # -- 7 ------------------------------------------------------------------
        "<h3>7 &middot; The replay: the fourth clock survives a real gap"
        "<span class='tag'>L-2 &middot; docs/15 &sect;14.2</span></h3>"
        + verbatim("BLOCK G &mdash; captured: write, delete both tables, wait 1.05 s, re-project", BLOCK_G)
        + "<p>The value rides <b>inside</b> the audited event, which is law L-2 and not a stylistic choice. A "
          "timestamp held outside the event is restamped by the replay, which is the defect "
          "<span class='mono'>created_at</span> was moved inside the event to avoid in an earlier batch. The "
          "fourth clock went inside on the same reasoning, and the assertion is that the <b>whole row</b> is "
          "identical &mdash; not merely the two clocks quoted &mdash; so a replay that quietly dropped "
          "<span class='mono'>payload</span> or <span class='mono'>confidence</span> would fail here too. The "
          "1.05&nbsp;s wait is there so a restamped clock could not match by rounding.</p>",

        # -- 8 ------------------------------------------------------------------
        "<h3>8 &middot; Proof the gate is load-bearing: thirteen tampered sites, thirteen caught"
        "<span class='tag'>docs/15 &sect;14.6</span></h3>"
        "<p>Each site backs up one source file, applies one string replacement, <b>asserts the file actually "
        "changed</b> &mdash; a stale anchor leaves the tree untouched and reports a silent pass that means "
        "nothing &mdash; re-runs the four test files that exercise the column, and restores from the backup. "
        "Restoration is verified by <b>SHA-256 over all three touched files</b> and the suite is re-run at the "
        "end and required to be back at its baseline.</p>"
        + verbatim("captured: the tamper run, all thirteen sites", BLOCK_TAMPER)
        + "<div class='card'>" + tamper_table() + "</div>"
        + "<p><b>Thirteen sites, thirteen caught, zero silent passes &mdash; but only on the second run.</b> "
          "The first run found <b>one</b> silent pass, at site 5: dropping "
          "<span class='mono'>requires=\"memory_item\"</span> from 0006 left all <b>1,427</b> tests green.</p>"
        + "<p>The reason is structural, and it is the same shape as the silent pass 8.6 found. "
          "<span class='mono'>requires</span> only changes behaviour on a database where the required table is "
          "<b>absent</b>, and <b>no test put the runner on one</b>: every test boots a store, and "
          "<span class='mono'>0002</span> creates <span class='mono'>memory_item</span> before "
          "<span class='mono'>0006</span> could ever need it. The dependency was declared and nothing in the "
          "repository could observe it.</p>"
        + "<p><span class='mono'>test_migrations.py</span> gains the missing branch &mdash; "
          "<span class='mono'>test_a_memory_migration_defers_when_memory_item_is_absent</span> "
          "(15&nbsp;&rarr;&nbsp;<b>16</b> tests). It boots a durable store, drops "
          "<span class='mono'>memory_item</span>, deletes 0006&rsquo;s row from "
          "<span class='mono'>schema_migrations</span> so the version is pending again while 0001&ndash;0005 "
          "stay applied and the sequence keeps <b>no hole</b>, and reopens. The runner must <b>skip and "
          "report</b> &mdash; F-20&rsquo;s rule, that a deferral and a bypass look identical in "
          "<span class='mono'>schema_migrations</span> unless the skip is remembered. The same test then builds "
          "the <b>mirror</b>: an undeclared <span class='mono'>Migration</span> whose SQL is "
          "<span class='mono'>ALTER TABLE memory_item ADD COLUMN probe TEXT</span> against a database with no "
          "such table, which must raise <span class='mono'>MigrationError</span>. <b>Deferred on one side and "
          "fatal on the other</b> is what makes the declared dependency observable at all, and site 5 now fails "
          "exactly <b>1</b> test, by name.</p>"
        + "<p>Sites 7 and 10 both fail <b>46</b>, and that is not a coincidence: the event and the receipt are "
          "the two ends of one chain, so cutting either breaks every replay test and every assertion that reads "
          "the column back. Sites 9 and 12 fail <b>small</b>, which is the useful signal &mdash; an "
          "over-reaching refusal and an invented default each break only the tests written specifically about "
          "<b>permissions</b>, so the four ordering tests and the <span class='mono'>NULL</span> test are what "
          "make those two tampering attempts visible at all.</p>",

        # -- 9 ------------------------------------------------------------------
        "<h3>9 &middot; The gate"
        "<span class='tag'>docs/15 &sect;14.7</span></h3>"
        + verbatim("captured: the four commands, in full", BLOCK_GATE)
        + "<div class='card'>" + gate_table() + "</div>"
        + "<p><b>1,428 passed / 2 skipped / 0 failed</b>, up <b>20</b> from 8.6&rsquo;s 1,408. The two skips "
          "are named, because a skip is not a pass: "
          "<span class='mono'>test_live_endpoints.py:86</span> (live venue verification needs network egress; "
          "<b>nothing is verified by skipping it</b>) and <span class='mono'>test_archive_bars.py:117</span> "
          "(<span class='mono'>7m</span> is not a modelled interval). Both are inherited. "
          "<span class='mono'>tests</span> stays at <b>31</b> files &mdash; D-055&rsquo;s ruling 2 kept "
          "8.6&rsquo;s gate where it was rather than paying for a 32nd, and this batch adds no file either. "
          "<span class='mono'>src</span> stays at <b>62</b> files / <b>16,347</b> lines (+90); "
          "<span class='mono'>tests</span> is <b>31</b> files / <b>19,857</b> lines (+475).</p>",

        # -- 10 -----------------------------------------------------------------
        "<h3>10 &middot; What this batch did not touch, counted rather than claimed"
        "<span class='tag'>docs/15 &sect;14.7</span></h3>"
        + verbatim("BLOCK H &mdash; captured: the diff, and the files that did not move", BLOCK_H)
        + "<p>Four source-side files, of which <span class='mono'>operational.py</span>&rsquo;s 28 lines are "
          "the <span class='mono'>INSERT OR REPLACE</span> (14&nbsp;&rarr;&nbsp;<b>15</b> columns, "
          "<b>15</b> placeholders &mdash; the arity asserted by walking the AST for the literal rather than by "
          "grepping a guess at its formatting, because the statement is "
          "<span class='mono'>INSERT OR REPLACE</span> and a grep for <span class='mono'>INSERT INTO "
          "memory_item</span> finds nothing) plus two docstrings. <b>No route, no adapter, no archive, no venue "
          "code.</b> No adapter changed, so no live venue run speaks to this batch &mdash; though every push "
          "still triggers one.</p>",

        # -- 11 -----------------------------------------------------------------
        "<h3>11 &middot; Limitations of this batch"
        "<span class='tag'>docs/15 &sect;14.8</span></h3>"
        + "<div class='card'>" + limitation_table() + "</div>",

        # -- 12 -----------------------------------------------------------------
        "<h3>12 &middot; Decision requested"
        "<span class='tag'>docs/15 &sect;14.9</span></h3>"
        "<p>Four questions. Each has <b>exactly one</b> marked recommendation, and &sect;11&rsquo;s limitations "
        "are published beside them rather than being offered as arguments for any of them.</p>"
        + "<div class='card'>" + decision_table() + "</div>"
        + "<p>Whatever is ruled, <b>three things do not change without a ruling of their own</b>: no expiry "
          "<b>policy</b> before Stage 11&rsquo;s V1&ndash;V3 gates; no confidence <b>band</b> (F-24) without "
          "its own scope; and no wiring of either intelligence writer to a route, declined three times and not "
          "offered here.</p>",

        # -- 13 -----------------------------------------------------------------
        "<h3>13 &middot; D-056 &mdash; the four rulings"
        "<span class='tag'>2026-11-28 &middot; docs/15 &sect;14.10</span></h3>"
        "<p>All four questions in &sect;12 were answered <b><span class='ok'>Recommend</span></b>, each against "
        "exactly one marked recommendation, and are recorded as <b>D-056</b>. &sect;12 is left as it was put; "
        "this section is the ruling. <b>No code changed</b> &mdash; <span class='mono'>git diff 2267eb4 HEAD -- "
        "backend/</span> is empty &mdash; and the gate re-ran anyway, because this section quotes what it "
        "produces:</p>"
        + verbatim("captured after the ruling, on an unchanged backend tree", BLOCK_GATE)
        + "<div class='card'>" + ruling_table() + "</div>"
        + "<p><b>What ruling 4 does not settle, stated because it is the one gap the ruling leaves.</b> "
          "Q4&rsquo;s option (a) named &ldquo;8.8&rdquo; as the batch that runs beside Stage 9&rsquo;s first "
          "deliverable, and <b>no document in this repository defines 8.8&rsquo;s scope</b> &mdash; the option "
          "text carried the label without the content, and this record will not retro-fit a scope to a ruling "
          "that did not state one. What <i>is</i> derivable from in-repo pointers, and is therefore what the "
          "next board <b>puts</b> rather than assumes: <b>F-24</b> is the one open finding whose subject is "
          "Stage 8&rsquo;s own tables (a belief carries one confidence number where "
          "<span class='mono'>docs/10</span> &sect;3.1 asks for it <i>&ldquo;as a band&rdquo;</i> and D-035 "
          "approved <i>&ldquo;beliefs as bands&rdquo;</i>); "
          "<span class='mono'>migrations/0002_memory.sql</span>&rsquo;s header says exactly <b>one</b> thing is "
          "deliberately absent from it <i>&ldquo;because no batch has ruled on it&rdquo;</i>, and since 8.7 that "
          "one thing is the confidence band; and F-18&rsquo;s remaining gap 4 is the sufficiency meter, which "
          "<span class='mono'>docs/12</span> &sect;1.3 places at <b>stage 10</b> and not in Stage 8. So "
          "<b>8.8 = F-24</b> is the derivation &mdash; <b>and the shape of a band still has no ruling behind "
          "it</b> (&sect;12.8 recorded that when it opened the finding), so two more columns, one band column, "
          "or something else is a question for the owner and not a decision a batch may take silently.</p>"
        + "<p><b>What this ruling does not do</b>, stated so nobody has to infer it. It does <b>not</b> "
          "authorise an expiry <b>policy</b>: no filter, no <span class='mono'>is_expired()</span>-style reader "
          "on <span class='mono'>memory_item</span>, nothing acting on the column until "
          "<span class='mono'>docs/10</span> &sect;3.2&rsquo;s V1&ndash;V3 gates finalise at Stage 11. It does "
          "<b>not</b> authorise a confidence <b>band</b> &mdash; ruling 4 schedules two batches, and "
          "F-24&rsquo;s shape is a question on the next board rather than a consequence of this one. It does "
          "<b>not</b> wire either intelligence writer to a route, declined three times and not offered in "
          "&sect;12. It does <b>not</b> retire any of &sect;11&rsquo;s eight limitations, including limitation 1 "
          "&mdash; the one gap 2&rsquo;s closure could most easily have been read to retire. It does <b>not</b> "
          "make F-26&rsquo;s seam choice, which is Stage 9&rsquo;s first deliverable and is still open. It does "
          "<b>not</b> close F-24, F-26 or F-27, and does <b>not</b> close F-18. And it does <b>not</b> "
          "enumerate stages beyond 11: <span class='mono'>docs/12</span> &sect;1.3 names knowledge sufficiency "
          "as stage 10 and the three verification gates as stage 11, "
          "<span class='mono'>design/build_board52.py:73-87</span> defines 9, 10 and 11, and <b>no document in "
          "this repository names stages 12 to 23</b>, so none is invented here.</p>"
        + "<p><b>Next.</b> Two batches concurrently, on one combined board, per ruling 4: <b>8.8 = "
          "F-24&rsquo;s confidence band</b>, with the band&rsquo;s <i>shape</i> put as a question rather than "
          "assumed; and <b>Stage 9&rsquo;s first deliverable = F-26&rsquo;s seam</b>, settled before any "
          "Stage 9 writer is written. The next finding id is <b>F-28</b>.</p>",
    ])

    html_out = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Nexus-AI &middot; Stage 8.7 Intelligence Memory &mdash; The Fourth Clock</title>"
        "<style>" + tokens + "\n" + fonts_css() + "\n" + CSS + "</style></head><body><div class='wrap'>"
        "<div class=\"lede\">Nexus-AI &middot; Stage 8 of 23 &middot; sub-deliverable 8.7 &middot; "
        "ordered by D-055&rsquo;s ruling 4 as <b><span class=\"mono\">expires_at</span> on "
        "<span class=\"mono\">memory_item</span> only</b> &middot; "
        "<b>APPROVED 2026-11-28 (D-056)</b> &middot; <b>F-18&rsquo;S GAP 2 CLOSED</b> on the column, not on the TTL &middot; <b>F-27 OPEN</b>, found here, recorded with no batch "
        "&middot; next finding id <b>F-28</b> &middot; F-18 stays <b>NARROWED</b>, gap 4 open &middot; "
        "F-24 and F-26 untouched &middot; next: <b>Stage 9</b>, with F-26&rsquo;s seam settled inside it "
        "(&sect;12 Q3)</div>"
        "<h1 style=\"font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);"
        "margin:6px 0 0\">The fourth clock &mdash; stored faithfully, and read by nothing</h1>"
        "<div class=\"ribbon\">This batch changes <b>seven files</b>, <b>+623 / &minus;39</b>, and four of the "
        "seven are tests. <span class=\"mono\">store/schema.py</span> +55 for migration "
        "<span class=\"mono\">0006_memory_expiry</span> &mdash; <b>one statement</b>, "
        "<span class=\"mono\">MIGRATIONS</span> 5&nbsp;&rarr;&nbsp;<b>6</b>, and "
        "<b>0005&rsquo;s checksum unchanged</b>, which is the measurement that says no applied migration was "
        "edited. <span class=\"mono\">intelligence/memory.py</span> 497&nbsp;&rarr;&nbsp;<b>498</b>: one "
        "parameter (<b>15</b>), one receipt field (<b>17</b>), and <span class=\"mono\">raise ValueError</span> "
        "still <b>17</b> with <span class=\"mono\">__all__</span> still <b>12</b> &mdash; a column, not a rule. "
        "<span class=\"mono\">memory_item</span> 14&nbsp;&rarr;&nbsp;<b>15</b> columns; "
        "<span class=\"mono\">evidence_ref</span> stays <b>12</b>; <b>no index built</b>; "
        "<span class=\"mono\">api/</span>, <span class=\"mono\">evidence.py</span> and "
        "<span class=\"mono\">dossier.py</span> untouched; <span class=\"mono\">app.py</span> does not contain "
        "the string <span class=\"mono\">expires_at</span>. Gate <b>1,428 passed / 2 skipped / 0 failed</b> "
        "(+20), mypy strict clean on <b>62</b>, ruff and format clean on <b>93</b>. <b>Thirteen tampered sites, "
        "thirteen caught, zero silent</b> &mdash; after <b>one</b> was found: dropping "
        "<span class=\"mono\">requires=\"memory_item\"</span> left all 1,427 green because no test put the "
        "runner on a database where the table was absent, so the dependency was declared and unobservable. "
        "<b>Seven expiries through the writer: one refused</b> (a naive datetime, by the pre-existing "
        "<span class=\"mono\">_aware</span>) <b>and six accepted</b> &mdash; 400 days past, before "
        "<span class=\"mono\">valid_from</span>, equal to both interval ends, a decade after, and unstated "
        "&mdash; because <span class=\"mono\">valid_until</span> bounds the claim <b>in the world</b> while an "
        "expiry bounds <b>this system&rsquo;s serving</b> of it, and a refusal built on ordering them would "
        "assert a relationship the schema deliberately does not have. <b>F-27 found by measuring all six "
        "migrations</b>: <span class=\"mono\">Migration.statements</span> splits on "
        "<span class=\"mono\">\";\"</span> without stripping comment lines and without knowing a trigger body is "
        "one statement, so <span class=\"mono\">0003</span> records <b>4</b> and applies <b>2</b> and "
        "<span class=\"mono\">0004</span> records <b>15</b> and applies <b>13</b> &mdash; recorded rather than "
        "fixed, because the count is a row written at apply time and never rewritten, so a fix would split "
        "production into two populations reporting different numbers for the same version and checksum.</div>"
        + body
        + "<footer><b>Stage 8.7 &mdash; the fourth clock.</b> <b>APPROVED 2026-11-28 (D-056)</b>: all four "
          "questions in &sect;12 answered <b>Recommend</b>, the ruling in &sect;13 &middot; <b>F-18&rsquo;s gap 2 CLOSED</b> on the column and not on the TTL, with limitation 1 published "
          "beside the closure, and F-18&rsquo;s word still <b>NARROWED</b> &middot; <b>F-27 OPEN</b> "
          "with no batch &middot; <b>Stage 9 opens</b> with F-26&rsquo;s seam first, and <b>the cadence "
          "changes</b> to two batches on one combined board &middot; migration <span class=\"mono\">0006_memory_expiry</span>, <b>one</b> statement "
          "<span class=\"mono\">ALTER TABLE memory_item ADD COLUMN expires_at TEXT</span>, checksum "
          "<span class=\"mono\">f54eecd2c3f6c2c6&hellip;</span>, "
          "<span class=\"mono\">requires=\"memory_item\"</span> &middot; <b>0005&rsquo;s checksum unchanged</b> "
          "at <span class=\"mono\">4520e5b5e259eb4c&hellip;</span>, so no applied migration was edited and no "
          "existing database becomes unbootable &middot; <span class=\"mono\">memory_item</span> "
          "<b>15</b> columns, <span class=\"mono\">evidence_ref</span> <b>12</b>, <b>no new index</b>, "
          "<span class=\"mono\">notnull=0</span>, <span class=\"mono\">default=None</span>, and a raw "
          "<span class=\"mono\">INSERT</span> naming no expiry stores <span class=\"mono\">NULL</span> &middot; "
          "four clocks on one row, with <span class=\"mono\">valid_until</span> and "
          "<span class=\"mono\">expires_at</span> <b>disagreeing on purpose</b> on the captured row &middot; "
          "<span class=\"mono\">validity_of</span> <b>unchanged</b> at five keys, because an expiry is not part "
          "of the validity interval &middot; <span class=\"mono\">record_memory_item</span> <b>15</b> params, "
          "<span class=\"mono\">MemoryReceipt</span> <b>17</b> fields, "
          "<span class=\"mono\">raise ValueError</span> <b>17</b>, <span class=\"mono\">__all__</span> "
          "<b>12</b> &middot; the value rides <b>inside</b> the audited event, so a replay after "
          "<span class=\"mono\">DELETE FROM memory_item</span> + <span class=\"mono\">op_projection</span> + "
          "1.05&nbsp;s reproduces the <b>whole row</b> byte-identically &middot; <b>seven</b> expiries, "
          "<b>one</b> refused and <b>six</b> accepted, with no comparison against any clock on the other axis "
          "&middot; <b>nothing acts on it</b>: no filter, no reader, no route &mdash; an expired row is still "
          "served (<b>2 of 2</b>), <span class=\"mono\">memory_items()</span> still binds <b>three</b> "
          "parameters, and the scan that says so is an <b>AST walk with SQL comments stripped</b> after two "
          "versions failed against prose that names the clause it refuses &middot; <b>F-27 OPEN, no batch</b>, "
          "found by measuring all six migrations; <b>not</b> an <span class=\"mono\">O-</span> row, so "
          "<span class=\"mono\">docs/00</span> still ends at <span class=\"mono\">O-014</span>, and <b>the next "
          "finding id is F-28</b> &middot; <b>thirteen</b> tampered sites, <b>thirteen</b> caught, <b>zero</b> "
          "silent after <b>one</b> was found and a <b>missing test</b> was written rather than a weak assertion "
          "strengthened &middot; the harness itself was corrected twice: a "
          "<span class=\"mono\">pytest -q</span> that suppressed the summary line so every site looked silent, "
          "and a restore check that compared each file with itself &middot; gate <b>1,428 passed / 2 skipped / "
          "0 failed</b> (+20: memory_writer 77&nbsp;&rarr;&nbsp;88, schema_fidelity 41&nbsp;&rarr;&nbsp;49, "
          "migrations 15&nbsp;&rarr;&nbsp;16; the other four files unchanged), mypy strict clean on <b>62</b>, "
          "ruff and format clean on <b>93</b> &middot; <span class=\"mono\">src</span> <b>62</b> files and "
          "<b>16,347</b> lines, <span class=\"mono\">tests</span> <b>31</b> and <b>19,857</b> &middot; "
          "<b>eight</b> limitations published in full, including that the column is <b>inert by design</b> and "
          "that 8.7 delivered the <b>column</b> &ldquo;expiring TTLs&rdquo; needs, not the TTL &middot; F-18 "
          "stays <span class=\"mono\">NARROWED</span> with gap 4 open and no batch, F-24 and F-26 untouched "
          "&middot; no adapter changed, so no live run speaks to this batch &middot; next: <b>Stage 9</b>, "
          "settling <b>F-26</b>&rsquo;s seam inside it as its first deliverable, and Q4 asks whether the "
          "cadence changes so two batches ship against one combined board</footer>"
          "</div></body></html>"
    )

    out = HERE / "stage8-7-the-fourth-clock.html"
    out.write_text(html_out)
    return out


if __name__ == "__main__":
    path = main()
    print(f"wrote {path} ({path.stat().st_size // 1024} KB)")
