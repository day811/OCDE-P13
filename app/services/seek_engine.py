import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from app.services.vector_store import VectorStoreService
from app.services.query_parser import QueryParser
from app.core.llm_factory import LLMFactory
from app.config import get_unique_locations, LOG_LEVEL

logging.basicConfig(level=LOG_LEVEL)
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
            f"Given the conversation below, rephrase the follow-up question "
            f"into a standalone search query in French.\n\n"
            f"History:\n{history_str}\n"
            f"Follow-up: {user_query}\n"
            f"Standalone Query:"
        )
        
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
        if geo_constraints["city"] and geo_constraints["city"].upper() != city.upper():
            return False, []
        if geo_constraints["dept"] and geo_constraints["dept"].upper() != dept.upper():
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

    def _generate_answer(self, user_query: str, context: str, 
                         chat_history: List[Dict[str, str]]) -> Tuple[Any, Dict[str, int]]:
        """
        Selects the appropriate prompt and invokes the LLM for the final answer.
        """
        persona = (
            "Tu es Gemini, un assistant IA authentique, adaptatif et expert de la culture.\n"
            "Ton but est de conseiller l'utilisateur de manière conviviale et insightful, "
            "comme un ami qui partage ses meilleurs bons plans."
        )
        
        guidelines = (
            "CONSIGNES DE RÉDACTION :\n"
            "- Utilise des verbes de conseil ('Je te suggère...', 'Tu devrais adorer...').\n"
            "- Mets en avant l'intérêt de chaque événement.\n"
            "- Mentionne impérativement les dates pertinentes.\n"
            "- Termine par un petit mot d'esprit."
        )

        if not chat_history:
            # Initial prompt
            prompt = (
                f"{persona}\n\n{guidelines}\n\n"
                f"CONTEXTE DES ÉVÉNEMENTS :\n{context}\n\n"
                f"QUESTION : {user_query}"
            )
        else:
            # Follow-up prompt with history
            history_block = "\n".join([f"{m['role']}: {m['content']}" for m in chat_history[-5:]])
            prompt = (
                f"{persona}\n\n"
                f"HISTORIQUE DE LA CONVERSATION :\n{history_block}\n\n"
                f"{guidelines}\n\n"
                f"NOUVEAU CONTEXTE :\n{context}\n\n"
                f"DERNIÈRE QUESTION : {user_query}"
            )

        response = self.llm.invoke(prompt)
        usage = response.usage_metadata
        
        return response, {
            "input": usage.get("input_tokens", 0), # type: ignore
            "output": usage.get("output_tokens", 0) # type: ignore
        }

    def search(self, user_query: str, user_id: str, 
               chat_history: List[Dict[str, str]] = [],
               fav_city: Optional[str] = None, 
               fav_dept: Optional[str] = None, 
               top_k: int = 5
               ) -> Dict[str, Any]:
        """
        Main entry point for the RAG search.
        """
        # 1. Handle conversation context (Query Condensation)
        standalone_query, condensation_usage = self._condense_query(user_query, chat_history)

        # 2. Extract constraints and determine filters
        target_date, tolerance = self.parser.parse_date(standalone_query)
        geo_constraints = self.parser.parse_geo(standalone_query)

        has_explicit_geo = geo_constraints["city"] or geo_constraints["dept"]
        effective_city = geo_constraints["city"] if has_explicit_geo else fav_city
        effective_dept = geo_constraints["dept"] if has_explicit_geo else fav_dept
        
        # Build search query for vector retrieval
        search_query = standalone_query
        if not has_explicit_geo:
            if effective_city: search_query += f" dans la ville de {effective_city}"
            elif effective_dept: search_query += f" dans le département de {effective_dept}"
        
        logger.info(f"Searching for: {search_query}")
        logger.info(f"Date: {str(target_date)} + {str(tolerance)}j - City: {effective_city} - Dept: {effective_dept}")
        # 3. Vector Search
        store = self.vector_store._get_store()
        if not store:
            return {"answer": "Error: Vector store unavailable.", "sources": []}
            
        raw_candidates = store.similarity_search(search_query, k=top_k * 30)

        # 4. Filter and build context
        validated_entries = []
        geo_filter = {"city": effective_city, "dept": effective_dept}
        
        for doc in raw_candidates:
            is_valid, matching_dates = self._validate_event(doc.metadata, target_date, tolerance, geo_filter)
            if is_valid:
                context_block = self._build_context_block(doc.metadata, matching_dates, doc.page_content)
                validated_entries.append({"block": context_block, "metadata": doc.metadata})
            if len(validated_entries) >= top_k:
                break

        if not validated_entries:
            return {"answer": "Désolé, je n'ai trouvé aucun événement.", "sources": []}

        # 5. Generate final response
        full_context = "\n---\n".join([e["block"] for e in validated_entries])
        logger.debug(f"Query: {user_query} ")
        logger.debug(f"Full context: {full_context} ")
        logger.debug(f"Chat history: {chat_history} ")
        answer_obj, generation_usage = self._generate_answer(user_query, full_context, chat_history)

        # 6. Total Accounting
        total_input = condensation_usage["input"] + generation_usage["input"]
        total_output = condensation_usage["output"] + generation_usage["output"]

        return {
            "answer": answer_obj.content,
            "sources": [e["metadata"] for e in validated_entries],
            "usage": {
                "prompt": total_input,
                "completion": total_output,
                "total": total_input + total_output
            }
        }