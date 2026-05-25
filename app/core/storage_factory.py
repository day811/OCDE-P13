import os
from app.services.storage.local_provider import LocalProvider
from app.services.storage.azure_provider import AzureProvider
from app.services.storage.storage_base import StorageBase

class StorageFactory:
    """ Factory to instantiate the appropriate storage provider. """

    @staticmethod
    def get_storage() -> StorageBase:
        """
        Determines the storage mode from environment variables.
        Returns:
            StorageBase: An instance of either LocalProvider or AzureProvider.
        """
        env = os.getenv("ENV", "LOCAL").upper()
        
        if env == "AZURE":
            return AzureProvider()
        return LocalProvider()