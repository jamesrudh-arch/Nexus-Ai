"""Repository hygiene: every source module must actually be *in* the repository.

Why this file exists
--------------------
An unanchored ``data/`` pattern in ``.gitignore`` matches at any depth, so it silently
excluded ``backend/src/nexus/data/`` — and ``secrets/`` excluded ``backend/src/nexus/secrets/``.
Six modules the package imports were missing from a commit that had already been pushed. A
fresh clone could not import ``nexus`` at all, and CI would have failed on checkout.

Nothing caught it, because the test suite runs against the **working tree**. The files were
all present locally; they simply were not in git. These tests compare the two, which is the
only way to detect that class of failure.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
SOURCE_ROOT = BACKEND / "src" / "nexus"

#: The only files allowed to contain secret-shaped strings, because recognising those shapes is
#: literally their job: the redactor and the audit gate must spell out what a PEM block or an AWS
#: key looks like in order to mask it, and their test must contain a value that looks like one.
#: Every matching value in them is fabricated. Scoped as a path allowlist in `.gitleaks.toml`.
_SECRET_SHAPE_FILES = frozenset(
    {
        r"backend/src/nexus/secrets/redaction\.py",
        r"backend/src/nexus/audit/log\.py",
        r"backend/tests/test_secrets_and_redaction\.py",
    }
)

#: The same files as plain paths, for the repo-wide sweep that does not use regexes.
_SECRET_SHAPE_PLAIN = frozenset(p.replace("\\", "") for p in _SECRET_SHAPE_FILES)

#: Exactly one historical revision is excused from secret scanning, by full SHA.
#:
#: `eb5234f` added the first version of `.gitleaks.toml`, which allowlisted the redaction
#: fixtures *by regex* — so it copied a fabricated JWT and a fabricated PEM block into the
#: config file and into `test_repo_hygiene.py`, neither of which is a detection-code path.
#: Both literals were removed in the very next commit. A `pull_request` run scans the whole
#: branch history, so without this the scan fails on a revision that no longer exists at HEAD.
#:
#: The values were never credentials: the JWT's signature is a run of the alphabet and the PEM
#: body is four characters. `test_head_carries_secret_shapes_only_in_allowlisted_paths` is what
#: makes excusing this safe — it fails the moment any current file outside the allowlist holds
#: a secret-shaped literal, so the excuse cannot quietly become a hiding place.
_ALLOWLISTED_COMMITS = ("eb5234f25a587da6b442785be8754a6954f0bdd4",)

#: The gitleaks release CI runs, pinned in `.github/workflows/ci.yml` via `GITLEAKS_VERSION`.
#: gitleaks-action@v2 defaults to this same version (hard-coded in its src/index.js), but the
#: default moves when the action is updated, and `.gitleaks.toml` is written against this
#: release's config schema — so it is pinned explicitly and asserted here.
_GITLEAKS_VERSION = "8.24.3"

#: Top-level tables gitleaks 8.24.3 reads from a config file (`config.ViperConfig`).
#:
#: Plural `allowlists` is NOT in this list: it was added to gitleaks after 8.24.3. A config that
#: uses it is not rejected — Viper ignores the unknown key and the allowlist simply never applies,
#: which is how five consecutive CI runs failed while `.gitleaks.toml` looked perfectly correct.
_GITLEAKS_TOP_LEVEL_KEYS = frozenset({"description", "title", "extend", "allowlist", "rules"})

#: Fields of the singular global `[allowlist]` table in gitleaks 8.24.3. Note there is no
#: `description` field, so the rationale for each entry lives in TOML comments instead.
_GITLEAKS_ALLOWLIST_KEYS = frozenset({"commits", "paths", "regextarget", "regexes", "stopwords"})

#: Resolved to an absolute path once. Running a bare "git" would depend on PATH contents,
#: which is both a security smell and a portability one.
GIT = shutil.which("git")


def _is_shallow_clone() -> bool:
    """True when this working copy was cloned with a truncated history."""
    import subprocess

    if GIT is None:
        return False
    result = subprocess.run(  # noqa: S603 - fixed arguments, no shell, no user input
        [GIT, "rev-parse", "--is-shallow-repository"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() == "true"


def _git_available() -> bool:
    return GIT is not None and (REPO_ROOT / ".git").exists()


pytestmark = pytest.mark.skipif(
    not _git_available(),
    reason="not a git checkout (e.g. running from an installed wheel) — nothing to compare against",
)


def _git(*args: str) -> str:
    assert GIT is not None  # guaranteed by the module-level skipif
    result = subprocess.run(  # noqa: S603 - fixed arguments, no shell, no user input
        [GIT, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def _source_modules() -> list[Path]:
    """Every Python module that ships as part of the package."""
    return sorted(p for p in SOURCE_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def _tracked_files() -> set[str]:
    """Everything git knows about, plus everything currently staged.

    Staged files count as tracked: this suite runs before a commit, so a newly added module
    must not be reported missing just because the commit has not happened yet.
    """
    tracked = set(_git("ls-files").splitlines())
    staged = set(_git("diff", "--cached", "--name-only").splitlines())
    return {t for t in (tracked | staged) if t}


class TestSourceTreeIsTracked:
    def test_the_source_package_exists_on_disk(self) -> None:
        modules = _source_modules()
        assert modules, f"no modules found under {SOURCE_ROOT}"
        assert len(modules) >= 40  # Phase 3 ships 49; fail loudly if the tree looks truncated

    def test_every_source_module_is_in_the_repository(self) -> None:
        """The regression test. Compares the working tree against what git actually holds."""
        tracked = _tracked_files()
        missing = [
            str(p.relative_to(REPO_ROOT))
            for p in _source_modules()
            if str(p.relative_to(REPO_ROOT)) not in tracked
        ]
        assert not missing, (
            f"{len(missing)} source module(s) exist on disk but are NOT tracked by git, so a "
            f"fresh clone cannot import the package: {missing}. This is usually an unanchored "
            ".gitignore directory pattern such as `data/` or `secrets/` matching inside "
            "backend/src — anchor it with a leading slash."
        )

    def test_migrations_are_in_the_repository(self) -> None:
        tracked = _tracked_files()
        migrations = sorted((BACKEND / "migrations").glob("*.sql"))
        assert migrations, "no migration files found"
        missing = [
            str(p.relative_to(REPO_ROOT)) for p in migrations if str(p.relative_to(REPO_ROOT)) not in tracked
        ]
        assert not missing, f"untracked migrations: {missing}"

    def test_running_the_suite_leaves_no_database_in_the_repository(self) -> None:
        """Execute a test that builds the app with defaults, from the repository's own cwd.

        `Settings.database_url` defaults to a *relative* path, so without conftest's autouse cwd
        isolation the suite writes `backend/data/nexus.db` into the working tree — gitignored and
        therefore invisible, and shared between tests and between runs. This runs a real pytest
        subprocess instead of checking that the fixture exists, because a fixture can exist and
        not be autouse, and only the second case actually protects anything.
        """
        data_dir = BACKEND / "data"
        if data_dir.exists():
            shutil.rmtree(data_dir)  # start from a known state, whatever the last run left
        result = subprocess.run(  # noqa: S603 - fixed arguments, no shell, no user input
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_api.py",
                "-q",
                "-k",
                "test_app_state_holds_dependencies",
                "-p",
                "no:cacheprovider",
            ],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"the nested run failed: {result.stdout[-600:]}"
        assert not data_dir.exists(), (
            "running the suite wrote backend/data into the repository. conftest's autouse cwd "
            "isolation is missing or no longer autouse, so every app-building test appends to one "
            "shared, gitignored audit database"
        )


class TestGitignoreCannotSwallowSource:
    """`git check-ignore` asks git itself, so this catches patterns added later."""

    def test_no_source_directory_is_ignored(self) -> None:
        ignored = [
            str(p.relative_to(REPO_ROOT))
            for p in sorted(SOURCE_ROOT.rglob("*"))
            if p.is_dir() and "__pycache__" not in p.parts and _is_ignored(p)
        ]
        assert not ignored, f"git is ignoring source directories: {ignored}"

    def test_no_source_file_is_ignored(self) -> None:
        ignored = [str(p.relative_to(REPO_ROOT)) for p in _source_modules() if _is_ignored(p)]
        assert not ignored, f"git is ignoring source modules: {ignored}"

    def test_runtime_artifacts_are_still_ignored(self) -> None:
        """Anchoring must not turn into committing the tick archive or the audit database."""
        for candidate in (
            REPO_ROOT / "data" / "nexus.db",
            REPO_ROOT / "data" / "archive" / "bars" / "a.parquet",
            REPO_ROOT / "secrets" / "owner.yaml",
            REPO_ROOT / "backups" / "dump.sql",
            BACKEND / "data" / "nexus.sqlite",
        ):
            assert _is_ignored(candidate), f"{candidate} should be ignored but is not"

    def test_dot_env_is_still_ignored_but_the_template_is_not(self) -> None:
        assert _is_ignored(REPO_ROOT / ".env")
        assert _is_ignored(REPO_ROOT / ".env.local")
        assert not _is_ignored(REPO_ROOT / ".env.example")

    def test_pycache_is_still_ignored_inside_the_source_tree(self) -> None:
        """The source-tree negation must not resurrect compiled artifacts."""
        assert _is_ignored(SOURCE_ROOT / "__pycache__" / "x.cpython-311.pyc")
        assert _is_ignored(SOURCE_ROOT / "core" / "__pycache__")


class TestNoSecretMaterialIsTracked:
    def test_no_credential_shaped_file_is_tracked(self) -> None:
        dangerous = (".pem", ".key", ".p12", ".age", ".env")
        offenders = [
            t
            for t in _tracked_files()
            if any(t.endswith(suffix) for suffix in dangerous) and not t.endswith(".env.example")
        ]
        assert not offenders, f"credential-shaped files are tracked: {offenders}"

    def test_no_archive_or_database_file_is_tracked(self) -> None:
        artifacts = (".parquet", ".zst", ".sqlite", ".sqlite3", ".duckdb")
        offenders = [t for t in _tracked_files() if t.endswith(artifacts)]
        assert not offenders, f"runtime artifacts are tracked: {offenders}"


def _is_ignored(path: Path) -> bool:
    """Ask git whether its *rules* would ignore this path.

    ``--no-index`` is essential. Without it git consults the index, and a path that is
    already tracked reports as "not ignored" no matter what the rules say — which made an
    earlier version of this guard pass vacuously even with the offending pattern reinstated.
    The question worth asking is what would happen to a **fresh clone**, and that is a
    question about the rules alone.
    """
    assert GIT is not None  # guaranteed by the module-level skipif
    relative = str(path.relative_to(REPO_ROOT)) if path.is_absolute() else str(path)
    result = subprocess.run(  # noqa: S603 - fixed arguments, no shell, no user input
        [GIT, "check-ignore", "-q", "--no-index", relative],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


class TestCiWorkflowIsRunnable:
    """Both CI failures on the first two pushes were detectable offline.

    `aquasecurity/trivy-action@0.28.0` does not exist (the tags are `v`-prefixed), so two jobs
    died at "Set up job". And `docker-compose.yml` declares `MINIO_ROOT_USER` with the
    required-variable syntax `:?`, but the compose step exported only the three passwords, so
    `docker compose config` aborted before validating anything. Neither needs a runner to find.
    """

    WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    COMPOSE = REPO_ROOT / "docker-compose.yml"

    def test_the_workflow_and_compose_files_exist(self) -> None:
        assert self.WORKFLOW.is_file(), "CI workflow missing"
        assert self.COMPOSE.is_file(), "compose file missing"

    def test_every_required_compose_variable_is_supplied_by_ci(self) -> None:
        """A `${VAR:?...}` in compose aborts the parse unless CI exports it."""

        required = set(re.findall(r"\$\{([A-Z_][A-Z0-9_]*):\?", self.COMPOSE.read_text()))
        assert required, "expected compose to declare required variables"

        workflow = _load_workflow()
        step = next(
            (
                s
                for s in workflow["jobs"]["compose"]["steps"]
                if s.get("name") == "Validate docker-compose.yml"
            ),
            None,
        )
        assert step is not None, "the compose validation step is missing from CI"
        supplied = set(re.findall(r"([A-Z_][A-Z0-9_]*)=", step["run"]))
        missing = required - supplied
        assert not missing, (
            f"docker compose config will abort: required variable(s) {sorted(missing)} are "
            f"declared with `:?` in docker-compose.yml but never exported by the CI step"
        )

    def test_pinned_actions_use_tags_that_exist(self) -> None:
        """trivy-action publishes `v0.28.0`, not `0.28.0`; an unresolvable ref kills the job."""

        refs = re.findall(r"uses:\s*([\w.-]+/[\w.-]+)@([\w.+-]+)", self.WORKFLOW.read_text())
        assert refs, "no pinned actions found — the workflow probably changed shape"
        known_v_prefixed = {"aquasecurity/trivy-action"}
        for name, ref in refs:
            if name in known_v_prefixed:
                assert ref.startswith("v"), (
                    f"{name}@{ref}: this action publishes v-prefixed tags, so `{ref}` will not "
                    "resolve and the job fails at 'Set up job'"
                )
            assert not ref.startswith(("main", "master")), f"{name}@{ref} is an unpinned branch"

    def test_trivy_version_is_one_verified_to_resolve(self) -> None:
        """A tag existing is not sufficient — its *own* references must resolve too.

        `trivy-action@v0.28.0` is a real published tag, and it still failed every job at
        "Set up job", because its composite action hard-references
        `aquasecurity/setup-trivy@v0.2.1` — a tag that no longer exists (the oldest published
        is v0.2.6). No offline check can discover that; it was found by reading the failure.
        `v0.36.0` pins setup-trivy by commit hash to v0.2.6 and is verified to resolve.

        So this is a deliberate allowlist: bumping trivy must be a reviewed act, with the new
        version confirmed to run, not a guess at a version number.
        """

        verified = {"v0.36.0"}
        known_broken = {
            "0.28.0": "not a published tag (trivy-action tags are v-prefixed)",
            "v0.28.0": "references aquasecurity/setup-trivy@v0.2.1, which does not exist",
        }
        refs = re.findall(r"aquasecurity/trivy-action@([\w.+-]+)", self.WORKFLOW.read_text())
        assert refs, "trivy is no longer referenced — update this test deliberately"
        for ref in refs:
            assert ref not in known_broken, f"trivy-action@{ref} is known broken: {known_broken[ref]}"
            assert ref in verified, (
                f"trivy-action@{ref} has not been verified to resolve in CI. Confirm the run is "
                f"green, then add it to `verified`. Known broken: {known_broken}"
            )

    def test_ci_never_enables_live_trading(self) -> None:
        """The workflow's own environment must fail closed, matching the phase gate."""
        import yaml

        workflow = yaml.safe_load(self.WORKFLOW.read_text())
        env = workflow.get("env", {})
        assert env.get("NEXUS_LIVE_TRADING_ENABLED") == "false"
        assert env.get("NEXUS_ENVIRONMENT") == "DISABLED"

    def test_ci_runs_the_phase_gate_assertion(self) -> None:
        """If the assertion step is ever dropped, the gate stops being enforced in CI."""
        text = self.WORKFLOW.read_text()
        assert "real_money_orders_possible" in text
        assert "order_capability" in text
        assert "PHASE_GATE" in text

    def test_ci_runs_the_repo_hygiene_guard(self) -> None:
        """The guard that caught defect 12 must run in CI, not only on a developer machine."""
        text = self.WORKFLOW.read_text()
        assert "pytest" in text
        # The suite runs as a whole, so the hygiene module is included; assert it is not
        # excluded by a targeted selection that skips it.
        assert "--ignore" not in text, "CI excludes part of the suite"

    def test_a_healthcheck_only_probes_a_port_the_service_actually_opens(self) -> None:
        """Overriding `command:` discards the image's defaults, including the ports it opened.

        `nats:2-alpine` ships `CMD nats-server --config /etc/nats/nats-server.conf`, and that
        config file is what set `monitor_port: 8222`. compose replaced the command with
        `--jetstream --store_dir /data`, so nothing ever listened on 8222, the healthcheck could
        only ever get a connection refused, the container was permanently unhealthy, and `core` —
        which waits on `nats: condition: service_healthy` — never started. The whole stack was
        unstartable and nothing in the repository could say so, because a config parse succeeds and
        an image builds regardless. Only starting it found this (defect 36).

        The rule generalises: if a service both overrides its command and has an HTTP healthcheck,
        every port that healthcheck probes must be re-declared in the command.
        """
        compose = yaml.safe_load(self.COMPOSE.read_text())
        checked: list[str] = []
        for name, service in compose["services"].items():
            healthcheck = service.get("healthcheck") or {}
            command = service.get("command")
            if not healthcheck or command is None:
                continue
            probe = " ".join(str(part) for part in healthcheck.get("test") or [])
            args = " ".join(str(part) for part in command) if isinstance(command, list) else str(command)
            for port in sorted(set(re.findall(r"(?:127\.0\.0\.1|localhost):(\d+)", probe))):
                checked.append(f"{name}:{port}")
                assert port in args, (
                    f"service `{name}` healthcheck probes port {port} but its command does not "
                    f"enable it ({args!r}); the container will never become healthy and anything "
                    f"waiting on it will never start"
                )
        assert checked, (
            "no service both overrides its command and probes a local HTTP port, so this test has "
            "gone vacuous rather than passing"
        )


