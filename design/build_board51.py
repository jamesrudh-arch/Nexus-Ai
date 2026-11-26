"""Stage 5.1 board: architecture inventory, target context diagram, bounded contexts,
ADRs, honesty statuses. Design only — no code changes.

Run:  backend/.venv/bin/python design/build_board51.py
"""

from __future__ import annotations

import pathlib
import re

from build_board33 import CSS as CSS33
from build_specimen import fonts_css

HERE = pathlib.Path(__file__).resolve().parent
CSS = CSS33 + """
.diag { width: 100%; background: var(--color-surface-panel);
  border: 1px solid var(--color-border-subtle); border-radius: var(--radius-card); }
.diag text { font-family: var(--font-family-sans); }
.diag .mono { font-family: var(--font-family-mono); }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-gutter); }
h3 { font-size: var(--font-size-emphasis); font-weight: var(--font-weight-semibold);
  margin: 40px 0 2px; }
"""

DIAGRAM = """
<svg class="diag" viewBox="0 0 940 560" role="img" aria-label="NEXUS target context diagram">
  <defs>
    <marker id="ar" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
      <path d="M0,0 L8,4 L0,8 z" fill="var(--color-text-muted)"/></marker>
  </defs>
  <g font-size="9" fill="var(--color-text-muted)">
    <text x="16" y="20" class="mono">EXTERNAL · VENUES &amp; DATA (capability registry governs what is advertised)</text>
    <text x="16" y="150" class="mono">OWNER SURFACES</text>
    <text x="250" y="150" class="mono">NEXUS CORE BOUNDARY (single VM first, D-028)</text>
    <text x="250" y="330" class="mono">PLANNED CONTEXTS — dashed until their stage approves them</text>
  </g>
  <!-- venues -->
  <g font-size="10">
    <rect x="16" y="30" width="120" height="34" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="26" y="51" fill="var(--color-text-primary)">binance public</text>
    <rect x="146" y="30" width="100" height="34" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="156" y="51" fill="var(--color-text-primary)">okx v5</text>
    <rect x="256" y="30" width="100" height="34" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="266" y="51" fill="var(--color-feedback-negative-text)">bybit v5 · 403</text>
    <rect x="366" y="30" width="110" height="34" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="376" y="51" fill="var(--color-feedback-warning-text)">dukascopy bi5</text>
  </g>
  <!-- owner surfaces -->
  <g font-size="10">
    <rect x="16" y="160" width="100" height="34" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="26" y="181" fill="var(--color-text-primary)">web (Next.js)</text>
    <rect x="16" y="200" width="100" height="34" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="26" y="221" fill="var(--color-text-primary)">mobile PWA</text>
    <rect x="16" y="240" width="100" height="34" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="26" y="261" fill="var(--color-text-primary)">web push VAPID</text>
  </g>
  <!-- core boundary -->
  <rect x="240" y="160" width="684" height="150" rx="10" fill="none"
        stroke="var(--color-border-strong)"/>
  <g font-size="10">
    <rect x="256" y="176" width="110" height="40" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="266" y="193" fill="var(--color-text-primary)">api gateway</text>
    <text x="266" y="206" class="mono" fill="var(--color-text-muted)">FastAPI · labelled data</text>
    <rect x="386" y="176" width="120" height="40" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="396" y="193" fill="var(--color-text-primary)">ingestion pipeline</text>
    <text x="396" y="206" class="mono" fill="var(--color-text-muted)">integrity gates</text>
    <rect x="526" y="176" width="110" height="40" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="536" y="193" fill="var(--color-text-primary)">data quality</text>
    <text x="536" y="206" class="mono" fill="var(--color-text-muted)">freshness · bar feed</text>
    <rect x="656" y="176" width="110" height="40" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="666" y="193" fill="var(--color-text-primary)">archive</text>
    <text x="666" y="206" class="mono" fill="var(--color-text-muted)">parquet · retention</text>
    <rect x="786" y="176" width="120" height="40" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="796" y="193" fill="var(--color-text-primary)">instrument registry</text>
    <text x="796" y="206" class="mono" fill="var(--color-text-muted)">sessions · coverage</text>
    <rect x="256" y="240" width="150" height="52" rx="6" fill="var(--color-feedback-negative-subtle)"/>
    <text x="266" y="260" fill="var(--color-feedback-negative-text)">risk engine</text>
    <text x="266" y="274" class="mono" fill="var(--color-feedback-negative-text)">deterministic · fail-closed</text>
    <text x="266" y="286" class="mono" fill="var(--color-feedback-negative-text)">no model I/O · authority gate</text>
    <rect x="426" y="240" width="130" height="52" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="436" y="260" fill="var(--color-text-primary)">execution gateway</text>
    <text x="436" y="274" class="mono" fill="var(--color-text-muted)">idempotent · halt</text>
    <text x="436" y="286" class="mono" fill="var(--color-text-muted)">reconciliation</text>
    <rect x="576" y="240" width="120" height="52" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="586" y="260" fill="var(--color-text-primary)">event bus</text>
    <text x="586" y="274" class="mono" fill="var(--color-text-muted)">spine · NATS JetStream</text>
    <text x="586" y="286" class="mono" fill="var(--color-text-muted)">in prod (Phase 2 decision)</text>
    <rect x="716" y="240" width="90" height="52" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="726" y="260" fill="var(--color-text-primary)">audit chain</text>
    <text x="726" y="274" class="mono" fill="var(--color-text-muted)">hash-chained</text>
    <text x="726" y="286" class="mono" fill="var(--color-text-muted)">append-only</text>
    <rect x="826" y="240" width="82" height="52" rx="6" fill="var(--color-surface-elevated)"/>
    <text x="836" y="260" fill="var(--color-text-primary)">secrets</text>
    <text x="836" y="274" class="mono" fill="var(--color-text-muted)">vault-only</text>
    <text x="836" y="286" class="mono" fill="var(--color-text-muted)">redactor</text>
  </g>
  <!-- planned contexts -->
  <g font-size="10">
    <rect x="256" y="344" width="150" height="44" rx="6" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="266" y="362" fill="var(--color-feedback-intelligence-text)">intelligence / research</text>
    <text x="266" y="376" class="mono" fill="var(--color-text-muted)">stages 8–10</text>
    <rect x="426" y="344" width="130" height="44" rx="6" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="436" y="362" fill="var(--color-feedback-intelligence-text)">verification engine</text>
    <text x="436" y="376" class="mono" fill="var(--color-text-muted)">stage 11 · 3 gates</text>
    <rect x="576" y="344" width="120" height="44" rx="6" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="586" y="362" fill="var(--color-feedback-intelligence-text)">strategy lab runtime</text>
    <text x="586" y="376" class="mono" fill="var(--color-text-muted)">stage 12</text>
    <rect x="716" y="344" width="90" height="44" rx="6" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="726" y="362" fill="var(--color-feedback-intelligence-text)">learning</text>
    <text x="726" y="376" class="mono" fill="var(--color-text-muted)">stage 18</text>
    <rect x="826" y="344" width="82" height="44" rx="6" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="836" y="362" fill="var(--color-feedback-intelligence-text)">notify</text>
    <text x="836" y="376" class="mono" fill="var(--color-text-muted)">stage 19</text>
    <rect x="256" y="404" width="150" height="44" rx="6" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="266" y="422" fill="var(--color-feedback-intelligence-text)">portfolio intelligence</text>
    <text x="266" y="436" class="mono" fill="var(--color-text-muted)">stage 16</text>
    <rect x="426" y="404" width="130" height="44" rx="6" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="436" y="422" fill="var(--color-feedback-intelligence-text)">paper trading sim</text>
    <text x="436" y="436" class="mono" fill="var(--color-text-muted)">stage 15 · labelled</text>
    <rect x="576" y="404" width="120" height="44" rx="6" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="586" y="422" fill="var(--color-feedback-intelligence-text)">ops &amp; recovery</text>
    <text x="586" y="436" class="mono" fill="var(--color-text-muted)">stage 20</text>
    <rect x="716" y="404" width="192" height="44" rx="6" fill="none"
          stroke="var(--color-feedback-intelligence-graphic)" stroke-dasharray="4 3"/>
    <text x="726" y="422" fill="var(--color-feedback-intelligence-text)">security hardening · observability UI</text>
    <text x="726" y="436" class="mono" fill="var(--color-text-muted)">stages 21–22</text>
  </g>
  <!-- edges -->
  <g stroke="var(--color-text-muted)" stroke-width="1" fill="none">
    <path d="M76,64 V160" marker-end="url(#ar)"/>
    <path d="M196,64 V120 H446 V176" marker-end="url(#ar)"/>
    <path d="M411,64 V120 H446" />
    <path d="M116,177 H256" marker-end="url(#ar)"/>
    <path d="M116,217 H200 V266 H256" marker-end="url(#ar)"/>
    <path d="M506,196 H526" marker-end="url(#ar)"/>
    <path d="M636,196 H656" marker-end="url(#ar)"/>
    <path d="M366,196 H386" marker-end="url(#ar)"/>
    <path d="M446,216 V240" marker-end="url(#ar)"/>
    <path d="M406,266 H426" marker-end="url(#ar)"/>
    <path d="M556,266 H576" marker-end="url(#ar)"/>
    <path d="M696,266 H716" marker-end="url(#ar)"/>
  </g>
  <g font-size="8.5" class="mono" fill="var(--color-text-muted)">
    <text x="300" y="480">solid = implemented &amp; tested (Phase 2–4, gate 930) · dashed = planned, stage-numbered</text>
    <text x="300" y="494">risk engine draws no data from model layers; verification gates sit between intelligence and execution (stage 11)</text>
    <text x="300" y="508">every write emits an event; every event lands in the audit chain; api exposes only real or labelled-simulated values</text>
  </g>
</svg>"""


