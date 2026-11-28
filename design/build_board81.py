"""Stage 8.1 board: intelligence memory — what exists, what is schema-only, and what a writer must satisfy.

Research only, authorised by D-049: no production code changed, so no new CI surface and the gate is
unchanged from Stage 7's closure. Every claim here was produced by a named command, and the ones that
could be executed were executed — the transcripts in §4 and §6 are reproduced verbatim from
`backend/.venv/bin/python` runs against the real applied DDL, not written from memory.

Where this batch corrected the record it had just written, the correction is shown: Stage 8's invented
title (§0), and Stage 7's "five consecutive zeros" (§7), which run 29 falsified.

Run:  backend/.venv/bin/python design/build_board81.py
"""

from __future__ import annotations

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


# --------------------------------------------------------------------- 1 · what the record does fix
def chain_table() -> str:
    return table(
        ["Source", "What it fixes"],
        [
            ("<span class='cite'>docs/13</span> §2.4, §2.5",
             "the intelligence-memory tables <span class='mono'>dossier</span>, "
             "<span class='mono'>evidence_ref</span>, <span class='mono'>memory_item</span> are "
             "<b>schema only</b> &mdash; &ldquo;writers arrive with stages 8&ndash;10&rdquo;"),
            ("<span class='cite'>docs/12</span> §1.3 (P-2)",
             "the decision chain: candidate with ABSTAIN default &rarr; <b>knowledge sufficiency "
             "(stage 10, planned)</b> &rarr; <b>three verification gates (stage 11, planned)</b> &rarr; "
             "immutable digest-bound intent &rarr; <span class='mono'>LiveAuthority</span> &rarr; "
             "deterministic sizing &rarr; environment routing"),
            ("<span class='cite'>build_board52.py:73</span>",
             "&ldquo;intelligence dossier (<b>stage 9</b>) &middot; evidence set + uncertainty &middot; "
             "ABSTAIN is the default record&rdquo;"),
            ("<span class='cite'>docs/03</span> §7, §8 &middot; <span class='cite'>docs/10</span> §3.1",
             "the Intelligence Centre screen and the evidence graph it must serve &mdash; "
             "<b>approved at Stage 3.3, D-035</b>"),
        ],
    )


# -------------------------------------------------------------------------------- 2 · the inventory
def exists_table() -> str:
    return table(
        ["Piece", "Where", "State"],
        [
            ("<span class='mono'>DecisionRecord</span>, <span class='mono'>DecisionVerb</span> "
             "(ACCEPT/REJECT/WAIT/REDUCE/EXIT/ESCALATE/ABSTAIN), <span class='mono'>DecisionState</span>",
             "<span class='cite'>domain/decision.py:17-67</span>",
             "<span class='ok'><b>Built</b></span> &mdash; matches the "
             "<span class='cite'>docs/03</span> §7 vocabulary exactly"),
            ("Persistence for decisions",
             "<span class='cite'>store/operational.py:366-414</span>",
             "<span class='ok'><b>Built</b></span> &mdash; audit-first, "
             "<span class='mono'>INSERT OR REPLACE</span>"),
            ("The three memory tables",
             "<span class='cite'>store/schema.py:267-313</span> (applied) &middot; "
             "<span class='cite'>migrations/0002_memory.sql</span> (target)",
             "<span class='warn'><b>Schema only</b></span> &mdash; no writer, as "
             "<span class='cite'>docs/13</span> records"),
            ("<span class='mono'>counts()</span> includes all three",
             "<span class='cite'>store/operational.py:931-951</span>",
             "<span class='ok'><b>Built</b></span> &mdash; observable today at "
             "<span class='mono'>/v1/status &rarr; persistence.counts</span>, all zero"),
            ("Audit hash chain, append-only triggers, <span class='mono'>assert_no_secrets</span>",
             "<span class='cite'>audit/chain.py</span>, <span class='cite'>audit/log.py</span>, "
             "<span class='cite'>schema.py:316-333</span>",
             "<span class='ok'><b>Built</b></span>"),
            ("Projection bookkeeping",
             "<span class='mono'>op_projection</span>, <span class='mono'>mark_projected</span>, "
             "<span class='mono'>projected_refs</span>",
             "<span class='ok'><b>Built</b></span> &mdash; the store is already modelled as a projection "
             "of the audit chain"),
            ("Write-ahead replay", "<span class='cite'>store/writeahead.py:75-87</span>",
             "<span class='ok'><b>Built</b></span> for 7 event types, including "
             "<span class='mono'>instrument.registered</span>"),
            ("<span class='mono'>LiveAuthority</span>, sizing, routing",
             "<span class='cite'>risk/authority.py</span>, <span class='cite'>risk/engine.py</span>",
             "<span class='ok'><b>Built</b></span> &mdash; steps 5&ndash;7 of the P-2 chain"),
        ],
    )


