"""Run the whole project: consent, a clean environment, the forwarder, address rewriting, stopping, and plan detection.

These start REAL processes (a tiny standard-library server standing in for an uploaded project), always inside the test
sandbox, always stopped again by the fixture.
"""
import asyncio
import json
import os
import re
import shutil
import socket
import time
from pathlib import Path

import pytest

from app.config import settings
from app.services import runner

SERVER = '''
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

class H(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "http://project-own-cors.example")
        self.send_header("Set-Cookie", "session=abc")
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        if self.path.startswith("/env"):
            return self._send(sorted(os.environ))
        self._send({"path": self.path, "origin": self.headers.get("Origin"), "cookie": self.headers.get("Cookie"), "x-custom": self.headers.get("X-Custom")})
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self._send({"echo": self.rfile.read(n).decode(), "type": self.headers.get("Content-Type")}, 201)
    def log_message(self, *a):
        print("request", self.path, flush=True)

print("project booting", flush=True)
HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
'''
CONFIG = {"start": ["{python}", "server.py", "{port}"], "app_ports": [8000]}


@pytest.fixture
def root(project) -> Path:
    path = Path(project["root_path"])
    for child in list(path.iterdir()):
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    return path


@pytest.fixture
def allowed(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_RUNNING_PROJECT_CODE", True)


@pytest.fixture(autouse=True)
async def cleanup():
    yield
    await runner.stop_all()
    runner._RUNS.clear()


def write_project(root: Path, config=CONFIG, server=SERVER):
    (root / "server.py").write_text(server)
    (root / "stackpilot.json").write_text(json.dumps(config))


def url(project, tail):
    return f"/api/projects/{project['id']}/{tail}"


async def wait_for(client, project, states, timeout=25.0):
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        last = (await client.get(url(project, "run"))).json()
        if last["state"] in states:
            return last
        await asyncio.sleep(0.2)
    raise AssertionError(f"never reached {states}; last status: {last['state']} {last.get('message')} {last['log'][-6:]}")


async def start_and_wait(client, project):
    res = await client.post(url(project, "run/start"))
    assert res.status_code == 202, res.text
    return await wait_for(client, project, ("running", "failed"))


# --- consent ---------------------------------------------------------------------------------------------------------
async def test_nothing_starts_without_the_owners_switch(async_client, project, root):
    write_project(root)
    assert settings.ALLOW_RUNNING_PROJECT_CODE is False
    res = await async_client.post(url(project, "run/start"))
    assert res.status_code == 403 and res.json()["detail"]["code"] == "not_allowed"
    assert "ALLOW_RUNNING_PROJECT_CODE=true" in res.json()["detail"]["message"]
    status = (await async_client.get(url(project, "run"))).json()
    assert status["allowed"] is False and status["state"] == "idle" and status["blocked_reason"]
    assert runner._RUNS == {}, "no run was even created"


async def test_the_switch_cannot_be_turned_on_through_the_api():
    from app.main import app

    paths = list(app.openapi()["paths"])
    assert not any("allow" in p.lower() and "run" in p.lower() for p in paths)
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert "ALLOW_RUNNING_PROJECT_CODE = " not in source.replace("settings.ALLOW_RUNNING_PROJECT_CODE is True", "")


# --- plans -----------------------------------------------------------------------------------------------------------
async def test_a_project_with_no_way_to_start_says_how_to_add_one(async_client, project, root, allowed):
    (root / "notes.txt").write_text("hi")
    res = await async_client.post(url(project, "run/start"))
    assert res.status_code == 422 and res.json()["detail"]["code"] == "no_plan" and "stackpilot.json" in res.json()["detail"]["message"]


async def test_a_broken_stackpilot_json_is_reported_not_run(async_client, project, root, allowed):
    (root / "stackpilot.json").write_text(json.dumps({"start": "python server.py"}))  # a string, not a list: no shell strings
    assert "list" in (await async_client.get(url(project, "run"))).json()["plan_problem"]
    res = await async_client.post(url(project, "run/start"))
    assert res.status_code == 422 and res.json()["detail"]["code"] == "bad_plan"


def test_plans_are_detected_from_the_projects_own_files(tmp_path):
    (tmp_path / "start_backend.ps1").write_text("uvicorn backend.app:app --host 0.0.0.0 --port 8123 --reload\n")
    (tmp_path / "requirements.txt").write_text("fastapi\n")
    plan = runner.detect_plan(str(tmp_path))
    assert plan.kind == "python" and plan.app_ports == (8123,) and plan.needs_venv and not plan.auto_reload
    assert "--reload" not in plan.start, "uvicorn's reloader never finishes restarting on Windows; StackPilot restarts the project instead"
    assert plan.start[:4] == ("{python}", "-m", "uvicorn", "backend.app:app") and "127.0.0.1" in plan.start and "0.0.0.0" not in plan.start
    assert plan.install == ("{python}", "-m", "pip", "install", "-r", "requirements.txt")


def test_a_fastapi_or_flask_app_object_is_found_by_reading_the_code(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    plan = runner.detect_plan(str(tmp_path))
    assert "api.main:app" in plan.start and plan.app_ports == (8000,)
    flask = tmp_path.parent / (tmp_path.name + "-flask")
    flask.mkdir()
    (flask / "web.py").write_text("from flask import Flask\nserver = Flask(__name__)\n")
    plan = runner.detect_plan(str(flask))
    assert "web:server" in plan.start and "flask" in plan.start and plan.app_ports == (5000,)


def test_a_node_project_uses_its_dev_script(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"dev": "vite", "start": "node x.js"}, "devDependencies": {"vite": "5"}}))
    plan = runner.detect_plan(str(tmp_path))
    assert plan.kind == "node" and plan.start[1:3] == ("run", "dev") and "--port" in plan.start and "{port}" in plan.start
    assert plan.install[-1] == "install" and ("HOST", "127.0.0.1") in plan.env


