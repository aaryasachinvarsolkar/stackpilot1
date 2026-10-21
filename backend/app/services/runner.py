"""Run a project's own backend so the whole project can be used in the browser.

This starts uploaded code on this computer, so it is deliberately fenced in:
  * `settings.ALLOW_RUNNING_PROJECT_CODE` (environment only, default false) must be on. Until then `start_run` refuses and
    nothing is installed or started. There is no API or UI switch for it.
  * commands are plain argument lists (never a shell string), run with the project folder as the working directory and the
    server bound to 127.0.0.1 on a free port chosen here;
  * the process gets a CLEAN environment (a short allow-list plus PORT/HOST). StackPilot's own settings, such as the LLM key
    and the JWT secret, are never passed on;
  * Python dependencies go into a virtual environment kept outside the project folder (settings.RUNTIME_ROOT), so the
    project's files are never polluted and the backend's own packages are never changed;
  * Python servers are started WITHOUT their own file watcher (`--reload`): on Windows uvicorn's reloader notices a change but never
    finishes restarting. After a saved or applied change the UI asks for a restart instead (`restart_run`), which behaves the same
    everywhere. Node dev servers (`npm run dev`) keep their own hot reload.
  * one run per project, at most MAX_RUNS at a time; everything is stopped (whole process tree) when asked or when the
    backend shuts down.
It is NOT a sandbox: the project's code runs with this user's permissions. That is why the switch exists and is off.

Where the commands come from (first match wins), see `detect_plan`:
  1. `stackpilot.json` in the project: {"install": [...], "start": [...], "python": true, "app_ports": [8000], "auto_reload": false}
  2. a Python web app: `uvicorn pkg.mod:app` in a start script / README, or an `app = FastAPI(...)` / `Flask(...)` / manage.py
  3. a Go module (go.mod + main.go): go run
  4. a Node project: package.json "dev" or "start" script
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

import asyncio

from app.config import settings

logger = logging.getLogger("stackpilot.runner")

MAX_RUNS = 2
LOG_LINES = 800
MAX_LINE_CHARS = 2000
INSTALL_TIMEOUT_SECONDS = 45 * 60
START_TIMEOUT_SECONDS = 240
SCAN_FILE_LIMIT = 400
SCAN_BYTES = 200_000
MAX_ARGS = 40
MAX_ARG_CHARS = 500
ACTIVE_STATES = ("preparing", "installing", "starting", "running")

# The only variables copied from StackPilot's own environment. Nothing else (keys, tokens, database URLs) is passed on.
_ENV_ALLOW = (
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE",
    "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
    "LANG", "LC_ALL", "TZ", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
)
_SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".idea", ".vscode", ".next", "dist", "build", "tests", "test", "notebooks"})
_SCRIPT_NAMES = re.compile(r"^(procfile|dockerfile|makefile|readme(\.md)?|.*\.(ps1|sh|bat|cmd))$", re.I)
_UVICORN = re.compile(r"uvicorn\s+(?:--?\S+(?:[ =]\S+)?\s+)*([A-Za-z_][\w.]*:[A-Za-z_]\w*)")
_PORT_FLAG = re.compile(r"--port[ =](\d{2,5})")
_FASTAPI_APP = re.compile(r"^(\w+)\s*(?::\s*\w+\s*)?=\s*FastAPI\s*\(", re.M)
_FLASK_APP = re.compile(r"^(\w+)\s*=\s*Flask\s*\(", re.M)


class RunError(Exception):
    """The caller can act on this. `code` is stable for the API; the message is safe to show."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --- the plan --------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class RunPlan:
    kind: str  # python | node | custom
    source: str  # where the commands came from, shown to the user
    install: Optional[Tuple[str, ...]]
    start: Tuple[str, ...]  # may contain {python} and {port}
    app_ports: Tuple[int, ...]  # the ports the project's own pages call (they are re-pointed at the proxy)
    auto_reload: bool  # the start command reloads by itself when files change
    needs_venv: bool
    env: Tuple[Tuple[str, str], ...] = ()
    fingerprint_files: Tuple[str, ...] = ()  # files whose content decides whether the install must run again
    fixed_port: Optional[int] = None  # the project insists on this port (it ignores PORT), so it is used instead of a free one
    warnings: Tuple[str, ...] = ()  # things that will probably stop it from running, found by reading its files

    def tools(self) -> Tuple[str, ...]:
        """Programs the commands need that are not Python itself (e.g. go, npm). Python runs from this backend's own interpreter."""
        names = []
        for command in (self.install, self.start):
            if command and not command[0].startswith("{"):
                name = re.sub(r"\.(cmd|exe|bat)$", "", command[0], flags=re.I)
                if name not in names:
                    names.append(name)
        return tuple(names)

    def describe(self) -> Dict[str, Any]:
        return {
            "kind": self.kind, "source": self.source,
            "install": " ".join(self.install) if self.install else None,
            "start": " ".join(self.start), "app_ports": list(self.app_ports), "auto_reload": self.auto_reload,
            "fixed_port": self.fixed_port, "requires": list(self.tools()), "warnings": list(self.warnings),
        }


