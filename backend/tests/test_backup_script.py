"""scripts/backup.py: create, verify, restore. Uses throwaway directories only."""
import importlib.util
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

from tests.test_migrations import make_legacy_db, snapshot

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backup.py"
spec = importlib.util.spec_from_file_location("stackpilot_backup", SCRIPT)
backup = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = backup  # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(backup)


@pytest.fixture
def world(tmp_path):
    """A fake project: db + workspaces + env files, with backups going outside of it."""
    proj = tmp_path / "proj"
    ws = proj / "backend" / "workspaces"
    (ws / "alpha" / "app").mkdir(parents=True)
    (ws / "alpha" / "app" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (ws / "alpha" / "README.md").write_text("# alpha ✓\n", encoding="utf-8")
    (ws / "empty-dir").mkdir()
    db = proj / "backend" / "stackpilot.db"
    make_legacy_db(db)
    (proj / ".env").write_text("A=1\n", encoding="utf-8")
    src = backup.Sources(db_path=db, workspaces=ws, env_files=(proj / ".env",), project_root=proj)
    return src, tmp_path / "backups"


def tree_hashes(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): backup.sha256(p) for p in sorted(root.rglob("*")) if p.is_file()}


def test_create_then_verify_passes_and_does_not_touch_the_sources(world):
    src, dest = world
    before = (backup.sha256(src.db_path), tree_hashes(src.workspaces))
    out = backup.create(dest, "t1", src)
    assert (backup.sha256(src.db_path), tree_hashes(src.workspaces)) == before
    assert {"stackpilot.db", "workspaces.zip", "manifest.json", "backup-report.json"} <= {p.name for p in out.iterdir()}
    assert backup.verify(out)["all_checks_passed"] is True
    assert json.loads((out / "backup-report.json").read_text(encoding="utf-8"))["all_checks_passed"] is True


def test_create_refuses_a_destination_inside_the_project_or_an_existing_backup(world):
    src, dest = world
    with pytest.raises(SystemExit):
        backup.create(src.project_root / "backups", "x", src)
    backup.create(dest, "t1", src)
    with pytest.raises(SystemExit):
        backup.create(dest, "t1", src)


def test_verify_detects_a_tampered_manifest(world):
    src, dest = world
    out = backup.create(dest, "t1", src)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest[0]["sha256"] = "0" * 64
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    report = backup.verify(out)
    assert report["all_checks_passed"] is False
    assert report["checks"]["zip_matches_manifest"]["pass"] is False


def test_verify_detects_altered_archive_content(world):
    src, dest = world
    out = backup.create(dest, "t1", src)
    with zipfile.ZipFile(out / "workspaces.zip") as z:
        members = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}
    members["alpha/README.md"] = b"tampered"
    with zipfile.ZipFile(out / "workspaces.zip", "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    assert backup.verify(out)["checks"]["zip_matches_manifest"]["pass"] is False


def test_live_differences_are_informational_unless_strict(world):
    src, dest = world
    out = backup.create(dest, "t1", src)
    (src.workspaces / "alpha" / "new.txt").write_text("later", encoding="utf-8")  # normal use after the backup
    relaxed = backup.verify(out, src=src)
    assert relaxed["all_checks_passed"] is True
    assert relaxed["live_comparison_informational"]["workspaces_match_live"]["pass"] is False
    assert backup.verify(out, src=src, strict_live=True)["all_checks_passed"] is False


def test_restore_reproduces_database_and_workspaces_exactly(world, tmp_path):
    src, dest = world
    out = backup.create(dest, "t1", src)
    target_db, target_ws = tmp_path / "restored" / "db.sqlite", tmp_path / "restored" / "ws"
    result = backup.restore(out, target_db, target_ws)

    assert snapshot(target_db) == snapshot(src.db_path)
    assert tree_hashes(target_ws) == tree_hashes(src.workspaces)
    assert (target_ws / "empty-dir").is_dir(), "empty folders are restored too"
    assert result["moved_existing_to"] is None


def test_restore_refuses_to_overwrite_an_existing_database(world, tmp_path):
    src, dest = world
    out = backup.create(dest, "t1", src)
    existing = tmp_path / "existing.db"
    make_legacy_db(existing, names=("other",))
    before = backup.sha256(existing)
    with pytest.raises(SystemExit):
        backup.restore(out, existing)
    assert backup.sha256(existing) == before


def test_restore_with_move_existing_keeps_the_old_database_renamed(world, tmp_path):
    src, dest = world
    out = backup.create(dest, "t1", src)
    existing = tmp_path / "existing.db"
    make_legacy_db(existing, names=("other",))
    old_hash = backup.sha256(existing)

    result = backup.restore(out, existing, move_existing=True)

    kept = Path(result["moved_existing_to"])
    assert kept.exists() and backup.sha256(kept) == old_hash, "the replaced database must be preserved"
    assert snapshot(existing) == snapshot(src.db_path)


def test_restore_refuses_a_non_empty_workspace_target_and_a_corrupt_backup(world, tmp_path):
    src, dest = world
    out = backup.create(dest, "t1", src)
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "keep.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(SystemExit):
        backup.restore(out, tmp_path / "a.db", busy)
    assert (busy / "keep.txt").read_text(encoding="utf-8") == "mine"

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest[0]["sha256"] = "f" * 64
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SystemExit):
        backup.restore(out, tmp_path / "b.db")
    assert not (tmp_path / "b.db").exists(), "nothing may be restored from a backup that fails verification"


def test_archive_members_that_escape_the_destination_are_refused(world, tmp_path):
    src, dest = world
    out = backup.create(dest, "t1", src)
    with zipfile.ZipFile(out / "workspaces.zip", "w") as z:
        z.writestr("../evil.txt", "x")
    (out / "manifest.json").write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit):
        backup.restore(out, tmp_path / "c.db", tmp_path / "ws-out")
    assert not (tmp_path / "evil.txt").exists()
