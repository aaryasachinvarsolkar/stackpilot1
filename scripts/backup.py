"""STACKPILOT backup, verification and restore tool (standard library only).

    python scripts/backup.py create  --dest <backups-root> [--label YYYY-MM-DD]
    python scripts/backup.py verify  <backup-dir> [--strict-live]
    python scripts/backup.py restore <backup-dir> --target-db <file> [--move-existing]
                                     [--target-workspaces <empty-dir>]

* create  READS the project and writes only inside <backups-root>/<label>/ (which must be outside
          the repository and must not already exist). The backup is verified before it is reported.
* verify  checks the backup on its own (DB integrity, zip CRC, every file against the manifest).
          Differences from the live data are only informational unless --strict-live is given,
          so an old backup still verifies after the application has legitimately changed.
* restore never deletes anything. A pre-existing target DB is refused unless --move-existing, in
          which case it is renamed to <name>.replaced-<UTC timestamp>. Workspaces are extracted only
          into an empty (or new) directory that you name. Everything restored is re-verified.

Layout of <backups-root>/<label>/:
    stackpilot.db          consistent copy made with SQLite's online backup API
    workspaces.zip         every file and folder under backend/workspaces
    manifest.json          path, size and sha256 of every workspace file at backup time
    secrets/               copies of .env and .env.example (never commit these)
    backup-report.json     verification results and sha256 of each backup artifact
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Sources:
    db_path: Path = PROJECT_ROOT / "backend" / "stackpilot.db"
    workspaces: Path = PROJECT_ROOT / "backend" / "workspaces"
    env_files: tuple = (PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.example")
    project_root: Path = PROJECT_ROOT


DEFAULT = Sources()


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


def schema_fingerprint(conn: sqlite3.Connection) -> list[tuple]:
    """Normalised (type, name, sql) of every table/index, ignoring whitespace differences."""
    rows = conn.execute(
        "select type, name, sql from sqlite_master where name not like 'sqlite_%' order by type, name"
    ).fetchall()
    return [(t, n, re.sub(r"\s+", " ", s or "").strip()) for t, n, s in rows]


def workspace_manifest(workspaces: Path) -> list[dict]:
    entries = []
    if workspaces.exists():
        for p in sorted(workspaces.rglob("*")):
            if p.is_file():
                entries.append({"path": p.relative_to(workspaces).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)})
    return entries


def _safe_member_target(dest: Path, member: str) -> Path:
    name = member.replace("\\", "/")
    if not name or name.startswith("/") or ":" in name or ".." in name.split("/"):
        raise SystemExit(f"Refusing unsafe path inside backup archive: {member!r}")
    target = (dest / name).resolve()
    if dest.resolve() != target and dest.resolve() not in target.parents:
        raise SystemExit(f"Refusing path that escapes the destination: {member!r}")
    return target


def _extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for info in zf.infolist():
        target = _safe_member_target(dest, info.filename)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def create(dest_root: Path, label: str, src: Sources = DEFAULT) -> Path:
    dest = dest_root / label
    if dest.exists():
        raise SystemExit(f"Refusing to overwrite existing backup directory: {dest}")
    resolved = dest.resolve()
    if src.project_root.resolve() in resolved.parents or resolved == src.project_root.resolve():
        raise SystemExit("Backup destination must be OUTSIDE the project folder (so Git can never see it).")
    if not src.db_path.exists():
        raise SystemExit(f"Database not found: {src.db_path}")

    dest.mkdir(parents=True)
    (dest / "secrets").mkdir()

    reader = open_ro(src.db_path)
    writer = sqlite3.connect(dest / "stackpilot.db")
    try:
        reader.backup(writer)
    finally:
        writer.close()
        reader.close()

    manifest = workspace_manifest(src.workspaces)
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with zipfile.ZipFile(dest / "workspaces.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src.workspaces.rglob("*")) if src.workspaces.exists() else []:
            rel = p.relative_to(src.workspaces).as_posix()
            z.write(p, rel + ("/" if p.is_dir() else ""))

    for f in src.env_files:
        if f.exists():
            shutil.copy2(f, dest / "secrets" / f.name)

    report = verify(dest, src=src, strict_live=True)
    report["created_at"] = datetime.now(timezone.utc).isoformat()
    report["source_db"] = str(src.db_path)
    report["artifacts_sha256"] = {n: sha256(dest / n) for n in ("stackpilot.db", "workspaces.zip", "manifest.json")}
    (dest / "backup-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return dest


def verify(backup_dir: Path, src: Sources | None = None, strict_live: bool = False) -> dict:
    checks: dict[str, dict] = {}
    live: dict[str, dict] = {}

    def record(bucket: dict, name: str, passed: bool, detail: object = None) -> None:
        bucket[name] = {"pass": passed, "detail": detail}

    b = open_ro(backup_dir / "stackpilot.db")
    try:
        record(checks, "db_integrity_check", b.execute("pragma integrity_check").fetchone()[0] == "ok")
        record(checks, "db_foreign_keys_consistent", b.execute("pragma foreign_key_check").fetchall() == [])
        backup_counts = table_counts(b)
        backup_schema = schema_fingerprint(b)
        project_rows = b.execute("select name from projects order by created_at").fetchall() if "projects" in backup_counts else []
    finally:
        b.close()
    record(checks, "db_projects_readable", len(project_rows) == backup_counts.get("projects", 0), [r[0] for r in project_rows])

    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(backup_dir / "workspaces.zip") as z:
        bad = z.testzip()
        record(checks, "zip_crc_ok", bad is None, bad)
        _extract_zip(z, Path(tmp))
        mismatches = [
            e["path"]
            for e in manifest
            if not (Path(tmp) / e["path"]).is_file()
            or sha256(Path(tmp) / e["path"]) != e["sha256"]
            or (Path(tmp) / e["path"]).stat().st_size != e["size"]
        ]
        record(checks, "zip_matches_manifest", not mismatches, {"files": len(manifest), "mismatches": mismatches})
    record(checks, "secrets_folder_present", (backup_dir / "secrets").is_dir(), sorted(p.name for p in (backup_dir / "secrets").glob("*")))

    if src is not None:
        bucket = checks if strict_live else live
        if src.db_path.exists():
            s = open_ro(src.db_path)
            try:
                live_counts, live_schema = table_counts(s), schema_fingerprint(s)
            finally:
                s.close()
            record(bucket, "db_row_counts_match_live", backup_counts == live_counts, {"backup": backup_counts, "live": live_counts})
            record(bucket, "db_schema_matches_live", backup_schema == live_schema)
        stored = {e["path"]: e["sha256"] for e in manifest}
        now = {e["path"]: e["sha256"] for e in workspace_manifest(src.workspaces)}
        record(bucket, "workspaces_match_live", stored == now)
        if strict_live:
            record(checks, "env_files_copied", all(f.name in {p.name for p in (backup_dir / "secrets").glob("*")} for f in src.env_files if f.exists()))

    return {
        "all_checks_passed": all(c["pass"] for c in checks.values()),
        "checks": checks,
        "live_comparison_informational": live,
    }


def restore(
    backup_dir: Path,
    target_db: Path,
    target_workspaces: Path | None = None,
    move_existing: bool = False,
) -> dict:
    """Restore a verified backup. Never deletes: an existing target DB is only ever renamed."""
    report = verify(backup_dir)
    if not report["all_checks_passed"]:
        raise SystemExit("Backup failed verification; refusing to restore from it.")

    result: dict = {"moved_existing_to": None}
    if target_workspaces is not None and target_workspaces.exists() and any(target_workspaces.iterdir()):
        raise SystemExit(f"Refusing to extract into a non-empty directory: {target_workspaces}")

    if target_db.exists():
        if not move_existing:
            raise SystemExit(f"Target database already exists: {target_db} (use --move-existing to keep it renamed)")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        for suffix in ("", "-journal", "-wal", "-shm"):
            old = Path(str(target_db) + suffix)
            if old.exists():
                os.replace(old, Path(f"{old}.replaced-{stamp}"))
        result["moved_existing_to"] = f"{target_db}.replaced-{stamp}"

    target_db.parent.mkdir(parents=True, exist_ok=True)
    staging = target_db.with_name(target_db.name + f".restoring-{os.getpid()}")
    reader = open_ro(backup_dir / "stackpilot.db")
    writer = sqlite3.connect(staging)
    try:
        reader.backup(writer)
    finally:
        writer.close()
        reader.close()
    os.replace(staging, target_db)

    restored = open_ro(target_db)
    original = open_ro(backup_dir / "stackpilot.db")
    try:
        if restored.execute("pragma integrity_check").fetchone()[0] != "ok":
            raise SystemExit("Restored database failed integrity_check.")
        if table_counts(restored) != table_counts(original):
            raise SystemExit("Restored row counts differ from the backup.")
        if schema_fingerprint(restored) != schema_fingerprint(original):
            raise SystemExit("Restored schema differs from the backup.")
    finally:
        restored.close()
        original.close()
    result["db_restored_to"] = str(target_db)

    if target_workspaces is not None:
        with zipfile.ZipFile(backup_dir / "workspaces.zip") as z:
            _extract_zip(z, target_workspaces)
        manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
        bad = [e["path"] for e in manifest if not (target_workspaces / e["path"]).is_file() or sha256(target_workspaces / e["path"]) != e["sha256"]]
        if bad:
            raise SystemExit(f"Restored workspace files differ from the manifest: {bad}")
        result["workspaces_restored_to"] = str(target_workspaces)
        result["workspace_files"] = len(manifest)
    return result


def _print_checks(report: dict) -> None:
    for name, r in report["checks"].items():
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {name}")
    for name, r in report.get("live_comparison_informational", {}).items():
        print(f"  [info: {'same as live' if r['pass'] else 'differs from live (not a failure)'}] {name}")
    print("RESULT:", "ALL CHECKS PASSED" if report["all_checks_passed"] else "FAILED")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--dest", required=True, type=Path)
    c.add_argument("--label", default=date.today().isoformat())
    v = sub.add_parser("verify")
    v.add_argument("backup_dir", type=Path)
    v.add_argument("--strict-live", action="store_true", help="also fail if the live data differs from the backup")
    r = sub.add_parser("restore")
    r.add_argument("backup_dir", type=Path)
    r.add_argument("--target-db", required=True, type=Path)
    r.add_argument("--target-workspaces", type=Path)
    r.add_argument("--move-existing", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "create":
        dest = create(args.dest.resolve(), args.label)
        print(f"Backup written to: {dest}")
        report = json.loads((dest / "backup-report.json").read_text(encoding="utf-8"))
    elif args.cmd == "verify":
        report = verify(args.backup_dir.resolve(), src=DEFAULT, strict_live=args.strict_live)
    else:
        result = restore(args.backup_dir.resolve(), args.target_db.resolve(), args.target_workspaces and args.target_workspaces.resolve(), args.move_existing)
        print(json.dumps(result, indent=2))
        print("RESULT: RESTORE COMPLETED AND VERIFIED")
        return 0
    _print_checks(report)
    return 0 if report["all_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
