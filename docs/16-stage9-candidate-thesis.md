# Stage 9 — Candidate thesis: the seam settled first, then the writer that needed it

**Sub-deliverable 9.1 — F-26's seam settled, and the candidate-thesis writer.** Status: `AWAITING REVIEW`.
Authorised by **D-056**'s ruling 3 (Stage 9 opens, and F-26's seam is settled inside it *as its first
deliverable*) and ruling 4 (two batches concurrently against one combined board; the gate, the tamper
proof, the register rows and this record stay per-batch). Date: 2026-11-28.
This is batch **A** of the two D-056's ruling 4 authorised. Batch **B** — 8.8, F-24's confidence band —
is measured in §10 and is **not built**, because the shape it would build is a migration and the shape
was never ruled.

---

## 1. What Stage 9 is, and what authorised it

Two sources, and they agree. `design/build_board52.py:73` is the only stage map in the repository, and
its P-2 decision path opens:

> `("Candidate thesis", "intelligence dossier (stage 9) · evidence set + uncertainty · ABSTAIN is the
> default record")`

with steps 2 and 3 — *"Knowledge sufficiency · stage 10"* and *"Verification gates · stage 11 · three
gates between thesis and execution (A-08) · planned"* — and P-2's law recorded beside them: *"Steps 2–3 are planned and drawn
dashed in the diagram until Stage 11 delivers them."* `docs/12` §1.3 supplies the two ADRs the path is
built under: **A-02**, *risk-engine isolation as architectural law: deterministic, fail-closed on missing
inputs, confidence never a satisfied requirement*, and **A-08**, *intelligence reaches execution only
through the verification engine's three gates; no agent holds an execution credential*.

D-056's ruling 3 is what makes this batch Stage 9 rather than another 8.x: *"Stage 9 opens, and F-26's
seam is settled inside it as its first deliverable — Stage 9 is the first code that would write `decision`
or `trade_intent` rows, so the seam is answered before that writer exists."* The ruling **schedules** the
seam decision; it does not make it, so F-26 was still `OPEN` when this batch started. §2 makes it, and
§2.6 records why the answer is a **correction** to the finding rather than a closure of it.

The writer lives at `src/nexus/intelligence/thesis.py` — 521 lines — and not beside
`domain/decision.py`, for two reasons that are both checkable: `intelligence/__init__.py:1` already
claims *stages 8–10*, and a thesis is step 1 of P-2's intelligence-to-execution path. The domain
dataclass is the shape of the record; this package is the discipline around writing one.

## 2. The seam, measured — F-26's answer

F-26 was recorded in `docs/15` §13 as a question Stage 9 would have to answer:

> *"either those writers gain a store in the seam so a parent can be checked before a row is written, or
> the trading path accepts that its parents are checked **upstream** in whatever produces a
> `DecisionRecord` and says so in a document instead of leaving it to be inferred from five unguarded
> `REFERENCES` clauses."*

The measurement says the question as posed offered a choice that does not exist.

### 2.1 There is one seam and two doors onto it

`save_decision` is not a competing seam. Its body is four statements:

```python
payload = asdict(record)
payload['state'] = record.state.value
payload['verb'] = record.verb.value
self.save_decision_payload(payload, audit_ref=audit_ref)
```

and its last statement *is* the payload door. `save_intent` has the same shape in three statements
(`asdict`, then `payload['digest'] = intent.digest()`, then the delegate) and `save_approval` in one —
`self.save_approval_payload(asdict(approval), audit_ref=audit_ref)` — so the three doors are not
identical and pinning one body for all three would have been a false measurement. What all three share,
and all the seam's answer rests on, is that the domain object is flattened with `asdict` and the write
happens in the payload sibling. `project()` already calls the three payload siblings
(`writeahead.py:78-83`), so the write-ahead path never touched the domain doors at all.

**Answer: the second of F-26's two options, at no cost.** Parents are checked upstream, in the writer,
and this document says so. No store method's signature moves, because none needed to: `thesis.py` builds
a complete payload and hands it to `write_with_audit`, exactly as `open_dossier`, `record_evidence` and
`record_memory_item` have since Stages 8.3, 8.2 and 8.5.

### 2.2 What could have broken by widening a signature, and why nothing did

F-23 was the finding that a protocol growing a method silently breaks implementations in modules the
offline suite cannot import. The scan that answers it counts *definitions across all classes* in `src/`
and `tests/` rather than searching for subclasses, because a `Protocol` is conformed to structurally and
a fake implementing every method would never appear in a subclass search. Across all **95** Python files in `src/` and `tests/` it finds:

| method | definitions | where |
|---|---|---|
| `save_decision`, `save_intent`, `save_approval`, `get_decision` | **2** each | the protocol's declaration + `SqliteOperationalStore` |
| `save_decision_payload` | **3** | the two above **plus** `FlakyStore` in `tests/test_boot_recovery.py:62` |
| `save_intent_payload`, `save_approval_payload` | **2** each | the protocol + the store |

**This corrects a measurement this batch had already recorded.** An earlier pass over the same scan
reported *"no structural fakes anywhere in `src/` or `tests/`, so F-23's blind spot does not apply"* —
wrong, and wrong in the direction that flatters the change. There are two: `FlakyStore` and
`HaltBlindStore`. They do not bite, but for a reason that has to be stated rather than assumed: each
overrides exactly **one** method and forwards every other attribute through `__getattr__` to a real
`SqliteOperationalStore`, so a method the protocol grows resolves through them without either being
edited. A fake that *enumerated* the protocol would have to be updated, and a batch that forgot to would
have failed in a module this suite skips — F-23 exactly. `test_thesis_writer.py` pins both halves: the
count, and that each wrapper defines `__getattr__` plus one override.