def contexts_table() -> str:
    rows = [
        ("Ingestion", "venue adapters, integrity gates, throttle backoff", "ingestion/* · <b>implemented+tested</b>", "async in, sync out per poll", "Stage 7 extends provider-by-provider"),
        ("Data quality & archive", "freshness gating, bar building, parquet retention", "data/*, archive/* · <b>implemented+tested</b>", "sync", "Stage 7 adds per-market depth"),
        ("Instrument master", "canonical registry, sessions, coverage states", "instruments/* · <b>implemented+tested</b>", "sync, cached", "source of truth for the capability registry"),
        ("Risk", "deterministic limits, fail-closed, live-authority gate", "risk/* · <b>implemented+tested</b>", "sync call, no I/O to models", "Stage 13 deepens portfolio risk"),
        ("Execution governance", "intents, idempotency, halt, reconciliation", "execution/* · <b>implemented+tested</b>", "sync + events", "Stage 14 wires venues, Stage 17 management"),
        ("Audit & events", "hash-chained log, event bus spine", "audit/*, events/* · <b>implemented+tested</b>", "async spine", "NATS JetStream in production (Phase 2 ADR)"),
        ("API surface", "status, health, audit verification only (today)", "api/* · <b>implemented+tested</b>", "sync HTTP", "Stage 22 expands to dashboard contracts"),
        ("Observability & secrets", "structured logs, Prometheus metrics, vault+redactor", "observability/*, secrets/* · <b>implemented+tested</b>", "cross-cutting", "Stage 21 hardening, $0 stack"),
        ("Intelligence / research", "agents, dossiers, memory, knowledge sufficiency", "<i>planned</i>", "async on bus", "Stages 6, 8–10"),
        ("Verification engine", "three gates between thesis and execution", "<i>planned</i>", "sync gate in decision path", "Stage 11"),
        ("Strategy lab / learning", "backtests, promotion gates, versioned learning + rollback", "<i>planned</i>", "batch + events", "Stages 12, 18"),
        ("Portfolio intelligence / notify / ops", "attribution, reporting, recovery runbooks", "<i>planned</i>", "async", "Stages 16, 19, 20"),
    ]
    return ("<table><tr><th>bounded context</th><th>responsibility</th><th>module · honesty status</th>"
            "<th>coupling</th><th>roadmap</th></tr>" +
            "".join(f"<tr><td><b>{a}</b></td><td>{b}</td><td>{c}</td><td class='cap'>{d}</td>"
                    f"<td class='cap'>{e}</td></tr>" for a, b, c, d, e in rows) + "</table>")


