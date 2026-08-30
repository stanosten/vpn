import datetime
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from app.core.geoip import GeoLocation


class ProtocolType(str, Enum):
    RAW_TCP = "TCP"
    HTTP_PROXY = "HTTP"
    HTTPS_PROXY = "HTTPS"
    SOCKS4 = "SOCKS4"
    SOCKS5 = "SOCKS5"
    SHADOWSOCKS = "Shadowsocks"
    VLESS = "VLESS"
    VMESS = "VMess"
    WIREGUARD = "WireGuard"
    UNKNOWN = "UNKNOWN"


class NodeInfo(BaseModel):
    raw_input: str
    host: str
    port: int
    protocol: ProtocolType = ProtocolType.RAW_TCP
    tag: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    uuid: Optional[str] = None
    extra_params: Dict[str, Any] = Field(default_factory=dict)

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"


class CheckResult(BaseModel):
    node: NodeInfo
    is_alive: bool
    latency_ms: float = -1.0
    status_code: Optional[int] = None
    error: Optional[str] = None
    geo: GeoLocation = Field(default_factory=GeoLocation)
    checked_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    details: Dict[str, Any] = Field(default_factory=dict)


class BaseChecker(ABC):
    """Abstract base class for all protocol checkers."""

    @abstractmethod
    async def check(self, node: NodeInfo) -> CheckResult:
        """Perform non-blocking health check against the given node."""
        pass
