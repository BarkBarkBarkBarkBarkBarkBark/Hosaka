import socket

from hosaka.boot.launcher import is_port_in_use


def test_is_port_in_use_detects_bound_socket() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        assert is_port_in_use("127.0.0.1", port)
    finally:
        sock.close()

    assert not is_port_in_use("127.0.0.1", port)


def test_macos_supervisor_does_not_restart_after_exit(monkeypatch) -> None:
    from hosaka.boot import launcher
    from hosaka.tui import style

    monkeypatch.setattr(style.sys, "platform", "darwin")
    monkeypatch.delenv("HOSAKA_ALLOW_SHELL", raising=False)
    calls = []
    monkeypatch.setattr(launcher, "run_main_console", lambda: calls.append(True))
    launcher.run_console_supervised()
    assert calls == [True]