def test_nothing_is_detected_in_a_project_with_nothing_to_run(tmp_path):
    (tmp_path / "index.html").write_text("<h1>x</h1>")
    assert runner.detect_plan(str(tmp_path)) is None


# --- running ---------------------------------------------------------------------------------------------------------
async def test_the_project_starts_and_the_page_can_reach_it_through_the_forwarder(async_client, project, root, allowed):
    write_project(root)
    status = await start_and_wait(async_client, project)
    assert status["state"] == "running" and status["port"] and any("project booting" in line for line in status["log"])
    assert status["port"] != settings.PORT, "the project got its own free port"

    got = await async_client.get(url(project, "app/hello?x=1&y=2"), headers={"Origin": "null", "Cookie": "stackpilot=secret", "X-Custom": "kept"})
    body = got.json()
    assert got.status_code == 200 and body["path"] == "/hello?x=1&y=2"
    assert body["origin"] is None and body["cookie"] is None, "the page's origin and cookies are not passed on"
    assert body["x-custom"] == "kept"
    assert got.headers["access-control-allow-origin"] == "*", "the project's own CORS header is replaced"
    assert "set-cookie" not in got.headers and "sandbox" in got.headers["content-security-policy"]

    posted = await async_client.post(url(project, "app/save"), content=b'{"a": 1}', headers={"Content-Type": "application/json"})
    assert posted.status_code == 201 and posted.json() == {"echo": '{"a": 1}', "type": "application/json"}


