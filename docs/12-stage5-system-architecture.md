# 12 — Stage 5: System Architecture

Status: **IN PROGRESS**, sub-deliverables: 5.1 inventory + target architecture (this document §1,
board `design/stage5-1-target-architecture.html`) → 5.2 pipelines, deployment topology, DR.
Design only: Stage 5 writes no production code. Started after Stage 4 stage-level approval
(D-039). Stages 6–23 untouched.

Binding inputs: docs/04–06 (Phase 2–4 evidence), backend/src/nexus (14 packages, 49 modules),
D-019 ($0 stack), D-028 (VM-first), mandate laws (fail-closed risk, verification gates,
idempotent execution, capability registry honesty, §26 statuses), D-039 flow laws.

---

## 1. Sub-deliverable 5.1 — Inventory, boundaries, ADRs, honesty (BUILT — AWAITING REVIEW)

### 1.1 Inventory (research)

Phase 2–4 already implement, tested at gate 930/0/0/2 with ruff + mypy strict clean:
hash-chained append-only audit (audit/), event bus with NATS JetStream slated for production
(events/), deterministic fail-closed risk engine + live-authority gate (risk/), execution
governance with intents, idempotency, halt and reconciliation (execution/), venue adapters with
integrity gates and throttle backoff (ingestion/: binance_vision, okx, bybit, dukascopy),
freshness gating + records (data/), parquet archive + retention (archive/), canonical instrument
master + sessions + coverage (instruments/), structured logs + Prometheus metrics
(observability/), vault-only secrets + tested redactor (secrets/), FastAPI surface exposing
status/health/audit-verification only (api/), core primitives (config, environment state machine,
errors, ids, aware-UTC time).

Stage 5 therefore designs the **target** architecture: the same foundation extended by planned
contexts (intelligence/research, verification engine, strategy-lab runtime, controlled learning,
portfolio intelligence, notifications, ops/recovery), each dashed and stage-numbered until its
stage approves it.

### 1.2 Bounded contexts

Twelve contexts with responsibility, owning module, coupling and roadmap (board table). Rules:
the capability registry (instruments/) is the single source for coverage states everywhere
including API contracts; risk/ is sync, pure and I/O-free toward models; audit+events are the
cross-cutting spine; planned contexts own no credentials they do not need (intelligence never
holds execution credentials).

### 1.3 ADRs

A-01 event spine (in-process now, NATS JetStream production) — existing, extended.
A-02 risk-engine isolation as architectural law: deterministic, fail-closed on missing inputs,
confidence never a satisfied requirement — existing, formalised.
A-03 capability registry single source — existing, extended to API contracts.
A-04 environment state machine as the only intent→execution gate; live authority DENIED by
default; promotion is an owner decision with audit entry — existing, extended.
A-05 audit chain as spine of record; reconciliation diffs are audit events — existing, extended.
A-06 API honesty contract: data status per field group on the wire (live/delayed/stale/
unavailable/simulated); simulation labelled at the wire, not at the UI — **new**.
A-07 single VM, docker-compose, modules-not-microservices until measured need; $0 self-hosted
observability — existing, formalised.
A-08 intelligence reaches execution only through the verification engine's three gates; no agent
holds an execution credential — **new law**.

### 1.4 Honesty statuses (§26)

Implemented+tested: the twelve Phase 2–4 packages above. Connected+live-verified: okx (twice),
binance vision (end-to-end, µs-timestamp defect found and fixed). Connected-but-untested:
bybit v5 from hosted runners (403 geo-block; code exercised against public docs only).
Connected, layout-unverified: dukascopy (real 25,761-byte bi5 downloaded; LAYOUT_VERIFIED=False;
503 throttling characterised). Planned: NATS production bus; intelligence/verification/lab/
learning/notify/ops/portfolio contexts — nothing simulated to look built. Stage 7 retires the
unverified rows market by market with evidence per market.

---

## 2. Sub-deliverable 5.2 — Pipelines, topology, DR (BUILT — AWAITING REVIEW)

Board: `design/stage5-2-pipelines-topology-dr.html`. Four pipelines (27 stages), topology read
from the committed compose file, memory budget, fail-safes, DR. Var audit clean.

### 2.1 Pipelines

Each stage names a real module or a stage number — a stage without an owner is a gap, not prose.