def _load_workflow() -> dict:
    import yaml

    return yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text())


class TestImageScanHasAnImageToScan:
    """Regression: both Trivy image steps failed on a ref that was never loaded.

    The build step had `push: false` and `load: false`, and a multi-platform image cannot be
    loaded into the daemon at all — one tag holds one architecture. So `nexus-core:ci` did not
    exist, and the scan errored out regardless of severity. Notably the step configured with
    `exit-code: "0"` failed too, which is the tell: the failure was not a finding, it was a
    missing image. This is checkable offline, from the workflow alone.
    """

    WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

    def _image_job(self) -> list[dict]:
        import yaml

        workflow = yaml.safe_load(self.WORKFLOW.read_text())
        return workflow["jobs"]["image"]["steps"]

    def _loaded_refs(self) -> set[str]:
        """Image refs that a build step actually loads into the daemon."""
        loaded: set[str] = set()
        for step in self._image_job():
            with_block = step.get("with") or {}
            if "build-push-action" in str(step.get("uses", "")) and with_block.get("load") is True:
                for tag in str(with_block.get("tags", "")).split():
                    loaded.add(tag.strip())
        return loaded

    def _scanned_refs(self) -> set[str]:
        refs: set[str] = set()
        for step in self._image_job():
            with_block = step.get("with") or {}
            if "trivy-action" in str(step.get("uses", "")) and with_block.get("image-ref"):
                refs.add(str(with_block["image-ref"]))
        return refs

    def test_a_build_step_loads_an_image(self) -> None:
        assert self._loaded_refs(), (
            "no build step has `load: true`, so nothing is present in the daemon for a "
            "scanner to read — a multi-arch build with load:false leaves no local image"
        )

    def test_every_scanned_ref_is_actually_loaded(self) -> None:
        scanned = self._scanned_refs()
        loaded = self._loaded_refs()
        assert scanned, "no Trivy image-ref found — the scan step changed shape"
        missing = scanned - loaded
        assert not missing, (
            f"Trivy scans {sorted(missing)} but no build step loads it; the scan will fail on a "
            f"missing image. Loaded refs: {sorted(loaded)}"
        )

    def test_no_image_is_pushed_to_a_registry(self) -> None:
        """D-019 and Phase 3: nothing is published, and no registry credential exists."""
        for step in self._image_job():
            with_block = step.get("with") or {}
            if "build-push-action" in str(step.get("uses", "")):
                assert with_block.get("push") is not True, f"step {step.get('name')} pushes an image"

    def test_multi_arch_build_is_still_proven(self) -> None:
        """The ARM64 Oracle host (D-021) must stay covered even though it cannot be loaded."""
        platforms = [
            str((step.get("with") or {}).get("platforms", ""))
            for step in self._image_job()
            if "build-push-action" in str(step.get("uses", ""))
        ]
        assert any("linux/arm64" in p for p in platforms), f"arm64 is no longer built: {platforms}"
        assert any("linux/amd64" in p for p in platforms), f"amd64 is no longer built: {platforms}"


