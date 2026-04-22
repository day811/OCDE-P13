# src/rag/langchain_bridge.py
"""
LangChain integration bridge for RAG pipeline
Connects Faiss retriever + Mistral LLM
"""
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_classic.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
from src.utils.token_accounting import get_accounting
from src.llm.factory import get_langchain_llm
from src.rag.engine import RAGEngine
from src.rag.query_parser import QueryParser

from typing import List, Callable
import logging
from src.config import Config
import faiss
import json
from pathlib import Path



logger = logging.getLogger(__name__)

class FaissRetrieverAdapter(BaseRetriever):
    """Adapter to use RAGRetriever as LangChain Retriever"""
    
    def __init__(self, rag_retriever, query_parser,top_k, snapshot_date = None):
        super().__init__()
        # Lazy init pour éviter inspection prématurée
        object.__setattr__(self, '_rag_retriever', rag_retriever)  # Force set même avec __slots__
        object.__setattr__(self, '_query_parser', query_parser)
        object.__setattr__(self, '_top_k', top_k)
        object.__setattr__(self, '_snapshot_date', snapshot_date)
        object.__setattr__(self, '_embed_tokens', 0)
        object.__setattr__(self, '_faiss_time', 0)

    @property
    def rag_retriever(self):
        return getattr(self, '_rag_retriever', None)

    @property
    def query_parser(self):
        return getattr(self, '_query_parser', None)

    @property
    def top_k(self):
        return getattr(self, '_top_k', None)

    @property
    def snapshot_date(self):
        return getattr(self, '_snapshot_date', None)
   
    @property
    def embed_tokens(self):
        return getattr(self, '_embed_tokens', None)
   
    @property
    def faiss_time(self):
        return getattr(self, '_faiss_time', None)
   

    def _get_relevant_documents(self, query: str) -> List[Document]: # type: ignore
        """Get relevant documents from Faiss through RAGRetriever"""
        # Parse constraints from query
        constraints = self.query_parser.parse_constraints(query, self.snapshot_date) # type: ignore
        
        # Retrieve chunks using your existing RAGRetriever
        result = self.rag_retriever.retrieve( # type: ignore
            query_text=query,
            date_constraint=constraints['date'],
            city_constraint=constraints['city'],
            dept_constraint=constraints['dept']
        )
        chunks = result['chunks']
        embed_tokens = result['embed_tokens']
        faiss_time = result['faiss_time']

        object.__setattr__(self, '_embed_tokens', embed_tokens)
        object.__setattr__(self, '_faiss_time', faiss_time)

#        self.embed_tokens = embed_tokens
        # Convert chunks to LangChain Documents
        chunks = chunks[:self.top_k]
        documents = []
        for chunk in chunks:
            dates = self.rag_retriever._matches_date(chunk, constraints['date'],only_first=False) # type: ignore
            dates = " et ".join(date.strftime("%d/%m/%Y, %H:%M:%S") for date in dates)
            documents.append(Document(
                page_content=chunk.get('text'),
                metadata={
                    'url': chunk.get('url'),
                    'title': chunk.get('title'),
                    'description' : chunk.get('text'),
                    'event_id': chunk.get('event_id'),
                    'dept': chunk.get('dept'),
                    'city': chunk.get('city'),
                    'address': chunk.get('address'),
                    'distance': chunk.get('distance'),
                    'faiss_time' : faiss_time,
                    'dates': dates
                }
            ))
        
        logger.info(f"Retrieved {len(documents)} documents from Faiss")
        return documents
    
    async def aget_relevant_documents(self, query: str) -> List[Document]:
        """Async version"""
        return self._get_relevant_documents(query)


class LangChainRAG:
    """RAG system using LangChain orchestration"""
    
    def __init__(self, embedder:str,embed_function: Callable, snapshot_date=Config.DEV_SNAPSHOT_DATE):
        
        self.snapshot_date = snapshot_date
        self.embed_function  = embed_function
        self.qa_chain = None
        
        # Define RAG prompt
        index_path = Config.get_index_path(embedder, self.snapshot_date)
        metadata_path = Config.get_metadata_path(embedder, self.snapshot_date)
        
        self.faiss_index = faiss.read_index(index_path)
        logger.info(f"Faiss indexes loaded - provider :{embedder} - date : {snapshot_date}")

        with open(metadata_path, 'r', encoding='utf-8') as f:
            self.metadata = json.load(f)


        # Initialize components
        self.query_parser = QueryParser()
        self.prompt = PromptTemplate(
            input_variables=['context', 'question', ''],
            template="""Tu es un assistant expert en événements culturels en Occitanie.

Voici les événements pertinents trouvés :
{context}

Question de l'utilisateur : {question}

Fournis une recommandation personnalisée basée sur ces événements.
Sois concis et pertinent.
""" 
        )
        
        # Create RAG chain with LangChain

    def make_chain_retriever(self, top_k: int =5, temperature:float=0.7):
        """
        Docstring for get_chain_retriever
        """
        # Initialize  LLM
        self.llm = get_langchain_llm(temperature)
        self.temperature=temperature
        self.top_k = top_k
        
        self.rag_retriever = RAGEngine(
            faiss_index=self.faiss_index,
            metadata=self.metadata,
            embed_function=self.embed_function,
            top_k=top_k
        )

        self.retriever = FaissRetrieverAdapter(self.rag_retriever, self.query_parser, top_k=top_k, snapshot_date= self.snapshot_date)
        
        # Initialize LangChain RAG
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type='stuff',  # Simple context concatenation
            retriever=self.retriever,
            return_source_documents=True,
            chain_type_kwargs={'prompt': self.prompt}
        )
         



    def answer(self, question: str, top_k: int =5, temperature: float = 0.7 ) -> dict:
        """Answer a question using LangChain RAG"""
        
        if self.qa_chain is None or temperature !=  self.temperature or top_k != self.top_k:
            self.make_chain_retriever(top_k=top_k, temperature=temperature)

        total_tokens = 0
        try:
            result = self.qa_chain.invoke({'query': question}) # type: ignore
                
            sources  = [source.metadata for source in result['source_documents']]
            result['sources'] = sources

            # Estimate tokens (query embedding + context + generation)
            query_tokens = self.retriever.embed_tokens  # rough estimate
            faiss_time = self.retriever.faiss_time  # rough estimate
            
            context_string = " ".join([str(source) for source in sources]) + self.prompt.template
            context_tokens = int(len(context_string.split()) * 1.3)
            llm_tokens = int(len(result['result'].split(' ')) * 1.3)

            return {
                'answer': result['result'],
                'sources': sources,
                'constraints' : self.query_parser.parse_constraints(query=question, snapshot_date= self.snapshot_date),
                'query_tokens' : query_tokens,
                'context_tokens' : context_tokens,
                'llm_tokens' : llm_tokens,
                'faiss_time' : faiss_time,
                'success': True
            }
        except Exception as e:
            logger.error(f"LangChain RAG error: {e}")
            return {
                'answer': f"Erreur: {str(e)}",
                'sources': [],
                'total_tokens': total_tokens,
                'success': False
            }