### 2.3 What the writer actually touches on the store

Asserted against `thesis.py`'s own AST rather than by patching the store, because patching cannot tell
the writer's call from the projection's — `project()` calls `save_decision_payload` on purpose, and that
call is the seam working rather than being bypassed. The complete set of store attributes the writer
reads is:

```
['get_decision', 'get_evidence_ref', 'instruments']
```

All three are reads. The writer never writes the store.

### 2.4 The five foreign keys F-26 named, and where each is guarded now

`docs/15` §13.5 inventoried nine declared foreign keys and named five as having no writer that *could*
guard them. Stage 9 changes one of the five:

| foreign key | written by | guarded in the writer? |
|---|---|---|
| `decision.instrument_id → instrument` | **`thesis.py` (this batch)** | **yes** — `_resolve_instrument`, against `store.instruments()` |
| `trade_intent.decision_id → decision` | nothing (no intent writer exists) | no writer, so nothing to guard |
| `approval.intent_id → trade_intent` | nothing (no approval writer exists) | no writer, so nothing to guard |
| `orders.intent_id → trade_intent` | projection only (`operational.py:734`) | upstream, in whatever emits `order.state` |
| `fills.order_id → orders` | projection only (`operational.py:826`) | upstream, in whatever emits `fill.recorded` |

`PRAGMA foreign_keys` remains deliberately off (`docs/13` §2.5), so every one of those guards is a writer
guard or nothing. F-25's precedent is followed exactly: two separate refusals, because an empty string is
neither an instrument nor `None`, and a name the master has never held is a dangling parent — different
mistakes, different messages, and the second one names what the master *does* hold (`INS-BTC-USDT`,
`INS-BTC-USDT-USDT`, `INS-EUR-USD`) rather than saying only "not found".

### 2.5 F-29 — the getter the protocol never declared

`OperationalStore` declares **36** methods, and one asymmetry in them was invisible until a writer needed
it: every entity the protocol serves declares its single-row getter — `get_intent`, `get_dossier`,
`get_evidence_ref`, `get_memory_item` — and `decision` did not, although
`SqliteOperationalStore.get_decision` has existed since Phase 2. Nothing noticed because nothing wrote a
decision: it is a *writer* that has to ask whether an id is already taken, and `record_thesis` is the
first. A fake conforming to the protocol would have passed `mypy` and raised `AttributeError` on that
guard — F-23's blind spot inverted, an implementation holding a method the protocol never declared.

**F-29 is fixed here, and fixing it moves no signature:** the method already existed with exactly the
declared shape. The protocol now declares **37**. `test_thesis_writer.py` reads the declaration from
source with `ast` rather than from `__protocol_attrs__`, which arrived in Python 3.12 and is an empty set
on the 3.11 this suite runs on — a check built on it would have passed by asserting that nothing is
declared, and did, on the first run of this sweep.

### 2.6 F-26 becomes a CORRECTION, not a closure

F-26 is answered and **stays `OPEN`**, for two reasons. D-056's ruling 3 scheduled the decision and did
not make it, so the finding closes on the owner's ruling and not on this batch's measurement; and a batch
does not declare its own finding closed. The precedent for the label is F-15 at `docs/07:379` —
**F-15 CORRECTED** — because the finding as recorded was partly wrong: it described `save_decision`,
`save_intent` and `save_approval` as three seams needing a store in the signature, and they are one seam
with two doors, reachable without moving anything.

What survives of F-26 is narrower and is still true: `DecisionRecord.instrument_id` is `str | None` with
no validation, so a dangling instrument stays *representable* in the domain object, and
`store.save_decision(record)` still accepts one. That is the posture `docs/15` §13.7's limitation 3
already publishes for the store layer, and Stage 9 does not change it — it changes what happens upstream
of it. Four foreign keys from §2.4 remain unguarded by any writer, and three of those have no writer at
all.

## 3. F-28 — `decision.recorded` has two producers, and they disagree

`decision.recorded` has been registered in `PROJECTABLE` and read by `save_decision_payload` since the
write-ahead path was built, and nothing in `src/nexus` ever emitted it. The only two ways to build its
payload in this repository produce different payloads:

| producer | keys | carries `rationale` | carries `created_at` |
|---|---|---|---|
| `asdict(record)`, via `save_decision` | **18** — every `DecisionRecord` field | yes | yes |
| `DecisionRecord.to_audit_payload()` | **14** | **no** | **no** |

`to_audit_payload()` withholds four keys the projection reads: `rationale`, `risk_check`, `created_at`,
`updated_at`. The first is deliberate and **pinned** — `tests/test_core_guarantees.py:498`,
`test_audit_payload_has_no_free_text_model_output`, asserts `"rationale" not in payload` — so F-28 cannot
be closed by adding the four keys, and this batch does not try. The method has **zero call sites** in
`src/` or `tests/` other than that one assertion.

The other three are not deliberate, and their absence is measurable. `write_with_audit` audits and
projects *the same* payload, so a caller that audits the fourteen-key one has written an audit entry that
cannot reproduce its own row. Measured, not inferred:

| payload written through `write_with_audit` | first projection | after `DELETE` + 1.05 s + `reproject_missing` | columns differing |
|---|---|---|---|
| `DecisionRecord(rationale=…, reason_codes=("C",)).to_audit_payload()` | `rationale=''`, `created_at=…10:28:59.089Z` | `rationale=''`, `created_at=…10:29:00.142Z` | **2** — `created_at`, `updated_at` |
| `record_thesis(rationale=…, confidence="0.42")` | `rationale="Perp basis on INS-BTC-USDT runs wide…"`, `created_at=…10:36:06.381Z` | byte-identical | **0** |