class TestTrivyFindingsAreReadable:
    """O-011 existed because a gate's output could not be read from every environment.

    The first successful image build failed a combined HIGH,CRITICAL Trivy scan, and the
    findings were unreachable: GitHub serves job logs from a separate host, so the report could
    not be opened, triaged, or acted on. Splitting HIGH off made the build green but left the
    findings just as unreadable — not a resolution, only a quieter problem.

    Publishing the report as check annotations made it readable from anywhere, and there turned
    out to be exactly one finding, so HIGH blocks again. These tests execute the publishing step
    rather than merely asserting it exists: a shell heredoc embedded in YAML breaks silently on
    indentation, and "the step is present" would not notice. They also hold the blocking posture,
    because reverting to report-only is the easy way to make a future finding go away.
    """

    def _steps(self) -> list[dict]:
        return list(_load_workflow()["jobs"]["image"]["steps"])

    def _scan(self) -> dict:
        return next(s for s in self._steps() if str(s.get("name", "")).startswith("Trivy image scan"))

    def _publish(self) -> dict:
        return next(s for s in self._steps() if "annotations" in str(s.get("name", "")))

    def _script(self) -> str:
        """The embedded Python, extracted from the shell heredoc exactly as bash would."""
        run = str(self._publish()["run"])
        assert "<<'PY'" in run, "expected the report step to embed a quoted heredoc"
        return run.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]

    def test_there_is_one_image_scan_and_it_blocks_on_high_and_critical(self) -> None:
        """The split posture was a workaround for an unreadable report, not a risk decision."""
        scans = [s for s in self._steps() if str(s.get("name", "")).startswith("Trivy image scan")]
        assert len(scans) == 1, (
            f"{len(scans)} Trivy image scans: {[s.get('name') for s in scans]}. HIGH was split "
            "into a report-only step only while its findings could not be read; they can now."
        )
        with_ = self._scan()["with"]
        assert with_.get("exit-code") == "1", (
            "a vulnerability scan that cannot fail the build is a comment, not a gate"
        )
        severity = set(str(with_.get("severity", "")).split(","))
        assert {"HIGH", "CRITICAL"} <= severity, f"HIGH is no longer blocking: {sorted(severity)}"
        assert with_.get("format") == "json", "the report must be JSON to be reparsed"
        assert with_.get("output"), "the scan must write to a file, not only to the log"
        assert with_.get("ignore-unfixed") is True, (
            "without a fix there is nothing to act on; unfixed findings would make the gate "
            "permanently red, which is how gates get ignored"
        )

    def test_the_publish_step_reads_what_the_scan_writes(self) -> None:
        """Two steps agreeing on a filename is the kind of thing that drifts."""
        written = str(self._scan()["with"]["output"])
        assert written in str(self._publish()["run"]), (
            f"the scan writes {written} but the publish step never mentions it"
        )
        assert self._publish().get("if") == "${{ always() }}", (
            "must run even when the scan step is skipped or failed, or the findings vanish "
            "exactly when they are most interesting"
        )

    def test_the_embedded_script_parses(self) -> None:
        """Heredoc-in-YAML fails on indentation, not on logic. Check both layers."""
        import subprocess

        script = self._script()
        compile(script, "embedded-report-step", "exec")  # noqa: S102 - parse check, not eval
        bash = shutil.which("bash")
        if bash is not None:
            result = subprocess.run(  # noqa: S603 - fixed arguments, no shell, no user input
                [bash, "-n", "-c", str(self._publish()["run"])],
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, f"embedded shell does not parse: {result.stderr}"

    def _run_script(self, tmp_path: Path, report: str | None) -> subprocess.CompletedProcess[str]:
        import subprocess

        if report is not None:
            # Named from the workflow, so the test cannot drift from the step it exercises.
            (tmp_path / str(self._scan()["with"]["output"])).write_text(report)
        script = tmp_path / "emit.py"
        script.write_text(self._script())
        return subprocess.run(  # noqa: S603 - fixed arguments, no shell, no user input
            [sys.executable, str(script)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_findings_become_annotations_naming_the_cve_and_the_fix(self, tmp_path: Path) -> None:
        report = json.dumps(
            {
                "Results": [
                    {
                        "Target": "nexus-core:ci (debian 12)",
                        "Class": "os-pkgs",
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2025-12345",
                                "PkgName": "libssl3",
                                "InstalledVersion": "3.0.15",
                                "FixedVersion": "3.0.16",
                                "Severity": "HIGH",
                            }
                        ],
                    }
                ]
            }
        )
        result = self._run_script(tmp_path, report)
        assert result.returncode == 0, result.stderr
        out = result.stdout
        assert "::warning" in out, "findings must be warnings, not notices"
        assert "CVE-2025-12345" in out and "libssl3" in out
        assert "3.0.15" in out and "3.0.16" in out, "the available fix is the actionable part"
        assert "HIGH CVE-2025-12345" in out, "severity belongs on the finding, not only the total"
        assert "1 findings" in out, "the total must be stated, not implied"

    def test_critical_findings_are_counted_separately(self, tmp_path: Path) -> None:
        """CRITICAL is what blocks first; a total alone hides whether anything is that severe."""
        report = json.dumps(
            {
                "Results": [
                    {
                        "Target": "t",
                        "Class": "os-pkgs",
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2025-00001",
                                "PkgName": "libc6",
                                "InstalledVersion": "1",
                                "FixedVersion": "2",
                                "Severity": "CRITICAL",
                            },
                            {
                                "VulnerabilityID": "CVE-2025-00002",
                                "PkgName": "zlib1g",
                                "InstalledVersion": "1",
                                "FixedVersion": "2",
                                "Severity": "HIGH",
                            },
                        ],
                    }
                ]
            }
        )
        result = self._run_script(tmp_path, report)
        assert result.returncode == 0, result.stderr
        assert "2 findings (1 CRITICAL)" in result.stdout

    def test_a_clean_image_says_so_instead_of_staying_silent(self, tmp_path: Path) -> None:
        result = self._run_script(tmp_path, json.dumps({"Results": []}))
        assert result.returncode == 0, result.stderr
        assert "::notice" in result.stdout and "no HIGH or CRITICAL" in result.stdout

    def test_the_known_base_image_finding_is_still_fixed(self) -> None:
        """CVE-2025-47273 was the single finding that closed O-011. Its fix must not vanish.

        Trivy would catch a regression, but only in CI and only while the scan runs; this catches
        it in the suite, with the reason attached.

        The finding is a false positive, and establishing that took three attempts. setuptools is
        not installed in the image at all — CI probes the base image and the builder stage and
        both report ModuleNotFoundError. What the scanner reads is `pip/_vendor/bom.cdx.json`, a
        CycloneDX SBOM in which pip lists its own vendored dependencies; that manifest declares
        `pkg:pypi/setuptools@70.3.0`. Upgrading could not work (nothing was installed to upgrade,
        and no pip command rewrites a string inside pip's own SBOM) and neither could removal (it
        removed nothing). So pip goes instead: the runtime installs no packages, a package
        installer in the image is attack surface with no benefit, and pip is the only carrier of
        an SBOM anywhere in the tree.
        """
        dockerfile = (BACKEND / "Dockerfile").read_text()
        runtime = dockerfile.split("AS runtime", 1)[1]
        for interpreter in ("/usr/local/bin/python", "/opt/venv/bin/python"):
            assert f"{interpreter} -m pip uninstall -y pip setuptools" in runtime, (
                f"pip is no longer uninstalled from {interpreter}, so its vendored SBOM stays in "
                "the image and the scanner keeps reporting setuptools 70.3.0 as HIGH"
            )
            # The uninstall is not the fix; the assertion after it is. pip can leave the
            # dist-info behind, and the dist-info is exactly what a scanner reads.
            assert f"! {interpreter} -c 'import setuptools'" in runtime, (
                f"nothing verifies that {interpreter} can no longer import setuptools"
            )
        assert "! /opt/venv/bin/python -c 'import pip'" in runtime, (
            "nothing verifies pip is actually gone from the venv"
        )
        # The declaration the scanner reads, asserted absent by file content not package name.
        assert "--include='*.cdx.json'" in runtime, "the vendored SBOM is no longer asserted absent"
        # Removal must happen after the venv is copied in and before privileges are dropped.
        assert (
            runtime.index("COPY --from=builder /opt/venv")
            < runtime.index("pip uninstall -y pip setuptools")
            < runtime.index("USER nexus")
        ), "pip removal must run after the venv is copied and before `USER nexus`"

    def test_the_removal_does_not_match_pips_own_vendored_files(self) -> None:
        """A `find -name 'pkg_resources'` deletes part of pip and fails the build on a non-defect.

        This is the exact mistake that made the image job red: the assertion matched
        `pip/_vendor/pkg_resources`, a real and necessary part of pip that has nothing to do with
        the finding. Matching distribution metadata at the only depth a distribution can live at
        is what makes the check both effective and harmless, so a bare `pkg_resources` pattern
        must not come back — and because the removal is recursive, every pattern is enumerated.
        """
        runtime = (BACKEND / "Dockerfile").read_text().split("AS runtime", 1)[1]
        names = re.findall(r"-name '([^']+)'", runtime)
        assert names, "no find name patterns at all — the removal has silently stopped matching"
        assert "pkg_resources" not in names, (
            "matching a bare `pkg_resources` deletes pip's vendored copy and fails the build on "
            "a file that is not the finding"
        )
        allowed = {"pip", "pip-*.dist-info", "setuptools*"}
        for pattern in names:
            assert pattern in allowed, (
                f"unexpected removal pattern {pattern!r}; this deletes files recursively, so "
                "every pattern must be reviewed before it is added"
            )

    def test_the_sbom_check_targets_setuptools_not_every_manifest(self) -> None:
        """A blanket "no SBOM survives" check fails the build on a package that is not the finding.

        Measured in CI rather than assumed: the image carries two CycloneDX manifests and only
        pip's mentions setuptools. The other is
        `psycopg_binary-3.3.9.dist-info/sboms/auditwheel.cdx.json`, from the `postgres` extra — an
        extra the local dev venv does not install, which is exactly how the blanket version of this
        check came to be written and shipped. It cost a red build on a file that has nothing to do
        with the finding.

        The general lesson is the one worth keeping: a conclusion drawn from the dev environment
        about the contents of the image is not a conclusion about the image.
        """
        runtime = (BACKEND / "Dockerfile").read_text().split("AS runtime", 1)[1]
        assert "grep -rl setuptools --include='*.cdx.json'" in runtime, (
            "the SBOM check no longer searches manifest contents for the package that matters"
        )
        assert "-name '*.cdx.json'" not in runtime, (
            "a blanket SBOM check has returned; it fails the build on psycopg-binary's auditwheel "
            "manifest, which does not mention setuptools"
        )

    def test_the_dockerfile_survivor_check_is_not_vacuous(self) -> None:
        """`find a -o b -print -quit` binds the action to `b` only.

        Verified against a mock tree: with a setuptools dist-info present, the paren-less form
        matched zero items, so the assertion passed while the finding was still there. The
        grouping parentheses are what make the check mean anything, so they are asserted rather
        than trusted — the same reason `git check-ignore` is called with `--no-index`.
        """
        runtime = (BACKEND / "Dockerfile").read_text().split("AS runtime", 1)[1]
        # Raw string: the Dockerfile escapes the parens for the shell with a single
        # backslash, and a plain literal would need it doubled — ambiguity that has
        # already caused one false failure here.
        grouped = r"\( -name 'pip' -o -name 'pip-*.dist-info' -o -name 'setuptools*' \)"
        assert runtime.count(grouped) >= 2, (
            "the survivor check lost its grouping parentheses, so `-print -quit` applies only to "
            "the last branch and the other survivors go unreported"
        )
        assert "-print -quit" in runtime, "the survivor check no longer prints what it finds"

    def test_the_image_checks_exit_with_distinct_documented_codes(self) -> None:
        """A failed build publishes the failing command line but not the log.

        Six assertions in one RUN can therefore only report "one of these failed", which is what
        happened: the image job went red and nothing said which check had tripped. Each now exits
        with its own code, and the legend above the RUN names them. Both halves are asserted, so
        neither the codes nor the legend can drift — a legend that disagrees with the checks is
        worse than none, because it is believed.

        Every code was verified reachable on a mock tree, including 23 and 24, which fire only
        when setuptools is importable from a path the two search roots do not cover.
        """
        runtime = (BACKEND / "Dockerfile").read_text().split("AS runtime", 1)[1]
        block = runtime.split("# Each check exits", 1)[1].split("# Data directory", 1)[0]
        used = sorted(set(re.findall(r"\|\| exit (\d+)", block)))
        legend = sorted(set(re.findall(r"^#\s+(\d+) ", block, re.MULTILINE)))
        assert used == [str(n) for n in range(21, 27)], (
            f"the checks exit with {used}; expected the documented 21-26"
        )
        assert legend == used, (
            f"the legend documents {legend} but the checks exit with {used} — one of them has "
            "been edited without the other"
        )
        assert len(set(used)) == len(used), "two checks share an exit code and cannot be told apart"

    def test_the_image_installs_the_tz_database_its_entrypoint_needs(self) -> None:
        """The module the CMD runs builds `ZoneInfo("America/New_York")` at import time.

        `nexus.instruments.sessions` resolves two zones at module scope and `nexus.api.app`
        imports it, so without the IANA database the container raises ZoneInfoNotFoundError and
        dies before it binds a port. Reproduced locally with PYTHONTZPATH pointed at nothing.
        Nothing caught it before, because no container has ever been started and no test asserted
        the import — the kind of failure that surfaces only on the deployment host.
        """
        runtime = (BACKEND / "Dockerfile").read_text().split("AS runtime", 1)[1]
        assert "apt-get install -y --no-install-recommends curl tzdata" in runtime, (
            "tzdata is no longer installed explicitly; the entrypoint import would fail on any "
            "base image that does not happen to ship it"
        )

    def test_the_image_asserts_its_own_entrypoint_still_imports(self) -> None:
        """Removing pip is only safe to do blind if the build proves the venv still works.

        Nothing in CI has ever started this container, so a runtime dependency broken at build
        time would otherwise be discovered on the deployment host. Importing the module the CMD
        runs is the cheapest possible proof, and it verifies tzdata for real instead of trusting
        the package manager's exit code.
        """
        runtime = (BACKEND / "Dockerfile").read_text().split("AS runtime", 1)[1]
        assert "import nexus.api.app as m; assert callable(m.create_app)" in runtime, (
            "the image no longer verifies that its own entrypoint can be imported"
        )
        cmd = runtime.split("CMD ", 1)[1]
        assert "nexus.api.app:create_app" in cmd, (
            "the CMD changed; the build-time import assertion must follow it"
        )

    def test_a_missing_report_is_reported_not_crashed_on(self, tmp_path: Path) -> None:
        """The scan step can be skipped; the publish step must not then fail the job."""
        result = self._run_script(tmp_path, None)
        assert result.returncode == 0, f"a missing report must not break CI: {result.stderr}"
        assert "::warning" in result.stdout and "no report produced" in result.stdout

    def test_the_finding_list_is_capped_and_says_it_was(self, tmp_path: Path) -> None:
        """A base image can carry hundreds; the annotation is a pointer, not the report."""
        result = self._run_script(tmp_path, self._report_with(80))
        assert result.returncode == 0, result.stderr
        assert result.stdout.count("CVE-2025-") == 60, "expected the cap of 60 findings"
        assert "and 20 more" in result.stdout, "truncation must be stated, never silent"

    def test_findings_are_packed_into_one_annotation(self, tmp_path: Path) -> None:
        """GitHub Actions allows 10 annotations per level per step. Then it stops listening.

        This is not a hypothetical: the first diagnostic written for defect 23 emitted one
        annotation per line, and docker's image-pull progress consumed the entire budget, so the
        answer it was built to fetch never arrived. A report that emits one annotation per
        finding would lose everything past the tenth and the cap would look like the result.
        """
        result = self._run_script(tmp_path, self._report_with(80))
        assert result.returncode == 0, result.stderr
        warnings = [line for line in result.stdout.splitlines() if line.startswith("::")]
        assert len(warnings) <= 2, (
            f"{len(warnings)} annotations emitted; the per-step limit is 10 per level and the "
            "findings must be packed into one"
        )
        # Packing must not lose the findings: they survive as encoded newlines inside it.
        assert result.stdout.count("%0A") >= 60, "the packed annotation dropped finding lines"

    @staticmethod
    def _report_with(count: int) -> str:
        return json.dumps(
            {
                "Results": [
                    {
                        "Target": "t",
                        "Class": "os-pkgs",
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": f"CVE-2025-{i:05d}",
                                "PkgName": f"pkg{i}",
                                "InstalledVersion": "1.0",
                                "FixedVersion": "1.1",
                                "Severity": "HIGH",
                            }
                            for i in range(count)
                        ],
                    }
                ]
            }
        )


