import json
from datetime import datetime
import logging
from typing import List, Dict, Any, Optional, Tuple
from app.services.vector_store import VectorStoreService
from app.services.query_parser import QueryParser
from app.core.llm_factory import LLMFactory
from app.config import get_unique_locations

logging.basicConfig(level=logging.INFO)
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

    def _validate_event(self, meta: Dict[str, Any], target_date: datetime, tolerance: int, geo_constraints: Dict[str, Optional[str]]) -> Tuple[bool, List[str]]:
        """
        Isolated validation logic. 
        Checks geographic and temporal constraints and returns matching dates.
        """
        city: str = meta.get("location_city", "")
        dept: str = meta.get("location_department", "")

        # 1. Geographic Validation (Case-insensitive check)
        if geo_constraints["city"]:
            if geo_constraints["city"].upper() != city.upper():
                return False, []
        
        if geo_constraints["dept"]:
            if geo_constraints["dept"].upper() != dept.upper():
                return False, []

        # 2. Temporal Validation
        # Timings are stored as a JSON string in FAISS metadata 
        timings = json.loads(meta.get("timings", "[]"))
        matching_dates = []
        
        for t in timings:
            try:
                # Handle ISO format and potential 'Z' suffix 
                start_dt = datetime.fromisoformat(t["start"].replace('Z', '+00:00'))
                
                # Calculate the difference in days from the target date 
                delta = (start_dt.date() - target_date.date()).days
                
                # The event is valid if it falls within [target_date, target_date + tolerance]
                if 0 <= delta <= tolerance:
                    matching_dates.append(start_dt.strftime("%d/%m/%Y à %H:%M"))
            except (ValueError, KeyError, TypeError):
                continue
        
        return (len(matching_dates) > 0), matching_dates


    def search(self, user_query: str, 
               fav_city: Optional[str] = None, 
               fav_dept: Optional[str] = None,
               top_k: int = 5
               ) -> Dict[str, Any]:
        """
        Full RAG pipeline: Parsing -> Broad Vector Search -> Filtering -> Conversational Generation.
        Includes an updated prompt for a warmer and more advisory tone.
        """
        # 1. Extract constraints from query
        target_date, tolerance = self.parser.parse_date(user_query)
        geo_constraints = self.parser.parse_geo(user_query)

        # 2. Logic: Fallback and Query Augmentation
        has_explicit_geo = geo_constraints["city"] or geo_constraints["dept"]
        
        effective_city = geo_constraints["city"] if has_explicit_geo else fav_city
        effective_dept = geo_constraints["dept"] if has_explicit_geo else fav_dept        
        # We create a specific query for the vector search
        search_query = user_query
        if not has_explicit_geo:
            if effective_city: search_query += f" dans la ville de {effective_city}"
            elif effective_dept: search_query += f" dans le département de {effective_dept}"
        
        geo_filter = {"city": effective_city, "dept": effective_dept}
        logger.info(f"Date: {str(target_date)} + {str(tolerance)}j - City: {effective_city} - Dept: {effective_dept}")

        # 3. Broad search 
        store = self.vector_store._get_store()
        if not store: return {"answer": "Error: Store unavailable.", "sources": []}
            
        raw_candidates = store.similarity_search(search_query, k=top_k*20)

        # 4. Validation Layer using the updated geo_constraints 
        validated_entries = []
        for doc in raw_candidates:
            is_valid, matching_dates = self._validate_event(
                doc.metadata, target_date, tolerance, geo_filter
            )
            
            if is_valid:
                # Format the context block with a focus on valid dates 
                refined_context = (
                    f"ÉVÉNEMENT: {doc.metadata.get('title_fr')}\n"
                    f"DATES PERTINENTES: {', '.join(matching_dates)}\n"
                    f"LIEU:  {doc.metadata.get('location_name')} : {doc.metadata.get('location_city')}, {doc.metadata.get('location_address')}\n"
                    f"DESCRIPTION: {doc.metadata.get('description_fr')} -- {doc.metadata.get('longdescription_fr')}\n"
                    f"CONDITIONS: {doc.metadata.get('conditions_fr')}\n"
                    f"URL: {doc.metadata.get('canonicalurl')}\n"
                )
                
                validated_entries.append({
                    "context_block": refined_context,
                    "metadata": doc.metadata
                })
            
            if len(validated_entries) >= top_k: break

        # 5. LLM Generation (Augmentation with Personality)
        if not validated_entries:
            return {
                "answer": "Oh mince ! Je n'ai déniché aucun événement correspondant exactement à tes critères pour le moment. "
                          "N'hésite pas à élargir un peu ta recherche ou à me demander une autre ville !", 
                "sources": []
            }
        else:
            logger.info(f"Number of events found : {len(validated_entries)}")

        final_context = "\n---\n".join([e["context_block"] for e in validated_entries])
        
        # New Persona-driven Prompt
        prompt = (
            "Tu es Gemini, un assistant IA authentique, adaptatif et expert de la culture.\n"
            "Ton but est de conseiller l'utilisateur de manière conviviale et insightful, comme un ami qui partage ses meilleurs bons plans.\n"
            "En te basant sur le contexte ci-dessous, formule une réponse chaleureuse, structurée et pleine de conseils.\n\n"
            "CONSIGNES DE RÉDACTION :\n"
            "- Utilise des verbes de conseil ('Je te suggère...', 'Tu devrais adorer...', 'C'est l'occasion idéale pour...').\n"
            "- Mets en avant l'intérêt de chaque événement (pourquoi c'est sympa ?).\n"
            "- Mentionne impérativement les dates qui correspondent à sa recherche pour chaque événement.\n"
            "- Termine par un petit mot d'esprit ou une suggestion globale.\n\n"
            f"CONTEXTE DES ÉVÉNEMENTS :\n{final_context}\n\n"
            f"QUESTION DE L'UTILISATEUR : {search_query}"
        )
        logger.info(f"Prompt :\n{prompt}")
        # Invoke the LLM 
        answer = self.llm.invoke(prompt)

        # --- TOKEN ACCOUNTING ---

        usage_metadata = answer.usage_metadata
        
        # Mapping for Gemini/OpenAI
        
        input_tokens = usage_metadata.get("input_tokens",0) if isinstance(usage_metadata,dict) else 0
        output_tokens = usage_metadata.get("candidates_token_count",0) if isinstance(usage_metadata,dict) else 0

        # Enregistrement via le service de stockage
        
        return {
            "answer": answer.content,
            "sources": [e["metadata"] for e in validated_entries],
            "usage": {
                "prompt": input_tokens,
                "completion": output_tokens,
                "total": input_tokens + output_tokens
            }
        }