async def test_the_project_never_sees_stackpilots_own_secrets(async_client, project, root, allowed, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-SHOULD-NOT-LEAK")
    monkeypatch.setenv("JWT_SECRET", "jwt-SHOULD-NOT-LEAK")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///leak")
    write_project(root)
    await start_and_wait(async_client, project)
    names = (await async_client.get(url(project, "app/env"))).json()
    assert not {"LLM_API_KEY", "JWT_SECRET", "DATABASE_URL", "ALLOW_SENDING_CODE_TO_PROVIDER", "ALLOW_RUNNING_PROJECT_CODE"} & set(names)
    assert "PORT" in names and "PYTHONUNBUFFERED" in names


def test_the_environment_is_built_from_an_allow_list(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("MY_TOKEN", "x")
    plan = runner.RunPlan("custom", "t", None, ("x",), (), False, False)
    env = runner._clean_env(runner.ProjectRun("p", str(tmp_path), plan), 4242)
    assert "OPENAI_API_KEY" not in env and "MY_TOKEN" not in env and env["PORT"] == "4242"


async def test_the_page_is_re_pointed_at_the_forwarder_only_while_running_and_the_file_is_untouched(async_client, project, root, allowed):
    write_project(root)
    page = "<script>const API='http://localhost:8000'; const ws=new WebSocket('ws://127.0.0.1:8000/live'); fetch('http://localhost:3999/x')</script>"
    (root / "index.html").write_text(page)
    before = await async_client.get(url(project, "preview/index.html"))
    assert before.text == page and "x-stackpilot-rewrites" not in before.headers

    await start_and_wait(async_client, project)
    after = await async_client.get(url(project, "preview/index.html"))
    base = f"/api/projects/{project['id']}/app"
    assert after.headers["x-stackpilot-rewrites"] == "2"
    assert f"http://test{base}" in after.text or f"://127.0.0.1{base}" in after.text or base in after.text
    assert "ws://" in after.text and "localhost:8000" not in after.text and "127.0.0.1:8000" not in after.text
    assert "http://localhost:3999/x" in after.text, "ports the project did not declare are left alone"
    assert (root / "index.html").read_text() == page, "the file on disk never changes"


def test_rewriting_only_touches_declared_ports_and_whole_port_numbers():
    text = "a http://localhost:8000/x b ws://localhost:8000 c http://localhost:80001 d http://example.com:8000 e https://127.0.0.1:8000/y"
    out, count = runner.rewrite_origins(text, [8000], "http://127.0.0.1:9", "PID")
    assert count == 3
    assert "http://localhost:80001" in out and "http://example.com:8000" in out
    assert out.count("http://127.0.0.1:9/api/projects/PID/app") == 2 and "ws://127.0.0.1:9/api/projects/PID/app" in out
    assert runner.rewrite_origins(text, [], "http://127.0.0.1:9", "PID") == (text, 0)


async def test_the_sandboxed_pages_preflight_is_answered_for_the_forwarder_only(async_client, project, root):
    ask = {"Origin": "null", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
    res = await async_client.options(url(project, "app/save"), headers=ask)
    assert res.status_code == 204 and res.headers["access-control-allow-origin"] == "*"
    assert "POST" in res.headers["access-control-allow-methods"] and res.headers["access-control-allow-headers"] == "content-type"
    # the rest of the API still trusts only this app's own pages
    other = await async_client.options("/api/projects", headers=ask)
    assert other.status_code != 204 and other.headers.get("access-control-allow-origin") != "*"
    other = await async_client.options(url(project, "files/content"), headers=ask)
    assert other.headers.get("access-control-allow-origin") != "*"


async def test_a_sandboxed_page_still_cannot_read_the_stackpilot_api(async_client, project, root):
    res = await async_client.get("/api/projects", headers={"Origin": "null"})
    assert res.headers.get("access-control-allow-origin") not in ("*", "null")


async def test_the_forwarder_says_so_when_the_project_is_not_running(async_client, project, root):
    res = await async_client.get(url(project, "app/anything"))
    assert res.status_code == 409 and "not running" in res.json()["detail"] and res.headers["access-control-allow-origin"] == "*"


async def test_stopping_ends_the_process_and_the_forwarder_stops_answering(async_client, project, root, allowed):
    write_project(root)
    await start_and_wait(async_client, project)
    proc = runner.get_run(project["id"]).proc
    assert proc.poll() is None
    res = await async_client.post(url(project, "run/stop"))
    assert res.json()["state"] == "stopped"
    assert proc.poll() is not None
    assert (await async_client.get(url(project, "app/hello"))).status_code == 409


async def test_stop_all_ends_every_process(async_client, project, root, allowed):
    write_project(root)
    await start_and_wait(async_client, project)
    port = runner.get_run(project["id"]).port
    await runner.stop_all()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1)


async def test_a_project_that_crashes_on_start_is_reported_with_its_output(async_client, project, root, allowed):
    write_project(root, {"start": ["{python}", "-c", "import sys; print('boom: missing module'); sys.exit(3)"]})
    status = await start_and_wait(async_client, project)
    assert status["state"] == "failed" and "exit code 3" in status["message"]
    assert any("boom: missing module" in line for line in status["log"])


async def test_the_install_step_runs_once_and_is_skipped_until_the_files_change(async_client, project, root, allowed):
    write_project(root, {**CONFIG, "install": ["{python}", "-c", "print('INSTALLING NOW')"], "fingerprint": ["deps.txt"]})
    (root / "deps.txt").write_text("one")
    first = await start_and_wait(async_client, project)
    assert any("INSTALLING NOW" in line for line in first["log"])
    await async_client.post(url(project, "run/stop"))
    runner._RUNS.clear()
    second = await start_and_wait(async_client, project)
    assert not any("INSTALLING NOW" in line for line in second["log"]) and any("already installed" in line for line in second["log"])
    await async_client.post(url(project, "run/stop"))
    runner._RUNS.clear()
    (root / "deps.txt").write_text("two")
    third = await start_and_wait(async_client, project)
    assert any("INSTALLING NOW" in line for line in third["log"])


async def test_a_failing_install_stops_before_anything_starts(async_client, project, root, allowed):
    write_project(root, {**CONFIG, "install": ["{python}", "-c", "import sys; sys.exit(9)"]})
    status = await start_and_wait(async_client, project)
    assert status["state"] == "failed" and "exit code 9" in status["message"] and status["port"] is None
    assert not any("project booting" in line for line in status["log"])


async def test_restart_starts_the_project_again_on_a_fresh_process(async_client, project, root, allowed):
    write_project(root)
    await start_and_wait(async_client, project)
    old = runner.get_run(project["id"]).proc
    res = await async_client.post(url(project, "run/restart"))
    assert res.status_code == 202
    status = await wait_for(async_client, project, ("running", "failed"))
    assert status["state"] == "running" and old.poll() is not None and runner.get_run(project["id"]).proc is not old


async def test_only_a_few_projects_can_run_at_once(async_client, project, root, allowed, monkeypatch):
    write_project(root)
    monkeypatch.setattr(runner, "MAX_RUNS", 1)
    plan = runner.detect_plan(str(root))
    runner._RUNS["other-project"] = runner.ProjectRun("other-project", str(root), plan, state="running")
    res = await async_client.post(url(project, "run/start"))
    assert res.status_code == 409 and res.json()["detail"]["code"] == "too_many_runs"


async def test_starting_twice_does_not_start_a_second_copy(async_client, project, root, allowed):
    write_project(root)
    await start_and_wait(async_client, project)
    first = runner.get_run(project["id"])
    await async_client.post(url(project, "run/start"))
    assert runner.get_run(project["id"]) is first


async def test_run_endpoints_refuse_a_wrong_host_header_and_a_project_name(async_client, project, root):
    assert (await async_client.get(url(project, "run"), headers={"Host": "evil.example"})).status_code == 400
    assert (await async_client.get(f"/api/projects/{project['name']}/run")).status_code == 404


# --- the websocket relay -------------------------------------------------------------------------------------------------
WS_SERVER = '''
import asyncio, sys
from websockets.asyncio.server import serve

async def echo(ws):
    async for message in ws:
        await ws.send("echo:" + message if isinstance(message, str) else message)

async def main():
    async with serve(echo, "127.0.0.1", int(sys.argv[1])):
        print("ws booting", flush=True)
        await asyncio.Future()

asyncio.run(main())
'''


async def test_a_websocket_from_the_page_is_relayed_to_the_project(async_client, project, root, allowed):
    from starlette.testclient import TestClient
    from app.main import app

    write_project(root, CONFIG, WS_SERVER)
    await start_and_wait(async_client, project)
    # A loopback host (the Host check applies) and no `with`: entering the app's lifespan would stop the run on exit.
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    with client.websocket_connect(f"/api/projects/{project['id']}/app/live?room=1", headers={"host": "127.0.0.1:8000"}) as ws:
        ws.send_text("hello")
        assert ws.receive_text() == "echo:hello"
        ws.send_bytes(b"\x01\x02")
        assert ws.receive_bytes() == b"\x01\x02"


async def test_a_websocket_to_a_project_that_is_not_running_is_closed(project):
    from starlette.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from app.main import app

    client = TestClient(app, base_url="http://127.0.0.1:8000")
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect(f"/api/projects/{project['id']}/app/live", headers={"host": "127.0.0.1:8000"}) as ws:
            ws.receive_text()
    assert closed.value.code == 1013


# --- what these modules are allowed to do ------------------------------------------------------------------------------------
def test_the_forwarder_only_ever_talks_to_loopback():
    code = (Path(runner.__file__).parent.parent / "api" / "run.py").read_text(encoding="utf-8")
    assert len(re.findall(r"httpx\.AsyncClient\(", code)) == 1
    targets = re.findall(r"""f?["'](https?|wss?)://([^/"'{:]*)""", code)
    assert targets and {host for _scheme, host in targets} == {"127.0.0.1"}, targets


def test_commands_are_never_run_through_a_shell():
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert "shell=True" not in source and "os.system" not in source and "create_subprocess_shell" not in source
    assert source.count("shell=False") == 1


def test_no_python_plan_relies_on_a_server_side_file_watcher(tmp_path):
    (tmp_path / "manage.py").write_text("# django")
    django = runner.detect_plan(str(tmp_path))
    assert "--noreload" in django.start and not django.auto_reload
    (tmp_path / "manage.py").unlink()
    (tmp_path / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    scanned = runner.detect_plan(str(tmp_path))
    assert "--reload" not in scanned.start and not scanned.auto_reload


# --- every kind of project gets a clear answer -------------------------------------------------------------------------------
GO_FIXED = 'package main\nimport "net/http"\nfunc main() { http.ListenAndServe(":8080", nil) }\n'
GO_PORT_ENV = 'package main\nimport ("net/http"; "os")\nfunc main() { http.ListenAndServe(":"+os.Getenv("PORT"), nil) }\n'


def test_a_go_program_with_a_hardcoded_port_must_be_given_that_port(tmp_path):
    (tmp_path / "go.mod").write_text("module x\n\ngo 1.22\n")
    (tmp_path / "main.go").write_text(GO_FIXED)
    plan = runner.detect_plan(str(tmp_path))
    assert plan.kind == "go" and plan.start == ("go", "run", ".") and plan.fixed_port == 8080 and plan.app_ports == (8080,)
    assert plan.install is None and plan.tools() == ("go",)


def test_a_go_program_that_reads_PORT_gets_a_free_port(tmp_path):
    (tmp_path / "go.mod").write_text("module x\n")
    (tmp_path / "main.go").write_text(GO_PORT_ENV.replace('":"+os.Getenv("PORT")', '":9090"') + '// os.Getenv("PORT")\n')
    plan = runner.detect_plan(str(tmp_path))
    assert plan.fixed_port is None and ("PORT", "{port}") in plan.env


def test_a_go_program_in_cmd_is_found(tmp_path):
    (tmp_path / "go.mod").write_text("module x\n")
    (tmp_path / "cmd" / "api").mkdir(parents=True)
    (tmp_path / "cmd" / "api" / "main.go").write_text(GO_FIXED)
    assert runner.detect_plan(str(tmp_path)).start == ("go", "run", "./cmd/api")


def test_a_node_script_that_runs_a_framework_missing_from_package_json_is_warned_about(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"dev": "next dev"}}))
    plan = runner.detect_plan(str(tmp_path))
    assert plan.warnings and "'next'" in plan.warnings[0] and "dependency" in plan.warnings[0]
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"dev": "next dev"}, "dependencies": {"next": "14", "react": "18"}}))
    assert runner.detect_plan(str(tmp_path)).warnings == ()


