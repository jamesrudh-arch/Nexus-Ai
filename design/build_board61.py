"""Stage 6.1 board: persistent-memory architecture, findings from code, the P-6 ruling.

Design only. Every finding cites the file it was read from; the two safety-relevant gaps are
stated plainly rather than softened, because Stage 6 exists to close them.

Run:  backend/.venv/bin/python design/build_board61.py
"""

from __future__ import annotations

import pathlib
import re

from build_board42 import CSS as CSS42
from build_specimen import fonts_css

HERE = pathlib.Path(__file__).resolve().parent
CSS = CSS42 + """
.diag { width: 100%; background: var(--color-surface-panel);
  border: 1px solid var(--color-border-subtle); border-radius: var(--radius-card); }
.diag text { font-family: var(--font-family-sans); }
.diag .mono { font-family: var(--font-family-mono); }
h3 { font-size: var(--font-size-emphasis); font-weight: var(--font-weight-semibold);
  margin: 40px 0 2px; }
h3 .tag { font-family: var(--font-family-mono); font-size: var(--font-size-caption);
  font-weight: var(--font-weight-regular); color: var(--color-text-muted); margin-left: 8px; }
.finding { border-left: 3px solid var(--color-feedback-negative-graphic); padding: 8px 12px;
  background: var(--color-surface-elevated); margin-top: 10px; font-size: var(--font-size-caption);
  line-height: 1.55; border-radius: 0 var(--radius-card) var(--radius-card) 0; }
.finding.warn { border-color: var(--color-feedback-warning-graphic); }
.finding.ok { border-color: var(--color-feedback-positive-graphic); }
.finding .cite { font-family: var(--font-family-mono); color: var(--color-text-muted); }
.rec { border: 1px solid var(--color-feedback-positive-graphic); border-radius: var(--radius-card);
  padding: 12px 14px; background: var(--color-feedback-positive-subtle); margin-top: 12px; }
.rec .t { font-size: var(--font-size-emphasis); font-weight: var(--font-weight-semibold);
  color: var(--color-feedback-positive-text); }
"""