class TestSecretScanningIsNotWeakened:
    """`.gitleaks.toml` allowlists the detection code. This keeps that scope honest.

    An allowlist is how a security gate gets quietly turned off: one broad path, or a `ruleIDs`
    list, or a bare `[allowlist]` with no conditions at all, and the scanner still reports
    "passed" while finding nothing. These tests assert the config stays as narrow as it claims
    to be, so widening it breaks the build instead of silently reducing coverage.

    They also assert the config is *understood* by the gitleaks version CI runs, which is the
    failure that took five runs to find: a key gitleaks does not recognise is ignored without an
    error, so a config that looks correct can have no effect whatsoever.
    """

    CONFIG = REPO_ROOT / ".gitleaks.toml"

    def _parsed(self) -> dict:
        import tomllib

        with self.CONFIG.open("rb") as handle:
            return tomllib.load(handle)

    def _allowlist(self) -> dict:
        config = self._parsed()
        assert "allowlist" in config, (
            "no top-level [allowlist] table. gitleaks 8.24.3 reads exactly one singular allowlist; "
            "without it nothing in this repository is excused and the scan fails on fixtures."
        )
        return config["allowlist"]

    def test_the_config_uses_the_schema_the_pinned_gitleaks_understands(self) -> None:
        """Every key here must exist in gitleaks 8.24.3's `ViperConfig`, or it is ignored silently.

        This is the test that would have saved five failed runs. The previous version of this
        file used plural `[[allowlists]]` — valid in current gitleaks, but 8.24.3 declares only a
        singular `Allowlist` struct, so Viper dropped the unknown key without complaint. The
        config looked right, the scan kept reporting the same two findings, and nothing anywhere
        said why.
        """
        config = self._parsed()
        unknown_top = set(config) - _GITLEAKS_TOP_LEVEL_KEYS
        assert not unknown_top, (
            f"keys gitleaks {_GITLEAKS_VERSION} does not define: {sorted(unknown_top)}. It would "
            f"ignore them silently. Known: {sorted(_GITLEAKS_TOP_LEVEL_KEYS)}"
        )
        assert "allowlists" not in config, (
            "plural [[allowlists]] is not understood by gitleaks 8.24.3 and would be ignored "
            "without an error. Use the singular [allowlist] table."
        )
        unknown_keys = set(self._allowlist()) - _GITLEAKS_ALLOWLIST_KEYS
        assert not unknown_keys, (
            f"[allowlist] keys gitleaks {_GITLEAKS_VERSION} does not define: {sorted(unknown_keys)}. "
            f"Known: {sorted(_GITLEAKS_ALLOWLIST_KEYS)}"
        )

    def test_the_config_exists_and_extends_the_default_ruleset(self) -> None:
        assert self.CONFIG.is_file(), ".gitleaks.toml is missing — gitleaks would use defaults"
        config = self._parsed()
        assert config.get("extend", {}).get("useDefault") is True, (
            "the config must extend the default ruleset; replacing it would drop every built-in "
            "rule and let real credentials through"
        )

    def test_no_rule_is_disabled_globally(self) -> None:
        """Disabling a rule is repo-wide suppression with extra steps."""
        config = self._parsed()
        allowlist = self._allowlist()
        for key in ("ruleIDs", "targetRules"):
            assert not allowlist.get(key), (
                f"[allowlist] sets {key}={allowlist[key]}, which switches rules off globally. "
                "Scope by path or commit instead."
            )
        assert not config.get("rules"), (
            "defining `rules` here would shadow the default ruleset's rules of the same id"
        )
        assert not config.get("extend", {}).get("disabledRules"), (
            f"disabledRules={config['extend']['disabledRules']} turns built-in detection off"
        )

    def test_no_secret_shape_is_excused_anywhere(self) -> None:
        """`regexes` excuse a *shape* wherever it appears. This config must not use them.

        An earlier version allowlisted the fixtures by regex, which meant copying a fabricated
        JWT and a fabricated PEM into this file — and gitleaks then flagged the file itself.
        An allowlist that reproduces what it allowlists defeats itself.
        """
        allowlist = self._allowlist()
        assert not allowlist.get("regexes"), (
            f"[allowlist] uses regexes {allowlist['regexes']}, which would excuse that shape in "
            "every file in the repository. Scope by path or commit instead."
        )
        assert not allowlist.get("stopwords"), (
            f"stopwords {allowlist['stopwords']} would excuse any secret containing those words "
            "anywhere in the repository"
        )

    def test_the_allowlist_is_bound_to_narrow_paths(self) -> None:
        allowlist = self._allowlist()
        paths = allowlist.get("paths") or []
        assert paths, "an allowlist with no path scope applies everywhere"
        unexpected = [p for p in paths if p not in _SECRET_SHAPE_FILES]
        assert not unexpected, (
            f"allowlist covers {unexpected}, which are not the files whose job is to recognise "
            f"secret shapes. Permitted: {sorted(_SECRET_SHAPE_FILES)}"
        )
        missing = sorted(_SECRET_SHAPE_FILES - set(paths))
        assert not missing, (
            f"detection code no longer allowlisted: {missing}. Those files must spell out secret "
            "shapes to mask them, so the scan would fail on their fixtures."
        )

    def test_every_allowlisted_path_pattern_actually_matches_its_file(self) -> None:
        """A path regex that matches nothing is as useless as a key gitleaks ignores.

        gitleaks compiles each entry with `regexp.MustCompile` and matches it against the
        finding's path. A typo — a wrong escape, a bad separator — produces an allowlist entry
        that silently excuses nothing, which is the same failure mode as the plural-key bug and
        is just as invisible in a passing scan. So each pattern is required to match the real
        file it names, and that file is required to exist.
        """

        for pattern in self._allowlist().get("paths") or []:
            plain = pattern.replace("\\.", ".").replace("\\", "")
            assert (REPO_ROOT / plain).is_file(), (
                f"allowlist path {pattern!r} names {plain}, which does not exist — the entry "
                "would excuse nothing and should be removed or corrected"
            )
            compiled = re.compile(pattern)
            assert compiled.search(plain), f"pattern {pattern!r} does not match {plain!r}"

    def test_exactly_one_commit_is_excused(self) -> None:
        """A commit allowlist excuses history forever, so it must stay a closed set.

        The reason lives in the comments above the table rather than a `description` key:
        gitleaks 8.24.3's global allowlist struct has no such field, so writing one there would
        be ignored — the same silent-key trap this whole test class exists to catch.
        """
        excused = list(self._allowlist().get("commits") or [])
        assert excused == list(_ALLOWLISTED_COMMITS), (
            f"excused commits changed from {list(_ALLOWLISTED_COMMITS)} to {excused}. Each entry "
            "needs a documented reason in .gitleaks.toml and in _ALLOWLISTED_COMMITS."
        )
        text = self.CONFIG.read_text()
        for sha in _ALLOWLISTED_COMMITS:
            assert sha in text
        # The justification has to be written down next to the SHA, not just asserted here.
        assert "fabricated" in text, "the config must state that the excused values are fabricated"

    def test_the_excused_commit_exists_in_this_repository(self) -> None:
        """A typo'd SHA would silently excuse nothing — or, worse, look like it excuses something.

        Verifies for real wherever the commit object is present, and skips only when it is
        genuinely absent — which is what a depth-1 checkout looks like. Checking shallowness
        first would be wrong: this workspace *is* shallow, and the commit is still there,
        because it was made locally after the graft point. CI checks out with
        ``fetch-depth: 0`` so the verification always runs there.
        """
        import subprocess

        assert GIT is not None
        for sha in _ALLOWLISTED_COMMITS:
            result = subprocess.run(  # noqa: S603 - fixed arguments, no shell, no user input
                [GIT, "cat-file", "-e", f"{sha}^{{commit}}"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                continue
            if _is_shallow_clone():
                pytest.skip(f"shallow clone: commit {sha[:12]} is not present to verify")
            assert result.returncode == 0, (
                f"allowlisted commit {sha} does not exist in this repo — a typo'd SHA would "
                "silently excuse nothing while looking like it excuses something"
            )

    def test_head_carries_secret_shapes_only_in_allowlisted_paths(self) -> None:
        """The invariant the commit allowlist depends on: HEAD itself is clean elsewhere.

        Excusing one historical revision is only safe while no *current* file outside the
        allowlist contains a secret-shaped literal. This checks the working tree directly, so if
        a future commit reintroduces one the build fails instead of leaning on the old excuse.
        """
        header = "-----BEGIN PRIVATE KEY" + "-----"
        # Assembled from fragments, exactly like the PEM header above. Written contiguously, this
        # assertion would trip over its own search string — the test that looks for JWT literals
        # would itself contain one, which is the same self-defeating move that broke the first
        # version of `.gitleaks.toml`. gitleaks needs three dot-separated segments to fire, but
        # this sweep is deliberately stricter than the scanner, so it has to hold itself to that.
        jwt_prefix = "eyJhbGci" + "OiJIUzI1NiJ9"
        offenders: list[str] = []
        for path in _tracked_files():
            if path in _SECRET_SHAPE_PLAIN:
                continue
            full = REPO_ROOT / path
            if not full.is_file():
                continue
            try:
                content = full.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            if header in content or jwt_prefix in content:
                offenders.append(path)
        assert not offenders, (
            f"secret-shaped literals outside the allowlisted detection code: {offenders}. "
            "Either remove them or justify widening the allowlist."
        )

    def test_the_config_contains_no_secret_shaped_literal_of_its_own(self) -> None:
        """An allowlist that reproduces what it allowlists defeats itself.

        An earlier version scoped the fixtures by regex, which meant copying a fake JWT and a
        fake PEM into `.gitleaks.toml` — and gitleaks then flagged the config file itself,
        failing a build that had been green. Path scoping only.
        """
        text = self.CONFIG.read_text()
        header = "-----BEGIN PRIVATE KEY" + "-----"  # assembled so this file is not itself a hit
        assert header not in text, ".gitleaks.toml contains a PEM header literal"
        assert "eyJhbGci" not in text, ".gitleaks.toml contains a JWT literal"
        assert "AKIA" not in text, ".gitleaks.toml contains an AWS key shape"
        own_source = Path(__file__).read_text()
        assert header not in own_source, "this test must not embed a PEM header literal either"

    def test_ci_pins_the_gitleaks_version_this_schema_targets(self) -> None:
        """The config's meaning depends on the gitleaks release that reads it.

        gitleaks-action@v2 defaults to a version hard-coded in its own source, which changes when
        the action is updated. Pinning it keeps `[allowlist]` semantics — and therefore the tests
        above — tied to a known release instead of drifting.
        """
        import yaml

        workflow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text())
        steps = workflow["jobs"]["secrets"]["steps"]
        gitleaks = next(s for s in steps if "gitleaks" in str(s.get("uses", "")))
        pinned = (gitleaks.get("env") or {}).get("GITLEAKS_VERSION")
        assert pinned == _GITLEAKS_VERSION, (
            f"CI runs gitleaks {pinned} but .gitleaks.toml and these tests are written for "
            f"{_GITLEAKS_VERSION}. Re-check the config schema against the new version before "
            "changing this."
        )

    def test_ci_passes_no_ignored_inputs_to_gitleaks(self) -> None:
        """gitleaks-action@v2 accepts no inputs; `config-path` is warned about and discarded."""
        import yaml

        workflow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text())
        steps = workflow["jobs"]["secrets"]["steps"]
        gitleaks = next(s for s in steps if "gitleaks" in str(s.get("uses", "")))
        assert not gitleaks.get("with"), (
            f"gitleaks-action@v2 takes no inputs; {list(gitleaks['with'])} would be ignored with "
            "an 'Unexpected input(s)' warning. The binary auto-discovers .gitleaks.toml."
        )

    def test_the_config_sits_where_gitleaks_auto_discovers_it(self) -> None:
        """Auto-discovery is the only mechanism now, so the location is load-bearing."""
        assert (REPO_ROOT / ".gitleaks.toml").is_file()

    def test_ci_permissions_are_still_least_privilege(self) -> None:
        """pull-requests: write is needed to post findings; contents: write would not be."""
        import yaml

        workflow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text())
        perms = workflow.get("permissions", {})
        assert perms.get("contents") == "read", f"contents permission widened: {perms.get('contents')}"
        assert perms.get("pull-requests") == "write"
        for scope in ("issues", "deployments", "packages", "actions", "checks", "statuses"):
            assert scope not in perms, f"unexpected permission grant: {scope}"

    def test_the_allowlisted_fixtures_are_still_fake(self) -> None:
        """The allowlist is justified only while those literals unlock nothing.

        The expected values are assembled from fragments on purpose. Writing a full PEM header
        into this file would make *this* file a gitleaks hit — which is exactly the mistake the
        first version of `.gitleaks.toml` made, and the reason a secret-scanning fix has to be
        checked for what it adds, not only for what it removes.
        """
        text = (BACKEND / "tests" / "test_secrets_and_redaction.py").read_text()
        begin = "-----BEGIN PRIVATE KEY" + "-----"
        end = "-----END" + " PRIVATE KEY-----"
        body = "MII" + "E"
        # The fabricated JWT signature and the four-character PEM body are the whole point:
        # if either is ever replaced with something real, this test fails before gitleaks does.
        assert "abcdefghijklmnopqrstuv" in text, "the JWT fixture signature changed"
        assert f"{begin}\\n{body}\\n{end}" in text, (
            "the PEM fixture changed — re-verify it is still fabricated, then update the allowlist"
        )
        own_source = Path(__file__).read_text()
        assert begin not in own_source and end not in own_source, (
            "this test file must not contain an assembled PEM literal of its own"
        )

    def test_no_real_credential_shaped_literal_exists_anywhere(self) -> None:
        """A coarse sweep, independent of gitleaks, over every tracked text file."""

        patterns = {
            "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
            "slack_token": re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
            "github_pat": re.compile(r"gh[pousr]_[0-9A-Za-z]{20,}"),
            "openai_style_key": re.compile(r"sk-[0-9A-Za-z]{20,}"),
            "pem_body": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----\s*\n[MII]{4,}[0-9A-Za-z+/]{40,}"),
        }
        # The detection code and its fixtures are allowed to mention these shapes; nothing else
        # is. This sweep is deliberately independent of gitleaks: it runs offline, in the test
        # suite, and covers the files gitleaks is told to skip.
        permitted = set(_SECRET_SHAPE_PLAIN) | {".gitleaks.toml", "backend/tests/test_repo_hygiene.py"}
        offenders: list[str] = []
        for path in _tracked_files():
            if path in permitted or not path.endswith(
                (".py", ".md", ".yml", ".yaml", ".toml", ".sql", ".env")
            ):
                continue
            full = REPO_ROOT / path
            if not full.is_file():
                continue
            try:
                content = full.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            for name, pattern in patterns.items():
                if pattern.search(content):
                    offenders.append(f"{path}: {name}")
        assert not offenders, f"credential-shaped literals outside the permitted fixtures: {offenders}"

    def test_the_backend_job_checks_out_full_history(self) -> None:
        """The hygiene suite verifies a historical commit, so a depth-1 checkout cannot run it.

        This failed in CI before it was asserted: the default `fetch-depth: 1` left the excused
        commit object absent, and the SHA check reported a valid configuration as broken.
        """
        import yaml

        workflow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text())
        checkout = next(
            s for s in workflow["jobs"]["backend"]["steps"] if "actions/checkout" in str(s.get("uses", ""))
        )
        assert (checkout.get("with") or {}).get("fetch-depth") == 0, (
            "the backend job must check out full history (fetch-depth: 0), or "
            "test_the_excused_commit_exists_in_this_repository cannot run"
        )


