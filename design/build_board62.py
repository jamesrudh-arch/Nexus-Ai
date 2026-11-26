"""Stage 6.2 board: implementation evidence for Database & Persistent Memory.

Every claim on this board is a test, a gate output, or a file. Where something is not done, it says
so in the same typeface as the things that are.

Run:  backend/.venv/bin/python design/build_board62.py
"""

from __future__ import annotations

import pathlib
import re

from build_board42 import CSS as CSS42
from build_specimen import fonts_css

HERE = pathlib.Path(__file__).resolve().parent
CSS = CSS42 + """
h3 { font-size: var(--font-size-emphasis); font-weight: var(--font-weight-semibold);
  margin: 40px 0 2px; }
h3 .tag { font-family: var(--font-family-mono); font-size: var(--font-size-caption);
  font-weight: var(--font-weight-regular); color: var(--color-text-muted); margin-left: 8px; }
.defect { border-left: 3px solid var(--color-feedback-warning-graphic); padding: 8px 12px;
  background: var(--color-surface-elevated); margin-top: 10px; font-size: var(--font-size-caption);
  line-height: 1.55; border-radius: 0 var(--radius-card) var(--radius-card) 0; }
.defect .cite { font-family: var(--font-family-mono); color: var(--color-text-muted); }
.gate { border: 1px solid var(--color-feedback-positive-graphic); border-radius: var(--radius-card);
  padding: 10px 14px; background: var(--color-feedback-positive-subtle); margin-top: 12px;
  font-family: var(--font-family-mono); font-size: var(--font-size-data);
  color: var(--color-feedback-positive-text); }
"""


def flow(steps: list[tuple[str, str]]) -> str:
    return '<div class="flow">' + "".join(
        f'<div class="fstep"><span class="n">{i}</span><div class="t">{t}</div>'
        f'<div class="w">{w}</div></div>'
        for i, (t, w) in enumerate(steps, 1)
    ) + "</div>"


BOOT = [
    ("Open store", "SqliteOperationalStore(path, audit=…) · WAL · synchronous=FULL · busy_timeout 5000 · same file as the audit chain"),
    ("Apply migrations", "MigrationRunner.run() · 0001_operational, 0002_memory, 0003_audit_append_only · checksum + hole refusals · each application audited"),
    ("Verify chain", "AuditLog.verify() · any break ⇒ BootRefused(AUDIT_CHAIN_INVALID), retryable=False, and nothing is written to the broken chain"),
    ("Finish unfinished writes", "reproject_missing() compares the chain against op_projection and re-applies what a crash left behind (L-2)"),
    ("Re-derive halt", "derive_halt_state(store.halt_events()) · unreadable history ⇒ indeterminate_halt_state() = ALL_TRADING kill switch"),
    ("Resolve open orders", "SENT_STATES ⇒ UNKNOWN · pre-submission ⇒ EXPIRED / REJECTED_BY_GOVERNANCE · terminal states untouched · stable on a second run"),
    ("Report", "boot.recovery audited · /readyz 503 while anything is unresolved · /v1/status carries the persistence block"),
]


def closed_table() -> str:
    rows = [
        ("F-2", "operational state had DDL but no writer — a restart lost decisions, intents, approvals, orders, fills, halt events and limit changes",
         "<code>nexus.store.operational.SqliteOperationalStore</code>: typed writers and readers for nine entities, Decimal stored as exact TEXT, secrets refused at the boundary",
         "test_store_persistence.py (17 tests) — round trips, Decimal exactness, refusals"),
        ("F-3", "a restart cleared an active halt: <code>HaltManager.__init__</code> built <code>HaltState()</code> = scope NONE, active False",
         "halt events are durable; boot re-derives state and hands it back as <code>restored_state</code>, preserving incident id, scope, reason and timestamp. Unreadable history ⇒ kill switch",
         "test_boot_recovery.py — restart keeps ALL_TRADING + incident id; release boots clean; blind store fails closed"),
        ("F-6", "TimescaleDB was health-checked and waited on while nothing read it: 1.5 GB of a 12 GB budget",
         "<code>db</code> moved to an opt-in <code>postgres</code> profile; <code>core</code> depends on <code>nats</code> only; tiers T1–T5 documented in the compose header; T3 3.71 GB → 2.18 GB without db",
         "compose YAML parsed and asserted (db profiles, core depends_on); CI compose job validates on push"),
        ("F-7", "<b>found during implementation:</b> the gateway's idempotency ledger (<code>_seen_intents</code>) was in-memory, so a restart lost the record of which intents had been processed — exactly when a duplicate order becomes possible",
         "<code>execution_result</code> table + <code>rehydrate_from_store()</code> at construction; a replay after restart returns the same refusal, with IDEMPOTENCY_CONFLICT and its audit entry",
         "test_boot_recovery.py::TestDurableIdempotency — restart, rehydrate 1, replay refused"),
    ]
    return ("<table><tr><th>finding</th><th>what was wrong</th><th>what closes it</th>"
            "<th>proof</th></tr>" +
            "".join(f"<tr><td class='mono'><b>{a}</b></td><td>{b}</td><td>{c}</td>"
                    f"<td class='cap'>{d}</td></tr>" for a, b, c, d in rows) + "</table>")


