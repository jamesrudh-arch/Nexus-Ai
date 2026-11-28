"""Stage 5.2 board: pipeline designs, deployment topology, memory budget, DR.

Design only. Topology describes the real docker-compose.yml (caps, profiles, networks read from
the file), not an imagined one; the TimescaleDB gap the compose file itself documents is carried
to Stage 6 as proposal P-6 rather than silently resolved here.

Run:  backend/.venv/bin/python design/build_board52.py
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
.planned { opacity: 0.95; }
h3 { font-size: var(--font-size-emphasis); font-weight: var(--font-weight-semibold);
  margin: 40px 0 2px; }
h3 .tag { font-family: var(--font-family-mono); font-size: var(--font-size-caption);
  font-weight: var(--font-weight-regular); color: var(--color-text-muted); margin-left: 8px; }
.budget td.num, .budget th.num { text-align: right; font-variant-numeric: tabular-nums; }
.law { border-left: 3px solid var(--color-border-strong); padding: 8px 12px;
  background: var(--color-surface-elevated); border-radius: 0 var(--radius-card) var(--radius-card) 0;
  font-size: var(--font-size-caption); line-height: 1.5; margin-top: 10px; }
"""


def flow(steps: list[tuple[str, str, str]]) -> str:
    """Reuse the approved 4.2 step vocabulary: number, title, wiring."""
    return '<div class="flow">' + "".join(
        f'<div class="fstep"><span class="n">{i}</span><div class="t">{t}</div>'
        f'<div class="w">{w}</div></div>'
        for i, (t, w) in enumerate(steps, 1)
    ) + "</div>"


def block(title: str, tag: str, steps, failure: str, law: str, neg: bool = False) -> str:
    cls = "branch neg" if neg else "branch"
    return (f"<h3>{title}<span class='tag'>{tag}</span></h3>{flow(steps)}"
            f"<div class='{cls}'><b>Failure semantics:</b> {failure}</div>"
            f"<div class='law'>{law}</div>")


# ---------------------------------------------------------------- P-1 ingestion
P1 = [
    ("Adapter poll", "ingestion/{okx,binance_vision,bybit,dukascopy}.py · injected Transport · throttle backoff on 429/503"),
    ("Integrity gates", "source-specific: timestamp sanity, monotonic sequence, checksum, layout. dukascopy bi5 stays LAYOUT_VERIFIED=False"),
    ("Quality gate", "data/freshness.DataQualityGate → GateResult; <b>new_risk_allowed</b> is the binding flag, not ok"),
    ("Report", "PipelineReport.reject(reason) / finish(); resolution_rate + rejection_rate computed, to_audit_payload()"),
    ("Persist", "IngestionPipeline.persist() → archive/parquet_store (separate volume) + store write; idempotent by (source, symbol, ts)"),
    ("Emit", "EventEnvelope on the bus (topic-versioned); NatsEventBus <b>raises</b> EventPublishError rather than dropping"),
    ("Record", "audit/log append-only hash chain; report payload audited with its rejection counts"),
]
P1_FAIL = ("a rejected record is counted and reasoned, never silently discarded; an unverifiable "
           "layout leaves the source at UNVERIFIED so nothing downstream treats it as trusted; a "
           "bus failure raises to the caller — the pipeline stops rather than continuing on an "
           "unrecorded event; a 503/429 backs off and the poll is reported as incomplete, not as "
           "zero data.")
P1_LAW = ("Law: data that cannot be proven is labelled, never assumed. DataStatus "
          "(LIVE · DELAYED · STALE · UNAVAILABLE · FAULT) travels with the record to the API "
          "per A-06.")

