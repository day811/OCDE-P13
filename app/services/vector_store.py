import os
import logging
from typing import List, Dict, Any, Optional, Union
from langchain_community.vectorstores import FAISS, AzureSearch
from app.core.embedding_factory import EmbeddingFactory

logger = logging.getLogger(__name__)

class VectorStoreService:
    """
    Handles the storage and retrieval of vectorized events.
    """

    def __init__(self):
        self.embeddings = EmbeddingFactory.get_embedding_model()
        self.env: str = os.getenv("ENV", "LOCAL").upper()
        self.index_name: str = os.getenv("AZURE_SEARCH_INDEX_NAME", "puls-events-index")

    def _get_store(self, 
                   texts: Optional[List[str]] = None, 
                   metadatas: Optional[List[Dict[str, Any]]] = None) -> Union[FAISS, AzureSearch, None]:
        """
        Initializes the vector store based on environment.
        Args:
            texts (Optional[List[str]]): List of strings to index.
            metadatas (Optional[List[Dict[str, Any]]]): Metadata for each text.
        Returns:
            Union[FAISS, AzureSearch, None]: The initialized store.
        """
        if self.env == "AZURE":
            return AzureSearch(
                azure_search_endpoint=os.getenv("AZURE_SEARCH_ENDPOINT", ""),
                azure_search_key=os.getenv("AZURE_SEARCH_API_KEY", ""),
                index_name=self.index_name,
                embedding_function=self.embeddings.embed_query
            )
        
        vector_db_path: str = "data/faiss_index"
        if os.path.exists(vector_db_path) and not texts:
            return FAISS.load_local(
                vector_db_path, 
                self.embeddings, 
                allow_dangerous_deserialization=True
            )
        elif texts and metadatas:
            return FAISS.from_texts(texts, self.embeddings, metadatas=metadatas)
        return None

    def add_events(self, transformed_events: List[Dict[str, Any]]) -> None:
        """
        Adds a batch of events to the store (cumulative/incremental).
        Args:
            transformed_events (List[Dict[str, Any]]): List of processed events.
        """
        if not transformed_events:
            return

        texts: List[str] = [e['content'] for e in transformed_events]
        metadatas: List[Dict[str, Any]] = [e['metadata'] for e in transformed_events]
        vector_db_path: str = "data/faiss_index"

        if self.env == "AZURE":
            store = self._get_store()
            if store:
                store.add_texts(texts, metadatas=metadatas)
        else:
            # --- LOGIQUE LOCALE CUMULATIVE ---
            if os.path.exists(os.path.join(vector_db_path, "index.faiss")):
                # 1. On charge l'index existant
                store = FAISS.load_local(
                    vector_db_path, 
                    self.embeddings, 
                    allow_dangerous_deserialization=True
                )
                # 2. On ajoute les nouveaux vecteurs à l'objet chargé
                store.add_texts(texts, metadatas=metadatas)
                logger.info(f"Added {len(texts)} events to existing local index.")
            else:
                # 1. On crée le tout premier index
                store = FAISS.from_texts(texts, self.embeddings, metadatas=metadatas)
                logger.info(f"Created new local index with {len(texts)} events.")

            # 3. On sauvegarde (écrase le fichier par la version augmentée en RAM)
            store.save_local(vector_db_path)