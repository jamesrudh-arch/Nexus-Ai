# NEXUS — Phase 4: Venue Certification (demo/paper only)

**Status:** PRE-FLIGHT. No venue has been contacted, no account connected, no credential requested.
**Date:** 2026-11-25 · **Branch:** `arena/06913352-nexus-ai` · **Cost:** $0 (D-019)

Phase 3 was accepted on 2026-11-25 (D-027). Phase 4 is authorized **VM-first** (D-028): before any
venue is certified, the stack must be brought up for real, because nothing in Phase 2 or Phase 3
ever started a container. This document records that work. The accepted Phase 3 record
(`docs/05-phase3-market-data.md`) is frozen and is not amended here.

---

## 1. Authority and scope

| Ref | Decision | Date |
|-----|----------|------|
| **D-027** | **Phase 3 ACCEPTED.** Market data + instrument master; exit gate PASSED for offline-verifiable scope. O-009 (live endpoints) and O-010 (Dukascopy layout) remain **open** and tracked, both requiring network egress this sandbox does not have | 2026-11-25 |
| **D-028** | **Phase 4 authorized, VM-first.** The first task is a real `docker compose up` on the Oracle Always Free VM approved in D-021, closing the "no container has ever started" limitation and testing the runtime image's assumptions for real. Venue certification follows. **Demo/paper accounts only** — no live trading, no real-money keys, no withdrawal-enabled credential | 2026-11-25 |
| **D-029** | **First venues: Bybit and OKX, certified in parallel**, matching the Phase 3 build order (D-026). Each is certified independently (D-007); neither inherits the other's status. Both are ADOPT for Nigeria per `docs/02` §3 (OKX removed from the restricted list 8 Jul 2026; Bybit partial) | 2026-11-25 |

Unchanged and still binding: D-004 (autonomy requires a separate live-authority approval),
D-013 (legal review before live), D-019 (zero cost), D-021 (the VM must be re-approved before any
live phase).

**Out of scope for Phase 4:** live trading, real-money orders, withdrawal permissions, any paid
service, any venue not named in D-007, and any change to a model or strategy without owner
approval (D-012).

---

## 2. Pre-flight defects — found before any venue work began

Found while preparing the bring-up, by reading what the deployment actually configures against
what the code actually honours. None is a venue defect; all would have been discovered *during*
the bring-up, at the worst possible moment, and one would have destroyed evidence.

| # | Defect | Impact if unfixed | Fix |
|---|--------|-------------------|-----|
| 31 | **`_default_store` silently substituted an in-memory audit store** for any `NEXUS_DATABASE_URL` that was not `sqlite:///` — and `.env.example` advertised `postgresql+psycopg://...` as the compose variant, with a TimescaleDB service shipped to serve it | **The audit trail — the system's evidence record — would have been discarded on every restart**, while `/healthz` and `/readyz` both reported success. Reachable purely by following the documentation. For a system whose decisions must be auditable after the fact, this is the worst failure mode available: not a crash, but plausible-looking compliance with nothing behind it | Refuse startup with `CONFIG_INVALID`, naming the scheme that works and the explicit way to choose memory (`NEXUS_AUDIT_BACKEND=memory`). This is the codebase's own rule — `NatsEventBus` documents "events are never silently discarded"; the audit store is now held to it. The refusal carries only the URL *scheme* in its context, because it is persisted and surfaced in the UI and a database URL can contain a password |
| 32 | **The test suite wrote a real audit database into `backend/data/`** | `Settings.database_url` is relative, so every test that built the app with defaults appended to one shared SQLite file — shared between tests *and* between runs, and invisible to git because the path is ignored. An append-only hash-chained log shared across runs is not isolation: a verification that passes on a dirty tree can fail on a clean one | An autouse fixture runs each test in its own directory. Guarded by executing a real pytest subprocess from the repository cwd and asserting no `backend/data` appears — not by checking the fixture exists, because a fixture can exist and not be autouse, and only the second case protects anything |
| 33 | **`.env.example` never documented `NEXUS_SECRET_OWNER_TOTP_SECRET`** | The step-up factor for `POST /v1/halt/release`. An operator following the documentation would bring up a system whose emergency halt could be **engaged but never released**, and nothing would explain why until the first incident needed it | Documented, with what it gates. Guarded in *both* directions by a new test class: every variable the deployment sets or the docs recommend must be read by something (a `Settings` field, an `os.environ` read, a Caddyfile/compose template, or the secrets naming convention), and every `SecretRef` the code declares must appear in `.env.example` |
| 34 | **`core` waits for `db` to be healthy but never connects to it** | TimescaleDB costs ~1.5 GB of the 12 GB Always Free budget and adds startup latency for a database nothing reads, on the most memory-constrained host in the plan | Recorded as a KNOWN GAP in the compose header rather than papered over. Wiring `core` to Postgres is Phase 4 work; until then a memory-constrained host should bring up `core` alone. `backend/migrations/0001_core.sql` is complete Postgres DDL, including append-only triggers, and is what that wiring will apply |
| 35 | **A negative-control loop silently failed to restore the files it mutated** | Six deliberate mutations — including re-introducing defect 31 — were left in the working tree, and the next commit would have shipped every one of them. Two causes: the loop backed up each file *after* mutating it, and `git -C <repo> checkout -- <path>` was given paths relative to a different cwd, so git errored and the fallback restored the mutated copy | Repaired by hand and verified line by line. The lesson is recorded rather than the history rewritten: a control whose restoration is not verified is worse than no control, because it leaves the tree in a state that looks intentional. Restore by absolute path, and diff against HEAD before committing |

