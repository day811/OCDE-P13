import json, re
import logging
from typing import Dict, Any, Optional, List, Tuple

from app.config import VECTORIZED_FIELDS
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
    def transform(cls, raw_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
            
            # 2. Build full content for chunking
            full_content = (
                f"TITRE: {event.title_fr}\n"
                f"VILLE: {event.location_city}\n"
                f"DESCRIPTION: {event.description_fr}\n"
                f"CONDITIONS: {event.description_fr}"
            )
            
            # 3. Create Chunks
            text_chunks = cls.split_text(full_content)
            
            # 4. Common metadata preparation 
            metadata = event.dict()
            if isinstance(event.timings, List):
                metadata['timings'] = json.dumps([t.dict() for t in event.timings])

            # Return a list of chunk objects
            return [{
                "id": f"{event.uid}_{i}", # Unique ID per chunk
                "content": chunk,
                "metadata": metadata # Every chunk carries the full event metadata
            } for i, chunk in enumerate(text_chunks)] # type: ignore

        except Exception as e:
            # logger.debug(f"Validation failed for event: {e}")
            return None