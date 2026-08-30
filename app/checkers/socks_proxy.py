import asyncio
import time
from app.checkers.base import BaseChecker, NodeInfo, CheckResult, ProtocolType
from app.core.geoip import geoip_service
from app.config import settings


class SocksProxyChecker(BaseChecker):
    """SOCKS4 and SOCKS5 Protocol Checker via raw binary handshake."""

    async def check(self, node: NodeInfo) -> CheckResult:
        start_time = time.perf_counter()
        geo_task = asyncio.create_task(geoip_service.lookup(node.host))

        is_socks4 = node.protocol == ProtocolType.SOCKS4
        try:
            connect_coro = asyncio.open_connection(node.host, node.port)
            reader, writer = await asyncio.wait_for(connect_coro, timeout=settings.TCP_PING_TIMEOUT)

            if is_socks4:
                # SOCKS4 Handshake: VN=4, CD=1 (CONNECT), DSTPORT=80 (0x0050), DSTIP=1.1.1.1, NULL USERID
                req = b"\x04\x01\x00\x50\x01\x01\x01\x01\x00"
                writer.write(req)
                await writer.drain()
                resp = await asyncio.wait_for(reader.read(8), timeout=settings.TCP_PING_TIMEOUT)
                latency = (time.perf_counter() - start_time) * 1000.0

                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

                if len(resp) >= 2 and resp[0] == 0x00 and resp[1] == 0x5A:
                    geo = await geo_task
                    return CheckResult(
                        node=node,
                        is_alive=True,
                        latency_ms=round(latency, 2),
                        status_code=200,
                        geo=geo,
                        details={"version": "SOCKS4", "status": "REQUEST_GRANTED"}
                    )
            else:
                # SOCKS5 Initial Greeting: VER=5, NMETHODS=2 (0x00 NO_AUTH, 0x02 USER_PASS)
                req = b"\x05\x02\x00\x02"
                writer.write(req)
                await writer.drain()
                resp = await asyncio.wait_for(reader.read(2), timeout=settings.TCP_PING_TIMEOUT)
                latency = (time.perf_counter() - start_time) * 1000.0

                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

                if len(resp) == 2 and resp[0] == 0x05:
                    auth_method = "NO_AUTH" if resp[1] == 0x00 else "USER_PASS" if resp[1] == 0x02 else f"METHOD_{resp[1]}"
                    geo = await geo_task
                    return CheckResult(
                        node=node,
                        is_alive=True,
                        latency_ms=round(latency, 2),
                        status_code=200,
                        geo=geo,
                        details={"version": "SOCKS5", "auth_method": auth_method}
                    )

            geo = await geo_task
            return CheckResult(
                node=node,
                is_alive=False,
                latency_ms=-1.0,
                status_code=None,
                error="Invalid SOCKS handshake response",
                geo=geo,
                details={"handshake": "INVALID_RESPONSE"}
            )

        except asyncio.TimeoutError:
            geo = await geo_task
            return CheckResult(
                node=node,
                is_alive=False,
                latency_ms=-1.0,
                status_code=None,
                error=f"Timeout after {settings.TCP_PING_TIMEOUT}s",
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
