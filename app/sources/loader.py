import base64
from pathlib import Path
from typing import List, Union
import aiohttp
from app.checkers.base import NodeInfo
from app.sources.parser import NodeParser
from app.core.logger import logger
from app.config import settings


class SourceLoader:
    """Async source loader for reading node lists from files and URLs."""

    @classmethod
    async def load_from_file(cls, file_path: Union[str, Path]) -> List[NodeInfo]:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"Source file {path} not found.")
            return []

        try:
            content = path.read_text(encoding="utf-8")
            nodes = NodeParser.parse_text(content)
            logger.info(f"Loaded {len(nodes)} valid nodes from {path}")
            return nodes
        except Exception as e:
            logger.error(f"Error reading source file {path}: {e}")
            return []

    @classmethod
    async def load_from_url(cls, url: str) -> List[NodeInfo]:
        """Fetch and parse nodes from a remote HTTP/HTTPS subscription URL."""
        timeout = aiohttp.ClientTimeout(total=settings.TIMEOUT_SECONDS * 2)
        try:
            headers = {"User-Agent": "v2rayN/6.23 (Windows NT 10.0; Win64; x64) AsyncNodeChecker/1.0"}
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        raw_text = await resp.text()

                        # Check if response is Base64 encoded subscription
                        try:
                            decoded = base64.b64decode(raw_text.strip()).decode("utf-8", errors="ignore")
                            if "\n" in decoded or "://" in decoded:
                                raw_text = decoded
                        except Exception:
                            pass

                        nodes = NodeParser.parse_text(raw_text)
                        logger.info(f"Loaded {len(nodes)} nodes from URL: {url}")
                        return nodes
                    else:
                        logger.warning(f"Failed to fetch {url}, HTTP status {resp.status}")
        except Exception as e:
            logger.error(f"Error fetching subscription from {url}: {e}")
        return []

    @classmethod
    async def load_default_sources(cls) -> List[NodeInfo]:
        """Load from default configured file."""
        return await cls.load_from_file(settings.INPUT_SOURCES_FILE)