# ---------------------------------------------------------------- P-2 decision
P2 = [
    ("Candidate thesis", "intelligence dossier (stage 9) · evidence set + uncertainty · ABSTAIN is the default record"),
    ("Knowledge sufficiency", "stage 10 · does the dossier meet the sufficiency bar for this instrument/session? planned"),
    ("Verification gates", "stage 11 · three gates between thesis and execution (A-08) · planned"),
    ("Immutable intent", "execution/intent.py · frozen slots dataclass · digest-bound approval; material change invalidates"),
    ("Authority gate", "risk/authority.py · 11 independent fields · any missing/unknown/false ⇒ DENIED · no override flag"),
    ("Risk sizing", "risk/engine.py · deterministic max_loss / stop_distance_per_unit · reductions only · fail-closed"),
    ("Route by environment", "core/environment.py · SHADOW ⇒ paper simulator (labelled) · LIVE only with granted authority"),
]
P2_FAIL = ("no gate can be satisfied by a confidence value — confidence is an input the risk "
           "engine may ignore; a missing input denies; an expired or changed intent invalidates "
           "the approval and re-asks (4.1 friction ladder); ABSTAIN is a complete outcome, not an "
           "error state.")
P2_LAW = ("Law (A-02 + A-08): the path from intelligence to execution passes every gate in order "
          "and the risk engine sees no model I/O. Steps 2–3 are planned and drawn dashed in the "
          "diagram until Stage 11 delivers them.")

# ---------------------------------------------------------------- P-3 execution
P3 = [
    ("Idempotency key", "core/ids.py · replay of the same key returns the same outcome, never a second order"),
    ("Halt scope check", "execution/halt.HaltManager · widest_scope() monotonic · ALL_TRADING allows risk-reducing only"),
    ("Gateway transmit", "execution/gateway.py · venue credential from secrets/ only · refused unless authority GRANTED"),
    ("Order state machine", "execution/orders.py · <b>UNKNOWN never auto-resolved</b> · every transition an event"),
    ("Fill / partial ack", "venue-reported only; no synthetic fills, no invented Greeks (§8 of docs/10)"),
    ("Reconciliation", "diff venue truth vs local state · mismatch blocks new risk until closed · diff is an audit event"),
    ("Audit + notify", "append-only chain entry · alert on failure with a delivery-failure alert of its own"),
]
P3_FAIL = ("an UNKNOWN order halts and invokes the unknown-order policy — the system never guesses "
           "a fill; a partial venue acknowledgement is treated as unknown, not as success; a "
           "reconciliation mismatch blocks new risk before any new decision is taken; a halt "
           "engages at the risk engine so it holds even if the UI is unreachable.")
P3_LAW = ("Law: idempotent in, reconciled out. Every transmission has one outcome and one record; "
          "the venue is the source of truth for fills.")

# ---------------------------------------------------------------- P-4 learning
P4 = [
    ("Outcome events", "fills, decisions, abstentions, incidents on the bus · append-only dataset"),
    ("Versioned artifact", "stage 18 · model/params/prompt as a content-addressed version with provenance"),
    ("Promotion gate", "must beat the incumbent on owner-set criteria + pass the regression suite · no auto-promote"),
    ("Staged rollout", "shadow first, then paper, then the environment state machine · one stage at a time"),
    ("Rollback", "first-class path: revert to the previous version, audit the revert and its reason"),
    ("Observe", "stage 22 dashboards show incumbent vs candidate; divergence is an incident, not a metric"),
]
P4_FAIL = ("a candidate that cannot be reproduced from its version is rejected outright; a "
           "promotion without an owner-set criterion is refused; rollback never requires the "
           "failing version to be diagnosable first — reverting is always available.")
P4_LAW = ("Law: learning is controlled or it is off. Planned context, drawn dashed; Stage 18 owns "
          "the implementation, Stage 5 only fixes these constraints.")

