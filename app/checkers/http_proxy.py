import asyncio
import time
import aiohttp
from app.checkers.base import BaseChecker, NodeInfo, CheckResult
from app.core.geoip import geoip_service
from app.config import settings


class HttpProxyChecker(BaseChecker):
    """HTTP and HTTPS Proxy Checker."""

    TEST_TARGETS = [
        "http://cp.cloudflare.com",
        "http://httpbin.org/ip",
        "http://www.google.com/generate_204",
    ]

    async def check(self, node: NodeInfo) -> CheckResult:
        start_time = time.perf_counter()
        geo_task = asyncio.create_task(geoip_service.lookup(node.host))

        proxy_url = f"http://{node.host}:{node.port}"
        if node.username and node.password:
            proxy_auth = aiohttp.BasicAuth(node.username, node.password)
        else:
            proxy_auth = None

        timeout = aiohttp.ClientTimeout(total=settings.TIMEOUT_SECONDS, connect=settings.TCP_PING_TIMEOUT)

        for test_url in self.TEST_TARGETS:
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    req_start = time.perf_counter()
                    async with session.get(test_url, proxy=proxy_url, proxy_auth=proxy_auth) as resp:
                        latency = (time.perf_counter() - req_start) * 1000.0
                        if resp.status in (200, 204):
                            geo = await geo_task
                            return CheckResult(
                                node=node,
                                is_alive=True,
                                latency_ms=round(latency, 2),
                                status_code=resp.status,
                                error=None,
                                geo=geo,
                                details={
                                    "target": test_url,
                                    "anonymity": "Unknown",
                                    "server": resp.headers.get("Server", "Unknown"),
                                }
                            )
            except Exception as e:
                # Try next target before failing
                last_err = str(e)
                continue

        geo = await geo_task
        return CheckResult(
            node=node,
            is_alive=False,
            latency_ms=-1.0,
            status_code=None,
            error=last_err if 'last_err' in locals() else "Connection failed",
            geo=geo,
            details={"proxy": proxy_url}
        )
