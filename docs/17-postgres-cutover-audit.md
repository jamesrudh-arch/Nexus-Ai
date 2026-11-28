# 17 — The PostgreSQL cutover, and the audit of it

**Sub-deliverable: the store's second engine, and a full audit of the seam it now runs through.**
Status: `AWAITING REVIEW`. Authorised by the owner's directive of 2026-11-28 — *"Change is from
SQLite to progrel or something that way is even more effective just build it then z.ai would do the
connecting of others okay so finish up and run a proper and full well detailed and solid audit do not
assume anything"* — recorded as **D-058**. Date: 2026-11-28.
Binding inputs: `backend/migrations/0001_core.sql`, `backend/migrations/0002_memory.sql`,
`store/operational.py`, `store/schema.py`, `audit/log.py`, `api/app.py`, R-1 (D-042), D-019 §13.3,
D-026, L-3, and the four promotion triggers T-1…T-4 that `docs/13` §2 records.

---

## 1. What was ruled, and what the ruling does not reach

The directive does three things and this batch does those three things.

**It rules a promotion trigger.** R-1 (D-042) made SQLite the single-node system of record and gated
PostgreSQL on one of four *measured* triggers: **T-1** a second writer process, **T-2** a
benchmarked write ceiling, **T-3** a hypertable or pgvector need, **T-4** the deployment leaving the
single VM. The owner's directive is a ruling, not a measurement, and it is the authority R-1 named as
able to amend it. It fires **T-4**: the system is going somewhere that is not one VM. T-1 and T-2
remain **unmeasured** and this batch does not claim them — no benchmark was run, no second writer
exists, and nothing here is evidence about throughput at any scale.

**It authorises building.** "just build it" is what makes this a batch that writes code rather than a
board that asks. Built: §3.

**It sets a boundary.** "z.ai would do the connecting of others" puts external service wiring outside
this batch. That boundary is also a fact about this environment rather than only an instruction: there
is no route from here to `api.supabase.com`, any `*.supabase.co`, `api.vercel.com` or `api.railway.app`
— egress is allowlisted to github.com, api.github.com, codeload.github.com, registry.npmjs.org,
pypi.org and files.pythonhosted.org. So nothing in this batch connects to a provider, and no provider
credential was requested, received or stored. What *is* delivered is the thing a provider needs in
order to be connected at all: a store that speaks to a PostgreSQL server, selected by
`NEXUS_DATABASE_URL`, refusing to start rather than degrading if the server or the driver is absent.

Four things the directive does **not** authorise, recorded rather than left to be inferred:

1. **It does not change the default engine.** SQLite remains what a fresh checkout and a $0
   single-host install run, because D-019 requires zero cost and a PostgreSQL server is not zero cost.
   `NEXUS_DATABASE_URL` selects the engine; `sqlite:///./data/nexus.db` is still the shipped default
   in `.env.example` and in `docker-compose.yml:145`. Making PostgreSQL the deployment default is a
   question, **Q-5**, and it is the owner's.
2. **It does not reconcile a single divergence between the two engines.** Every difference measured in
   §6 is pinned by a test and recorded as a finding. Reconciling one changes which writes are refused,
   and that is a ruling, not an implementation detail.
3. **It does not touch the phase gate.** `live_trading`, `venue_adapters`,
   `real_money_orders_possible` and `order_capability` are all still `False`, re-asserted by CI's
   structural step and re-run locally (§9.4). Live trading stays hard-off pending the phase gates,
   O-004's Nigerian legal review and owner authority.
4. **It does not carry any existing data across.** There is no copier, no exporter and no import path
   from a SQLite database to a PostgreSQL one. That is **F-37**, and it is the largest operational gap
   this audit found.

---

## 2. Method: nothing in this document is recalled

The directive's last clause is a method, so it is stated as one. Every number below was produced by a
command that ran, in this workspace, against a real server; where a number could have been guessed it
was measured twice, and where a guess was made and found wrong the wrong guess is recorded too
(§4, §5.4). Nothing is quoted from memory, from documentation, or from a previous stage's conclusion.

**The server.** `pgserver` 0.1.4, which bundles **PostgreSQL 16.2** — measured, not assumed, by
`SHOW server_version_num` → `160002`, and asserted `>= 160000` in the suite's session fixture so a
future downgrade of the bundled server fails the build rather than quietly testing something else.
The parity target is written for PostgreSQL 16; `docker-compose.yml:45` ships
`timescale/timescaledb:latest-pg16`, which is PostgreSQL 16 plus an extension, and that difference is
**F-40**, not an assumption that they are the same.

**Why a real server and not a fake.** The reason is in the repository's own history: the six missing
commas in `0001_core.sql` (§4) survived four stages because nothing ever executed that file, while a
test suite that parsed it — `test_schema_fidelity.py`, 896 lines — passed every run. Parsing fidelity
and execution are different claims. `pgserver` exists in this sandbox because there is no docker
binary or daemon here; it is a development and test dependency only and ships nothing to production.

**Why the dependency went into `dev` and not behind `importorskip`.** `.github/workflows/ci.yml:99`
installs `-e ".[dev]"` and nothing else. A parity suite guarded by `importorskip("pgserver")` would
therefore have skipped on every CI run and reported green — a test that never contacted a database
proves nothing about one. So `psycopg[binary]>=3.1` and `pgserver>=0.1.4` are pinned in the `dev`
extra, and **F-39** records what that cost: pgserver publishes no Linux arm64 wheel and no sdist, so
the extra needed an environment marker to stay installable on the production architecture.

