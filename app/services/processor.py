import json
import logging
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
from app.config import VECTORIZED_FIELDS, METADATA_FIELDS

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
    def transform(cls, raw_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Transforms a raw ODS record into a structured document for the Vector Store.
        Args:
            raw_event (Dict[str, Any]): Raw record from ODS results.
        Returns:
            Optional[Dict[str, Any]]: Transformed dictionary or None.
        """
        try:
            # 1. Build Vectorized Content
            content_parts: List[str] = []
            for field in VECTORIZED_FIELDS:
                val: Any = cls.get_nested_value(raw_event, field)
                if val:
                    content_parts.append(f"{field.upper()}: {cls.clean_text(val)}")
            
            if not content_parts:
                return None

            # 2. Build Metadata
            metadata: Dict[str, Any] = {}
            for field in METADATA_FIELDS:
                if field == "timings":
                    # Specific treatment for timings verification
                    metadata["parsed_timings"] = cls.parse_timings(raw_event.get("timings"))
                    # We also keep the raw string for reference
                    metadata["timings"] = str(raw_event.get("timings", ""))
                else:
                    metadata[field] = cls.get_nested_value(raw_event, field)

            return {
                "id": str(raw_event.get('uid', '')),
                "content": "\n".join(content_parts),
                "metadata": metadata
            }
        except Exception as e:
            logger.error(f"Transformation failed: {e}")
            return None