- **P-1 Ingestion integrity** (implemented): adapter poll with throttle backoff → source-specific
  integrity gates (dukascopy stays `LAYOUT_VERIFIED=False`) → `DataQualityGate` where
  **`new_risk_allowed` is the binding flag, not `ok`** → `PipelineReport` with counted, reasoned
  rejections → idempotent persist → `EventEnvelope` on the bus → hash-chained audit.
  Failure semantics: `NatsEventBus` **raises** `EventPublishError` rather than dropping, so the
  pipeline stops instead of continuing unrecorded. Law: data that cannot be proven is labelled,
  never assumed; `DataStatus` travels to the API per A-06.
- **P-2 Decision → verification → authority** (mixed): candidate with ABSTAIN default → knowledge
  sufficiency (stage 10, planned) → three verification gates (stage 11, planned) → immutable
  digest-bound intent → 11-field `LiveAuthority` (any missing/unknown/false denies; no override
  flag) → deterministic sizing → environment routing (SHADOW ⇒ labelled paper). Law (A-02+A-08):
  **no gate can be satisfied by a confidence value**; steps 2–3 are dashed until Stage 11.
- **P-3 Idempotent execution** (governance implemented, venue wiring stage 14): idempotency key →
  monotonic `widest_scope()` halt check → gateway → order state machine where **UNKNOWN is never
  auto-resolved** → venue-reported fills only → reconciliation whose mismatch blocks new risk →
  audit + notify. Law: idempotent in, reconciled out; the venue is the source of truth for fills.
- **P-4 Controlled learning** (planned, stage 18): outcome events → content-addressed versioned
  artifact with provenance → promotion gate that must beat the incumbent on owner-set criteria and
  pass regression (no auto-promote) → shadow → paper → state machine, one stage at a time →
  rollback as a first-class path that never requires diagnosing the failure first.

### 2.2 Deployment topology & memory budget

Single VM (Oracle Always Free A1, 2 OCPU / 12 GB — allowance halved 15 Jun 2026 — 200 GB disk,
arm64). Caddy is the sole public entry (80/443); `core` exposes 8000 on `nexus-internal` only;
nothing else is published. Startup tiers from the real caps: **T1** core+caddy 1.15 GB · **T2**
+nats/cache/minio 2.18 GB · **T3** +db 3.71 GB · **T4** +observability 5.25 GB (5,248 MB) ·
**T5** +ollama 10.37 GB. **Budget law: T4 and T5 are mutually exclusive with headroom on a 12 GB
host — never both while trading is armed.** Ollama stays commented out; a quantized 7B at
5–12 tok/s on A1 CPU is a research aid and never a path to order authority (A-08).

**P-6 handed to Stage 6 (recorded, not applied):** the compose file documents that `core` waits on
`db` healthy but never connects to it; SQLite (WAL, `synchronous=FULL`) is the only implemented
store and refuses other schemes at startup, while `migrations/0001_core.sql` is complete Postgres
DDL. Cost today: 1.5 GB of the free-tier budget for a database nothing reads. Stage 6 (Database &
Persistent Memory) rules between (a) wire Postgres as system of record, (b) declare SQLite the
single-node store and make `db` optional/deferred, (c) hybrid — SQLite for the audit chain,
Timescale for time series. Stage 5 records the trade-off; it does not pre-empt the stage that owns
it.

### 2.3 Fail-safes and DR

Fail-safes (all implemented unless noted): disk watermark with retention running **before** the
watermark, `RetentionPlan.is_safe` + recorded refusals; memory caps so a runaway cannot starve the
audit store; UNKNOWN never auto-resolved; monotonic halt widening; binding `new_risk_allowed`;
11-gate authority; raising bus; secrets fail-closed with a tested redactor; CI with gitleaks,
Trivy, ruff, mypy strict, pytest, arm64+amd64 build, compose validation.

DR by store with design RPO/RTO and honesty status: audit chain (implemented+tested; a restore is
*verifiable* because the chain is hash-chained, not merely copied); JetStream (planned in
production); parquet archive (implemented; re-derivable from public venues within retention);
configuration (implemented; **off-VM copy unverified**); off-VM backup (**DESIGNED — UNTESTED: no
backup has ever been restored in this project**, candidate $0 targets unproven here, Stage 20
drill sets the real numbers); whole VM (**single point of failure — free tier has no HA**).

**The DR claim, stated plainly:** the objective is *resume monitoring and reconcile*, not *keep
trading*. VM loss stops trading safely. Redundancy is replaced by determinism and by an audit
chain that can prove what happened.

### 2.4 Stage 5 completion summary (pending stage-level approval)

5.1 boundaries + ADRs (D-040) and 5.2 pipelines + topology + DR. Stage 5 wrote no production
code; it fixed A-06 and A-08 as laws, mapped planned contexts to stage numbers, and handed P-6 to
Stage 6. Stage-level approval gates Stage 6 (Database & Persistent Memory).
