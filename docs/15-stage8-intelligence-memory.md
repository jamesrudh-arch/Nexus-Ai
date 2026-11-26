# Stage 8 — Intelligence Memory: what exists, what is schema-only, and what a writer must satisfy

**Sub-deliverable 8.1 — research.** Status: `DELIVERED, AWAITING REVIEW`.
Authorised by **D-049** (research only; no production code).
Date: 2026-11-26.

> **8.1 changed no production code.** The owner's ruling was explicit: read the code and the approved
> design, inventory what exists against what is schema-only, and produce findings, $0 levers and a
> proposed scope for 8.2. Nothing in `backend/` was modified, so no new CI surface was added and the
> gate is unchanged from Stage 7's closure. Every claim below was produced by a command or a read that
> is named beside it, and the ones that could be executed were executed.

---

## 1. Why Stage 8 has no name, and what this batch does about it

`docs/07` carried "STAGE 8 — KNOWLEDGE GRAPH" for two commits. **No document in this repository says
that.** It was invented, and it has been retracted (`f006d1f`). What the record does establish is the
chain Stage 8 sits in:

| Source | What it fixes |
|---|---|
| `docs/13` §2.4, §2.5 | the intelligence-memory tables `dossier`, `evidence_ref`, `memory_item` are **schema only**; "writers arrive with stages 8–10" |
| `docs/12` §1.3 (P-2) | the decision chain: candidate with ABSTAIN default → **knowledge sufficiency (stage 10, planned)** → **three verification gates (stage 11, planned)** → immutable digest-bound intent → `LiveAuthority` → deterministic sizing → environment routing |
| `design/build_board52.py:73` | "intelligence dossier (**stage 9**) · evidence set + uncertainty · ABSTAIN is the default record" |
| `docs/03` §7, §8 and `docs/10` §3.1 | the Intelligence Centre screen and the evidence graph it must serve — **approved at Stage 3.3, D-035** |

So Stage 8 is the first of the three stages that give those tables writers, and it sits *before* the
dossier stage and two stages before sufficiency is defined. Its scope is the owner's to set. This
document does not set it; it establishes what is there to build on, what is missing, and what any
builder would have to satisfy — then proposes a scope in §8 for the owner to rule on.

**Finding ids.** This document continues the numbering from `docs/14` (F-15 onward) rather than
restarting at F-1, for a reason recorded as **F-19** in §3: F-1…F-7 already mean different things in
`docs/13` and `docs/14`, and neither says its ids are scoped to itself. Restarting would give "F-4" a
third meaning.

---

## 2. The inventory, verified

What follows was established by reading the source and, where a claim could be executed, executing it.
The command that produced each row is named in §2.4.

### 2.1 What exists and works

| Piece | Where | State |
|---|---|---|
| `DecisionRecord`, `DecisionVerb` (ACCEPT/REJECT/WAIT/REDUCE/EXIT/ESCALATE/ABSTAIN), `DecisionState` (12 states) | `domain/decision.py:17-67` | **Built**, matches the `docs/03` §7 vocabulary exactly |
| Persistence for decisions | `store/operational.py:366-414` (`save_decision`, `save_decision_payload`, `decisions`, `get_decision`) | **Built**, audit-first, `INSERT OR REPLACE` |
| The three memory tables | `store/schema.py:267-313` (SQLite, applied) and `migrations/0002_memory.sql` (Postgres target) | **Schema only** — no writer, as `docs/13` records |
| `counts()` includes all three | `store/operational.py:931-951` | **Built** — the tables are observable today at `/v1/status → persistence.counts`, all zero |
| Audit hash chain, append-only | `audit/chain.py`, `audit/log.py`, triggers in `schema.py:316-333` | **Built**; `assert_no_secrets` guards every payload |
| Projection bookkeeping | `op_projection` table, `mark_projected`, `projected_refs` | **Built** — the operational store is already modelled as a projection of the audit chain |
| Write-ahead replay | `store/writeahead.py:75-87` | **Built** for 7 event types, including `instrument.registered` |
| `LiveAuthority`, sizing, routing | `risk/authority.py`, `risk/engine.py` | **Built** — steps 5–7 of the P-2 chain |

