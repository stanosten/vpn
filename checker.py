#!/usr/bin/env python3
"""
⚡ Async IP & CIDR Network Checker
High-performance asynchronous IPv4 scanner using standard library only.
"""

import argparse
import asyncio
import ipaddress
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional, Set, Tuple

# ==============================================================================
# Default Configuration
# ==============================================================================
DEFAULT_TARGET_PORT: int = 443
DEFAULT_CONCURRENCY_LIMIT: int = 400
DEFAULT_TIMEOUT_SECONDS: float = 1.2
DEFAULT_SOURCES_FILE: Path = Path("sources.txt")
DEFAULT_OUTPUT_FILE: Path = Path("working-ips.txt")
DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 AsyncIPChecker/1.0"
)

# Regular expression matching IPv4 addresses and CIDR notations
IP_OR_CIDR_REGEX = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)(?:/\d{1,2})?\b"
)


def init_console_encoding() -> None:
    """Ensure safe UTF-8 console output across different platforms."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def load_source_urls(sources_path: Path) -> List[str]:
    """Read URLs from the sources file, skipping empty lines and comments."""
    if not sources_path.exists():
        print(f"[!] Sources file '{sources_path}' not found.")
        return []

    urls: List[str] = []
    with open(sources_path, "r", encoding="utf-8") as f:
        for line in f:
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("#"):
                urls.append(cleaned)
    return urls


def fetch_url_sync(url: str, user_agent: str) -> str:
    """Download text content from a raw URL with a custom User-Agent."""
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            content_bytes = resp.read()
            return content_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[x] Error downloading source {url}: {e}")
        return ""


async def fetch_all_sources(urls: List[str], user_agent: str) -> List[str]:
    """Fetch all source URLs concurrently."""
    tasks = [asyncio.to_thread(fetch_url_sync, url, user_agent) for url in urls]
    results = await asyncio.gather(*tasks)
    return [res for res in results if res]


def extract_and_validate_ips(raw_texts: List[str]) -> List[str]:
    """
    Extract IPv4 addresses and CIDR networks from raw texts.
    Validates addresses and filters out private, multicast, loopback, and reserved ranges.
    Expands CIDR ranges safely (limiting subnets larger than /24 to the first host).
    """
    unique_ips: Set[str] = set()

    for text in raw_texts:
        matches = IP_OR_CIDR_REGEX.findall(text)
        for match in matches:
            try:
                if "/" in match:
                    # CIDR network
                    net = ipaddress.IPv4Network(match, strict=False)
                    if (
                        net.is_private
                        or net.is_multicast
                        or net.is_reserved
                        or net.is_loopback
                        or net.is_link_local
                        or net.is_unspecified
                    ):
                        continue

                    # If subnet is larger than /24 (prefix < 24), take only the first usable host to prevent OOM
                    if net.prefixlen < 24:
                        first_host = next(net.hosts(), None)
                        if first_host:
                            unique_ips.add(str(first_host))
                    elif net.prefixlen == 32:
                        unique_ips.add(str(net.network_address))
                    elif net.prefixlen == 31:
                        # RFC 3021: point-to-point links have 2 addresses
                        unique_ips.add(str(net.network_address))
                        unique_ips.add(str(net.broadcast_address))
                    else:
                        for host in net.hosts():
                            unique_ips.add(str(host))
                else:
                    # Single IPv4 address
                    ip = ipaddress.IPv4Address(match)
                    if (
                        ip.is_private
                        or ip.is_multicast
                        or ip.is_reserved
                        or ip.is_loopback
                        or ip.is_link_local
                        or ip.is_unspecified
                    ):
                        continue
                    unique_ips.add(str(ip))
            except ValueError:
                continue

    return sorted(list(unique_ips))


async def check_ip(
    ip: str, port: int, timeout: float, semaphore: asyncio.Semaphore
) -> Optional[Tuple[str, float]]:
    """
    Asynchronously test TCP connection to the IP and port.
    Returns (ip, latency_ms) on success, or None on failure/timeout.
    """
    async with semaphore:
        start_time = time.perf_counter()
        try:
            connect_coro = asyncio.open_connection(ip, port)
            reader, writer = await asyncio.wait_for(connect_coro, timeout=timeout)
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

            return (ip, round(latency_ms, 2))
        except (asyncio.TimeoutError, OSError, Exception):
            return None


async def scan_all_ips(
    ips: List[str], port: int, concurrency: int, timeout: float
) -> List[Tuple[str, float]]:
    """Scan all candidate IPs concurrently with rate limiting and progress reporting."""
    semaphore = asyncio.Semaphore(concurrency)
    total = len(ips)
    working_nodes: List[Tuple[str, float]] = []
    completed = 0
    start_time = time.perf_counter()

    async def worker(ip: str) -> None:
        nonlocal completed
        res = await check_ip(ip, port, timeout, semaphore)
        completed += 1
        if res is not None:
            working_nodes.append(res)

        # Periodic progress report
        if completed % 250 == 0 or completed == total:
            percent = (completed / total) * 100.0
            elapsed = time.perf_counter() - start_time
            print(
                f"[*] Progress: {completed}/{total} ({percent:.1f}%) | "
                f"Active: {len(working_nodes)} | Elapsed: {elapsed:.1f}s"
            )

    tasks = [asyncio.create_task(worker(ip)) for ip in ips]
    await asyncio.gather(*tasks)
    return working_nodes


def save_results(results: List[Tuple[str, float]], output_path: Path) -> None:
    """Sort responsive IPs by latency (ascending) and save to output file."""
    results.sort(key=lambda x: x[1])
    lines = [ip for ip, _ in results]
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def parse_arguments() -> argparse.Namespace:
    """Parse optional command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Async IP & CIDR Network Checker (Python stdlib)"
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=DEFAULT_SOURCES_FILE,
        help=f"Path to file with source URLs (default: {DEFAULT_SOURCES_FILE})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help=f"Path to output file for working IPs (default: {DEFAULT_OUTPUT_FILE})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_TARGET_PORT,
        help=f"Target TCP port to probe (default: {DEFAULT_TARGET_PORT})",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY_LIMIT,
        help=f"Maximum concurrent connections (default: {DEFAULT_CONCURRENCY_LIMIT})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Connection timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}s)",
    )
    return parser.parse_args()