TIERS = """
<svg class="diag" viewBox="0 0 940 430" role="img"
     aria-label="Persistence tiers: durable engines, volatile cache, demoted Postgres">
  <defs>
    <marker id="ar3" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7"
            orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="var(--color-text-muted)"/></marker>
  </defs>
  <g font-size="9" class="mono" fill="var(--color-text-muted)">
    <text x="16" y="18">CORE PROCESS (single writer today — the constraint that decides P-6)</text>
    <text x="16" y="150">DURABLE · SYSTEM OF RECORD</text>
    <text x="16" y="300">VOLATILE · NEVER A SOURCE OF TRUTH</text>
    <text x="560" y="150">DEMOTED / PLANNED — dashed until a trigger condition is measured</text>
  </g>
  <!-- core -->
  <rect x="16" y="28" width="500" height="100" rx="10" fill="none" stroke="var(--color-border-strong)"/>
  <g font-size="10">
    <rect x="30" y="44" width="140" height="34" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="40" y="65" fill="var(--color-text-primary)">AuditLog.record/verify</text>
    <rect x="184" y="44" width="150" height="34" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="194" y="65" fill="var(--color-text-primary)">IngestionPipeline.persist</text>
    <rect x="348" y="44" width="154" height="34" rx="6" fill="var(--color-feedback-negative-subtle)"/>
    <text x="358" y="65" fill="var(--color-feedback-negative-text)">operational state (gap)</text>
    <rect x="30" y="86" width="230" height="32" rx="6" fill="var(--color-feedback-negative-subtle)"/>
    <text x="40" y="106" fill="var(--color-feedback-negative-text)">HaltManager — in-memory, cleared on restart</text>
    <rect x="274" y="86" width="228" height="32" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="284" y="106" fill="var(--color-text-primary)">decisions · intents · approvals · orders · fills</text>
  </g>
  <!-- durable -->
  <g font-size="10">
    <rect x="16" y="160" width="240" height="110" rx="8" fill="var(--color-surface-elevated)"/>
    <text x="28" y="180" fill="var(--color-text-primary)">SQLite — governance record</text>
    <text x="28" y="196" class="mono" fill="var(--color-text-muted)">audit_log · WAL · synchronous=FULL</text>
    <text x="28" y="210" class="mono" fill="var(--color-text-muted)">SHA-256 hash chain · append-only</text>
    <text x="28" y="224" class="mono" fill="var(--color-text-muted)">assert_no_secrets at the boundary</text>
    <text x="28" y="240" class="mono" fill="var(--color-feedback-positive-text)">implemented + tested (22 tests)</text>
    <text x="28" y="256" class="mono" fill="var(--color-text-muted)">Stage 6 adds the operational tables</text>
    <rect x="276" y="160" width="240" height="110" rx="8" fill="var(--color-surface-elevated)"/>
    <text x="288" y="180" fill="var(--color-text-primary)">Parquet + zstd — time series</text>
    <text x="288" y="196" class="mono" fill="var(--color-text-muted)">Hive: dataset/venue/symbol/interval/y/m</text>
    <text x="288" y="210" class="mono" fill="var(--color-text-muted)">files never rewritten · DuckDB reads</text>
    <text x="288" y="224" class="mono" fill="var(--color-text-muted)">D-024 ladder: ticks 30d · 1m 12mo</text>
    <text x="288" y="240" class="mono" fill="var(--color-feedback-positive-text)">implemented + tested (59+ tests)</text>
    <text x="288" y="256" class="mono" fill="var(--color-text-muted)">re-derivable from public venues</text>
  </g>
  <!-- volatile -->
  <g font-size="10">
    <rect x="16" y="310" width="240" height="60" rx="8" fill="var(--color-surface-elevated)"/>
    <text x="28" y="330" fill="var(--color-text-primary)">Valkey cache · 200mb LRU</text>
    <text x="28" y="346" class="mono" fill="var(--color-text-muted)">rate limits, hot registry state</text>
    <text x="28" y="360" class="mono" fill="var(--color-feedback-warning-text)">loss is a slow start, never a wrong number</text>
    <rect x="276" y="310" width="240" height="60" rx="8" fill="var(--color-surface-elevated)"/>
    <text x="288" y="330" fill="var(--color-text-primary)">MinIO objects</text>
    <text x="288" y="346" class="mono" fill="var(--color-text-muted)">exports, reports, artifacts (P-4)</text>
    <text x="288" y="360" class="mono" fill="var(--color-text-muted)">content-addressed by version</text>
  </g>
  <!-- demoted / planned -->
  <g font-size="10">
    <rect x="556" y="160" width="368" height="110" rx="8" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="568" y="180" fill="var(--color-feedback-intelligence-text)">PostgreSQL 16 + TimescaleDB — demoted to opt-in profile</text>
    <text x="568" y="196" class="mono" fill="var(--color-text-muted)">0001_core.sql: 12 tables, portable DDL, hypertable commented out</text>
    <text x="568" y="210" class="mono" fill="var(--color-text-muted)">SQLAlchemy 2.1.9 already a runtime dep; driver NOT installed</text>
    <text x="568" y="224" class="mono" fill="var(--color-text-muted)">api/app.py refuses non-sqlite schemes, leaking only the scheme</text>
    <text x="568" y="242" class="mono" fill="var(--color-feedback-warning-text)">triggers: 2nd writer process · write-throughput ceiling ·</text>
    <text x="568" y="256" class="mono" fill="var(--color-feedback-warning-text)">hypertable/pgvector need · multi-node — each measured, not assumed</text>
    <rect x="556" y="290" width="176" height="80" rx="8" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="568" y="310" fill="var(--color-feedback-intelligence-text)">intelligence memory</text>
    <text x="568" y="326" class="mono" fill="var(--color-text-muted)">dossiers · evidence refs</text>
    <text x="568" y="340" class="mono" fill="var(--color-text-muted)">stages 8–10 · schema now,</text>
    <text x="568" y="354" class="mono" fill="var(--color-text-muted)">writer later</text>
    <rect x="748" y="290" width="176" height="80" rx="8" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="760" y="310" fill="var(--color-feedback-intelligence-text)">vector recall</text>
    <text x="760" y="326" class="mono" fill="var(--color-text-muted)">engine UNDECIDED:</text>
    <text x="760" y="340" class="mono" fill="var(--color-text-muted)">pgvector needs Postgres;</text>
    <text x="760" y="354" class="mono" fill="var(--color-text-muted)">DuckDB VSS unverified here</text>
  </g>
  <g stroke="var(--color-text-muted)" stroke-width="1" fill="none">
    <path d="M100,78 V160" marker-end="url(#ar3)"/>
    <path d="M259,78 V128 H396 V160" marker-end="url(#ar3)"/>
    <path d="M145,118 V160" marker-end="url(#ar3)"/>
    <path d="M455,78 V118" />
  </g>
  <g font-size="8.5" class="mono" fill="var(--color-text-muted)">
    <text x="16" y="396">two engines already hold the two hardest jobs and are tested; the third (operational state) is the gap Stage 6 closes</text>
    <text x="16" y="410">law: one system of record per data class — two audit stores at once is worse than the 1.5 GB it saves</text>
  </g>
</svg>"""