### 2.2 What is absent

| Absent thing | How it was established |
|---|---|
| **Any candidate or thesis generation.** No `intelligence`, `research` or `memory` package exists | `ls src/nexus/` → 15 packages: api, archive, audit, core, data, domain, events, execution, ingestion, instruments, observability, risk, secrets, store |
| **Any construction of `DecisionRecord` in production code** | `grep -rn "DecisionRecord(" src/` → **zero hits**; the only constructions are in `tests/test_core_guarantees.py` and `tests/test_store_persistence.py` |
| **Any real value in `evidence_refs`** | `grep -rn "evidence_refs=" src/ tests/` → one hit, `tests/test_store_persistence.py:71`, with the literals `("EV-1", "EV-2")` |
| **Any "evidence graph"** | `grep -rn "evidence graph\|evidence_graph" src/` → one hit, and it is the *comment* on `decision.py:62`: "source ids from the evidence graph". There is no graph |
| **Any route serving decisions, dossiers, memory or evidence** | The 11 routes are `/healthz`, `/metrics`, `/readyz`, `/v1/audit/verify`, `/v1/data/coverage`, `/v1/halt`, `/v1/halt/release`, `/v1/instruments`, `/v1/instruments/coverage`, `/v1/instruments/{id}/session`, `/v1/status`. All operational |
| **Any emitter of `instrument.registered`** | `writeahead.py:81` can *replay* it; nothing in `src/` ever produces it |

### 2.3 What the seeded master does and does not reach

Stage 7.3 seeded the instrument registry with 3 instruments. That seed reaches the **registry** and the
API's coverage routes. It does **not** reach the store:

```
GET /v1/status   →  instrument_master.count      = 3        (the in-memory registry, seeded by L-C)
                 →  persistence.counts.instrument = 0       (SQLite, "system of record" per docs/13 R-1)
                 →  persistence.counts.dossier    = 0
                 →  persistence.counts.evidence_ref = 0
                 →  persistence.counts.memory_item  = 0
```

Identical under both backends — `NEXUS_AUDIT_BACKEND=memory` (ephemeral) and `sqlite` (durable,
`./data/nexus.db`). So the system of record has never heard of any instrument, while the coverage routes
report three.

### 2.4 Commands that produced this section

```
ls src/nexus/                                        # 2.2 package inventory
grep -rn "DecisionRecord(" src/ tests/               # 2.2 no production construction
grep -rn "evidence_refs=" src/ tests/                # 2.2 one test, literal placeholders
grep -rn "save_instrument" src/                      # 2.2 only caller is writeahead replay
grep -n 'version="' src/nexus/store/schema.py        # 3 migrations applied from schema.py
ls backend/migrations/                               # 2 .sql files, no 0003
NEXUS_AUDIT_BACKEND=memory|sqlite python …/status    # 2.3 counts, both backends
```

---

## 3. Findings

### F-15 — the applied SQLite schema is not the mirror its Postgres counterpart claims

`migrations/0002_memory.sql` opens: *"Mirror of migration 0002_memory in `nexus/store/schema.py`
(SQLite), which is the one applied today."* The mirror is not faithful. Six divergences, found by
parsing both DDLs and diffing per column:

| Table | Column | Postgres target | Applied SQLite | Consequence |
|---|---|---|---|---|
| `dossier` | `instrument_id` | `TEXT REFERENCES instrument (instrument_id)` | `TEXT` — **no REFERENCES at all** | the link from a dossier to the instrument it is about is **undeclared**, so it cannot be enforced even in principle |
| `dossier` | `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | `TEXT NOT NULL` | insert omitting it fails in SQLite, succeeds in Postgres |
| `dossier` | `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | `TEXT NOT NULL` | same |
| `evidence_ref` | `retrieved_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | `TEXT NOT NULL` | same — and this is the column F-14 needs |
| `memory_item` | `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | `TEXT NOT NULL` | same |
| `memory_item` | `confidence` | `NUMERIC(6, 5)` | `TEXT` | see below |

The `TIMESTAMPTZ`→`TEXT` and `JSONB`→`TEXT` translations are legitimate: SQLite has no such types. The
six above are not translations, they are omissions.