def schema_table() -> str:
    rows = [
        ("audit_log", "governance record, hash-chained", "SqliteAuditStore (Phase 2)", "<b>written + tested</b>, now with append-only triggers"),
        ("schema_migrations", "which migrations applied, with checksums", "MigrationRunner", "<b>new</b>"),
        ("instrument", "canonical master + coverage state", "save_instrument()", "<b>new</b>"),
        ("decision", "decision records, ABSTAIN default", "save_decision()", "<b>new</b>"),
        ("trade_intent", "immutable intent + digest + idempotency key", "save_intent()", "<b>new</b>"),
        ("approval", "digest-bound approval, step-up flag", "save_approval()", "<b>new</b>"),
        ("orders", "order lifecycle state", "save_order() / update_order_state()", "<b>new</b>"),
        ("fills", "venue-reported fills only", "save_fill()", "<b>new</b>"),
        ("execution_result", "durable idempotency ledger (F-7)", "gateway.submit() → save_execution_result()", "<b>new</b>"),
        ("halt_event", "durable halt history, monotonic seq", "HaltManager._record()", "<b>new</b>"),
        ("risk_limit_change", "owner-set limit changes + cooldown", "save_limit_change()", "<b>new</b>"),
        ("op_projection", "which audit records have been projected (L-2)", "every writer, in the same transaction", "<b>new</b>"),
        ("dossier · evidence_ref · memory_item", "intelligence memory with mandatory provenance", "none — stages 8–10 own the writers", "<b>schema only, by design</b>"),
    ]
    return ("<table><tr><th>table</th><th>role</th><th>writer</th><th>status</th></tr>" +
            "".join(f"<tr><td class='mono'>{a}</td><td class='cap'>{b}</td><td class='cap'>{c}</td>"
                    f"<td>{d}</td></tr>" for a, b, c, d in rows) + "</table>")


DEFECTS = [
    ("ID-1", "Migration 0003 (append-only triggers on <code>audit_log</code>) failed outright on an "
     "ephemeral audit backend — an in-memory audit log has no table to protect, and the runner "
     "treated that as a broken migration.",
     "Migrations gained a <code>requires</code> declaration. A migration whose requirement is absent "
     "is <b>skipped and reported</b> — and deliberately <i>not</i> recorded as applied, so a later "
     "boot against a durable store still gets its triggers. Two tests pin both halves of that.",
     "store/schema.py Migration.requires · store/migrations.py SkippedMigration"),
    ("ID-2", "The forward-only gap check called a skipped migration a hole, which broke an ordinary "
     "path: reopening a durable store with no audit store present raised MIGRATION_INVALID at boot.",
     "A hole is now defined correctly — an <i>applicable</i> migration still pending <b>below</b> the "
     "last applied one. The real hole case (0001 and 0003 applied, 0002 missing) still refuses.",
     "store/migrations.py _validate() · tests/test_migrations.py::test_gap_in_the_sequence_is_refused"),
    ("ID-3", "The explicit \"construct the audit store first\" refusal never fired, because SQLite "
     "reports <code>no such table: main.audit_log</code> and the check matched the unqualified name.",
     "Match widened; a test now asserts the message a developer actually sees when ordering is wrong.",
     "store/migrations.py _apply()"),
    ("ID-4", "Tooling, not product: a patch script put a docstring inside a triple-quoted string, so "
     "it died at parse time and applied nothing while the suite still reported the old failures.",
     "Caught by the assert-before-write discipline (no partial writes), re-run with the nested "
     "docstring replaced by a comment. Recorded because a silent no-op patch is how evidence gets "
     "misreported.", "this board"),
    ("ID-5", "Two API tests asserted the durable file path without declaring it. Locally the default "
     "audit backend is SQLite, so they passed; CI runs the whole suite with "
     "<code>NEXUS_AUDIT_BACKEND=memory</code>, which makes both stores ephemeral by design, and the "
     "first push failed CI's pytest step.",
     "The tests now set the backend they mean, and the rule they depended on is pinned by a new "
     "test: with an ephemeral audit log the operational store is ephemeral too and <b>no file is "
     "created</b> behind the operator's back. Recorded because CI caught what the local run could "
     "not — a green local suite is not the gate.",
     "run 45753053217 ✗ → f994271 → run 45753628845 ✓"),
]


