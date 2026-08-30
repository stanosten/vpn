import pytest
import asyncio
from app.checkers.base import NodeInfo, ProtocolType
from app.checkers.ip_port import IPPortChecker
from app.checkers.dispatcher import dispatcher
from app.core.geoip import country_code_to_flag, is_private_ip


def test_flag_converter():
    assert country_code_to_flag("US") == "🇺🇸"
    assert country_code_to_flag("DE") == "🇩🇪"
    assert country_code_to_flag("RU") == "🇷🇺"
    assert country_code_to_flag(None) == "🌐"


def test_is_private_ip():
    assert is_private_ip("127.0.0.1") is True
    assert is_private_ip("192.168.1.1") is True
    assert is_private_ip("10.0.0.5") is True
    assert is_private_ip("8.8.8.8") is False
    assert is_private_ip("1.1.1.1") is False


@pytest.mark.asyncio
async def test_ip_port_checker_live():
    # Test checking a known public DNS host:port (e.g. 1.1.1.1:53 or 8.8.8.8:53)
    node = NodeInfo(
        raw_input="1.1.1.1:53",
        host="1.1.1.1",
        port=53,
        protocol=ProtocolType.RAW_TCP,
    )
    checker = IPPortChecker()
    res = await checker.check(node)
    assert res.node.host == "1.1.1.1"
    assert res.node.port == 53
    # Either alive or handled gracefully without throwing unhandled exceptions
    assert isinstance(res.is_alive, bool)


@pytest.mark.asyncio
async def test_ip_port_checker_dead():
    # Test checking an unused closed local port
    node = NodeInfo(
        raw_input="127.0.0.1:59998",
        host="127.0.0.1",
        port=59998,
        protocol=ProtocolType.RAW_TCP,
    )
    checker = IPPortChecker()
    res = await checker.check(node)
    assert res.is_alive is False
    assert res.latency_ms == -1.0