**`docs/13` §2.5 already records that foreign keys are "declared but not enforced", and gives the reason:
`PRAGMA foreign_keys` is off because recovery re-projects in chain order, which is not always
parent-first.** That limitation is real and deliberate, and this finding does not dispute it. But it does
not cover `dossier.instrument_id`: that column is not *declared*, so turning the pragma on would not
restore it. Executed proof that the two behave differently under the **same** pragma:

```
PRAGMA foreign_keys = ON
  dossier      -> instrument_id that never existed : ACCEPTED          (nothing to enforce)
  evidence_ref -> dossier_id   that never existed : rejected, FOREIGN KEY constraint failed
```

So `docs/13`'s sentence is inaccurate for one column, and the inaccuracy matters precisely where Stage 8
will write.

**On `confidence`, the divergence is behavioural and the obvious fix is not sufficient.** The migration
states its own law — *"Confidence uses NUMERIC, never FLOAT"* — and the applied schema uses neither.
Executed against the real applied DDL:

```
TEXT-affinity column, ORDER BY confidence  ->  ['', '0.5', '99999999', 'not-a-number']
                                                '99999999' sorts ABOVE '0.5'
accepts '' and 'not-a-number'              ->  both ACCEPTED
```

Declaring `NUMERIC(6,5)` in SQLite **fixes the ordering and not the acceptance** — affinity is a
conversion preference, not a constraint, so it converts what it can and stores junk as-is:

```
NUMERIC(6,5) column, ORDER BY  ->  [0.5, 0.5, 99999999, '', 'not-a-number']   (numerics correct, junk last)
NUMERIC(6,5) column, INSERT 'not-a-number'  ->  ACCEPTED, typeof() = text
```

Postgres' `NUMERIC(6,5)` would reject both strings outright. So the two schemas do not merely store
confidence differently, they **disagree about what a confidence is allowed to be**, and the SQLite fix
requires a `CHECK` constraint or validation in the writer — not a type change.

**Nothing detects any of this.** No test reads `migrations/*.sql`; the runner applies
`schema.MIGRATIONS` (`store/migrations.py:111`, `:229`), so the `.sql` files are executed by neither the
app nor the suite. `grep -rn "0002_memory\|migrations" tests/` finds tests that assert migration
*names*, *checksums* and *ordering* — never column definitions.

### F-16 — the instrument master is in the registry and the API, but not in the system of record

`/v1/status` reports `instrument_master.count = 3` and `persistence.counts.instrument = 0`, under both
the ephemeral and the durable backend (§2.3). The cause is not a missing call but a missing emitter:
`save_instrument` has exactly one caller, `writeahead.py:82`, which replays an `instrument.registered`
audit event — and nothing in `src/` ever emits one. Stage 7.3's seed writes thirteen entries into the
registry's own in-memory change log, not into the audit chain.

Two consequences for Stage 8, and they compound:

1. `dossier.instrument_id` has no candidate parent rows, so **every dossier written today would reference
   an instrument the system of record has never heard of**.
2. Because of F-15, that reference is undeclared, so **it would be accepted silently** rather than
   rejected.

This is the single most important scoping fact in this document: the intelligence layer's first table
points at a parent that does not exist, through a constraint that does not exist.

### F-17 — nothing in the product ever creates a decision

`DecisionRecord` is never constructed in `src/` (§2.2). Its `evidence_refs` and `counter_evidence_refs`
fields are persisted faithfully, default to `ABSTAIN`, and have only ever held the literals `"EV-1"` and
`"EV-2"` in one test. No route serves decisions. So the P-2 chain is built from step 5 onward
(`LiveAuthority`, sizing, routing) and **steps 1–4 are absent**: candidate, sufficiency, verification
gates, decision.

That is consistent with `docs/12` — sufficiency is stage 10 and the gates are stage 11 — but it means
Stage 8 is not extending a decision layer, it is **creating the thing that produces decisions**. The
`ABSTAIN` default is already correct in the data model (`DecisionVerb.ABSTAIN` is the dataclass default,
`dossier.stance` defaults to `'ABSTAIN'` with the comment *"ABSTAIN is the default, not a fallback"*,
and `save_decision_payload` defaults a missing verb to `"ABSTAIN"`), so the honesty posture Stage 8
inherits is sound. What is missing is anything that could ever move off it.

