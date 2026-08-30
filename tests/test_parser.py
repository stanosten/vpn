import pytest
from app.sources.parser import NodeParser
from app.checkers.base import ProtocolType


def test_parse_ip_port():
    node = NodeParser.parse_line("1.1.1.1:53")
    assert node is not None
    assert node.host == "1.1.1.1"
    assert node.port == 53
    assert node.protocol == ProtocolType.RAW_TCP


def test_parse_with_tag():
    node = NodeParser.parse_line("8.8.8.8:443 # GoogleDNS")
    assert node is not None
    assert node.host == "8.8.8.8"
    assert node.port == 443
    assert node.tag == "GoogleDNS"


def test_parse_http_proxy():
    node = NodeParser.parse_line("http://user:pass@192.168.1.100:8080#MyProxy")
    assert node is not None
    assert node.host == "192.168.1.100"
    assert node.port == 8080
    assert node.protocol == ProtocolType.HTTP_PROXY
    assert node.username == "user"
    assert node.password == "pass"
    assert node.tag == "MyProxy"


def test_parse_socks5():
    node = NodeParser.parse_line("socks5://127.0.0.1:1080")
    assert node is not None
    assert node.host == "127.0.0.1"
    assert node.port == 1080
    assert node.protocol == ProtocolType.SOCKS5


def test_parse_vless():
    vless_uri = "vless://d342d11e-d424-4583-b36e-524ab1f0afa4@1.1.1.1:443?encryption=none&security=tls#CloudflareVLESS"
    node = NodeParser.parse_line(vless_uri)
    assert node is not None
    assert node.host == "1.1.1.1"
    assert node.port == 443
    assert node.protocol == ProtocolType.VLESS
    assert node.uuid == "d342d11e-d424-4583-b36e-524ab1f0afa4"
    assert node.tag == "CloudflareVLESS"
    assert node.extra_params.get("security") == "tls"


def test_parse_text_multi_line():
    raw = """
    # Comment line
    1.1.1.1:53
    8.8.8.8:53
    1.1.1.1:53  # Duplicate should be filtered out
    http://proxy.test:8080
    """
    nodes = NodeParser.parse_text(raw)
    assert len(nodes) == 3
