"""Alembic migrations actually apply and match the live ORM schema.

Without this, migrations/ can silently drift from app/models/store.py — a
model field added without a matching revision would work fine against
Base.metadata.create_all() (what Store() uses for :memory: and dev) while
quietly breaking `alembic upgrade head` against a real persistent database.
"""

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("alembic", reason="alembic is not installed")

ROOT = Path(__file__).resolve().parents[1]


def run_alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess:
    env = {"PME_DB_URL": f"sqlite:///{db_path}", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    import os

    env.update(os.environ)
    env["PME_DB_URL"] = f"sqlite:///{db_path}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_upgrade_head_applies_cleanly_to_a_fresh_database(tmp_path):
    db_path = tmp_path / "db" / "test.sqlite"
    db_path.parent.mkdir(parents=True)
    result = run_alembic("upgrade", "head", db_path=db_path)
    assert result.returncode == 0, result.stderr
    assert db_path.exists()


def test_migrated_schema_has_every_table_the_orm_defines(tmp_path):
    import sqlite3

    from app.models.store import Base

    db_path = tmp_path / "db" / "test.sqlite"
    db_path.parent.mkdir(parents=True)
    result = run_alembic("upgrade", "head", db_path=db_path)
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(db_path)
    tables = {
        r[0]
        for r in conn.execute(
            "select name from sqlite_master where type='table' "
            "and name not like 'sqlite_%' and name != 'alembic_version'"
        )
    }
    conn.close()
    assert tables == set(Base.metadata.tables.keys())


def test_current_reports_the_head_revision(tmp_path):
    db_path = tmp_path / "db" / "test.sqlite"
    db_path.parent.mkdir(parents=True)
    run_alembic("upgrade", "head", db_path=db_path)
    result = run_alembic("current", db_path=db_path)
    assert result.returncode == 0, result.stderr
    assert "0001" in result.stdout
