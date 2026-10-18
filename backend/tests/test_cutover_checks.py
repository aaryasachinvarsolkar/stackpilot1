"""scripts/phase3_cutover_checks.py, tested on throwaway databases only."""
import importlib.util
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest
from alembic import command

from tests.test_migrations import alembic_run, file_hash, make_legacy_db

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "phase3_cutover_checks.py"
spec = importlib.util.spec_from_file_location("stackpilot_cutover_checks", SCRIPT)
checks = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checks
spec.loader.exec_module(checks)


@pytest.fixture
def legacy(tmp_path):
    """(db, workspaces, snapshot_path): a pre-Alembic database plus a small workspaces folder."""
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    ws = tmp_path / "workspaces"
    (ws / "p" / "app").mkdir(parents=True)
    (ws / "p" / "app" / "main.py").write_text("print(1)\n", encoding="utf-8")
    (ws / "p" / "README.md").write_text("hi\n", encoding="utf-8")
    return db, ws, tmp_path / "out" / "snapshot.json"


async def migrate(db: Path) -> None:
    await alembic_run(command.stamp, db, "0001")
    await alembic_run(command.upgrade, db, "head")


def run(*argv) -> int:
    return checks.main([str(a) for a in argv])


# --- preflight ---------------------------------------------------------------------------

def test_preflight_passes_on_a_legacy_database(legacy, capsys):
    db, ws, _ = legacy
    assert run("preflight", db, "--workspaces", ws) == 0
    assert "ALL PASSED" in capsys.readouterr().out


def test_leftover_journal_files_stop_the_script_before_the_database_is_opened(legacy, capsys):
    db, ws, snap = legacy
    journal = Path(str(db) + "-journal")
    journal.write_bytes(b"not a real journal")
    db_before, journal_before = file_hash(db), file_hash(journal)

    assert run("preflight", db, "--workspaces", ws) == 1
    assert "database was NOT opened" in capsys.readouterr().out
    assert run("post", db, "--workspaces", ws, "--snapshot", snap) == 1  # stops before even reading the snapshot's db

    # opening the database could have triggered a rollback of the journal; neither file may change
    assert file_hash(db) == db_before and file_hash(journal) == journal_before


def test_preflight_fails_on_names_differing_only_by_case(tmp_path):
    db = tmp_path / "dups.db"
    make_legacy_db(db, names=("Foo", "foo", "bar"))
    ws = tmp_path / "ws"
    ws.mkdir()
    assert run("preflight", db, "--workspaces", ws) == 1


def test_preflight_fails_when_the_schema_is_not_the_baseline(legacy):
    db, ws, _ = legacy
    conn = sqlite3.connect(db)
    conn.execute("ALTER TABLE projects ADD COLUMN surprise TEXT")
    conn.commit()
    conn.close()
    assert run("preflight", db, "--workspaces", ws) == 1


async def test_preflight_refuses_an_already_migrated_database(legacy):
    db, ws, _ = legacy
    await migrate(db)
    assert run("preflight", db, "--workspaces", ws) == 1


# --- snapshot ----------------------------------------------------------------------------

def test_snapshot_records_rows_counts_and_workspace_digest(legacy):
    db, ws, snap = legacy
    assert run("snapshot", db, "--workspaces", ws, "--out", snap) == 0
    data = json.loads(snap.read_text(encoding="utf-8"))
    assert data["counts"] == {"projects": 3, "conversations": 1, "messages": 1, "project_files": 1}
    assert data["workspaces"]["files"] == 2
    assert len(data["row_digest"]) == 64


def test_snapshot_refuses_unsafe_output_locations(legacy, tmp_path):
    db, ws, snap = legacy
    repo = checks.REPO
    for bad in (db, ws / "snap.json", repo / "snapshot-leak.json"):
        with pytest.raises(SystemExit):
            run("snapshot", db, "--workspaces", ws, "--out", bad)
    assert not (repo / "snapshot-leak.json").exists()
    assert not (ws / "snap.json").exists()
    run("snapshot", db, "--workspaces", ws, "--out", snap)
    with pytest.raises(SystemExit):  # never overwrites
        run("snapshot", db, "--workspaces", ws, "--out", snap)


# --- post-migration verification ---------------------------------------------------------

async def test_post_passes_after_a_correct_migration(legacy, capsys):
    db, ws, snap = legacy
    run("snapshot", db, "--workspaces", ws, "--out", snap)
    await migrate(db)
    capsys.readouterr()
    assert run("post", db, "--workspaces", ws, "--snapshot", snap) == 0
    out = capsys.readouterr().out
    assert "ALL PASSED (16/16)" in out  # check 0 (journal files, before opening) + checks 1-15


