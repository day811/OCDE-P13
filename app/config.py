# app/config.py

import os
import json
import logging
from pathlib import Path
from typing import List, Set, Tuple

from azure.storage.blob import BlobServiceClient

# ============= FIELD CONSTANTS =============
UID        = "uid"
UPDATE     = "updatedAt"
TITLE      = "title_fr"
DESC       = "description_fr"
LONG_DESC  = "longdescription_fr"
LOC_NAME   = "location_name"
LOC_DEPT   = "location_department"
LOC_CITY   = "location_city"
LOC_REGION = "location_region"
LOC_ADDRESS= "location_address"
CONDITIONS = "conditions_fr"
URL        = "canonicalurl"
LOC_COORD  = "location_coordinates"
LOC_LAT    = "location_lat"
LOC_LON    = "location_lon"
TIMINGS    = "timings"
FIRST_DATE = "first_date"

# Fields concatenated for embedding
VECTORIZED_FIELDS = [
    TITLE, DESC, LONG_DESC, CONDITIONS,
    LOC_NAME, LOC_CITY, LOC_ADDRESS, LOC_DEPT, LOC_REGION
]

# Fields kept as metadata for filtering (Azure AI Search / OData)
METADATA_FIELDS = [
    UID, UPDATE, TITLE, DESC, LONG_DESC, LOC_NAME, LOC_DEPT,
    LOC_CITY, LOC_REGION, LOC_ADDRESS, CONDITIONS, URL, TIMINGS, LOC_COORD
]


# ============= LOGGING SETUP =============

def setup_logging() -> None:
    """
    Initializes global logging configuration using environment variables.
    The 'force=True' parameter ensures this config overrides any default
    settings from third-party libraries.
    """
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level_str, logging.INFO)
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True
    )
    logging.getLogger("app.config").info(
        f"Logging system initialized at {log_level_str} level."
    )

# Triggered immediately when app.config is imported
setup_logging()

logger = logging.getLogger(__name__)


# ============= GEOGRAPHIC REFERENCE DATA =============

_location_cache: dict = {"cities": [], "depts": [], "loaded": False}


def get_cached_locations() -> Tuple[List[str], List[str]]:
    """
    Returns cached cities and departments.
    Falls back to live fetch if cache is not yet loaded.

    Returns:
        Tuple[List[str], List[str]]: Sorted lists of cities and departments.
    """
    if not _location_cache["loaded"]:
        warm_location_cache()
    return _location_cache["cities"], _location_cache["depts"]


def warm_location_cache() -> None:
    """
    Forces a fresh load of geographic data from Azure AI Search into the cache.
    Called once at app startup via on_app_startup in ui.py.
    """
    cities, depts = get_unique_locations()
    _location_cache["cities"] = cities
    _location_cache["depts"]  = depts
    _location_cache["loaded"] = True
    logger.info(
        f"Location cache warmed: {len(cities)} cities, {len(depts)} departments."
    )


def get_unique_locations() -> Tuple[List[str], List[str]]:
    """
    Retrieves unique cities and departments from Azure AI Search using facets.
    This is the primary source of truth (93k+ indexed events).

    Falls back to Silver Blob Storage if Azure Search is unavailable.

    Returns:
        Tuple[List[str], List[str]]: (cities, departments) sorted and title-cased.
    """
    env = os.getenv("ENV", "LOCAL").upper()

    if env == "AZURE":
        try:
            return _get_locations_from_search()
        except Exception as e:
            logger.warning(
                f"Azure Search facets failed, falling back to Silver: {e}"
            )
            return _get_locations_from_silver()
    else:
        return _get_locations_from_silver()


