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
        if (geo_constraints["city"] and normalize_str(geo_constraints["city"]) != normalize_str(city)) or city != "" :
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
               top_k: int = 5) -> Dict[str, Any]:
        """
        Main RAG pipeline entry point.
        """
        # 1. Condensation Step
        # This now returns a clean sentence like "Je cherche des rencontres sportives en juin"
        standalone_query, condensation_usage = self._condense_query(user_query, chat_history)
        logger.info(f"Condensed query: {standalone_query}")

        # 2. Parsing Step
        # The QueryParser now works on the standalone_query which contains all context
        target_date, tolerance = self.parser.parse_date(standalone_query)
        geo_constraints = self.parser.parse_geo(standalone_query)

        # 3. Geo Fallback Logic
        # Only use favorites if NO geographic info was found in the standalone query
        has_explicit_geo = geo_constraints["city"] or geo_constraints["dept"]
        effective_city = geo_constraints["city"] if has_explicit_geo else fav_city
        effective_dept = geo_constraints["dept"] if has_explicit_geo else fav_dept
        
        # Build augmented search query for vector retrieval
        search_query = standalone_query
        if not has_explicit_geo:
            if effective_city: search_query += f" à {effective_city}"
            elif effective_dept: search_query += f" en {effective_dept}"
        
        logger.info(f"Date: {str(target_date)} + {str(tolerance)}j - City: {effective_city} - Dept: {effective_dept}")
        # 3. Vector Search
        store = self.vector_store._get_store()
        if not store:
            return {"answer": "Error: Store unavailable.", "sources": []}
        
        multiplier = 10 if os.getenv('ENV', 'LOCAL') != 'LOCAL' else 40
            
        raw_candidates = store.similarity_search(search_query, k=top_k * multiplier)
        
        # Filter loop using validated dates and location
        validated_entries = []
        geo_filter = {"city": effective_city, "dept": effective_dept}
        
        for doc in raw_candidates:
            is_valid, matching_dates = self._validate_event(doc.metadata, target_date, tolerance, geo_filter)
            if is_valid:
                context_block = self._build_context_block(doc.metadata, matching_dates, doc.page_content)
                validated_entries.append({"block": context_block, "metadata": doc.metadata})
            if len(validated_entries) >= top_k:
                break

        # 5. Final Answer Generation
        if not validated_entries:
            return {"answer": "Désolé, aucun événement trouvé pour cette période.", "sources": []}

        full_context = "\n---\n".join([e["block"] for e in validated_entries])
        logger.debug(f"Query: {user_query} ")
        logger.debug(f"Full context: {full_context} ")
        logger.debug(f"Chat history: {chat_history} ")
        answer_obj, generation_usage = self._generate_answer(user_query, full_context, chat_history)

        # 6. Usage Accounting
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