def limits_table() -> str:
    rows = [
        ("Foreign keys are declared but not enforced", "<code>PRAGMA foreign_keys</code> stays off: recovery re-projects in chain order, which is not always parent-first, and a hard FK failure mid-recovery would be worse than the inconsistency it prevents. Writer order and recovery reconcile instead.", "documented in store/schema.py"),
        ("No PostgreSQL store implementation", "R-1 keeps <code>0001_core.sql</code> as the portable target and the <code>OperationalStore</code> Protocol as the seam. Nothing connects to Postgres; <code>db</code> is opt-in.", "no driver installed (asyncpg/psycopg absent)"),
        ("Triggers T-1…T-4 are unmeasured", "The single-writer ceiling and the write-throughput ceiling are not benchmarked; Stage 23 validation measures them. No claim is made that SQLite is sufficient at any particular scale.", "docs/13 §1.3"),
        ("Vector recall still undecided", "No embedding store is chosen, installed or claimed. pgvector would pull Postgres in via T-3; a DuckDB VSS path is unverified here.", "board 6.1"),
        ("Intelligence memory has no writers", "<code>dossier</code>, <code>evidence_ref</code>, <code>memory_item</code> exist so provenance is mandatory from the start; stages 8–10 write them.", "migration 0002_memory"),
        ("Off-VM backup is still untested", "No backup has been restored in this project. Recovery here means \"restart on the same host\"; the DR rows from 5.2 are unchanged, and Stage 20 owns the drill.", "docs/12 §2.3"),
        ("Compose change validated in CI, not locally", "Docker is unavailable in this sandbox, so the edit was first checked by parsing the YAML and asserting the two intended facts (db profiles, core depends_on), then validated for real by CI: `Compose config valid` plus the runtime smoke test, which brought up `nats core` — no `db` — in a real container and served requests from it.", "CI run 45753628845 ✓"),
    ]
    return ("<table><tr><th>limitation</th><th>why, stated plainly</th><th>where it is recorded</th></tr>" +
            "".join(f"<tr><td><b>{a}</b></td><td>{b}</td><td class='cap'>{c}</td></tr>"
                    for a, b, c in rows) + "</table>")


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())
    defects = "".join(
        f"<div class='defect'><b>{tag}</b> — {what}<br><b>Fix:</b> {fix}<br>"
        f"<span class='cite'>{cite}</span></div>"
        for tag, what, fix, cite in DEFECTS
    )
    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI · Stage 6.2 Implementation Evidence</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 6 of 23 &middot; sub-deliverable 6.2 (final batch)</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
Database &amp; persistent memory: implementation evidence</h1>
<div class="ribbon">IMPLEMENTATION BATCH — the backend pause was lifted by the owner for this work.
Four findings closed (F-2, F-3, F-6, F-7), six new modules under <code>nexus/store/</code>, 48 new
tests, CI green on all five jobs. The limitations table below is part of the deliverable, not a
footnote: nothing here claims a backup was restored, a Postgres store exists, or a scaling ceiling
was measured. The first push failed CI's pytest step (ID-5) and that failure is on this board, not
edited out of it.</div>