def absent_table() -> str:
    return table(
        ["Absent", "How it was established"],
        [
            ("<b>Any candidate or thesis generation.</b> No <span class='mono'>intelligence</span>, "
             "<span class='mono'>research</span> or <span class='mono'>memory</span> package exists",
             "<span class='mono'>ls src/nexus/</span> &rarr; 15 packages: api, archive, audit, core, "
             "data, domain, events, execution, ingestion, instruments, observability, risk, secrets, "
             "store"),
            ("<b>Any construction of <span class='mono'>DecisionRecord</span> in production code</b>",
             "<span class='mono'>grep -rn \"DecisionRecord(\" src/</span> &rarr; <b>zero hits</b>; the "
             "only constructions are in two test files"),
            ("<b>Any real value in <span class='mono'>evidence_refs</span></b>",
             "<span class='mono'>grep -rn \"evidence_refs=\" src/ tests/</span> &rarr; one hit, "
             "<span class='cite'>test_store_persistence.py:71</span>, with the literals "
             "<span class='mono'>(\"EV-1\", \"EV-2\")</span>"),
            ("<b>Any &ldquo;evidence graph&rdquo;</b>",
             "one hit in <span class='mono'>src/</span>, and it is the <i>comment</i> on "
             "<span class='cite'>decision.py:62</span>: &ldquo;source ids from the evidence graph&rdquo;. "
             "There is no graph"),
            ("<b>Any route serving decisions, dossiers, memory or evidence</b>",
             "The 11 routes are all operational: <span class='mono'>/healthz</span>, "
             "<span class='mono'>/metrics</span>, <span class='mono'>/readyz</span>, "
             "<span class='mono'>/v1/audit/verify</span>, <span class='mono'>/v1/data/coverage</span>, "
             "<span class='mono'>/v1/halt</span>, <span class='mono'>/v1/halt/release</span>, "
             "<span class='mono'>/v1/instruments</span>, "
             "<span class='mono'>/v1/instruments/coverage</span>, "
             "<span class='mono'>/v1/instruments/{id}/session</span>, "
             "<span class='mono'>/v1/status</span>"),
            ("<b>Any emitter of <span class='mono'>instrument.registered</span></b>",
             "<span class='cite'>writeahead.py:81</span> can <i>replay</i> it; nothing in "
             "<span class='mono'>src/</span> ever produces it"),
        ],
    )


# ------------------------------------------------------------- 4 · F-15, the mirror that is not one
def divergence_table() -> str:
    return table(
        ["Table", "Column", "Postgres target", "Applied SQLite", "Consequence"],
        [
            ("<span class='mono'>dossier</span>", "<span class='mono'>instrument_id</span>",
             "<span class='mono'>TEXT REFERENCES instrument (instrument_id)</span>",
             "<span class='mono'>TEXT</span> &mdash; <b class='no'>no REFERENCES at all</b>",
             "the link from a dossier to the instrument it is about is <b>undeclared</b>, so it cannot be "
             "enforced even in principle"),
            ("<span class='mono'>dossier</span>", "<span class='mono'>created_at</span>",
             "<span class='mono'>TIMESTAMPTZ NOT NULL DEFAULT now()</span>",
             "<span class='mono'>TEXT NOT NULL</span>",
             "an insert omitting it fails in SQLite and succeeds in Postgres"),
            ("<span class='mono'>dossier</span>", "<span class='mono'>updated_at</span>",
             "<span class='mono'>TIMESTAMPTZ NOT NULL DEFAULT now()</span>",
             "<span class='mono'>TEXT NOT NULL</span>", "same"),
            ("<span class='mono'>evidence_ref</span>", "<span class='mono'>retrieved_at</span>",
             "<span class='mono'>TIMESTAMPTZ NOT NULL DEFAULT now()</span>",
             "<span class='mono'>TEXT NOT NULL</span>",
             "same &mdash; and this is the column <b>F-14</b> needs"),
            ("<span class='mono'>memory_item</span>", "<span class='mono'>created_at</span>",
             "<span class='mono'>TIMESTAMPTZ NOT NULL DEFAULT now()</span>",
             "<span class='mono'>TEXT NOT NULL</span>", "same"),
            ("<span class='mono'>memory_item</span>", "<span class='mono'>confidence</span>",
             "<span class='mono'>NUMERIC(6, 5)</span>",
             "<span class='mono'>TEXT</span> &mdash; <b class='no'>unconstrained</b>",
             "the file's own law says &ldquo;Confidence uses NUMERIC, never FLOAT&rdquo;; the applied "
             "schema uses <b>neither</b>"),
        ],
    )