def adrs() -> str:
    rows = [
        ("A-01", "Event spine: in-process bus now, NATS JetStream in production (Phase 2 decision, bus.py). Every state change emits an event; consumers are idempotent.", "existing — extended, not replaced"),
        ("A-02", "Risk engine isolation: pure deterministic functions over explicit state; no network, no model layer I/O; confidence values are inputs it may ignore but never requirements it satisfies. Fail-closed on any missing input.", "existing — formalised as an architectural law"),
        ("A-03", "Capability registry single source: instruments.registry owns coverage states; no screen, API response or report may advertise a market the registry does not mark supported/connected/verified.", "existing — extended to API contracts"),
        ("A-04", "Environment state machine (core.environment) is the only gate between intent and execution; live authority DENIED by default; promotion is an owner decision with audit entry, never a code path.", "existing — extended"),
        ("A-05", "Audit chain is the spine of record: approvals, decisions, orders, fills, config changes hash-chained; reconciliation diffs are audit events.", "existing — extended"),
        ("A-06", "API honesty contract: responses carry data status (live/delayed/stale/unavailable/simulated) per field group; simulated values are labelled at the wire, not at the UI.", "new — Stage 5"),
        ("A-07", "Deployment: single VM, docker-compose, modules-not-microservices until a measured scaling need; $0 stack (D-019, D-028); observability self-hosted Prometheus + structured logs.", "existing — formalised"),
        ("A-08", "Intelligence layers (stages 8–10, 18) connect to execution ONLY through the verification engine's three gates (stage 11); no agent holds an execution credential.", "new — Stage 5 law"),
    ]
    return ("<table><tr><th>ADR</th><th>decision</th><th>status</th></tr>" +
            "".join(f"<tr><td class='mono'>{a}</td><td>{b}</td><td class='cap'>{c}</td></tr>"
                    for a, b, c in rows) + "</table>")


