from __future__ import annotations

from unittest.mock import MagicMock, patch
import sys

from hosaka.llm.gateway import GatewayAdapter
from hosaka.llm.gateway.client import OpenClawGatewayClient


def test_gateway_reachable_uses_url_port() -> None:
    with patch("socket.create_connection") as mock_conn:
        OpenClawGatewayClient.is_gateway_reachable(url="ws://127.0.0.1:18790")
    mock_conn.assert_called_once_with(("127.0.0.1", 18790), timeout=1)


def test_gateway_adapter_uses_picoclaw_url_env() -> None:
    with (
        patch.dict("os.environ", {"PICOCLAW_GATEWAY_URL": "ws://127.0.0.1:18790"}, clear=True),
        patch("hosaka.llm.gateway.OpenClawGatewayClient.is_gateway_reachable", return_value=True) as mock_reachable,
        patch.dict(sys.modules, {"websockets": MagicMock()}),
    ):
        assert GatewayAdapter.is_available() is True
    mock_reachable.assert_called_once_with(url="ws://127.0.0.1:18790")