**Counts.** `1,587 passed, 2 skipped, 0 failed` for the whole suite; `60` of those are
`tests/test_postgres_store.py` (51 test functions, 60 collected cases through parametrisation) and
`1,527 passed, 2 skipped` is everything else — measured by running the suite with that one file
ignored. The 2 skips are pre-existing and unrelated. The baseline at `608f166` was `1,527/2/0`, so
**no pre-existing test was removed or weakened**: `test_api.py` went 33 → 34 test functions and
`test_schema_fidelity.py` 35 → 36, both measured against `git show 608f166:backend/<file>`.

---

## 3. What was built

| File | Lines | What it is |
|------|-------|------------|
| `backend/migrations/0001_core.sql` | 324 | The portable target: 14 tables, the append-only function, its two triggers, and `row_order` on four tables. **Fixed** — see §4. |
| `backend/migrations/0002_memory.sql` | 127 | `dossier`, `evidence_ref`, `memory_item`. Applied unchanged; it was already valid. |
| `backend/src/nexus/store/pg.py` | 795 | The driver seam. A `sqlite3.Connection`-shaped façade over one psycopg connection: placeholder translation, `INSERT OR REPLACE`/`OR IGNORE` → `ON CONFLICT`, `PRAGMA` mapping, `rowid` → `row_order`, value conversion in both directions, error redaction, and the refusals. |
| `backend/src/nexus/store/postgres.py` | 288 | `bootstrap_schema`, `split_statements`, `PostgresOperationalStore`, `PostgresAuditStore`. |
| `backend/src/nexus/store/operational.py` | 1,438 | Now `SqlOperationalStore` — **52 methods** shared by both drivers — with three seams (`_prepare_storage`, `_open_connection`, `_apply_migrations`) overridden per driver. `SqliteOperationalStore` is 3 methods. |
| `backend/src/nexus/audit/log.py` | 246 | The chain, unchanged in behaviour; its `:name` placeholders are what exposed §5.2. |
| `backend/src/nexus/api/app.py` | 848 | Engine selection by `NEXUS_DATABASE_URL`, fail-closed refusals, and the two fixes in §5.1 and §5.3. |
| `backend/tests/test_postgres_store.py` | 1,153 | 60 cases against a real server. |

L-3 forbids two systems of record for one data class, so this is **one store implementation with a
driver seam**, not two stores. `isinstance(postgres_store, SqliteOperationalStore)` is `False` and
both share the same 52 methods, the same deserialisers and the same refusals. The name
`SqliteOperationalStore` is kept because 101 references across `src/` and `tests/` name it.

---

## 4. F-31 — the portable target had never been executed against any database. `FOUND` and `CLOSED`

`docs/15` §14 and `.env.example:34` both described `backend/migrations/*.sql` as the portable
PostgreSQL target, "kept column-for-column compatible" with the SQLite schema. That description was
load-bearing for R-1: it is the reason promotion was recorded as *gated* rather than *impossible*.

**Measured before the fix.** Both files replayed through the bundled `psql` with
`-v ON_ERROR_STOP=1` on a fresh database:

| | before | after |
|---|---|---|
| tables created from `0001_core.sql` | **2 of 14** | 14 |
| first error | `0001_core.sql:98` | none |
| cause | **6 missing commas**, at lines 96, 154, 155, 188, 220, 221 | — |
| both files, `ON_ERROR_STOP=1` | stops at line 98 | **rc = 0** |
| objects in the database | 2 tables | **17 tables, 34 indexes, 1 function, 2 triggers** |

The function is `audit_log_is_append_only` and the triggers are `trg_audit_no_update` and
`trg_audit_no_delete`. So the append-only property the audit chain claims is, on PostgreSQL, enforced
by the server rather than by application discipline — measured in §8.3.

**Why it survived four stages.** `test_schema_fidelity.py` regex-parses the mirror and asserts
column-for-column agreement with `store/schema.py`. It never executes it, and a missing comma is
invisible to a parser that reads column lists. That is not a defect in the fidelity test — it proves
the claim it was written to prove — but it is the reason the claim "the mirror is a working portable
target" was never tested by anything. **F-27's defect class was checked here and does not repeat**:
`split_statements()` tracks single-quoted literals, dollar-quote tags, `--` line comments and `/* */`
block comments, so a `;` only ends a statement where it actually does. F-27 was `Migration.statements`
splitting on `";"` without stripping comments; the PostgreSQL path does not inherit it.

**Closed by measurement, not by assertion**: both files apply `rc=0`, 17 tables exist, and a second
boot reports `applied == ()` with `already_applied == ("0001_core", "0002_memory")` — idempotent, and
order-independent (both an audit-first and an operational-first opening work).

---

## 5. Three defects this found in code that had already shipped

None of these is in the new driver. All three were in code the repository was already running, and all
three were found by executing the new path rather than by reading the old one.

### 5.1 F-32 — `/v1/status` published the database URL verbatim, and named the wrong engine. `FOUND` and `CLOSED`

`/v1/status` is unauthenticated, because D-026 requires the market-data and status surface to be
public. Its `persistence` block reports where the system of record lives. Two defects, measured on a
live process before either was fixed:

```
persistence.engine = "sqlite"                                              <- hard-coded
persistence.path   = "postgresql://postgres:@/nexus_live?host=/tmp/..."    <- a PostgreSQL DSN
```

The endpoint contradicted itself on the wire: it claimed SQLite while publishing a PostgreSQL DSN
beside the claim. The engine string was a literal in `api/app.py:749`.

The second half is worse than the first. `"path"` came from `getattr(op_store, "path", None)`, and the
base store returns `self._path` — a filesystem path for SQLite, where publishing it is harmless, and a
**DSN** for PostgreSQL, where the shape every managed platform hands out is
`postgresql://user:password@host:5432/db`. Publishing that would have put a live credential on an open
endpoint the first time the owner connected a provider.

