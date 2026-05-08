import os
import uuid
import logging
from datetime import datetime
from azure.cosmos import CosmosClient
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ConversationStorageService:
    def __init__(self):
        endpoint = os.getenv("COSMOS_ENDPOINT")
        key = os.getenv("COSMOS_KEY")
        db_name = os.getenv("COSMOS_DATABASE")
        container_name = os.getenv("COSMOS_CONTAINER_CONVERSATIONS")

        self.client = CosmosClient(endpoint, key)
        self.container = self.client.get_database_client(db_name).get_container_client(container_name)

    def save_message(self, session_id: str, user_id: str, role: str, content: str):
        """ Sauvegarde un message (user ou assistant) dans Cosmos DB. """
        message_item = {
            "id": str(uuid.uuid4()),
            "sessionId": session_id,
            "userId": user_id,
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }
        try:
            self.container.create_item(body=message_item)
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du message : {e}")

    def get_history_by_user(self, user_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """ Récupère les derniers messages d'un UTILISATEUR (indépendant de la session) """
        # On trie par timestamp DESC pour avoir les plus récents, puis on les remet dans l'ordre chronologique
        query = "SELECT * FROM c WHERE c.userId = @userId ORDER BY c.timestamp DESC"
        params = [{"name": "@userId", "value": user_id}]
        
        try:
            # On prend les X derniers
            items = list(self.container.query_items(
                query=query, 
                parameters=params, 
                enable_cross_partition_query=True,
                max_item_count=limit
            ))
            # On inverse pour que le plus vieux soit au début (ordre chronologique pour le LLM)
            items.reverse() 
            return [{"role": item["role"], "content": item["content"]} for item in items]
        except Exception as e:
            logger.error(f"Erreur get_history_by_user : {e}")
            return []