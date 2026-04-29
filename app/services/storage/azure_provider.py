import json
import logging
import os
from typing import Dict, Any, Optional
from azure.storage.blob import BlobServiceClient
from app.services.storage.storage_base import StorageBase

logger = logging.getLogger(__name__)

class AzureProvider(StorageBase):
    """ Implementation of StorageBase for Azure Blob Storage. """

    def __init__(self):
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING not set.")
        self.client = BlobServiceClient.from_connection_string(connection_string)

    def upload_json(self, folder: str, filename: str, data: Dict[str, Any]) -> bool:
        """ Uploads data to an Azure container (folder). """
        try:
            container_client = self.client.get_container_client(folder)
            blob_client = container_client.get_blob_client(filename)
            blob_client.upload_blob(json.dumps(data, indent=4), overwrite=True)
            return True
        except Exception as e:
            logger.error(f"Azure storage upload failed: {e}")
            return False

    def download_json(self, folder: str, filename: str) -> Optional[Dict[str, Any]]:
        """ Downloads data from an Azure container. """
        try:
            blob_client = self.client.get_container_client(folder).get_blob_client(filename)
            if not blob_client.exists():
                return None
            return json.loads(blob_client.download_blob().readall())
        except Exception as e:
            logger.error(f"Azure storage download failed: {e}")
            return None