**Fix.** `public_dsn()` in `store/pg.py` strips the userinfo and keeps scheme, host, port, database
and query. It is `netloc.rpartition("@")[2]` rather than `urlsplit`'s `hostname` and `port`, and the
reason is measured: `hostname` lower-cases the host, `port` raises on a malformed one, and
`urlunsplit` **drops the `//` from an empty authority** — the first implementation turned
`sqlite:///./data/nexus.db` into `sqlite:/./data/nexus.db`, a different URL that opens nothing. The
shipped version is the input verbatim minus the userinfo, so scrubbing an already-clean target is a
no-op and the function is idempotent (asserted for 10 inputs, including `sqlite:////abs/x.db`,
`postgresql://u:p%40ss@h/db`, `:memory:` and the keyword form). `engine` is now a store attribute:
`"sqlite"`, `"postgresql"`, or `"unknown"` for a subclass that forgets to declare one — which reports
ignorance rather than claiming an engine it did not declare.

**Measured after the fix, live.** The API was booted on
`postgresql://postgres:Sup3rSecret@/nexus_live?host=…` — a real password in the configured URL,
accepted because the local cluster uses trust authentication over its unix socket. Then:

| surface | result |
|---|---|
| all 12 routes, every `GET` swept | **0** contained the password |
| every `text`/`varchar`/`jsonb` column of all **17 tables**, `LIKE '%Sup3rSecret%'` | **0 rows** |
| the audit chain, all 7 records' payloads | **0** contained it |
| `persistence.engine` | `"postgresql"` |
| `persistence.path` | `postgresql:///nexus_live?host=/tmp/pglive/cluster` — no userinfo |

### 5.2 F-33 — a refusal wrote a keyword-form password into the audit chain. `FOUND` and `CLOSED`

`create_app` refuses an unimplemented scheme with `NexusError(..., context={"scheme": url.split(":", 1)[0]})`.
For `postgresql://user:pw@host/db` that yields `"postgresql"` and is safe. psycopg also accepts the
**keyword form** — `host=db password=secret dbname=nexus` — which contains **no colon at all**, so
`split(":", 1)[0]` returned the entire string, password included. That context is not a log line: a
refusal is persisted into the audit chain, hashed, durable, and served to anyone who can open a
dossier. A configuration mistake would have written a live credential into the system of record.

**Fix.** `_scheme_of()` matches a real `^scheme://` prefix and returns `"<not-a-url>"` otherwise,
pinned by a test that asserts `"Sup3rSecret" not in _scheme_of("host=h password=Sup3rSecret dbname=nexus")`.

### 5.3 F-34 — a read left a transaction open that SQLite never opened. `FOUND` and `CLOSED`

Found by asking the server what it was holding, not by reading the code. One live API process, at
steady state after serving reads:

```
before:  ('client backend', 'active', 1)  ('client backend', 'idle in transaction', 2)
```

Two of three client backends were **idle in transaction**. The cause is a genuine semantic difference:
`sqlite3` defers `BEGIN` until a write, so `in_transaction` is `False` after any number of SELECTs —
measured, on the same two reads, `False` — and the store was written against that and never had to end
a read transaction. PostgreSQL opens a transaction on the first statement and holds it until commit.

Consequences on a server-backed database, none of which exist on SQLite: the open snapshot pins
`xmin`, so dead tuples cannot be vacuumed and tables and indexes bloat; and every managed provider
enforces an `idle_in_transaction_session_timeout` that **terminates** the session — after which the
next statement fails, on a connection this store opens once and never re-opens. That is a permanently
broken store until the process restarts.

**Fix.** `reads_only()` classifies a statement on its first word and then on its whole text, and
`PostgresConnection.execute` ends the transaction immediately after a read when no write is pending.
The classifier errs towards calling a statement a write, and the reason is that `save_decision` is
**four statements, not one**: if a read between them ended the transaction the write would be
half-applied. So `WITH x AS (DELETE …)` is a write despite starting with a read keyword, `SET` is a
write because rolling a `SET` back undoes it — and `SET synchronous_commit = on` is exactly what the
`PRAGMA synchronous=FULL` mapping produces — and a literal that merely mentions `delete` keeps the
transaction open, which costs nothing and cannot lose a write.

The fix rests on one property that was measured rather than assumed: libpq transfers the whole result
set on `execute`, so ending the transaction cannot lose rows. Verified element-for-element identical to
the same query left inside its transaction, via `fetchall`, `fetchone`, iteration and `description`.

**Measured after the fix**, four properties, each pinned by a test:

| | before | after |
|---|---|---|
| two reads, live process | 2 sessions `idle in transaction` | **0**; both sessions `idle` |
| `transaction_status` after reads | `INTRANS` | **`IDLE`** |
| after a write, before commit | `INTRANS` | `INTRANS` (unchanged, as it must be) |
| a read inside a write unit | sees the uncommitted row | sees it, **and does not end the transaction** |

### 5.4 The defect this audit made, and what it cost

Recorded because the directive says not to assume anything, and the assumptions made here were wrong
four times before the suite was green. Each was caught by execution:

1. **A subclass spliced into a large module swallowed the base class's body.** `SqliteOperationalStore`
   was inserted *before* `SqlOperationalStore`'s 1,000-line body, so all 52 methods became the
   subclass's and the "shared" base held only `__init__`. Every `PostgresOperationalStore.save_*`
   raised `AttributeError`. **The SQLite suite stayed green** — it only touches the subclass — and only
   a second driver exposed it. Structure is now verified with `ast`, not by eye: base 52 methods at
   line 362, subclass 3 at line 1407.
2. **A load-once catalog cache froze mid-bootstrap.** `bootstrap_schema` applies `0001`, then writes a
   bookkeeping row, which loaded the catalog and froze the schema *before* `0002_memory.sql` existed.
   `memory_item` resolved to 0 columns and every write to it failed with *"cannot choose an ON
   CONFLICT target … 0 constraints fit"*. The cache is now invalidated after DDL and reloaded on a miss.
