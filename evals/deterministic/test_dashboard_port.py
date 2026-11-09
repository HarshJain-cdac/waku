"""DETERMINISTIC EVAL — a named dashboard port is honoured exactly.

The dashboard walks past a busy port so an unconfigured run does not crash on
the default. That is right for a default and wrong for an explicit setting:
nit-forge-ui, bookmarks and forwarded tunnels all address the port that was
asked for, so a backend that quietly started on the next one is a backend
nothing can reach — and the port it drifted to may belong to another checkout.

Offline: binds a real socket on an ephemeral port, no network egress.
"""

from __future__ import annotations

import socket

import pytest

from waku.ops import dashboard


def _busy_port() -> tuple[socket.socket, int]:
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    return holder, holder.getsockname()[1]


def test_an_explicit_busy_port_refuses_to_start(monkeypatch):
    holder, port = _busy_port()
    try:
        monkeypatch.setenv("WAKU_DASHBOARD_PORT", str(port))
        monkeypatch.delenv("PORT", raising=False)
        with pytest.raises(SystemExit) as raised:
            dashboard.main()
        message = str(raised.value)
        assert str(port) in message
        assert "will not start somewhere else" in message
    finally:
        holder.close()


def test_the_plain_PORT_variable_is_explicit_too(monkeypatch):
    """Deploy platforms and IDE preview panes set PORT. It names a port just as
    definitely as WAKU_DASHBOARD_PORT does."""
    holder, port = _busy_port()
    try:
        monkeypatch.delenv("WAKU_DASHBOARD_PORT", raising=False)
        monkeypatch.setenv("PORT", str(port))
        with pytest.raises(SystemExit):
            dashboard.main()
    finally:
        holder.close()


def test_the_default_still_walks_past_a_busy_port(monkeypatch):
    """With nothing configured, a busy 7777 must NOT be fatal — that is what
    the walk is for, and this eval exists so the strict path never eats it."""
    monkeypatch.delenv("WAKU_DASHBOARD_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    holder, free_port = _busy_port()
    holder.close()  # a port we know nothing holds

    attempted: list[int] = []
    real_server = dashboard.ThreadingHTTPServer

    class Recorder:
        def __init__(self, address, handler):
            attempted.append(address[1])
            if len(attempted) < 3:  # first two "busy", third succeeds
                raise OSError("address in use")
            self._server = real_server(("127.0.0.1", 0), handler)

        def __getattr__(self, name):
            return getattr(self._server, name)

    monkeypatch.setattr(dashboard, "ThreadingHTTPServer", Recorder)
    monkeypatch.setattr(dashboard, "PORT", free_port)
    # serve_forever would block; stop right after the bind decision.
    monkeypatch.setattr(Recorder, "serve_forever", lambda self: None, raising=False)

    try:
        dashboard.main()
    except SystemExit as exc:  # a walk must never end in SystemExit
        pytest.fail(f"the unconfigured default must walk, not exit: {exc}")
    except Exception:
        pass  # anything after the bind (gateways, browser) is out of scope here

    assert attempted[:3] == [free_port, free_port + 1, free_port + 2]


def test_env_and_ui_agree_on_the_port():
    """The frontend addresses the backend by port. If these two drift apart the
    UI talks to nothing — or to another checkout's waku."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    env = (root / ".env").read_text(encoding="utf-8")
    ui_env = root / "nit-forge-ui" / ".env"
    if not ui_env.exists():
        pytest.skip("frontend env not present")

    backend = next(
        (line.split("=", 1)[1].strip()
         for line in env.splitlines()
         if line.strip().startswith("WAKU_DASHBOARD_PORT=")),
        "",
    )
    if not backend:
        pytest.skip("no explicit backend port pinned")
    assert f":{backend}" in ui_env.read_text(encoding="utf-8"), (
        f"nit-forge-ui/.env must point at port {backend}"
    )