async def test_a_missing_program_is_reported_up_front_and_refuses_to_start(async_client, project, root, allowed, monkeypatch):
    (root / "go.mod").write_text("module x\n")
    (root / "main.go").write_text(GO_FIXED)
    monkeypatch.setattr(runner.shutil, "which", lambda name: None)
    status = (await async_client.get(url(project, "run"))).json()
    assert status["missing_tools"] == ["go"] and "https://go.dev/dl/" in status["missing_tools_help"]
    res = await async_client.post(url(project, "run/start"))
    assert res.status_code == 422 and res.json()["detail"]["code"] == "tool_missing" and "'go' is not installed" in res.json()["detail"]["message"]
    assert runner._RUNS == {}, "nothing was created or started"


async def test_a_project_that_insists_on_a_port_someone_else_is_using_says_so(async_client, project, root, allowed):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        port = taken.getsockname()[1]
        write_project(root, {**CONFIG, "fixed_port": port})
        status = await start_and_wait(async_client, project)
    assert status["state"] == "failed" and f"port {port}" in status["message"] and "already using it" in status["message"]
    assert not any("project booting" in line for line in status["log"])


async def test_a_project_with_a_fixed_port_is_started_on_exactly_that_port(async_client, project, root, allowed):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    write_project(root, {**CONFIG, "fixed_port": port})
    status = await start_and_wait(async_client, project)
    assert status["state"] == "running" and status["port"] == port
    assert (await async_client.get(url(project, "app/hello"))).json()["path"] == "/hello"


