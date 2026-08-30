from typing import Dict
from app.checkers.base import BaseChecker, NodeInfo, CheckResult, ProtocolType
from app.checkers.ip_port import IPPortChecker
from app.checkers.http_proxy import HttpProxyChecker
from app.checkers.socks_proxy import SocksProxyChecker
from app.checkers.vpn_node import VPNNodeChecker


class CheckerDispatcher:
    """Routes nodes to the appropriate protocol checker."""

    def __init__(self):
        self.tcp_checker = IPPortChecker()
        self.http_checker = HttpProxyChecker()
        self.socks_checker = SocksProxyChecker()
        self.vpn_checker = VPNNodeChecker()

    async def check_node(self, node: NodeInfo) -> CheckResult:
        checker = self._get_checker(node.protocol)
        return await checker.check(node)

    def _get_checker(self, protocol: ProtocolType) -> BaseChecker:
        if protocol in (ProtocolType.HTTP_PROXY, ProtocolType.HTTPS_PROXY):
            return self.http_checker
        elif protocol in (ProtocolType.SOCKS4, ProtocolType.SOCKS5):
            return self.socks_checker
        elif protocol in (ProtocolType.SHADOWSOCKS, ProtocolType.VLESS, ProtocolType.VMESS, ProtocolType.WIREGUARD):
            return self.vpn_checker
        else:
            return self.tcp_checker


dispatcher = CheckerDispatcher()
