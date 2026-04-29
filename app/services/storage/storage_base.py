from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class StorageBase(ABC):
    """
    Abstract Base Class defining the storage interface.
    All storage implementations (Local, Azure, etc.) must implement these methods.
    """

    @abstractmethod
    def upload_json(self, folder: str, filename: str, data: Dict[str, Any]) -> bool:
        """ Persists a dictionary as a JSON file. """
        pass

    @abstractmethod
    def download_json(self, folder: str, filename: str) -> Optional[Dict[str, Any]]:
        """ Retrieves and parses a JSON file. """
        pass