def test_the_private_environment_lives_at_a_short_path():
    """Windows stops at 260 characters, and a long dependency tree (TensorFlow) gets close even from a modest folder."""
    path = runner._venv_python("f92d4565-c14f-4539-abd8-e3d1103e19eb")
    assert path.parent.parent.name == "v" and path.parent.parent.parent.name == "f92d4565-c"
    assert len(str(path.parent.parent)) <= len(str(runner.runtime_root())) + 14


def test_every_starter_template_gets_a_clean_runnable_plan(tmp_path):
    from app.api.projects import DEFAULT_STARTER_FILES, scaffold_starter_project

    expected = {"FastAPI + Python": "python", "Next.js + TypeScript": "node", "Go Microservice": "go"}
    assert set(DEFAULT_STARTER_FILES) == set(expected)
    for name, kind in expected.items():
        folder = tmp_path / kind
        folder.mkdir()
        scaffold_starter_project(str(folder), name)
        plan = runner.detect_plan(str(folder))
        assert plan is not None and plan.kind == kind and plan.warnings == (), name


def test_the_nextjs_starter_lists_what_it_needs_to_run():
    from app.api.projects import DEFAULT_STARTER_FILES

    files = DEFAULT_STARTER_FILES["Next.js + TypeScript"]
    deps = json.loads(files["package.json"])["dependencies"]
    assert {"next", "react", "react-dom"} <= set(deps)
    assert "app/layout.tsx" in files and "tsconfig.json" in files, "the app router needs a root layout"
    assert 'os.Getenv("PORT")' in DEFAULT_STARTER_FILES["Go Microservice"]["main.go"], "the Go starter must accept the port it is given"


