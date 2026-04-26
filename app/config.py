import os
import json
import pandas as pd
from pathlib import Path
from typing import List, Set

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

def get_unique_locations() -> tuple[List[str], List[str]]:
    """
    Scans the Silver Layer (JSONL) to extract unique cities and departments.
    This should be called once during SeekEngine initialization.
    """
    silver_path = Path("data/silver")
    cities: Set[str] = set()
    depts: Set[str] = set()
    
    # We look for the most recent silver file
    files = sorted(silver_path.glob("events_*.jsonl"), reverse=True)
    if not files:
        return [], []
    
    for file_path in silver_path.glob("events_*.jsonl"):
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    event = json.loads(line)
                    if event.get("location_city"):
                        cities.add(event["location_city"]) 
                    if event.get("location_department"):
                        depts.add(event["location_department"]) 
                except json.JSONDecodeError:
                    continue
                
    return sorted(list(cities)), sorted(list(depts))