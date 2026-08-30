import csv
import io
import json
from pathlib import Path
from typing import List, Optional
from app.checkers.base import CheckResult
from app.config import settings
from app.core.logger import logger


class NodeExporter:
    """Exports validated nodes into JSON, TXT and CSV formats."""

    @classmethod
    def export_to_files(
        cls,
        results: List[CheckResult],
        output_dir: Optional[Path] = None,
        only_live: bool = True,
    ) -> dict[str, Path]:
        """Save results to JSON, TXT, and CSV in output_dir."""
        target_dir = output_dir or settings.OUTPUT_DIR
        target_dir.mkdir(parents=True, exist_ok=True)

        filtered = [r for r in results if r.is_alive] if only_live else results

        json_path = target_dir / "live_nodes.json"
        txt_path = target_dir / "live_nodes.txt"
        csv_path = target_dir / "live_nodes.csv"

        # 1. JSON Export
        json_data = [r.model_dump() for r in filtered]
        json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")

        # 2. TXT Export (clean raw inputs/endpoints)
        txt_lines = [r.node.raw_input for r in filtered]
        txt_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")

        # 3. CSV Export
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow([
            "Endpoint", "Protocol", "Latency (ms)", "Is Alive", "Country",
            "Country Code", "City", "ISP", "ASN", "Tag", "Raw Input", "Checked At"
        ])
        for r in filtered:
            writer.writerow([
                r.node.endpoint,
                r.node.protocol.value,
                r.latency_ms,
                "YES" if r.is_alive else "NO",
                r.geo.country,
                r.geo.country_code,
                r.geo.city,
                r.geo.isp,
                r.geo.asn,
                r.node.tag or "",
                r.node.raw_input,
                r.checked_at,
            ])
        csv_path.write_text(csv_buffer.getvalue(), encoding="utf-8")

        logger.info(f"Exported {len(filtered)} nodes to {target_dir}")
        return {
            "json": json_path,
            "txt": txt_path,
            "csv": csv_path,
        }

    @classmethod
    def get_raw_txt(cls, results: List[CheckResult], only_live: bool = True) -> str:
        """Return raw TXT string for API responses."""
        filtered = [r for r in results if r.is_alive] if only_live else results
        return "\n".join(r.node.raw_input for r in filtered)

    @classmethod
    def get_csv_string(cls, results: List[CheckResult], only_live: bool = True) -> str:
        """Return CSV formatted string."""
        filtered = [r for r in results if r.is_alive] if only_live else results
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Endpoint", "Protocol", "Latency_MS", "Alive", "Country", "City", "ISP", "Raw_Input"])
        for r in filtered:
            writer.writerow([
                r.node.endpoint,
                r.node.protocol.value,
                r.latency_ms,
                r.is_alive,
                r.geo.country,
                r.geo.city,
                r.geo.isp,
                r.node.raw_input
            ])
        return output.getvalue()
