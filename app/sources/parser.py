import base64
import json
import re
import urllib.parse
import ipaddress
from typing import List, Optional, Tuple, Dict, Any
from app.checkers.base import NodeInfo, ProtocolType
from app.core.logger import logger


class NodeParser:
    """Robust parser for network nodes, proxies, and VPN subscription formats."""

    @classmethod
    def parse_line(cls, line: str) -> Optional[NodeInfo]:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            return None

        # Try URL formats
        if line.startswith("ss://"):
            return cls._parse_shadowsocks(line)
        elif line.startswith("vless://"):
            return cls._parse_vless(line)
        elif line.startswith("vmess://"):
            return cls._parse_vmess(line)
        elif line.startswith("socks5://") or line.startswith("socks4://"):
            return cls._parse_socks_uri(line)
        elif line.startswith("http://") or line.startswith("https://"):
            return cls._parse_http_uri(line)
        elif line.startswith("wg://") or line.startswith("wireguard://"):
            return cls._parse_wireguard_uri(line)

        # Fallback to host:port or ip:port
        return cls._parse_host_port(line)

    @classmethod
    def _parse_host_port(cls, text: str) -> Optional[NodeInfo]:
        """Parse `1.2.3.4:8080`, `example.com:443`, or `1.2.3.4 8080`."""
        # Clean inline comments
        clean_text = text.split("#")[0].split(";")[0].strip()
        tag = text.split("#")[1].strip() if "#" in text else None

        # Check for colon separator: host:port
        match = re.match(r"^([a-zA-Z0-9\.\-\:_]+)[:\s]+(\d{1,5})$", clean_text)
        if match:
            host, port_str = match.groups()
            port = int(port_str)
            if 1 <= port <= 65535:
                proto = ProtocolType.HTTPS_PROXY if port in (443, 8443) else ProtocolType.RAW_TCP
                return NodeInfo(
                    raw_input=text,
                    host=host,
                    port=port,
                    protocol=proto,
                    tag=tag or f"{host}:{port}",
                )
        return None

    @classmethod
    def _parse_http_uri(cls, uri: str) -> Optional[NodeInfo]:
        parsed = urllib.parse.urlparse(uri)
        protocol = ProtocolType.HTTPS_PROXY if parsed.scheme == "https" else ProtocolType.HTTP_PROXY
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        host = parsed.hostname
        if not host:
            return None

        tag = urllib.parse.unquote(parsed.fragment) if parsed.fragment else f"{parsed.scheme.upper()}-{host}:{port}"
        return NodeInfo(
            raw_input=uri,
            host=host,
            port=port,
            protocol=protocol,
            tag=tag,
            username=parsed.username,
            password=parsed.password,
        )

    @classmethod
    def _parse_socks_uri(cls, uri: str) -> Optional[NodeInfo]:
        parsed = urllib.parse.urlparse(uri)
        protocol = ProtocolType.SOCKS4 if parsed.scheme == "socks4" else ProtocolType.SOCKS5
        port = parsed.port or 1080
        host = parsed.hostname
        if not host:
            return None

        tag = urllib.parse.unquote(parsed.fragment) if parsed.fragment else f"{protocol.value}-{host}:{port}"
        return NodeInfo(
            raw_input=uri,
            host=host,
            port=port,
            protocol=protocol,
            tag=tag,
            username=parsed.username,
            password=parsed.password,
        )

    @classmethod
    def _parse_shadowsocks(cls, uri: str) -> Optional[NodeInfo]:
        try:
            raw_body = uri[5:]  # strip 'ss://'
            tag = None
            if "#" in raw_body:
                raw_body, tag = raw_body.split("#", 1)
                tag = urllib.parse.unquote(tag)

            # SIP002 format: ss://base64(method:password)@host:port
            if "@" in raw_body:
                user_info, host_port = raw_body.split("@", 1)
                host, port_str = host_port.split(":", 1)
                port = int(port_str.split("?")[0].split("/")[0])
                decoded_user = cls._safe_b64decode(user_info)
                return NodeInfo(
                    raw_input=uri,
                    host=host,
                    port=port,
                    protocol=ProtocolType.SHADOWSOCKS,
                    tag=tag or f"SS-{host}:{port}",
                    extra_params={"auth": decoded_user}
                )
            else:
                # Old format: ss://base64(method:password@host:port)
                decoded = cls._safe_b64decode(raw_body)
                if "@" in decoded:
                    auth, host_port = decoded.split("@", 1)
                    host, port_str = host_port.split(":", 1)
                    port = int(port_str)
                    return NodeInfo(
                        raw_input=uri,
                        host=host,
                        port=port,
                        protocol=ProtocolType.SHADOWSOCKS,
                        tag=tag or f"SS-{host}:{port}",
                        extra_params={"auth": auth}
                    )
        except Exception as e:
            logger.debug(f"Failed to parse Shadowsocks URI '{uri}': {e}")
        return None

    @classmethod
    def _parse_vless(cls, uri: str) -> Optional[NodeInfo]:
        try:
            parsed = urllib.parse.urlparse(uri)
            host = parsed.hostname
            port = parsed.port or 443
            uuid = parsed.username
            tag = urllib.parse.unquote(parsed.fragment) if parsed.fragment else f"VLESS-{host}:{port}"
            params = dict(urllib.parse.parse_qsl(parsed.query))

            if host:
                return NodeInfo(
                    raw_input=uri,
                    host=host,
                    port=port,
                    protocol=ProtocolType.VLESS,
                    uuid=uuid,
                    tag=tag,
                    extra_params=params,
                )
        except Exception as e:
            logger.debug(f"Failed to parse VLESS URI: {e}")
        return None

    @classmethod
    def _parse_vmess(cls, uri: str) -> Optional[NodeInfo]:
        try:
            b64_str = uri[8:]
            decoded_json = cls._safe_b64decode(b64_str)
            data = json.loads(decoded_json)

            host = data.get("add")
            port = int(data.get("port", 443))
            tag = data.get("ps") or f"VMess-{host}:{port}"
            uuid = data.get("id")

            if host and port:
                return NodeInfo(
                    raw_input=uri,
                    host=host,
                    port=port,
                    protocol=ProtocolType.VMESS,
                    uuid=uuid,
                    tag=tag,
                    extra_params=data,
                )
        except Exception as e:
            logger.debug(f"Failed to parse VMess URI: {e}")
        return None

    @classmethod
    def _parse_wireguard_uri(cls, uri: str) -> Optional[NodeInfo]:
        try:
            parsed = urllib.parse.urlparse(uri)
            host = parsed.hostname
            port = parsed.port or 51820
            tag = urllib.parse.unquote(parsed.fragment) if parsed.fragment else f"WG-{host}:{port}"
            if host:
                return NodeInfo(
                    raw_input=uri,
                    host=host,
                    port=port,
                    protocol=ProtocolType.WIREGUARD,
                    tag=tag,
                )
        except Exception as e:
            logger.debug(f"Failed to parse WireGuard URI: {e}")
        return None

    @classmethod
    def _safe_b64decode(cls, s: str) -> str:
        s = s.strip()
        padding = 4 - (len(s) % 4)
        if padding and padding < 4:
            s += "=" * padding
        return base64.urlsafe_b64decode(s.encode("utf-8")).decode("utf-8", errors="ignore")

    @classmethod
    def parse_text(cls, content: str) -> List[NodeInfo]:
        """Parse raw multi-line string into distinct valid nodes."""
        nodes: List[NodeInfo] = []
        seen = set()

        for line in content.splitlines():
            node = cls.parse_line(line)
            if node:
                key = (node.host, node.port, node.protocol)
                if key not in seen:
                    seen.add(key)
                    nodes.append(node)

        return nodes