def design_gap_table() -> str:
    return table(
        ["Required by", "Requirement", "What the schema has"],
        [
            ("<span class='cite'>docs/03</span> §7 &middot; <span class='cite'>docs/10</span> §3.1",
             "beliefs with &ldquo;confidence, <b>validity interval</b>, <b>change conditions</b>&rdquo;; "
             "<span class='cite'>docs/10</span> adds <i>&ldquo;a point estimate without them is a "
             "defect&rdquo;</i>",
             "<span class='mono'>memory_item</span> has <span class='mono'>confidence</span> and "
             "<b class='no'>neither</b> of the other two"),
            ("<span class='cite'>docs/10</span> §3.1", "memory with &ldquo;<b>expiring TTLs</b>&rdquo;",
             "<b class='no'>no expiry column anywhere.</b> <span class='mono'>superseded_by</span> models "
             "correction, not expiry; <span class='mono'>DecisionRecord.expires_at</span> exists but "
             "memory has no equivalent"),
            ("<span class='cite'>docs/03</span> §8 &middot; <span class='cite'>docs/10</span> §3.1",
             "evidence graph with &ldquo;<b>contradictions highlighted and linked</b>&rdquo;",
             "<span class='mono'>evidence_ref</span> has <b class='no'>no column linking one row to "
             "another it contradicts.</b> <span class='mono'>counter_evidence_refs</span> exists on the "
             "<i>decision</i>, not on the evidence"),
            ("<span class='cite'>docs/10</span> §3.1",
             "&ldquo;<b>knowledge-sufficiency meter with stated basis and what it is sufficient "
             "for</b>&rdquo;",
             "<span class='mono'>dossier.sufficiency</span> is a single "
             "<span class='mono'>TEXT</span> defaulting to "
             "<span class='mono'>'INSUFFICIENT'</span> &mdash; <b class='no'>no basis, no target</b>"),
        ],
    )


def alter_table() -> str:
    return table(
        ["Operation attempted against the real applied DDL", "Result"],
        [
            ("<span class='mono'>ALTER TABLE memory_item ADD COLUMN expires_at TEXT</span>",
             "<span class='ok'><b>OK</b></span>"),
            ("<span class='mono'>ALTER TABLE memory_item ADD COLUMN supersedes TEXT REFERENCES "
             "memory_item (memory_id)</span>",
             "<span class='ok'><b>OK</b></span> &mdash; and "
             "<span class='mono'>PRAGMA foreign_key_list</span> confirms the FK <i>is</i> registered"),
            ("<span class='mono'>ALTER TABLE memory_item ALTER COLUMN confidence TYPE "
             "NUMERIC(6,5)</span>",
             "<span class='no'><b>refused</b></span> &mdash; "
             "<span class='mono'>near \"ALTER\": syntax error</span>"),
            ("<span class='mono'>ALTER TABLE dossier ADD CONSTRAINT fk_instr FOREIGN KEY "
             "(instrument_id) REFERENCES instrument (instrument_id)</span>",
             "<span class='no'><b>refused</b></span> &mdash; "
             "<span class='mono'>near \"CONSTRAINT\": syntax error</span>"),
            ("create-new &rarr; copy &rarr; drop &rarr; rename",
             "<span class='ok'><b>OK</b></span> &mdash; the only route for a type change or an FK on an "
             "existing column"),
        ],
    )


def lever_table() -> str:
    return table(
        ["Lever", "What it does", "Why it is ordered here"],
        [
            ("<b>L-A</b> &mdash; schema fidelity",
             "migration <span class='mono'>0004_memory_fidelity</span> rebuilding "
             "<span class='mono'>memory_item</span> (confidence <span class='mono'>NUMERIC(6,5)</span> + "
             "<span class='mono'>CHECK</span>) and <span class='mono'>dossier</span> (its "
             "<span class='mono'>REFERENCES</span> restored), plus a <b>fidelity test</b> that parses both "
             "DDLs and asserts agreement on column names, nullability, defaults and FK declarations",
             "This is the guard that would have caught F-15. Without it the two schemas keep drifting and "
             "every later lever is written against a shape that may not survive a Postgres deploy"),
            ("<b>L-B</b> &mdash; project the master",
             "emit <span class='mono'>instrument.registered</span> audit events for the seeded master so "
             "<span class='mono'>persistence.counts.instrument</span> becomes 3 rather than 0",
             "F-16: a dossier's parent rows must exist before dossiers do. The replay path is already "
             "built, so this is an emitter, not a mechanism"),
            ("<b>L-C</b> &mdash; first writer",
             "<span class='mono'>evidence_ref</span> only: record one piece of evidence against a dossier, "
             "populating <span class='mono'>observed_at</span> and "
             "<span class='mono'>retrieved_at</span> <b>separately</b>, plus "
             "<span class='mono'>data_status</span>, <span class='mono'>locator</span>, "
             "<span class='mono'>checksum</span>, <span class='mono'>audit_ref</span>",
             "It is the leaf table, its FK is already enforced, and it needs no new columns. It is also "
             "where <b>F-14 gets its home</b>: the schema already separates observation from retrieval, so "
             "a writer that fills both correctly stops the venue-time defect propagating into the "
             "evidence graph"),
            ("<b>L-D</b> &mdash; first route",
             "<span class='mono'>/v1/intelligence/dossiers</span>, read-only, serving what exists and "
             "rendering empty honestly",
             "The Intelligence Centre chrome has been reserved since D-035 with nothing behind it. A route "
             "that returns an honest empty is worth more than a route that does not exist"),
            ("<b>L-E</b> &mdash; dossier writer",
             "create a dossier with <span class='mono'>stance=ABSTAIN</span> and sufficiency carried "
             "<b>with its basis and its target</b> as pinned payload keys",
             "Last because it depends on L-A (its FK), L-B (its parent rows) and L-C (its evidence). Its "
             "sufficiency must stay a string until Stage 10 defines the meter &mdash; but it must be a "
             "string that says what it is sufficient <i>for</i>"),
        ],
    )


