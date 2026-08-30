import asyncio
import time
import aiohttp
from typing import Optional, Dict, Any
from pydantic import BaseModel
from app.core.logger import logger
from app.config import settings


class GeoLocation(BaseModel):
    country: str = "Unknown"
    country_code: str = "UN"
    flag: str = "🌐"
    city: str = "Unknown"
    region: str = "Unknown"
    isp: str = "Unknown"
    org: str = "Unknown"
    asn: str = "Unknown"
    is_private: bool = False


def country_code_to_flag(code: Optional[str]) -> str:
    """Convert ISO-3166-1 alpha-2 country code to emoji flag."""
    if not code or len(code) != 2:
        return "🌐"
    code = code.upper()
    try:
        return chr(127397 + ord(code[0])) + chr(127397 + ord(code[1]))
    except Exception:
        return "🌐"


def is_private_ip(ip: str) -> bool:
    """Check if an IP address belongs to a private/local range."""
    if not ip:
        return True
    if ip.startswith(("127.", "10.", "192.168.", "169.254.", "0.", "localhost", "::1")):
        return True
    if ip.startswith("172."):
        parts = ip.split(".")
        if len(parts) >= 2 and parts[1].isdigit():
            second_octet = int(parts[1])
            if 16 <= second_octet <= 31:
                return True
    return False


class GeoIPService:
    """Async GeoIP enrichment service with in-memory caching."""

    def __init__(self, cache_ttl: int = settings.GEOIP_CACHE_TTL):
        self.cache: Dict[str, tuple[float, GeoLocation]] = {}
        self.cache_ttl = cache_ttl
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(15)  # Limit concurrent GeoIP requests

    async def lookup(self, ip: str, session: Optional[aiohttp.ClientSession] = None) -> GeoLocation:
        """Fetch GeoIP details for a given IP with caching."""
        if not settings.ENABLE_GEOIP or not ip:
            return GeoLocation()

        if is_private_ip(ip):
            return GeoLocation(
                country="Private Network",
                country_code="LOCAL",
                flag="🏠",
                city="Localhost",
                isp="Local Loopback / Private Range",
                is_private=True,
            )

        now = time.time()
        # Check cache
        if ip in self.cache:
            cached_time, data = self.cache[ip]
            if now - cached_time < self.cache_ttl:
                return data

        async with self._semaphore:
            # Re-check cache inside lock
            if ip in self.cache:
                cached_time, data = self.cache[ip]
                if now - cached_time < self.cache_ttl:
                    return data

            location = await self._fetch_from_api(ip, session)
            self.cache[ip] = (now, location)
            return location

    async def _fetch_from_api(self, ip: str, session: Optional[aiohttp.ClientSession] = None) -> GeoLocation:
        url = f"http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,regionName,city,isp,org,as,query"
        close_session = False
        if session is None:
            session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4.0))
            close_session = True

        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "success":
                        code = data.get("countryCode", "UN")
                        return GeoLocation(
                            country=data.get("country", "Unknown"),
                            country_code=code,
                            flag=country_code_to_flag(code),
                            city=data.get("city", "Unknown"),
                            region=data.get("regionName", "Unknown"),
                            isp=data.get("isp", "Unknown"),
                            org=data.get("org", "Unknown"),
                            asn=data.get("as", "Unknown"),
                            is_private=False,
                        )
        except Exception as e:
            logger.debug(f"GeoIP lookup failed for {ip}: {e}")
        finally:
            if close_session and not session.closed:
                await session.close()

        return GeoLocation()


geoip_service = GeoIPService()
