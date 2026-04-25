import os
import json
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.services.processor import EventProcessor
from app.services.vector_store import VectorStoreService

logger = logging.getLogger(__name__)

class OpenAgendaIngestor:
    """
    Service for incremental ingestion from the OpenDataSoft (ODS) mirror of OpenAgenda.
    Handles the national volume using SQL-like filtering on 'updatedat'.
    """

    def __init__(self, manifest_path: str = "data/ingestion_manifest.json"):
        """
        Initializes the ODS ingestor.
        Args:
            manifest_path (str): Path to the persistent JSON manifest file.
        """
        self.manifest_path: Path = Path(manifest_path)
        self.base_url: str = os.getenv("OPENAGENDA_URL", "")
        self.page_size: int = 100
        # ODS supports high offsets, but we still use the High Watermark for reliability
        self.records_per_watermark: int = 10000

        self.processor = EventProcessor()
        self.vector_store = VectorStoreService()
        self.env=os.getenv("ENV", "LOCAL").upper()
 

    def _get_start_timestamp(self) -> str:
        """
        Retrieves the last processed timestamp from manifest or defaults to 13 months ago.
        Returns:
            str: ISO 8601 formatted timestamp.
        """
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, 'r') as f:
                    manifest_data: Dict[str, Any] = json.load(f)
                    val: Optional[str] = manifest_data.get("last_updated_at")
                    if val: return val
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to read manifest: {e}")
        
        start_date: datetime = datetime.now() - timedelta(days=13 * 30)
        return start_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _update_manifest(self, timestamp: str, count: int) -> None:
        """
        Persists the current progress into the manifest file.
        Args:
            timestamp (str): The last processed 'updatedat' value.
            count (int): Total records processed in this session.
        """
        data: Dict[str, Any] = {
            "last_updated_at": timestamp,
            "total_processed_session": count,
            "last_run": datetime.now().isoformat()
        }
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, 'w') as f:
            json.dump(data, f, indent=4)

    def fetch_events(self, after_ts: str, offset: int) -> List[Dict[str, Any]]:
        """
        Fetches a page of records using ODS SQL-like syntax.
        Args:
            after_ts (str): Filter for records updated after this timestamp.
            offset (int): Pagination offset.
        Returns:
            List[Dict[str, Any]]: List of raw event records.
        """
        # ODS V2.1 uses 'where' and 'order_by' parameters
        # Note: the field name in ODS is usually lowercase 'updatedat'
        if self.env == "AZURE":
            location_filter = 'location_countrycode = "FR"'
        else:
            location_filter = 'location_region = "Occitanie"'


        params: Dict[str, Any] = {
            "where": f'updatedat >= "{after_ts}"  AND {location_filter}',
            "order": f"updatedat ASC",
            "limit": self.page_size,
            "offset": offset
        }
        
        try:
            response: requests.Response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data: Dict[str, Any] = response.json()
            # ODS V2.1 structure: { "total_count": ..., "results": [...] }
            results: Optional[List[Dict[str, Any]]] = data.get('results')
            return results if results is not None else []
            
        except requests.exceptions.RequestException as e:
            logger.error(f"ODS API Error: {e}")
            return []

    def process_and_index(self, events: List[Dict[str, Any]]) -> None:
        """
        Placeholder for the ETL and VectorStore pipeline.
        Args:
            events (List[Dict[str, Any]]): Raw records to process.
        """
        transformed_batch = []
        
        for raw_event in events:
            transformed = self.processor.transform(raw_event)
            if transformed:
                transformed_batch.append(transformed)
        
        if transformed_batch:
            self.save_to_silver(transformed_batch)
            self.vector_store.add_events(transformed_batch)
            logger.info(f"Successfully processed {len(transformed_batch)} events.")

    def save_to_bronze(self, batch: List[Dict[str, Any]], offset: int) -> None:
        """
        Saves raw API response to the Bronze layer.
        Args:
            batch (List[Dict[str, Any]]): Raw results from ODS.
            offset (int): Current offset for filename.
        """
        path = Path(f"data/bronze/batch_{datetime.now().strftime('%Y%m%d')}_{offset}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(batch, f, ensure_ascii=False, indent=4)

    def save_to_silver(self, validated_events: List[Dict[str, Any]]) -> None:
        """
        Saves validated/cleaned metadata to the Silver layer (JSONL format).
        """
        path = Path(f"data/silver/events_{datetime.now().strftime('%Y%m%d')}.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            for item in validated_events:
                # On sauvegarde uniquement la partie metadata (Silver data)
                f.write(json.dumps(item['metadata'], ensure_ascii=False) + "\n")


    def run(self, max_total: Optional[int] = None) -> None:
        """
        Main loop for incremental ingestion.
        Args:
            max_total (Optional[int]): Maximum number of records to process in this run.
        """
        current_watermark: str = self._get_start_timestamp()
        total_processed: int = 0
        keep_running: bool = True

        logger.info(f"Starting ODS ingestion from: {current_watermark}")

        while keep_running:
            for offset in range(0, self.records_per_watermark, self.page_size):
                batch: List[Dict[str, Any]] = self.fetch_events(current_watermark, offset)
                
                if not batch:
                    keep_running = False
                    break

                # POINT 2 (Suite): Utilisation de save_to_bronze
                self.save_to_bronze(batch, offset)

                self.process_and_index(batch)
                
                total_processed += len(batch)
                
                # Update watermark based on the last record's updatedat
                last_event_ts: Optional[str] = batch[-1].get('updatedat')
                if last_event_ts:
                    self._update_manifest(last_event_ts, total_processed)

                if len(batch) < self.page_size or (max_total and total_processed >= max_total):
                    keep_running = False
                    break

            if keep_running and 'last_event_ts' in locals():
                current_watermark = last_event_ts # type: ignore
                logger.debug(f"Watermark shifted to {current_watermark}")

        logger.info(f"Ingestion finished. Total processed: {total_processed}")