class TestDocumentedConfigurationIsHonoured:
    """Every variable the deployment sets or the docs recommend must reach something that reads it.

    `.env.example` advertised `NEXUS_DATABASE_URL=postgresql+psycopg://...` as the compose variant
    and `docker-compose.yml` ships a TimescaleDB service for it, but no Postgres store existed: an
    operator who followed the documentation got an in-memory audit log that vanished on every
    restart, while `/healthz` and `/readyz` both reported success. The variable reached the process
    and nothing honoured it — a documented capability that did not exist, which is worse than an
    undocumented one, because it is trusted.

    The code now refuses an unsupported scheme (see `TestAuditStoreSelectionFailsClosed` in
    `test_api.py`). These tests guard the other half: that the deployment files, the documentation
    and the code agree about what exists.
    """

    @staticmethod
    def _names_something_honours() -> set[str]:
        """Every `NEXUS_*` name that something actually reads.

        Four places, because a variable can be honoured without appearing in Python source at all:
        a `Settings` field (six models, each with its own env prefix), an `os.environ` read, a
        Caddyfile or compose template expansion, and the secrets naming convention.
        """
        from pydantic_settings import BaseSettings

        import nexus.core.config as config_module
        from nexus.core.config import Settings
        from nexus.secrets.provider import EnvSecretProvider

        names: set[str] = set()
        for candidate in vars(config_module).values():
            if (
                isinstance(candidate, type)
                and issubclass(candidate, BaseSettings)
                and candidate is not BaseSettings
            ):
                prefix = candidate.model_config.get("env_prefix", "")
                names |= {f"{prefix}{field}".upper() for field in candidate.model_fields}

        for path in (BACKEND / "src" / "nexus").rglob("*.py"):
            names |= set(re.findall(r'"(NEXUS_[A-Z0-9_]+)"', path.read_text()))

        # `NEXUS_HOST` is consumed by Caddy, not by Python: `{$NEXUS_HOST::80}` in the Caddyfile.
        for path in (REPO_ROOT / "infra").rglob("*"):
            if path.is_file():
                names |= set(re.findall(r"(NEXUS_[A-Z0-9_]+)", path.read_text(errors="ignore")))
        names |= set(re.findall(r"(NEXUS_[A-Z0-9_]+)", (REPO_ROOT / "docker-compose.yml").read_text()))

        # The secrets convention: reference `owner/api-token` is read as
        # NEXUS_SECRET_OWNER_API_TOKEN. Derived through the provider's own function, so this test
        # cannot drift from the implementation it is checking.
        secrets = Settings(_env_file=None).secrets
        names |= {
            EnvSecretProvider._var_name(getattr(secrets, field))  # noqa: SLF001 - the convention
            for field in type(secrets).model_fields
            if field.startswith("ref_")
        }
        return names

    @staticmethod
    def _documented_secret_vars() -> dict[str, str]:
        from nexus.core.config import Settings
        from nexus.secrets.provider import EnvSecretProvider

        secrets = Settings(_env_file=None).secrets
        return {
            field: EnvSecretProvider._var_name(getattr(secrets, field))  # noqa: SLF001
            for field in type(secrets).model_fields
            if field.startswith("ref_")
        }

    def test_no_deployment_variable_is_silently_ignored(self) -> None:
        compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text())
        set_in_compose: set[str] = set()
        for service in compose["services"].values():
            set_in_compose |= {key for key in (service.get("environment") or {}) if key.startswith("NEXUS_")}
        documented = set(
            re.findall(
                r"^#?\s*(NEXUS_[A-Z0-9_]+)=",
                (REPO_ROOT / ".env.example").read_text(),
                re.MULTILINE,
            )
        )
        assert set_in_compose, "compose sets no NEXUS_* variables — this check has gone vacuous"
        assert documented, ".env.example documents no NEXUS_* variables — this check has gone vacuous"
        unknown = sorted((set_in_compose | documented) - self._names_something_honours())
        assert not unknown, (
            "these variables are set by the deployment or recommended by .env.example but are read "
            f"by nothing — not a Settings field, not os.environ, not the Caddyfile or compose file, "
            f"and not the secrets convention, so they are silently ignored: {unknown}"
        )

    def test_every_secret_reference_the_code_declares_is_documented(self) -> None:
        """The other direction: a secret the code requires but the documentation never mentions.

        Found while writing the test above. `owner/totp-secret` — the step-up factor for releasing
        an emergency halt — was absent from `.env.example`. An operator following the documentation
        would bring up a system whose halt could be engaged but never released, and nothing would
        explain why until the first incident needed it.
        """
        example = (REPO_ROOT / ".env.example").read_text()
        undocumented = sorted(
            f"{var} (from `{field}`)"
            for field, var in self._documented_secret_vars().items()
            if var not in example
        )
        assert not undocumented, (
            f"the secrets provider will look these up and .env.example never mentions them: {undocumented}"
        )

    def test_the_documented_database_url_is_one_the_code_accepts(self) -> None:
        example = (REPO_ROOT / ".env.example").read_text()
        active = re.findall(r"^NEXUS_DATABASE_URL=(\S+)$", example, re.MULTILINE)
        assert active == ["sqlite:///./data/nexus.db"], (
            f".env.example sets NEXUS_DATABASE_URL to {active}; only sqlite:/// is implemented and "
            "anything else now refuses startup"
        )
        assert "postgresql+psycopg://nexus:CHANGE_ME" not in example, (
            "the Postgres example is back. Following it used to produce a silently ephemeral audit "
            "log; it now prevents the container from starting. Either way it must not be presented "
            "as a working option until a Postgres store exists"
        )

    def test_the_compose_default_database_url_starts(self) -> None:
        """A `docker compose up` with no .env must not hit the refusal."""
        raw = (REPO_ROOT / "docker-compose.yml").read_text()
        match = re.search(r"NEXUS_DATABASE_URL:\s*\$\{NEXUS_DATABASE_URL:-([^}]+)\}", raw)
        assert match, "the compose default for NEXUS_DATABASE_URL is gone"
        assert match.group(1).startswith("sqlite:///"), (
            f"compose defaults NEXUS_DATABASE_URL to {match.group(1)!r}, which the app refuses; a "
            "default bring-up would fail to start"
        )