The mechanism is `operational.py`'s own fallback: `_text(payload.get("created_at")) or now`. A payload
without the key gets the *projection's* clock, and on a replay that clock is later than the write's.

**F-28 is recorded, `OPEN`, no batch, and not fixed here** — the fix would be to `to_audit_payload()`,
which a pinned test forbids, and the finding is about the disagreement rather than about either producer.
What this batch does is not have it: `intelligence/memory.py:456` already carries the remedy as a
comment — *"The timestamp rides in the event, so a replay reproduces the row it first wrote instead of
restamping it with the replay's clock"* — and `thesis.py` carries the same sentence and the same
behaviour. Both are pinned, the comment in both files and the behaviour by the byte-identical replay
above. Tamper site **T12** drops `"created_at": now` from the event and the suite catches it; **T13**
empties `"rationale"` and the suite catches it.

`rationale` riding in the event is not a relaxation of the pinned refusal. `docs/03` §7 permits
*"Auditable evidence + structured findings + concise rationale only"* and forbids hidden
chain-of-thought, and `open_dossier` has audited free-form `summary` and `uncertainty` since Stage 8.3 —
its own docstring draws the line this writer follows: prose belongs in a named field, and *"no prose
reasoning is smuggled into `payload`"*. `decision` has no `payload` column at all (§5), so there is
nowhere to smuggle into.

## 4. What the writer refuses, and the one law behind each refusal

Five approved sources say the same thing about a record written at step 1 of the path: **A-02** and
**A-08** (`docs/12` §1.3), **P-2's failure text** (*"no gate can be satisfied by a confidence value —
confidence is an input the risk engine may ignore; a missing input denies; … ABSTAIN is a complete
outcome, not an error state"*), **J-04's exit condition** (`docs/03`, ending *"Research completion ≠
trade signal"*), and **`docs/10` §3.2** (*"any FAIL ends the candidate with a reason code; confidence
never overrides a failed stage"*, with the three stages' *"definitions finalise at Stage 11"*).

### 4.1 Four verbs permitted, three refused — each refusal its own message

`decision.verb` is free `TEXT` with **no `CHECK` and no `DEFAULT` in either DDL**, so the boundary is
enforced nowhere below this writer. Every `DEFAULT 'ABSTAIN'` in the repository is on a `stance` column —
`schema.py:291`, `schema.py:373`, `migrations/0002_memory.sql:50` — and the ABSTAIN default comes from
`DecisionRecord.verb`, a Phase-2 domain default, not from the schema.

| permitted (4) | refused (3) | the reason, which is not shared |
|---|---|---|
| `ABSTAIN` (the default), `REJECT`, `WAIT`, `ESCALATE` | `ACCEPT` | ACCEPT is the verb by which intelligence reaches execution; **A-08** puts three gates in between and `docs/10` §3.2 puts their definitions at Stage 11 |
| | `REDUCE` | REDUCE proposes a smaller size, and sizing is the risk engine's — `DecisionState.REDUCED`'s own comment is *"risk engine cut size to fit limits"*; **A-02** keeps the engine deterministic and P-2's law keeps model I/O out of it |
| | `EXIT` | EXIT closes an open position and nothing is open: this writer writes no `trade_intent` row, and A-08 is why |

The four sets partition the vocabulary exactly — `THESIS_VERBS ∪ GATED_VERBS == set(DecisionVerb)`,
disjoint, 4 + 3 = 7 — and the partition is pinned so a seventh word cannot arrive silently. Tamper
**T19** folds the three refusals into one shared message and the suite catches it, which is the point of
asserting three distinct messages rather than three refusals.

### 4.2 Six states permitted, six refused

| permitted (6) | refused (6) | why |
|---|---|---|
| `PROPOSED` (the default), `WAITING_DATA`, `REJECTED`, `CANCELLED`, `ABSTAINED`, `FAILED` | `WAITING_APPROVAL`, `APPROVED`, `REDUCED`, `EXECUTED`, `PARTIALLY_EXECUTED` | all five are past A-08's gates or are the risk engine's own outcome |
| | `EXPIRED` | refused for a **different** reason, with its own sentence: it needs an expiry reader, and Stage 8.7 added `memory_item.expires_at` with no reader and published the column as inert rather than implying a policy |

One rule, two enumerated consequences, both pinned — `THESIS_STATES ∪ GATED_STATES == set(DecisionState)`,
disjoint, 6 + 6 = 12.

### 4.3 Three columns absent from the signature, not accepted and ignored

`intent_id`, `risk_check` and `expires_at` are columns on `decision` and are **not parameters**. Each is
left at what the projection's own defaults produce (`NULL`, `'{}'`, `NULL`), and `ThesisReceipt` echoes
all three so the omission is visible to the caller rather than only to a reader of the source. The
justifications: A-08 for `intent_id`, A-02 for `risk_check`, and for `expires_at` what Stage 8.7
measured. `test_thesis_writer.py` pins the absence **against the signature** — a parameter added later is
a scope change and shows up there first — following `docs/15` §12's discipline that an absence should be
a decision a reader can argue with. Tamper **T16** adds `intent_id` as a parameter and is caught; **T21**
drops it from the event and is caught, by the test that asserts the event carries all nineteen columns'
keys minus `audit_ref`.

One claim in that justification was **narrowed by measurement** rather than left as written. Expiry
readers *do* exist in `src/`: `execution/intent.py:115` and `:146` both compare
`parse_iso(self.expires_at) <= reference`. What does not exist is any comparison of an expiry **read back
from the store** against a clock — so `memory_item.expires_at` is inert, as `docs/15` §14.8 limitation 1
says and D-056's ruling 1 re-affirmed, and `decision.expires_at` would be too. The test scans for
*ordering* comparisons only, because `memory.py:380`'s `expires_at is not None` is a writer deciding
whether an expiry was supplied, not a reader deciding whether one has passed, and counting it would have
made the test pass for the wrong reason.