_TOOL_HELP = {
    "go": "Install Go from https://go.dev/dl/ and restart the backend.",
    "npm": "Install Node.js (which includes npm) from https://nodejs.org/ and restart the backend.",
    "node": "Install Node.js from https://nodejs.org/ and restart the backend.",
    "yarn": "Install Yarn (https://yarnpkg.com/) and restart the backend.",
    "pnpm": "Install pnpm (https://pnpm.io/) and restart the backend.",
}


def missing_tools(plan: "RunPlan") -> List[str]:
    """Programs the plan needs that cannot be found on this computer."""
    return [name for name in plan.tools() if shutil.which(name) is None]


def tool_problem(missing: Sequence[str]) -> str:
    parts = [f"'{name}' is not installed (or not on PATH) on this computer. {_TOOL_HELP.get(name, 'Install it and restart the backend.')}" for name in missing]
    return "This project needs a program that is missing. " + " ".join(parts)


def _clean_argv(value: Any, what: str) -> Optional[Tuple[str, ...]]:
    if value is None:
        return None
    if not isinstance(value, list) or not value or len(value) > MAX_ARGS or not all(isinstance(a, str) and a and len(a) <= MAX_ARG_CHARS and "\x00" not in a for a in value):
        raise RunError("bad_plan", f"stackpilot.json: '{what}' must be a list of up to {MAX_ARGS} non-empty strings (one command, no shell).")
    return tuple(value)


def _read_text(path: Path, limit: int = SCAN_BYTES) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def _walk_files(root: Path, max_depth: int):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in _SKIP_DIRS and not d.startswith(".") and not os.path.islink(os.path.join(dirpath, d)))
        if depth >= max_depth:
            dirnames[:] = []
        for name in sorted(filenames):
            count += 1
            if count > SCAN_FILE_LIMIT:
                return
            yield Path(dirpath, name), ("" if rel == "." else rel.replace(os.sep, "/"))


def _module_path(rel_dir: str, file_name: str) -> str:
    parts = [p for p in rel_dir.split("/") if p] + [os.path.splitext(file_name)[0]]
    return ".".join(parts)


def _port_from(text: str, default: int) -> int:
    match = _PORT_FLAG.search(text)
    return int(match.group(1)) if match and 1 <= int(match.group(1)) <= 65535 else default


