# src/core/search_engine.py
"""
Unified Search Engine Interface
Abstraction commune pour RAGEngine et ChatBot
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime
from src.rag.searchbot import SearchBot
from src.rag.chatbot import ChatBot
from src.utils.token_accounting import get_accounting
from src.config import Config

logger = logging.getLogger(__name__)


class SeekEngine:
    """
    Interface unifiée pour recherche et chat.
    Abstrait les détails d'implémentation de RAGEngine et ChatBot.
    """
    
    def __init__(self, embedder:str, snapshot_date: str = "", mode: str = 'search'):
        """
        Initialize SeekEngine.
        
        Args:
            snapshot_date: Date du snapshot (YYYY-MM-DD). Default: Config.DEV_SNAPSHOT_DATE
            mode: 'search' pour recherche simple, 'chat' pour chat interactif
        """
        self.snapshot_date = snapshot_date or Config.DEV_SNAPSHOT_DATE
        self.embedder = embedder
        self.mode = mode

        
        logger.info(f"Initializing SeekEngine (mode={mode}, snapshot={self.snapshot_date})")
        self.load_engine(embedder, snapshot_date=snapshot_date)
        
    
    def load_engine(self, embedder:str, snapshot_date: str = ""):

        self.snapshot_date = snapshot_date or Config.DEV_SNAPSHOT_DATE
        self.embedder = embedder
        try:
            if self.mode == 'search':
                self.seek_engine = SearchBot(embedder, snapshot_date=snapshot_date)
            elif self.mode == 'chat':
                self.seek_engine = ChatBot(embedder,snapshot_date=snapshot_date)
            else:
                raise ValueError(f"Invalid mode: {self.mode}. Use 'search' or 'chat'.")
        except Exception as e:
            logger.error(f"Failed to initialize engine: {e}")
            raise
    
    
    def query(self, question: str, top_k: int = 5, 
            temperature: float = 0.7, 
            session_id: str = "") -> Dict:
        """
        Execute unified query (compatible with both RAGEngine and ChatBot).
        
        Args:
            question: User question/query
            top_k: Number of top results to retrieve
            temperature: LLM temperature (0.0-1.0), ignored for pure RAG
            
        Returns:
            Dictionary with keys:
            - 'quesion' : str - Inital query from user
            - 'answer': str - Main answer/response
            - 'sources': List[Dict] - Source events
            - 'total_tokens': int - Tokens used
            - 'execution_time': float - Query execution time in seconds
            - 'constraints': Dict - Extracted constraints (date, city)
            - 'top_k' : int - Amount of wished results
            - 'snapshot_index' : Pathname of the used index file
            - 'llm_model' : str - Provider and model used for chat
            - 'll_embed_model' : str - Provider and model used for embedding query
            - 'temperature' : float - temperature used by llm_model
        """
        
        query_start = datetime.now()
        result={}
        try:
            if self.mode == 'search':
                result = self._handle_search(question, top_k, temperature)
            elif self.mode == 'chat':
                result = self._handle_chat(question, top_k, temperature)
            
            # Calculate execution time
            execution_time = (datetime.now() - query_start).total_seconds()
            nb_answer =len(result['sources']) # type: ignore
            total_distance = sum([source['distance'] for source in result['sources']])
                        # ✅ LOG TOKENS
            
            accounting = get_accounting(session_id=session_id)
            query_tokens=int(result.get("query_tokens", 0))
            context_tokens=int(result.get("context_tokens", 0))
            llm_tokens=int(result.get("llm_tokens", 0))
            accounting.log_tokens(
                query_tokens=query_tokens,
                context_tokens=context_tokens,
                llm_tokens=llm_tokens,
                operation=self.mode,
                session_id=session_id  # Assure alignement
            )
            total_tokens = int(query_tokens) + int(context_tokens) + int(llm_tokens)
            result['total_tokens']= int(total_tokens)
            result['timestamp'] = datetime.now().strftime('%Y%m%d_%H%M%s')
            result['mean_distance'] = (total_distance/nb_answer) if nb_answer else None
            result['execution_time'] = execution_time # type: ignore
            result['question'] = question # type: ignore
            result['snapshot_index'] = Config.get_index_path(provider=self.embedder, snapshot_date=self.snapshot_date) 
            result['llm_embed_model'] = f"{self.seek_engine.embed_llm.NAME}:{self.seek_engine.embed_llm.EMBED_MODEL}"
            logger.info(f"Query completed in {execution_time:.3f}s | Tokens: {result.get('total_tokens', 0)}") 
            
            return result # type: ignore
        
        except Exception as e:
            logger.error(f"Query failed: {e}", exc_info=True)
            raise
    
    def _handle_search(self, question: str, top_k: int, temperature: float) -> Dict:
        """Handle search mode query (RAGEngine)."""
        
        logger.debug(f"Handling search query: {question}")
        
        result = self.seek_engine.answer_question( # type: ignore
            question=question,
            top_k=top_k,
            temperature=temperature
        )

        result['llm_chat_model'] = f"{self.seek_engine.search_llm.NAME}:{self.seek_engine.search_llm.CHAT_MODEL}"
        result['temperature'] = self.seek_engine.search_llm.temperature
        result['top_k'] = self.seek_engine.rag_engine.top_k

        return result
    
    def _handle_chat(self, question: str, top_k: int, 
                     temperature: float) -> Dict:
        """Handle chat mode query (ChatBot with LangChain)."""
        
        logger.debug(f"Handling chat query: {question}")
        
        result = self.seek_engine.chat( # type: ignore
            user_question=question,
            top_k=top_k,
            temperature=temperature
        )
        result['llm_chat_model'] = f"{self.seek_engine.rag_engine.llm.__class__.__name__}:{self.seek_engine.rag_engine.llm.model}" 
        result['temperature'] = self.seek_engine.rag_engine.llm.temperature
        result['top_k'] = self.seek_engine.rag_engine.retriever.top_k

        return result
    
    def get_session_accounting(self) -> Dict:
        """Get token accounting for current session."""
        accounting = get_accounting()
        return accounting.get_session_report()
    
    def reset_session(self):
        """Reset session accounting."""
        from src.utils.token_accounting import reset_accounting
        reset_accounting()
        logger.info("Session accounting reset")
