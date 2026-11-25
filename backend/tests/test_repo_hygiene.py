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
