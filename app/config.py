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

_location_cache: dict = {"cities": [], "depts": [], "loaded": False}

def get_cached_locations() -> tuple[list, list]:
    """
    Returns cached cities and departments.
    Falls back to live fetch if cache is empty.
    """
    if not _location_cache["loaded"]:
        warm_location_cache()
    return _location_cache["cities"], _location_cache["depts"]

def warm_location_cache() -> None:
    """Forces a fresh load of geographic data into the cache."""
    cities, depts = get_unique_locations()
    _location_cache["cities"] = cities
    _location_cache["depts"]  = depts
    _location_cache["loaded"] = True


def get_unique_locations() -> Tuple[List[str], List[str]]:
    """
    Retrieves unique cities and departments. 
    Scans local files in LOCAL mode or Azure Blobs in AZURE mode.
    """
    env = os.getenv("ENV", "LOCAL").upper()
    cities: Set[str] = set()
    depts: Set[str] = set()

    # Initialisation du client Blob si nécessaire
    container_client = None
    if env == "AZURE":
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string: return [], []
        client = BlobServiceClient.from_connection_string(connection_string)
        container_client = client.get_container_client("silver")
        blobs = sorted(container_client.list_blobs(), key=lambda x: x.name, reverse=True)[:10] # Un peu plus pour la diversité
    else:
        silver_path = Path("data/silver")
        blobs = sorted(silver_path.glob("events_*.json*"), reverse=True)[:10]

    for b in blobs:
        try:
            if env == "AZURE":
                blob_client = container_client.get_blob_client(b.name) # type: ignore
                content = blob_client.download_blob().readall().decode('utf-8')
            else:
                with open(b, 'r', encoding='utf-8') as f: # type: ignore
                    content = f.read()

            # --- LOGIQUE DE DÉCODAGE ROBUSTE ---
            # 1. On tente de charger le contenu global
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                # Si le fichier est un vrai JSONL brut, json.loads(content) échouera
                data = content.splitlines()

            # 2. On normalise en liste pour itérer
            if isinstance(data, str): 
                # Cas du double encodage global : la "string" contient du JSONL
                data = data.splitlines()
            elif not isinstance(data, list):
                data = [data]

            for item in data:
                # 3. Décodage de second niveau si item est une string (double encodage par ligne)
                event = item
                if isinstance(item, str):
                    try:
                        event = json.loads(item)
                    except:
                        continue # Pas du JSON, on ignore
                
                if isinstance(event, dict):
                    city = event.get("location_city")
                    dept = event.get("location_department")
                    if city: cities.add(city) # Correction du bug d'inversion city/dept 
                    if dept: depts.add(dept)
        except Exception as e:
            print(f"Warning: Failed to process blob {b}: {e}")
            continue

    return sorted(list(cities)), sorted(list(depts))
                

def normalize_str(text:str) -> str:
    new_str = text.strip().lower()
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
            new_str = new_str.replace(accented_char, char)
    return new_str  