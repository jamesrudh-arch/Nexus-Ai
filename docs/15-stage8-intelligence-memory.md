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

> Two rows below are overtaken by §9 and one number in them is wrong. `intelligence` now exists as a
> package (§9.5), and `evidence_ref` now has a writer (§9.5). The package count reads 15 because `ls`
> counted `__pycache__`; the tracked count was **14** (`git ls-files 'backend/src/nexus/*/__init__.py'`).
> Left as published because it is the inventory D-050 was ruled on.

| Absent thing | How it was established |
|---|---|
| **Any candidate or thesis generation.** No `intelligence`, `research` or `memory` package exists | `ls src/nexus/` → 15 packages: api, archive, audit, core, data, domain, events, execution, ingestion, instruments, observability, risk, secrets, store |
| **Any construction of `DecisionRecord` in production code** | `grep -rn "DecisionRecord(" src/` → **zero hits**; the only constructions are in `tests/test_core_guarantees.py` and `tests/test_store_persistence.py` |
| **Any real value in `evidence_refs`** | `grep -rn "evidence_refs=" src/ tests/` → one hit, `tests/test_store_persistence.py:71`, with the literals `("EV-1", "EV-2")` |
| **Any "evidence graph"** | `grep -rn "evidence graph\|evidence_graph" src/` → one hit, and it is the *comment* on `decision.py:62`: "source ids from the evidence graph". There is no graph |
| **Any route serving decisions, dossiers, memory or evidence** | The 11 routes are `/healthz`, `/metrics`, `/readyz`, `/v1/audit/verify`, `/v1/data/coverage`, `/v1/halt`, `/v1/halt/release`, `/v1/instruments`, `/v1/instruments/coverage`, `/v1/instruments/{id}/session`, `/v1/status`. All operational. *(Superseded by Stage 8.3: the count is 13, and `GET /v1/intelligence/dossiers` with `GET /v1/intelligence/dossiers/{dossier_id}` serve the `dossier` table — see §10. This row is left as the 8.1 inventory it is.)* |
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

> **Corrected in §9.1.** Executing the fix in Stage 8.2 required diffing every table and every column,
> and the systematic diff showed this finding was **partly wrong**: two of the six divergences below are
> uniform house conventions rather than drift, one table count is off by one, and the drift that is real
> is larger and runs in both directions. The load-bearing part — `dossier.instrument_id` carrying no
> `REFERENCES` at all — is correct and is what migration 0004 fixed. The text below is left as published
> because it is what D-050 was ruled on.

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

---

## 9. Stage 8.2 delivered (D-050): the schemas converge, the master projects, evidence has a writer

Batch **L-A + L-B + L-C**. L-D (`/v1/intelligence/dossiers`) and L-E (the dossier writer) are deferred to
8.3 by the same ruling. This is the first batch to change `backend/` since `9e70ed3`.

`git diff --stat`: **17 files changed, 2,236 insertions(+), 23 deletions(-)**. Source **14,162** LOC,
tests **14,760** LOC. Three new source files, three new test files, one new package.

### 9.0 What was ruled, and what was not

D-050 answered four questions, each answered `Recommend` against exactly one marked recommendation:

1. **Stage 8.1 is approved** — recorded as D-050, asked up front rather than assumed from a later
   `Proceed`, because Stage 7.1 was left unratified for a day and needed D-047 to fix it.
2. **8.2 = L-A + L-B + L-C**, with L-D and L-E deferred to 8.3.
3. **F-15 = rebuild migration plus a fidelity test** — the test is what makes the fix stay fixed.
4. **F-14 = the cheap half inside L-C**, with F-14 itself left open and re-asked on its own merits.

**Not ruled.** §8's fourth question — whether finding ids should be scoped per stage from Stage 8 onward —
was not among the four asked, so it is still open and is re-asked in §9.8. F-20 below continues the global
numbering this document already uses; if the owner prefers a prefix scheme, F-20 is the first id that
would move and the only one.

### 9.1 Correction: F-15 as published in §3 was partly wrong

§3 was written from one hand-picked pair of tables (`dossier` in both DDLs). Fixing the finding required
parsing both DDLs and diffing **every table and every column**, and the systematic diff disagreed with
§3 in three ways. The published text is unchanged above; this is the correction.

**(a) Two of the six "divergences" are house conventions, not drift.**

- The four lost `DEFAULT now()` clauses: every timestamp column in the applied schema is `TEXT NOT NULL`
  with no default, because the writers stamp them with `iso_utc(utc_now())`. Nothing in `src/` relies on a
  database default. Presenting these as drift implied a defect where there is a convention.
- `confidence TEXT` against `NUMERIC(6,5)`: **26 numeric columns across 8 tables** are TEXT in the applied
  schema, because SQLite's NUMERIC affinity stores a REAL — a float — and the house rule is that Decimals
  travel as strings. §3 said 19 across 8 tables. **The 19 reproduces exactly** and is the count before 0004
  created `venue_instrument_mapping`, whose seven `NUMERIC(28,12)` columns join the others: 19 + 7 = 26.
  **The table count did not reproduce**: those 19 columns sat across **7** tables, not 8.

**(b) The real drift is larger than §3 said, and it runs in both directions.** §3 described SQLite losing
columns the target had. The diff found the target losing columns the application really writes.

| Direction | What was missing | Consequence |
|---|---|---|
| absent from SQLite | `venue_instrument_mapping` — the entire table, declared in the target since `0001_core.sql` | the four venue mappings Stage 7.3 seeded had nowhere to be projected; F-16 was unfixable without L-A |
| absent from the target | `halt_event.cancel_working_orders` | a field `/v1/status` really serves would not exist after a promotion |
| absent from the target | `halt_event.seq`; `audit_ref` on `approval`, `decision`, `fills`, `orders`, `trade_intent`, `halt_event`, `venue_instrument_mapping`; `instrument.payload`; `trade_intent.payload` | 11 columns across 8 tables, every one written by `store/operational.py` today |
| absent from the target | `schema_migrations`, and now `schema_migration_skips` | a PostgreSQL deploy following the `.sql` files could not record which migrations it had applied, so it could not refuse a changed checksum |

**(c) Two apparent divergences are not divergences at all**, and §3 should have said so. `audit_log` is
created by `SqliteAuditStore` in `src/nexus/audit/log.py`, not by a migration, because migration
`0003_audit_append_only` *requires* it to exist already. `schema_migrations` comes from
`SCHEMA_MIGRATIONS_DDL`, which the runner executes before applying anything.

**What survives, and is the load-bearing part:** `dossier.instrument_id` carried no `REFERENCES` at all,
so `docs/13` §2.5's "foreign keys declared but not enforced" could not reach it — it was never declared.
Migration 0004 declares it and `TestDossierForeignKey` pins both halves: enforced when the pragma is on,
and still *not* enforced by default (§9.7).

**The lesson, recorded because it cost a batch to learn.** A divergence finding written from one
hand-picked table pair is a guess about the whole schema. §3 diffed two tables and reported six
divergences; the full diff found eleven columns and three tables of drift in the direction §3 never
looked, and reclassified two of its six as conventions.

### 9.2 L-A — migration 0004, and the test that keeps the fix fixed

**Deviation from the approved option, disclosed.** The recommendation D-050 accepted said
`confidence NUMERIC(6,5)` plus a `CHECK`. Writing it that way and then executing it showed the type change
is wrong:

| Probe, executed | Result |
|---|---|
| `CREATE TABLE t (c NUMERIC(6,5))`, insert `'0.5'`, read `typeof(c)` | **`real`** — a float, in what would be the only float-backed numeric column in the applied schema |
| `TEXT` with `CHECK (confidence IS NULL OR CAST(confidence AS REAL) <> 0.0)` | accepts `'0.5'`, `'0.12345'`, `'1'`, `'0'`, `'0.00000'`, `'1e-9'`, NULL; rejects `'not-a-number'`, `''`, `'abc123'` |
| the same CHECK, adversarially | **leaks `'0.5abc'` and `'1e-9'`** — `CAST` is permissive, so a CHECK is necessary and not sufficient |
| `TEXT` with `ORDER BY CAST(confidence AS REAL)` over `0.5, 0.05, 0.9, 0.12345` | orders `0.05, 0.12345, 0.5, 0.9` |
| `ORDER BY confidence` (no `CAST`) over the same four values | **the same order** — see the correction below |
| the CHECK against `'12'`, `'-0.5'`, `'99999999'`, `'1.0'` | **all accepted** — it bounds nothing but "casts to a nonzero number" |

So 0004 keeps `confidence TEXT` and adds only the CHECK. Changing the type would have broken the
Decimal-as-string rule for no gain, and would not have fixed acceptance anyway.

**A second correction, found while capturing the transcript for the board.** This batch first wrote that a
bare `ORDER BY confidence` remains lexicographic and therefore wrong, and that `CAST` is what fixes it.
Executing it says otherwise: over `0.5, 0.05, 0.9, 0.12345` the two orderings are **identical**, and they
stay identical for the prefix tie `'0.5'` against `'0.50'`. For values in `[0,1)` — the only range a
probability may occupy — TEXT ordering and numeric ordering coincide, because every value shares the
`'0.'` prefix and digit-by-digit comparison then agrees with magnitude. They diverge only at ten and
above (`ORDER BY confidence` gives `1, 12, 9`; `CAST` gives `1, 9, 12`).