Defect 31 is the significant one. It is the same shape as the CI-era defects in `docs/05` §4 — a
configuration key or code path that is silently inert while looking correct — but the payload is
worse: those lost a scan result or a build diagnosis, and this one loses the evidence trail that
every other guarantee depends on. It was found by asking a question nobody had asked: *which of the
variables this deployment sets does the code actually read?*

---

## 3. Bring-up plan

Sequenced so that each step produces evidence the next one depends on. Nothing here contacts a
venue.

| Step | What is verified | Where | Evidence produced |
|------|------------------|-------|-------------------|
| **B-1** | The stack starts and serves. `core` builds, starts, answers `/healthz` and `/readyz`, and reports the phase gate honestly from a *running* process | GitHub Actions (x86-64), then the Oracle VM (ARM64) | Container logs, endpoint responses, `docker compose ps` health states |
| **B-2** | The runtime image's assumptions hold under execution: the pip removal did not break a runtime import, `tzdata` is present, the non-root user can write its audit database, the healthcheck actually answers | same | The same assertions the Dockerfile makes at build time, re-checked in a running container |
| **B-3** | SQLite audit store durability across a restart **and across a container recreate**: records survive, the hash chain resumes from the stored head and still verifies | GitHub Actions, then the Oracle VM | `/v1/audit/verify` plus a direct row count from the volume, before and after each |
| **B-4** | ARM64-native execution (not QEMU-emulated), and the memory budget on 2 OCPU / 12 GB | Oracle VM only — CI cannot do this | `docker stats` under load, `uname -m` from inside the container |
| **B-5** | Postgres/TimescaleDB actually used by `core`, closing defect 34 and Phase 3 limitation 5 | Oracle VM | Migration applied, records written to and read from Postgres, `db` no longer idle |
| **B-6** | Only then: Bybit and OKX **demo/paper** connectivity, per D-029 | Oracle VM (has egress) | Per-venue certification records |

B-1 and B-2 can run in CI, on GitHub-hosted runners, for $0 — which is worth doing before the VM,
because a failure found there costs minutes and a failure found on the VM costs a rebuild. B-4 and
B-5 cannot be done anywhere but the VM. B-3 turned out to belong in the first group as well: a
`docker compose rm -sf core` followed by `up -d core` destroys the container and keeps the
`core-data` named volume, which is available on a hosted runner and is a *stronger* test than the
restart alone.

### 3.1 How B-1/B-2/B-3 are wired

Three pieces, all offline-verifiable except the container run itself.

**`infra/smoke_check.py`** — 34 assertions, standard library only, because it has to run inside the
runtime image where the only guaranteed interpreter is the application's own. It is piped in with
`docker compose exec -T core python - < infra/smoke_check.py` rather than copied, so it cannot be
stale relative to the checkout. It reads the API from inside the container (`/healthz`, `/readyz`,
`/v1/status`, `/openapi.json`, `/v1/instruments`, `/v1/audit/verify`) and asserts the *posture*: the
phase gate is closed, live authority is `DENIED` with reasons, `venue_adapters` is empty, the market
data sources are unauthenticated and read-only at zero cost, SMS and WhatsApp stay blocked (D-020),
no route can place or cancel an order, the only mutations are halt and halt/release, and the
instrument master refuses a POST with 405.

The route assertions read `/openapi.json` rather than the router object, so they describe what a
client can actually reach. Forbidden routes are matched as substrings — `order`, `trade`, `execute`,
`position`, `withdraw`, `transfer` — so a capability added later under a new prefix is still caught.

Image-only properties (pip and setuptools absent, the IANA tz database installed, uid 1001, `/app/data`
writable, no SBOM in the image declaring setuptools) run only when `NEXUS_SMOKE_RUNTIME_CHECKS=1`.
That gate exists so the checks have a **negative control**: in a development virtualenv they must
fail, because pip and setuptools are both present there. A check that passes in every environment
is not checking anything.

**`infra/smoke-test.sh`** — the orchestration. It brings up `db nats core` under a *separate compose
project name* (`nexus-smoke`) so it cannot touch a real deployment's containers or volumes, which
matters on the VM where a live stack may already be running; tears down what it created; and runs
every check rather than stopping at the first failure, because one complete report is worth more
than six CI runs that each die on the first problem. Exit status is non-zero if any check failed.

It asserts the image's own `HEALTHCHECK` answers (docker reports `core` healthy — nothing had ever
exercised that), runs the checker inside the container with the runtime checks on, then proves
durability twice over: a restart, and a container recreate against the surviving volume. It also
confirms the runtime user — not root — can write `/app/data` in the *new* container, which is where
a volume that inherited the wrong ownership would show up.

