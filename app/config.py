import os
import json
import pandas as pd
from pathlib import Path
from typing import List, Set, Tuple
import logging
from azure.storage.blob import BlobServiceClient

# ============= FIELDS =============
UID = "uid"
UPDATE = "updatedAt"
TITLE = "title_fr"
DESC = "description_fr"
LONG_DESC = "longdescription_fr"
LOC_NAME = "location_name"
LOC_DEPT = "location_department"
LOC_CITY = "location_city"
LOC_REGION = "location_region"
LOC_ADDRESS = "location_address"
CONDITIONS = "conditions_fr"
URL = "canonicalurl"
LOC_COORD = "location_coordinates"
LOC_LAT = "location_lat"
LOC_LON = "location_lon"
TIMINGS = "timings"
FIRST_DATE = "first_date"


# Fields from OpenAgenda to be concatenated for the embedding
VECTORIZED_FIELDS = [TITLE, DESC, LONG_DESC, CONDITIONS, LOC_NAME, LOC_CITY, LOC_ADDRESS, LOC_DEPT, LOC_REGION]

# Fields to be kept as metadata for filtering (Azure AI Search / OData)
METADATA_FIELDS = [UID, UPDATE, TITLE, DESC, LONG_DESC, LOC_NAME, LOC_DEPT, LOC_CITY, LOC_REGION, LOC_ADDRESS, CONDITIONS, URL, TIMINGS, LOC_COORD ]

def setup_logging() -> None:
    """
    Initializes global logging configuration using environment variables.
    The 'force=True' parameter ensures this config overrides any default 
    settings from third-party libraries.
    """
    # Retrieve log level from environment or default to INFO
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Map string to logging constants
    level = getattr(logging, log_level_str, logging.INFO)

    # Global configuration for the root logger
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True  # Important: overrides settings from other libs like Chainlit
    )
    
    # Internal logger to confirm initialization
    root_logger = logging.getLogger("app.config")
    root_logger.info(f"Logging system initialized at {log_level_str} level.")

# Trigger the setup immediately when app.config is imported
setup_logging()

def get_unique_locations() -> Tuple[List[str], List[str]]:
    """
    Retrieves unique cities and departments. 
    Scans local files in LOCAL mode or Azure Blobs in AZURE mode.
    """
    env = os.getenv("ENV", "LOCAL").upper()
    cities: Set[str] = set()
    depts: Set[str] = set()

    if env == "AZURE":
        # Cloud logic: Scan the 'silver' container
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string:
            return [], []
        
        client = BlobServiceClient.from_connection_string(connection_string)
        container_client = client.get_container_client("silver")
        
        # We limit to the last 5 blobs to avoid performance issues with 1M events
        blobs = sorted(container_client.list_blobs(), key=lambda x: x.name, reverse=True)[:5]
        
        for blob in blobs:
            blob_client = container_client.get_blob_client(blob.name)
            content = blob_client.download_blob().readall().decode('utf-8')
            for line in content.splitlines():
                event = json.loads(line)
                if event.get("location_city"): depts.add(event["location_city"])
                if event.get("location_department"): depts.add(event["location_department"])
    else:
        # Local logic: Scan data/silver[cite: 2]
        silver_path = Path("data/silver")
        for file_path in silver_path.glob("events_*.jsonl"):
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    event = json.loads(line)
                    if event.get("location_city"): cities.add(event["location_city"])
                    if event.get("location_department"): depts.add(event["location_department"])

    return sorted(list(cities)), sorted(list(depts))
                

def normalize_str(text:str) -> str:
    location = text.strip().lower()
    """ Remove accents from text """
    accents = { 'a': ['à', 'ã', 'á', 'â'],
                'e': ['é', 'è', 'ê', 'ë'],
                'i': ['î', 'ï'],
                'u': ['ù', 'ü', 'û'],
                'o': ['ô', 'ö'],
                ' ': ['-','/'] 
                }
    for (char, accented_chars) in accents.items():
        for accented_char in accented_chars:
            location = location.replace(accented_char, char)
    return location  