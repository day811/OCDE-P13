import os
import json
import logging
import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from app.services.processor import EventProcessor
from app.services.vector_store import VectorStoreService
from app.services.storage.storage_factory import StorageFactory

logger = logging.getLogger(__name__)

class IngestionService:
    """
    Unified Ingestion Service handling both Local (Occitanie) and Azure (National).
    Uses StorageFactory for persistence and implements the 90% reduction strategy.
    """

    def __init__(self):
        self.env = os.getenv("ENV", "LOCAL").upper()
        self.storage = StorageFactory.get_storage()
        self.processor = EventProcessor()
        self.vector_store = VectorStoreService()
        
        # ODS Configuration
        self.base_url = os.getenv("OPENAGENDA_URL", "")
        self.page_size = 100
        self.batch_limit = 10000 # Max records to check per session
        
        # Containers/Folders names
        self.container_data = "bronze" if self.env == "AZURE" else "bronze"
        self.container_settings = "settings"
        self.manifest_file = "ingestion_manifest.json"

        self.today = datetime.now().date()
        self.stats = {"total_raw": 0, "indexed": 0, "skipped": 0}

    def _is_upcoming(self, event_metadata: Dict[str, Any]) -> bool:
        """
        Implements the 90% reduction strategy for the Search Index (Gold).
        Logic: Only keep events that haven't ended yet.
        """
        # If National mode isn't strictly required to filter, 
        # we can toggle this via ENV
        if self.env != "AZURE":
            return True

        end_date_str = event_metadata.get("lastdate_with_occurrence")
        if not end_date_str:
            return True
        try:
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00')).date()
            return end_date >= self.today
        except (ValueError, TypeError):
            return True

    def _get_manifest(self) -> Dict[str, Any]:
        """ Retrieves the high watermark from the configured storage. """
        data = self.storage.download_json(self.container_settings, self.manifest_file)
        if data:
            return data
        
        # Default: 13 months ago
        start_date = datetime.now() - timedelta(days=13 * 30)
        return {
            "last_updated_at": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_processed": 0
        }

    def fetch_batch_with_retry(self, after_ts: str, offset: int, max_retries: int = 5) -> List[Dict[str, Any]]:
        """
        Fetches a page of records with an exponential backoff strategy 
        to handle HTTP 429 (Rate Limiting) gracefully.
        """
        geo_filter = 'location_countrycode = "FR"' if self.env == "AZURE" else 'location_region = "Occitanie"'
        
        params = {
            "where": f'updatedat >= "{after_ts}" AND {geo_filter}', # [cite: 180]
            "order_by": "updatedat ASC",
            "limit": self.page_size,
            "offset": offset
        }

        retries = 0
        wait_time = 2  # Initial wait in seconds

        while retries < max_retries:
            try:
                response = requests.get(self.base_url, params=params, timeout=30)
                
                if response.status_code == 200:
                    return response.json().get('results', [])
                
                if response.status_code == 429:
                    logger.warning(f"Rate limit hit (429). Retrying in {wait_time}s... (Attempt {retries+1}/{max_retries})")
                    time.sleep(wait_time)
                    retries += 1
                    wait_time *= 2  # Exponentially increase wait
                    continue
                
                response.raise_for_status() # Handle other HTTP errors [cite: 181]

            except requests.exceptions.RequestException as e:
                logger.error(f"Network error: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                retries += 1
                wait_time *= 2

        logger.error(f"Max retries reached for offset {offset}. Skipping batch.")
        return []

    async def run(self, max_records: Optional[int] = None):
        """ Executes the incremental ingestion pipeline. """
        manifest = self._get_manifest()
        current_ts = manifest["last_updated_at"]
        total_session = 0
        
        logger.info(f"Starting ingestion in {self.env} mode from {current_ts}")

        keep_running = True
        while keep_running:
            # We process by offset windows to handle ODS pagination
            for offset in range(0, self.batch_limit, self.page_size):
                raw_events = self.fetch_batch(current_ts, offset)
                
                if not raw_events:
                    keep_running = False
                    break

                # 1. Archive to Bronze (Cloud or Local)
                batch_name = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{offset}.json"
                self.storage.upload_json("bronze", batch_name, {"results": raw_events})

                # 2. Process and Index
                indexed_batch = []
                for raw_event in raw_events:
                    self.stats["total_raw"] += 1
                    chunks = self.processor.transform(raw_event)
                    
                    if chunks:
                        # Check if the event is relevant for the Search Index (Upcoming)
                        if self._is_upcoming(chunks[0]['metadata']):
                            indexed_batch.extend(chunks)
                            self.stats["indexed"] += 1
                        else:
                            self.stats["skipped"] += 1

                if indexed_batch:
                    # Push to FAISS (Local) or Azure Search (Cloud)
                    self.vector_store.add_events(indexed_batch)

                total_session += len(raw_events)
                
                # 3. Update progress
                last_ts = raw_events[-1].get('updatedat')
                if last_ts:
                    manifest.update({"last_updated_at": last_ts, "total_processed": manifest["total_processed"] + len(raw_events)})
                    self.storage.upload_json(self.container_settings, self.manifest_file, manifest)

                # Exit conditions
                if len(raw_events) < self.page_size or (max_records and total_session >= max_records):
                    keep_running = False
                    break
            
            if keep_running:
                current_ts = last_ts # type: ignore
                # Small delay for local dev to avoid rate limiting
                if self.env != "AZURE": time.sleep(1)

        logger.info(f"Ingestion finished: {self.stats}")