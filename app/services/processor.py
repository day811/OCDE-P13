import json, re
import logging
from typing import Dict, Any, Optional, List, Tuple

from app.config import VECTORIZED_FIELDS, normalize_str
from app.schemas.event import EventSchema

logger = logging.getLogger(__name__)

class EventProcessor:
    """
    Advanced ETL Processor for OpenDataSoft events.
    Includes specific logic for timings parsing to support temporal RAG.
    """

    @staticmethod
    def get_nested_value(data: Dict[str, Any], path: str) -> Any:
        """
        Safely retrieves a value from the record.
        Args:
            data (Dict[str, Any]): The raw ODS record.
            path (str): The field name (flattened in ODS).
        Returns:
            Any: The found value or None.
        """
        return data.get(path)

    @staticmethod
    def split_text(text: str, chunk_size: int = 600) -> List[str]:
        """
        Restored P11 logic: Splits text into semantic chunks.
        """
        if len(text) <= chunk_size:
            return [text]
        
        # Split on sentences to preserve meaning
        parts = re.split(r'(?<=[.!?]) +', text)
        chunks = []
        current_chunk = ""
        
        for part in parts:
            if len(current_chunk) + len(part) <= chunk_size:
                current_chunk += " " + part
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = part
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks
    
  
    @staticmethod
    def parse_timings(timings_raw: Any) -> List[Dict[str, str]]:
        """
        Parses the 'timings' field into a structured list of start/end dates.
        Args:
            timings_raw (Any): The raw timing data (string or list).
        Returns:
            List[Dict[str, str]]: List of {'start': ISO, 'end': ISO}.
        """
        parsed_timings: List[Dict[str, str]] = []
        
        if not timings_raw:
            return parsed_timings

        try:
            # Handle string-encoded JSON (common in ODS)
            if isinstance(timings_raw, str):
                data = json.loads(timings_raw)
            else:
                data = timings_raw

            # Extract start/end for each occurrence
            if isinstance(data, list):
                for t in data:
                    start = t.get('start') or t.get('begin')
                    end = t.get('end')
                    if start and end:
                        parsed_timings.append({"start": start, "end": end})
            elif isinstance(data, dict):
                # Handle single occurrence or different structure
                start = data.get('start') or data.get('begin')
                end = data.get('end')
                if start and end:
                    parsed_timings.append({"start": start, "end": end})
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse timings: {e}")
            
        return parsed_timings

    @classmethod
    def transform(cls, raw_record: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """
        Validates and transforms raw record into Silver format.
        Args:
            raw_record (Dict[str, Any]): Data from ODS results.
        Returns:
            Optional[Dict[str, Any]]: Validated document for indexing.
        """
        try:
            # 1. Validation via Pydantic
            event = EventSchema(**raw_record)
            event_data = event.model_dump()
            
            # 2. Build vectorizable content
            content_parts = []
            for field in VECTORIZED_FIELDS: # Défini dans app/config.py
                value = event_data.get(field)
                if value:
                    content_parts.append(f"{field.upper()}: {value}")

            full_vectorizable_text = "\n".join(content_parts)
            
            # 3. Create Chunks (Logique P11)
            text_chunks = cls.split_text(full_vectorizable_text)
            
            # 4. Preparation of Metadata for Azure
            metadata = event.model_dump()
            
            # --- AJOUTS POUR AZURE AI SEARCH ---
            occurrence_starts = []
            last_end_date = None
            
            if event.timings:
                # On extrait toutes les dates de début pour le champ Collection(Edm.DateTimeOffset)
                occurrence_starts = [t.start for t in event.timings]
                
                # On identifie la date de fin la plus tardive pour la réduction de 90%
                # (Utile pour filtrer les événements totalement terminés)
                last_end_date = max([t.end for t in event.timings])
            
            # On injecte ces deux nouveaux champs dans le dictionnaire metadata
            metadata['occurrence_dates'] = occurrence_starts
            metadata['last_date'] = last_end_date
            metadata['location_city'] = normalize_str(metadata['location_city'])
            metadata['location_department'] = normalize_str(metadata['location_department'])

            # On garde aussi la version JSON pour que le LLM puisse lire les horaires détaillés[cite: 2]
            if isinstance(event.timings, list):
                metadata['timings'] = json.dumps([t.model_dump() for t in event.timings])

            # 5. Return the list of chunk objects[cite: 2]
            return [{
                "id": f"{event.uid}_{i}", # ID unique pour Azure
                "content": chunk,
                "metadata": metadata 
            } for i, chunk in enumerate(text_chunks)]

        except Exception as e:
            logger.error(f"Transformation failed for record {raw_record.get('uid')}: {e}")
            return None