# --------------------------------------------------------------------- runtime smoke test
@contextmanager
def _serving_real_app() -> Iterator[str]:
    """Serve the real application over a real socket and yield its base URL.

    ``TestClient`` calls the ASGI app in-process, which is the right tool for asserting route
    behaviour and the wrong tool for asserting that a *process* serves: it never binds a port, so
    it cannot notice a startup failure, a bad bind address, or a body that only serialises over a
    real connection. These tests run the checker against something that is actually listening.

    The port is ephemeral (0) and read back from the bound socket, so the tests neither need a
    free port nor can collide with one.
    """
    import uvicorn

    from nexus.api.app import create_app
    from nexus.core.config import Settings

    config = uvicorn.Config(
        create_app(settings=Settings(_env_file=None)),
        host="127.0.0.1",
        port=0,
        log_level="critical",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 60
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "the application never started serving; the smoke tests cannot run"
    try:
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=30)


def _closed_port() -> int:
    """A port nothing is listening on, obtained by binding one and letting it go."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _run_checker(base_url: str, *, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, NEXUS_SMOKE_BASE_URL=base_url, **(extra_env or {}))
    return subprocess.run(  # noqa: S603 - fixed arguments, no shell, no user input
        [sys.executable, str(REPO_ROOT / "infra" / "smoke_check.py")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


class TestTheRuntimeSmokeTestIsWiredUp:
    """A bring-up check that nothing runs is worse than none, because it is trusted.

    Phase 3 shipped with every runtime claim inferred from a build: the image compiled and its
    entrypoint imported, which says nothing about whether a process serves a request, whether the
    non-root user can write its audit database, or whether the image HEALTHCHECK ever answers.
    Defects 31, 32 and 34 were all found by reading files, and all three would have been found
    immediately by starting the stack once. `infra/smoke-test.sh` is that start, and the CI job
    below is what keeps it from rotting into a script nobody runs.
    """

    WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    SCRIPT = REPO_ROOT / "infra" / "smoke-test.sh"
    CHECKER = REPO_ROOT / "infra" / "smoke_check.py"

    def _smoke_job(self) -> dict:
        workflow = yaml.safe_load(self.WORKFLOW.read_text())
        assert "smoke" in workflow["jobs"], "the CI workflow no longer has a `smoke` job"
        return dict(workflow["jobs"]["smoke"])

    def test_both_scripts_exist(self) -> None:
        assert self.SCRIPT.is_file(), "infra/smoke-test.sh is missing"
        assert self.CHECKER.is_file(), "infra/smoke_check.py is missing"

    def test_ci_runs_the_smoke_script(self) -> None:
        runs = " ".join(str(step.get("run", "")) for step in self._smoke_job()["steps"])
        assert "infra/smoke-test.sh" in runs, "no CI step executes the smoke script"

    def test_the_smoke_script_runs_the_checker(self) -> None:
        assert "smoke_check.py" in self.SCRIPT.read_text(), (
            "the bring-up script never runs the in-container checker, so nothing is asserted "
            "from inside the running process"
        )

    def test_the_smoke_script_parses(self) -> None:
        """Executed rather than eyeballed: a malformed `sed`/`[` expression aborts silently."""
        shell = shutil.which("sh")
        if shell is None:
            pytest.skip("no POSIX shell available")
        result = subprocess.run(  # noqa: S603 - fixed arguments, no shell, no user input
            [shell, "-n", str(self.SCRIPT)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, f"infra/smoke-test.sh does not parse: {result.stderr}"

    def test_the_smoke_job_loads_the_image_compose_names(self) -> None:
        """`load: true` under compose's own tag, or `compose up` has no image to start.

        The same mistake already cost a CI cycle in the `image` job: a multi-platform build with
        `push: false` and `load: false` leaves no image in the daemon at all, because one tag
        holds one architecture. The tag is read from docker-compose.yml rather than written here,
        so renaming the image cannot silently desynchronise the two.
        """
        compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text())
        wanted = str(compose["services"]["core"]["image"])

        loaded: set[str] = set()
        for step in self._smoke_job()["steps"]:
            block = step.get("with") or {}
            if "build-push-action" in str(step.get("uses", "")) and block.get("load") is True:
                loaded.update(tag.strip() for tag in str(block.get("tags", "")).split())

        assert wanted in loaded, (
            f"the smoke job does not load {wanted} into the daemon; loaded: {sorted(loaded) or 'nothing'}"
        )

    def test_the_smoke_job_publishes_a_readable_report(self) -> None:
        """Job logs are served from a host outside this environment's egress allowlist.

        That is what made O-011 untriageable: a red build whose findings could not be opened. The
        smoke report is republished as a check annotation for the same reason, and it matters most
        on the runs that fail — which is exactly when the log is unreachable.
        """
        steps = self._smoke_job()["steps"]
        publishing = [
            step
            for step in steps
            if "always()" in str(step.get("if", "")) and "::" in str(step.get("run", ""))
        ]
        assert publishing, "no `if: always()` step publishes annotations, so a failure is unreadable"
        body = " ".join(str(step.get("run", "")) for step in publishing)
        assert "smoke-report.txt" in body, "the annotation step does not read the smoke report"

    def test_the_smoke_job_is_not_gated_behind_the_lint_and_build_jobs(self) -> None:
        """A lint failure must not hide a runtime failure.

        These are independent signals about different things. Chaining them means the runtime
        verdict arrives only on pushes that are already lint-clean, which is precisely when it is
        least interesting.
        """
        needs = self._smoke_job().get("needs") or []
        if isinstance(needs, str):
            needs = [needs]
        assert not set(needs) & {"backend", "image"}, f"the smoke job is gated behind {sorted(needs)}"


class TestTheSmokeCheckerIsExecutedNotJustPresent:
    """The checker is run here, against the real app, on every push.

    Asserting that a check script exists proves nothing about whether it passes, and a checker
    that has never been executed against a live process is a hypothesis. Running it here also
    means a bug in the *checker* is caught offline instead of surfacing as a confusing red
    container job. Two defects found while writing it are now regression-tested below: it
    crashed with a traceback when nothing was listening, and one of its route probes used the
    wrong HTTP method and so failed against a correct application.
    """

    def test_the_checker_passes_against_the_real_running_app(self) -> None:
        with _serving_real_app() as base_url:
            result = _run_checker(base_url)
        assert result.returncode == 0, (
            f"the smoke checker failed against a real, serving application:\n"
            f"{result.stdout[-3000:]}\n{result.stderr[-1000:]}"
        )
        assert "checks passed" in result.stdout

    def test_the_checker_reports_an_unreachable_process_rather_than_crashing(self) -> None:
        """A dead container must produce a report, not a Python traceback.

        The first version caught only HTTPError, so a connection refusal escaped as an unhandled
        URLError. The least useful possible output from a bring-up check is a stack trace saying
        the process was not there — that is the one thing the operator already suspects.
        """
        result = _run_checker(f"http://127.0.0.1:{_closed_port()}")
        assert result.returncode != 0, "an unreachable process must fail the check"
        assert "Traceback" not in result.stderr, f"the checker crashed instead of reporting:\n{result.stderr}"
        assert "FAIL" in result.stdout, "the failure was not reported as a check result"

    def test_the_checker_refuses_a_non_http_base_url(self) -> None:
        """The URL comes from the environment, so it is constrained rather than trusted."""
        result = _run_checker("file:///etc/passwd")
        assert result.returncode != 0
        assert "must be http(s)" in (result.stdout + result.stderr)

    def test_the_runtime_image_checks_are_not_vacuous(self) -> None:
        """The image-only checks must be capable of failing, or they assert nothing.

        This is the negative control for the checks that distinguish the container from a dev
        interpreter: pip and setuptools are removed from the image, and a development virtualenv
        has both. If this stops failing outside the image, the checks have gone quiet rather than
        correct. It skips when the interpreter has neither module, because then the control
        genuinely cannot fire and saying so is better than passing.
        """
        import importlib.util

        if importlib.util.find_spec("setuptools") is None and importlib.util.find_spec("pip") is None:
            pytest.skip("this interpreter has neither setuptools nor pip, so the control cannot fire")

        with _serving_real_app() as base_url:
            result = _run_checker(base_url, extra_env={"NEXUS_SMOKE_RUNTIME_CHECKS": "1"})
        assert result.returncode != 0, (
            "the runtime-image checks passed outside the runtime image, so they cannot be "
            "distinguishing anything"
        )
        assert "is absent from the runtime image" in result.stdout


class TestLiveEndpointVerificationIsGatedAndReadable:
    """O-009 and O-010 need a host with egress, and the development sandbox is not one.

    A test that cannot run must say so loudly rather than look like it passed. The live module
    skips at module level unless ``NEXUS_LIVE_VERIFY=1``, and the workflow that sets it publishes
    its measurements as an annotation because job logs are unreachable from here. Two details in
    that chain are load-bearing and were each found by running it rather than by reading it: pytest
    writes no captured stdout into its JUnit XML by default, so without ``junit_logging=all`` the
    report holds statuses and no numbers; and a run where every source was unreachable must fail,
    because a verification that verified nothing is not a pass.
    """

    WORKFLOW = REPO_ROOT / ".github" / "workflows" / "venue-verification.yml"
    MODULE = BACKEND / "tests" / "test_live_endpoints.py"

    def _steps(self) -> list[dict]:
        workflow = yaml.safe_load(self.WORKFLOW.read_text())
        return list(workflow["jobs"]["live"]["steps"])

    def _publish_step(self) -> str:
        for step in self._steps():
            if str(step.get("name", "")).startswith("Publish"):
                # Named-step lookup, not a bare `if: always()` search: the upload step carries the
                # same condition, so matching on the condition alone cannot tell them apart.
                assert "always()" in str(step.get("if", "")), (
                    "the report step must run on failure too — that is when it matters most"
                )
                return str(step.get("run", ""))
        raise AssertionError("no step publishes the verification report")

    def test_the_workflow_and_module_exist(self) -> None:
        assert self.WORKFLOW.is_file()
        assert self.MODULE.is_file()

    def test_the_live_marker_is_registered(self) -> None:
        """`--strict-markers` is on, so an unregistered marker fails collection outright."""
        import tomllib

        config = tomllib.loads((BACKEND / "pyproject.toml").read_text())
        markers = config["tool"]["pytest"]["ini_options"].get("markers") or []
        assert any(str(m).startswith("live:") for m in markers), f"markers: {markers}"

    def test_the_module_skips_without_the_flag_and_runs_with_it(self) -> None:
        """Executed, not asserted from the source: the gate has to hold in both directions.

        Both directions use `--collect-only`, because with the flag set the tests really would
        contact Bybit, OKX, Binance Vision and Dukascopy — and this hygiene module runs in the
        ordinary CI job, which must not make market-data requests on every push.
        """
        base = [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_live_endpoints.py",
            "-p",
            "no:cacheprovider",
            "--no-header",
            "--collect-only",
        ]
        gated = subprocess.run(  # noqa: S603 - fixed arguments, no shell, no user input
            base,
            cwd=BACKEND,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "NEXUS_LIVE_VERIFY": ""},
        )
        assert "no tests collected" in gated.stdout, (
            f"without the flag the module must collapse to its module-level skip and collect "
            f"nothing, so the ordinary suite never touches the network. Got rc={gated.returncode}: "
            f"{gated.stdout[-400:]}"
        )

        live = subprocess.run(  # noqa: S603 - fixed arguments, no shell, no user input
            base,
            cwd=BACKEND,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "NEXUS_LIVE_VERIFY": "1"},
        )
        collected = re.search(r"(\d+) tests? collected", live.stdout)
        assert live.returncode == 0 and collected is not None, (
            f"with the flag the module must collect every live check. rc={live.returncode}: "
            f"{live.stdout[-400:]}"
        )
        assert int(collected.group(1)) >= 10, (
            f"only {collected.group(1)} live checks collected; the module has quietly lost coverage"
        )

    def _commands(self) -> str:
        """The run steps' commands with comment lines stripped.

        Asserting on the raw text is vacuous here: this workflow *explains* `junit_logging=all` in a
        comment as well as using it, so a control that deleted the flag from the command still
        matched the prose and the test passed while the report went empty. Only what executes counts.
        """
        lines = []
        for step in self._steps():
            for line in str(step.get("run", "")).splitlines():
                if not line.strip().startswith("#"):
                    lines.append(line)
        return " ".join(lines)

    def test_the_workflow_requests_captured_output_in_the_report(self) -> None:
        """Without this the JUnit XML holds statuses and none of the measurements."""
        commands = self._commands()
        assert "-o junit_logging=all" in commands, (
            "pytest writes no captured stdout into its JUnit XML by default, so the EVIDENCE lines "
            "the annotation is built from would never reach the report"
        )
        assert "NEXUS_LIVE_VERIFY=1" in commands, "the module-level skip is never lifted"

    def test_the_workflow_marks_the_live_tests_it_runs(self) -> None:
        """`-m live` must reach pytest as a command, not only be described in a comment."""
        assert "-m live" in self._commands()

    def test_the_annotation_budget_is_measured_after_escaping(self) -> None:
        """GitHub truncates an annotation at 4096 characters *silently*, after escaping.

        Escaping expands the text — ":" becomes "%3A", "," becomes "%2C", a newline becomes "%0A" —
        so budgeting the raw length is not enough. That mistake cost the Dukascopy layout evidence,
        the whole point of the run, which was cut off mid-value. The budget must be applied to the
        escaped form and the escaping must happen inside the same function that enforces the cap.
        """
        body = self._publish_step()
        assert "LIMIT = 4096" in body, (
            "GitHub's annotation cap is 4096 characters; a larger budget is silently truncated"
        )
        # Anchored on the guard itself, not on `len(escape(` appearing anywhere: the function also
        # escapes when printing and when measuring the truncation loop, so a loose search still
        # matched after a control replaced the guard with the raw length (a vacuous assertion).
        assert re.search(r"if len\(escape\(text\)\) <= LIMIT", body), (
            "the cap must be compared against the ESCAPED length, or a body full of URLs and "
            "commas escapes past the limit and loses its tail"
        )
        assert "%3A" in body and "%2C" in body and "%0A" in body, (
            "the escaping that expands the text is missing"
        )

    def test_the_workflow_publishes_the_report_as_an_annotation(self) -> None:
        body = self._publish_step()
        assert "::" in body and "live-report.xml" in body

    def test_a_run_that_verified_nothing_is_not_reported_as_a_pass(self) -> None:
        """Executed against a real report shape: all-skipped must exit non-zero."""
        script = re.search(r"python3 - <<'PY'\n(.*)\nPY\n", self._publish_step(), re.S)
        assert script is not None, "could not extract the embedded report script"
        work = BACKEND.parent / ".pytest-live-control"
        work.mkdir(exist_ok=True)
        try:
            (work / "vv.py").write_text(script.group(1))
            (work / "live-report.xml").write_text(
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<testsuites><testsuite tests="2" failures="0" errors="0" skipped="2">'
                '<testcase classname="tests.test_live_endpoints.TestBybitLiveEndpoints" name="test_a">'
                '<skipped message="bybit did not answer"/></testcase>'
                '<testcase classname="tests.test_live_endpoints.TestOkxLiveEndpoints" name="test_b">'
                '<skipped message="okx did not answer"/></testcase>'
                "</testsuite></testsuites>\n"
            )
            result = subprocess.run(  # noqa: S603 - fixed arguments, no shell, no user input
                [sys.executable, "vv.py"], cwd=work, capture_output=True, text=True, check=False
            )
            assert result.returncode != 0, (
                f"an all-skipped run exited 0, so a verification that reached nothing would look "
                f"green: {result.stdout[:300]}"
            )
            assert "NOTHING WAS VERIFIED" in result.stdout
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_live_workflow_needs_no_credential_of_any_kind(self) -> None:
        """D-026: these are public endpoints. A secret reference here would be a design change."""
        text = self.WORKFLOW.read_text()
        assert "secrets." not in text, "the verification workflow reads a secret"
        # Substrings that would indicate an authenticated call. Deliberately not the bare word
        # "token": this module rate-limits through `TokenBucket`, and a check that fires on a rate
        # limiter teaches everyone to ignore it.
        module = self.MODULE.read_text().lower()
        for shape in (
            "authorization",
            "api_key",
            "apikey",
            "api_secret",
            "apisecret",
            "passphrase",
            "ok-access",
            "private_key",
            "signin",
            "nexuS_secret_".lower(),
        ):
            assert shape not in module, f"the live verification module mentions {shape!r}"
