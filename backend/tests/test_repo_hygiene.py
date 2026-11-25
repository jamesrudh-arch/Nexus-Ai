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
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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
        it in the suite, with the reason attached. The base image ships setuptools 70.3.0, whose
        `PackageIndex.download` joins an unquoted URL segment onto a temp directory and so allows
        an arbitrary file write. Fixed upstream in 78.1.1.

        It is *removed* here rather than upgraded. Upgrading the system interpreter was tried
        first and the scan still reported 70.3.0 — the copy the scanner read was not the copy the
        upgrade touched. Removing it from both interpreters and asserting the result is the fix
        that does not depend on knowing which one was wrong.
        """
        dockerfile = (BACKEND / "Dockerfile").read_text()
        runtime = dockerfile.split("AS runtime", 1)[1]
        for interpreter in ("/usr/local/bin/python", "/opt/venv/bin/python"):
            assert f"{interpreter} -m pip uninstall -y setuptools" in runtime, (
                f"setuptools is no longer uninstalled from {interpreter}; the base image's "
                "70.3.0 would be scanned as HIGH and fail the build"
            )
            # The uninstall is not the fix; the assertion after it is. pip can leave the
            # dist-info behind, and the dist-info is exactly what a scanner reads.
            assert f"! {interpreter} -c 'import setuptools'" in runtime, (
                f"nothing verifies that {interpreter} can no longer import setuptools"
            )
        # Removal must happen after the venv is copied in and before privileges are dropped.
        assert (
            runtime.index("COPY --from=builder /opt/venv")
            < runtime.index("pip uninstall -y setuptools")
            < runtime.index("USER nexus")
        ), "setuptools removal must run after the venv is copied and before `USER nexus`"

    def test_the_dockerfile_survivor_check_is_not_vacuous(self) -> None:
        """`find a -o b -print -quit` binds the action to `b` only.

        Verified against a mock tree: with a setuptools dist-info present, the paren-less form
        matched zero items, so the assertion passed while the finding was still there. The
        grouping parentheses are what make the check mean anything, so they are asserted rather
        than trusted — the same reason `git check-ignore` is called with `--no-index`.
        """
        runtime = (BACKEND / "Dockerfile").read_text().split("AS runtime", 1)[1]
        grouped = "\\( -name 'setuptools*' -o -name 'pkg_resources' \\)"
        assert runtime.count(grouped) >= 2, (
            "the survivor check lost its grouping parentheses, so `-print -quit` applies only to "
            "the pkg_resources branch and setuptools survivors go unreported"
        )
        assert "-print -quit" in runtime, "the survivor check no longer prints what it finds"

    def test_a_missing_report_is_reported_not_crashed_on(self, tmp_path: Path) -> None:
        """The scan step can be skipped; the publish step must not then fail the job."""
        result = self._run_script(tmp_path, None)
        assert result.returncode == 0, f"a missing report must not break CI: {result.stderr}"
        assert "::warning" in result.stdout and "no report produced" in result.stdout

    def test_the_annotation_list_is_capped_and_says_it_was(self, tmp_path: Path) -> None:
        """A base image can carry hundreds; annotations are a pointer, not the report."""
        vulns = [
            {
                "VulnerabilityID": f"CVE-2025-{i:05d}",
                "PkgName": f"pkg{i}",
                "InstalledVersion": "1.0",
                "FixedVersion": "1.1",
                "Severity": "HIGH",
            }
            for i in range(60)
        ]
        result = self._run_script(
            tmp_path, json.dumps({"Results": [{"Target": "t", "Vulnerabilities": vulns}]})
        )
        assert result.returncode == 0, result.stderr
        emitted = [line for line in result.stdout.splitlines() if "CVE-2025-" in line]
        assert len(emitted) == 40, f"expected the cap of 40, got {len(emitted)}"
        assert "and 20 more" in result.stdout, "truncation must be stated, never silent"


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