def _python_plan(root: Path) -> Optional[RunPlan]:
    has_requirements = (root / "requirements.txt").is_file()
    install = ("{python}", "-m", "pip", "install", "-r", "requirements.txt") if has_requirements else None
    fingerprint = ("requirements.txt",) if has_requirements else ()

    for path, _rel in _walk_files(root, 2):  # start scripts and README name the app
        if _SCRIPT_NAMES.match(path.name):
            text = _read_text(path)
            match = _UVICORN.search(text)
            if match:
                port = _port_from(text, 8000)
                return RunPlan(
                    "python", f"uvicorn {match.group(1)}, as named in {path.relative_to(root).as_posix()}", install,
                    ("{python}", "-m", "uvicorn", match.group(1), "--host", "127.0.0.1", "--port", "{port}"), (port,), False, True,
                    fingerprint_files=fingerprint,
                )
    if (root / "manage.py").is_file():
        return RunPlan("python", "Django project (manage.py)", install, ("{python}", "manage.py", "runserver", "--noreload", "127.0.0.1:{port}"), (8000,), False, True, fingerprint_files=fingerprint)
    for path, rel in _walk_files(root, 3):  # otherwise look for the app object itself
        if path.suffix != ".py":
            continue
        text = _read_text(path)
        found = _FASTAPI_APP.search(text)
        if found:
            target = f"{_module_path(rel, path.name)}:{found.group(1)}"
            return RunPlan(
                "python", f"FastAPI app {target} found in {path.relative_to(root).as_posix()}", install,
                ("{python}", "-m", "uvicorn", target, "--host", "127.0.0.1", "--port", "{port}"), (8000,), False, True, fingerprint_files=fingerprint,
            )
        found = _FLASK_APP.search(text)
        if found:
            target = f"{_module_path(rel, path.name)}:{found.group(1)}"
            return RunPlan(
                "python", f"Flask app {target} found in {path.relative_to(root).as_posix()}", install,
                ("{python}", "-m", "flask", "--app", target, "run", "--host", "127.0.0.1", "--port", "{port}"), (5000,), False, True, fingerprint_files=fingerprint,
            )
    return None


_GO_LISTEN = re.compile(r'ListenAndServe(?:TLS)?\(\s*"[^"]*:(\d{2,5})"')


def _go_plan(root: Path) -> Optional[RunPlan]:
    if not (root / "go.mod").is_file():
        return None
    target, main = ".", root / "main.go"
    if not main.is_file():
        candidates = sorted((root / "cmd").glob("*/main.go")) if (root / "cmd").is_dir() else []
        if not candidates:
            return None
        main, target = candidates[0], "./" + candidates[0].parent.relative_to(root).as_posix()
    text = _read_text(main)
    listens = _GO_LISTEN.search(text)
    literal = int(listens.group(1)) if listens and 1 <= int(listens.group(1)) <= 65535 else None
    fixed = literal if literal and 'Getenv("PORT")' not in text else None  # a program that reads PORT can be given any port
    return RunPlan(
        "go", f"go run {target}, from go.mod", None, ("go", "run", target), (literal or 8080,), False, False,
        env=(("PORT", "{port}"),), fixed_port=fixed,
    )


def _node_warnings(scripts: Dict[str, Any], name: str, deps: Dict[str, Any]) -> Tuple[str, ...]:
    command = str(scripts.get(name, "")).strip().split(" ")[0]
    if command in ("next", "vite", "react-scripts", "nuxt", "astro", "gatsby", "svelte-kit") and command not in deps:
        return (f"package.json runs '{command}' but does not list it as a dependency, so the install will not provide it. Add {command} (and what it needs, e.g. react and react-dom) to package.json.",)
    return ()


def _node_plan(root: Path) -> Optional[RunPlan]:
    package = root / "package.json"
    if not package.is_file():
        return None
    try:
        data = json.loads(_read_text(package, 500_000))
    except ValueError:
        return None
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return None
    name = "dev" if "dev" in scripts else "start" if "start" in scripts else None
    if name is None:
        return None
    deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
    extra: Tuple[str, ...] = ()
    if "vite" in deps:
        extra = ("--", "--host", "127.0.0.1", "--port", "{port}")
    elif "next" in deps:
        extra = ("--", "-H", "127.0.0.1", "-p", "{port}")
    npm = "npm.cmd" if os.name == "nt" else "npm"
    return RunPlan(
        "node", f"npm run {name}, from package.json", (npm, "install"), (npm, "run", name, *extra), (3000, 5173, 8080), name == "dev", False,
        env=(("PORT", "{port}"), ("HOST", "127.0.0.1"), ("BROWSER", "none")), fingerprint_files=("package.json", "package-lock.json"),
        warnings=_node_warnings(scripts, name, deps),
    )