# --- leftovers from a backend that was killed without a clean shutdown -----------------------------------------------------------
import subprocess
import sys


def _leftover(project_id: str, argv, recorded=None):
    """Start a long-sleeping process and write the record a run would have left behind."""
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    folder = runner.project_runtime_dir(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(json.dumps({"pid": proc.pid, "argv": recorded or argv}))
    return proc


def test_a_server_left_running_by_an_earlier_backend_is_stopped_at_startup():
    proc = _leftover("orphan-one-xyz", [sys.executable, "-c", "import time; time.sleep(300)  # stackpilot-leftover-1"])
    try:
        assert proc.poll() is None
        assert "orphan-one" in "".join(runner.reap_orphans())
        proc.wait(timeout=10)
        assert proc.poll() is not None
        assert not (runner.project_runtime_dir("orphan-one-xyz") / "run.json").exists()
    finally:
        if proc.poll() is None:
            proc.kill()


def test_a_different_program_that_reused_the_process_id_is_never_stopped():
    argv = [sys.executable, "-c", "import time; time.sleep(300)  # an unrelated program"]
    proc = _leftover("orphan-two-xyz", argv, recorded=[sys.executable, "-m", "uvicorn", "backend.app:app", "--port", "4242"])
    try:
        assert runner.reap_orphans() == []
        assert proc.poll() is None, "the unrelated process must still be running"
        assert not (runner.project_runtime_dir("orphan-two-xyz") / "run.json").exists(), "the stale record is dropped"
    finally:
        proc.kill()


def test_a_record_for_a_process_that_is_gone_is_just_removed():
    folder = runner.project_runtime_dir("orphan-three-x")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(json.dumps({"pid": 2_000_000_000, "argv": ["whatever"]}))
    assert runner.reap_orphans() == [] and not (folder / "run.json").exists()
    (folder / "run.json").write_text("not json")
    assert runner.reap_orphans() == [] and not (folder / "run.json").exists()


async def test_a_started_project_leaves_a_record_that_is_removed_when_it_stops(async_client, project, root, allowed):
    write_project(root)
    await start_and_wait(async_client, project)
    record = runner.project_runtime_dir(project["id"]) / "run.json"
    assert json.loads(record.read_text())["pid"] == runner.get_run(project["id"]).proc.pid
    await async_client.post(url(project, "run/stop"))
    assert not record.exists()
