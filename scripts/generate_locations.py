#!/usr/bin/env python3
# scripts/generate_locations.py
"""
Generates a locations.json file from local Bronze batch files.
Extracts unique cities and departments, saves to data/gold/locations.json.

Usage:
    python scripts/generate_locations.py
    python scripts/generate_locations.py --upload   # also uploads to Azure Blob

Then upload manually if needed:
    az storage blob upload \
        --container-name gold \
        --account-name stapulsevents \
        --name locations.json \
        --file data/gold/locations.json \
        --overwrite
"""

import os
import json
import logging
from pathlib import Path
from typing import Set, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def normalize_str(text: str) -> str:
    """Normalizes a string for deduplication (lowercase, no accents)."""
    if not text:
        return ""
    s = text.strip().lower()
    accents = {
        'a': ['à', 'ã', 'á', 'â'],
        'e': ['é', 'è', 'ê', 'ë'],
        'i': ['î', 'ï'],
        'u': ['ù', 'ü', 'û'],
        'o': ['ô', 'ö'],
        ' ': ['-', '/']
    }
    for char, chars in accents.items():
        for c in chars:
            s = s.replace(c, char)
    return s


def extract_locations_from_bronze(bronze_path: str = "data/bronze") -> Dict:
    """
    Scans all JSON batch files in the bronze directory and extracts
    unique normalized cities and departments.

    Args:
        bronze_path (str): Path to the local bronze directory.

    Returns:
        dict: { 'cities': [...], 'departments': [...], 'total_events_scanned': int }
    """
    bronze_dir = Path(bronze_path)
    if not bronze_dir.exists():
        raise FileNotFoundError(f"Bronze directory not found: {bronze_path}")

    batch_files = sorted(bronze_dir.glob("batch_*.json"))
    logger.info(f"Found {len(batch_files)} bronze batch files in {bronze_path}")

    cities_norm: Set[str] = set()
    depts_norm:  Set[str] = set()
    cities_orig: Dict[str, str] = {}   # normalized → original display value
    depts_orig:  Dict[str, str] = {}
    total_events = 0

    for i, batch_file in enumerate(batch_files):
        try:
            with open(batch_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            events = data.get("results", [])
            total_events += len(events)

            for event in events:
                city = event.get("location_city", "").strip()
                dept = event.get("location_department", "").strip()

                if city:
                    norm = normalize_str(city)
                    if norm not in cities_norm:
                        cities_norm.add(norm)
                        cities_orig[norm] = city

                if dept:
                    norm = normalize_str(dept)
                    if norm not in depts_norm:
                        depts_norm.add(norm)
                        depts_orig[norm] = dept

            if (i + 1) % 20 == 0:
                logger.info(
                    f"Processed {i+1}/{len(batch_files)} files "
                    f"— {len(cities_norm)} cities, {len(depts_norm)} depts"
                )

        except Exception as e:
            logger.warning(f"Failed to process {batch_file.name}: {e}")
            continue

    cities_sorted = sorted(cities_orig.values(), key=lambda x: normalize_str(x))
    depts_sorted  = sorted(depts_orig.values(),  key=lambda x: normalize_str(x))

    logger.info(
        f"Done: {total_events} events scanned, "
        f"{len(cities_sorted)} cities, {len(depts_sorted)} departments."
    )

    return {
        "cities":               cities_sorted,
        "departments":          depts_sorted,
        "total_events_scanned": total_events,
        "generated_from":       "bronze",
    }


def save_locations(locations: Dict, output_path: str = "data/gold/locations.json") -> None:
    """Saves the locations dict to a local JSON file."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(locations, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved to {output_path} ({len(locations['cities'])} cities, {len(locations['departments'])} depts)")


def upload_to_azure(local_path: str = "data/gold/locations.json") -> None:
    """Uploads locations.json to Azure Blob Storage gold container."""
    from azure.storage.blob import BlobServiceClient
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        logger.error("AZURE_STORAGE_CONNECTION_STRING not set.")
        return
    client = BlobServiceClient.from_connection_string(conn_str)
    with open(local_path, 'rb') as f:
        client.get_blob_client(container="gold", blob="locations.json").upload_blob(f, overwrite=True)
    logger.info("✅ Uploaded to gold/locations.json on Azure Blob Storage")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--bronze", default="data/bronze")
    parser.add_argument("--output", default="data/gold/locations.json")
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()

    locations = extract_locations_from_bronze(args.bronze)
    save_locations(locations, args.output)

    if args.upload:
        upload_to_azure(args.output)
    else:
        logger.info(
            f"\nTo upload manually:\n"
            f"  az storage blob upload \\\n"
            f"    --container-name gold \\\n"
            f"    --account-name stapulsevents \\\n"
            f"    --name locations.json \\\n"
            f"    --file {args.output} --overwrite"
        )