def detect_plan(project_root: str) -> Optional[RunPlan]:
    """How to start this project, or None. Reads names and a few small files; executes nothing. May raise RunError(bad_plan)."""
    root = Path(project_root)
    if not root.is_dir():
        return None
    config = root / "stackpilot.json"
    if config.is_file():
        try:
            data = json.loads(_read_text(config, 100_000))
        except ValueError:
            raise RunError("bad_plan", "stackpilot.json is not valid JSON.") from None
        if not isinstance(data, dict):
            raise RunError("bad_plan", "stackpilot.json must contain a JSON object.")
        start = _clean_argv(data.get("start"), "start")
        if start is None:
            raise RunError("bad_plan", "stackpilot.json needs a 'start' command.")
        ports = data.get("app_ports", [])
        if not isinstance(ports, list) or not all(isinstance(p, int) and not isinstance(p, bool) and 1 <= p <= 65535 for p in ports):
            raise RunError("bad_plan", "stackpilot.json: 'app_ports' must be a list of port numbers.")
        fingerprint = data.get("fingerprint", [])
        files = tuple(f for f in fingerprint if isinstance(f, str) and f and ".." not in f and not f.startswith(("/", "\\"))) if isinstance(fingerprint, list) else ()
        fixed = data.get("fixed_port")
        if fixed is not None and (isinstance(fixed, bool) or not isinstance(fixed, int) or not 1 <= fixed <= 65535):
            raise RunError("bad_plan", "stackpilot.json: 'fixed_port' must be a port number.")
        return RunPlan(
            "custom", "stackpilot.json", _clean_argv(data.get("install"), "install"), start, tuple(ports), bool(data.get("auto_reload", False)),
            bool(data.get("python", False)), fingerprint_files=files, fixed_port=fixed,
        )
    return _python_plan(root) or _go_plan(root) or _node_plan(root)


# --- one run ---------------------------------------------------------------------------------------------------------
@dataclass
class ProjectRun:
    project_id: str
    root: str
    plan: RunPlan
    state: str = "preparing"  # preparing | installing | starting | running | stopped | failed
    message: str = ""
    port: Optional[int] = None
    started_at: Optional[str] = None
    log: Deque[str] = field(default_factory=lambda: deque(maxlen=LOG_LINES))
    proc: Optional[subprocess.Popen] = None
    task: Optional["asyncio.Task[None]"] = None
    stop_requested: bool = False

    def add_log(self, line: str) -> None:
        self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {line[:MAX_LINE_CHARS]}")


_RUNS: Dict[str, ProjectRun] = {}


def runtime_root() -> Path:
    base = settings.RUNTIME_ROOT.strip() if settings.RUNTIME_ROOT else ""
    return Path(base) if base else Path(__file__).resolve().parent.parent.parent / "runtime"


def get_run(project_id: str) -> Optional[ProjectRun]:
    return _RUNS.get(project_id)


def active_run(project_id: str) -> Optional[ProjectRun]:
    run = _RUNS.get(project_id)
    return run if run is not None and run.state == "running" and run.port else None


def consent_problem() -> Optional[str]:
    if settings.ALLOW_RUNNING_PROJECT_CODE is True:
        return None
    return (
        "Running a project's code is turned off (ALLOW_RUNNING_PROJECT_CODE is false), so nothing was installed or started. "
        "To allow it for projects you trust, set ALLOW_RUNNING_PROJECT_CODE=true in the backend's environment (.env) and restart the backend."
    )


def project_runtime_dir(project_id: str) -> Path:
    """Where this project's private environment lives. The name is kept SHORT on purpose: on Windows a path over 260 characters
    makes pip fail halfway (long dependency trees such as TensorFlow need the room), so the id is cut to 10 characters."""
    return runtime_root() / project_id[:10]


def _venv_dir(project_id: str) -> Path:
    return project_runtime_dir(project_id) / "v"


def _venv_python(project_id: str) -> Path:
    return _venv_dir(project_id) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


