"""STACKPILOT backup & verification tool (standard library only).

Creates a verified backup of the development database, the workspaces folder and the
environment files. It only READS from the project; everything is written to --dest.

    python scripts/backup.py create --dest <backups-root> [--label YYYY-MM-DD]
    python scripts/backup.py verify <backup-dir>

Layout of <backups-root>/<label>/:
    stackpilot.db          consistent copy made with SQLite's online backup API
    workspaces.zip         every file under backend/workspaces
    manifest.json          path, size and sha256 of every workspace file at backup time
    secrets/               copies of .env and .env.example (never commit these)
    backup-report.json     verification results and sha256 of each backup artifact
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "backend" / "stackpilot.db"
WORKSPACES = PROJECT_ROOT / "backend" / "workspaces"
ENV_FILES = [PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.example"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def open_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    names = [r[0] for r in conn.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
    return {n: conn.execute(f'select count(*) from "{n}"').fetchone()[0] for n in names}


def workspace_manifest() -> list[dict]:
    entries = []
    if WORKSPACES.exists():
        for p in sorted(WORKSPACES.rglob("*")):
            if p.is_file():
                entries.append({"path": p.relative_to(WORKSPACES).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)})
    return entries


def create(dest_root: Path, label: str) -> Path:
    dest = dest_root / label
    if dest.exists():
        raise SystemExit(f"Refusing to overwrite existing backup directory: {dest}")
    if PROJECT_ROOT in dest.resolve().parents or dest.resolve() == PROJECT_ROOT:
        raise SystemExit("Backup destination must be OUTSIDE the project folder (so Git can never see it).")
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")

    dest.mkdir(parents=True)
    (dest / "secrets").mkdir()

    # 1. Database: online backup from a read-only connection.
    src = open_ro(DB_PATH)
    dst = sqlite3.connect(dest / "stackpilot.db")
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    # 2. Workspaces: manifest + zip.
    manifest = workspace_manifest()
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with zipfile.ZipFile(dest / "workspaces.zip", "w", zipfile.ZIP_DEFLATED) as z:
        # Directories are recorded too so empty folders survive a restore.
        for p in sorted(WORKSPACES.rglob("*")) if WORKSPACES.exists() else []:
            rel = p.relative_to(WORKSPACES).as_posix()
            z.write(p, rel + ("/" if p.is_dir() else ""))

    # 3. Env files.
    for f in ENV_FILES:
        if f.exists():
            shutil.copy2(f, dest / "secrets" / f.name)

    report = verify(dest)
    report["created_at"] = datetime.now(timezone.utc).isoformat()
    report["source_db"] = str(DB_PATH)
    report["artifacts_sha256"] = {
        name: sha256(dest / name) for name in ("stackpilot.db", "workspaces.zip", "manifest.json")
    }
    (dest / "backup-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return dest


def verify(backup_dir: Path) -> dict:
    checks: dict[str, object] = {}
    ok = True

    def record(name: str, passed: bool, detail: object = None) -> None:
        nonlocal ok
        checks[name] = {"pass": passed, "detail": detail}
        ok = ok and passed

    # Database
    bdb = backup_dir / "stackpilot.db"
    b = open_ro(bdb)
    try:
        record("db_integrity_check", b.execute("pragma integrity_check").fetchone()[0] == "ok")
        backup_counts = table_counts(b)
        projects = b.execute("select id, name, root_path from projects order by created_at").fetchall()
    finally:
        b.close()
    if DB_PATH.exists():
        s = open_ro(DB_PATH)
        try:
            live_counts = table_counts(s)
        finally:
            s.close()
        record("db_row_counts_match_live", backup_counts == live_counts, {"backup": backup_counts, "live": live_counts})
    record("db_projects_readable", len(projects) == backup_counts.get("projects"), [p[1] for p in projects])

    # Workspaces: extract zip to a temp dir and compare with the stored manifest.
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(backup_dir / "workspaces.zip") as z:
        bad_zip = z.testzip()
        record("zip_crc_ok", bad_zip is None, bad_zip)
        z.extractall(tmp)
        mismatches = []
        for e in manifest:
            p = Path(tmp) / e["path"]
            if not p.is_file() or sha256(p) != e["sha256"] or p.stat().st_size != e["size"]:
                mismatches.append(e["path"])
        record("zip_matches_manifest", not mismatches, {"files": len(manifest), "mismatches": mismatches})
    # Manifest vs the live workspace (informational: live data may legitimately change later).
    live = {e["path"]: e["sha256"] for e in workspace_manifest()}
    stored = {e["path"]: e["sha256"] for e in manifest}
    record("manifest_matches_live_workspaces", live == stored, None if live == stored else "live workspaces differ from backup")

    secrets = sorted(p.name for p in (backup_dir / "secrets").glob("*"))
    record("env_files_copied", all(f.name in secrets for f in ENV_FILES if f.exists()), secrets)

    return {"all_checks_passed": ok, "checks": checks}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--dest", required=True, type=Path)
    c.add_argument("--label", default=date.today().isoformat())
    v = sub.add_parser("verify")
    v.add_argument("backup_dir", type=Path)
    args = ap.parse_args()

    if args.cmd == "create":
        dest = create(args.dest.resolve(), args.label)
        report = json.loads((dest / "backup-report.json").read_text(encoding="utf-8"))
        print(f"Backup written to: {dest}")
    else:
        report = verify(args.backup_dir.resolve())
    for name, r in report["checks"].items():
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {name}")
    print("RESULT:", "ALL CHECKS PASSED" if report["all_checks_passed"] else "FAILED")
    sys.exit(0 if report["all_checks_passed"] else 1)


if __name__ == "__main__":
    main()