# ---------------------------------------------------------------- topology
TOPOLOGY = """
<svg class="diag" viewBox="0 0 940 470" role="img"
     aria-label="Deployment topology: single VM, Caddy entry, internal bridge, profiles">
  <defs>
    <marker id="ar2" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7"
            orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="var(--color-text-muted)"/></marker>
  </defs>
  <g font-size="9" class="mono" fill="var(--color-text-muted)">
    <text x="16" y="18">PUBLIC · 80/443 ONLY</text>
    <text x="150" y="18">HOST · Oracle Always Free A1 · 2 OCPU / 12 GB (allowance halved 15 Jun 2026) · 200 GB disk · arm64</text>
  </g>
  <!-- public -->
  <g font-size="10">
    <rect x="16" y="30" width="110" height="40" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="26" y="47" fill="var(--color-text-primary)">owner browser</text>
    <text x="26" y="61" class="mono" fill="var(--color-text-muted)">web + mobile PWA</text>
    <rect x="16" y="82" width="110" height="34" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="26" y="103" fill="var(--color-text-primary)">venues (egress)</text>
  </g>
  <!-- host boundary -->
  <rect x="142" y="30" width="782" height="392" rx="12" fill="none" stroke="var(--color-border-strong)"/>
  <!-- caddy -->
  <g font-size="10">
    <rect x="158" y="46" width="120" height="52" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="168" y="66" fill="var(--color-text-primary)">caddy 2-alpine</text>
    <text x="168" y="80" class="mono" fill="var(--color-text-muted)">sole public entry</text>
    <text x="168" y="92" class="mono" fill="var(--color-text-muted)">128M · Let's Encrypt</text>
  </g>
  <!-- internal network -->
  <rect x="300" y="40" width="608" height="220" rx="10" fill="none"
        stroke="var(--color-border-subtle)" stroke-dasharray="5 3"/>
  <text x="312" y="56" class="mono" font-size="9" fill="var(--color-text-muted)">
    nexus-internal (bridge) — nothing else is published; core exposes 8000 internally only</text>
  <g font-size="10">
    <rect x="312" y="66" width="140" height="52" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="322" y="86" fill="var(--color-text-primary)">core (nexus-core:0.2.0)</text>
    <text x="322" y="100" class="mono" fill="var(--color-text-muted)">1024M · non-root</text>
    <text x="322" y="112" class="mono" fill="var(--color-feedback-negative-text)">LIVE off in code</text>
    <rect x="468" y="66" width="130" height="52" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="478" y="86" fill="var(--color-text-primary)">nats 2-alpine</text>
    <text x="478" y="100" class="mono" fill="var(--color-text-muted)">256M · JetStream</text>
    <text x="478" y="112" class="mono" fill="var(--color-text-muted)">-m 8222 healthz</text>
    <rect x="614" y="66" width="130" height="52" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="624" y="86" fill="var(--color-text-primary)">db timescaledb pg16</text>
    <text x="624" y="100" class="mono" fill="var(--color-text-muted)">1536M · 0001_core.sql</text>
    <text x="624" y="112" class="mono" fill="var(--color-feedback-warning-text)">healthy, unread — P-6</text>
    <rect x="760" y="66" width="132" height="52" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="770" y="86" fill="var(--color-text-primary)">valkey 8 + minio</text>
    <text x="770" y="100" class="mono" fill="var(--color-text-muted)">256M + 512M</text>
    <text x="770" y="112" class="mono" fill="var(--color-text-muted)">cache · objects</text>
    <rect x="312" y="132" width="140" height="52" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="322" y="152" fill="var(--color-text-primary)">SQLite audit store</text>
    <text x="322" y="166" class="mono" fill="var(--color-text-muted)">WAL · synchronous=FULL</text>
    <text x="322" y="178" class="mono" fill="var(--color-text-muted)">only implemented store</text>
    <rect x="468" y="132" width="130" height="52" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="478" y="152" fill="var(--color-text-primary)">archive-data vol</text>
    <text x="478" y="166" class="mono" fill="var(--color-text-muted)">parquet ticks/bars</text>
    <text x="478" y="178" class="mono" fill="var(--color-text-muted)">D-024 ladder</text>
    <rect x="614" y="132" width="278" height="52" rx="6" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="624" y="152" fill="var(--color-feedback-intelligence-text)">profile: observability</text>
    <text x="624" y="166" class="mono" fill="var(--color-text-muted)">prometheus 512M · grafana 256M · loki 512M</text>
    <text x="624" y="178" class="mono" fill="var(--color-text-muted)">uptime-kuma 256M = +1536M</text>
    <rect x="312" y="196" width="580" height="52" rx="6" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="322" y="216" fill="var(--color-feedback-intelligence-text)">profile: ai — ollama (commented out today)</text>
    <text x="322" y="230" class="mono" fill="var(--color-text-muted)">5120M cap · quantized 7B at ~5–12 tok/s on A1 CPU · no GPU on free tier</text>
    <text x="322" y="242" class="mono" fill="var(--color-feedback-negative-text)">never receives credentials, positions or order authority (A-08)</text>
  </g>
  <!-- host-level -->
  <g font-size="10">
    <rect x="158" y="278" width="200" height="52" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="168" y="298" fill="var(--color-text-primary)">volumes (host-backed)</text>
    <text x="168" y="312" class="mono" fill="var(--color-text-muted)">db · nats · minio · core · archive</text>
    <text x="168" y="324" class="mono" fill="var(--color-text-muted)">caddy · prometheus · grafana · loki · kuma</text>
    <rect x="374" y="278" width="200" height="52" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="384" y="298" fill="var(--color-text-primary)">.env (host, never committed)</text>
    <text x="384" y="312" class="mono" fill="var(--color-text-muted)">:?-required vars refuse to start</text>
    <text x="384" y="324" class="mono" fill="var(--color-text-muted)">gitleaks + Trivy in CI</text>
    <rect x="590" y="278" width="150" height="52" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="600" y="298" fill="var(--color-text-primary)">GitHub Actions CI</text>
    <text x="600" y="312" class="mono" fill="var(--color-text-muted)">free tier · arm64+amd64</text>
    <text x="600" y="324" class="mono" fill="var(--color-text-muted)">compose validation</text>
    <rect x="756" y="278" width="136" height="52" rx="6" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="766" y="298" fill="var(--color-feedback-intelligence-text)">off-VM backup target</text>
    <text x="766" y="312" class="mono" fill="var(--color-text-muted)">planned · unverified</text>
    <text x="766" y="324" class="mono" fill="var(--color-text-muted)">Stage 20 drill</text>
  </g>
  <!-- startup tiers -->
  <g font-size="9.5" class="mono" fill="var(--color-text-muted)">
    <text x="158" y="356">STARTUP TIERS (bring up in order, stop at the tier the host can hold):</text>
    <text x="158" y="372" fill="var(--color-text-secondary)">T1 core+caddy 1.15 GB · T2 +nats/cache/minio 2.18 GB · T3 +db 3.71 GB · T4 +observability 5.25 GB · T5 +ollama 10.37 GB</text>
    <text x="158" y="388" fill="var(--color-feedback-negative-text)">budget law: T4 and T5 are mutually exclusive with headroom on a 12 GB host — never both while trading is armed</text>
    <text x="158" y="404">core depends_on db+nats healthy; db currently costs 1.5 GB for a store nothing reads (P-6 to Stage 6)</text>
  </g>
  <!-- edges -->
  <g stroke="var(--color-text-muted)" stroke-width="1" fill="none">
    <path d="M126,50 H158" marker-end="url(#ar2)"/>
    <path d="M278,72 H312" marker-end="url(#ar2)"/>
    <path d="M452,92 H468" marker-end="url(#ar2)"/>
    <path d="M598,92 H614" marker-end="url(#ar2)"/>
    <path d="M744,92 H760" marker-end="url(#ar2)"/>
    <path d="M382,118 V132" marker-end="url(#ar2)"/>
    <path d="M126,99 H200 V118 H312" marker-end="url(#ar2)"/>
    <path d="M258,278 V262" marker-end="url(#ar2)"/>
  </g>
</svg>"""