def findings() -> str:
    rows = [
        ("F-1", "ok", "Two durable stores exist and are tested: <b>SqliteAuditStore</b> (WAL, "
         "<code>synchronous=FULL</code>, SHA-256 chain, tamper/gap/reorder detection, "
         "<code>assert_no_secrets</code> refusing keys, patterns and long secret-like values) and "
         "<b>ParquetArchive</b> (zstd, Hive partitions, files never rewritten, DuckDB reads).",
         "audit/log.py · archive/parquet_store.py · tests/test_audit.py (22) · test_archive_bars.py (59)"),
        ("F-2", "neg", "<b>Operational state has DDL but no writer.</b> <code>0001_core.sql</code> "
         "defines 12 tables; only <code>audit_log</code> is written by code. <code>decision</code>, "
         "<code>trade_intent</code>, <code>approval</code>, <code>orders</code>, <code>fills</code>, "
         "<code>halt_event</code>, <code>risk_limit_change</code> and <code>instrument</code> "
         "have no persistence path — a core restart loses them. <code>market_tick</code> and "
         "<code>market_bar</code> are unused for a good reason: ParquetArchive already holds "
         "that job, so they should be retired from the DDL, not wired (one system of record, L-3).",
         "grep INSERT/CREATE across src: 2 hits only (audit/log.py, parquet_store.py SELECT)"),
        ("F-3", "neg", "<b>Halt is volatile, so a restart clears an active halt.</b> "
         "<code>HaltManager.__init__</code> builds <code>HaltState()</code> = "
         "<code>scope NONE, active False</code>; nothing re-derives state from the audit chain at "
         "boot. Fail-open on restart is the one behaviour this system must never have.",
         "execution/halt.py:43–56, 90–96"),
        ("F-4", "warn", "The Postgres path is <b>part-paid, not free</b>: portable DDL exists "
         "(TIMESTAMPTZ, NUMERIC never FLOAT, append-only triggers, hypertable conversion "
         "deliberately commented) and SQLAlchemy ≥2.0 is already a runtime dependency — but no "
         "driver is installed (asyncpg, psycopg both absent) and the wiring was Phase 4 work that "
         "never happened.",
         "migrations/0001_core.sql (247 lines) · pyproject dependencies · venv import probe"),
        ("F-5", "ok", "The refusal is well-built: an unrecognised <code>database_url</code> scheme "
         "is refused, not downgraded, and <b>only the scheme</b> enters the error context because a "
         "URL can carry a password.",
         "api/app.py:311–341"),
        ("F-6", "warn", "Cost of the status quo: <code>core</code> waits on <code>db</code> healthy "
         "while nothing reads it — 1.5 GB of a 12 GB free-tier budget and added startup latency, "
         "documented by the compose file itself.",
         "docker-compose.yml KNOWN GAP note"),
    ]
    out = []
    for tag, kind, text, cite in rows:
        out.append(f"<div class='finding {kind}'><b>{tag}</b> — {text}<br>"
                   f"<span class='cite'>evidence: {cite}</span></div>")
    return "".join(out)


