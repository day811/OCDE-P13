import os
import json
import logging
from typing import Dict, Any, Optional
from app.services.storage.storage_base import StorageBase

logger = logging.getLogger(__name__)

class LocalProvider(StorageBase):
    """ Implementation of StorageBase for the local filesystem. """

    def __init__(self, base_path: str = "data"):
        self.base_path = base_path

    def upload_json(self, folder: str, filename: str, data: Dict[str, Any]) -> bool:
        """ Saves data to a local JSON file. """
        try:
            target_dir = os.path.join(self.base_path, folder)
            os.makedirs(target_dir, exist_ok=True)
            file_path = os.path.join(target_dir, filename)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Local storage upload failed: {e}")
            return False

    def download_json(self, folder: str, filename: str) -> Optional[Dict[str, Any]]:
        """ Reads data from a local JSON file. """
        file_path = os.path.join(self.base_path, folder, filename)
        if not os.path.exists(file_path):
            return None
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)