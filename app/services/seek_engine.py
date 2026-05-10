import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from app.services.vector_store import VectorStoreService
from app.services.query_parser import QueryParser
from app.core.llm_factory import LLMFactory
from app.config import get_unique_locations,normalize_str


logger = logging.getLogger(__name__)

class SeekEngine:
    """
    Core RAG engine handling conversational retrieval and event recommendation.
    """

    def __init__(self):
        """ Initializes internal services and loads reference data. """
        self.vector_store = VectorStoreService()
        self.llm = LLMFactory.get_chat_model()
        
        # Load geographic reference data once at startup
        logger.info("SeekEngine: Loading geographic reference data...")
        cities, depts = get_unique_locations()
        self.parser = QueryParser(cities=cities, departments=depts)

    def _condense_query(self, user_query: str, chat_history: List[Dict[str, str]]) -> Tuple[str, Dict[str, int]]:
        """
        Rephrases a follow-up question into a standalone query based on history.
        
        Args:
            user_query (str): The latest user input.
            chat_history (List[Dict]): Previous conversation turns.
            
        Returns:
            Tuple[str, Dict[str, int]]: The standalone query and the token usage.
        """
        if not chat_history:
            return user_query, {"input": 0, "output": 0}

        history_str = "\n".join([f"{m['role']}: {m['content']}" for m in chat_history[-3:]])
        prompt = (
            f"Given the conversation history and the follow-up question, rewrite it as a "
            f"complete and standalone sentence in French. \n"
            f"IMPORTANT: Use natural language (e.g., 'au mois de...', 'à Toulouse'). \n"
            f"DO NOT use keywords only.\n\n"
            f"History:\n{history_str}\n"
            f"Follow-up: {user_query}\n"
            f"Standalone sentence in French:"        )
        
        response = self.llm.invoke(prompt)
        usage = response.usage_metadata
        
        return response.content, { # type: ignore
            "input": usage.get("input_tokens", 0), # type: ignore
            "output": usage.get("output_tokens", 0) # type: ignore
        }

    def _validate_event(self, meta: Dict[str, Any], target_date: datetime, 
                        tolerance: int, geo_constraints: Dict[str, Optional[str]]) -> Tuple[bool, List[str]]:
        """
        Checks geographic and temporal constraints for a candidate event.
        """
        city: str = meta.get("location_city", "")
        dept: str = meta.get("location_department", "")

        # 1. Geographic Validation
        if (geo_constraints["city"] and city != "" and normalize_str(geo_constraints["city"]) != normalize_str(city))  :
            return False, []
        if geo_constraints["dept"] and normalize_str(geo_constraints["dept"]) != normalize_str(dept):
            return False, []

        # 2. Temporal Validation
        timings = json.loads(meta.get("timings", "[]"))
        matching_dates = []
        
        for t in timings:
            try:
                start_dt = datetime.fromisoformat(t["start"].replace('Z', '+00:00'))
                delta = (start_dt.date() - target_date.date()).days
                if 0 <= delta <= tolerance:
                    matching_dates.append(start_dt.strftime("%d/%m/%Y à %H:%M"))
            except (ValueError, KeyError, TypeError):
                continue
        
        return (len(matching_dates) > 0), matching_dates

    def _build_context_block(self, meta: Dict[str, Any], matching_dates: List[str], page_content: str) -> str:
        """
        Builds a rich text block for an event to be sent to the LLM.
        """
        return (
            f"ÉVÉNEMENT: {meta.get('title_fr')}\n"
            f"DATES PERTINENTES: {', '.join(matching_dates)}\n"
            f"LIEU: {meta.get('location_name')} : {meta.get('location_city')}, {meta.get('location_address')}\n"
            f"DESCRIPTION: {meta.get('description_fr')} -- {meta.get('longdescription_fr')}\n"
            f"CONDITIONS: {meta.get('conditions_fr')}\n"
            f"URL: {meta.get('canonicalurl')}\n"
        )



    async def _generate_answer_stream(self, user_query: str, context: str, 
                               chat_history: List[Dict[str, str]]):
        """
        Version streaming de la génération de réponse.
        """
        persona = (
            "Tu es Gemini, un assistant IA authentique, adaptatif et expert de la culture.\n"
            "Ton but est de conseiller l'utilisateur de manière conviviale et insightful."
        )
        
        guidelines = (
            "CONSIGNES DE RÉDACTION :\n"
            "- Utilise des verbes de conseil.\n"
            "- Mets en avant l'intérêt de chaque événement.\n"
            "- Mentionne impérativement les dates pertinentes.\n"
            "- Termine par un petit mot d'esprit."
        )

        if not chat_history:
            prompt = f"{persona}\n\n{guidelines}\n\nCONTEXTE :\n{context}\n\nQUESTION : {user_query}"
        else:
            history_block = "\n".join([f"{m['role']}: {m['content']}" for m in chat_history[-5:]])
            prompt = f"{persona}\n\nHISTORIQUE :\n{history_block}\n\n{guidelines}\n\nCONTEXTE :\n{context}\n\nQUESTION : {user_query}"

        # Utilisation de .astream() pour le streaming asynchrone
        async for chunk in self.llm.astream(prompt):
            yield chunk

    async def search(self, user_query: str, user_id: str, 
               chat_history: List[Dict[str, str]] = [],
               fav_city: Optional[str] = None, 
               fav_dept: Optional[str] = None, 
               top_k: int = 5):
        """
        Pipeline RAG asynchrone qui yield des tokens puis les métadonnées.
        """
        # 1. Condensation (reste synchrone car rapide)
        standalone_query, condensation_usage = self._condense_query(user_query, chat_history)
        
        # 2. Parsing & Geo Logic
        target_date, tolerance = self.parser.parse_date(standalone_query)
        geo_constraints = self.parser.parse_geo(standalone_query)
        has_explicit_geo = geo_constraints["city"] or geo_constraints["dept"]
        effective_city = geo_constraints["city"] if has_explicit_geo else fav_city
        effective_dept = geo_constraints["dept"] if has_explicit_geo else fav_dept
        
        filter_city = normalize_str(effective_city) if effective_city else None
        filter_dept = normalize_str(effective_dept) if effective_dept else None 

        search_query = standalone_query
        azure_filter = None
        if has_explicit_geo:
            if filter_city: azure_filter = f"location_city eq '{filter_city}'"
            elif filter_dept: azure_filter = f"location_department eq '{filter_dept}'"
        
        # 3. Vector Search
        store = self.vector_store._get_store()
        multiplier = 10 if os.getenv('ENV', 'LOCAL') != 'LOCAL' else 40
        raw_candidates = store.similarity_search(search_query, k=top_k * multiplier, filters=azure_filter)
        
        validated_entries = []
        geo_filter = {"city": effective_city, "dept": effective_dept}
        for doc in raw_candidates:
            is_valid, matching_dates = self._validate_event(doc.metadata, target_date, tolerance, geo_filter)
            if is_valid:
                context_block = self._build_context_block(doc.metadata, matching_dates, doc.page_content)
                validated_entries.append({"block": context_block, "metadata": doc.metadata})
            if len(validated_entries) >= top_k: break

        if not validated_entries:
            yield "Désolé, aucun événement trouvé."
            return

        full_context = "\n---\n".join([e["block"] for e in validated_entries])

        # 4. STREAMING DE LA RÉPONSE
        full_answer = ""
        total_input = condensation_usage["input"]
        total_output = condensation_usage["output"]

        async for chunk in self._generate_answer_stream(user_query, full_context, chat_history):
            content = chunk.content
            full_answer += content
            # On yield le texte pour l'UI
            yield content 
            
            # On accumule l'usage si disponible dans le chunk
            if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                total_input += chunk.usage_metadata.get("input_tokens", 0)
                total_output += chunk.usage_metadata.get("output_tokens", 0)

        # 5. DERNIER YIELD : MÉTADONNÉES
        # On envoie un dictionnaire final pour que l'UI récupère les sources et l'usage
        yield {
            "full_answer": full_answer,
            "sources": [e["metadata"] for e in validated_entries],
            "usage": {
                "prompt": total_input,
                "completion": total_output,
                "total": total_input + total_output
            }
        }