### 4.4 Confidence is an input and never a gate

`decision.confidence` is `TEXT` on SQLite and `NUMERIC(6, 5)` in the portable target at
`migrations/0001_core.sql:112` — the same pair `memory_item.confidence` has — so the boundary check is
the one Stage 8.5 built and Stage 8.7 tested with 27 inputs, imported rather than reimplemented. One
opinion about one type, not two. It refuses a magnitude PostgreSQL would reject (`10`, `47`, `-12.5`) and
a scale it would silently round (`1e-6`, `0.999999`), and — as **D-054** ruled — it bounds **no range**:
`0`, `1`, `0.42`, `-0.4`, `1.1` and `9.99999` all store. A `float` is accepted because
`DecisionRecord.confidence` is typed `float | None`, and is stringified through `Decimal(repr(...))`
before the check so the value that lands is the value that was checked.

`domain/decision.py:59` comments this column *"0..1, calibrated"* and **nothing in the repository
enforces that comment on either table**. This writer does not start; the comment is recorded here as a
claim that is published and unenforced, in the same family as F-24.

That confidence is never a gate is asserted directly: the lowest and the highest value the target can
hold both record `verb=ABSTAIN, state=PROPOSED`.

### 4.5 ABSTAIN is the default record and not a fallback

`build_board52.py:73` makes ABSTAIN the default record and P-2's failure text makes it a complete
outcome, so it has to say what it is complete **about**: `verb=ABSTAIN` requires at least one reason
code, on `docs/10` §3.1's *"disposition + reason code"* and §3.2's *"any FAIL ends the candidate with a
reason code"*. The three non-ABSTAIN permitted verbs require none, and that permissiveness is asserted
too — a gate nobody has tested for permissiveness is a gate nobody can tell from a bug.

No vocabulary for these codes exists yet, because §3.2 puts their definitions at Stage 11, so they are
free text for the same reason `evidence_ref.kind` was left free text in Stage 8.2: where no vocabulary is
declared anywhere, inventing one is the larger mistake. Duplicates and order are preserved because
`DecisionRecord.transition` appends without deduplicating.

**The writer asks for a reason code and not for an uncertainty, and says so in the refusal**, because
`decision` has no uncertainty column — §5. A code is a label, not a statement of what is unresolved.

### 4.6 The parent guards, and one integrity rule of this writer's own

`rationale` is required and stripped; the schema's `DEFAULT ''` would store an empty one without comment.
`venue` is validated against the `Venue` enum as `open_dossier` has validated it since Stage 8.3, and
`Venue` is **case-sensitive** — `venue="okx"` is refused, which an early draft of this batch's test got
wrong. `instrument_id` and both evidence columns are checked against the store. A caller-supplied
`decision_id` that already exists is refused, because the store writes with `INSERT OR REPLACE` and a
second record would restate the first row's verb, state and rationale while the audit chain kept both
events — `open_dossier`'s refusal, and the guard F-29 was declared for.

One rule is this writer's own rather than inherited: **an evidence id may not appear in both
`evidence_refs` and `counter_evidence_refs`.** `docs/10` §3.1 asks for contradictions *"highlighted and
linked"*, and a source listed on both sides renders as a source arguing with itself, which tells a
reviewer less than either citation alone. The refusal names **every** such id and not just the first, and
points at `evidence_ref.contradicts`, which has existed since Stage 8.6, as the way to record a real
disagreement. A duplicate on *one* side is kept: a source cited twice is a claim the caller made twice.

## 5. F-30 — the stage map's "uncertainty" has nowhere to live, and the fix is a migration

`build_board52.py:73` asks Stage 9 for *"evidence set + uncertainty"*. Measured against the live schema:

| table | columns | `uncertainty` | `payload` | free-form JSON |
|---|---|---|---|---|
| `decision` | **19** | **no** | **no** | `risk_check` — the risk engine's |
| `dossier` | 12 | **yes** | yes | `payload` |
| `trade_intent` | 30 | no | yes | `payload`, plus `evidence_summary` and `counter_case` |

The evidence set has two columns, `evidence_refs` and `counter_evidence_refs`. The uncertainty has none,
and `decision` is the only one of the three tables on this path with no `payload` column to pin a key
into — which is also why `rationale` is the only home for a thesis's prose and why §4.6 requires it. The
gap is between two approved artifacts, not between an artifact and an invention: the stage map asks for
it and the schema built in Stage 6 has nowhere to put it.

**F-30 is recorded, `OPEN`, and asked rather than decided**, for one reason: every remedy is a migration,
and a migration is the one artifact this repository has measured itself unable to take back. F-27's count
is a row written at apply time and never rewritten, so a shape chosen here and ruled differently later
would split production into two populations reporting different counts for the same version and checksum
— D-056's ruling 2, applied to this batch's own fork. The options and their costs are §10's question 2.

Until it is ruled, this writer stores what `decision` can hold and publishes the rest: the reason code
requirement of §4.5 is a **substitute**, not a fulfilment, and the refusal message says so.

## 6. What was built, and what it costs

| | before | after |
|---|---|---|
| `src/nexus` | 62 files / 16,347 lines | **63** files / **16,903** lines |
| `tests/` | 31 files / 19,857 lines | **32** files / **20,843** lines |
| gate | 1,428 passed / 2 skipped / 0 failed | **1,527** passed / 2 skipped / **0** failed |
| `ruff check src tests` | clean | clean |
| `ruff format` | 93 files | **95** files |
| `mypy src/nexus` (strict) | 62 files | **63** files |
| `OperationalStore` declared methods | 36 | **37** (F-29) |
| writers in `intelligence/` | 3 (`evidence_ref`, `dossier`, `memory_item`) | **4** (+ `decision`) |