So `CAST` is still the correct way to order the column, but the reason is not the one first written, and
the divergence is reachable **only because the CHECK does not bound the range**: it asks whether a value
casts to a nonzero number, not whether it is a probability, so `'12'`, `'-0.5'` and `'99999999'` are all
accepted. That is a larger gap than the ordering claim it replaced, and it is recorded as a limitation
(§9.7) and pinned by `test_the_check_does_not_bound_the_range_and_that_is_recorded` rather than quietly
fixed — bounding the range belongs to whoever writes `memory_item.confidence` in stage 10, and a
constraint that pretended to bound it would be worse than one that says it does not.

`0004_memory_fidelity`: **15 statements**, `requires="dossier"`, checksum `4c7368d407bb…`.

- Rebuilds `dossier` through `dossier_0004`. SQLite refuses both `ALTER COLUMN … TYPE` and
  `ADD CONSTRAINT … FOREIGN KEY` (§5.3), so the foreign key needs create → copy → drop → rename; all 12
  columns are copied and `ix_dossier_created` is recreated.
- Rebuilds `memory_item` the same way to add the CHECK, recreating `ix_memory_kind` and
  `ix_memory_created`.
- Creates `venue_instrument_mapping`, translating `BIGINT GENERATED ALWAYS AS IDENTITY` to
  `INTEGER PRIMARY KEY AUTOINCREMENT` (the IDENTITY clause has no SQLite equivalent, which is the likeliest
  reason the table was omitted when the SQLite schema was written), `NUMERIC(28,12)` to TEXT seven times,
  `JSONB fees` to `TEXT DEFAULT '{}'`, plus `audit_ref`, `UNIQUE (instrument_id, venue, venue_symbol)` and
  `ix_mapping_venue`.

The three earlier checksums are unchanged (`fcfd79161c83…`, `5e7fafd0673e…`, `1e9ec5a5d915…`), and all four
are now pinned literally in `test_no_applied_migration_was_edited` — because `store/migrations.py` refuses
a moved checksum only for a database that *already applied it*. A fresh checkout, a CI runner and a new
host apply whatever the file says, so a literal list is the only thing that makes forward-only checkable
offline. Adding to that list is normal; changing a line already in it means history was edited.

Executed proofs rather than readings of the SQL: `PRAGMA foreign_key_list(dossier)` shows the FK; on a
fresh autocommit connection with `PRAGMA foreign_keys=1` a dangling `instrument_id` is **rejected** and a
real one accepted; all four indexes survive the rebuild; `mapping_id` autoincrements from 1; a duplicate
`(instrument_id, venue, venue_symbol)` is refused. And
`test_the_rebuild_preserves_existing_rows` writes rows into the **pre-0004** schema first and then rebuilds
over them, because a migration that is only safe on an empty table will be run against a non-empty one
someday. Both tables are empty today; that is luck, not a property.

The target was corrected in the same commit — 11 columns across 8 tables, both bookkeeping tables, and both
file headers rewritten. `0001_core.sql` claimed *"the two are kept column-for-column compatible"*: a claim
nothing checked, and false in both directions. It is now enforced by `tests/test_schema_fidelity.py`
(**35 tests**), which compares the **live post-migration** SQLite schema against the target and fails on
divergence in tables, columns, nullability, foreign keys and types.

Two properties of that test are deliberate. It compares the schema *after the migrations run*, not the SQL
text: parsing `schema.py` statically also picks up 0004's staging tables and the superseded pre-rebuild
`dossier`, and reports divergences that do not exist. And the legitimate translations are a written-down
map, with `test_the_translation_map_covers_every_type_the_target_declares` failing if the target starts
using a type the map has no rule for — so a new type is a decision rather than a difference absorbed
silently. Result: **17 tables each side, 16 compared** (`audit_log` exempt and checked separately against
its own mirror claim), **0 divergences**.

Building that test produced three false positives worth recording, because an audit that cries wolf gets
its findings acted on: a constraint filter matching the prefix `"CHECK"` silently swallowed the column
named `checksum`; static parsing reported 0004's staging tables as drift; and a first draft asserted
`payload["observed_at"] not in payload`, which raises `KeyError` precisely when the assertion holds.

### 9.3 F-20 — 0004 exposed a defect in the migration runner: a deferral was indistinguishable from a bypass

**Found by the existing suite, not by a new test.**
`test_migrations.py::test_a_skipped_migration_applies_once_its_table_exists` failed with
`MIGRATION_INVALID: migration 0003_audit_append_only is pending while later migrations are already
applied; the sequence has a hole and this runner only moves forward`.

The scenario is one this repository deliberately supports and tests: boot once with an ephemeral audit
backend, where there is no `audit_log` to protect so 0003 is *skipped*, then boot the same file with a
durable one. Until 0004, 0003 was the last migration, so nothing could ever move past it. Adding a
migration **behind a skippable one** made the combination fatal: the ephemeral boot applies 0004 while
0003 waits, and the next durable boot finds an applicable migration below an applied one and refuses to
start.

The refusal is **correct**. "No holes" is how a permanently bypassed migration gets noticed, and a bypass
is fatal. What the runner could not do was tell a hole from a deferral it had itself reported one boot
earlier — in `schema_migrations` the two look identical, because in both cases the version is simply
absent. That is F-20, and it is a defect in the Stage 6 runner that only a fourth migration could expose.

Fix: `schema_migration_skips (version, reason, skipped_at)`, created by `SCHEMA_MIGRATIONS_DDL` — which is
not a versioned migration, so this needed no new version and moved no checksum. The runner records a skip
when it reports one, clears that row in the **same transaction** as the application (a version must never
be recorded as applied while a stale skip row still claims it is waiting), and treats a recorded deferral
as not-a-hole.

Verified by execution, three ways:

| Boot sequence | Result |
|---|---|
| ephemeral boot, no `audit_log` | applies 0001, 0002, **0004**; skips *and records* 0003; `venue_instrument_mapping` exists |
| durable boot over the same file | applies 0003; **no `MigrationError`**; all four recorded; the skip row is cleared |
| `DELETE FROM schema_migrations WHERE version='0002_memory'`, then run | **refused**: `the sequence has a hole` |

The third row is the one that matters. The refinement must not cost the guard its teeth, so
`test_a_genuine_hole_is_still_refused` pins that a version removed from the bookkeeping with no deferral
recorded against it still fails the boot closed.

A consequence worth stating plainly: because 0004 now applies in memory mode too,
`venue_instrument_mapping` exists under CI's `NEXUS_AUDIT_BACKEND=memory`. Had the fix gone the other way —
stopping the runner at the first migration it cannot apply, which is what most migration runners do —
memory mode would have had no such table, `counts()` would have failed on it, and L-B could not have been
wired into boot at all. The choice was between two defensible runner semantics, and only one of them left
the rest of this batch possible.

Three stale expectations were updated in the same commit, and two were made **derived** rather than
re-hardcoded: `test_boot_recovery.py::test_status_reports_the_system_of_record` asserted a literal
three-version list and `TestMigrationSkip` a literal two-version list. Both now derive from `MIGRATIONS`,
so adding 0005 will not break them. This is the third time the project has had to repair a test that
hardcoded a total which grows; the standing rule about publishing floors rather than totals applies to
test expectations as well as to documents.

### 9.4 L-B — the seeded master reaches the system of record

F-16's observable, inverted. `/v1/status` reported `instrument_master.count = 3` beside
`persistence.counts.instrument = 0`; it now reports `count 3, active 0, projected 3` with
`persistence.counts.venue_instrument_mapping = 4`. The `projected` key was added to that block precisely
because this pair of numbers is how the finding was found: reporting only the registry side would have
left the fix invisible in the one place the defect was visible.

The mechanism already existed. `instrument.registered` was in `PROJECTABLE`, the dispatcher routed it to
`save_instrument`, and `reproject_missing` would have replayed it from the chain. Nothing emitted the
event, so there was nothing to replay. L-B is therefore an emitter and not a mechanism:
`src/nexus/instruments/projection.py`, 168 lines. Three decisions inside it:

1. **The payload is built from the domain objects, not from `registry._mapping_to_dict`.** That serialiser
   is an API read-model and omits `margin_rate` and `fees` — the two fields that make a mapping an economic
   description rather than a symbol translation. Projecting through it would have written all four seeded
   mappings with both columns empty, and nothing would have failed, because both are nullable.
   `test_mapping_payload_names_every_field_the_column_set_holds` now fails if a field is added to
   `VenueMapping` and not to the projection.
2. **The payload carries no timestamp of its own.** A projection stamped at call time has a different
   digest on every boot, so every boot would append three audit records for instruments that had not
   changed — a chain that grows without describing anything. `project_master` compares canonical digests
   and appends only for an instrument that actually moved, which is what makes "call this at every boot"
   safe. Verified across process restarts on one durable file: `instrument.registered` stays at exactly
   **3 over three boots**, while `api.app_created` and `boot.recovery` legitimately grow by one each.