def tier_table() -> str:
    rows = [
        ("Governance record (audit chain)", "SQLite, WAL, synchronous=FULL", "per-commit fsync; append-only, hash-chained so a restore is <i>verifiable</i>", "<b>written + tested</b>", "never deleted; retention by partition/archival, never mutation"),
        ("Market time series (ticks/bars/quotes)", "Parquet + zstd, Hive partitions, DuckDB reads", "per-run file; files never rewritten", "<b>written + tested</b>", "D-024 ladder: ticks 30d · 1m 12mo · 5m/1d indefinite"),
        ("Operational state (decisions, intents, approvals, orders, fills, halt, limits)", "SQLite (same file, new tables) — DDL already drafted", "must be durable <b>before</b> acknowledgement (L-2)", "<b>GAP — Stage 6 implements</b>", "audit-linked; reconciliation is the recovery path"),
        ("Instrument master / registry", "SQLite + Valkey hot cache", "registry is the capability source of truth (A-03)", "<b>in-memory + tested logic</b>; persistence Stage 6", "staged activation (D-002), coverage states"),
        ("Intelligence memory (dossiers, evidence refs, sufficiency)", "SQLite tables designed now, writer at stages 8–10", "append-oriented; provenance per item", "<b>planned — schema only</b>", "immutable once cited by a decision"),
        ("Vector recall", "engine UNDECIDED: pgvector (needs Postgres) vs DuckDB VSS ($0, unverified here)", "n/a until chosen", "<b>planned — no engine claimed</b>", "must never be the only record of an evidence claim"),
        ("Ephemeral cache", "Valkey 200mb allkeys-lru", "none by design", "implemented", "loss = slow start, never a wrong number"),
        ("Objects (exports, reports, learning artifacts)", "MinIO", "per-write; content-addressed versions (P-4)", "implemented", "artifacts carry provenance or are rejected"),
    ]
    return ("<table><tr><th>data class</th><th>engine</th><th>durability</th><th>writer today</th>"
            "<th>retention / rule</th></tr>" +
            "".join(f"<tr><td><b>{a}</b></td><td class='cap'>{b}</td><td class='cap'>{c}</td>"
                    f"<td>{d}</td><td class='cap'>{e}</td></tr>" for a, b, c, d, e in rows) +
            "</table>")


def p6_options() -> str:
    rows = [
        ("(a) Wire Postgres as the system of record", "one engine, hypertables, concurrent writers, pgvector available",
         "new driver dependency + untested path; 1.5 GB RAM on a 12 GB host; migration of a working, tested audit store — risk where there is no defect; two stores during cutover (split-brain)",
         "rejected for now — revisit on a measured trigger"),
        ("(b) SQLite-only, <code>db</code> removed", "zero extra RAM; keeps the tested store; simplest",
         "throws away portable DDL and the SQLAlchemy seam already paid for; time-series analytics stay in DuckDB only (acceptable); no path stated for the day a second writer appears",
         "close, but under-specifies the future"),
        ("(b′) <b>RECOMMENDED</b> — SQLite + Parquet declared the single-node system of record; Postgres demoted to an opt-in profile with the seam kept and triggers written down",
         "no new dependency; the two tested engines keep the two hardest jobs; Stage 6 adds operational tables to the same SQLite file; 1.5 GB returned to the budget; Postgres stays one wiring change away (DDL portable, SQLAlchemy present, <code>AuditStore</code> Protocol already the seam)",
         "single-writer ceiling must be respected and <b>measured</b>; vector engine stays undecided until a trigger",
         "<b>R-1</b>"),
        ("(c) Hybrid: SQLite audit + Timescale time series", "each engine does what it is best at",
         "duplicates what Parquet+zstd+DuckDB already does <b>and is tested</b>; two durability stories for one data class; violates one-system-of-record",
         "rejected — Parquet already holds that job"),
    ]
    return ("<table><tr><th>option</th><th>for</th><th>against</th><th>verdict</th></tr>" +
            "".join(f"<tr><td>{a}</td><td class='cap'>{b}</td><td class='cap'>{c}</td>"
                    f"<td class='cap'>{d}</td></tr>" for a, b, c, d in rows) + "</table>")


