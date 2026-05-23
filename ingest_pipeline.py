# ingest_pipeline.py — monitoring wrapper
"""
Ingestion pipeline entry point with execution monitoring.
Run metadata is persisted to PostgreSQL (ingestor_runs) on every execution.
"""

import os
import asyncio
import time
import dotenv
from azure.storage.blob import BlobServiceClient
from azure.search.documents.indexes import SearchIndexClient
from azure.core.credentials import AzureKeyCredential
from app.services.ingestion_service import IngestionService
from app.services.storage.monitoring_storage import MonitoringStorageService
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

logger = logging.getLogger(__name__)

dotenv.load_dotenv()

def _collect_infrastructure_metrics() -> dict:
    """
    Queries Azure Blob Storage and Azure AI Search for current infrastructure state.
    Runs synchronously — called from the ingestor job after pipeline completion.

    Returns:
        dict: Keys matching the infrastructure_snapshots table columns.
              Returns zeros on any failure to avoid blocking the job.
    """
    metrics = {
        "bronze_bytes": 0, "silver_bytes": 0, "gold_bytes": 0,
        "bronze_files": 0, "silver_files": 0, "gold_files": 0,
        "index_document_count": 0, "index_storage_bytes": 0,
    }

    # ── Blob Storage ──────────────────────────────────────────────────────────
    try:
        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        blob_service = BlobServiceClient.from_connection_string(conn_str)

        for layer in ("bronze", "silver", "gold"):
            container_client = blob_service.get_container_client(layer)
            total_bytes = 0
            total_files = 0
            for blob in container_client.list_blobs():
                total_bytes += blob.size or 0
                total_files += 1
            metrics[f"{layer}_bytes"] = total_bytes
            metrics[f"{layer}_files"] = total_files

        logger.info(
            "Blob snapshot — bronze:%d silver:%d gold:%d files",
            metrics["bronze_files"], metrics["silver_files"], metrics["gold_files"]
        )
    except Exception as exc:
        logger.warning("Blob Storage metric collection failed: %s", exc)

    # ── Azure AI Search index stats ───────────────────────────────────────────
    try:
        index_client = SearchIndexClient(
            endpoint=os.getenv("AZURE_SEARCH_ENDPOINT", ""),
            credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_API_KEY", ""))
        )
        index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "puls-events-index")
        stats = index_client.get_index_statistics(index_name)

        metrics["index_document_count"] = stats.document_count or 0
        metrics["index_storage_bytes"]  = stats.storage_size   or 0

        logger.info(
            "Index snapshot — docs:%d storage:%.1f MB",
            metrics["index_document_count"],
            metrics["index_storage_bytes"] / 1_048_576
        )
    except Exception as exc:
        logger.warning("Azure AI Search metric collection failed: %s", exc)

    return metrics


async def main() -> None:
    start = time.monotonic()
    events_fetched = 0
    events_indexed = 0
    service = None

    try:
        service = IngestionService()
        result = await service.run()

        logger.info("=== service.run() COMPLETE — result: %s ===", result)

        stats = result if isinstance(result, dict) else getattr(service, "stats", {})
        logger.info("=== stats resolved: %s ===", stats)

        events_fetched = stats.get("total_raw", 0)
        events_indexed = stats.get("indexed", 0)

        logger.info(
            "=== BEFORE record_ingestor_run — fetched=%d indexed=%d ===",
            events_fetched, events_indexed
        )

        duration = time.monotonic() - start
        status = "success" if events_indexed > 0 else "partial"
        await MonitoringStorageService.record_ingestor_run(
            status=status,
            events_fetched=events_fetched,
            events_indexed=events_indexed,
            duration_seconds=round(duration, 2),
        )
        logger.info("=== AFTER record_ingestor_run — status=%s ===", status)

    except Exception as exc:
        logger.exception("=== EXCEPTION in main(): %s ===", exc)
        duration = time.monotonic() - start
        await MonitoringStorageService.record_ingestor_run(
            status="failed",
            events_fetched=service.stats.get("total_raw", 0) if service else 0,
            events_indexed=0,
            duration_seconds=round(duration, 2),
            error_message=str(exc),
        )
        raise

    finally:
        logger.info("=== ENTERING FINALLY BLOCK ===")
        infra = _collect_infrastructure_metrics()
        logger.info("=== infra metrics collected: %s ===", infra)
        await MonitoringStorageService.record_infrastructure_snapshot(**infra)
        logger.info("=== FINALLY BLOCK COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(main())