3. **`op_projection` is keyed on `audit_ref` alone, so a projection that writes several rows marks itself
   complete once, after all of them.** Handing `audit_ref` to each save would have booked the event as done
   the moment the instrument row landed; a crash before the mappings were written would then leave a hole
   that boot recovery believes is filled — the exact failure L-2 exists to prevent.
   `test_a_crash_between_the_instrument_and_its_mappings_leaves_a_hole_recovery_fills` simulates that crash
   and asserts the interrupted instrument's mapping is restored from the chain alone.

Wired into boot: `create_app` projects **only a master it seeded itself**, for the same reason it seeds
only its own — an injected registry is a test fixture and stays one, which is why
`test_api_phase3.py`'s status assertion reads `projected: 0`. A boot that cannot write the master into the
system of record does not serve.

**What the projection faithfully records as empty.** All four seeded mappings project `margin_rate = NULL`
and `fees = {}`, because Stage 7.3's seed specs never carried them — neither word appears in
`instruments/seed.py`. The writer no longer drops those fields; the evidence never contained them.
Filling them in would mean inventing a margin rate and a fee schedule with nothing behind them, so they
stay empty and `test_the_seeded_mappings_have_no_margin_rate_or_fees_to_project` pins that they are empty
for that reason rather than by accident.

The bybit row survives the trip with its reason attached: `status = SUPPORTED` and a note beginning
`GEO-BLOCKED`, naming F-2 and the D-021 VM. The owner's Stage 7 ruling was that the row stays open *and
visible*, and a projection that dropped the note would have made it invisible again in the system of
record while remaining visible in the registry.

### 9.5 L-C — the first `evidence_ref` writer, and the half of F-14 it does not fix

`src/nexus/intelligence/` is a new package — the fifteenth under `src/nexus/`, verified by
`git ls-files 'backend/src/nexus/*/__init__.py'`: 14 before this batch, 15 after — holding `evidence.py`
(279 lines). `dossier` and `memory_item` remain writer-less by ruling: 8.3 and stage 10.

The writer follows §5.1's contract exactly — validate the identity column and raise `PersistenceError` if
it is absent, `assert_no_secrets`, write inside `self._transaction()`, then `_mark` into `op_projection` —
and it is audited as `evidence.recorded`, so it is recoverable from the chain like every other write.
`test_a_missing_projection_is_refilled_from_the_chain` deletes the row, keeps the chain, and asserts boot
recovery restores it field for field.

`dossier_id` is nullable and the writer needs no dossier: the first writer must not depend on the one 8.3
has not built. `test_evidence_can_be_recorded_before_any_dossier_exists` pins that.

**The two timestamps are the content of this batch.** Per D-050 this is F-14's cheap half, so the claim is
narrow and deliberate:

- `retrieved_at` is a **required keyword-only argument with no default**, pinned by inspecting the
  signature. A default of `observed_at` would manufacture a latency of exactly zero; a default of "now"
  would record write time as receipt time. Both would look like measurements, which is worse than a gap.
- `observed_at_source` records whether the observation time really came from the venue. A snapshot with no
  `observed_at` is **refused** unless the caller declares `LOCAL_FALLBACK`; and declaring the fallback
  while passing two *different* timestamps is refused too, because a flag that can be contradicted by the
  row it qualifies is decoration.
- `apparent_latency_seconds` is stored beside them and is **not** a latency measurement. It is
  `retrieved_at - observed_at`, which contains the offset between the venue's clock and ours as well as any
  network delay. A negative value is recorded rather than refused: run 27 measured 1.089 s of venue time
  against 0.298 s of wall clock, so venue clocks run both ways, and a negative interval is evidence about
  the clock rather than an error condition.
- The provenance fields are written **last**, so a caller's payload cannot overwrite them.
  `test_a_caller_cannot_overwrite_the_provenance_fields` passes `apparent_latency_seconds: 999.0` and
  asserts the stored row still carries the computed value.
- `data_status` defaults to `UNAVAILABLE` — the schema default and the fail-closed value — and is validated
  against `DataStatus` (A-06). No vocabulary was extended: the writer's refusals raise `ValueError`,
  following `core.time.iso_utc`, because they are programmer errors at an internal boundary, and a
  `RejectReason` is vocabulary the audit log and the UI both consume. `RejectReason` is unchanged and
  `test_the_reason_vocabulary_was_not_extended` pins that.
- `kind` is passed through as free text. **No vocabulary for it is declared anywhere in the repository** —
  the schema says only `DEFAULT 'DATA'` — and inventing an enum here would put a plausible-looking
  controlled list in front of a distinction nobody has yet drawn.
- `checksum` is computed by the writer over exactly what is stored, so it cannot disagree with the payload.
  It is an **integrity** checksum over the recorded row, not an authenticity signature over the bytes the
  venue sent; nothing in this system can attest to those yet.

  > **Corrected by Stage 8.3 — this is F-21 (§10.3).** The second sentence was false: the checksum
  > covered `payload` alone and not "the recorded row", so two evidence rows differing in `source`,
  > `observed_at`, `retrieved_at`, `locator` and `evidence_id` but sharing a payload produced the *same*
  > value. Nine of the row's eleven stored fields could change undetected, `observed_at` among them. The
  > text is left as published because D-051 was ruled on it; §10.3 records the probe that falsified it,
  > the fix, the test that had pinned the wrong behaviour, and the disclosure that this changes what an
  > approved batch stored.

One defect found while testing the writer, and fixed: a naive `observed_at` raised a bare `TypeError` from
the timestamp subtraction, because `iso_utc`'s own refusal runs *after* the arithmetic. An unclassified
crash at a boundary names nothing — the failure mode F-4 was about — so both timestamps are gated before
they are used, and `test_a_naive_datetime_is_refused_by_name` pins the message.

**F-14 stays OPEN (O-012).** No adapter was touched. `observed_at` is still venue time in all four and no
receipt time exists anywhere in ingestion, so latency remains unmeasurable. What changed is that the
evidence graph no longer *imports* the defect: a row written from now on says which of its two timestamps
came from the venue, and carries the interval with its qualification attached.

### 9.6 The gate

| Check | at 8.1 | at 8.2 |
|---|---|---|
| `ruff format --check src tests` | 82 files | **88 files already formatted** |
| `ruff check src tests` | clean | **clean** |
| `mypy` (strict, `files = ["src/nexus"]`) | 57 files | **60 files, no issues** |
| `pytest` | 1036 passed, 2 skipped | **1117 passed, 2 skipped** |
| `tests/test_repo_hygiene.py` | 83 passed | **83 passed** |
| `test_live_endpoints.py --collect-only` | 49 | **49** |
| offline subset `-k "DiagnosisLogic or PatienceBehaviour or TradeSideRuling or CrossEndpoint"` | 32 | **32 passed, 17 deselected** |

**+81 tests**: `test_schema_fidelity.py` 35, `test_evidence_writer.py` 27, `test_master_projection.py` 16,
`test_migrations.py` 12 → 15. No live endpoint was called; nothing in this batch touches ingestion, so the
live-check count is unchanged at 49 and no run number is published here.

**Superseded after the board was built, and recorded rather than left in the annotations.** That
sentence is true of the batch and not of its commit: the push that carried `11d6db3` triggered CI's
own `venue-verification`, **run 30**, which is recorded in §9.9 with what it adds and what it does
not. None of the 49 checks exercises this batch's code.

### 9.7 Limitations of this batch

1. **The CHECK on `confidence` bounds nothing but "is it a number".** It accepts `'0.5abc'` (which casts
   to 0.5) and `'1e-9'`, but also `'12'`, `'-0.5'` and `'99999999'` — it asks whether the value casts to a
   nonzero number, not whether it is a probability. It is a floor, not a validation, and the range is
   unguarded: whoever writes `memory_item.confidence` in stage 10 must validate the value itself. This is
   the only reason TEXT ordering can diverge from numeric ordering at all (§9.2).
2. **Foreign keys are declared and still not enforced.** `PRAGMA foreign_keys` stays off, for the reason
   `docs/13` §2.5 gives: boot recovery re-projects in chain order, which is not always parent-first, and a
   hard FK failure mid-recovery would be worse than the inconsistency it prevents. 0004 moved
   `dossier.instrument_id` *inside* that limitation; it did not lift it.
   `test_it_is_not_enforced_by_default_and_that_is_recorded` pins that a dangling dossier is still
   accepted at runtime, so nobody reads the new FK as protection that does not exist.
3. **The fidelity test compares SQLite against a target no PostgreSQL server has ever executed.** There is
   no PostgreSQL server or driver in this sandbox, so every statement about the target is a property of
   declared types. The `.sql` files have never been run by anything, here or in CI.
4. **The four seeded mappings carry no economics.** `margin_rate` NULL and `fees` `{}` on all four,
   `contract_size` on one of four. The projection is faithful; the seed evidence is not there.
5. **Nothing calls `record_evidence` yet.** L-C delivered the writer and its contract; wiring it into the
   four adapters is F-14's expensive half and is unauthorised. Until something calls it, `evidence_ref`
   stays empty in production exactly as `dossier` and `memory_item` do.
6. **`/v1/status` gained one key** (`instrument_master.projected`). Two tests asserted that block by exact
   equality and were updated; an external consumer doing the same would see the change.

### 9.8 Decision requested

> **Ruled 2026-11-26 — all four answered `Recommend`, recorded as D-051 (§9.9).** The four
> questions below are the request exactly as it was put and are unchanged; §9.9 carries the ruling
> and what each answer changes.