def triggers() -> str:
    rows = [
        ("T-1", "a second writer process exists (separate ingestion or learning worker)", "SQLite WAL allows one writer; contention would show as SQLITE_BUSY"),
        ("T-2", "operational write throughput hits a measured ceiling", "benchmark at Stage 23 validation, not guessed now"),
        ("T-3", "hypertable partitioning or pgvector is genuinely required", "only when Parquet+DuckDB cannot answer the query"),
        ("T-4", "the deployment leaves a single VM", "multi-node needs a shared store; free tier does not offer HA (5.2 DR)"),
    ]
    return ("<table><tr><th>trigger</th><th>condition (measured, not assumed)</th><th>how it is detected</th></tr>" +
            "".join(f"<tr><td class='mono'>{a}</td><td>{b}</td><td class='cap'>{c}</td></tr>"
                    for a, b, c in rows) + "</table>")


def laws() -> str:
    rows = [
        ("L-1", "<b>Fail-closed boot.</b> On start, halt state is re-derived from the audit chain: the last halt engagement without a matching release ⇒ the system boots HALTED, whatever the in-memory default says. Closes F-3."),
        ("L-2", "<b>Durable before acknowledged.</b> An intent, approval, order or fill is acknowledged to any caller only after its row and its audit entry are committed. No write-ahead gap between \"done\" and \"recorded\"."),
        ("L-3", "<b>One system of record per data class.</b> Never two audit stores, never a cache promoted to truth. Valkey loss must cost latency only."),
        ("L-4", "<b>Portable DDL, forward-only migrations.</b> TIMESTAMPTZ in UTC, NUMERIC never FLOAT, append-only triggers where the record is governance; each migration is idempotent, numbered, and its application is itself an audit event. No destructive migration without owner approval."),
        ("L-5", "<b>Secrets refused at the store boundary.</b> <code>assert_no_secrets</code> runs before any payload is written; a database URL contributes only its scheme to an error context (F-5 keeps this behaviour)."),
        ("L-6", "<b>A restore is a verified restore.</b> Recovery is not complete until <code>/v1/audit/verify</code> passes on the restored chain and reconciliation closes; until then, no new risk."),
    ]
    return ("<table><tr><th>law</th><th>statement</th></tr>" +
            "".join(f"<tr><td class='mono'>{a}</td><td>{b}</td></tr>" for a, b in rows) + "</table>")


BOOT = [
    ("Open store", "SqliteAuditStore(path) · WAL + synchronous=FULL · schema idempotent"),
    ("Verify chain", "AuditLog.verify() · any tamper/gap/reorder ⇒ refuse to serve, alert CRIT"),
    ("Re-derive halt", "scan halt_event / audit for last engage without release ⇒ boot HALTED (L-1)"),
    ("Reconcile open state", "orders in non-terminal states ⇒ UNKNOWN, never auto-resolved; block new risk until closed"),
    ("Apply migrations", "numbered, idempotent, forward-only; each application audited (L-4)"),
    ("Ready", "/readyz only after 1–5 pass; /healthz reports degraded with the specific reason"),
]


def flow(steps: list[tuple[str, str]]) -> str:
    return '<div class="flow">' + "".join(
        f'<div class="fstep"><span class="n">{i}</span><div class="t">{t}</div>'
        f'<div class="w">{w}</div></div>' for i, (t, w) in enumerate(steps, 1)
    ) + "</div>"


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())
    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI · Stage 6.1 Persistent Memory</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 6 of 23 &middot; sub-deliverable 6.1</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