def budget_table() -> str:
    rows = [
        ("core", "1024M", "T1", "FastAPI + risk + execution + audit; SQLite store"),
        ("nats", "256M", "T2", "JetStream spine; -m 8222 is load-bearing (defect 36, docs/06 §2)"),
        ("cache (valkey)", "256M", "T2", "rate limits + hot state; allkeys-lru at 200mb"),
        ("minio", "512M", "T2", "object storage for reports/exports"),
        ("db (timescaledb)", "1536M", "T3", "healthy + waited-on, unread today — P-6"),
        ("caddy", "128M", "T1", "sole public entry; TLS"),
        ("observability profile", "1536M", "T4", "prometheus 512 + grafana 256 + loki 512 + kuma 256"),
        ("ollama (ai profile)", "5120M", "T5", "commented out; no GPU; never holds credentials"),
    ]
    tot = ("<tr><td><b>T4 total</b></td><td class='num'><b>5.25 GB</b></td><td class='cap'>T1–T4</td>"
           "<td class='cap'>of 12 GB — leaves OS + page cache headroom</td></tr>")
    return ("<table class='budget'><tr><th>service</th><th class='num'>cap</th><th>tier</th>"
            "<th>note</th></tr>" +
            "".join(f"<tr><td class='mono'>{a}</td><td class='num mono'>{b}</td><td class='cap'>{c}</td>"
                    f"<td class='cap'>{d}</td></tr>" for a, b, c, d in rows) + tot + "</table>")