1. **Is Stage 8.2 approved?** L-A + L-B + L-C as described, with the deviation in §9.2 (TEXT kept, CHECK
   added) and the runner change in §9.3 (F-20) disclosed above. **Recommendation: approve**, and record as
   **D-051**.
2. **What is 8.3?** L-D is the read-only `/v1/intelligence/dossiers` route; L-E is the dossier writer at
   `stance=ABSTAIN`; F-18's cheap half is three `ADD COLUMN`s on `memory_item` (`valid_from`, `valid_until`,
   `change_conditions`) plus `contradicts` on `evidence_ref`. **Recommendation: L-D + L-E only**, and defer
   F-18's columns to the batch that writes `memory_item` in stage 10 — columns no writer populates are
   columns no test can exercise, and this batch is evidence that a nullable column nobody fills is
   indistinguishable from one that was dropped.
3. **F-14's expensive half: authorise it, and when?** The merits, now quantified: run 29 measured the
   wall-clock rate at 3.95× the venue-time rate, so using `observed_at` as a denominator biases a rate
   *downward* by the skew factor rather than merely adding noise. Changing it means giving four adapters a
   real receipt time, which changes what a persisted field means. **Recommendation: authorise it as its own
   batch (8.4), not folded into 8.3** — it deserves its own gate and its own live runs, and folding a
   four-adapter semantic change into a batch that also writes the dossier would make any regression
   ambiguous between the two.
4. **§8's question 4, still unanswered: should finding ids be scoped per stage from Stage 8 onward?**
   F-19 records that F-1…F-7 are already ambiguous between two approved documents, and F-20 continues the
   global sequence. **Recommendation: continue global numbering**, as §8 recommended — a prefix scheme
   introduced halfway creates a second convention to remember, and the collision is now recorded where a
   reader will find it.

### 9.9 D-051 — the four rulings, and the live run this commit's push triggered

All four questions in §9.8 were answered `Recommend`, each against exactly one marked recommendation, and
are recorded as **D-051**. §9.8 is left as it was put; this section is the ruling.

| # | Question as put | Ruled | What it changes |
|---|---|---|---|
| 1 | Is Stage 8.2 approved? | **Approved, recorded as D-051**, with §9.2's deviation (TEXT kept, CHECK added) and §9.3's runner change (F-20) both disclosed | This batch's row in `docs/07` flips to `APPROVED`; **F-15/O-013 and F-16 close as fixed** and **F-20 as found-and-fixed**. The alternative offered — bound the CHECK's range in a follow-up before 8.3 — was **not** taken, so §9.7's limitation 1 stands exactly as published: `confidence` is constrained to "casts to a nonzero number", and `'12'`, `'-0.5'`, `'99999999'`, `'0.5abc'` and `'1e-9'` are accepted. Bounding the range belongs to whoever writes `memory_item.confidence` in stage 10 |
| 2 | What is 8.3? | **L-D + L-E only** | L-D = the read-only `/v1/intelligence/dossiers` route; L-E = the dossier writer at `stance=ABSTAIN`. **F-18's cheap half is deferred** to the stage-10 batch that writes `memory_item`: the three `ADD COLUMN`s (`valid_from`, `valid_until`, `change_conditions`) and `evidence_ref.contradicts` are not landed now. The reason the ruling adopted is this batch's own evidence — `save_venue_mapping` writes `margin_rate=NULL` and `fees={}` for all four seeded mappings and nothing detects it, so a nullable column no writer fills is indistinguishable from one that was dropped |
| 3 | F-14's expensive half — authorise it, and when? | **Authorised as its own batch, 8.4**, not folded into 8.3 | F-14/O-012 stays `OPEN` and is now **authorised** rather than merely re-asked: four adapters get a real receipt time, which changes what a persisted field means. **8.3 does not touch ingestion.** 8.4 gets its own gate and its own live runs, because a regression inside a batch that both writes the dossier and re-stamps four adapters could not be attributed to either half |
| 4 | Should finding ids be scoped per stage from Stage 8 onward? | **Continue global numbering** | F-21 onward continues the sequence; no prefix scheme, so there is one convention and not two. F-19's record of the F-1…F-7 collision between two approved documents stands as the place a reader finds it. This was §8's question 4, put for the first time here and now answered |

**Run 30 — the live run CI triggered on this batch's own commit, recorded rather than left in the
annotations.** Commit `11d6db3` produced three runs and all three are `conclusion=success`:
`45875230477` (`push`, five jobs) and `45875239151` + `45875239156` (`pull_request`). The
`pull_request` event carries `venue-verification`, so a live run happened even though nothing in this
batch calls a venue — §9.6's "no run number is published" was true of the batch and is superseded by CI.
Run 30 is `45875239151`, and its annotation carries:

```
44 passed / 0 failed / 5 geo-blocked / 0 skipped of 49 live checks
PARTIAL - 5 geo-blocked (need a runner outside the restricted region)

okx.cross_endpoint quotes_mid=60490.35 book_mid=60490.35 gap_bps=0.0 dt_observed_s=0.385
                   dt_wall_s=0.249 bps_per_s_observed=0.0 bps_per_s_wall=0.0
                   quoted_spread_bps=0.017 asserts_agreement=False
okx.trades         count=50 price_min=60487 price_max=60490.4 buy=37 sell=13 unspecified=0
dukascopy.layout   passed=True payload_bytes=25761 decompressed_bytes=101480 tick_count=5074
dukascopy.ticks    count=5074 price_min=1.09502 price_max=1.0964 layout_flag=True
binance-vision.parse rows=1440 accepted=1440 rejected=0 timestamp_units=us
dukascopy.probe.*  outcome=network-IngestFault (browser_ua, production_ua, production_ua_other_hour)
```

What it adds, and what it does not. **It is the fourth measured skew and the smallest: 1.55×**
(`dt_observed_s=0.385` against `dt_wall_s=0.249`), beside 3.95× in run 29, 2.6× in run 28 and 3.7× in
run 27.

> **Corrected by Stage 8.3 (§10.4): this is the *seventh* measured skew, not the fourth, and it is not the
> smallest.** Seven runs have published both intervals — `docs/14` §4.1's table holds runs 24–29 and this
> section holds run 30 — and every pair was re-read from its CI annotation on 2026-11-26: 24 = **1.46x** (0.439/0.300), 25 = **2.51x** (0.739/0.294), 26 = **0.80x** (0.238/0.298), 27 = **3.65x** (1.089/0.298), 28 = **2.62x** (0.937/0.358), 29 = **3.97x** (1.170/0.295), 30 = **1.55x** (0.385/0.249).
> Run 26's **0.80×** and run 24's **1.46×** are both below 1.55×, and run 26 is below 1, which is the
> bidirectionality `docs/14` §4.1 already recorded. The quoted **3.95×** for run 29 is that run's *rate*
> ratio (`bps_per_s_wall=0.557` against `bps_per_s_observed=0.141`, `docs/14` §4.1), not its interval
> ratio, which is 3.97×. **The conclusion is unchanged and stronger**: the factor spans 0.80×–3.97×, a
> 5.0× range across seven runs, so it is not a constant and cannot be divided out after the fact. The
> sentence is left as published because D-051 was ruled on it. Both rates are `0.0` because the gap is `0.000` again, so this run yields **no rate comparison**
and adds nothing to run 29's finding that the wall-clock rate is the one that means anything. What it
does add is the point ruling 3 rests on: **the skew factor is not a constant**, so it cannot be divided
out after the fact — giving four adapters a real receipt time is the only way to stop dividing a market
move by somebody else's clock. It breaks no floor either: **0 skips**, so `layout_flag=` is
live-evidenced in run 30 as well as 24, 25, 26, 27 and 29 — six runs, with run 28 the only one that
skipped the check — and dukascopy's three reachability probes returned `network-IngestFault` under both
user agents, as they have since F-8.

Two things this section does not claim. The annotation is truncated at `2713 escaped characters over the
cap`, so the bybit rows sit inside the truncated tail and are **not** quoted here; naming them from a
partial annotation is not something this document does. And run 30 says nothing about this batch's code:
no check in the 49 exercises migration 0004, the projection or the evidence writer, all three of which
are covered by the 1,117 offline tests instead.

---

## 10. Stage 8.3 delivered (D-051): the dossier opens, the route serves it, and one of 8.2's claims turns out to have been false

**Date: 2026-11-26. Authorised by D-051 as L-D + L-E only.**

### 10.0 What was ruled, and what was not

D-051 scoped this batch as **L-D + L-E**: the read-only `/v1/intelligence/dossiers` route and the dossier
writer at `stance=ABSTAIN`. It ruled *out* three plausible additions, and none of them is here:

* **F-18's cheap half is not landed.** No `ADD COLUMN` on `memory_item`, no `contradicts` on
  `evidence_ref`. `memory_item` is still schema-only and still empty, and a test pins both facts.
* **F-14 is untouched.** No adapter changed, no third timestamp exists, O-012 stays `OPEN`. Its expensive
  half is authorised as 8.4 and has not happened.
* **Finding ids stay global**, so this batch's one new finding is **F-21**, not a scoped `S8-F-1`.