Persistent memory: findings from code, storage tiers, the P-6 ruling</h1>
<div class="ribbon">DESIGN ONLY — no backend changes in 6.1 (backend remains paused at
<code>d9a83fe</code>). Every finding cites the file it was read from. Two of them are safety
gaps and are stated plainly: operational state has DDL but no writer, and a restart currently
clears an active halt. Stage 6 exists to close both.</div>

<h3>Findings<span class="tag">read from code, not assumed</span></h3>
{findings()}

<h3>Storage tiers</h3>
{TIERS}
<div class="card">{tier_table()}</div>

<h3>P-6 — persistence target<span class="tag">carried from Stage 5, ruled here</span></h3>
<div class="card">{p6_options()}</div>
<div class="rec"><div class="t">R-1 — recommendation</div>
Declare <b>SQLite (governance + operational state) and Parquet+zstd/DuckDB (time series) the
single-node system of record</b>. Move TimescaleDB out of <code>core</code>'s
<code>depends_on</code> into an opt-in <code>db</code> profile, returning 1.5 GB to the 12 GB
budget. Keep <code>0001_core.sql</code> as the portable migration target and the
<code>AuditStore</code> Protocol as the seam, so Postgres stays one wiring change away — with the
four trigger conditions below written down and <b>measured</b>, never assumed. Two audit stores at
once is worse than the memory it saves.
</div>
<div class="card" style="margin-top:12px">{triggers()}</div>

<h3>Laws binding on Stage 6 implementation and every stage after</h3>
<div class="card">{laws()}</div>

<h3>Boot sequence under L-1<span class="tag">the fix for F-3, as a flow</span></h3>
{flow(BOOT)}
<div class="branch neg"><b>Failure semantics:</b> a chain that fails verification refuses to serve
rather than serving possibly-wrong state; an order found in a non-terminal state at boot becomes
UNKNOWN and blocks new risk until reconciliation closes it; a boot that cannot determine halt
state boots HALTED.</div>

<h3>Scope of 6.2 (implementation — requires the backend pause to be lifted)</h3>
<div class="card"><table>
<tr><th>item</th><th>what it does</th><th>closes</th></tr>
<tr><td><b>Operational store</b></td><td>SQLite writer for decision, trade_intent, approval, orders, fills, halt_event, risk_limit_change, instrument — reusing the drafted DDL, NUMERIC/TIMESTAMPTZ semantics preserved</td><td class="cap">F-2</td></tr>
<tr><td><b>Durable halt + boot recovery</b></td><td>halt persisted on engage/release; boot re-derives from the audit chain and fails closed</td><td class="cap">F-3, L-1</td></tr>
<tr><td><b>Migration runner</b></td><td>numbered, idempotent, forward-only; application recorded as an audit event</td><td class="cap">L-4</td></tr>
<tr><td><b>Write-ahead discipline</b></td><td>acknowledge only after row + audit entry commit</td><td class="cap">L-2</td></tr>
<tr><td><b>Compose tier fix</b></td><td>db → opt-in profile; core no longer waits on a store it does not read; tiers T1–T3 drop 1.5 GB</td><td class="cap">F-6, R-1</td></tr>
<tr><td><b>Intelligence-memory schema</b></td><td>dossier / evidence_ref / memory_item tables designed, no writer until stages 8–10</td><td class="cap">planned</td></tr>
<tr><td><b>Tests</b></td><td>restart-with-active-halt, crash-between-write-and-audit, chain-verify-on-restore, migration idempotence</td><td class="cap">L-1…L-6</td></tr>
</table></div>
<p class="cap">Vector recall stays undecided: pgvector would pull Postgres back in via T-3, and a
DuckDB VSS path is unverified in this environment. Neither is claimed as available.</p>
<footer>Stage 6.1 &middot; sources: backend/migrations/0001_core.sql, audit/log.py,
execution/halt.py, archive/parquet_store.py, api/app.py, core/config.py, pyproject.toml,
docker-compose.yml, tests/ &middot; 6.2 on approval and unpause.</footer>
</div></body></html>"""
    out = HERE / "stage6-1-persistent-memory.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