<div class="gate">local pytest: 976 passed, 2 skipped (both pre-existing: live-egress, 7m interval), 0 failed —
  identical under CI's env (NEXUS_AUDIT_BACKEND=memory) and under the default SQLite backend
  978 collected vs a 930 baseline · ruff check: All checks passed · ruff format --check: 80 files
  unchanged · mypy --strict: Success, no issues in 56 source files
new tests: 48 — test_migrations.py 12 · test_store_persistence.py 17 · test_boot_recovery.py 19</div>
<div class="gate">CI run 45753628845 (commit f994271): Secret scanning ✓ · Compose config valid ✓ ·
  Backend lint+types+tests ✓ · Runtime smoke test ✓ (real container, `nats core`, no `db`) ·
  Container image amd64+arm64 ✓
first push f69def3 → run 45753053217: backend pytest ✗ (ID-5) — compose and smoke were already ✓</div>

<h3>Boot sequence, as implemented<span class="tag">laws L-1, L-2, L-6</span></h3>
{flow(BOOT)}
<div class="branch neg"><b>Failure semantics:</b> a chain that does not verify raises
<code>BootRefused</code> and is not written to; the API then fails closed into the
<code>ALL_TRADING</code> kill switch, <code>/readyz</code> returns 503 with
<code>AUDIT_CHAIN_INVALID</code>, and <code>/v1/status</code> says so on the wire (A-06). An order
left non-terminal becomes UNKNOWN and blocks new risk until reconciliation — it is never resolved by
guessing.</div>

<h3>Findings closed</h3>
<div class="card">{closed_table()}</div>

<h3>Schema: what is written by what</h3>
<div class="card">{schema_table()}</div>
<p class="cap">One SQLite file holds the audit chain and operational state (R-1: one system of record
per data class). Market time series stay in the Parquet+zstd archive; <code>market_tick</code> and
<code>market_bar</code> were retired from the PostgreSQL target rather than wired, so no data class
has two durability stories.</p>

<h3>Defects the implementation exposed<span class="tag">ID-n, not D-n: these are not register decisions</span></h3>
{defects}

<h3>Limitations — stated in the same typeface as the wins</h3>
<div class="card">{limits_table()}</div>

<h3>What changed where</h3>
<div class="card"><table>
<tr><th>area</th><th>change</th></tr>
<tr><td class="mono">nexus/store/ (new)</td><td>schema · migrations · operational · writeahead · recovery · serialise</td></tr>
<tr><td class="mono">core/errors.py</td><td>four reason codes: PERSISTENCE_FAILED, AUDIT_CHAIN_INVALID, BOOT_RECOVERY_INCOMPLETE, MIGRATION_INVALID</td></tr>
<tr><td class="mono">audit/log.py</td><td><code>records()</code> for recovery, <code>store</code> property so wiring can match durability footings</td></tr>
<tr><td class="mono">execution/halt.py</td><td>durable <code>store</code>, <code>restored_state</code>, RESTORED history entry</td></tr>
<tr><td class="mono">execution/gateway.py</td><td>durable idempotency ledger + <code>rehydrate_from_store()</code> + <code>rehydrated_count</code></td></tr>
<tr><td class="mono">api/app.py</td><td>operational store wiring, boot recovery, fail-closed halt, <code>/readyz</code> problems, <code>/v1/status</code> persistence block</td></tr>
<tr><td class="mono">migrations/*.sql</td><td>market_tick/market_bar retired; execution_result + op_projection added; 0002_memory.sql mirror</td></tr>
<tr><td class="mono">docker-compose.yml · infra/smoke-test.sh · .env.example</td><td>db opt-in (<code>postgres</code> profile), tiers T1–T5 in the header, KNOWN GAP → RESOLVED, smoke defaults to <code>nats core</code>, storage guidance rewritten</td></tr>
</table></div>
<footer>Stage 6.2 &middot; gate 976/2/0 &middot; ruff + format + mypy strict clean &middot; Stage 6
closes for stage-level approval after this batch.</footer>
</div></body></html>"""
    out = HERE / "stage6-2-implementation-evidence.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
