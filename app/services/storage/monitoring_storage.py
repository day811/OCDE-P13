# app/services/storage/monitoring_storage.py
"""
Monitoring storage service for PulsEvents.

Centralises all async writes to the PostgreSQL monitoring tables:
  - rag_telemetry : per-request RAG pipeline latency and retrieval quality
  - ingestor_runs : ETL job execution history

Uses the same DATABASE_URL environment variable as chainlit_storage.py
(postgresql+asyncpg://...) but opens a direct asyncpg connection, keeping
this module free of Chainlit dependencies so it can be used in both
the UI service and the ingestor job.
"""

import os
import logging
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

# ── Internal helper ────────────────────────────────────────────────────────────

def _get_pg_dsn() -> str:
    """
    Returns the raw PostgreSQL DSN from DATABASE_URL.
    asyncpg requires 'postgresql://' (not 'postgresql+asyncpg://').

    Returns:
        str: asyncpg-compatible DSN.

    Raises:
        ValueError: If DATABASE_URL is not set.
    """
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise ValueError("DATABASE_URL is required for MonitoringStorageService.")
    return url.replace("postgresql+asyncpg://", "postgresql://")


# ── Public service ─────────────────────────────────────────────────────────────

class MonitoringStorageService:
    """
    Async service writing monitoring data to PostgreSQL.

    All methods are fire-and-forget friendly: exceptions are caught and
    logged at WARNING level so a telemetry failure never disrupts the
    main request flow.

    Tables must exist before use — run migration_monitoring.sql first.
    """

    # ── RAG telemetry ──────────────────────────────────────────────────────────

    @staticmethod
    async def record_rag_telemetry(
        user_id: str,
        thread_id: str,
        condensation_latency_ms: int,
        search_latency_ms: int,
        generation_latency_ms: int,
        total_latency_ms: int,
        candidates_retrieved: int,
        candidates_after_filter: int,
    ) -> None:
        """
        Persists one RAG request's telemetry to the rag_telemetry table.

        Args:
            user_id                  (str): Authenticated user identifier.
            thread_id                (str): Chainlit conversation thread ID.
            condensation_latency_ms  (int): Duration of query condensation (ms).
            search_latency_ms        (int): Duration of Azure AI Search query (ms).
            generation_latency_ms    (int): Duration of GPT-4o token generation (ms).
            total_latency_ms         (int): End-to-end wall-clock latency (ms).
            candidates_retrieved     (int): Documents returned by Azure AI Search.
            candidates_after_filter  (int): Documents remaining after _validate_event().
        """
        try:
            conn = await asyncpg.connect(_get_pg_dsn())
            try:
                await conn.execute(
                    """
                    INSERT INTO rag_telemetry (
                        "userId",                "threadId",
                        condensation_latency_ms, search_latency_ms,
                        generation_latency_ms,   total_latency_ms,
                        candidates_retrieved,    candidates_after_filter,
                        query_had_zero_results
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    user_id,
                    thread_id,
                    condensation_latency_ms,
                    search_latency_ms,
                    generation_latency_ms,
                    total_latency_ms,
                    candidates_retrieved,
                    candidates_after_filter,
                    candidates_after_filter == 0,
                )
            finally:
                await conn.close()
        except Exception as exc:
            logger.warning("RAG telemetry write failed (non-blocking): %s", exc)

    # ── Ingestor runs ──────────────────────────────────────────────────────────

    @staticmethod
    async def record_ingestor_run(
        status: str,
        events_fetched: int,
        events_indexed: int,
        duration_seconds: float,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Persists one ETL job execution record to the ingestor_runs table.

        Args:
            status            (str):   Outcome — 'success', 'partial', or 'failed'.
            events_fetched    (int):   Total events retrieved from OpenAgenda API.
            events_indexed    (int):   Events successfully pushed to Azure AI Search.
            duration_seconds  (float): Wall-clock duration of the full run.
            error_message     (str):   Exception message if status is 'failed'.
        """
        try:
            conn = await asyncpg.connect(_get_pg_dsn())
            try:
                await conn.execute(
                    """
                    INSERT INTO ingestor_runs
                        (status, events_fetched, events_indexed,
                         duration_seconds, error_message)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    status,
                    events_fetched,
                    events_indexed,
                    duration_seconds,
                    error_message,
                )
            finally:
                await conn.close()
        except Exception as exc:
            logger.warning("Ingestor run record write failed: %s", exc)

    @staticmethod
    async def record_infrastructure_snapshot(
        bronze_bytes: int,
        silver_bytes: int,
        gold_bytes: int,
        bronze_files: int,
        silver_files: int,
        gold_files: int,
        index_document_count: int,
        index_storage_bytes: int,
    ) -> None:
        """
        Persists a point-in-time snapshot of Azure infrastructure state to PostgreSQL.
        Called once per ingestor run so Grafana can track storage and index growth.

        Args:
            bronze_bytes          (int): Total bytes across all blobs in the bronze container.
            silver_bytes          (int): Total bytes across all blobs in the silver container.
            gold_bytes            (int): Total bytes across all blobs in the gold container.
            bronze_files          (int): Number of blobs in the bronze container.
            silver_files          (int): Number of blobs in the silver container.
            gold_files            (int): Number of blobs in the gold container.
            index_document_count  (int): Total documents in the Azure AI Search index.
            index_storage_bytes   (int): Storage consumed by the index in bytes.
        """
        try:
            conn = await asyncpg.connect(_get_pg_dsn())
            try:
                await conn.execute(
                    """
                    INSERT INTO infrastructure_snapshots (
                        bronze_bytes, silver_bytes, gold_bytes,
                        bronze_files, silver_files, gold_files,
                        index_document_count, index_storage_bytes
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    bronze_bytes, silver_bytes, gold_bytes,
                    bronze_files, silver_files, gold_files,
                    index_document_count, index_storage_bytes,
                )
            finally:
                await conn.close()
        except Exception as exc:
            logger.warning("Infrastructure snapshot write failed (non-blocking): %s", exc)            