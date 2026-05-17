import json
import os
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from langchain_core.documents import Document

from app.services.vector_store import VectorStoreService, AzureSearch
from app.services.query_parser import QueryParser
from app.services.web_search_service import WebSearchService
from app.core.llm_factory import LLMFactory
from app.config import get_cached_locations, normalize_str


logger = logging.getLogger(__name__)


class SeekEngine:
    """
    Core RAG engine handling conversational retrieval and event recommendation.
    """

    def __init__(self):
        """Initializes internal services and loads reference data."""
        self.vector_store = VectorStoreService()
        self.llm = LLMFactory.get_chat_model()
        self._web_search: Optional[WebSearchService] = None

        # Native Azure Search client for OData date filtering
        # (LangChain wraps DateTimeOffset values in quotes, causing type errors)
        self._azure_client = SearchClient(
            endpoint=os.getenv("AZURE_SEARCH_ENDPOINT", ""),
            index_name=os.getenv("AZURE_SEARCH_INDEX_NAME", "puls-events-index"),
            credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_API_KEY", ""))
        )

        # Load geographic reference data once at startup
        logger.info("SeekEngine: Loading geographic reference data...")
        cities, depts = get_cached_locations()
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
            f"Standalone sentence in French:"
        )

        response = self.llm.invoke(prompt)
        usage = response.usage_metadata
        logger.info(f"Condensed query : {response.content}")
        return response.content, {  # type: ignore
            "input": usage.get("input_tokens", 0),  # type: ignore
            "output": usage.get("output_tokens", 0)  # type: ignore
        }

    def _validate_event(self, meta: Dict[str, Any], target_date: datetime,
                        tolerance: int, geo_constraints: Dict[str, Optional[str]]) -> Tuple[bool, List[str]]:
        """
        Checks geographic and temporal constraints for a candidate event.

        Args:
            meta (Dict[str, Any]): Event metadata dict from the vector store document.
            target_date (datetime): Reference date parsed from the user query.
            tolerance (int): Number of days after target_date that are still considered valid.
            geo_constraints (Dict[str, Optional[str]]): Effective geographic filters with keys
                "city" and "dept" (either may be None to skip that constraint).

        Returns:
            Tuple[bool, List[str]]: A boolean indicating validity and a list of matching date
            strings formatted as "DD/MM/YYYY à HH:MM".
        """
        title = meta.get("title_fr", "?")[:50]
        city: str = meta.get("location_city", "")
        dept: str = meta.get("location_department", "")
        score = meta.get("_search_score", 0)

        # 1. Geographic Validation
        if (geo_constraints["city"] and city != "" and
                normalize_str(geo_constraints["city"]) != normalize_str(city)):
            logger.debug(f"REJECTED geo | score={score:.4f} | {city} | {title}")
            return False, []
        if geo_constraints["dept"] and normalize_str(geo_constraints["dept"]) != normalize_str(dept):
            logger.debug(f"REJECTED geo | score={score:.4f} | {city} | {title}")
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
        if matching_dates:
            logger.info(f"VALIDATED | score={score:.4f} | {city} | {title} | {matching_dates}")
        else:
            logger.debug(f"REJECTED temporal | score={score:.4f} | {city} | {title}")

        return (len(matching_dates) > 0), matching_dates

    def _build_context_block(self, meta: Dict[str, Any], matching_dates: List[str], page_content: str) -> str:
        """
        Builds a rich text block for an event to be injected into the LLM prompt.

        Args:
            meta (Dict[str, Any]): Event metadata dict from the vector store document.
            matching_dates (List[str]): Pre-formatted date strings within the requested window.
            page_content (str): Raw page content from the vector store document.

        Returns:
            str: A multi-line text block summarising the event.
        """
        return (
            f"ÉVÉNEMENT: {meta.get('title_fr')}\n"
            f"DATES PERTINENTES: {', '.join(matching_dates)}\n"
            f"LIEU: {meta.get('location_name')} : {meta.get('location_city')}, {meta.get('location_address')}\n"
            f"DESCRIPTION: {meta.get('description_fr')} -- {meta.get('longdescription_fr')}\n"
            f"CONDITIONS: {meta.get('conditions_fr')}\n"
            f"URL: {meta.get('canonicalurl')}\n"
        )

    def _native_search(self, search_query, odata_filter, top_k,
                    min_score: float = 2.0) -> List[Document]:
        """
        ...
        Args:
            min_score (float): Minimum hybrid search score threshold.
                            Candidates below this score are discarded.
                            Azure hybrid scores typically range 0.01–3.0.
                            Default 0.02 filters the weakest matches.
        """
        results = self._azure_client.search(
            search_text=search_query,
            filter=odata_filter if odata_filter else None,
            top=top_k,
            select=[
                "id", "content", "location_city", "location_department",
                "last_date", "occurrence_dates", "metadata"
            ]
        )

        documents = []
        seen_uids  = set()

        for r in results:
            score = r.get("@search.score", 0)
            
            # Filter out weak semantic matches
            if score < min_score:
                logger.debug(f"Discarded candidate score={score:.4f} (below threshold {min_score})")
                continue

            logger.info(f"Candidate score={score:.4f} city={r.get('location_city')}")
            
            try:
                meta = json.loads(r.get("metadata", "{}"))
            except (json.JSONDecodeError, TypeError):
                meta = {}

            uid = meta.get("uid")
            if uid and uid in seen_uids:
                logger.debug(f"Skipping duplicate chunk uid={uid} score={score:.2f}")
                continue
            if uid:
                seen_uids.add(uid)

            meta["location_city"]       = r.get("location_city") or meta.get("location_city", "")
            meta["location_department"] = r.get("location_department") or meta.get("location_department", "")
            meta["last_date"]           = r.get("last_date")
            meta["occurrence_dates"]    = r.get("occurrence_dates", [])
            meta["_search_score"]       = score  # Keep for debugging

            documents.append(Document(
                page_content=r.get("content", ""),
                metadata=meta
            ))

        logger.info(f"Native search: {len(documents)} candidates above score threshold {min_score}")
        return documents
    
    def _get_web_search(self) -> WebSearchService:
        """
        Returns the WebSearchService instance, initialising it lazily on first use.
        Lazy init avoids loading smolagents at app startup when it may not be needed.
 
        Returns:
            WebSearchService: Ready-to-use web search service instance.
        """
        if self._web_search is None:
            self._web_search = WebSearchService()
        return self._web_search
 

    async def _generate_answer_stream(self, user_query: str, context: str,
                                      chat_history: List[Dict[str, str]]):
        """
        Streams the LLM answer token by token.

        Args:
            user_query (str): The original user question.
            context (str): The concatenated event context blocks to pass to the LLM.
            chat_history (List[Dict[str, str]]): Previous conversation turns.

        Yields:
            LLM chunk objects whose .content attribute carries the streamed text fragment.
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

        async for chunk in self.llm.astream(prompt):
            yield chunk

    async def search(self, user_query: str, user_id: str,
                     chat_history: List[Dict[str, str]] = [],
                     fav_city: Optional[str] = None,
                     fav_dept: Optional[str] = None,
                     top_k: int = 5):
        """
        Async RAG pipeline that yields response tokens followed by a final metadata dict.

        Args:
            user_query (str): The latest user question.
            user_id (str): Identifier of the requesting user.
            chat_history (List[Dict[str, str]]): Previous conversation turns.
            fav_city (Optional[str]): User's preferred city (fallback if no city in query).
            fav_dept (Optional[str]): User's preferred department (fallback).
            top_k (int): Maximum number of validated events to include in the context.

        Yields:
            str: Streamed text fragments of the LLM answer.
            dict: Final metadata dict with keys full_answer, sources, and usage.
        """
        logger.info(f"New query -> {user_query}")
        logger.info(f"Settings -> fav_city : {fav_city} - fav_dept : {fav_dept} - top_k : {top_k}")

        # 0. First-question geo enrichment
        # On the first question only, if no explicit geo constraint is found,
        # inject fav_city/fav_dept into the query before condensation so that
        # the geographic context is embedded in the standalone query and
        # preserved in future condensed turns.
        user_query_for_condensation = user_query
        first_conv = len(chat_history) == 0

        if first_conv:
            geo_constraints = self.parser.parse_geo(user_query)
            has_explicit_geo = geo_constraints["city"] or geo_constraints["dept"]
            if not has_explicit_geo:
                geo_hint = fav_city or fav_dept
                if geo_hint:
                    user_query_for_condensation = f"{user_query} à {geo_hint}"
                    logger.info(f"User settings improved query : {user_query_for_condensation}")
                else:
                    yield "Merci de préciser le lieu de votre recherche."
                    return

        # 1. Condense follow-up into a standalone query
        standalone_query, condensation_usage = self._condense_query(
            user_query_for_condensation, chat_history
        )
        yield {"type": "step", "name": "🔍 Analyse de la question", "content": f"Requête reformulée : *{standalone_query}*"}        


        # 2. Parse date and geo constraints from the condensed query
        target_date, tolerance, cleaned_after_date = self.parser.parse_date(standalone_query)
        geo_constraints = self.parser.parse_geo(cleaned_after_date)

        has_explicit_geo = geo_constraints["city"] or geo_constraints["dept"]
        if not has_explicit_geo:
            yield "Merci de vérifier l'orthographe du lieu de votre recherche."
            return

        effective_city = geo_constraints["city"]        
        effective_dept = geo_constraints["dept"]
        thematic_query   = geo_constraints["cleaned"]

        yield {"type": "step", "name": "📅 Contraintes détectées", "content": (
            f"📍 Lieu : {effective_city or effective_dept or 'Non spécifié'}\n"
            f"🗓️ Date cible : {target_date.strftime('%d/%m/%Y')} (±{tolerance} jours)"
        )}

        logger.info(f"City constraint : {effective_city}")
        logger.info(f"Dept constraint : {effective_dept}")
        logger.info(f"Thematic query : {thematic_query}")

        # 3. Build OData filter — geo + temporal
        # DateTimeOffset values MUST be passed WITHOUT quotes in OData.
        # LangChain's similarity_search wraps them in single quotes, causing
        # a type mismatch error. We use the native Azure Search SDK instead.
        target_date_utc = target_date.replace(tzinfo=timezone.utc)
        target_date_iso = target_date_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.info(f"Date filter : last_date ge {target_date_iso} (tolerance {tolerance}d)")

        odata_parts = []
        if effective_city:
            odata_parts.append(f"location_city eq '{effective_city}'")
        elif effective_dept:
            odata_parts.append(f"location_department eq '{effective_dept}'")
        odata_parts.append(f"last_date ge {target_date_iso}")
        odata_filter = " and ".join(odata_parts)

        # 4. Native Azure Search — bypasses LangChain DateTimeOffset quoting bug
        multiplier = 4 if os.getenv("ENV", "LOCAL") != "LOCAL" else 20
        raw_candidates = self._native_search(
            search_query=thematic_query,
            odata_filter=odata_filter,
            top_k=top_k * multiplier,
            min_score=3
        )

        yield {"type": "step", "name": "🗂️ Recherche dans l'index", "content": f"{len(raw_candidates)} candidats trouvés"}

        # 5. Post-retrieval validation (temporal + geo fine-grained check)
        validated_entries = []
        geo_filter = {"city": effective_city, "dept": effective_dept}

        for doc in raw_candidates:
            is_valid, matching_dates = self._validate_event(
                doc.metadata, target_date, tolerance, geo_filter
            )
            if is_valid:
                context_block = self._build_context_block(
                    doc.metadata, matching_dates, doc.page_content
                )
                validated_entries.append({"block": context_block, "metadata": doc.metadata})
            if len(validated_entries) >= top_k:
                break

        yield {"type": "step", "name": "✅ Événements retenus", "content": f"{len(validated_entries)} événement(s) sélectionné(s)"}

        if not validated_entries:
            # No results from the index — trigger web search fallback
            yield {
                "type": "step",
                "name": "🌐 Recherche web",
                "content": (
                    f"Aucun résultat dans l'index pour '{effective_city or effective_dept}'. "
                    f"Recherche sur les sites événementiels..."
                )
            }
 
            # Run synchronous smolagents search in a thread to avoid blocking the event loop
            import asyncio
            web_results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._get_web_search().search_events(
                    city=effective_city,
                    dept=effective_dept,
                    target_date=target_date,
                    tolerance=tolerance,
                    user_query=user_query,
                )
            )
 
            if not web_results:
                yield "Désolé, aucun événement trouvé ni dans l'index ni sur le web."
                return
 
            # Generate a response from web results using the LLM
            web_prompt = (
                f"L'utilisateur cherche : '{user_query}'\n\n"
                f"Voici des événements trouvés sur le web :\n{web_results}\n\n"
                f"Présente ces événements de façon conviviale en français. "
                f"Précise clairement que ces résultats proviennent d'une recherche web "
                f"et non de notre base de données. Mentionne les dates et les URLs."
            )
 
            yield "\n\n---\n*📡 Résultats complémentaires issus d'une recherche web :*\n\n"
 
            full_answer = ""
            total_input  = condensation_usage["input"]
            total_output = condensation_usage["output"]
 
            async for chunk in self.llm.astream(web_prompt):
                content = chunk.content
                full_answer += content
                yield content
                if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                    total_input  += chunk.usage_metadata.get("input_tokens", 0)
                    total_output += chunk.usage_metadata.get("output_tokens", 0)
 
            yield {
                "full_answer": full_answer,
                "sources": [],
                "usage": {
                    "prompt":     total_input,
                    "completion": total_output,
                    "total":      total_input + total_output
                }
            }
            return
        
        full_context = "\n---\n".join([e["block"] for e in validated_entries])

        # 6. Stream the LLM answer
        full_answer = ""
        total_input  = condensation_usage["input"]
        total_output = condensation_usage["output"]

        async for chunk in self._generate_answer_stream(user_query, full_context, chat_history):
            content = chunk.content
            full_answer += content
            yield content

            if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                total_input  += chunk.usage_metadata.get("input_tokens", 0)
                total_output += chunk.usage_metadata.get("output_tokens", 0)

        # 7. Final metadata yield
        yield {
            "full_answer": full_answer,
            "sources": [e["metadata"] for e in validated_entries],
            "usage": {
                "prompt":     total_input,
                "completion": total_output,
                "total":      total_input + total_output
            }
        }