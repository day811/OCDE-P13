# scripts/test_infra_snapshot.py
"""Quick script to test infrastructure metric collection and PostgreSQL write."""

import asyncio
import dotenv
dotenv.load_dotenv()

from ingest_pipeline import _collect_infrastructure_metrics
from app.services.storage.monitoring_storage import MonitoringStorageService

async def main():
    print("Collecting metrics...")
    infra = _collect_infrastructure_metrics()
    for k, v in infra.items():
        print(f"  {k}: {v}")

    print("\nWriting snapshot to PostgreSQL...")
    await MonitoringStorageService.record_infrastructure_snapshot(**infra)
    print("Done — check infrastructure_snapshots table in Grafana.")

asyncio.run(main())