def gate_table() -> str:
    return table(
        ["Claim", "Value", "Command"],
        [
            ("Production code changed", "<b>none</b> &mdash; the ruling was research only",
             "<span class='mono'>git diff --stat 4fef432..HEAD -- backend/src</span>"),
            ("Backend gate, unchanged from Stage 7's closure",
             "<b>1,036 passed / 2 skipped / 0 failed</b>",
             "<span class='mono'>pytest</span> with CI's env"),
            ("Types, lint, format", "mypy strict clean on <b>57</b> files; ruff + format clean on "
             "<b>82</b>", "<span class='mono'>mypy</span>, <span class='mono'>ruff check</span>, "
             "<span class='mono'>ruff format --check</span>"),
            ("Packages under <span class='mono'>src/nexus/</span>",
             "<b>15</b> &mdash; none named intelligence, research or memory",
             "<span class='mono'>ls src/nexus/</span>"),
            ("API routes", "<b>11</b>, all operational; none serving decisions, dossiers, memory or "
             "evidence", "<span class='mono'>grep -oE '\"/[^\"]*\"' src/nexus/api/app.py</span>"),
            ("Registry vs system of record",
             "<span class='mono'>instrument_master.count=<b>3</b></span> beside "
             "<span class='mono'>persistence.counts.instrument=<b>0</b></span>, on <b>both</b> backends",
             "<span class='mono'>GET /v1/status</span> under "
             "<span class='mono'>NEXUS_AUDIT_BACKEND=memory</span> and "
             "<span class='mono'>sqlite</span>"),
            ("Migrations applied", "<b>3</b> from <span class='mono'>schema.py</span> "
             "(<span class='mono'>0001_operational</span>, <span class='mono'>0002_memory</span>, "
             "<span class='mono'>0003_audit_append_only</span>) against <b>2</b> "
             "<span class='mono'>.sql</span> files",
             "<span class='mono'>grep -n 'version=\"' src/nexus/store/schema.py</span>; "
             "<span class='mono'>ls backend/migrations/</span>"),
        ],
    )


def limits_table() -> str:
    return table(
        ["#", "Limitation"],
        [
            ("1", "<b>Nothing here was executed against Postgres.</b> No server or driver exists in this "
                  "sandbox (<span class='cite'>docs/13</span> §2.5 records the same). Every statement "
                  "about Postgres behaviour is a property of the declared types, not a measurement &mdash; "
                  "including that <span class='mono'>NUMERIC(6,5)</span> would reject "
                  "<span class='mono'>'not-a-number'</span>"),
            ("2", "<b>The absence claims are grep-shaped.</b> &ldquo;No production code constructs a "
                  "<span class='mono'>DecisionRecord</span>&rdquo; is true of the literal "
                  "<span class='mono'>DecisionRecord(</span>; a factory or "
                  "<span class='mono'>**kwargs</span> splat built elsewhere could evade that pattern. The "
                  "supporting evidence is stronger than the grep alone &mdash; no route serves decisions "
                  "and <span class='mono'>counts.decision</span> is 0 on a booted app &mdash; but the grep "
                  "by itself would not prove it"),
            ("3", "<b><span class='mono'>payload</span> was not inventoried.</b> All three tables carry one "
                  "and nothing writes it, so there is no established key vocabulary to conform to. L-E "
                  "proposes pinning one; until then any claim about &ldquo;the payload contract&rdquo; "
                  "would be invented"),
            ("4", "<b>No design was produced.</b> 8.1 is an inventory and a constraint list. It proposes no "
                  "schema for beliefs, no contradiction model and no sufficiency semantics &mdash; the "
                  "first two need F-18's columns and the third is Stage 10's by "
                  "<span class='cite'>docs/12</span> §1.3"),
            ("5", "<b>The run-29 fold-in belongs to Stage 7, not Stage 8.</b> It is recorded in "
                  "<span class='cite'>docs/14</span> §4.1 in this same commit because the owner ruled it "
                  "should ride with this batch rather than generate a commit of its own. It is not evidence "
                  "about intelligence memory"),
        ],
    )


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())

    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI &middot; Stage 8.1 Intelligence Memory Research</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 8 of 23 &middot; sub-deliverable 8.1 (research) &middot;