### F-18 — the approved design requires four things neither schema can hold

Stage 3.3 was approved at **D-035**, so these are obligations, not aspirations:

| Required by | Requirement | `dossier` / `evidence_ref` / `memory_item` |
|---|---|---|
| `docs/03` §7; `docs/10` §3.1 | beliefs with "confidence, **validity interval**, **change conditions**"; `docs/10` adds *"a point estimate without them is a defect"* | `memory_item` has `confidence` and **neither** of the other two |
| `docs/10` §3.1 | memory with "**expiring TTLs**" | no expiry column anywhere. `superseded_by` models correction, not expiry. `DecisionRecord.expires_at` exists but memory has no equivalent |
| `docs/03` §8; `docs/10` §3.1 | evidence graph with "**contradictions highlighted and linked**" | `evidence_ref` has **no column linking one row to another it contradicts**. `counter_evidence_refs` exists on the *decision*, not on the evidence |
| `docs/10` §3.1 | "**knowledge-sufficiency meter with stated basis and what it is sufficient *for***" | `dossier.sufficiency` is a single `TEXT` defaulting to `'INSUFFICIENT'` — no basis, no target |

All four could be pushed into the unenforced `payload JSONB`/`TEXT` column, which is how a schema starts
lying: the field exists, the meaning does not. Note that three of the four are **cheap to add properly**
(§5.3) and only the fourth needs Stage 10's definition before it can be more than a string.

### F-19 — finding ids already collide across stages, and nothing says so

`docs/13` uses F-1…F-7 and `docs/14` uses F-1…F-14. They are different findings: `docs/13`'s **F-4** is
*"the Postgres path is part-paid, not free"*; `docs/14`'s **F-4** is *venue vocabulary*. Neither document
states that its ids are scoped to itself, and `docs/07`'s register cites bare ids. So "F-4" is ambiguous
in this repository today, and Stage 8 would have made it three ways.

Recorded rather than rewritten: renumbering two approved stages would falsify their citations. This
document continues from **F-15**, which creates no new collision, and the historical ambiguity is stated
here so a reader who meets a bare "F-4" knows to ask which stage.

---

## 4. The design obligations Stage 8 must honour

Beyond F-18, the approved design fixes behaviour that a first writer can get wrong quietly:

* **`docs/03` §7: "No hidden chain-of-thought. Auditable evidence + structured findings + concise
  rationale only."** A dossier that stores a model's reasoning prose in `payload` would violate this.
  The schema's `summary` / `stance` / `uncertainty` split is the right shape and should be used as
  designed rather than bypassed.
* **`docs/10` §3.2: three verification stages per candidate — V1 evidence & data sufficiency, V2 risk &
  mandate compliance, V3 execution safety; "definitions finalise at Stage 11, chrome reserved"; any FAIL
  ends the candidate with a reason code; confidence never overrides a failed stage.** Stage 8 must not
  define V1–V3, but it must not make them undefinable either: a dossier that records sufficiency as a
  bare enum leaves nowhere for V1's outcome to live.
* **`docs/12` §1.3: "no gate can be satisfied by a confidence value"** (law A-02+A-08). So
  `memory_item.confidence` and `DecisionRecord.confidence` may inform ranking but must never satisfy a
  gate — which is an argument for keeping confidence strictly ordered and typed (F-15) *and* for never
  letting it be the only thing a gate reads.
* **`docs/10` §3.1: "every line links to its run record"** for tasks and tool activity, and *"quant result
  with run id"* in the dossier view. The evidence row's `locator` + `checksum` + `audit_ref` are the
  mechanism; a writer that leaves `locator` empty (it defaults to `''`) produces an untraceable claim.

---

## 5. What any writer must satisfy

These are constraints discovered by reading and executing, not preferences. They bound 8.2's cost.

### 5.1 The audit contract

Every one of the three tables carries `audit_ref`, and the existing writers show the required shape
(`operational.py:372-408`):

