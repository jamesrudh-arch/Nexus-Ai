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
