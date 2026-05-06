import os
import logging
from typing import List, Dict, Any, Optional, Union
from langchain_community.vectorstores import FAISS, AzureSearch
from app.core.embedding_factory import EmbeddingFactory
from azure.search.documents.indexes.models import (
    SearchField, SearchFieldDataType, SimpleField, SearchableField
)

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
            fields = [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                SearchableField(name="content", type=SearchFieldDataType.String),
                SearchField(
                    name="content_vector", 
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True, 
                    vector_search_dimensions=1536, 
                    vector_search_profile_name="myHnswProfile"
                ),
                # Ces champs DOIVENT être à plat pour le filtrage [cite: 161]
                SimpleField(name="location_city", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="location_department", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="last_date", type=SearchFieldDataType.DateTimeOffset, filterable=True),
                SearchField(name="occurrence_dates", type=SearchFieldDataType.Collection(SearchFieldDataType.DateTimeOffset), filterable=True),
                SimpleField(name="metadata", type=SearchFieldDataType.String)
            ]
            return AzureSearch(
                azure_search_endpoint=os.getenv("AZURE_SEARCH_ENDPOINT", ""),
                azure_search_key=os.getenv("AZURE_SEARCH_API_KEY", ""),
                index_name=self.index_name,
                embedding_function=self.embeddings.embed_query,
                fields=fields
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
        Adds a batch of events to the store with Upsert logic (Delete if exists, then Add).
        Args:
            transformed_events (List[Dict[str, Any]]): List of processed events. 
        """
        if not transformed_events:
            return

        vector_db_path: str = "data/faiss_index"
        store = None

        # --- LOCAL UPSERT PREPARATION ---
        # If we are in local mode and an index exists, we find internal IDs to delete them
        if self.env != "AZURE" and os.path.exists(os.path.join(vector_db_path, "index.faiss")):
            store = FAISS.load_local(vector_db_path, self.embeddings, allow_dangerous_deserialization=True) # 
            
            # Parent UIDs to refresh
            incoming_parent_uids = {str(e['metadata'].get('uid')) for e in transformed_events}
            
            # Find all internal IDs where metadata 'uid' matches any incoming parent UID
            ids_to_delete = [
                f_id for f_id, doc in store.docstore._dict.items() # type: ignore
                if str(doc.metadata.get('uid')) in incoming_parent_uids
            ]
            
            if ids_to_delete:
                logger.info(f"Gold Layer: Removing {len(ids_to_delete)} old chunks for update.")
                store.delete(ids_to_delete)
        
        # Prepare data for all events (no filtering, to allow modified events to be updated)
        texts: List[str] = [e['content'] for e in transformed_events]
        metadatas: List[Dict[str, Any]] = [e['metadata'] for e in transformed_events]

        if self.env == "AZURE":
            store = self._get_store() 
            if store:
                # Azure Search automatically handles upserts if the 'uid' is the document key
                store.add_texts(texts, metadatas=metadatas)
                logger.info(f"Azure Layer: Upserted {len(transformed_events)} events.")
        else:
            if store: 
                # Add new/updated versions to the already loaded store 
                store.add_texts(texts, metadatas=metadatas)
            else:
                # Create a brand new index if none existed 
                store = self._get_store(texts, metadatas)

            if isinstance(store, FAISS):
                store.save_local(vector_db_path)
                logger.info(f"Gold Layer: Successfully indexed/updated {len(transformed_events)} events in FAISS.")