import json
import logging
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
from app.config import VECTORIZED_FIELDS, METADATA_FIELDS
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
    def clean_text(text: Any) -> str:
        """Removes HTML and normalizes whitespaces."""
        if not isinstance(text, str) or not text:
            return ""
        soup = BeautifulSoup(text, "html.parser")
        return " ".join(soup.get_text(separator=" ").split())

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
            
            # 2. Construction du contenu pour embedding (Vectorized Fields)
            # On utilise les attributs de l'objet 'event' validé
            content_parts = [
                f"TITRE: {event.title_fr}",
                f"DESCRIPTION: {cls.clean_text(event.description_fr)}",
                f"VILLE: {event.location_city}",
                f"CONDITIONS: {cls.clean_text(event.conditions_fr)}"
            ]
            
            # 3. Préparation des métadonnées pour FAISS/index.pkl
            # IMPORTANT: C'est ici qu'on assure la persistence des meta
            metadata = event.dict() 
            # On transforme la liste de timings en format JSON string pour FAISS si besoin
            metadata['timings'] = json.dumps([t.dict() for t in event.timings])

            return {
                "id": event.uid,
                "content": "\n".join(content_parts),
                "metadata": metadata
            }
        except Exception as e:
            # logger.debug(f"Validation failed for event: {e}")
            return None