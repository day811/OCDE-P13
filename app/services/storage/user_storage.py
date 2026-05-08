import os
import bcrypt
import logging
from azure.cosmos import CosmosClient, exceptions
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class UserStorageService:
    def __init__(self):
        endpoint = os.getenv("COSMOS_ENDPOINT")
        key = os.getenv("COSMOS_KEY")
        database_name = os.getenv("COSMOS_DATABASE")
        container_name = os.getenv("COSMOS_CONTAINER_USERS")

        try:
            self.client = CosmosClient(endpoint, key)
            self.database = self.client.get_database_client(database_name)
            self.container = self.database.get_container_client(container_name)
        except Exception as e:
            logger.error(f"Erreur de connexion Cosmos DB : {e}")

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Vérifie les identifiants et retourne les données utilisateur si valide.
        """
        try:
            # On récupère l'utilisateur par son ID (username)
            user = self.container.read_item(item=username, partition_key=username)
            
            # Vérification du mot de passe hashé
            stored_password = user.get("password_hash").encode('utf-8')
            if bcrypt.checkpw(password.encode('utf-8'), stored_password):
                return user
            
        except exceptions.CosmosResourceNotFoundError:
            logger.warning(f"Utilisateur non trouvé : {username}")
        except Exception as e:
            logger.error(f"Erreur lors de l'authentification : {e}")
            
        return None

    def create_user(self, username: str, password: str, metadata: Dict[str, Any] = None):
        """
        Méthode utilitaire pour ajouter un utilisateur en base (à utiliser une fois).
        """
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user_item = {
            "id": username,
            "username": username,
            "password_hash": hashed,
            "metadata": metadata or {"role": "user"}
        }
        self.container.upsert_item(user_item)
        logger.info(f"Utilisateur {username} créé avec succès.")