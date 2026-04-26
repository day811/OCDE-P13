import json
from datetime import datetime
import logging
from typing import List, Dict, Any
from app.services.vector_store import VectorStoreService
from app.services.query_parser import QueryParser
from app.core.llm_factory import LLMFactory
from app.config import get_unique_locations

logger = logging.getLogger(__name__)

class SeekEngine:
    """
    Core RAG engine: Retrieval + Post-filtering + Augmentation.
    """

    def __init__(self):
        self.vector_store = VectorStoreService()
        self.llm = LLMFactory.get_chat_model()
        
        # Point 2: Initializing locations once at startup
        logger.info("SeekEngine: Loading geographic reference data...")
        cities, depts = get_unique_locations() # From app/config.py
        self.parser = QueryParser(cities=cities, departments=depts)

def search(self, user_query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        Full RAG pipeline: Parsing -> Broad Vector Search -> Filtering -> Generation. 
        """
        # 1. Extract constraints 
        target_date, tolerance = self.parser.parse_date(user_query)
        geo_constraints = self.parser.parse_geo(user_query)

        # 2. Broad search (Retrieving more for filtering) 
        store = self.vector_store._get_store()
        if not store:
            return {"answer": "Error: Vector store not available.", "sources": []}
            
        raw_candidates = store.similarity_search(user_query, k=50)

        # 3. Post-Filtering logic (Validation Layer) 
        validated = []
        for doc in raw_candidates:
            meta = doc.metadata
            
            # City/Dept Validation 
            if geo_constraints["city"] and geo_constraints["city"] != meta.get("location_city"):
                continue
            if geo_constraints["dept"] and geo_constraints["dept"] != meta.get("location_department"):
                continue
            
            # Temporal Validation (Checking parsed_timings from Silver Layer) 
            # Since timings are stored as JSON string in FAISS
            timings = json.loads(meta.get("timings", "[]"))
            match_date = False
            for t in timings:
                start_dt = datetime.fromisoformat(t["start"].replace('Z', ''))
                delta = (start_dt.date() - target_date.date()).days
                if 0 <= delta <= tolerance:
                    match_date = True
                    break
            
            if match_date:
                validated.append(doc)
            
            if len(validated) >= top_k: break

        # 4. LLM Generation (Augmentation) 
        if not validated:
            return {"answer": "I found no events matching your criteria.", "sources": []}

        context = "\n---\n".join([d.page_content for d in validated])
        prompt = f"Expert recommendation for Occitanie events.\nContext:\n{context}\n\nQuestion: {user_query}"
        
        answer = self.llm.invoke(prompt).content

        return {
            "answer": answer,
            "sources": [d.metadata for d in validated],
            "constraints": {**geo_constraints, "date": target_date.isoformat()}
        }