"""Unit tests for the trusted path/name helpers (Phase 2, fixes F1 and F2)."""
import os
import subprocess

import pytest

from app.services.workspace import (
    UnsafePathError,
    count_workspace_files,
    project_dir_for,
    resolve_in_project,
    validate_project_name,
    workspaces_root,
)


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "proj"
    (r / "app" / "api").mkdir(parents=True)
    (r / "app" / "main.py").write_text("x", encoding="utf-8")
    return r


# --- resolve_in_project ------------------------------------------------------------------

@pytest.mark.parametrize("rel", ["app/main.py", "app\\main.py", "./app/main.py", "app//main.py", "app/./main.py"])
def test_valid_relative_paths_resolve_inside_root(root, rel):
    assert resolve_in_project(root, rel) == (root / "app" / "main.py").resolve()


def test_new_file_in_new_subfolder_is_allowed(root):
    assert resolve_in_project(root, "notes/new/file.txt") == (root / "notes" / "new" / "file.txt").resolve()


@pytest.mark.parametrize(
    "rel",
    [
        "",
        ".",
        "./",
        "..",
        "../x",
        "..\\x",
        "a/../../x",
        "a/..",
        "app/../../etc/passwd",
        "/etc/passwd",
        "\\Windows\\win.ini",
        "C:\\Windows\\win.ini",
        "C:/Windows/win.ini",
        "C:win.ini",
        "\\\\server\\share\\f",
        "//server/share/f",
        "app/main.py:stream",
        "bad\x00name",
        "a" * 2000,
    ],
)
def test_unsafe_paths_are_rejected(root, rel):
    with pytest.raises(UnsafePathError):
        resolve_in_project(root, rel)


def test_absolute_path_of_a_real_outside_file_is_rejected(root, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(UnsafePathError):
        resolve_in_project(root, str(outside))


def test_symlink_pointing_outside_is_rejected(root, tmp_path):
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    link = root / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        # Unprivileged Windows: a directory junction escapes the same way and needs no privilege.
        made = (
            os.name == "nt"
            and subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True).returncode == 0
        )
        if not made:
            pytest.skip("neither symlinks nor junctions can be created in this environment")
    with pytest.raises(UnsafePathError):
        resolve_in_project(root, "link/secret.txt")


# --- project names -----------------------------------------------------------------------

@pytest.mark.parametrize("name", ["a", "task-manager-service", "e-commerce-api", "phase3-test", "My_App.v2", "x" * 100])
def test_valid_project_names(name):
    assert validate_project_name(name) == name


@pytest.mark.parametrize(
    "name",
    ["", " ", "../x", "a/b", "a\\b", ".hidden", "-x", "has space", "a:b", "name.", "con", "NUL", "com1", "LPT9.txt", "x" * 101, "ünï"],
)
def test_invalid_project_names(name):
    with pytest.raises(ValueError):
        validate_project_name(name)


def test_project_dir_is_a_direct_child_of_the_workspaces_root():
    d = project_dir_for("some-project")
    assert d.parent == workspaces_root()


def test_project_dir_rejects_traversal_names():
    with pytest.raises(UnsafePathError):
        project_dir_for("../escape")


# --- counting ----------------------------------------------------------------------------

def test_count_workspace_files_counts_real_files_and_skips_ignored(root):
    (root / "node_modules").mkdir()
    (root / "node_modules" / "junk.js").write_text("x", encoding="utf-8")
    (root / ".env").write_text("SECRET=1", encoding="utf-8")
    assert count_workspace_files(root) == 1  # only app/main.py


def test_count_workspace_files_is_none_for_missing_folder(tmp_path):
    assert count_workspace_files(tmp_path / "does-not-exist") is None