authorised by D-049 &middot; no production code changed</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
Intelligence memory: three tables, no writers, and a schema that is not the mirror it claims to be</h1>
<div class="ribbon">RESEARCH BATCH &mdash; nothing in <span class="mono">backend/</span> was modified, so
no new CI surface and the gate is unchanged from Stage 7's closure (<b>1,036 passed / 2 skipped / 0
failed</b>). The inventory found the ground is not level: <b>five findings F-15&hellip;F-19</b> and
<b>five $0 levers L-A&hellip;L-E</b>. The two that matter most compound &mdash; the seeded instrument
master is in the registry and the API but <b>not in the system of record</b> (F-16), and the column that
would link a dossier to an instrument has <b>no foreign key at all</b> in the schema that actually runs
(F-15). So a dossier written today would point at an instrument the system of record has never heard of,
through a constraint that does not exist, and would store its confidence in a column that cannot be
ordered numerically.</div>

<h3>0 &middot; Why this board has no stage title to inherit<span class="tag">D-048 &middot; retraction</span></h3>
<p>Stage 7 closed by naming Stage 8 as the next batch. Two commits later
<span class="cite">docs/07</span> carried &ldquo;<b>STAGE 8 &mdash; KNOWLEDGE GRAPH</b>&rdquo; and the
board index carried &ldquo;Stage 8 &mdash; Knowledge graph&rdquo;. <b>No document in this repository says
that.</b> The title was invented, and it has been retracted (<span class="cite">f006d1f</span>). Searching
for a source found the opposite: Stage 8 has no name and no mandate at all. What the record does fix is
the chain it sits in:</p>
<div class="card">{chain_table()}</div>
<p class="cap">So Stage 8 is the first of the three stages that give those tables writers, and it sits
<i>before</i> the dossier stage and two stages before sufficiency is defined. Its scope is the
owner's to set. <b>This board does not set it</b> &mdash; it establishes what is there to build on, what
is missing, and what any builder would have to satisfy, then proposes a scope in &sect;9.</p>
<div class="blocked"><b>Why the retraction is on the board rather than quietly fixed.</b> A plausible
sounding label with nothing behind it is the same class of defect as <b>F-12</b> (a run count in source
that went stale) and the <span class="cite">41aca23</span> commit message that overclaims. It is cheaper
to retract it in the commit that introduced it than to let a future stage cite &ldquo;the knowledge graph
stage&rdquo; as though the repository had said so.</div>

<h3>1 &middot; What exists and works<span class="tag">docs/15 §2.1</span></h3>
<p>Read against the code, not against its summaries. More is built than &ldquo;tables only, writers
arrive later&rdquo; suggests &mdash; the decision <i>record</i>, its persistence, its audit contract and
its projection bookkeeping all exist:</p>
<div class="card">{exists_table()}</div>

<h3>2 &middot; What is absent<span class="tag">docs/15 §2.2</span></h3>
<div class="card">{absent_table()}</div>
<p class="cap">The P-2 chain is built from step 5 onward and <b>steps 1&ndash;4 are absent</b>:
candidate, sufficiency, verification gates, decision. Sufficiency is Stage 10's and the gates are Stage
11's by <span class="cite">docs/12</span> §1.3 &mdash; but that means Stage 8 is not extending a decision
layer, it is <b>creating the thing that produces decisions</b>.</p>
<div class="gate"><b>The honesty posture it inherits is already sound.</b>
<span class="mono">DecisionVerb.ABSTAIN</span> is the dataclass default,
<span class="mono">dossier.stance</span> defaults to <span class="mono">'ABSTAIN'</span> with the comment
<i>&ldquo;ABSTAIN is the default, not a fallback&rdquo;</i>, and
<span class="mono">save_decision_payload</span> defaults a missing verb to
<span class="mono">"ABSTAIN"</span>. What is missing is anything that could ever move off it.</div>

<h3>3 &middot; The master that does not reach the system of record<span class="tag">F-16 &middot; executed</span></h3>
<p>Stage 7.3 seeded three instruments. That seed reaches the <b>registry</b> and the coverage routes. It
does not reach the store that <span class="cite">docs/13</span> calls the system of record
(R-1 / D-042). Both backends, booted app, <span class="mono">GET /v1/status</span>:</p>
<div class="ba after"><div class="hd">TRANSCRIPT &mdash; VERBATIM, BOTH BACKENDS, BOOTED APP</div><pre>### NEXUS_AUDIT_BACKEND=memory
  engine/ephemeral/path : sqlite True None
  instrument_master.count      : 3
  counts.instrument            : 0
  counts.dossier/evidence/memory: 0 0 0
  counts.decision              : 0
  counts.op_projection         : 0