async def async_main(args: argparse.Namespace) -> None:
    init_console_encoding()
    print("=" * 65)
    print("⚡ Async IP & CIDR Network Checker (StdLib Edition)")
    print(
        f"Target Port : {args.port} | Concurrency : {args.concurrency} | "
        f"Timeout : {args.timeout}s"
    )
    print("=" * 65)

    # 1. Load source URLs
    urls = load_source_urls(args.sources)
    if not urls:
        print(f"[!] No valid URLs found in {args.sources}. Exiting.")
        sys.exit(1)

    print(f"[*] Loaded {len(urls)} source URL(s) from {args.sources}...")

    # 2. Fetch raw contents
    raw_texts = await fetch_all_sources(urls, DEFAULT_USER_AGENT)
    print(f"[*] Successfully downloaded data from {len(raw_texts)}/{len(urls)} sources.")

    # 3. Parse and filter IPs
    candidate_ips = extract_and_validate_ips(raw_texts)
    print(f"[*] Extracted and validated {len(candidate_ips)} unique public IPv4 addresses.")

    if not candidate_ips:
        print("[!] No candidate IPs found to scan.")
        sys.exit(0)

    # 4. Asynchronous checking
    print(f"[*] Starting high-speed scan on port {args.port}...")
    scan_start = time.perf_counter()
    working_nodes = await scan_all_ips(
        ips=candidate_ips,
        port=args.port,
        concurrency=args.concurrency,
        timeout=args.timeout,
    )
    scan_duration = time.perf_counter() - scan_start

    # 5. Export results and print summary
    save_results(working_nodes, args.output)

    print("\n" + "=" * 65)
    print(" SCAN RESULTS SUMMARY")
    print("=" * 65)
    print(f"Total Candidate IPs Scanned : {len(candidate_ips)}")
    print(f"Active Working Nodes (TCP OK): {len(working_nodes)}")
    print(f"Total Scan Duration          : {scan_duration:.2f} seconds")
    if working_nodes:
        avg_lat = sum(lat for _, lat in working_nodes) / len(working_nodes)
        min_lat = min(lat for _, lat in working_nodes)
        max_lat = max(lat for _, lat in working_nodes)
        print(f"Latency Range (RTT)          : {min_lat:.1f}ms - {max_lat:.1f}ms (Avg: {avg_lat:.1f}ms)")
        print("\nTop 5 fastest IPs:")
        for ip, lat in working_nodes[:5]:
            print(f"  -> {ip:<18} | {lat} ms")
    print(f"\n[+] Saved list of active IPs to: {args.output.resolve()}")
    print("=" * 65)


def main() -> None:
    args = parse_arguments()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