_LONG_PATH_HINT = (
    " On Windows this often means the folder path is too long (260-character limit): set RUNTIME_ROOT in the backend's .env to a short "
    "folder such as C:\\sp, or turn on Windows long paths, then restart the backend."
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def _clean_env(run: ProjectRun, port: Optional[int]) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOW}
    env.update({"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "NO_COLOR": "1", "CI": "1"})
    if run.plan.needs_venv:
        scripts = _venv_python(run.project_id).parent
        env["PATH"] = str(scripts) + os.pathsep + env.get("PATH", "")
        env["VIRTUAL_ENV"] = str(scripts.parent)
    for key, value in run.plan.env:
        env[key] = value.replace("{port}", str(port)) if port else value
    if port:
        env.setdefault("PORT", str(port))
    return env


def _argv(run: ProjectRun, template: Sequence[str], port: Optional[int]) -> List[str]:
    python = str(_venv_python(run.project_id)) if run.plan.needs_venv else sys.executable
    return [a.replace("{python}", python).replace("{port}", str(port or "")) for a in template]


def _pump(stream, run: ProjectRun) -> None:
    """Copy a process's output into the run's log (runs in a thread)."""
    try:
        for raw in iter(stream.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                run.add_log(line)
    except (OSError, ValueError):
        pass


def _spawn(run: ProjectRun, argv: List[str], port: Optional[int]) -> subprocess.Popen:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.Popen(
        argv, cwd=run.root, env=_clean_env(run, port), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=flags, start_new_session=(os.name != "nt"), shell=False,
    )
    threading.Thread(target=_pump, args=(proc.stdout, run), daemon=True).start()
    return proc


def _pidfile(project_id: str) -> Path:
    return project_runtime_dir(project_id) / "run.json"


def _remember_process(run: ProjectRun, argv: List[str], proc: subprocess.Popen) -> None:
    """Write down which process was started, so that if this backend is killed without a clean shutdown (or restarted by its own
    auto-reload), the next start can find the project's server and stop it instead of leaving it running unseen."""
    try:
        _pidfile(run.project_id).parent.mkdir(parents=True, exist_ok=True)
        _pidfile(run.project_id).write_text(json.dumps({"pid": proc.pid, "argv": argv}), encoding="utf-8")
    except OSError:
        logger.warning("could not record the started process for %s", run.project_id)


def _forget_process(project_id: str) -> None:
    try:
        _pidfile(project_id).unlink(missing_ok=True)
    except OSError:
        pass


def _command_line_of(pid: int) -> Optional[str]:
    """The command line of a running process, or None if there is no such process."""
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"],
                capture_output=True, text=True, timeout=20,
            )
            text = out.stdout.strip()
            return text or None
        return Path(f"/proc/{int(pid)}/cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace").strip() or None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def reap_orphans() -> List[str]:
    """Stop project servers left behind by an earlier run of this backend. Returns the ids that were cleaned up.

    A process is only stopped if its CURRENT command line still contains every part of the command that was recorded when it
    was started, so a different program that happens to have reused the process id is never touched."""
    reaped: List[str] = []
    root = runtime_root()
    if not root.is_dir():
        return reaped
    for entry in root.iterdir():
        record = entry / "run.json"
        if not record.is_file():
            continue
        try:
            data = json.loads(record.read_text(encoding="utf-8"))
            pid, argv = int(data["pid"]), [str(a) for a in data["argv"]]
        except (OSError, ValueError, KeyError, TypeError):
            record.unlink(missing_ok=True)
            continue
        current = _command_line_of(pid)
        normal = (current or "").replace('"', "").replace("\\", "/").lower()
        if current and all(part.replace("\\", "/").lower() in normal for part in argv if part):
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15)
                else:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                reaped.append(entry.name)
                logger.warning("stopped a project server left running by an earlier backend (pid %s)", pid)
            except (OSError, subprocess.SubprocessError):
                logger.exception("could not stop leftover pid %s", pid)
        record.unlink(missing_ok=True)
    return reaped


def kill_tree(proc: Optional[subprocess.Popen]) -> None:
    """Stop a process and everything it started."""
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=15)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass


def _install_marker(run: ProjectRun) -> Path:
    return project_runtime_dir(run.project_id) / "install.sha256"


def _install_fingerprint(run: ProjectRun) -> str:
    digest = hashlib.sha256(" ".join(run.plan.install or ()).encode())
    for name in run.plan.fingerprint_files:
        try:
            digest.update(Path(run.root, name).read_bytes())
        except OSError:
            digest.update(b"-")
    return digest.hexdigest()


