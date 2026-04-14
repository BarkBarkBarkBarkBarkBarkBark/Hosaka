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
