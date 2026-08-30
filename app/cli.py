import argparse
import asyncio
import sys
from pathlib import Path

from app.config import settings
from app.checkers import dispatcher, NodeInfo, CheckResult
from app.core.concurrency import AsyncRunner
from app.sources.loader import SourceLoader
from app.sources.parser import NodeParser
from app.storage.repository import repository
from app.storage.exporter import NodeExporter
from app.storage.git_sync import GitSync
from app.core.logger import logger


async def run_check_cli(args):
    """Execute batch check from CLI."""
    settings.init_directories()
    await repository.init_db()

    nodes = []

    # 1. Load from file
    if args.file:
        file_nodes = await SourceLoader.load_from_file(args.file)
        nodes.extend(file_nodes)
    elif not args.url:
        default_nodes = await SourceLoader.load_default_sources()
        nodes.extend(default_nodes)

    # 2. Load from URL
    if args.url:
        url_nodes = await SourceLoader.load_from_url(args.url)
        nodes.extend(url_nodes)

    # Deduplicate
    seen = set()
    unique_nodes = []
    for n in nodes:
        key = (n.host, n.port, n.protocol)
        if key not in seen:
            seen.add(key)
            unique_nodes.append(n)

    if not unique_nodes:
        logger.error("No valid nodes to check.")
        sys.exit(1)

    logger.info(f"Starting check for {len(unique_nodes)} unique nodes (Concurrency: {args.concurrency})...")

    cli_runner = AsyncRunner(max_concurrency=args.concurrency)

    async def on_complete(node: NodeInfo, res: CheckResult):
        await repository.upsert_node(res)
        status_symbol = "+" if res.is_alive else "-"
        lat = f"{res.latency_ms}ms" if res.is_alive else "DEAD"
        logger.info(f"[{status_symbol}] {res.geo.flag} {node.protocol.value:<8} {node.endpoint:<22} | {lat:<8} | {res.geo.country}")

    results = await cli_runner.run_batch(
        items=unique_nodes,
        task_fn=dispatcher.check_node,
        on_item_complete=on_complete,
    )

    out_dir = Path(args.output_dir) if args.output_dir else settings.OUTPUT_DIR
    files = NodeExporter.export_to_files(results, output_dir=out_dir, only_live=not args.all)
    logger.info(f"Results exported: JSON -> {files['json']}, TXT -> {files['txt']}, CSV -> {files['csv']}")

    if args.git or settings.AUTO_GIT_COMMIT:
        logger.info("Executing Git Auto-Commit & Push...")
        GitSync.sync_output_files()


async def run_stats_cli():
    """Print stats from DB."""
    await repository.init_db()
    stats = await repository.get_stats()
    print("\n" + "=" * 45)
    print("      ASYNC NODE CHECKER STATISTICS")
    print("=" * 45)
    print(f"Total Nodes in DB : {stats['total_nodes']}")
    print(f"Active Live Nodes : {stats['live_nodes']}")
    print(f"Dead / Offline    : {stats['dead_nodes']}")
    print(f"Average Latency   : {stats['avg_latency_ms']} ms")
    print("-" * 45)
    print("Protocols Breakdown:")
    for proto, count in stats["protocols"].items():
        print(f"  - {proto:<12}: {count}")
    print("-" * 45)
    print("Top Countries:")
    for code, data in stats["top_countries"].items():
        print(f"  {data['flag']} {data['name']:<18} ({code}): {data['count']}")
    print("=" * 45 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Async IP, Proxy & VPN Node Checker CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Check command
    check_parser = subparsers.add_parser("check", help="Run batch validation of nodes")
    check_parser.add_argument("-f", "--file", help="Input file path containing nodes/proxies")
    check_parser.add_argument("-u", "--url", help="Subscription URL to fetch nodes from")
    check_parser.add_argument("-c", "--concurrency", type=int, default=settings.MAX_CONCURRENT_CHECKS, help="Max concurrency")
    check_parser.add_argument("-o", "--output-dir", help="Target output directory")
    check_parser.add_argument("--git", action="store_true", help="Auto-commit and push results to git")
    check_parser.add_argument("--all", action="store_true", help="Include dead nodes in export files")

    # Stats command
    subparsers.add_parser("stats", help="Display aggregated database stats")

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Launch FastAPI Web Dashboard & REST API")
    serve_parser.add_argument("--host", default=settings.HOST, help="Host to bind")
    serve_parser.add_argument("-p", "--port", type=int, default=settings.PORT, help="Port to bind")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()

    if args.command == "check":
        asyncio.run(run_check_cli(args))
    elif args.command == "stats":
        asyncio.run(run_stats_cli())
    elif args.command == "serve":
        import uvicorn
        uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
