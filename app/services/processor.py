import logging
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
from app.core.rag_config import VECTORIZED_FIELDS, METADATA_FIELDS

logger = logging.getLogger(__name__)

class EventProcessor:
    """
    Advanced ETL Processor for OpenAgenda events.
    """

    @staticmethod
    def get_nested_value(data: Dict[str, Any], path: str) -> Any:
        """
        Safely retrieves a value from a nested dictionary.
        Args:
            data (Dict[str, Any]): The source dictionary.
            path (str): Dot-separated path (e.g., 'location.city').
        Returns:
            Any: The found value or None.
        """
        keys: List[str] = path.split('.')
        current: Any = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    @staticmethod
    def clean_text(text: Any) -> str:
        """
        Removes HTML tags and normalizes whitespace.
        Args:
            text (Any): The input to clean (usually a string).
        Returns:
            str: Cleaned string, defaults to empty string.
        """
        if not isinstance(text, str) or not text:
            return ""
        soup = BeautifulSoup(text, "html.parser")
        clean: str = soup.get_text(separator=" ")
        return " ".join(clean.split())

    @classmethod
    def transform(cls, raw_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Transforms a raw event into a structured document.
        Args:
            raw_event (Dict[str, Any]): Raw JSON from the API.
        Returns:
            Optional[Dict[str, Any]]: Transformed data or None if invalid.
        """
        try:
            content_parts: List[str] = []
            for field in VECTORIZED_FIELDS:
                val: Any = cls.get_nested_value(raw_event, field)
                if val:
                    clean_val: str = cls.clean_text(val)
                    content_parts.append(f"{field.split('.')[-1].capitalize()}: {clean_val}")
            
            if not content_parts:
                return None

            metadata: Dict[str, Any] = {}
            for field in METADATA_FIELDS:
                key: str = field.replace('.', '_')
                metadata[key] = cls.get_nested_value(raw_event, field)

            return {
                "id": str(raw_event.get('uid', 'unknown')),
                "content": "\n".join(content_parts),
                "metadata": metadata
            }
        except Exception as e:
            logger.error(f"Transformation failed: {e}")
            return None