1. validate the identity column is present and raise `PersistenceError` if not;
2. `assert_no_secrets(payload)` — the guard that raises `SecretMaterialDetected`;
3. write inside `self._transaction()`, defaulting `state`/`verb`/`stance` to their ABSTAIN-side values;
4. `self._mark(conn, audit_ref, entity_type, entity_id)` so the row is booked into `op_projection`.

The operational store uses `INSERT OR REPLACE`, so it is a **projection**, not the record; the audit
chain is the record and is append-only by trigger. A Stage 8 writer inherits that split and must not
treat a re-save as an edit — `memory_item.superseded_by` exists precisely because *"memory is
superseded, never edited in place"*.

### 5.2 Migrations are forward-only and checksummed

`store/migrations.py:194-199` refuses a version whose checksum changed after it was applied. So **no
column in `0002_memory` can be edited**; any fix is a new `0004_*` migration plus a matching `.sql` file.
Note also that the migration *boundaries* already differ: `schema.py` has `0001_operational`,
`0002_memory`, `0003_audit_append_only`, while `migrations/` has `0001_core.sql` and `0002_memory.sql`
with **no 0003** — the append-only triggers live in `0001_core.sql:26-38` instead. The triggers
themselves do mirror faithfully (same names, same two operations), so this is a boundary difference and
not a missing feature; but a Postgres deploy following the `.sql` files would have a different migration
history from the one `tests/test_boot_recovery.py:341` asserts.

### 5.3 What SQLite's `ALTER TABLE` permits — executed, not assumed

| Operation | Result |
|---|---|
| `ADD COLUMN expires_at TEXT` | **OK** |
| `ADD COLUMN supersedes TEXT REFERENCES memory_item (memory_id)` | **OK**, and `PRAGMA foreign_key_list` confirms the FK is registered |
| `ALTER COLUMN confidence TYPE NUMERIC(6,5)` | **refused** — `near "ALTER": syntax error` |
| `ADD CONSTRAINT … FOREIGN KEY (instrument_id) REFERENCES …` | **refused** — `near "CONSTRAINT": syntax error` |
| create-new → copy → drop → rename | **OK** |

So the cost of the two halves of F-15/F-18 is very different, and this is what makes the sequencing in
§8 a real choice rather than a preference:

* **Cheap, no rebuild:** adding `valid_from`, `valid_until`, `change_conditions`, `expires_at` to
  `memory_item`, and a `contradicts` FK column to `evidence_ref` — three of F-18's four gaps.
* **Requires a table rebuild inside a forward-only migration:** `memory_item.confidence` TEXT →
  NUMERIC(6,5) with a `CHECK`, and `dossier.instrument_id` gaining its `REFERENCES` — F-15(a) and (c).

---

## 6. $0 levers for 8.2

No new dependency, no new service, no cost. Each is independently testable offline.

| Lever | What it does | Why it is ordered here |
|---|---|---|
| **L-A** — schema fidelity | migration `0004_memory_fidelity` rebuilding `memory_item` (confidence `NUMERIC(6,5)` + `CHECK`) and `dossier` (its `REFERENCES` restored), plus a **fidelity test** that parses both DDLs and asserts agreement on column names, nullability, defaults and FK declarations | This is the guard that would have caught F-15. Without it the two schemas keep drifting and every later lever is written against a shape that may not survive a Postgres deploy |
| **L-B** — project the master | emit `instrument.registered` audit events for the seeded master so the store's `instrument` table matches `instrument_master.count`, making `persistence.counts.instrument` 3 rather than 0 | F-16: a dossier's parent rows must exist before dossiers do. The replay path is already built, so this is an emitter, not a mechanism |
| **L-C** — first writer | `evidence_ref` only: record one piece of evidence against a dossier, populating `observed_at` and `retrieved_at` **separately**, plus `data_status`, `locator`, `checksum`, `audit_ref` | It is the leaf table, its FK is already enforced, and it needs no new columns. It is also where **F-14 gets its home**: the schema already separates observation from retrieval, so a writer that fills both correctly stops the venue-time defect propagating into the evidence graph |
| **L-D** — first route | `/v1/intelligence/dossiers`, read-only, serving what exists and rendering empty honestly | The Intelligence Centre chrome has been reserved since D-035 with nothing behind it. A route that returns an honest empty is worth more than a route that does not exist |
| **L-E** — dossier writer | create a dossier with `stance=ABSTAIN` and sufficiency carried **with its basis and its target** as pinned payload keys | Last because it depends on L-A (its FK), L-B (its parent rows) and L-C (its evidence). Its sufficiency must stay a string until Stage 10 defines the meter — but it must be a string that says what it is sufficient *for* |

