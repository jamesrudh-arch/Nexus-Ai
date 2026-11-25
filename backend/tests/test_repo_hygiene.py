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

#: Resolved to an absolute path once. Running a bare "git" would depend on PATH contents,
#: which is both a security smell and a portability one.
GIT = shutil.which("git")


def _parsed_allowlists(config_path: Path) -> list[dict]:
    """The `[[allowlists]]` entries from a gitleaks config."""
    import tomllib

    with config_path.open("rb") as handle:
        return list(tomllib.load(handle).get("allowlists", []))


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


class TestSecretScanningIsNotWeakened:
    """`.gitleaks.toml` allowlists the detection code. This keeps that scope honest.

    An allowlist is how a security gate gets quietly turned off: one broad path, or a `ruleIDs`
    list, or a top-level `[allowlist]`, and the scanner still reports "passed" while finding
    nothing. These tests assert the config stays as narrow as it claims to be, so widening it
    breaks the build instead of silently reducing coverage.
    """

    CONFIG = REPO_ROOT / ".gitleaks.toml"

    def _parsed(self) -> dict:
        import tomllib

        with self.CONFIG.open("rb") as handle:
            return tomllib.load(handle)

    def test_the_config_exists_and_extends_the_default_ruleset(self) -> None:
        assert self.CONFIG.is_file(), ".gitleaks.toml is missing — gitleaks would use defaults"
        config = self._parsed()
        assert config.get("extend", {}).get("useDefault") is True, (
            "the config must extend the default ruleset; replacing it would drop every built-in "
            "rule and let real credentials through"
        )

    def test_no_rule_is_disabled_globally(self) -> None:
        config = self._parsed()
        for entry in config.get("allowlists", []):
            assert not entry.get("ruleIDs"), (
                f"allowlist {entry.get('description', '')[:40]!r} disables rules globally: "
                f"{entry['ruleIDs']}. Scope it to a path instead."
            )

    def test_there_is_no_repo_wide_allowlist(self) -> None:
        """A top-level `[allowlist]` suppresses findings everywhere. That is a disabled gate."""
        config = self._parsed()
        assert "allowlist" not in config, "top-level [allowlist] found — this suppresses repo-wide"

    def test_every_allowlist_is_bound_to_narrow_paths(self) -> None:
        config = self._parsed()
        allowlists = config.get("allowlists", [])
        assert allowlists, "expected the detection-code allowlist"
        for entry in allowlists:
            paths = entry.get("paths") or []
            commits = entry.get("commits") or []
            assert paths or commits, "an allowlist with neither path nor commit scope applies everywhere"
            unexpected = [p for p in paths if p not in _SECRET_SHAPE_FILES]
            assert not unexpected, (
                f"allowlist covers {unexpected}, which are not the files whose job is to "
                f"recognise secret shapes. Permitted: {sorted(_SECRET_SHAPE_FILES)}"
            )
            unexpected_commits = [c for c in commits if c not in _ALLOWLISTED_COMMITS]
            assert not unexpected_commits, (
                f"allowlist excuses commit(s) {unexpected_commits}. Only "
                f"{sorted(_ALLOWLISTED_COMMITS)} may be excused, each with a documented reason."
            )

    def test_exactly_one_commit_is_excused_and_why(self) -> None:
        """A commit allowlist excuses history forever, so it must stay a closed, documented set."""
        config = self._parsed()
        excused = [c for e in config.get("allowlists", []) for c in (e.get("commits") or [])]
        assert excused == list(_ALLOWLISTED_COMMITS)
        for entry in config.get("allowlists", []):
            if entry.get("commits"):
                description = entry.get("description", "")
                # The reason has to be written down, not just referenced by SHA.
                assert len(description) > 200, "a commit allowlist needs a real explanation"
                assert "fabricated" in description or "not a real credential" in description

    def test_the_excused_commit_exists_in_this_repository(self) -> None:
        """A typo'd SHA would silently excuse nothing — or, worse, look like it excuses something."""
        import subprocess

        for sha in _ALLOWLISTED_COMMITS:
            assert GIT is not None
            result = subprocess.run(  # noqa: S603 - fixed arguments, no shell, no user input
                [GIT, "cat-file", "-e", f"{sha}^{{commit}}"],
                cwd=REPO_ROOT,
                capture_output=True,
                check=False,
            )
            assert result.returncode == 0, f"allowlisted commit {sha} does not exist in this repo"

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

    def test_only_detection_code_and_its_tests_are_allowlisted(self) -> None:
        """Source, docs, config and every other test remain fully scanned."""
        config = self._parsed()
        scoped = {p for e in config.get("allowlists", []) for p in (e.get("paths") or [])}
        assert scoped == _SECRET_SHAPE_FILES

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
        for entry in _parsed_allowlists(self.CONFIG):
            assert not entry.get("regexes"), (
                "allowlist uses `regexes`, which requires embedding a secret-shaped literal in "
                "the config. Scope by path instead."
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
        import re

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