def honesty_table() -> str:
    rows = [
        ("core, audit, events, risk, execution, ingestion adapters, data, archive, instruments, observability, secrets, api", "implemented + tested (gate 930/0/0/2; ruff+mypy strict clean)", "Phase 2–4 CI"),
        ("okx v5 adapter", "connected + live-verified twice", "Phase 4 runs"),
        ("binance vision adapter", "connected + verified end-to-end (µs timestamp defect found & fixed)", "Phase 3–4"),
        ("bybit v5 adapter", "connected-but-untested from hosted runners (403 geo-block); code path exercised only against public docs", "Phase 4 evidence"),
        ("dukascopy adapter", "connected; real 25,761-byte bi5 downloaded; layout UNVERIFIED (LAYOUT_VERIFIED=False); 503 throttling characterised", "Phase 4 evidence"),
        ("NATS JetStream", "planned for production; in-process bus tested today", "Phase 2 ADR"),
        ("intelligence, verification, lab, learning, notify, ops, portfolio intelligence", "planned — stage-numbered, nothing simulated to look built", "this register"),
    ]
    return ("<table><tr><th>component</th><th>honesty status (§26 vocabulary)</th><th>evidence</th></tr>" +
            "".join(f"<tr><td class='mono'>{a}</td><td>{b}</td><td class='cap'>{c}</td></tr>"
                    for a, b, c in rows) + "</table>")


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())
    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI · Stage 5.1 Target Architecture</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 5 of 23 &middot; sub-deliverable 5.1</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
Target architecture: inventory, boundaries, decisions, honesty statuses</h1>
<div class="ribbon">DESIGN ONLY — no code changes in Stage 5.1. Solid boxes are implemented and
tested (Phase 2–4, gate 930); dashed boxes are planned contexts with their stage numbers. Nothing
planned is drawn as built; nothing built is drawn as verified beyond its evidence.</div>

<h3>Context diagram</h3>
{DIAGRAM}

<h3>Bounded contexts &amp; ownership</h3>
<div class="card">{contexts_table()}</div>

<h3>Architecture decision records</h3>
<div class="card">{adrs()}</div>
<p class="cap">A-02 and A-08 are the two laws the mandate cannot compromise: the risk engine is
deterministic and fail-closed with no model I/O, and intelligence reaches execution only through
the verification gates. Both are stated as architecture so Stages 10–13 inherit them as tests.</p>

<h3>Honesty statuses (§26 vocabulary)</h3>
<div class="card">{honesty_table()}</div>
<p class="cap">The bybit and dukascopy rows are the important ones: geo-blocked and
layout-unverified are stated as conditions with evidence, never painted green. Stage 7 retires
them one market at a time.</p>
<footer>Stage 5.1 &middot; inventory from backend/src/nexus (14 packages, 49 modules) + docs/04–06
&middot; 5.2 (pipelines, deployment topology, DR) next on approval.</footer>
</div></body></html>"""
    out = HERE / "stage5-1-target-architecture.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