What is here: one new module (`intelligence/dossier.py`, 357 lines), three new store members
(`save_dossier`, `dossiers`, `get_dossier`), one new audited event type (`dossier.opened`) in
`writeahead.PROJECTABLE`, two new routes, one correction to what 8.2 shipped (**F-21**), and **141 new
tests**. `backend/` moved **11 files, +2,079 / −24**. Route count: 11 application routes became **13**
(17 handler routes once FastAPI's own four are counted; the OpenAPI schema publishes 12 because
`/metrics` is `include_in_schema=False`).

### 10.1 L-E — the dossier writer, and four decisions it makes on the record's behalf

A writer's defaults are its politics. Everything here defaults to the ABSTAIN side, because this
package's own rule — written in 8.2, before a dossier existed — is that an intelligence record which can
be created without a basis is a record that will be.

```
dossier_id: CASE-0CB572D89F5247D1-MPCJ26KZ   (prefix CASE, which core.ids.new_id has declared
                                              for a research case since Phase 2 and nothing had spent)
audit_ref:  AUD-19285A24053F45CA-HVBA9CPD    PROJECTABLE["dossier.opened"] = dossier
stance: ABSTAIN | state: DRAFT | sufficiency: INSUFFICIENT | venue_maps_instrument: True
created_at: 2026-11-26T20:59:51.934Z | updated_at: 2026-11-26T20:59:51.934Z
stored row: {
  "dossier_id": "CASE-0CB572D89F5247D1-MPCJ26KZ", "instrument_id": "INS-BTC-USDT-USDT",
  "venue": "OKX", "state": "DRAFT", "stance": "ABSTAIN",
  "summary": "Perp basis widening into the US session; watching for a funding flip.",
  "uncertainty": "Sixty seconds of ticker data only, so the regime is unknown.",
  "sufficiency": "INSUFFICIENT",
  "payload": {
    "sufficiency_basis": "one okx ticker and one order-book snapshot, both LIVE, 0.3s apart",
    "sufficiency_target": "V1 evidence and data sufficiency for a research case, not for a trade",
    "venue_maps_instrument": true },
  "audit_ref": "AUD-19285A24053F45CA-HVBA9CPD" }
```

**Decision 1 — `stance` uses `DecisionVerb`, and that is not the treatment `kind` got.** The seven words
ACCEPT/REJECT/WAIT/REDUCE/EXIT/ESCALATE/ABSTAIN are validated. Two things point at that vocabulary and
not at free text: the schema's own default `'ABSTAIN'` is a `DecisionVerb` member and belongs to no other
enum in the repository, and `docs/03` §7 with `docs/10` §3.1 both name exactly this list for the
intelligence layer's disposition. Stage 8.2 left `evidence_ref.kind` as free text *because no vocabulary
for it is declared anywhere*; where one exists and the default is in it, using it is not invention, and
leaving the column open would invite an eighth word for ABSTAIN. The column stays `TEXT` — the writer
enforces this, the schema does not, and a test pins that fact so nobody mistakes the two. Lower case is
refused too: a vocabulary that silently normalises case is a vocabulary nobody has to learn.

**Decision 2 — `sufficiency` stays a string, and a claim has to carry its basis and its target.**
`docs/15` §6's L-E is explicit that sufficiency must stay a string until stage 10 defines the meter, so
no scale is invented here. But `docs/10` §3.1's context rail asks for a *"knowledge-sufficiency meter
with stated basis and what it is sufficient for"*, and §3.2 warns that *"a dossier that records
sufficiency as a bare enum leaves nowhere for V1's outcome to live"*. So two payload keys are pinned —
`sufficiency_basis` and `sufficiency_target` — and claiming anything other than `INSUFFICIENT` without
both is refused. `INSUFFICIENT` needs neither, because it claims nothing. A **numeric** sufficiency is
refused outright under `docs/12` §1.3's law (A-02+A-08), that no gate can be satisfied by a confidence
value: `'0.85'` in this column is a confidence value wearing a judgement's name.

**Decision 3 — a venue the instrument is not mapped on is *recorded*, not refused.** `venue_maps_instrument`
is computed from the master at open time and pinned into the payload, because the two cases mean
different things to a reviewer: a case about a mapped pair is about something this system can observe,
and a case about an unmapped pair is about a gap. Refusing the second would block the research the
Intelligence Centre exists to hold — `INS-EUR-USD` on `OANDA` is a legitimate case today and the master
maps EUR/USD at `DUKASCOPY` only. The flag is a snapshot: nothing re-checks it if the master moves.

```
  master maps INS-BTC-USDT         on BINANCE    as BTCUSDT        DATA_AVAILABLE
  master maps INS-BTC-USDT-USDT    on BYBIT      as BTCUSDT        SUPPORTED
  master maps INS-BTC-USDT-USDT    on OKX        as BTC-USDT-SWAP  DATA_AVAILABLE
  master maps INS-EUR-USD          on DUKASCOPY  as EURUSD         DATA_AVAILABLE
  open(INS-BTC-USDT-USDT , OKX      ) -> venue_maps_instrument=True
  open(INS-BTC-USDT-USDT , BYBIT    ) -> venue_maps_instrument=True
  open(INS-BTC-USDT      , BINANCE  ) -> venue_maps_instrument=True
  open(INS-BTC-USDT      , MT4      ) -> venue_maps_instrument=False
  open(INS-EUR-USD       , DUKASCOPY) -> venue_maps_instrument=True
  open(INS-EUR-USD       , OANDA    ) -> venue_maps_instrument=False   <- a gap, not an error
  open(None              , OKX      ) -> venue_maps_instrument=None
  open(INS-EUR-USD       , None     ) -> venue_maps_instrument=None
  caller tried to forge the flag True -> False
```

**Decision 4 — opening is not editing.** A caller-supplied `dossier_id` that already exists is refused.
The store writes with `INSERT OR REPLACE` because it is a *projection*, so a second "open" would restate
the first row's stance and summary; the audit chain would still hold both events, so nothing is lost
durably, but the row a reviewer reads would no longer be the row that was opened. §5.1's principle —
memory is superseded, never edited in place — is why `memory_item.superseded_by` exists. Changing a
stance is a later batch's verb with its own audit event, not a second call to this one. A test pins that
the store *would* have replaced the row, so the refusal reads as a decision rather than an accident.

**The parent check, and why it is in the writer rather than in the projection.** Migration
`0004_memory_fidelity` gave `dossier.instrument_id` its `REFERENCES` clause back, but
`PRAGMA foreign_keys` is deliberately off (`store/schema.py`'s module docstring: recovery re-projects in
chain order, which is not always parent-first, and a hard FK failure mid-recovery would be worse than the
inconsistency it prevents). So the database accepts a dangling parent without comment, and the writer is
the only thing that refuses one. Demonstrated rather than asserted from the docs:

```
PRAGMA foreign_keys on a fresh connection: 0
PRAGMA foreign_key_list(dossier): [(0, 0, 'instrument', 'instrument_id', 'instrument_id',
                                    'NO ACTION', 'NO ACTION', 'NONE')]
dangling parent, pragma OFF -> accepted, rows: 1
pragma ON                   -> refused: FOREIGN KEY constraint failed
```

This is what makes 8.2's L-B load-bearing rather than decorative. Before the seeded master was
projected there was no parent row for a dossier to point at, and the honest failure would have been
silent:

```
instruments in store before projection: 0
open_dossier(instrument_id="INS-BTC-USDT") ->
  ValueError: instrument 'INS-BTC-USDT' is not in the system of record, which holds 0: [].
  dossier.instrument_id REFERENCES instrument since migration 0004_memory_fidelity, but
  PRAGMA foreign_keys is deliberately off, so SQLite would accept this dangling parent
  without comment — project the instrument first (Stage 8.2's L-B) or open the case with
  instrument_id=None
```

**The refusals, all fifteen, verbatim.** Each is a `ValueError` at an internal boundary except the last,
which is the audit log's own guard; none spends a `RejectReason`, for the reason 8.2 recorded. Every one
of them left the row count and the chain length unchanged.

```
  summary='' (whitespace)      -> ValueError: a dossier needs a summary: it is the thesis in one line, the 'concise rationale' docs/03 §7 permits ...
  stance='MAYBE'               -> ValueError: stance must be one of ['ACCEPT', 'REJECT', 'WAIT', 'REDUCE', 'EXIT', 'ESCALATE', 'ABSTAIN']; got 'MAYBE' ...
  stance='abstain' (case)      -> ValueError: stance must be one of [...]; got 'abstain' ...
  venue='NASDAQ'               -> ValueError: venue must be one of ['BYBIT', 'BINANCE', 'OKX', 'DUKASCOPY', 'MT4', 'MT5', 'CTRADER', 'IBKR', 'OANDA', 'ALPACA'] or None ...
  venue='okx' (case)           -> ValueError: venue must be one of [...] or None; got 'okx' ...
  sufficiency='0.85'           -> ValueError: sufficiency must be a judgement, not a number; got '0.85'. docs/12 §1.3's law (A-02+A-08) ...
  sufficiency='12'             -> ValueError: sufficiency must be a judgement, not a number ...
  sufficiency='1e-9'           -> ValueError: sufficiency must be a judgement, not a number ...
  SUFFICIENT, no basis         -> ValueError: sufficiency='SUFFICIENT_FOR_REVIEW' claims a judgement, so it needs both sufficiency_basis ... and sufficiency_target ...
  SUFFICIENT, no target        -> ValueError: sufficiency='SUFFICIENT_FOR_REVIEW' claims a judgement, so it needs both ...
  ABSTAIN, no uncertainty      -> ValueError: stance=ABSTAIN needs a non-empty uncertainty: the schema's comment is that ABSTAIN is the default and not a fallback ...
  instrument_id='INS-NOPE'     -> ValueError: instrument 'INS-NOPE' is not in the system of record, which holds 3: [...] ...
  instrument_id=''             -> ValueError: instrument_id must be a real id or None; an empty string is neither
  re-open the same id          -> ValueError: dossier 'CASE-0CB572...' already exists, and opening is not editing ...
  payload={'api_secret': ...}  -> SecretMaterialDetected: SECRET_UNAVAILABLE: refused to audit secret material: forbidden key at payload.api_secret
chain length before: 10 after: 10 | dossiers: 1
```