No step whose exit status matters is piped. `cmd | tail -5; echo "exit=$?"` reports `tail`'s status,
not `cmd`'s, and that silently turned a crash into a green result while this was being written.

**The `smoke` CI job** — builds the amd64 image with `load: true` under the exact tag
`docker-compose.yml` names, runs the script, and republishes `smoke-report.txt` as **one** check
annotation. The annotation is not a convenience: this environment cannot read job logs, because
GitHub serves them from a host outside the egress allowlist, so without it a failure here is a red
X with no content. One annotation rather than one per failure, because Actions caps annotations at
10 per level per step and a long report would silently lose everything past the tenth.

The job deliberately has no `needs:`. Lint and runtime are independent signals about different
things, and chaining them means the runtime verdict arrives only on pushes that are already
lint-clean.

**11 new tests in `test_repo_hygiene.py`** hold all of the above in place, including running the
checker against the real application served by uvicorn on an ephemeral port. That last one is the
important part: it executes the checker end to end, over a real socket, with no docker involved, so
a bug in the *checker* is caught offline instead of surfacing as a confusing red container job. Two
such bugs were found while writing it and are now regression-tested — it crashed with an unhandled
`URLError` traceback when nothing was listening (the least useful possible output from a bring-up
check, since "the process is not there" is the one thing the operator already suspects), and one
route probe used GET where it meant POST, so it failed against a correct application. All six
negative controls over these tests fired, and each mutated file was verified restored individually
rather than inferred from the controls passing.

**O-009 and O-010 can be closed from CI, not from this sandbox.** GitHub-hosted runners have
internet egress, which the sandbox does not: a scheduled or on-demand workflow can contact the
public Bybit and OKX endpoints and fetch a real Dukascopy bi5 file, then compare both against the
synthetic fixtures the adapters were written from. That is the plan for closing the two outstanding
Phase 3 exit-gate items without waiting for the VM, and it needs no API key (D-026: public
endpoints only).

---

## 4. Limitations — what is NOT verified

Per Appendix C. These are open, not finished.

1. **No container has ever been started.** Everything in Phase 2 and Phase 3 verified that the
   image *builds* and that its entrypoint *imports*. B-1 is the first step that changes this, and
   until it passes, every claim about runtime behaviour is inference.
2. **The pip removal from the runtime image is reasoned, not observed.** It was verified safe by
   grepping every installed distribution's metadata in the **dev venv**, whose package set differs
   from the image's — the same mistake as `docs/05` defect 30, which cost a red build. Nothing in
   `src/nexus` shells out to pip, but if an installed package imports it at runtime, only B-2 will
   find out.
3. **PostgreSQL/TimescaleDB is still untested at runtime**, and is now known to be *unused* by
   `core` (defect 34). Only SQLite has ever been exercised.
4. **The ARM64 build is QEMU-emulated in CI.** It proves cross-compilation, not native execution or
   performance. B-4 is the first ARM64-native evidence, and D-021's host is ARM64.
5. **The Caddyfile remains completely unexercised.** It has never been parsed by Caddy, in CI or
   anywhere else.
6. **No venue has been contacted.** O-009 and O-010 are open. The adapter tests run against a
   `RecordingTransport` with synthetic payloads written from published API contracts, which proves
   normalisation logic and not that the live endpoints still return those shapes.
7. **No credential of any kind exists yet**, and none is requested by anything built so far. Phase
   4 will need demo/paper credentials, which go to the secrets provider and never into chat, the
   repository, the image, or the audit log.

---

## 5. Evidence

| Check | Result | Date | Environment |
|-------|--------|------|-------------|
| Full suite | **884 tests, 0 failures, 0 errors, 1 skipped** (59 hygiene, 66 API) | 2026-11-25 | sandbox, local venv, Python 3.11.2 |
| Lint / format | `ruff check` clean, `ruff format --check` clean (69 files) | 2026-11-25 | same |
| Types | `mypy` strict — no issues in 49 source files | 2026-11-25 | same |
| Negative controls | **6 of 6 fired**: re-advertising the Postgres URL, un-documenting the TOTP secret, adding a variable nothing reads, changing the compose default to a refused scheme, reverting the refusal to a silent in-memory fallback, and making the cwd fixture non-autouse | 2026-11-25 | same |
| Control restoration | Failed silently on the first attempt (defect 35); repaired and verified line by line against HEAD before committing | 2026-11-25 | same |
| Repository state | No `backend/data`, no artifact, no credential-shaped file, no scan-suppression file | 2026-11-25 | same |
| CI on GitHub | **Green on both events** at `9522856`: `push` run `45709533997`, `pull_request` run `45709545037` — Backend ✓ · Compose ✓ · Secret scanning ✓ · Container image ✓ | 2026-11-25 | GitHub-hosted `ubuntu-latest`, x86-64 |

The 1 skip is a pre-existing `pytest.skip` for an interval outside the modelled set, not a disabled
test. Test counts rise from Phase 3's 868 because defects 31–33 each added tests.