async def _wait_for_exit(run: ProjectRun, proc: subprocess.Popen, timeout: float) -> Optional[int]:
    deadline = time.monotonic() + timeout
    while proc.poll() is None:
        if run.stop_requested or time.monotonic() > deadline:
            return None
        await asyncio.sleep(0.4)
    return proc.returncode


async def _drive(run: ProjectRun) -> None:
    try:
        plan = run.plan
        if plan.needs_venv and not _venv_python(run.project_id).is_file():
            run.state, run.message = "preparing", "Creating a private Python environment..."
            run.add_log(run.message)
            venv_dir = _venv_dir(run.project_id)
            run.add_log(f"Environment folder: {venv_dir} ({len(str(venv_dir))} characters)")
            venv_dir.parent.mkdir(parents=True, exist_ok=True)
            proc = _spawn(run, [sys.executable, "-m", "venv", str(venv_dir)], None)
            code = await _wait_for_exit(run, proc, 300)
            if run.stop_requested:
                kill_tree(proc)
                return
            if code != 0:
                raise RunError("venv_failed", "A private Python environment could not be created." + (_LONG_PATH_HINT if os.name == "nt" else ""))

        if plan.install:
            marker, fingerprint = _install_marker(run), _install_fingerprint(run)
            if marker.is_file() and _read_text(marker, 100).strip() == fingerprint:
                run.add_log("Dependencies are already installed; skipping the install step.")
            else:
                run.state, run.message = "installing", "Installing the project's dependencies (the first time can take several minutes)..."
                run.add_log("$ " + " ".join(_argv(run, plan.install, None)))
                proc = _spawn(run, _argv(run, plan.install, None), None)
                run.proc = proc
                code = await _wait_for_exit(run, proc, INSTALL_TIMEOUT_SECONDS)
                if run.stop_requested:
                    kill_tree(proc)
                    return
                if code is None:
                    kill_tree(proc)
                    raise RunError("install_timeout", "Installing the dependencies took too long and was stopped.")
                if code != 0:
                    raise RunError("install_failed", f"Installing the dependencies failed (exit code {code}). See the log below.")
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(fingerprint, encoding="utf-8")

        run.state, run.message = "starting", "Starting the project..."
        if plan.fixed_port:
            if await asyncio.to_thread(_port_open, plan.fixed_port):
                raise RunError("port_in_use", f"This project always listens on port {plan.fixed_port}, and another program is already using it. Stop that program and try again.")
            run.port = plan.fixed_port
        else:
            run.port = _free_port()
        argv = _argv(run, plan.start, run.port)
        run.add_log("$ " + " ".join(argv))
        run.proc = _spawn(run, argv, run.port)
        _remember_process(run, argv, run.proc)
        deadline = time.monotonic() + START_TIMEOUT_SECONDS
        while True:
            if run.stop_requested:
                return
            if run.proc.poll() is not None:
                raise RunError("exited", f"The project stopped right after starting (exit code {run.proc.returncode}). See the log below.")
            if await asyncio.to_thread(_port_open, run.port):
                break
            if time.monotonic() > deadline:
                kill_tree(run.proc)
                raise RunError("start_timeout", f"The project did not start listening within {START_TIMEOUT_SECONDS} seconds. See the log below.")
            await asyncio.sleep(0.5)

        run.state, run.message = "running", f"Running on port {run.port}."
        run.started_at = datetime.now(timezone.utc).isoformat()
        run.add_log(run.message)
        while run.proc.poll() is None and not run.stop_requested:
            await asyncio.sleep(1.0)
        if not run.stop_requested:
            run.state, run.message = "failed", f"The project stopped on its own (exit code {run.proc.returncode})."
    except asyncio.CancelledError:
        kill_tree(run.proc)
        raise
    except RunError as err:
        run.state, run.message = "failed", err.message
        run.add_log(err.message)
        kill_tree(run.proc)
    except Exception as exc:  # never lets a bug leave a run half-started
        logger.exception("run failed")
        run.state, run.message = "failed", f"Could not start the project ({type(exc).__name__})."
        kill_tree(run.proc)
    finally:
        if run.proc is None or run.proc.poll() is not None or run.stop_requested:
            _forget_process(run.project_id)
        if run.stop_requested:
            run.state, run.message = "stopped", "Stopped."


