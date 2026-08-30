import asyncio
import json
from typing import Optional, List
from fastapi import APIRouter, Query, Body, HTTPException, Response
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.checkers import dispatcher, CheckResult, NodeInfo
from app.core.concurrency import runner
from app.sources.loader import SourceLoader
from app.sources.parser import NodeParser
from app.storage.repository import repository
from app.storage.exporter import NodeExporter
from app.storage.git_sync import GitSync
from app.config import settings
from app.core.logger import logger

router = APIRouter(prefix="/api")


class CheckRequest(BaseModel):
    raw_text: Optional[str] = None
    subscription_urls: Optional[List[str]] = None
    use_default_sources: bool = True
    auto_export: bool = True
    auto_git_sync: bool = False


class SingleCheckRequest(BaseModel):
    target: str


@router.get("/status")
async def get_status():
    """Service status and configuration overview."""
    return {
        "status": "online",
        "app_name": settings.APP_NAME,
        "env": settings.APP_ENV,
        "concurrency_limit": settings.MAX_CONCURRENT_CHECKS,
        "is_job_running": runner.progress.is_running,
        "current_progress": runner.progress.model_dump(),
    }


@router.get("/stats")
async def get_stats():
    """Aggregated stats from stored nodes database."""
    return await repository.get_stats()


@router.get("/nodes")
async def get_nodes(
    is_alive: Optional[bool] = Query(None, description="Filter by alive/dead status"),
    protocol: Optional[str] = Query(None, description="Filter by protocol (TCP, HTTP, SOCKS5, VLESS, etc)"),
    country_code: Optional[str] = Query(None, description="Filter by 2-letter country code"),
    max_latency: Optional[float] = Query(None, description="Filter nodes with latency <= max_latency (ms)"),
    search: Optional[str] = Query(None, description="Search keyword in IP, port, ISP, or Tag"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Retrieve filtered list of nodes."""
    nodes = await repository.get_nodes(
        is_alive=is_alive,
        protocol=protocol,
        country_code=country_code,
        max_latency=max_latency,
        search=search,
        limit=limit,
        offset=offset,
    )
    return {"count": len(nodes), "limit": limit, "offset": offset, "nodes": [n.model_dump() for n in nodes]}


@router.post("/check/single")
async def check_single(req: SingleCheckRequest):
    """Perform immediate real-time check of a single node / URI."""
    node = NodeParser.parse_line(req.target)
    if not node:
        raise HTTPException(status_code=400, detail="Invalid node or URI format")

    result = await dispatcher.check_node(node)
    await repository.upsert_node(result)
    return result.model_dump()


@router.post("/check/run")
async def start_batch_check(req: CheckRequest = Body(default_factory=CheckRequest)):
    """Initiate an async batch check in the background."""
    if runner.progress.is_running:
        raise HTTPException(status_code=409, detail="A check job is already in progress.")

    nodes: List[NodeInfo] = []

    # 1. Load from custom raw text
    if req.raw_text:
        nodes.extend(NodeParser.parse_text(req.raw_text))

    # 2. Load from subscription URLs
    if req.subscription_urls:
        for url in req.subscription_urls:
            url_nodes = await SourceLoader.load_from_url(url.strip())
            nodes.extend(url_nodes)

    # 3. Load default sources if requested or empty
    if req.use_default_sources or not nodes:
        default_nodes = await SourceLoader.load_default_sources()
        nodes.extend(default_nodes)

    # Deduplicate
    seen = set()
    unique_nodes: List[NodeInfo] = []
    for n in nodes:
        key = (n.host, n.port, n.protocol)
        if key not in seen:
            seen.add(key)
            unique_nodes.append(n)

    if not unique_nodes:
        raise HTTPException(status_code=400, detail="No valid nodes found in the provided sources.")

    async def on_complete_callback(node: NodeInfo, res: CheckResult):
        await repository.upsert_node(res)

    async def background_task():
        results = await runner.run_batch(
            items=unique_nodes,
            task_fn=dispatcher.check_node,
            on_item_complete=on_complete_callback,
        )
        if req.auto_export:
            NodeExporter.export_to_files(results, only_live=True)

        if req.auto_git_sync or settings.AUTO_GIT_COMMIT:
            GitSync.sync_output_files()

    asyncio.create_task(background_task())

    return {
        "status": "started",
        "total_nodes_queued": len(unique_nodes),
        "message": f"Started async check of {len(unique_nodes)} nodes.",
    }


@router.get("/check/progress")
async def stream_progress():
    """SSE endpoint providing real-time streaming progress of running jobs."""
    async def event_generator():
        q = runner.subscribe()
        try:
            # Initial state
            yield {
                "event": "init",
                "data": json.dumps(runner.progress.model_dump()),
            }
            while True:
                msg = await q.get()
                yield {
                    "event": msg.get("event", "message"),
                    "data": json.dumps(msg.get("data", {})),
                }
        except asyncio.CancelledError:
            pass
        finally:
            runner.unsubscribe(q)

    return EventSourceResponse(event_generator())


@router.get("/export/{export_format}")
async def export_nodes(
    export_format: str,
    only_live: bool = Query(True),
    protocol: Optional[str] = Query(None),
    country_code: Optional[str] = Query(None),
    max_latency: Optional[float] = Query(None),
):
    """Download export files in json, txt, or csv format."""
    nodes = await repository.get_nodes(
        is_alive=True if only_live else None,
        protocol=protocol,
        country_code=country_code,
        max_latency=max_latency,
        limit=10000,
    )

    fmt = export_format.lower()
    if fmt == "json":
        data = [n.model_dump() for n in nodes]
        content = json.dumps(data, indent=2, ensure_ascii=False)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=live_nodes.json"},
        )
    elif fmt == "txt":
        content = NodeExporter.get_raw_txt(nodes, only_live=only_live)
        return PlainTextResponse(
            content=content,
            headers={"Content-Disposition": "attachment; filename=live_nodes.txt"},
        )
    elif fmt == "csv":
        content = NodeExporter.get_csv_string(nodes, only_live=only_live)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=live_nodes.csv"},
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported format. Choose json, txt, or csv.")


@router.delete("/nodes")
async def clear_nodes():
    """Clear all node records from the database."""
    await repository.clear_all()
    return {"status": "cleared", "message": "All nodes cleared from database."}