---

## 7. Limitations of this research

1. **Nothing here was executed against Postgres.** No Postgres server or driver exists in this sandbox
   (`docs/13` §2.5 records the same). Every statement about Postgres behaviour is a property of the
   declared types, not a measurement — including the claim that `NUMERIC(6,5)` would reject
   `'not-a-number'`.
2. **The absence claims are grep-shaped.** "No production code constructs a `DecisionRecord`" is true of
   the literal `DecisionRecord(`; a factory function or `**kwargs` splat built elsewhere could evade that
   pattern. The supporting evidence is stronger than the grep alone — no route serves decisions, and
   `persistence.counts.decision` is 0 on a booted app — but the grep by itself would not prove it.
3. **`payload` was not inventoried.** All three tables carry a `payload` column that nothing writes, so
   there is no established key vocabulary to conform to. L-E proposes pinning one; until then, any claim
   about "the payload contract" would be invented.
4. **No design was produced.** 8.1 is an inventory and a constraint list. It does not propose a schema
   for beliefs, a contradiction model, or a sufficiency semantics — the first two need F-18's columns and
   the third is Stage 10's by `docs/12` §1.3.
5. **The run-29 fold-in belongs to Stage 7, not Stage 8.** It is recorded in `docs/14` §4.1 in this same
   commit because the owner ruled that it should ride with this batch rather than generate a commit of
   its own; it is not evidence about intelligence memory.

---

## 8. Decision requested

**Recommendation: authorise 8.2 as L-A + L-B + L-C, and defer L-D and L-E to 8.3.**

The reasoning is dependency, not caution. F-16 and F-15 together mean that a dossier written today would
point at an instrument the system of record has never heard of, through a constraint that does not exist,
and would store its confidence in a column that cannot be ordered numerically. Writing the dossier first
would therefore build the intelligence layer on a schema that cannot hold what the approved design
requires — and every row written before L-A would have to be migrated afterward.

L-A + L-B are the ground; L-C is the first writer that can stand on it, and it is the one that gives
F-14 a home, because `evidence_ref` already separates `observed_at` from `retrieved_at` and the adapters
collapse them. L-D and L-E are worth doing but are better done against a schema that will not change
underneath them.

Four questions, in dependency order:

1. **Is batch 8.1 approved?** Its findings F-15…F-19 and levers L-A…L-E are the base 8.2 would stand on.
   Stage 7.1 was left unratified for a day and needed D-047 to fix it; this one is asked up front.
2. **Does F-15 get fixed by a rebuild migration (L-A), or is the divergence accepted and documented?**
   A rebuild touches two tables inside a forward-only migration and must keep the audit chain intact.
   Accepting it instead means the Postgres target and the applied schema stay different, and that
   difference should then be stated in `docs/13` §2.5 rather than left in a comment that claims to be a
   mirror. **Recommendation: fix it, and add the fidelity test** — the test is what makes the fix stay
   fixed.
3. **Should F-14 be fixed before or alongside L-C?** L-C can populate `evidence_ref.retrieved_at` from
   the local clock and `observed_at` from the venue, which makes the evidence graph correct *without*
   changing what `observed_at` means in the four adapters. That is the cheap half. The expensive half —
   giving the adapters a real receipt time — is still unauthorised. **Recommendation: do the cheap half
   in L-C and keep F-14 open**, so no writer imports the defect, and re-ask the adapter change on its own
   merits.
4. **Should finding ids be scoped explicitly from here on?** F-19 records that F-1…F-7 are already
   ambiguous between two approved documents. Options: continue global numbering (what this document
   does), or prefix per stage (`S8-F-1`) from Stage 8 onward and leave the historical ids alone.
   **Recommendation: continue global numbering** — a prefix scheme introduced halfway creates a second
   convention to remember, and the collision is now recorded where a reader will find it.
