# app/services/storage/settings_storage.py

import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional

import asyncpg

from app.services.storage.storage_factory import StorageFactory

logger = logging.getLogger(__name__)


class SettingsStorageService:
    """
    Handles persistent user settings, token usage (PostgreSQL) and
    guest daily quotas (Azure Blob Storage).

    Storage split:
        - settings_<user>.json  → Blob (gold) : city, dept, radius preferences
        - daily_<user>.json     → Blob (gold) : guest daily question/token counters
        - token_usage table     → PostgreSQL  : per-message token records for Grafana
    """

    def __init__(self):
        self.storage        = StorageFactory.get_storage()
        self.container_name = "gold"

    # ── Settings (Blob Storage) ────────────────────────────────────────────────

    def _get_settings_filename(self, user_id: str) -> str:
        """Returns the Blob filename for user UI settings."""
        return f"settings_{user_id}.json"

    def get_settings(self, user_id: str) -> Dict[str, Any]:
        """
        Retrieves UI settings for a given user.

        Args:
            user_id (str): Unique user identifier.

        Returns:
            Dict[str, Any]: User preferences (city, dept, radius).
        """
        filename = self._get_settings_filename(user_id)
        data = self.storage.download_json(self.container_name, filename)
        return data or {
            "favorite_city": None,
            "favorite_dept": None,
            "radius_km":     20
        }

    def save_settings(self, user_id: str, settings: Dict[str, Any]) -> bool:
        """
        Persists UI settings to Blob Storage.

        Args:
            user_id  (str): Unique user identifier.
            settings (dict): Preferences to store.

        Returns:
            bool: True if save succeeded.
        """
        filename = self._get_settings_filename(user_id)
        return self.storage.upload_json(self.container_name, filename, settings)

    # ── Token usage (PostgreSQL) ───────────────────────────────────────────────

    async def update_usage(
        self,
        user_id: str,
        thread_id: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> dict:
        """
        Persists token usage to PostgreSQL and returns cumulative totals.
        Replaces the previous Blob Storage implementation.

        Args:
            user_id           (str): Unique user identifier.
            thread_id         (str): Chainlit thread/conversation ID.
            prompt_tokens     (int): Tokens consumed by the prompt.
            completion_tokens (int): Tokens consumed by the model response.

        Returns:
            dict: Cumulative totals { prompt_tokens, completion_tokens, total_tokens }.
        """
        conn = await asyncpg.connect(os.getenv("DATABASE_URL","").replace("postgresql+asyncpg://", "postgresql://"))
        try:
            # Insert the per-message record
            await conn.execute(
                """
                INSERT INTO token_usage
                    ("userId", "threadId", "prompt_tokens", "completion_tokens",
                     "total_tokens", "createdAt")
                VALUES ($1, $2, $3, $4, $5, NOW())
                """,
                user_id,
                thread_id,
                prompt_tokens,
                completion_tokens,
                prompt_tokens + completion_tokens
            )

            # Return cumulative totals for the footer display
            row = await conn.fetchrow(
                """
                SELECT
                    SUM("prompt_tokens")     AS prompt_tokens,
                    SUM("completion_tokens") AS completion_tokens,
                    SUM("total_tokens")      AS total_tokens
                FROM token_usage
                WHERE "userId" = $1
                """,
                user_id
            )
            return {
                "prompt_tokens":     int(row["prompt_tokens"]     or 0),
                "completion_tokens": int(row["completion_tokens"] or 0),
                "total_tokens":      int(row["total_tokens"]      or 0),
            }
        finally:
            await conn.close()

    # ── Guest daily quota (Blob Storage) ──────────────────────────────────────

    def check_daily_quota(self, user_id: str, metadata: dict) -> dict:
        """
        Checks if the user has exceeded their daily token/question quota.
        Resets counters automatically if last usage was on a previous day.
        Only enforced for users with role == 'guest'.

        Args:
            user_id  (str):  Unique user identifier.
            metadata (dict): User metadata from Cosmos DB (role, limits).

        Returns:
            dict: {
                'allowed'        : bool,
                'reason'         : str,   # message to display if blocked
                'questions_today': int,
                'tokens_today'   : int
            }
        """
        role = metadata.get("role", "user")
        if role != "guest":
            return {"allowed": True}

        daily_limit   = metadata.get("daily_token_limit",       10000)
        max_questions = metadata.get("max_questions_per_day",   5)
        today         = datetime.now().strftime("%Y-%m-%d")

        filename = f"daily_{user_id}.json"
        data     = self.storage.download_json("gold", filename) or {}

        # Reset counters if it's a new day
        if data.get("date") != today:
            data = {"date": today, "questions": 0, "tokens": 0}
            self.storage.upload_json("gold", filename, data)

        if data["questions"] >= max_questions:
            return {
                "allowed": False,
                "reason": (
                    f"🔒 Limite journalière atteinte ({max_questions} questions/jour). "
                    f"Revenez demain ou contactez-moi pour un accès complet !"
                )
            }

        if data["tokens"] >= daily_limit:
            return {
                "allowed": False,
                "reason": "🔒 Quota de tokens journalier atteint. Revenez demain !"
            }

        return {
            "allowed":         True,
            "questions_today": data["questions"],
            "tokens_today":    data["tokens"]
        }

    def increment_daily_usage(self, user_id: str, tokens_used: int) -> None:
        """
        Increments the daily question and token counters for guest users.

        Args:
            user_id     (str): Unique user identifier.
            tokens_used (int): Total tokens consumed by this message.
        """
        today    = datetime.now().strftime("%Y-%m-%d")
        filename = f"daily_{user_id}.json"
        data     = self.storage.download_json("gold", filename) or \
                   {"date": today, "questions": 0, "tokens": 0}

        if data.get("date") != today:
            data = {"date": today, "questions": 0, "tokens": 0}

        data["questions"] += 1
        data["tokens"]    += tokens_used
        self.storage.upload_json("gold", filename, data)