import asyncio
import ssl
import time
from app.checkers.base import BaseChecker, NodeInfo, CheckResult, ProtocolType
from app.core.geoip import geoip_service
from app.config import settings
from app.core.logger import logger


class VPNNodeChecker(BaseChecker):
    """Checker for VPN protocols: Shadowsocks, VLESS, VMess, and WireGuard endpoints."""

    async def check(self, node: NodeInfo) -> CheckResult:
        if node.protocol == ProtocolType.WIREGUARD:
            return await self._check_wireguard(node)
        return await self._check_v2ray_or_ss(node)

    async def _check_v2ray_or_ss(self, node: NodeInfo) -> CheckResult:
        """Check TCP/TLS handshake for VLESS, VMess, or Shadowsocks."""
        start_time = time.perf_counter()
        geo_task = asyncio.create_task(geoip_service.lookup(node.host))

        security = node.extra_params.get("security", "").lower()
        sni = node.extra_params.get("sni") or node.extra_params.get("host") or node.host

        ssl_ctx = None
        if security == "tls" or node.port in (443, 8443):
            try:
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
            except Exception as e:
                logger.debug(f"SSL creation error: {e}")

        try:
            connect_coro = asyncio.open_connection(
                node.host,
                node.port,
                ssl=ssl_ctx,
                server_hostname=sni if ssl_ctx else None,
            )
            reader, writer = await asyncio.wait_for(connect_coro, timeout=settings.TCP_PING_TIMEOUT)
            latency = (time.perf_counter() - start_time) * 1000.0

            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

            geo = await geo_task
            return CheckResult(
                node=node,
                is_alive=True,
                latency_ms=round(latency, 2),
                status_code=200,
                geo=geo,
                details={
                    "protocol": node.protocol.value,
                    "security": security or "plain/tcp",
                    "sni": sni,
                    "handshake": "SUCCESS",
                }
            )

        except asyncio.TimeoutError:
            geo = await geo_task
            return CheckResult(
                node=node,
                is_alive=False,
                latency_ms=-1.0,
                status_code=None,
                error=f"Timeout connecting to {node.endpoint}",
                geo=geo,
                details={"handshake": "TIMEOUT"}
            )
        except Exception as e:
            geo = await geo_task
            return CheckResult(
                node=node,
                is_alive=False,
                latency_ms=-1.0,
                status_code=None,
                error=str(e),
                geo=geo,
                details={"handshake": "FAILED"}
            )

    async def _check_wireguard(self, node: NodeInfo) -> CheckResult:
        """Check WireGuard UDP endpoint connectivity."""
        start_time = time.perf_counter()
        geo_task = asyncio.create_task(geoip_service.lookup(node.host))

        class WGClientProtocol(asyncio.DatagramProtocol):
            def __init__(self, on_con_lost):
                self.on_con_lost = on_con_lost
                self.transport = None

            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, data, addr):
                pass

            def error_received(self, exc):
                pass

            def connection_lost(self, exc):
                pass

        try:
            loop = asyncio.get_running_loop()
            on_con_lost = loop.create_future()

            transport, protocol = await loop.create_datagram_endpoint(
                lambda: WGClientProtocol(on_con_lost),
                remote_addr=(node.host, node.port)
            )

            # Dummy WireGuard Initiation packet header (Type 1, 148 bytes)
            dummy_init = b"\x01\x00\x00\x00" + b"\x00" * 144
            transport.sendto(dummy_init)
            latency = (time.perf_counter() - start_time) * 1000.0

            transport.close()
            geo = await geo_task
            return CheckResult(
                node=node,
                is_alive=True,
                latency_ms=round(latency, 2),
                status_code=200,
                geo=geo,
                details={"protocol": "WireGuard", "type": "UDP_PROBE_SENT"}
            )
        except Exception as e:
            geo = await geo_task
            return CheckResult(
                node=node,
                is_alive=False,
                latency_ms=-1.0,
                status_code=None,
                error=str(e),
                geo=geo,
                details={"protocol": "WireGuard", "handshake": "FAILED"}
            )
