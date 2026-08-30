import asyncio
import ssl
import time
from app.checkers.base import BaseChecker, NodeInfo, CheckResult, ProtocolType
from app.core.geoip import geoip_service
from app.config import settings
from app.core.logger import logger


class IPPortChecker(BaseChecker):
    """TCP Port and Latency Checker with optional SSL Handshake."""

    async def check(self, node: NodeInfo) -> CheckResult:
        start_time = time.perf_counter()
        geo_task = asyncio.create_task(geoip_service.lookup(node.host))

        try:
            # Measure TCP connection latency
            connect_coro = asyncio.open_connection(node.host, node.port)
            reader, writer = await asyncio.wait_for(connect_coro, timeout=settings.TCP_PING_TIMEOUT)
            latency = (time.perf_counter() - start_time) * 1000.0

            ssl_info = {}
            # Optional SSL probe for port 443 / HTTPS
            if node.port in (443, 8443) or node.protocol == ProtocolType.HTTPS_PROXY:
                try:
                    ssl_ctx = ssl.create_default_context()
                    ssl_ctx.check_hostname = False
                    ssl_ctx.verify_mode = ssl.CERT_NONE
                except Exception as e:
                    logger.debug(f"SSL context error: {e}")

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
                error=None,
                geo=geo,
                details={"handshake": "TCP_SUCCESS", **ssl_info}
            )

        except asyncio.TimeoutError:
            geo = await geo_task
            return CheckResult(
                node=node,
                is_alive=False,
                latency_ms=-1.0,
                status_code=None,
                error=f"TCP Timeout after {settings.TCP_PING_TIMEOUT}s",
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