def _get_locations_from_search() -> Tuple[List[str], List[str]]:
    """
    Queries Azure AI Search with facets to get all distinct city and department
    values from the index. Single request, no document scanning.

    Returns:
        Tuple[List[str], List[str]]: (cities, departments) sorted and title-cased.
    """
    from azure.search.documents import SearchClient
    from azure.core.credentials import AzureKeyCredential

    endpoint  = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    api_key   = os.getenv("AZURE_SEARCH_API_KEY", "")
    index     = os.getenv("AZURE_SEARCH_INDEX_NAME", "puls-events-index")

    client = SearchClient(
        endpoint=endpoint,
        index_name=index,
        credential=AzureKeyCredential(api_key)
    )

    cities: Set[str] = set()
    depts:  Set[str] = set()

    # top=0 means we fetch only facets, no documents — very fast
    results = client.search(
        search_text="*",
        facets=["location_city,count:1000", "location_department,count:200"],
        top=0
    )
    facets = results.get_facets()

    if facets:
        for f in facets.get("location_city", []):
            val = f.get("value", "").strip()
            if val:
                cities.add(val)
        for f in facets.get("location_department", []):
            val = f.get("value", "").strip()
            if val:
                depts.add(val)

    logger.info(
        f"Locations loaded from Azure Search: "
        f"{len(cities)} cities, {len(depts)} departments."
    )

    # Values in index are normalized (lowercase, no accents) →
    # apply .title() for display in the UI Select widget
    return (
        sorted([c.title() for c in cities if c]),
        sorted([d.title() for d in depts  if d])
    )


def _get_locations_from_silver() -> Tuple[List[str], List[str]]:
    """
    Fallback: reads unique cities and departments from Silver Blob Storage
    (last 10 files). Used in LOCAL mode or when Azure Search is unavailable.

    Returns:
        Tuple[List[str], List[str]]: (cities, departments) sorted.
    """
    env = os.getenv("ENV", "LOCAL").upper()
    cities: Set[str] = set()
    depts:  Set[str] = set()

    container_client = None
    if env == "AZURE":
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string:
            return [], []
        client = BlobServiceClient.from_connection_string(connection_string)
        container_client = client.get_container_client("silver")
        blobs = sorted(
            container_client.list_blobs(),
            key=lambda x: x.name,
            reverse=True
        )[:10]
    else:
        silver_path = Path("data/silver")
        blobs = sorted(silver_path.glob("events_*.json*"), reverse=True)[:10]

    for b in blobs:
        try:
            if env == "AZURE":
                content = container_client.get_blob_client(b.name).download_blob().readall().decode('utf-8')  # type: ignore
            else:
                with open(b, 'r', encoding='utf-8') as f:  # type: ignore
                    content = f.read()

            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = content.splitlines()

            if isinstance(data, str):
                data = data.splitlines()
            elif not isinstance(data, list):
                data = [data]

            for item in data:
                event = item
                if isinstance(item, str):
                    try:
                        event = json.loads(item)
                    except Exception:
                        continue
                if isinstance(event, dict):
                    city = event.get("location_city")
                    dept = event.get("location_department")
                    if city:
                        cities.add(city)
                    if dept:
                        depts.add(dept)
        except Exception as e:
            logger.warning(f"Failed to process blob {b}: {e}")
            continue

    return sorted(list(cities)), sorted(list(depts))


# ============= STRING NORMALIZATION =============

def normalize_str(text: str) -> str:
    """
    Normalizes a string for comparison or OData filtering:
    lowercases, strips, removes accents, replaces hyphens and slashes with spaces.

    Args:
        text (str): Input string.

    Returns:
        str: Normalized string.
    """
    if not text:
        return ""
    new_str = text.strip().lower()
    accents = {
        'a': ['à', 'ã', 'á', 'â'],
        'e': ['é', 'è', 'ê', 'ë'],
        'i': ['î', 'ï'],
        'u': ['ù', 'ü', 'û'],
        'o': ['ô', 'ö'],
        ' ': ['-', '/']
    }
    for char, accented_chars in accents.items():
        for accented_char in accented_chars:
            new_str = new_str.replace(accented_char, char)
    return new_str