# src/rag/chatbot.py
"""
Interactive chatbot interface using LangChain RAG
"""
from src.rag.langchain_bridge import LangChainRAG
from src.rag.engine import RAGEngine
from src.config import Config
from src.llm.factory import get_llm
import logging


logger = logging.getLogger(__name__)

class ChatBot:
    """Chatbot for event recommendations"""
    
    def __init__(self, embedder:str, snapshot_date=Config.DEV_SNAPSHOT_DATE):

        from pathlib import Path

        self.snapshot_date = snapshot_date
        self.embedder = embedder
        # Load Faiss index and metadata
        
        self.embed_llm = get_llm(provider=embedder)
 
        # Initialize LangChain RAG
        self.rag_engine = LangChainRAG(embedder, embed_function= self._embed_query, snapshot_date= snapshot_date )
        
        logger.info("ChatBot initialized with LangChain RAG")
    
    def _embed_query(self, query_text: str):
        """Embed query using Faiss embedder"""
        
        return self.embed_llm.embed(query_text)
        
   
    def chat(self, user_question: str, top_k: int = 5, temperature: float = 0.7) -> dict:
        """Process user question through LangChain RAG"""

        logger.info(f"User question: {user_question}")
        
        result = self.rag_engine.answer(user_question, top_k=top_k, temperature=temperature)
        
 
        result['mode'] = 'chat'

        return result
    