### NEXUS_AUDIT_BACKEND=sqlite
  engine/ephemeral/path : sqlite False ./data/nexus.db
  instrument_master.count      : 3
  counts.instrument            : 0
  counts.dossier/evidence/memory: 0 0 0
  counts.decision              : 0
  counts.op_projection         : 0</pre></div>
<p class="cap">The cause is not a missing call but a missing emitter:
<span class="mono">save_instrument</span> has exactly one caller,
<span class="cite">writeahead.py:82</span>, which replays an
<span class="mono">instrument.registered</span> audit event &mdash; and nothing in
<span class="mono">src/</span> ever emits one. Stage 7.3's seed writes thirteen entries into the
registry's own in-memory change log, not into the audit chain.</p>
<div class="blocked"><b>Two consequences, and they compound.</b> (1)
<span class="mono">dossier.instrument_id</span> has no candidate parent rows, so <b>every dossier written
today would reference an instrument the system of record has never heard of</b>. (2) Because of F-15,
that reference is undeclared, so <b>it would be accepted silently</b> rather than rejected. This is the
single most important scoping fact in this batch.</div>

<h3>4 &middot; F-15 &mdash; the mirror that is not one<span class="tag">executed against the real DDL</span></h3>
<p><span class="cite">migrations/0002_memory.sql</span> opens: <i>&ldquo;Mirror of migration 0002_memory
in <span class="mono">nexus/store/schema.py</span> (SQLite), which is the one applied today.&rdquo;</i>
Parsing both DDLs and diffing per column finds <b>six divergences</b>. The
<span class="mono">TIMESTAMPTZ</span>&rarr;<span class="mono">TEXT</span> and
<span class="mono">JSONB</span>&rarr;<span class="mono">TEXT</span> translations are legitimate &mdash;
SQLite has no such types. These are not translations, they are omissions:</p>
<div class="card">{divergence_table()}</div>
<p><span class="cite">docs/13</span> §2.5 <b>already records</b> that foreign keys are &ldquo;declared
but not enforced&rdquo;, and gives the reason: <span class="mono">PRAGMA foreign_keys</span> is off
because recovery re-projects in chain order, which is not always parent-first. That limitation is real
and deliberate, and this finding does not dispute it. <b>But it does not cover
<span class="mono">dossier.instrument_id</span></b>, which is not <i>declared</i> &mdash; so turning the
pragma on would not restore it. Executed proof that the two behave differently under the <b>same</b>
pragma:</p>
<div class="ba before"><div class="hd">EXECUTED &mdash; PRAGMA foreign_keys = ON, THE STRONGEST CASE</div><pre>dossier      -> instrument_id that never existed : ACCEPTED   (nothing to enforce)
evidence_ref -> dossier_id   that never existed : rejected, FOREIGN KEY constraint failed
memory_item  -> superseded_by that never existed: ACCEPTED   (no FK declared, in either schema)</pre></div>
<p>On <span class="mono">confidence</span> the divergence is behavioural, and <b>the obvious fix is not
sufficient</b>. The migration states its own law and the applied schema obeys neither half of it:</p>
<div class="ba before"><div class="hd">APPLIED SQLITE &mdash; confidence TEXT</div><pre>accepts '' and 'not-a-number'          -> both ACCEPTED
ORDER BY confidence                    -> ['', '0.5', '99999999', 'not-a-number']
                                          '99999999' sorts ABOVE '0.5'</pre></div>
<div class="ba after"><div class="hd">SAME SQLITE, DECLARED NUMERIC(6,5) INSTEAD</div><pre>ORDER BY                               -> [0.5, 0.5, 99999999, '', 'not-a-number']
                                          numerics now correct, junk last