3. **The write side of type conversion was missing.** jsonb, bool, array and numeric *reads* were
   implemented; the bool *write* was not, and PostgreSQL refused `1` for a `boolean` column.
4. **A driver-internal column leaked into the public API.** Because the store reads with `SELECT *`
   and deserialises with `dict(row)`, `row_order` reached every entity dict and every HTTP response —
   on PostgreSQL and not on SQLite. It is now projected out of results by name, and a test asserts
   `"row_order" not in dict(row)` while the raw driver still sees the column and its monotonic value.
5. **Two tests passed on the CI runner while exercising no PostgreSQL at all, and one failed for a
   reason that was not a defect.** `ci.yml:35` sets `NEXUS_AUDIT_BACKEND=memory` for the whole
   workflow, and `_default_operational_store` answers that by building an ephemeral SQLite store and
   ignoring `database_url` — deliberately, and documented in its own docstring. So the app-boot test
   that asserted `persistence["engine"] == "postgresql"` failed on the runner and passed locally, and
   the app-boot test beside it passed **on both** while testing the in-memory store. The first push of
   this batch went red for exactly that, and the runner's log could not be read from here
   (`results-receiver.actions.githubusercontent.com` is outside this environment's egress allowlist,
   which is O-011 again in a job O-011's fix never covered), so the Pytest step now republishes its
   tail as one error annotation, readable through the ordinary REST API on any host. That annotation is
   how the cause was found. Both tests now clear the variable through `monkeypatch`, assert which
   store they actually got, and the override itself is pinned by a third test — see §9.5. A test whose
   meaning depends on an ambient environment variable is the same class of defect as a test that
   skips: it reports green and proves nothing.

---

## 6. Divergences between the two engines, pinned and not reconciled

Each of these changes **which writes are accepted**, so each is a ruling rather than an implementation
choice. All are pinned by tests in `TestKnownDivergences` so that a future change cannot close one
silently.

### 6.1 F-35 — promotion switches on nine foreign keys. `OPEN`, ruling needed. **The highest-consequence finding in this audit.**

Measured on a fresh database built from the two mirrors, and on the live SQLite store:

| | SQLite (shipped default) | PostgreSQL (mirror) |
|---|---|---|
| `PRAGMA foreign_keys` / enforced constraints | **0** — enforcement is off | **9 foreign keys enforced** |
| tables declaring `REFERENCES` | 8 | 8 |
| a `decision` row with an `instrument_id` that does not exist | **ACCEPTED** | **REFUSED** (`decision_instrument_id_fkey`) |

The nine, from `pg_constraint`: `approval.intent_id→trade_intent`, `decision.instrument_id→instrument`,
`dossier.instrument_id→instrument`, `evidence_ref.contradicts→evidence_ref`,
`evidence_ref.dossier_id→dossier`, `fills.order_id→orders`, `orders.intent_id→trade_intent`,
`trade_intent.decision_id→decision`, and `venue_instrument_mapping.instrument_id→instrument` with
`ON DELETE CASCADE`.

This is the same divergence F-26's residue described from the other side, and promotion closes it **by
accident**: the guards that writers added because SQLite would not enforce anything become redundant on
PostgreSQL, and writes the application has always been able to make become refusals. Note the last one
in particular — `ON DELETE CASCADE` on `venue_instrument_mapping` means deleting an instrument deletes
its mappings on PostgreSQL and orphans them on SQLite. **Q-1** puts the three options.

### 6.2 F-36 — five CHECK constraints differ, in both directions. `OPEN`, ruling needed

| table.column | SQLite | PostgreSQL | effect |
|---|---|---|---|
| `halt_event.scope`, `instrument.*`, `trade_intent.side` | a CHECK | a CHECK | spelling differs only; same writes refused |
| `fills.quantity`, `trade_intent.quantity` | none | **`quantity > 0`** | PostgreSQL refuses a zero or negative quantity SQLite stores |
| `memory_item.confidence` | the leaky 0004 CHECK, which admits `'0.5abc'`, `'1e400'`, `'-0.5'`, `'9.99999'` | **none** | SQLite refuses some writes PostgreSQL accepts |

So promotion is not simply "stricter". Two constraints exist only on PostgreSQL and one only on SQLite,
and the SQLite-only one is the leaky confidence CHECK whose replacement D-057 already ruled: **8.8**
builds `confidence_low` + `confidence_high` with a migration. The mirror deliberately grew **no**
confidence CHECK — a test asserts `"memory_item" not in checks`, because that column set is 8.8's
decision to make and not this file's. **Q-4** puts the options for the other four.

### 6.3 `INSERT OR REPLACE` is not `ON CONFLICT DO UPDATE`. Pinned, deliberately not replicated

20 `INSERT OR REPLACE` and 1 `INSERT OR IGNORE` statements are translated to `ON CONFLICT`. The two are
not equivalent and the difference is not hidden: `OR REPLACE` **deletes and re-inserts**, which churns
the rowid, fires `ON DELETE CASCADE`, and resets every column the statement does not list; `ON CONFLICT
DO UPDATE` updates in place and preserves all three. Replicating SQLite here would mean reproducing an
artifact of delete-plus-insert in a database that does not need it, so the divergence is recorded and
pinned by a test that re-saves a decision and asserts its `row_order` survived.

### 6.4 `rowid` has no PostgreSQL substitute, so four tables grew one

5 statements ordered by `rowid`. There is no equivalent: `ctid` moves under `VACUUM`, and `new_id()`
embeds uuid4, so a primary key is not monotonic — and monotonic order is load-bearing, because halt
history drives boot recovery. So `decision`, `orders`, `execution_result` and `halt_event` carry
`row_order BIGINT GENERATED ALWAYS AS IDENTITY`, verified `is_identity = YES` and preserved across an
upsert (`1 == 1`). It is a **driver-internal** column: projected out of every result (§5.4 item 4), exempted
in `test_schema_fidelity.py`'s `EXEMPT_COLUMNS`, and pinned by a test asserting the schema grew no
other column.

### 6.5 F-38 — `NUMERIC(6,5)` refuses what a `TEXT` column stores. `OPEN`, no batch

`decision.confidence` is `TEXT` on SQLite and `NUMERIC(6,5)` in the mirror. Measured through a real
`NUMERIC(6,5)` column: exact for `'0.5'`, `'-9.9'`, `'9.99999'`, `'0.00001'`, `'100'`; trailing zeros
are lost (`'0.50'` → `'0.5'`, `'1.0'` → `'1'`) because PostgreSQL pads to the declared scale, which is
why `numeric_to_text()` exists on the read path; and **`'10'` stores in SQLite's TEXT column and is
refused by PostgreSQL** with `numeric field overflow`. A promoted database is stricter on exactly the
column D-057 already ruled on: that one-digit-before-the-point ceiling is why F-24's band became two
columns rather than one width. Recorded here because it is a second consequence of the same ceiling, on
a different engine.

---

## 7. F-37 — nothing carries an existing database across. `OPEN`, the largest operational gap

**Promotion is greenfield-only.** There is no exporter, no copier, no import path and no verification
pass from a SQLite database to a PostgreSQL one, and `bootstrap_schema` creates tables; it does not
move rows. The two schemas have also drifted, measured:

| | live SQLite | PostgreSQL mirror |
|---|---|---|
| tables | 16 | 17 |
| migrations | **6**, `0001_operational` … `0006_memory_expiry`, checksummed | **2**, `0001_core`, `0002_memory`, checksummed by `bootstrap_schema` from file stem + SHA-256 of the bytes |
| mirror-only tables | — | `audit_log`, `schema_migrations`, `schema_migration_skips` |
| absent from the mirror | `dossier_0004`, `memory_item_0004` columns | — |

The two migration *sequences* are not the same sequence and share no version numbers, so nothing can
be replayed from one to the other. Today the live SQLite database holds 16 audit records and 3
instruments, so there is very little to lose — which is exactly why this is a question (**Q-2**) rather
than a batch: a copier built now would be built and tested against a database that is nearly empty.
The owner should know that the moment the ledger has data worth keeping, promotion stops being a
configuration change and becomes a migration project.

---

## 8. What was measured, in full

### 8.1 Statement translation — all 15 upserts plan on a real server

Every `INSERT OR REPLACE`/`OR IGNORE` in the store was extracted from the **AST** rather than by regex
— Python joins implicitly concatenated string literals into one `Constant`, which is how `op_projection`'s
concatenated `INSERT OR IGNORE` and the second module, `store/migrations.py`, became visible to the
count at all; a regex over the source found 13 and a first regex over module text matched
`from __future__ import annotations` as a table. All **15** were run through `EXPLAIN` on PostgreSQL
16.2: **0 failures**.

Conflict targets, derived from the catalog and not guessed: `decision(decision_id)` with 18 `EXCLUDED`
columns, `trade_intent(intent_id)` 29, `approval(approval_id)` 8, `instrument(instrument_id)` 15,
**`venue_instrument_mapping(instrument_id, venue, venue_symbol)`** 15, `orders(order_id)` 14,
`fills(fill_id)` 11, `execution_result(intent_id)` 7, `halt_event(halt_id)` 11,
`risk_limit_change(change_id)` 10, `dossier(dossier_id)` 11, `evidence_ref(evidence_id)` 11,
`memory_item(memory_id)` 14. `venue_instrument_mapping` is the one that matters: its upsert omits the
`IDENTITY` column `mapping_id`, so the primary key does not fit and the target falls back to the unique
triple. Choosing the primary key there would have failed every insert, which is why a table whose
constraint the catalog does not imply is **refused rather than guessed** — pinned by a test.

`to_pyformat` traps, all pinned: a `?` inside `'…'` is untouched, a `?` after `--` is untouched, a `?`
inside a quoted identifier `"odd?col"` is untouched. And both of SQLite's placeholder spellings are
translated, because the repository uses both — see §5.2's neighbour below.

**A fourth defect, found by the live boot rather than by the parity suite.** `audit/log.py:161` binds a
dict with SQLite's `:name` spelling; the 219 statements in `operational.py` use `?`. Translating only
`?` left the append with **no placeholder at all**, and boot recovery died with *"the query has 0
placeholders but 8 parameters were passed"* — after the schema had already been created, which is the
worst place to fail. `:name` → `%(name)s`, `::` preserved as a PostgreSQL cast, and SQLite's other two
spellings `@name` and `$name` deliberately **not** translated because neither appears here and both
collide with PostgreSQL syntax (`$1` is a server-side placeholder, `$.field` is a JSON path).
`execute` also grew a mapping path, resolving each named parameter's column type by its own name.
This is recorded inside §8 rather than as a finding because it never shipped: it was caught before the
first commit of this batch, by an end-to-end boot test rather than by a unit test. **The lesson is the
reason `TestTheApiBootsOnPostgres` exists** — a driver can pass every statement-level test and still
fail to boot an application.

`PRAGMA` mapping, measured: `journal_mode=WAL` → nothing, `busy_timeout` → nothing,
`synchronous=FULL` → `SET synchronous_commit = on`, and an **unknown PRAGMA is refused** with *"no
PostgreSQL counterpart"* rather than dropped. 23 PRAGMA occurrences exist in `src/`; only **3** are
ever executed, which is why only 3 are mapped.

### 8.2 Types and the value boundary

Type census of the mirror, from `information_schema`: text 128, timestamptz 29, numeric 26, jsonb 8,
`_text` (arrays) 7, boolean 7, bigint 3, integer 2, date 1. **141 distinct column names**, and
`payload` and `scope` each carry **two different PostgreSQL types** in different tables — so type
resolution is per-table, not per-name, and the adapter resolves it that way.

**15 columns where SQLite stores TEXT but PostgreSQL declares a structured type**: 8 jsonb and 7
`text[]`. Measured at the boundary: jsonb accepts a JSON *string* and reads back a `dict`, so the
adapter must return canonical text — byte-identical to `dumps_canonical` — or `loads_json` breaks on
it, and a test asserts exactly that byte equality; `text[]` **refuses** `'[]'` and `'["a","b"]'` with
*malformed array literal* and accepts a Python `list`; `timestamptz` accepts `'…Z'` and reads back
`datetime` with `ZoneInfo('Etc/UTC')`.

### 8.3 Append-only is a server property on PostgreSQL, and app discipline on SQLite

`audit_log`'s real columns, measured: `seq BIGINT` primary key, `record_id TEXT UNIQUE`, `event_type`,
`actor`, `payload`, `timestamp TIMESTAMPTZ`, `prev_hash`, `record_hash` — all `NOT NULL`, and **no**
`entity_type`, `entity_id` or `action`. On PostgreSQL an `UPDATE` raises and a `DELETE` raises, from
the two triggers; an `INSERT` succeeds. On SQLite the same property is held by application code and by
the tamper proof. That asymmetry is an improvement on promotion and is recorded rather than levelled.

### 8.4 Migrations, idempotence and drift

A second boot against the same database reports `applied == ()` and
`already_applied == ("0001_core", "0002_memory")`. Both an audit-first and an operational-first opening
work, which matters because `create_app` opens the audit store before the operational one — and the
audit store bootstrapping first is why a live `/v1/status` reports `applied: []` with both versions in
`already_applied`: the schema was already there by the time the operational store looked. That was
measured rather than assumed, since `applied: []` on a fresh database looks like a failure and is not
one. The mirror is not checksummed anywhere except by `bootstrap_schema` itself; the SQLite sequence's
six checksums and F-27's statement-count defect are unaffected and unchanged.

### 8.5 Refusals are safe to surface

All four psycopg connection-failure shapes were produced deliberately and their messages read: an
unresolvable host yields *"failed to resolve host 'db-host': [Errno -2]…"* — **which named the host**,
and nothing listening yields *"connection to server at "127.0.0.1", port 5999 failed…"*. The password
never appears in any shape. `_REDACTIONS` is now six patterns covering `password=`, `pwd=`, `//user@`,
`host 'x'`, `host=x`, `server at "x"` and `server at/on x`. And `connect()` is inside the handler:
before that fix a driver fault escaped as a raw `psycopg.OperationalError`, past `app.py`'s
`except PostgresError` and past redaction entirely — a driver error escaping its wrapper is a security
defect, not a robustness one. A missing driver is a **refusal**, not a silent fallback to memory,
pinned by `test_the_missing_driver_is_a_refusal_not_a_silent_fallback`.

---

## 9. The live system

### 9.1 Two engines, side by side

The SQLite API on `:8080` and a PostgreSQL-backed API on `:8090`, both from this working tree, both
serving the same 12 routes:

| route | SQLite | PostgreSQL | bodies |
|---|---|---|---|
| `/healthz` | 200 | 200 | identical apart from `time` |
| `/readyz` | 200 | 200 | **byte-identical** |
| `/v1/status` | 200 | 200 | identical apart from `time_utc` and the `persistence` block |
| `/v1/audit/verify` | 200 | 200 | both `intact: true`, `breaks: []` |
| `/v1/instruments` | 200 | 200 | identical apart from `generated_at` |
| `/v1/instruments/coverage` | 200 | 200 | identical |
| `/v1/intelligence/dossiers` | 200 | 200 | identical |
| `/v1/decisions` | 404 | 404 | no such route on either engine |

`row_order` appears in **none** of the six PostgreSQL response bodies.

### 9.2 The served chain is the stored chain

`/v1/audit/verify` reported `chain_head = 227d274bf9206d69…`, and a direct query of the server's
`audit_log` returned the same head. So the hash the API serves is the hash PostgreSQL holds, not a
recomputation over something else. 7 records, `intact: true`, `breaks: []`, and the boot-recovery
record shows `halt_scope: NONE`, `chain_breaks: []`, `blocks_new_risk: false`.

### 9.3 Restart

`PostgresOperationalStore` closed and re-opened against the same database: `migrations.applied == ()`
(a restart does not re-apply the schema), a decision written before the restart is readable after it
with its verb intact, and `counts()["decision"] >= 1`. A restart is where a promoted database either
survives or does not, so it is a test and not a manual step.

### 9.4 The gates

| gate | result |
|---|---|
| `ruff check src tests` | All checks passed |
| `ruff format --check src tests` | 98 files already formatted |
| `mypy` (strict, `src/nexus`) | Success: no issues found in **65** source files |
| `pytest` | **1,587 passed, 2 skipped, 0 failed** |
| `pytest` in CI's exact environment | **1,587 passed, 2 skipped** — re-run with `NEXUS_AUDIT_BACKEND=memory`, `NEXUS_ENVIRONMENT=DISABLED` and `NEXUS_LIVE_TRADING_ENABLED=false` set exactly as `ci.yml:30-35` sets them, because §9.5 makes the environment part of the behaviour under test |
| CI: phase gate | `live_trading False`, `venue_adapters False`, `real_money_orders_possible False`, `order_capability False` |
| CI: data adapters | all four `read-only, credential-free`; no credential parameter; no order verb |
| CI: paid vendors | none referenced in `backend/src` |
| CI: trading routes | **17 routes, none trading-capable** |

The four CI assertions were run locally from `ci.yml`'s own text rather than paraphrased.

### 9.5 The environment CI runs in is part of the behaviour under test

`ci.yml:30-35` sets three variables for every job: `NEXUS_LIVE_TRADING_ENABLED=false`,
`NEXUS_ENVIRONMENT=DISABLED` and **`NEXUS_AUDIT_BACKEND=memory`**. The third one changes which store
the application builds. `_default_operational_store` treats an explicitly ephemeral audit log as a
request for an ephemeral operational store too, and its docstring gives the reason: *"a durable
operational state next to a volatile record of why it changed would be worse than either choice
alone."* So `NEXUS_AUDIT_BACKEND=memory` **overrides `NEXUS_DATABASE_URL`**, and an app booted with a
PostgreSQL URL under that variable gets `SqliteOperationalStore(":memory:")`.

That is documented product behaviour and it is visible rather than silent — `/v1/status` reports
`engine: sqlite`, `ephemeral: true` and `path: null` — so it is recorded here as a coupling and pinned
by `test_an_ephemeral_audit_backend_overrides_the_database_url`, not raised as a finding. What it does
mean for this audit is narrower and worth stating: **on the CI runner, the app-boot tests do not reach
PostgreSQL unless they clear the variable themselves.** The 60 parity cases do run against a real
server there — measured, not assumed, by the runner's own output: 58 of them had passed before the one
environment-dependent failure stopped the run at `--maxfail=1`. So `pgserver`'s bundled PostgreSQL does
start on `ubuntu-latest`, which is the fact §10.1 needed and had until then only inferred from a wheel
tag.

---

## 10. F-39 and F-40 — what this audit could not run, stated rather than smoothed over

### 10.1 F-39 — the parity suite cannot run on the production architecture. `CLOSED` in this batch, with a residue

`ci.yml:166` records that **the production host is Ampere A1, ARM64**. Measured from PyPI's own
release files:

| package | version | Linux wheels | arm64 | sdist |
|---|---|---|---|---|
| `pgserver` | 0.1.4 | `manylinux_2_17_x86_64` **only**, cp39–cp312 | macOS `arm64` only — **not Linux** | **none** |
| `psycopg-binary` | 3.3.9 | x86_64, `manylinux_2_27_aarch64`, ppc64le, riscv64, musl | **yes**, 18 arm wheels | — |
| `psycopg` | 3.3.9 | `py3-none-any` | n/a, pure Python | — |

So the driver runs anywhere, and the **test server** runs on x86_64 Linux and on macOS only. With
`pgserver` in the `dev` extra and no sdist to fall back on, `pip install -e ".[dev]"` would have
**failed outright** on the production VM and on Python 3.13+. That was a defect this batch introduced
and it is fixed here: the dependency carries an environment marker — Linux requires x86_64, and
`python_version < '3.13'` — so the extra installs everywhere and the suite skips only where no server
can be provided.

**The residue, stated plainly.** CI runs `ubuntu-latest` on x86_64 with Python 3.11, where a matching
wheel exists, so the parity suite **does** run in CI and that is where it is enforced — **measured on
the runner rather than inferred from a wheel tag**: 58 of its cases had passed there before an
unrelated environment-dependent failure stopped the run (§9.5), so the bundled server does start on a
GitHub-hosted runner. On the
production VM it will skip, and a skipped parity test is not a passing one. To stop that from being
silent, CI gained a step that fails the build if this file reports a skip or collects nothing. What
cannot be recovered is parity evidence on ARM64: no ARM64 Linux PostgreSQL was executed anywhere in
this audit. That is a real limit and it is the reason §11 lists it rather than §9 claiming coverage.

### 10.2 F-40 — compose ships TimescaleDB; what was measured is vanilla PostgreSQL 16.2. `OPEN`, low risk, unmeasured

`docker-compose.yml:45` uses `timescale/timescaledb:latest-pg16` and the `postgres` profile is opt-in.
Everything in this document ran on the PostgreSQL 16.2 that `pgserver` bundles, with no extension
loaded. TimescaleDB is PostgreSQL 16 plus an extension, so the mirror's plain DDL should be unaffected
— but "should be" is exactly the kind of claim §2 excludes, and no TimescaleDB instance was reachable
from this environment. `docker-compose.yml:56` also mounts `./backend/migrations:/migrations:ro`, a
path the PostgreSQL image never executes (it runs `/docker-entrypoint-initdb.d`); that mount is now
vestigial, because `bootstrap_schema` applies the same files from the application side at boot, and
`Dockerfile:29` installs the `postgres` extra so the image can. The stale comment at
`docker-compose.yml:46` — *"opt-in: nothing reads it yet"* — is corrected in this batch, because the
code now reads it.

---

## 11. Questions for the owner

Five, each with a recommendation. None is applied: a ruling no question asked for cannot be applied,
and each of these changes behaviour the owner has not yet ruled on.

**Q-1 (F-35) — the nine foreign keys.** Promotion switches on referential integrity that SQLite has
never enforced.
*(a)* Enforce in SQLite too, `PRAGMA foreign_keys=ON`, so both engines refuse the same writes — needs a
sweep of every writer first, because it can refuse writes the application makes today, and it is a
behaviour change to the running system, so its own batch and tamper proof.
*(b)* Drop the nine constraints from the mirror, so both engines agree by having no integrity.
*(c)* Keep the divergence pinned and guard only the writers that can dangle.
**Recommend (a), measured first.** (b) discards the one thing a server-backed database buys, and (c)
leaves two engines permanently refusing different writes, which is the condition R-1 exists to prevent.
But (a) must not be applied blind: the sweep has to run first and report which writes it would newly
refuse, and the owner should see that list before anything is enforced.

**Q-2 (F-37) — carrying data across.** *(a)* Declare promotion greenfield-only and record it.
*(b)* Build a copier with a verification pass now. *(c)* Defer until a database worth carrying exists.
**Recommend (a) now and (b) on a trigger**, the way R-1 handles everything else: today's live database
holds 16 audit records and 3 instruments, so a copier built now would be tested against nothing, and
the honest record is that promotion is currently a fresh start and not a migration.

**Q-3 — connections and concurrency.** No finding id: one connection per process is a shape the
owner has not ruled on rather than a defect, and the repository's discipline is that an un-ruled
authorial choice is surfaced as a question. The store holds **one** psycopg connection
per process, guarded by an `RLock`, and there is no pool: measured, one live API process held 2 client
backends (the audit store's and the operational store's). Every statement in a process therefore
serialises. On SQLite that was forced by a single-writer file; on PostgreSQL it forfeits the server's
concurrency. *(a)* Keep one connection per process. *(b)* Add `psycopg_pool` with a bounded size.
*(c)* One connection per worker process. **Recommend (a) until T-2 is measured**, on R-1's own
discipline: no write ceiling has been benchmarked, so there is no evidence that the current shape is
the binding constraint, and a pool is a new dependency with its own failure modes. Recorded because the
owner should know the shape is a choice and not a law.

**Q-4 (F-36) — the five CHECK constraints.** *(a)* Reconcile all five to the stricter of the two
engines. *(b)* Reconcile to the looser. *(c)* Leave them pinned. **Recommend (a) for the two
PostgreSQL-only `quantity > 0` checks** — they encode an invariant the domain already asserts, and a
zero-quantity order or fill is not a thing the system should be able to store on either engine — and
**defer `memory_item.confidence` to 8.8**, which D-057 already authorised with a migration.

**Q-5 — which engine a deployment runs.** *(a)* Keep SQLite the default everywhere and PostgreSQL
opt-in by URL, which is what is built. *(b)* Make PostgreSQL the default in `docker-compose.yml` and
keep SQLite as the dev and test default. *(c)* Make PostgreSQL mandatory. **Recommend (b)**, because
the directive is a move to PostgreSQL and compose is the deployment path, while D-019's $0 constraint
keeps SQLite as the checkout-and-run default and CI's `NEXUS_AUDIT_BACKEND=memory` path unchanged.
This is the one question whose answer changes a file this batch deliberately left alone:
`docker-compose.yml:145` still defaults to `sqlite:///./data/nexus.db`.

---

## 12. Documents this supersedes, and drift corrected in this batch

Historical stage documents are records of what was decided when and are **not** rewritten; the
amendment is recorded beside them, which is what D-058 in `docs/07` and this document are. The
statements that are now inaccurate, named by line so nobody has to guess:

| where | what it says | status |
|---|---|---|
| `docs/13` §2, lines 76, 101, 169, 203 | PostgreSQL gated on T-1…T-4; "the portable DDL and the `AuditStore` Protocol remain the seam" | Superseded by **D-058**: T-4 ruled, the seam is built. The trigger list itself stands; T-1, T-2 and T-3 remain unmeasured. |
| `docs/15` §14, line 3409 | "`backend/migrations/` stays at two files" | Still true — and now those two files are **executed** (§4). |
| `docs/16` §12 tail | "The next finding id stays F-31" | Spent. **F-31…F-40** are used by this batch and **the next finding id is F-41**. |
| `.env.example` lines 28–40 | "the ONLY scheme this build implements"; "still has no store implementation" | **Corrected in this batch.** Both were false the moment `store/pg.py` landed, and this file is read by operators, not by historians. |
| `docker-compose.yml` lines 25–28, 46 | "remain the portable PostgreSQL target"; "opt-in: nothing reads it yet" | **Corrected in this batch.** The code reads it now. |
| `docs/07:294` | `confidence_text` enforces the portable target's `NUMERIC(6,5)` | Unchanged and now load-bearing twice — see §6.5. |

Nothing in `docs/00`–`docs/06` is contradicted. `docs/06:48`'s finding 34 — *"`core` waits for `db` to
be healthy but never connects to it"* — is now answerable in a way it was not: `core` connects to it if
`NEXUS_DATABASE_URL` says so, and refuses to start if it cannot.

---

## 13. What this audit does not prove

Stated because the directive asked for an audit rather than an assurance, and the difference is the
list of things not covered.

1. **No scale claim of any kind.** No benchmark, no write ceiling, no latency under load, no
   measurement of T-1 or T-2. The suite proves correctness on a quiet server.
2. **No ARM64 Linux PostgreSQL was executed** (§10.1), and the production host is ARM64.
3. **No TimescaleDB was executed** (§10.2), and compose ships TimescaleDB.
4. **No managed provider, no TLS, no network partition, no connection termination.** The server was
   local, over a unix socket, with trust authentication. `sslmode`, connection retry and reconnection
   after a server-side kill are **not implemented and not tested** — which is why F-34 mattered: a
   provider that terminates an idle-in-transaction session would break a store that never re-opens its
   connection, and that recovery path does not exist.
5. **No concurrency measurement.** Two processes writing at once was not exercised, because no second
   writer exists (T-1).
6. **No data migration** (§7), because none is built.
7. **The parity suite covers the store, the driver and the app's boot path.** It does not cover the
   ingestion, intelligence or risk pipelines against PostgreSQL; those reach the database only through
   the store, so they are covered transitively and not directly.

---

## 14. Next

The five questions in §11 go on the board beside **8.8** and **stage 10**, which D-057's ruling 4
already put on one combined board. Nothing in this batch closes a finding it opened: F-31…F-34 and
F-39 are closed **by measurement recorded above**, and F-35…F-38 and F-40 stay `OPEN` with the ruling
each one needs named. External service wiring — Supabase, Vercel, Railway — is z.ai's, per the
directive, and needs from this repository only `NEXUS_DATABASE_URL` and the fact that a missing server
is a refusal rather than a silent fallback to memory.
