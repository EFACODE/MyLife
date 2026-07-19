"""Guards for the Alembic migration environment.

These are cheap, DB-free checks. The end-to-end drift check (`alembic upgrade
head && alembic check`) runs in CI.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _script_directory() -> ScriptDirectory:
    root = Path(__file__).resolve().parents[1]
    return ScriptDirectory.from_config(Config(str(root / "alembic.ini")))


def test_single_migration_head() -> None:
    # More than one head means divergent migration branches that must be merged.
    assert len(_script_directory().get_heads()) == 1


def test_baseline_revision_present() -> None:
    revisions = {script.revision for script in _script_directory().walk_revisions()}
    assert "0001" in revisions