def dr_table() -> str:
    rows = [
        ("Audit chain (SQLite, WAL, synchronous=FULL)", "single node; append-only + hash-chained so a restore is verifiable, not just copied",
         "≤1 transaction (durability is per-commit by design)", "minutes to remount; verification via /v1/audit/verify", "<b>implemented + tested</b> (Phase 2)"),
        ("Event stream (JetStream on nats-data)", "durable stream; consumers idempotent by event_id", "≤ stream flush interval", "restart replays from store_dir", "<b>planned in production</b>; in-memory bus tested"),
        ("Market archive (parquet, archive-data)", "separate volume, D-024 ladder: ticks 30d · 1m 12mo · 5m/1d indefinite", "≤ last completed run", "re-derivable from public venues where retention allows", "<b>implemented + tested</b> (Phase 3)"),
        ("Configuration (.env, SOPS+age / OpenBao)", "never committed; :?-required vars refuse to boot; secrets backend fails closed until Phase 8", "manual rotation cadence", "rebuild from encrypted copy", "<b>implemented</b>; off-VM copy <b>unverified</b>"),
        ("Off-VM backup copy", "no backup has ever been restored in this project; candidate targets (free-tier object storage, restic to a $0 bucket) are unproven here", "unknown until a drill sets it", "unknown until a drill sets it", "<b>DESIGNED — UNTESTED</b>; Stage 20 gate"),
        ("Whole VM", "free tier has no HA and no second node — stated, not papered over", "n/a", "rebuild image + restore volumes; trading stays stopped until reconciliation closes", "<b>single point of failure</b>"),
    ]
    return ("<table><tr><th>store / scope</th><th>what survives</th><th>RPO (design)</th>"
            "<th>RTO (design)</th><th>honesty status</th></tr>" +
            "".join(f"<tr><td>{a}</td><td>{b}</td><td class='cap'>{c}</td><td class='cap'>{d}</td>"
                    f"<td>{e}</td></tr>" for a, b, c, d, e in rows) + "</table>")