New files: `src/nexus/intelligence/thesis.py` (521 lines) and `tests/test_thesis_writer.py` (986 lines,
**99** tests). `record_thesis` takes **16** parameters and `ThesisReceipt` has **19** fields, three of
which exist only to echo columns the writer declines to fill (§4.3); `thesis.py` has **17**
`raise ValueError` sites. Changed: `src/nexus/intelligence/__init__.py` (the fourth writer exported, `__all__` from
26 to 34, and the package docstring's *"All three are built and none is wired"* corrected to four) and
`src/nexus/store/operational.py` (one protocol declaration plus its comment).

**No migration. No schema change. No checksum moves.** Nothing in `store/schema.py` and nothing in
`migrations/*.sql` was touched, so `MIGRATIONS` stays at 6 and every checksum in
`tests/test_schema_fidelity.py` is unchanged — which is the property that lets §5's question stay open
without this batch having pre-empted it.

### 6.1 Tamper proof: 22 sites, 22 caught, 0 silent

Each site reverses one decision this batch claims, the full suite runs against it with `-x`, and the
verdict is parsed from `(\d+) failed` over the whole output. Baseline **1,527 passed / 0 failed** before
the first tamper and after the last; all three watched files restored to their pre-sweep **SHA-256**.

| | site | caught by |
|---|---|---|
| T01–T03 | the ACCEPT / REDUCE / EXIT refusal removed | `TestTheGatedVerbsAreRefusedSeparately` |
| T04 | the gated-state refusal removed | `TestTheGatedStatesAreRefused` |
| T05, T06 | `rationale` no longer required; ABSTAIN needs no code | `TestAbstainIsTheDefaultRecordAndNotAFallback` |
| T07–T11 | dangling instrument; empty instrument; dangling citation; empty citation; unvalidated venue | `TestTheParentGuardsAreInTheWriter` |
| T12, T13 | **F-28's remedy undone**: `created_at` dropped from the event; `rationale` emptied | `TestThePayloadCarriesWhatTheProjectionReads` |
| T14 | an existing `decision_id` may be re-recorded | `TestTheParentGuardsAreInTheWriter` |
| T15 | the `NUMERIC(6,5)` boundary check bypassed | `TestConfidenceIsAnInputAndNeverAGate` |
| T16, T21 | `intent_id` becomes a parameter; `intent_id` dropped from the event | `TestTheColumnsThisWriterIsNotRuledInto`, `…PayloadCarries…` |
| T17 | **F-29 undone**: `get_decision` undeclared on the protocol | `TestTheSeamIsSettledAndNothingMoved` |
| T18 | the writer writes the store directly | `TestTheSeamIsSettledAndNothingMoved` |
| T19 | the three verb refusals folded into one shared reason | `TestTheGatedVerbsAreRefusedSeparately` |
| T20 | an empty reason code accepted | `TestTheParentGuardsAreInTheWriter` |

**The harness itself was wrong once, and the wrongness looked like a result.** The first run reported
**21 sites, 0 caught, 21 silent** — every decision in the batch apparently unpinned. The baseline line
said `? passed`, which is the tell: `pyproject.toml`'s `addopts` already carries `-q`, so the harness's
own `-q` made it `-qq` and suppressed the summary both verdicts are parsed from. This is the same trap
`docs/15` §14 recorded for Stage 8.7, recorded there and repeated here anyway. A sweep that reports every
site silent is a broken sweep until the baseline is proven green **and parsed**, and one bad anchor
(`if not wanted.strip():` occurs in both `_resolve_instrument` and `_resolve_evidence`) was caught by
asserting each anchor matches exactly once before running.

### 6.2 Four costs this batch accepts and does not hide

1. **`_aware` is now copied three times** — `intelligence/evidence.py`, `intelligence/memory.py`,
   `intelligence/thesis.py`. `memory.py`'s docstring gives the reason and it still holds: a private
   helper is not a shared one, and promoting it to `core.time` would touch a Phase-2 module inside a
   batch whose scope a ruling named. Three copies is the price of that scope, and it is recorded rather
   than defended.
2. **`thesis.py` has a `_aware` it never calls.** No parameter is a datetime, because the one it would
   serve — `expires_at` — is deliberately absent (§4.3). The helper is there so the parameter cannot be
   added later without the naive-datetime refusal coming with it. Dead code on purpose, and named here so
   it is not mistaken for an oversight.
3. **A fourth unwired writer.** No caller in `src/nexus` invokes `record_thesis`, asserted by an AST scan
   for *calls* and not for the word, because `operational.py`'s F-29 comment names `record_thesis` to say
   which writer needed the getter and a substring scan reported that comment as a caller. Wiring a writer
   means deciding what the system should propose, and no ruling has made that decision. The package
   docstring says so for all four.
4. **`DecisionRecord` is still not what this writer writes.** The writer builds a payload, not a domain
   object, following the three writers before it. So the repository now has two ways to describe a
   decision — an 18-field dataclass nobody in `src/` constructs, and a 19-column row written by a
   function that never mentions the dataclass. F-28 is the visible edge of that; §10's question 3 is
   about the rest of it.

## 7. What Stage 9 did **not** do

Ruling 3 authorised the seam and the writer. Nothing else moved, and each of these is a thing a reader
might assume:

- **No migration, no schema change, no checksum moved** (§6). `decision` still has 19 columns.
- **No `trade_intent` row is written by anything.** A-08 is why, and §4.1's EXIT refusal says so.
- **No route.** Nothing serves a decision over HTTP; `app.py` gained no reference to `thesis`.
- **No expiry policy**, on `decision` or on `memory_item`. `docs/15` §14.8 limitation 1 stands exactly as
  published, and D-056's ruling 1 re-affirmed it.
- **No confidence band.** F-24 is untouched; §10 asks its shape.
- **No sufficiency meter.** F-18's gap 4 stays open and belongs to stage 10 by `docs/12` §1.3.
- **F-27 untouched.** The inflated counts stay pinned at `0003 → 4` and `0004 → 15`.
- **No stage beyond 11 is named.** `build_board52.py:73-87` remains the only stage map.
- **No `O-` row opened.** F-28, F-29 and F-30 are findings, on D-054's reasoning — re-applied by D-056 to
  F-26 and F-27 — that recording a finding is not opening an obligation. `docs/00` still holds
  `O-001`…`O-014`.
- **F-26 not closed and not corrected in the register by this batch.** §2.6 states the case for
  **CORRECTED**; the label is the owner's to apply.

## 8. Limitations, published beside the delivery

1. **A dangling instrument is still representable and still storable.** `record_thesis` refuses one, and
   `store.save_decision(record)` accepts one, because the store is a projection and `PRAGMA foreign_keys`
   is off. `docs/15` §13.7 limitation 3 stands; §2.6 is the residue of F-26 that survives its answer.
2. **Four of the five foreign keys F-26 named are still unguarded by any writer**, and three have no
   writer at all (§2.4). Closing F-26 on `decision.instrument_id` does not close it on the trading path.
3. **The uncertainty a thesis carries is a reason code, which is a label** (§4.5, §5). Nothing in the row
   states what is unresolved, and no test can assert what a column cannot hold.
4. **`decision.confidence`'s `0..1` comment is unenforced** on both tables (§4.4), and D-054's ruling
   that confidence stays unbounded was made about `memory_item` and has not been re-made about `decision`.
5. **The verb and state boundaries are this batch's derivation from five sources, not a quotation from
   any one of them** (§4). No document says "Stage 9 may carry these four verbs". The sets are pinned and
   enumerated so the derivation can be argued with, and §10's question 1 puts it to the owner.
6. **`risk_check` stays `'{}'` for every thesis**, so the column is as inert on `decision` as
   `expires_at` is on `memory_item` — with the difference that A-02 says it *should* stay empty until the
   risk engine writes it, rather than merely that nothing reads it yet.
7. **`thesis.py` is not wired** (§6.2 cost 3), so nothing in a running system produces a thesis. The row
   this batch can write is a row nothing yet asks for.
8. **`FlakyStore` and `HaltBlindStore` conform by forwarding**, which is why F-29 broke nothing (§2.2).
   That is a property of those two wrappers and not of the test suite: a future fake that enumerates the
   protocol would need updating, and nothing would say so offline.

## 9. Findings after this batch

| id | status | batch | one line |
|---|---|---|---|
| **F-24** | `OPEN` | **8.8 (batch B)** | the confidence band; shape un-ruled, measured in §10 |
| **F-26** | `OPEN` | none | **answered and due `CORRECTED`**, not closed (§2.6); residue is the domain object and the four unguarded keys |
| **F-27** | `OPEN` | none | `Migration.statements` counts prose semicolons; the inflated counts stay pinned |
| **F-28** | `OPEN` — **new** | none | `decision.recorded`'s two producers disagree; the fourteen-key one cannot reproduce its own row (§3) |
| **F-29** | `CLOSED` — **new** | **9.1** | `get_decision` was the one single-row getter the protocol never declared; declared here, 36 → 37 (§2.5) |
| **F-30** | `OPEN` — **new** | none | `decision` has no `uncertainty` and no `payload` column, so the stage map's ask cannot be stored (§5) |
| F-18 | `NARROWED` | none | gaps 1–3 closed; gap 4 (the sufficiency meter) alone open, stage 10 |
| F-22 / `O-014`, F-17, F-19 | `OPEN` | none | unchanged |

The next finding id is **F-31**.

## 10. Batch B, measured and not built — F-24's confidence band

D-056's ruling 4 authorised two concurrent batches, and §14.10 derived batch B's scope: **8.8 = F-24's
confidence band**, the one open finding on Stage 8's own tables. `migrations/0002_memory.sql:29` states it
in the schema's own words — *"confidence band: `confidence` stays one `NUMERIC(6,5)` point, while `docs/10`
§3.1 asks for it 'as a band'"* — and §3.1 calls the point estimate *"a defect"*.

**Batch B is not built, and the reason is not lack of time.** §14.10 is explicit that where an option's
label carried no scope, the un-ruled shape goes to the owner as a question and is never decided silently.
Three shapes are available and they are not equivalent, and two of the three are migrations. What follows
is the measurement that makes the question answerable rather than a proposal disguised as one.

### 10.1 What D-054 already rules, so it is not re-asked

**D-054 ruled confidence unbounded**, and that ruling is applied here rather than reopened: a band's
bounds inherit it. What "unbounded" means precisely, measured through `confidence_text` on 12 inputs:
there is **no range rule**, so `-0.4`, `0` and `9.99999` all store; but the portable target's own
magnitude ceiling still refuses `10` and `47`, and its scale still refuses `1e-6` and `0.999999`. A band
would inherit exactly that. An *ordering* rule — `high` not below `low` — is not a range rule, and Stage
8.5 already established the precedent for it: `valid_until <= valid_from` is refused including equality.
So the band's bounds are settled and its **shape is not**, which is why §10.3 asks one question.

### 10.2 Which shape is more expressive, measured

| band | (a) `confidence_low` + `confidence_high` | (b) `confidence` + `confidence_width` |
|---|---|---|
| `0.7 ± 0.4` | `0.3` and `1.1` — both store | `0.7` and `0.4` — both store |
| `-0.4 … 0.2` | both store | `-0.1` and `0.6` — both store |
| `-9.9 … 9.9` (19.8 across) | **both store** | width `19.8` **refused** — 2 digits before the point |

(a) is strictly more expressive under `NUMERIC(6,5)` plus D-054: a *width* is a magnitude, so it inherits
the one-digit-before-the-point ceiling even though confidence itself is unbounded, and a band wider than
`9.99999` becomes unrepresentable while its two endpoints are not. (b) also needs a second ruling that
(a) does not — whether `width` is a half-width or a full width — and an unruled ambiguity in a column is
the thing `docs/15` §12.8 was opened for. (c), a distribution, is not expressible in `NUMERIC(6,5)` at
all and would live in `memory_item.payload`, which no reader would be able to constrain.

### 10.3 What a band would touch, counted

`memory_item` has **15** columns; `record_memory_item` has **15** parameters; `MemoryReceipt` has **17**
fields; `memory.py` has **17** `raise ValueError` sites; `validity_of` returns **5** keys;
`evidence_ref`'s `CHECKSUMMED_FIELDS` holds **10** of its 12 columns. Shape (a) adds two columns and
leaves `confidence` either redundant or the midpoint — a third question nobody has asked. Shape (b) adds
one and leaves `confidence` meaning what it means. Both are migrations, so both are governed by §5's
argument: the shape is chosen once, in production, forever.

### 10.4 Also on the board, from `docs/10` §3.1's own gap list

`app.py`'s `DOSSIER_VIEW_GAPS` enumerates **9** elements of the dossier view that cannot be served. Stage
9 touches one of them: element 9, *"disposition with reason code"*, whose recorded reason is *"the
disposition is served as stance, but dossier has no reason-code column. Reason codes live on
`DecisionRecord`, and a dossier is not a decision."* `record_thesis` now writes reason codes onto a
`DecisionRecord`, so the element's *cause* is unchanged but its remedy is now reachable — a dossier view
could join to a decision. That is not built, not wired and not claimed; it is recorded because a gap list
that is never re-read becomes a list of things that were true once.

Two of the nine remain deferred to stage 10 by D-051 (*contradictions highlighted and linked*, and
*beliefs with confidence band, validity interval and change conditions*), one to stage 10 by name
(*knowledge-sufficiency meter*, which is also F-18's gap 4), and one — *publication time in the evidence
table* — was scheduled for 8.4 and **not filled by it**, with no batch since.

## 11. The combined board

Ruling 4's shape: both batches' questions on one board, so the owner rules once. Batch A's work is
delivered and measured; batch B's is measured and blocked on its question. Batch A contributes questions
1 and 3, batch B question 2, and question 4 is about what runs next under the new cadence.

1. **Batch A — is the verb and state boundary right?** Four verbs and six states permitted, three and six
   refused, derived in §4 from five sources but quoted by none of them. **Recommend: approve as built** —
   the refusals are fail-closed, which is A-02's own posture, and widening later is additive while
   narrowing after a row exists is not.
2. **Batch B — which shape is the confidence band?** (a) two columns, (b) one width column, (c) a
   distribution in `payload`. **Recommend: (a)**, on §10.2's measurement that it is strictly more
   expressive under the target that already exists, and because it needs no second ruling about what a
   width means. D-054's unbounded confidence and 8.5's ordering precedent are applied, not re-asked.
3. **Batch A — what becomes of `DecisionRecord`?** Two descriptions of one decision now exist and this
   writer uses neither's dataclass (§6.2 cost 4). **Recommend: leave both**, record the divergence beside
   F-28, and let the writer that eventually *reads* decisions decide which is the record — a reader does
   not exist yet, and choosing now would be choosing for it.
4. **What runs next under ruling 4's cadence?** **Recommend: stage 10 — knowledge sufficiency**, which is
   also F-18's gap 4 and two of the nine dossier-view gaps, so one batch closes three recorded items;
   with the expiry reader (§8 limitation 1, D-056 ruling 1's standing limitation) as the alternative if
   the owner would rather make an inert column do something than add a meter.

---

## 12. D-057 — the four rulings, and what each one does not settle

**Date: 2026-11-28. All four questions in §11 answered `Recommend`, so all four recommendations are the
rulings.** Recorded here rather than retro-fitted into §11: §11 asserts the questions *as put* and stays
unedited, and this section asserts what was ruled, for the reason `build_board87.py` keeps
`ruling_table()` and `decision_table()` apart — one table serving both would let a ruling silently rewrite
the question it answered.

| # | the question as put (§11) | ruled | what it changes |
|---|---|---|---|
| 1 | Is the verb and state boundary right? | **(a) approve as built** | The four permitted verbs and six permitted states, and the three and six refused, are now **owner-approved** rather than derived. No code changes. §8 limitation 5 is annotated below. |
| 2 | Which shape is F-24's confidence band? | **(a) two columns, `confidence_low` + `confidence_high`** | **8.8 is authorised to build**, and its shape is settled, so batch B stops being measured-and-blocked. It carries a migration. |
| 3 | What becomes of `DecisionRecord`? | **(a) leave both** | The 18-field dataclass and the 19-column row both stand. **F-28 stays `OPEN`, no batch**, with the divergence recorded beside it (§6.2 cost 4). |
| 4 | What runs next under ruling 4's cadence? | **(a) stage 10 — knowledge sufficiency** | The next two batches are **stage 10 and 8.8**, against **one combined board**, which is D-056 ruling 4's cadence applied for the first time to two batches that both have work in them. |

### 12.1 What ruling 1 does not settle — F-26's label, and the schema

**F-26 stays `OPEN` and unlabelled.** §2.6 stated the case for **CORRECTED** and said the label was the
owner's to apply; §11's question 1 asked about the verb and state boundary and **not** about the label, and
no option carried it. So the ruling does not apply it, and this section does not either: recording the case
for a label is not applying one, on D-056 §14.10's rule that where an option's label carried no scope the
derivation is recorded rather than a scope retro-fitted to the ruling. F-26's next appearance is as a
question, not as a row.

**Approving the boundary does not enforce it in the schema.** `decision.verb` and `decision.state` remain
free `TEXT` with no `CHECK` in either DDL, and ruling 1 did not ask for one. So the boundary lives in
`record_thesis` alone, and a caller that reaches `store.save_decision_payload(payload)` directly — which is
what `project()` does, and what `test_thesis_writer.py`'s last test does by hand — can still write
`verb=ACCEPT`. That is the same posture as `dossier.stance`, whose vocabulary `open_dossier` validates and
the schema does not, and it is published here rather than left to be inferred from an approval.

§8 limitation 5, annotated and not rewritten: the sets are no longer merely *a derivation from five
sources*, because ruling 1 approved them; the half that stands is that **no document quotes them**, so a
reader looking for the boundary in `docs/03` or `docs/10` will not find it — it is in this document, in
`thesis.py`'s `THESIS_VERBS`/`GATED_VERBS`/`THESIS_STATES`/`GATED_STATES`, and in the tests that pin all
four.

### 12.2 What ruling 2 does not settle — the third question its own option named

Option (a)'s cost was stated in the option and accepted with it: two columns, and *"`confidence` becomes
either redundant or the midpoint — a third question nobody has asked."* **Choosing the shape is not
choosing what happens to the existing column**, so 8.8 must ask it rather than decide it, on the same
§14.10 rule. The three readings are not equivalent and only one is reversible:

| what `confidence` becomes | consequence | reversible? |
|---|---|---|
| redundant — left nullable and unwritten | a column that stays empty forever, which is what F-27 and §14.8 limitation 1 both warn a reader cannot distinguish from a dropped one | yes, by writing it later |
| the midpoint — derived from the two endpoints on write | every existing row's meaning changes, and a *derived* value stored beside its inputs can disagree with them | **no** — rows already written carry the old meaning |
| a third, independent claim — the point estimate beside the band | three numbers where §3.1 asked for one band, and nothing says which a reader should trust | yes |

Also settled by ruling 2 and not re-asked, because D-054 and Stage 8.5 already ruled them: **both bounds
stay unbounded** — no `0..1` rule, only `NUMERIC(6,5)`'s own magnitude ceiling and scale — and **the
ordering is enforced**, `confidence_high` below `confidence_low` refused including equality, on 8.5's
`valid_until <= valid_from` precedent. §10.2's measurement stands as the reason (a) was recommended: a
width is a magnitude and inherits the one-digit ceiling, so `-9.9 … 9.9` is expressible as two endpoints
and not as a width of `19.8`.

### 12.3 What ruling 4 does not settle

- **F-27's fix stays declined.** Option (c) was not chosen, so D-056's ruling 2 stands unchanged: the
  inflated counts remain pinned at `0003 → 4` and `0004 → 15`, because a fix moves no checksum but the
  count is a row written at apply time and never rewritten.
- **The expiry reader is not authorised.** Option (b) was not chosen, so `docs/15` §14.8 limitation 1
  stands exactly as D-056's ruling 1 left it standing: `memory_item.expires_at` is inert, nothing in
  `src/` reads it, and an item expired 400 days ago is still served.
- **F-30's column is not authorised, and this is a consequence worth stating plainly.** Question 4's option
  (d) was *"F-30's column first, if question 2 wants a migration anyway"* — one batch carrying both
  migrations so production takes a single irreversible step. Ruling 2 **does** want a migration, and ruling
  4 chose (a) and **not** (d). So the band's migration does not carry `decision.uncertainty`, and
  production will take **two** irreversible steps rather than one. **F-30 stays `OPEN` with no batch**, and
  the reason-code substitute of §4.5 stays a substitute: a thesis still cannot state what is unresolved in
  a column, only label it.
- **Stage 10's own scope is not defined by any document.** The stage map names it *"Knowledge sufficiency ·
  stage 10 · does the dossier meet the sufficiency bar for this instrument/session?"* and `docs/15` §6's L-E
  says sufficiency *"stays a string until stage 10 defines the meter"*. No document defines the meter, the
  bar, or the vocabulary of what it is sufficient *for*. So stage 10 opens with a derivation and a question
  of its own, recorded now rather than invented later — which is F-18's gap 4 and two of the nine
  `DOSSIER_VIEW_GAPS` D-051 deferred to it by name, and one more (`disposition with reason code`) whose
  remedy §10.4 notes is now reachable but not built.

### 12.4 What D-057 does not do

It closes no finding except by confirming what 9.1 already closed in code: **F-29 `CLOSED`**, the protocol
36 → 37. **F-24** moves from un-ruled shape to ruled shape and stays `OPEN` until 8.8 builds it.
**F-26**, **F-27**, **F-28** and **F-30** all stay `OPEN` with no batch. **F-18** stays `NARROWED` with gap
4 alone open, now scheduled — gap 4 *is* stage 10's meter. It opens no `O-` row, on D-054's reasoning
re-applied by D-056 to F-26 and F-27: recording a ruling is not opening an obligation, and `docs/00` still
holds `O-001`…`O-014`. It retires none of §8's eight limitations, and annotates one (§12.1). It names no
stage beyond 11. **The next finding id stays F-31**, because a ruling that finds nothing invents nothing.

**Next:** two batches concurrently, per ruling 4 — **8.8**, the band as `confidence_low` +
`confidence_high` with a migration and question §12.2's third question on its board, and **stage 10**,
knowledge sufficiency, opening with the derivation §12.3 says it needs. One combined board.
