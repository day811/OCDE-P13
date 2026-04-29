import json
import os
import logging
from pathlib import Path

from typing import Dict, Any, Optional
from app.services.storage.storage_factory import StorageFactory

logger = logging.getLogger(__name__)

class SettingsStorageService:
    """
    Service to handle persistent user settings and preferences.
    Abstracts local file storage to allow future migration to Azure Table Storage.
    """

    def __init__(self):
        self.storage = StorageFactory.get_storage()
        self.container_name = "settings"

    def _get_settings_filename(self, user_id: str) -> str:
        """ Returns the filename for user settings. """
        return f"settings_{user_id}.json"

    def _get_usage_filename(self, user_id: str) -> str:
        """ Returns the filename for user token usage. """
        return f"usage_{user_id}.json"

    def get_settings(self, user_id: str) -> Dict[str, Any]:
        """
        Retrieves settings for a given user.
        Args:
            user_id (str): Unique identifier for the user.
        Returns:
            Dict[str, Any]: User preferences.
        """
        filename = self._get_settings_filename(user_id)
        data = self.storage.download_json(self.container_name, filename)
        
        if data:
            return data
        
        # Default settings if no file is found
        return {
            "favorite_city": None,
            "favorite_dept": None,
            "radius_km": 20
        }
    def save_settings(self, user_id: str, settings: Dict[str, Any]) -> bool:
        """
        Persists user settings.
        Args:
            user_id (str): Unique identifier.
            settings (Dict[str, Any]): Data to store.
        """
        filename = self._get_settings_filename(user_id)
        return self.storage.upload_json(self.container_name, filename, settings)       

    def update_usage(self, user_id: str, prompt_tokens: int, completion_tokens: int) -> Dict[str, int]:
        """
        Updates and returns cumulative token usage for a specific user.
        Args:
            user_id (str): Unique user identifier.
            prompt_tokens (int): Tokens from the prompt.
            completion_tokens (int): Tokens from the model response.
        Returns:
            Dict[str, int]: Updated usage statistics.
        """
        filename = self._get_usage_filename(user_id)
        
        # Try to download existing usage or start from zero
        usage = self.storage.download_json(self.container_name, filename) or {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }

        # Increment
        usage["prompt_tokens"] += prompt_tokens
        usage["completion_tokens"] += completion_tokens
        usage["total_tokens"] += (prompt_tokens + completion_tokens)

        # Persist back to storage (Local file or Azure Blob)
        self.storage.upload_json(self.container_name, filename, usage)
                
        return usage