def failsafes() -> str:
    rows = [
        ("Disk watermark", "retention runs <b>before</b> the watermark fail-safe, not after (compose comment); RetentionPlan.is_safe + refusals recorded; archive-data is the largest consumer on 200 GB", "implemented (archive/retention.py)"),
        ("Memory ceiling", "per-service caps total 5,248 MB (5.25 GB) at T4; core is capped so a runaway cannot starve the audit store; ollama is opt-in at T5", "compose caps + budget law"),
        ("Unknown order", "never auto-resolved; UNKNOWN halts and invokes the unknown-order policy", "implemented (execution/orders.py)"),
        ("Halt", "widest_scope() is monotonic — a halt never narrows by accident; engages at the risk engine, not the UI", "implemented (execution/halt.py)"),
        ("Data quality", "new_risk_allowed is binding; FAULT covers future timestamps, crossed books, clock skew", "implemented (data/freshness.py)"),
        ("Authority", "11 independent gates; any missing/unknown/false denies; no override flag, no debug bypass", "implemented (risk/authority.py)"),
        ("Event loss", "NatsEventBus raises EventPublishError instead of dropping — the pipeline stops rather than continuing unrecorded", "implemented (events/bus.py)"),
        ("Secrets", "backend fails closed until Phase 8; redactor refuses secret material in logs and audit", "implemented (secrets/)"),
        ("CI", "gitleaks + Trivy + ruff + mypy strict + pytest + arm64/amd64 build + compose validation on free GitHub Actions", "implemented (.github/workflows)"),
    ]
    return ("<table><tr><th>fail-safe</th><th>behaviour</th><th>status</th></tr>" +
            "".join(f"<tr><td><b>{a}</b></td><td>{b}</td><td class='cap'>{c}</td></tr>"
                    for a, b, c in rows) + "</table>")


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())
    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI · Stage 5.2 Pipelines, Topology &amp; DR</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 5 of 23 &middot; sub-deliverable 5.2 (final batch)</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
Pipelines, deployment topology, memory budget, disaster recovery</h1>
<div class="ribbon">DESIGN ONLY. The topology below is read from the committed
<code>docker-compose.yml</code> — real caps, real profiles, real network, and the gap that file
documents itself (TimescaleDB healthy but unread) carried to Stage 6 as <b>P-6</b> rather than
resolved by assertion. Nothing here claims a backup has been restored: none has.</div>

<h3>Four pipelines<span class="tag">each stage names a real module or a stage number</span></h3>
{block("P-1 Ingestion integrity", "implemented · Phase 3–4", P1, P1_FAIL, P1_LAW)}
{block("P-2 Decision → verification → authority", "mixed: gates planned (stages 10–11), intent/authority/risk implemented", P2, P2_FAIL, P2_LAW)}
{block("P-3 Idempotent execution &amp; reconciliation", "governance implemented · venue wiring Stage 14", P3, P3_FAIL, P3_LAW, neg=True)}
{block("P-4 Controlled learning", "planned · Stage 18", P4, P4_FAIL, P4_LAW)}

<h3>Deployment topology</h3>
{TOPOLOGY}

<h3>Memory budget (12 GB free-tier host)</h3>
<div class="card">{budget_table()}</div>
<p class="cap">Caps are the committed compose values. T5 (ollama) is commented out in the file and
stays that way until the core stack is stable on the host; a quantized 7B at 5–12 tok/s on A1 CPU
is a research aid, never a path to order authority (A-08).</p>

<h3>Fail-safes</h3>
<div class="card">{failsafes()}</div>

<h3>Disaster recovery on a $0 single VM</h3>
<div class="card">{dr_table()}</div>
<div class="law"><b>The DR claim, stated plainly:</b> the objective is <i>resume monitoring and
reconcile</i>, not <i>keep trading</i>. VM loss stops trading safely — fail-closed on unknown,
UNKNOWN never auto-resolved, halt engages in the risk engine, reconciliation must close before new
risk. There is no HA on the free tier and this document does not pretend otherwise; redundancy is
replaced by determinism and by an audit chain that can prove what happened.</div>
<footer>Stage 5.2 &middot; sources: docker-compose.yml, infra/, backend/src/nexus (events,
ingestion, data, risk, execution, archive), docs/04–06 &middot; Stage 5 closes for stage-level
approval after this batch.</footer>
</div></body></html>"""
    out = HERE / "stage5-2-pipelines-topology-dr.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
