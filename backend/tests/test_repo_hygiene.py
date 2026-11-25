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

import shutil
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
SOURCE_ROOT = BACKEND / "src" / "nexus"

#: Resolved to an absolute path once. Running a bare "git" would depend on PATH contents,
#: which is both a security smell and a portability one.
GIT = shutil.which("git")


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
        import re

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
        import re

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
        import re

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