async def test_post_fails_if_the_migration_was_not_applied(legacy):
    db, ws, snap = legacy
    run("snapshot", db, "--workspaces", ws, "--out", snap)
    await alembic_run(command.stamp, db, "0001")  # stamped but not upgraded
    assert run("post", db, "--workspaces", ws, "--snapshot", snap) == 1


async def test_post_detects_a_changed_value(legacy):
    db, ws, snap = legacy
    run("snapshot", db, "--workspaces", ws, "--out", snap)
    await migrate(db)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE projects SET description='tampered' WHERE id='pid-0'")
    conn.commit()
    conn.close()
    assert run("post", db, "--workspaces", ws, "--snapshot", snap) == 1


async def test_post_detects_a_lost_row(legacy):
    db, ws, snap = legacy
    run("snapshot", db, "--workspaces", ws, "--out", snap)
    await migrate(db)
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM project_files")
    conn.commit()
    conn.close()
    assert run("post", db, "--workspaces", ws, "--snapshot", snap) == 1


async def test_post_detects_a_changed_workspace_file(legacy):
    db, ws, snap = legacy
    run("snapshot", db, "--workspaces", ws, "--out", snap)
    await migrate(db)
    (ws / "p" / "README.md").write_text("changed\n", encoding="utf-8")
    assert run("post", db, "--workspaces", ws, "--snapshot", snap) == 1


async def test_post_detects_a_missing_index(legacy):
    db, ws, snap = legacy
    run("snapshot", db, "--workspaces", ws, "--out", snap)
    await migrate(db)
    conn = sqlite3.connect(db)
    conn.execute("DROP INDEX ix_messages_conversation_id")
    conn.commit()
    conn.close()
    assert run("post", db, "--workspaces", ws, "--snapshot", snap) == 1


async def test_post_detects_a_reclassified_origin(legacy):
    db, ws, snap = legacy
    run("snapshot", db, "--workspaces", ws, "--out", snap)
    await migrate(db)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE projects SET origin='seed' WHERE id='pid-0'")
    conn.commit()
    conn.close()
    assert run("post", db, "--workspaces", ws, "--snapshot", snap) == 1


# --- the script itself must be safe ------------------------------------------------------

async def test_the_script_never_modifies_the_database_or_the_workspaces(legacy):
    db, ws, snap = legacy
    ws_before = {p.relative_to(ws): file_hash(p) for p in ws.rglob("*") if p.is_file()}
    before = file_hash(db)
    run("preflight", db, "--workspaces", ws)
    run("snapshot", db, "--workspaces", ws, "--out", snap)
    assert file_hash(db) == before, "preflight/snapshot must not change the database"
    assert not [s for s in checks.SIDECARS if Path(str(db) + s).exists()], "no journal/WAL may be created"
    await migrate(db)
    migrated = file_hash(db)
    run("post", db, "--workspaces", ws, "--snapshot", snap)
    assert file_hash(db) == migrated, "post must not change the database"
    assert {p.relative_to(ws): file_hash(p) for p in ws.rglob("*") if p.is_file()} == ws_before


def test_the_database_is_opened_read_only(legacy):
    db, _, _ = legacy
    conn = checks.open_readonly(db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("UPDATE projects SET name='x'")
    finally:
        conn.close()


def test_script_source_has_no_destructive_operations_and_no_hardcoded_locations():
    source = SCRIPT.read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    forbidden = [
        r"rmtree", r"\.unlink\(", r"os\.remove", r"os\.rmdir", r"\.rmdir\(", r"os\.rename", r"os\.replace",
        r"shutil\.move", r"shutil\.copy", r"\bDROP\s", r"\bDELETE\s+FROM", r"\bINSERT\s", r"\bUPDATE\s+\w+\s+SET",
        r"\bALTER\s", r"\bVACUUM", r"subprocess", r"\.execute\(\s*['\"]PRAGMA\s+\w+\s*=",
    ]
    for pattern in forbidden:
        # the docstring/usage text mentions words like "write"; code only is scanned
        body = re.sub(r'""".*?"""', "", code, flags=re.S)
        assert not re.search(pattern, body, flags=re.I), f"script contains forbidden operation: {pattern}"
    for token in ("C:\\", "C:/", "/Users/", "stackpilot.db", "AppData", ".env"):
        assert token not in code, f"hardcoded location in script: {token!r}"
    assert "mode=ro" in code
