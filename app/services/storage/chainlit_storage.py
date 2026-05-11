# app/services/storage/chainlit_storage.py
"""
Chainlit data layer configuration for conversation persistence.

Uses the same Azure Blob Storage pattern as AzureProvider (BlobServiceClient
from connection string) to avoid any additional dependencies or credentials.

Usage in ui.py:
    from app.services.storage.chainlit_storage import get_data_layer
    cl.data_layer(get_data_layer)
"""

import os
import logging
from typing import Any, Dict, Optional, Union

from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
    BlobSasPermissions,
)
from datetime import datetime, timedelta, timezone
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.data.storage_clients.base import BaseStorageClient, storage_expiry_time

logger = logging.getLogger(__name__)


# ── Blob Storage client (same pattern as AzureProvider) ───────────────────────

class ChainlitBlobStorageClient(BaseStorageClient):
    """
    Chainlit-compatible storage client backed by Azure Blob Storage.
    Uses AZURE_STORAGE_CONNECTION_STRING exactly like the rest of the app.
    """

    def __init__(self):
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING is not set.")
        self.container    = os.getenv("CHAINLIT_STORAGE_CONTAINER", "chainlit")
        self.blob_service = BlobServiceClient.from_connection_string(connection_string)
        # Extract account name and key from connection string for SAS generation
        self._account_name = self.blob_service.account_name
        self._account_key  = self.blob_service.credential.account_key
        logger.info(f"ChainlitBlobStorageClient → container: {self.container}")

    async def upload_file(
        self,
        object_key: str,
        data: Union[bytes, str],
        mime: str = "application/octet-stream",
        overwrite: bool = True,
        content_disposition: str | None = None,
    ) -> Dict[str, Any]:
        """
        Uploads a file to the chainlit Blob container.

        Args:
            object_key          : Blob name (path within the container).
            data                : File content as bytes or str.
            mime                : MIME type stored as content_type metadata.
            overwrite           : Whether to overwrite an existing blob.
            content_disposition : Optional Content-Disposition header value.

        Returns:
            dict: { 'object_key': str, 'url': str }
        """
        try:
            blob_client = self.blob_service.get_blob_client(
                container=self.container,
                blob=object_key
            )
            cs = ContentSettings(
                content_type=mime,
                content_disposition=content_disposition
            )
            blob_client.upload_blob(data, overwrite=overwrite, content_settings=cs)
            return {"object_key": object_key, "url": blob_client.url}
        except Exception as e:
            logger.error(f"upload_file failed [{object_key}]: {e}")
            return {}

    async def delete_file(self, object_key: str) -> bool:
        """
        Deletes a blob from the chainlit container.

        Args:
            object_key: Blob name to delete.

        Returns:
            bool: True if deletion succeeded.
        """
        try:
            self.blob_service.get_blob_client(
                container=self.container, blob=object_key
            ).delete_blob()
            return True
        except Exception as e:
            logger.error(f"delete_file failed [{object_key}]: {e}")
            return False

    async def get_read_url(self, object_key: str) -> str:
        """
        Generates a time-limited SAS URL to read a blob.

        Args:
            object_key: Blob name.

        Returns:
            str: Pre-signed URL valid for storage_expiry_time seconds.
        """
        try:
            sas_token = generate_blob_sas(
                account_name=self._account_name,
                container_name=self.container,
                blob_name=object_key,
                account_key=self._account_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.now(timezone.utc) + timedelta(seconds=storage_expiry_time),
            )
            blob_client = self.blob_service.get_blob_client(
                container=self.container, blob=object_key
            )
            return f"{blob_client.url}?{sas_token}"
        except Exception as e:
            logger.error(f"get_read_url failed [{object_key}]: {e}")
            return ""

    async def close(self) -> None:
        """Closes the underlying BlobServiceClient connection."""
        try:
            self.blob_service.close()
        except Exception as e:
            logger.error(f"close failed: {e}")


# ── Data layer factory (called by cl.data_layer decorator) ────────────────────

def get_data_layer() -> SQLAlchemyDataLayer:
    """
    Returns a configured SQLAlchemyDataLayer connected to Azure PostgreSQL,
    with Blob Storage for file attachments.

    Environment variables required:
        DATABASE_URL                   : postgresql+asyncpg://user:pass@host/db
        AZURE_STORAGE_CONNECTION_STRING: Used by ChainlitBlobStorageClient
        CHAINLIT_STORAGE_CONTAINER     : Blob container name (default: 'chainlit')

    Returns:
        SQLAlchemyDataLayer: Ready-to-use Chainlit data layer.

    Raises:
        ValueError: If DATABASE_URL is not set.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "DATABASE_URL is required. "
            "Format: postgresql+asyncpg://user:password@host/dbname"
        )

    storage_client = ChainlitBlobStorageClient()
    logger.info("Chainlit data layer → PostgreSQL + Azure Blob Storage")

    return SQLAlchemyDataLayer(
        conninfo=database_url,
        storage_provider=storage_client,
        ssl_require=True,
        show_logger=False,
    )