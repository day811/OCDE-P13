import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SettingsStorageService:
    """
    Service to handle persistent user settings and preferences.
    Abstracts local file storage to allow future migration to Azure Table Storage.
    """

    def __init__(self):
        self.base_path = Path("data/user_data/settings")
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.env = os.getenv("ENV", "LOCAL").upper()

    def _get_user_path(self, user_id: str) -> Path:
        """ Returns the file path for a specific user. """
        return self.base_path / f"settings_{user_id}.json"

    def get_settings(self, user_id: str) -> Dict[str, Any]:
        """
        Retrieves settings for a given user.
        Args:
            user_id (str): Unique identifier for the user.
        Returns:
            Dict[str, Any]: User preferences.
        """
        if self.env == "AZURE":
            # Placeholder for Azure Table Storage logic
            pass
        
        path = self._get_user_path(user_id)
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Default settings
        return {"favorite_city": None, "radius_km": 20, "theme": "light"}

    def save_settings(self, user_id: str, settings: Dict[str, Any]) -> bool:
        """
        Persists user settings.
        Args:
            user_id (str): Unique identifier.
            settings (Dict[str, Any]): Data to store.
        """
        try:
            path = self._get_user_path(user_id)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save settings for {user_id}: {e}")
            return False
        

    def update_usage(self, user_id: str, prompt_tokens: int, completion_tokens: int) -> Dict[str, int]:
        """
        Updates and returns the cumulative token usage for a specific user.
        """
        usage_path = self.base_path / f"usage_{user_id}.json"
        
        # Load existing usage or start from zero
        if usage_path.exists():
            with open(usage_path, 'r', encoding='utf-8') as f:
                usage = json.load(f)
        else:
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        # Increment
        usage["prompt_tokens"] += prompt_tokens
        usage["completion_tokens"] += completion_tokens
        usage["total_tokens"] += (prompt_tokens + completion_tokens)

        # Save
        with open(usage_path, 'w', encoding='utf-8') as f:
            json.dump(usage, f, indent=4)
        
        return usage