def start_run(project_id: str, project_root: str) -> ProjectRun:
    """Begin installing and starting the project in the background. Refuses unless the owner allowed running project code."""
    problem = consent_problem()
    if problem:
        raise RunError("not_allowed", problem)
    existing = _RUNS.get(project_id)
    if existing is not None and existing.state in ACTIVE_STATES:
        return existing
    if sum(1 for r in _RUNS.values() if r.state in ACTIVE_STATES) >= MAX_RUNS:
        raise RunError("too_many_runs", f"At most {MAX_RUNS} projects can run at the same time. Stop one first.")
    plan = detect_plan(project_root)
    if plan is None:
        raise RunError(
            "no_plan",
            "No way to start this project was found. Add a stackpilot.json to the project, for example "
            '{"install": ["{python}", "-m", "pip", "install", "-r", "requirements.txt"], "start": ["{python}", "-m", "uvicorn", "app:app", "--port", "{port}"], "python": true, "app_ports": [8000]}',
        )
    missing = missing_tools(plan)
    if missing:
        raise RunError("tool_missing", tool_problem(missing))
    run = ProjectRun(project_id=project_id, root=project_root, plan=plan)
    run.add_log(f"Plan: {plan.source}")
    _RUNS[project_id] = run
    run.task = asyncio.create_task(_drive(run))
    return run


async def stop_run(project_id: str) -> Optional[ProjectRun]:
    run = _RUNS.get(project_id)
    if run is None:
        return None
    run.stop_requested = True
    if run.task is not None and not run.task.done():
        run.task.cancel()
        try:
            await run.task
        except (asyncio.CancelledError, Exception):
            pass
    await asyncio.to_thread(kill_tree, run.proc)
    _forget_process(project_id)
    run.state, run.message = "stopped", "Stopped."
    run.add_log("Stopped.")
    return run


async def restart_run(project_id: str, project_root: str) -> ProjectRun:
    await stop_run(project_id)
    _RUNS.pop(project_id, None)
    return start_run(project_id, project_root)


async def stop_all() -> None:
    for project_id in list(_RUNS):
        try:
            await stop_run(project_id)
        except Exception:
            logger.exception("could not stop %s", project_id)


def status(project_id: str, project_root: str, tail: int = 250) -> Dict[str, Any]:
    run = _RUNS.get(project_id)
    plan_info, plan_problem = None, None
    plan = run.plan if run is not None else None
    if plan is None:
        try:
            plan = detect_plan(project_root)
        except RunError as err:
            plan_problem = err.message
    if plan is not None:
        plan_info = plan.describe()
    return {
        "allowed": settings.ALLOW_RUNNING_PROJECT_CODE is True,
        "blocked_reason": consent_problem(),
        "state": run.state if run is not None else "idle",
        "message": run.message if run is not None else "",
        "plan": plan_info,
        "plan_problem": plan_problem,
        "missing_tools": missing_tools(plan) if plan is not None else [],
        "missing_tools_help": tool_problem(missing_tools(plan)) if plan is not None and missing_tools(plan) else None,
        "port": run.port if run is not None and run.state == "running" else None,
        "started_at": run.started_at if run is not None else None,
        "log": list(run.log)[-tail:] if run is not None else [],
    }


# --- pointing the project's own pages at the running backend ---------------------------------------------------------
def rewrite_origins(text: str, ports: Sequence[int], proxy_origin: str, project_id: str) -> Tuple[str, int]:
    """Re-point `http://localhost:<port>` (and ws://) in a served page at the proxy for this project. Only the served copy changes."""
    if not ports:
        return text, 0
    pattern = re.compile(r"\b(https?|wss?)://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]):(?:%s)(?![0-9])" % "|".join(str(p) for p in ports))
    base = proxy_origin.split("://", 1)[-1]
    count = 0

    def swap(match: "re.Match[str]") -> str:
        nonlocal count
        count += 1
        scheme = "ws" if match.group(1).startswith("ws") else "http"
        return f"{scheme}://{base}/api/projects/{project_id}/app"

    return pattern.sub(swap, text), count
