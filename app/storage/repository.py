import json
from typing import List, Optional, Dict, Any
import aiosqlite
from app.config import settings
from app.checkers.base import CheckResult, NodeInfo, ProtocolType
from app.core.geoip import GeoLocation
from app.core.logger import logger


class NodeRepository:
    """Async SQLite storage for checked nodes and historical metrics."""

    def __init__(self, db_path=settings.DB_PATH):
        self.db_path = str(db_path)

    async def init_db(self) -> None:
        """Create database tables and indices if they do not exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    endpoint TEXT PRIMARY KEY,
                    raw_input TEXT,
                    host TEXT,
                    port INTEGER,
                    protocol TEXT,
                    tag TEXT,
                    is_alive INTEGER,
                    latency_ms REAL,
                    status_code INTEGER,
                    error TEXT,
                    country TEXT,
                    country_code TEXT,
                    flag TEXT,
                    city TEXT,
                    isp TEXT,
                    asn TEXT,
                    checked_at TEXT,
                    check_count INTEGER DEFAULT 1,
                    success_count INTEGER DEFAULT 0,
                    details_json TEXT
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_nodes_alive ON nodes(is_alive)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_nodes_proto ON nodes(protocol)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_nodes_country ON nodes(country_code)")
            await db.commit()
            logger.info("SQLite Node repository initialized.")

    async def upsert_node(self, result: CheckResult) -> None:
        """Insert or update a node check result."""
        node = result.node
        geo = result.geo
        details_json = json.dumps(result.details)
        is_alive_int = 1 if result.is_alive else 0

        async with aiosqlite.connect(self.db_path) as db:
            # Check existing to update success counts
            async with db.execute("SELECT check_count, success_count FROM nodes WHERE endpoint = ?", (node.endpoint,)) as cur:
                row = await cur.fetchone()

            if row:
                check_count = row[0] + 1
                success_count = row[1] + (1 if result.is_alive else 0)
                await db.execute("""
                    UPDATE nodes SET
                        raw_input = ?, host = ?, port = ?, protocol = ?, tag = ?,
                        is_alive = ?, latency_ms = ?, status_code = ?, error = ?,
                        country = ?, country_code = ?, flag = ?, city = ?, isp = ?, asn = ?,
                        checked_at = ?, check_count = ?, success_count = ?, details_json = ?
                    WHERE endpoint = ?
                """, (
                    node.raw_input, node.host, node.port, node.protocol.value, node.tag,
                    is_alive_int, result.latency_ms, result.status_code, result.error,
                    geo.country, geo.country_code, geo.flag, geo.city, geo.isp, geo.asn,
                    result.checked_at, check_count, success_count, details_json,
                    node.endpoint
                ))
            else:
                await db.execute("""
                    INSERT INTO nodes (
                        endpoint, raw_input, host, port, protocol, tag,
                        is_alive, latency_ms, status_code, error,
                        country, country_code, flag, city, isp, asn,
                        checked_at, check_count, success_count, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    node.endpoint, node.raw_input, node.host, node.port, node.protocol.value, node.tag,
                    is_alive_int, result.latency_ms, result.status_code, result.error,
                    geo.country, geo.country_code, geo.flag, geo.city, geo.isp, geo.asn,
                    result.checked_at, 1, (1 if result.is_alive else 0), details_json
                ))
            await db.commit()

    async def get_nodes(
        self,
        is_alive: Optional[bool] = None,
        protocol: Optional[str] = None,
        country_code: Optional[str] = None,
        max_latency: Optional[float] = None,
        search: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[CheckResult]:
        """Fetch nodes matching given filter criteria."""
        query = "SELECT * FROM nodes WHERE 1=1"
        params: List[Any] = []

        if is_alive is not None:
            query += " AND is_alive = ?"
            params.append(1 if is_alive else 0)

        if protocol:
            query += " AND protocol = ?"
            params.append(protocol)

        if country_code:
            query += " AND country_code = ?"
            params.append(country_code.upper())

        if max_latency is not None and max_latency > 0:
            query += " AND latency_ms > 0 AND latency_ms <= ?"
            params.append(max_latency)

        if search:
            query += " AND (endpoint LIKE ? OR tag LIKE ? OR isp LIKE ? OR country LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term, term])

        query += " ORDER BY is_alive DESC, latency_ms ASC, checked_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        results: List[CheckResult] = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    try:
                        proto_enum = ProtocolType(row["protocol"])
                    except Exception:
                        proto_enum = ProtocolType.UNKNOWN

                    details = {}
                    if row["details_json"]:
                        try:
                            details = json.loads(row["details_json"])
                        except Exception:
                            pass

                    node = NodeInfo(
                        raw_input=row["raw_input"],
                        host=row["host"],
                        port=row["port"],
                        protocol=proto_enum,
                        tag=row["tag"],
                    )
                    geo = GeoLocation(
                        country=row["country"] or "Unknown",
                        country_code=row["country_code"] or "UN",
                        flag=row["flag"] or "🌐",
                        city=row["city"] or "Unknown",
                        isp=row["isp"] or "Unknown",
                        asn=row["asn"] or "Unknown",
                    )
                    results.append(
                        CheckResult(
                            node=node,
                            is_alive=bool(row["is_alive"]),
                            latency_ms=row["latency_ms"],
                            status_code=row["status_code"],
                            error=row["error"],
                            geo=geo,
                            checked_at=row["checked_at"],
                            details=details,
                        )
                    )
        return results

    async def get_stats(self) -> Dict[str, Any]:
        """Aggregate statistics across all stored nodes."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM nodes") as cur:
                total = (await cur.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM nodes WHERE is_alive = 1") as cur:
                live = (await cur.fetchone())[0]

            async with db.execute("SELECT AVG(latency_ms) FROM nodes WHERE is_alive = 1 AND latency_ms > 0") as cur:
                avg_lat = (await cur.fetchone())[0] or 0.0

            # Protocols breakdown
            protocols = {}
            async with db.execute("SELECT protocol, COUNT(*) FROM nodes GROUP BY protocol") as cur:
                for row in await cur.fetchall():
                    protocols[row[0]] = row[1]

            # Countries breakdown
            countries = {}
            async with db.execute("SELECT country_code, flag, country, COUNT(*) as c FROM nodes WHERE is_alive = 1 GROUP BY country_code ORDER BY c DESC LIMIT 10") as cur:
                for row in await cur.fetchall():
                    countries[row[0]] = {"flag": row[1], "name": row[2], "count": row[3]}

        return {
            "total_nodes": total,
            "live_nodes": live,
            "dead_nodes": total - live,
            "avg_latency_ms": round(avg_lat, 1),
            "protocols": protocols,
            "top_countries": countries,
        }

    async def clear_all(self) -> None:
        """Clear all records from database."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM nodes")
            await db.commit()


repository = NodeRepository()