INSERT 'not-a-number'                  -> STILL ACCEPTED, typeof() = text</pre></div>
<div class="gate"><b>So a type change fixes the ordering and not the acceptance.</b> SQLite affinity is a
conversion preference, not a constraint: it converts what it can and stores junk as-is. Postgres'
<span class="mono">NUMERIC(6,5)</span> would reject both strings outright, so the two schemas do not
merely store confidence differently &mdash; they <b>disagree about what a confidence is allowed to
be</b>. The real fix needs a <span class="mono">CHECK</span> constraint or validation in the writer, and
neither schema has one. This batch's first framing of F-15 was &ldquo;TEXT vs NUMERIC&rdquo;; executing it
produced the sharper fact, and the sharper fact changes what L-A has to do.</div>
<p class="cap"><b>Nothing detects any of this.</b> No test reads
<span class="mono">migrations/*.sql</span>; the runner applies
<span class="mono">schema.MIGRATIONS</span> (<span class="cite">migrations.py:111</span>,
<span class="cite">:229</span>), so the <span class="mono">.sql</span> files are executed by neither the
app nor the suite. The migration tests assert <i>names</i>, <i>checksums</i> and <i>ordering</i> &mdash;
never column definitions.</p>

<h3>5 &middot; F-17, F-18 and F-19<span class="tag">docs/15 §3</span></h3>
<div class="card">{design_gap_table()}</div>
<p class="cap"><b>F-18.</b> Stage 3.3 was approved at <b>D-035</b>, so these are obligations, not
aspirations. All four could be pushed into the unenforced <span class="mono">payload</span> column, which
is how a schema starts lying: the field exists, the meaning does not. Three of the four are <b>cheap to
add properly</b> (&sect;6); only sufficiency needs Stage 10's definition before it can be more than a
string.</p>
<div class="blocked"><b>F-19 &mdash; finding ids already collide, and nothing says so.</b>
<span class="cite">docs/13</span> uses F-1&hellip;F-7 and <span class="cite">docs/14</span> uses
F-1&hellip;F-14, and they are different findings: <span class="cite">docs/13</span>'s <b>F-4</b> is
<i>&ldquo;the Postgres path is part-paid, not free&rdquo;</i> while <span class="cite">docs/14</span>'s
<b>F-4</b> is <i>venue vocabulary</i>. Neither document states that its ids are scoped to itself, and
<span class="cite">docs/07</span> cites bare ids &mdash; so &ldquo;F-4&rdquo; is ambiguous in this
repository today, and Stage 8 would have made it three ways. <b>Recorded rather than rewritten:</b>
renumbering two approved stages would falsify their citations, so this batch continues from <b>F-15</b>,
which creates no new collision.</div>

<h3>6 &middot; What any writer must satisfy<span class="tag">docs/15 §5 &middot; constraints, not preferences</span></h3>
<p>The audit contract, from the existing writers at
<span class="cite">operational.py:372-408</span>: validate the identity column and raise
<span class="mono">PersistenceError</span> if absent &rarr;
<span class="mono">assert_no_secrets(payload)</span> &rarr; write inside
<span class="mono">self._transaction()</span>, defaulting state/verb/stance to their ABSTAIN-side values
&rarr; <span class="mono">self._mark(conn, audit_ref, entity_type, entity_id)</span> into
<span class="mono">op_projection</span>. The store uses
<span class="mono">INSERT OR REPLACE</span>, so it is a <b>projection</b> and the audit chain is the
record; a re-save is not an edit, which is why <span class="mono">superseded_by</span> exists.</p>
<p>Migrations are forward-only and checksummed &mdash; <span class="cite">migrations.py:194-199</span>
refuses a version whose checksum changed after it was applied &mdash; so <b>no column in
<span class="mono">0002_memory</span> can be edited</b> and any fix is a new
<span class="mono">0004_*</span>. The migration <i>boundaries</i> already differ too: three applied
versions against two <span class="mono">.sql</span> files, with no
<span class="mono">0003</span>. The append-only triggers themselves do mirror faithfully (same names,
same two operations, <span class="cite">0001_core.sql:26-38</span>), so this is a boundary difference and
not a missing feature &mdash; but a Postgres deploy following the <span class="mono">.sql</span> files
would have a different migration history from the one
<span class="cite">test_boot_recovery.py:341</span> asserts.</p>
<div class="card">{alter_table()}</div>
<p class="cap">Executed, not assumed &mdash; and this is what makes the sequencing in &sect;9 a real
choice rather than a preference. <b>Cheap, no rebuild:</b> adding
<span class="mono">valid_from</span>, <span class="mono">valid_until</span>,
<span class="mono">change_conditions</span> and <span class="mono">expires_at</span> to
<span class="mono">memory_item</span>, plus a <span class="mono">contradicts</span> FK column on
<span class="mono">evidence_ref</span> &mdash; three of F-18's four gaps. <b>Requires a table rebuild
inside a forward-only migration:</b> <span class="mono">confidence</span> and
<span class="mono">dossier.instrument_id</span> &mdash; F-15(a) and (c).</p>

<h3>7 &middot; Run 29, folded in as ruled<span class="tag">docs/14 §4.1 &middot; Stage 7 evidence</span></h3>
<p>The owner ruled that the run-29 evidence should ride with this batch rather than generate a commit of
its own. It belongs to Stage 7, and it is recorded here because it corrects a claim on the 7.3 board.</p>
<div class="ba before"><div class="hd">WHAT THE 7.3 BOARD SAID</div><pre>gap 0.000 in five consecutive runs, across four different prices ...
five zeros is not a tolerance waiting to be sized. It is the absence of a phenomenon.</pre></div>
<div class="ba after"><div class="hd">RUN 29 (45840904271) &mdash; 44 / 0 / 5 geo-blocked / 0 skipped of 49</div><pre>okx.cross_endpoint quotes_mid=60736.25 book_mid=60735.25 gap_bps=0.165
                   dt_observed_s=1.17 dt_wall_s=0.295
                   bps_per_s_observed=0.141 bps_per_s_wall=0.557
                   quoted_spread_bps=0.016 asserts_agreement=False</pre></div>
<p class="cap">&ldquo;Five consecutive zeros&rdquo; was five runs and not a property &mdash; the same
lesson run 27 taught about skips. What replaces it is stronger than what it displaced: <b>both rate
readings are nonzero and differ by 3.95&times;</b>, and only the wall clock measures the interval between
the two fetches, so <b>0.557 bps/s is the rate that means anything</b>. The venue-stamped rate understates
it fourfold by dividing the same gap across 1.170 s of skew &mdash; <b>F-14 quantified rather than merely
demonstrated</b>: using <span class="mono">observed_at</span> as the denominator does not just add noise,
it biases the rate <i>downward</i>. The gap is 10.3&times; the 0.016 bps quoted spread, so it is not tick
rounding. Arithmetic re-verified before publication, and a first check that compared point estimates
rather than intersecting the two rounding intervals reported a <b>false</b> mismatch &mdash; recorded
because the check was wrong and not the evidence.</p>

<h3>8 &middot; Verification and limitations<span class="tag">docs/15 §5, §7</span></h3>
<div class="card">{gate_table()}</div>
<p class="cap">Every number above was produced by the command beside it and re-verified before being
written here. Nothing in this batch re-triggers per push, because nothing in it is a count of CI runs.</p>
<div class="card">{limits_table()}</div>

<h3>9 &middot; Decision requested<span class="tag">docs/15 §8</span></h3>
<div class="card">{lever_table()}</div>
<div class="ask">
<p><b>Recommendation: authorise 8.2 as L-A + L-B + L-C, and defer L-D and L-E to 8.3.</b> The reasoning is
dependency, not caution. F-16 and F-15 together mean a dossier written today would point at an instrument
the system of record has never heard of, through a constraint that does not exist, storing its confidence
in a column that cannot be ordered numerically. Writing the dossier first would build the intelligence
layer on a schema that cannot hold what the approved design requires &mdash; and every row written before
L-A would have to be migrated afterward.</p>
<ol>
<li><b>Is batch 8.1 approved?</b> Its findings F-15&hellip;F-19 and levers L-A&hellip;L-E are the base 8.2
would stand on. Stage 7.1 was left unratified for a day and needed <b>D-047</b> to fix it; this one is
asked up front.</li>
<li><b>Does F-15 get fixed by a rebuild migration (L-A), or is the divergence accepted and documented?</b>
A rebuild touches two tables inside a forward-only migration and must keep the audit chain intact.
Accepting it instead means the Postgres target and the applied schema stay different, and that difference
should then be stated in <span class="cite">docs/13</span> §2.5 rather than left in a comment claiming to
be a mirror. <b>Recommendation: fix it, and add the fidelity test</b> &mdash; the test is what makes the
fix stay fixed.</li>
<li><b>Should F-14 be fixed before or alongside L-C?</b> L-C can populate
<span class="mono">retrieved_at</span> from the local clock and <span class="mono">observed_at</span> from
the venue, making the evidence graph correct <i>without</i> changing what
<span class="mono">observed_at</span> means in the four adapters. That is the cheap half; the expensive
half is still unauthorised. <b>Recommendation: do the cheap half in L-C and keep F-14 open</b>, so no
writer imports the defect, and re-ask the adapter change on its own merits.</li>
<li><b>Should finding ids be scoped explicitly from here on?</b> F-19 records that F-1&hellip;F-7 are
already ambiguous between two approved documents. Options: continue global numbering (what this batch
does), or prefix per stage from Stage 8 onward and leave the historical ids alone.
<b>Recommendation: continue global numbering</b> &mdash; a prefix scheme introduced halfway creates a
second convention to remember, and the collision is now recorded where a reader will find it.</li>
</ol>
</div>

<footer>Stage 8.1 &middot; research &middot; D-049 &middot; no production code changed, gate unchanged at
1,036 passed / 2 skipped / 0 failed, mypy strict clean on 57 files, ruff + format clean on 82 &middot;
five findings F-15&hellip;F-19, five $0 levers L-A&hellip;L-E &middot; every claim produced by a named
command and re-verified; the FK divergence, the confidence ordering and SQLite's ALTER TABLE limits were
executed against the real applied DDL rather than inferred &middot; the invented stage title
&ldquo;knowledge graph&rdquo; retracted in f006d1f, and Stage 7's &ldquo;five consecutive zeros&rdquo;
corrected by run 29 in this same commit &middot; F-14, F-2, F-5, F-6 and F-11 remain open from Stage 7;
F-15&hellip;F-19 open here</footer>
</div></body></html>"""
    out = HERE / "stage8-1-intelligence-memory.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
