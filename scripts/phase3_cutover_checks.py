"""Read-only safety checks for the Phase 3a database cutover (standard library + Alembic/ORM metadata).

    python scripts/phase3_cutover_checks.py preflight <db> --workspaces <dir>
    python scripts/phase3_cutover_checks.py snapshot  <db> --workspaces <dir> --out <snapshot.json>
    python scripts/phase3_cutover_checks.py post      <db> --workspaces <dir> --snapshot <snapshot.json>

preflight  Is this database a pre-Alembic ("legacy") database that is safe to stamp as revision 0001
           and upgrade? Checks the schema against the baseline fixture, case-insensitive duplicate
           names, integrity, and that no journal/WAL files are present.
snapshot   Records a fingerprint of every original column of every row, row counts and a digest of
           every workspace file, before the migration.
post       After the migration, verifies the database against that snapshot (16 checks).

Safety properties (each covered by tests/test_cutover_checks.py):
  * The database is only ever opened READ-ONLY (SQLite URI mode=ro); nothing is written to it.
  * No path is hardcoded: the database, workspaces and snapshot locations are explicit arguments.
  * Workspace files are only read. The snapshot file is the only thing written, it must not already
    exist, and it may not be placed inside the repository (it contains private project data), inside
    the workspaces folder, or on top of the database.
  * Exit status is 0 only if every check passed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
BASELINE_SQL = BACKEND / "tests" / "fixtures" / "pre_alembic_schema.sql"
EXPECTED_REVISION = "0002"
SIDECARS = ("-journal", "-wal", "-shm")

ORIGINAL_COLUMNS = {
    "projects": "id,name,description,root_path,is_indexed,languages,file_count,last_indexed_at,created_at,updated_at",
    "conversations": "id,project_id,title,created_at,updated_at",
    "messages": "id,conversation_id,sender,content,citations,plan_steps,created_at,updated_at",
    "project_files": "id,project_id,file_path,file_name,file_size_bytes,language,last_scanned_at,created_at,updated_at",
}
NEW_INDEXES = {
    "ux_projects_name_lower",
    "ux_project_files_project_path",
    "ix_conversations_project_id",
    "ix_messages_conversation_id",
}


# --- helpers -----------------------------------------------------------------------------

def open_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise SystemExit(f"Database file not found: {path}")
    return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def table_shape(conn: sqlite3.Connection) -> dict:
    shape = {}
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name <> 'alembic_version'"
    ):
        columns = [tuple(r[1:]) for r in conn.execute(f"PRAGMA table_info({name})")]
        fks = sorted(tuple(r[2:]) for r in conn.execute(f"PRAGMA foreign_key_list({name})"))
        shape[name] = (columns, fks)
    return shape


def baseline_shape() -> dict:
    """Shape of the pre-Alembic schema, built in memory from the checked-in fixture."""
    mem = sqlite3.connect(":memory:")
    try:
        mem.executescript(BASELINE_SQL.read_text(encoding="utf-8"))
        return table_shape(mem)
    finally:
        mem.close()


def row_fingerprint(conn: sqlite3.Connection) -> dict:
    rows = {
        table: [list(r) for r in conn.execute(f"SELECT {cols} FROM {table} ORDER BY id")]
        for table, cols in ORIGINAL_COLUMNS.items()
    }
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return {"rows": rows, "counts": {t: len(v) for t, v in rows.items()}, "row_digest": digest}


def workspace_digest(workspaces: Path) -> dict:
    if not workspaces.is_dir():
        raise SystemExit(f"Workspaces folder not found: {workspaces}")
    items = sorted(
        (p.relative_to(workspaces).as_posix(), sha256_file(p)) for p in workspaces.rglob("*") if p.is_file()
    )
    return {"files": len(items), "digest": hashlib.sha256(json.dumps(items).encode("utf-8")).hexdigest()}


def present_sidecars(db: Path) -> list[str]:
    return [s for s in SIDECARS if Path(str(db) + s).exists()]


class Checks:
    def __init__(self) -> None:
        self.results: list[bool] = []

    def check(self, label: str, passed: bool) -> None:
        self.results.append(bool(passed))
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")

    def finish(self, title: str) -> int:
        ok = all(self.results)
        print(f"{title}: {'ALL PASSED' if ok else 'FAILURES PRESENT'} ({sum(self.results)}/{len(self.results)})")
        return 0 if ok else 1


# --- preflight ---------------------------------------------------------------------------

def _stop_if_sidecars(db: Path, checks: Checks, title: str) -> bool:
    """A leftover journal/WAL means SQLite may try to roll it back the moment the file is opened,
    which a verification tool must never trigger, so nothing is opened until a person has looked."""
    leftovers = present_sidecars(db)
    checks.check("0  no -journal / -wal / -shm files next to the database (checked before opening it)", not leftovers)
    if leftovers:
        print(f"  STOP: found {leftovers}. The database was NOT opened. Inspect a copy of the database + these files.")
        return True
    return False


def safe_query(conn: sqlite3.Connection, sql: str):
    """Rows, or None when the query fails (for example a column that should exist but does not)."""
    try:
        return conn.execute(sql).fetchall()
    except sqlite3.DatabaseError:
        return None


def preflight(db: Path, workspaces: Path) -> int:
    checks = Checks()
    if _stop_if_sidecars(db, checks, "PREFLIGHT"):
        return checks.finish("PREFLIGHT")
    conn = open_readonly(db)
    try:
        checks.check("integrity_check is ok", conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
        checks.check("foreign_key_check is clean", conn.execute("PRAGMA foreign_key_check").fetchall() == [])
        has_version = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='alembic_version'").fetchone())
        checks.check("not yet under migration control (no alembic_version table)", not has_version)
        checks.check("schema equals the pre-Alembic baseline (safe to stamp as 0001)", table_shape(conn) == baseline_shape())
        try:
            dup_names = conn.execute(
                "SELECT lower(name) FROM projects GROUP BY lower(name) HAVING count(*) > 1"
            ).fetchall()
            dup_files = conn.execute(
                "SELECT 1 FROM project_files GROUP BY project_id, file_path HAVING count(*) > 1"
            ).fetchall()
        except sqlite3.DatabaseError:
            dup_names, dup_files = [("?",)], [("?",)]
        checks.check("no project names that differ only by case", not dup_names)
        checks.check("no duplicated (project_id, file_path) pairs", not dup_files)
        try:
            counts = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ORIGINAL_COLUMNS}
        except sqlite3.DatabaseError:
            counts = "unavailable (tables missing)"
    finally:
        conn.close()
    checks.check("workspaces folder is readable", workspaces.is_dir())
    print(f"  info: row counts {counts}")
    return checks.finish("PREFLIGHT")


# --- snapshot ----------------------------------------------------------------------------

def _refuse_unsafe_output(out: Path, db: Path, workspaces: Path) -> None:
    out_r = out.resolve()
    if out_r.exists():
        raise SystemExit(f"Refusing to overwrite an existing file: {out_r}")
    if out_r == db.resolve():
        raise SystemExit("Refusing to write the snapshot on top of the database.")
    ws_r = workspaces.resolve()
    if ws_r == out_r or ws_r in out_r.parents:
        raise SystemExit("Refusing to write the snapshot inside the workspaces folder (user data).")
    if REPO.resolve() in out_r.parents:
        raise SystemExit("Refusing to write the snapshot inside the repository (it contains private project data).")


def snapshot(db: Path, workspaces: Path, out: Path) -> int:
    _refuse_unsafe_output(out, db, workspaces)
    conn = open_readonly(db)
    try:
        snap = row_fingerprint(conn)
    finally:
        conn.close()
    snap["workspaces"] = workspace_digest(workspaces)
    snap["db_sha256"] = sha256_file(db)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap), encoding="utf-8")
    print(
        f"snapshot written: tables {snap['counts']}, workspace files {snap['workspaces']['files']}, "
        f"row digest {snap['row_digest'][:16]}..."
    )
    return 0


# --- post-migration verification ---------------------------------------------------------

def post(db: Path, workspaces: Path, snapshot_path: Path) -> int:
    sys.path.insert(0, str(BACKEND))
    warnings.simplefilter("ignore")
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    from app.models import Base  # registers the ORM tables; opens no database

    checks = Checks()
    if _stop_if_sidecars(db, checks, "POST-CHECKS"):
        return checks.finish("POST-CHECKS")
    before = json.loads(snapshot_path.read_text(encoding="utf-8"))
    conn = open_readonly(db)
    try:
        now = row_fingerprint(conn)
        version = safe_query(conn, "SELECT version_num FROM alembic_version")
        checks.check(f"1  alembic_version is {EXPECTED_REVISION}", bool(version) and version[0][0] == EXPECTED_REVISION)
        checks.check("2  every original value of every row identical to the snapshot", now["rows"] == before["rows"])
        checks.check(f"3  row counts identical {now['counts']}", now["counts"] == before["counts"])
        checks.check("4  integrity_check ok", conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
        checks.check("5  foreign_key_check clean", conn.execute("PRAGMA foreign_key_check").fetchall() == [])

        engine = create_engine(f"sqlite:///file:{db.resolve().as_posix()}?mode=ro&uri=true")
        try:
            with engine.connect() as sa_conn:
                diff = compare_metadata(MigrationContext.configure(sa_conn, opts={"compare_type": True}), Base.metadata)
        finally:
            engine.dispose()
        checks.check("6  migrated schema equals the ORM models (no drift)", diff == [])

        origins = safe_query(conn, "SELECT origin FROM projects ORDER BY id")
        checks.check(
            "7  every existing project is origin 'unclassified' (nothing guessed)",
            origins is not None and [r[0] for r in origins] == ["unclassified"] * before["counts"]["projects"],
        )
        set_projects = safe_query(conn, "SELECT count(*) FROM projects WHERE archived_at IS NOT NULL OR last_scanned_at IS NOT NULL")
        set_files = safe_query(conn, "SELECT count(*) FROM project_files WHERE file_hash IS NOT NULL")
        checks.check(
            "8  new nullable columns are all NULL",
            set_projects is not None and set_files is not None and set_projects[0][0] == 0 and set_files[0][0] == 0,
        )
        stored = ("description", "is_indexed", "languages", "file_count", "last_indexed_at")
        cols = ORIGINAL_COLUMNS["projects"].split(",")
        idx = [cols.index(c) for c in stored]
        checks.check(
            "9  stored descriptions / is_indexed / languages / file_count / last_indexed_at NOT altered",
            [[r[i] for i in idx] for r in now["rows"]["projects"]] == [[r[i] for i in idx] for r in before["rows"]["projects"]],
        )
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        checks.check("10 the 4 new indexes exist", NEW_INDEXES <= indexes)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        checks.check(
            f"11 no unexpected tables {sorted(tables)}",
            tables == set(ORIGINAL_COLUMNS) | {"alembic_version"},
        )
        root_idx = cols.index("root_path")
        checks.check(
            "12 project root_path values unchanged",
            [r[root_idx] for r in now["rows"]["projects"]] == [r[root_idx] for r in before["rows"]["projects"]],
        )
        checks.check("13 workspace files byte-identical (count + digest)", workspace_digest(workspaces) == before["workspaces"])
        checks.check(
            "14 original columns still present, in their original order",
            all(
                [r[1] for r in conn.execute(f"PRAGMA table_info({t})")][: len(c.split(','))] == c.split(",")
                for t, c in ORIGINAL_COLUMNS.items()
            ),
        )
        checks.check("15 still no -journal / -wal / -shm files after verification", not present_sidecars(db))
    finally:
        conn.close()
    return checks.finish("POST-CHECKS")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("preflight", "snapshot", "post"):
        p = sub.add_parser(name)
        p.add_argument("db", type=Path)
        p.add_argument("--workspaces", required=True, type=Path)
        if name == "snapshot":
            p.add_argument("--out", required=True, type=Path)
        if name == "post":
            p.add_argument("--snapshot", required=True, type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "preflight":
        return preflight(args.db, args.workspaces)
    if args.cmd == "snapshot":
        return snapshot(args.db, args.workspaces, args.out)
    return post(args.db, args.workspaces, args.snapshot)


if __name__ == "__main__":
    sys.exit(main())