`stance=ABSTAIN` requiring a non-empty `uncertainty` is the one that could look like over-reach, so its
reason is on the record: the schema's own comment is *"ABSTAIN is the default, not a fallback"*, and an
abstention that does not say what is unresolved is a fallback. `docs/03` J-04's exit condition is that
the owner learns *"what would invalidate the thesis"*. A summary is required for the same reason — it is
the "concise rationale" `docs/03` §7 permits and the first thing J-04 step 1 renders, and `state='DRAFT'`
means not yet dispositioned, not not yet described. Both rules are scoped by tests that assert what they
*permit*: the other six verbs need no uncertainty, so the gate is about ABSTAIN and not a demand for prose.

**Timestamps ride inside the event.** The applied schema has no `DEFAULT now()` for `created_at` or
`updated_at` (two of the four defaults §9.1 classifies as a house convention), so a projection that
filled them at write time would restamp a replayed event with the replay's clock — and boot recovery
would quietly rewrite the chronology `docs/10` §3.1 asks the view to show. Tested across a real gap:

```
after wipe: dossier = 0 evidence_ref = 0
reapplied refs: 14
created_at before wipe:  2026-11-26T20:59:51.934Z
created_at after replay: 2026-11-26T20:59:51.934Z
identical: True | payload identical: True
evidence row restored: 1 with checksum verifying: True
```

### 10.2 L-D — the route, the honest empty, and nine gaps it names instead of hiding

`docs/15` §6 scoped this lever as *"read-only, serving what exists and rendering empty honestly"*,
because the Intelligence Centre chrome has been reserved since D-035 with nothing behind it. The
interesting part is not that a 200 comes back. It is that an empty list explains itself, following the
distinction `/v1/data/coverage` already draws between "no archive" and "archive holds nothing":

```
GET /v1/intelligence/dossiers -> 0 dossiers, 9 named gaps
{ "meaning": "no dossier has been opened at all",
  "writer": "nexus.intelligence.open_dossier exists since Stage 8.3 and is audited as dossier.opened",
  "callers": "none yet — nothing in src/ opens a dossier, which is the same limitation Stage 8.2
              recorded for record_evidence. The writer is built and unwired on purpose: wiring it
              means deciding what the system should research, and that is not this batch's ruling",
  "not_a_fault": "the route works and the table exists; an empty list here is an honest empty, the
              distinction /v1/data/coverage draws between 'no archive' and 'archive holds nothing'" }
served_from: operational projection of the audit chain (R-1); the chain is the record
note: a stance is a research disposition and never a trade signal — docs/03 J-04's exit condition is
      'Research completion ≠ trade signal', and live authority is DENIED
vocabularies.stance.values:      ['ACCEPT', 'REJECT', 'WAIT', 'REDUCE', 'EXIT', 'ESCALATE', 'ABSTAIN']
vocabularies.stance.enforced_by: the writer (intelligence/dossier.py); the column is TEXT and the schema does not
vocabularies.sufficiency.values: None
vocabularies.state.values:       None
```

The empty is scoped when the list is filtered, so a filter that matches nothing does not read as a system
that has researched nothing: with one dossier open, `?instrument_id=INS-EUR-USD` answers `"no dossier has
been opened for this instrument"`.

**`view_gaps` is part of the response, not a comment in the source.** `docs/03` J-04 and `docs/10` §3.1
fix what the dossier view must show, and nine of those elements have no column to come from, or only
partly. A route that served what it can and stayed silent about the rest would render as complete:

| Element the approved view asks for | Asked by | Why this route cannot serve it | Moved by |
|---|---|---|---|
| contradictions highlighted and linked | `docs/10` §3.1; J-04 step 4 | needs `evidence_ref.contradicts`; no such column, so nothing records that two sources disagree | **D-051** deferred F-18's columns to the stage-10 writer |
| counter-thesis | J-04 step 1; `docs/10` §3.1 | no column. `uncertainty` is served and is the nearest thing, but "what is unresolved" is not "the case against", and the route does not present one as the other | — |
| publication time in the evidence table | J-04 step 2 | `evidence_ref` holds `observed_at` (the venue's stamp) and `retrieved_at` (our clock at receipt); a source's own publication moment has no column, and F-14 is still open | F-14/O-012 open; its expensive half authorised as **8.4** by D-051 |
| research depth Tier 0–4 | `docs/03` §7; `docs/10` §3.1 | no column, and no tier is defined anywhere in the repository | — |
| freshness | J-04 step 4; `docs/10` §3.1 | partly served, and the part that is not matters: each row's `data_status` is what its writer was told at record time and nothing re-evaluates it against the current clock, so a row recorded `LIVE` stays `LIVE` in the projection forever | — |
| quant result with run id | `docs/10` §3.1 | the run id *is* served — every dossier and evidence row carries `audit_ref` — but no quantitative result is computed anywhere in `src/`, so there is nothing to attach it to | — |
| knowledge-sufficiency meter | `docs/10` §3.1 rail | the basis and the target are served as strings; the meter is not. §6's L-E keeps sufficiency a string until stage 10 defines the meter | stage 10 |
| beliefs with confidence band, validity interval and change conditions | `docs/03` §7; `docs/10` §3.1 | that is `memory_item`: schema-only, no writer, and F-18's three columns do not exist | **D-051** deferred to the stage-10 writer |
| disposition with reason code | `docs/10` §3.1 | the disposition is served as `stance`, but `dossier` has no reason-code column; reason codes live on `DecisionRecord`, and a dossier is not a decision | — |

A test asserts the served dossier **invents none of them** — no `counter_thesis`, `contradictions`,
`tier` or `publication_time` key — because naming a gap is only honest if the response does not also fake
filling it.

**The chronology runs forwards while the store returns newest first.** `store.evidence_refs` orders by
`retrieved_at DESC`, which is right for "what did we lately rely on" and wrong for a chronology, so the
route re-sorts:

```
store order  (evidence_refs): ['okx.ticker', 'okx.books']
route order  (chronology)   : ['okx.books', 'okx.ticker']
   2026-11-26T12:00:00.300Z okx.books   observed=2026-11-26T12:00:00.000Z src=VENUE latency=0.3 status=LIVE checksum_ok=True
   2026-11-26T12:00:02.300Z okx.ticker  observed=2026-11-26T12:00:02.000Z src=VENUE latency=0.3 status=LIVE checksum_ok=True
evidence_count: 2 | evidence_checksums_verify: True
```

`observed_at_source` and `apparent_latency_seconds` are lifted out of the evidence payload beside the
columns, so a reader does not have to know where 8.2 put F-14's qualifications to see them.

**Read-only at the router, not only by convention**, and bounded:

```
  POST   /v1/intelligence/dossiers -> 405      PUT -> 405   PATCH -> 405   DELETE -> 405
  methods registered on both paths: ['GET']
  GET unknown id -> 404 {'detail': 'unknown dossier: CASE-NOPE'}
  GET known id   -> 200
  limit=   1 -> 200     limit= 200 -> 200     limit=   0 -> 422     limit= 201 -> 422
  openapi paths: ['/v1/intelligence/dossiers', '/v1/intelligence/dossiers/{dossier_id}']
```

The unknown id is a 404 and not a successful empty body, because a typo and a case that holds nothing
must not look the same. A detail route exists at all because J-04 step 1 is *"selects case"*.

**`/v1/status` gained no key.** `counts()` has listed `dossier` since Stage 6, so an empty Intelligence
Centre was always observable there; this batch added a view, not another status key — which matters
because §9.7 recorded the one key 8.2 *did* add as a limitation.

```
  top-level keys (14): unchanged
  any key mentioning intelligence or dossier: none
  persistence.counts.dossier      = 1
  persistence.counts.evidence_ref = 2
  persistence.counts.memory_item  = 0
  instrument_master               = {'count': 3, 'active': 0, 'projected': 3}
```

### 10.3 F-21 — the evidence checksum covered the payload, not the row (NEW, found and fixed here)

**Found by this batch's own route probe, and it falsifies a claim 8.2 published.** §9.5 says the
checksum *"is computed by the writer over exactly what is stored"* and is *"an **integrity** checksum
over the recorded row"*. It was not. `record_evidence` hashed `body` — the caller's payload plus the two
provenance keys the writer adds — and nothing else. So two evidence rows recorded with different
`source`, `observed_at`, `retrieved_at`, `locator` and `evidence_id` values but no caller payload
produced the *same* checksum:

```
two rows, no caller payload:
  EV-F34AF48F352 source=okx.books   observed_at=2026-11-26T12:00:00.000Z retrieved_at=...T12:00:00.300Z locator=.../books
  EV-BE947D99BD4 source=okx.ticker  observed_at=2026-11-26T12:00:02.000Z retrieved_at=...T12:00:02.300Z locator=.../ticker
  payload of both: {'apparent_latency_seconds': 0.3, 'observed_at_source': 'VENUE'}
  what 8.2 hashed  sha256(dumps_canonical(payload)):
     row A: 4e3f2bafa9e22a8a429f4a33b07d6bdf
     row B: 4e3f2bafa9e22a8a429f4a33b07d6bdf
     IDENTICAL: True <- the defect: different rows, one checksum
  what 8.3 hashes  evidence_checksum(row), covering 9 fields:
     row A: dab6a4e92c70a081a6583b2e5711d6c5
     row B: 98403ebaf87436adb41dc331f3605e8d
     DIFFER: True
```

Nine of the row's eleven stored fields could change undetected, and `observed_at` was one of them — the
field F-14 exists because of. The 8.2 test that pinned the behaviour was named
`test_the_checksum_is_over_exactly_what_was_stored` and its docstring said *"An integrity checksum over
the recorded row"* while its assertion read `sha256_hex(dumps_canonical(row["payload"]))`: the defect was
enshrined rather than caught, which is the same shape as the `ORDER BY confidence` claim §9.2 corrected —
a plausible sentence published before anything executed it.

**The fix.** `CHECKSUMMED_FIELDS` names the nine covered fields once, `evidence_checksum(row)` recomputes
the value from a row, and `verify_evidence_checksum(row)` compares. The writer uses the same function it
asks readers to use, so the two cannot drift. `audit_ref` is excluded deliberately and the reason is
recorded in the code: it does not exist yet when the writer hashes (L-2 writes the audit entry first and
the ref comes back from it), and the link into the chain is protected by the chain's own hash linkage —
`audit/chain.py` — rather than by this value. A test pins that exclusion so it reads as a decision.

Tampering, written straight into SQLite past every writer, is now detected in all nine fields and
survives restoration; a `NULL` or empty checksum verifies **False**, because an absence of evidence of
tampering is not evidence of integrity; and a reader adding a top-level key cannot change the value while
a reader changing the payload can.

```
    altered observed_at   -> verify=False      altered kind          -> verify=False
    altered source        -> verify=False      altered dossier_id    -> verify=False
    altered retrieved_at  -> verify=False      altered evidence_id   -> verify=False
    altered data_status   -> verify=False      altered payload       -> verify=False
    altered locator       -> verify=False      restored              -> verify=True
    checksum set NULL     -> verify=False
```

**And the route is the first reader that checks.** `_dossier_view` recomputes each row's checksum on the
way out and serves `checksum_ok` per row plus `evidence_checksums_verify` per dossier — `None` when the
dossier holds no evidence, because `all(())` is `True` and a case with no evidence must not report itself
verified. Until this batch the checksum was written and never read, so the value was a decoration; now a
tampered row is reported rather than served. A test tampers with `observed_at` through SQLite and asserts
the *response* says `checksum_ok: false`.

**Disclosure.** This changes what an approved batch stored. Both tables are empty in production — §9.7's
limitation 7 records that the rebuild was proven against rows the tables do not yet hold — so there is
nothing to backfill and no stored value changes meaning under a reader. It is disclosed here rather than
applied quietly, in the same way §9.2 disclosed the `NUMERIC(6,5)` deviation, and it is put to the owner
in §10.6.

### 10.4 Stale numbers: three copies of one count, and a skew series that omitted runs the record already held

Writing this section required the numeric-as-TEXT count again, so it was re-derived from both DDLs rather
than copied: **26 columns across 8 tables are TEXT today, and 19 across 7 were before `0004` added
`venue_instrument_mapping`'s seven**. That confirms §9.1's correction and exposes three places still
carrying the wrong pairing of "19" with "8 tables" — `migrations/0002_memory.sql`'s header and two
comments in `tests/test_schema_fidelity.py`, all three written in 8.2. All three now state both numbers,
and the `TYPE_TRANSLATIONS` comment points at the comparison that re-derives the count instead of trusting
a comment, because a total in a comment is a total nobody re-measures.

```
  target NUMERIC/DECIMAL columns      : 26 across 8 tables
  of those TEXT in the applied schema : 26 across 8 tables     not TEXT: none
  per table: {'decision': 1, 'fills': 3, 'instrument': 1, 'memory_item': 1, 'orders': 4,
              'risk_limit_change': 2, 'trade_intent': 7, 'venue_instrument_mapping': 7}
  without venue_instrument_mapping    : 19 across 7 tables
```

Also corrected, because 8.3 falsified them: §2's inventory row that lists *"the 11 routes"* and says
nothing serves dossiers now carries a pointer to this section, and `docs/13` §2.5's *"tables have no
writers"* is superseded for a second of the three. Both are annotated, not rewritten.

**And one published number turned out to be wrong in a section D-051 was ruled on.** Re-reading the CI
annotations for this batch's board showed that §9.9's *"the fourth measured skew and the smallest: 1.55×"*
is false twice over. Runs 24–30 had all published both intervals at the time of writing — seven, not four —
and two of them are smaller than 1.55×. (Run 31, on the commit carrying this correction, added an eighth;
§10.8 restates the series as a property, because a count that grows with every push is stale the moment it is
written and a range is not.)

| Run | Commit | `dt_observed_s` | `dt_wall_s` | skew |
|---|---|---|---|---|
| 24 | `7929a96` | 0.439 | 0.300 | **1.46×** |
| 25 | `7929a96` | 0.739 | 0.294 | **2.51×** |
| 26 | `ab841c7` | 0.238 | 0.298 | **0.80×** — the smallest, and below 1 |
| 27 | `4fef432` | 1.089 | 0.298 | **3.65×** |
| 28 | `f5e6201` | 0.937 | 0.358 | **2.62×** |
| 29 | `9e70ed3` | 1.170 | 0.295 | **3.97×** — the largest |
| 30 | `11d6db3` | 0.385 | 0.249 | **1.55×** |

*(Run 31, on the commit that carried this correction, added an eighth pair — 0.590/0.251 = **2.35×**. It is
in §10.8's table, which restates the series as a property rather than a count, because a total that
re-triggers on every push is stale the moment it is written. The range does not go stale.)*

Every pair was re-read from the run's own check annotation on 2026-11-26 (`gh api
repos/{owner}/{repo}/check-runs/<job>/annotations`), and the ratios recomputed rather than copied. The table
is a snapshot of runs 24–30; §10.8 carries the series as it stands after run 31. Two
further details the published sentence conflated: the **3.95×** it attributes to run 29 is that run's
*rate* ratio (`bps_per_s_wall=0.557` against `bps_per_s_observed=0.141`, recorded in `docs/14` §4.1), not
its interval ratio; and `docs/14` publishes run 27 as "a 3.7× skew" where 1.089/0.298 = 3.65.

**What survives is the conclusion, strengthened.** The factor spans **0.80×–3.97×**, a 5.0× range across
seven runs, and one run sits below 1, so it is bidirectional as well as non-constant: it cannot be divided
out after the fact, which is exactly the evidence D-051's ruling 3 rests on. A smaller series would have
supported that conclusion less well, so the correction does not weaken the ruling — but the number was
wrong, and the wrong number is what §9.9 published. A correction pointer is inserted there and the ruled-on
text is left intact. The same sentence is repeated in `docs/07`'s 8.2 register row and on board 8.2, and
both now carry the correction too.

### 10.5 The gate

| Check | Command | Result |
|---|---|---|
| Full suite | `.venv/bin/python -m pytest -p no:warnings` | **1,258 passed / 2 skipped / 0 failed** (+141) |
| New: dossier writer | `pytest tests/test_dossier_writer.py` | **87 tests** |
| New: intelligence routes | `pytest tests/test_intelligence_routes.py` | **39 tests** |
| Changed: evidence writer (F-21) | `pytest tests/test_evidence_writer.py` | **42 tests** (was 27, +15) |
| Unchanged: fidelity | `pytest tests/test_schema_fidelity.py` | **35 tests** — no DDL moved, so no checksum moved |
| Repository hygiene | `pytest tests/test_repo_hygiene.py` | **83 passed** |
| Live checks collect | `NEXUS_LIVE_VERIFY=1 pytest tests/test_live_endpoints.py --collect-only -q` | **49** — unchanged, nothing here touches ingestion |
| Offline live subset | `pytest tests/test_live_endpoints.py -k "DiagnosisLogic or PatienceBehaviour or TradeSideRuling or CrossEndpoint"` | **32 passed / 17 deselected** |
| Lint + format | `ruff check src tests` · `ruff format --check src tests` | clean · **91 files already formatted** (was 88) |
| Types | `mypy` (strict) | **Success: no issues found in 61 source files** (was 60) |
| Diff | `git diff --stat HEAD -- backend/` | **11 files, +2,079 / −24** |
| Size | source / tests | **14,938** / **16,074** lines |

No live endpoint was called by this batch. CI's own `venue-verification` will run on the commit that
carries it, as it did for 8.2 (run 30, §9.9); that run is CI's and not this batch's evidence, and no
check in it exercises the dossier writer or the route.

### 10.6 Limitations of this batch

1. **Nothing calls `open_dossier`.** The writer exists, is audited, is projectable and is tested; no
   production code opens a case, because deciding *what* the system should research was not this batch's
   ruling. The route therefore serves an honest empty in every environment, and says so. This is the same
   limitation §9.7 recorded for `record_evidence`, which still has no caller either.
2. **A stance is recorded, never produced.** Nothing in the repository derives a stance from evidence.
   `DecisionRecord` is still never constructed in `src/` (F-17), and a dossier's `stance` is whatever a
   caller passed, validated against a vocabulary and nothing more.
3. **`sufficiency` is a string with no meter.** The basis and the target are pinned and required for a
   claim above `INSUFFICIENT`, but the value itself is not validated against any list, because no list
   exists. Stage 10 defines the meter; until then a caller can write `SUFFICIENT_FOR_ANYTHING`.
4. **`venue_maps_instrument` is a snapshot taken at open.** If the master later maps that venue, the row
   still says `False`. Nothing re-checks it, and a dossier is not re-projected when an instrument is.
5. **Foreign keys are still declared and still not enforced.** The writer refuses a dangling parent and
   the database would not; with the pragma off, a row written by anything other than this writer can
   still point at an instrument that does not exist. §9.7's limitation 2 is unchanged.
6. **The checksum proves integrity, not authenticity, and nothing verifies it on a schedule.** F-21's fix
   makes the value cover the row and gives the route a recomputation, but there is no periodic audit, no
   alert on a `False`, and no signature over the bytes a venue actually sent.
7. **The route reads the projection, not the chain.** A row the projection lost and recovery has not yet
   restored is invisible here; `served_from` says so, and `reproject_missing` is what closes the gap.
8. **The dossier view's nine gaps are named, not filled.** Two of them (contradictions, beliefs with
   validity intervals) are deferred by D-051 to stage 10; one (publication time) waits on 8.4; the other
   six have no ruling behind them at all and no column, and this batch added none.

### 10.7 Decision requested

1. **Is Stage 8.3 approved?** L-D + L-E as described, with the **F-21 correction to an approved batch**
   disclosed in §10.3 — the evidence checksum now covers nine stored fields instead of the payload alone,
   which changes what `record_evidence` stores. **Recommendation: approve**, and record as **D-052**.
2. **What is 8.4?** D-051 authorised F-14's expensive half as its own batch: a real receipt time in
   `okx`, `bybit`, `binance_vision` and `dukascopy`, which changes what `observed_at` means in every
   record type and every test asserting on it. **Recommendation: 8.4 = F-14's expensive half alone** —
   no dossier work, no new tables — because its whole value is that a regression can be attributed to it
   and to nothing else. Its evidence is the measured skew series — **every run from 24 onward that has
   published both intervals, spanning 0.80×–3.97× with one run below 1** (§10.4 and §10.8; stated as a
   range because the count grows with every push) — and it needs its own live runs before and after.
3. **Should anything open a dossier yet?** §10.6's first limitation is that nothing calls the writer.
   Wiring it means deciding what the system researches, which no ruling has covered.
   **Recommendation: not yet** — leave both writers unwired until the verification stages exist (stage 11
   defines V1–V3), and let stage 10's `memory_item` writer be the next thing built, since a dossier with
   no beliefs beside it is a case file with no conclusions in it.
4. **F-21's verification: should it run anywhere other than on a read?** Today `verify_evidence_checksum`
   runs when the route serves a row. **Recommendation: no periodic audit yet**, but record the gap as a
   finding so it is not discovered later as an absence — an integrity check that only runs when somebody
   looks cannot catch a change nobody looks at.

### 10.8 CI's own run on this commit: run 31, and why the skew series is now stated as a property

`ffc4128` triggered three runs, all `conclusion=success`: the `push` run (`45898061044`) and two
`pull_request` runs (`45898067353`, `45898067364`). The second carries `Live public endpoints (O-009 /
O-010)`, which is **run 31** — a live measurement on the commit that delivered this batch. As with run 30,
**no check in those 49 exercises the dossier writer, the route, the projection, migration 0004 or F-21's
checksum**; all of that is covered by the 1,258 offline tests. What run 31 adds is the eighth pair of
interval readings.

```
44 passed / 0 failed / 5 geo-blocked / 0 skipped of 49 live checks
PARTIAL - 5 geo-blocked (need a runner outside the restricted region)

okx.cross_endpoint quotes_mid=60833.95 book_mid=60833.95 gap_bps=0.0 dt_observed_s=0.59 dt_wall_s=0.251
                   bps_per_s_observed=0.0 bps_per_s_wall=0.0 quoted_spread_bps=0.016 asserts_agreement=False
okx.trades         count=50 price_min=60826.1 price_max=60831.7 sides=['BUY'] buy=50 sell=0 unspecified=0
okx.bars           count=100 interval=1m span_hours=1.65 close_min=60639.8 close_max=60836.6
okx.book           depth=40 best_bid=60833.9 best_ask=60834 spread_bps=0.016 entitlement=LIVE
binance-vision.parse rows=1440 accepted=1440 rejected=0 had_header=False timestamp_units=us
dukascopy.layout   passed=True payload_bytes=25761 decompressed_bytes=101480 tick_count=5074 reasons=-
dukascopy.ticks    count=5074 price_min=1.09502 price_max=1.0964 source=DUKASCOPY_BI5 layout_flag=True
dukascopy.probe.production_ua outcome=ok bytes=25761 lzma=True
dukascopy.diagnosis verdict=nothing to diagnose: the production User-Agent works action=none
```

**The skew is 2.35× (`dt_observed_s=0.59` against `dt_wall_s=0.251`).** Four things about run 31 are worth
more than the number:

1. **§10.4 published a total, and the total re-triggered before the ink was dry.** That section corrected
   §9.9's "fourth measured skew" by counting seven runs — and the push carrying the correction produced an
   eighth. This is the exact trap the record's own rule names: a number that re-triggers per push must be
   written as a bound, floor or property, never a total. So the series is restated here as a property:
   **every run that has published both intervals, from run 24 onward, is in the table below; as of
   `ffc4128` that is runs 24–31, and the next push adds another.** The range is what carries the argument,
   and a range does not go stale: **0.80×–3.97×, a 5.0× spread, with one run below 1.**
2. **`gap_bps=0.0` again, so both rates are `0.0` and run 31 yields no rate comparison.** Run 29's
   `0.165` remains a single sample, and the finding that the wall-clock rate is the one that means anything
   still rests on that one measurement.
3. **A fully one-sided trade list passed live again, in the opposite direction.** Runs 24 and 25 returned
   `sides=['SELL'] buy=0 sell=50`; run 31 returns `sides=['BUY'] buy=50 sell=0`. P-7's ruling — record the
   side split and never assert on balance — is now vindicated in both directions across three runs.
4. **The dukascopy probes are not stable run to run.** Run 30 had all three return
   `network-IngestFault`; run 31 has `production_ua outcome=ok` with the diagnosis
   `nothing to diagnose: the production User-Agent works`, and run 27 had `browser_ua ok`. So the probe
   outcome is a property of the moment, not of the code, and no claim here is built on it.

**0 skips**, so `layout_flag=True` is live-evidenced in a seventh run (24, 25, 26, 27, 29, 30, 31) with run
28 still the only one that skipped the check that emits it. The annotation truncates at `2312 escaped
characters over the cap`, so the bybit rows sit inside the tail and are **not** quoted here.

| Run | Commit | `dt_observed_s` | `dt_wall_s` | skew |
|---|---|---|---|---|
| 24 | `7929a96` | 0.439 | 0.300 | 1.46× |
| 25 | `7929a96` | 0.739 | 0.294 | 2.51× |
| 26 | `ab841c7` | 0.238 | 0.298 | **0.80×** — the smallest, and below 1 |
| 27 | `4fef432` | 1.089 | 0.298 | 3.65× |
| 28 | `f5e6201` | 0.937 | 0.358 | 2.62× |
| 29 | `9e70ed3` | 1.170 | 0.295 | **3.97×** — the largest |
| 30 | `11d6db3` | 0.385 | 0.249 | 1.55× |
| 31 | `ffc4128` | 0.590 | 0.251 | 2.35× |

Every pair re-read from its own check annotation and every ratio recomputed, not copied. This table is the
evidence 8.4 starts from, and it is the reason 8.4 needs its own live runs before and after: the quantity it
changes is the one that has moved 5.0× between runs while nothing in the code did.

**Where the series stops being quoted, and why.** The commit that carried this section triggered its own
`Live public endpoints` run — run 32, `conclusion=success`, on a commit that changed documents and design
files and no code — and its numbers are deliberately **not** quoted here. Quoting them would require another
commit, which would trigger another run, whose numbers would then be unquoted for the same reason: the regress
is endless and each turn of it publishes a total that is stale on arrival. That is exactly what the property
phrasing above exists to stop. So the rule this section leaves behind is the rule it follows: **the series is
open-ended, the range is the claim, and the next batch that touches this record picks the table up from
wherever CI has reached** — with every pair re-read from its own annotation before it is written down.
