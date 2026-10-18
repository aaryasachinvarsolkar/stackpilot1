"""StackPilot has no authentication yet: every default must keep it on the loopback interface."""
import ipaddress
import re
from pathlib import Path

import yaml

from app.config import Settings

REPO = Path(__file__).resolve().parents[2]


def test_default_host_is_loopback_even_when_no_env_file_or_variable_is_present(monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    assert ipaddress.ip_address(Settings(_env_file=None).HOST).is_loopback


def test_env_example_binds_loopback():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    host = re.search(r"^HOST=(.*)$", text, re.M).group(1).strip()
    assert ipaddress.ip_address(host).is_loopback


def test_every_published_compose_port_is_bound_to_127_0_0_1():
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    published = [(name, port) for name, svc in compose["services"].items() for port in svc.get("ports", [])]
    assert published, "expected the compose file to publish ports"
    for name, port in published:
        assert str(port).startswith("127.0.0.1:"), f"service {name!r} publishes {port!r} on all interfaces"
