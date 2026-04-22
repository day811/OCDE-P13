# src/rag/retriever.py
import numpy as np
from typing import List, Dict, Optional, Callable, Tuple
from datetime import datetime, timedelta
from src.utils.utils import normalize_str, flat_date_constraints


class RAGEngine:
    """
    RAGEngine: Retrieve and Augment Generation Engine
    A retrieval system that integrates FAISS vector search with metadata filtering
    to retrieve and rank relevant chunks based on semantic similarity and constraints.
    Features:
        - Vector similarity search using FAISS indices
        - Multi-constraint filtering (date, city, department)
        - Distance-based relevance ranking
        - Formatted context building for LLM consumption
    Attributes:
        faiss_index: FAISS index for vector similarity search
        metadata (Dict): Mapping of chunk IDs to metadata dictionaries
        embed_function (Callable): Function to embed text queries
        top_k (int): Default number of results to retrieve (default: 5)
    Methods:
        retrieve: Main entry point for searching and filtering chunks
        _filter_chunks: Apply constraint-based filtering to search results
        _matches_date: Check if chunk date falls within specified range
        _matches_city: Check if chunk city/address matches target city
        _matches_dept: Check if chunk department matches target department
        build_context: Format retrieved chunks into readable context string
    """

    
    def __init__(self, faiss_index, metadata: Dict, embed_function: Callable, top_k:int = 5):
        """
        Initialize the RAG engine with FAISS index and retrieval configuration.
        Args:
            faiss_index: FAISS index object for similarity search.
            metadata (Dict): Dictionary containing metadata associated with indexed documents.
            embed_function (Callable): Function to generate embeddings for queries and documents.
            top_k (int, optional): Number of top results to retrieve. Defaults to 5.
        """
        
        self.faiss_index = faiss_index
        self.metadata = metadata
        self.embed_function = embed_function
        self.top_k = top_k
    

    def retrieve(
        self,
        query_text: str,
        k: int = 0,
        date_constraint: Optional[tuple[datetime,int]] = None,
        city_constraint: Optional[str] = None,
        dept_constraint: Optional[str] = None,
    ) -> Dict :
        """
        Retrieve and filter chunks based on semantic similarity and optional constraints.
        Args:
            query_text (str): The query text to search for.
            k (int, optional): Number of top results to return. Defaults to 0, which uses self.top_k.
            date_constraint (Optional[tuple[datetime, int]], optional): Tuple containing a datetime and an integer 
                for filtering results by date range. Defaults to None.
            city_constraint (Optional[str], optional): City name to filter results by. Defaults to None.
            dept_constraint (Optional[str], optional): Department code to filter results by. Defaults to None.
        Returns:
            Dict: A dictionary containing:
                - 'chunks': List of filtered chunk metadata dictionaries sorted by relevance, limited to k results.
                - 'embed_tokens': Approximate number of tokens used in the query embedding.
                - 'faiss_time': Execution time for the FAISS search in milliseconds.
        Process:
            1. Augments query text with date constraints if provided.
            2. Generates embedding for the augmented query.
            3. Performs vector similarity search using FAISS index (searches k*70 results, minimum 1000).
            4. Deduplicates results by event_id and assigns rankings based on distance scores.
            5. Applies spatial and temporal filters based on provided constraints.
            6. Returns top k filtered results with metadata.
        """
        
        if k == 0:
            k = self.top_k
        # Embed query
        query_text += flat_date_constraints(date_constraint)
        query_embedding = self.embed_function(query_text)

        embed_tokens = int(len(query_text.split()) * 1.3) # Approximate

        start_time = datetime.now()

        query_vector = np.array([query_embedding], dtype=np.float32)

        exec_time =  (datetime.now() - start_time       ).total_seconds() * 1000
        if hasattr(self.faiss_index, 'nprobe'):  # IndexIVFFlat
            self.faiss_index.nprobe = 20  

        # Search Faiss
        search_k = max(k * 70,1000)
        distances, indices = self.faiss_index.search(query_vector, search_k)
        
        # Build results with distances
        results = []
        seen= []
        for idx, (dist, chunk_id) in enumerate(zip(distances[0], indices[0])):
            if chunk_id >= 0:
                chunk_metadata = self.metadata.get(str(chunk_id), {})
                if chunk_metadata['event_id'] not in seen:
                    chunk_metadata['distance'] = float(dist)
                    chunk_metadata['rank'] = idx
                    results.append(chunk_metadata)
                    seen.append(chunk_metadata['event_id'])
        
        # Apply filters
        filtered_results = self._filter_chunks(
            results,
            date_constraint=date_constraint,
            city_constraint=city_constraint,
            dept_constraint=dept_constraint,
       )
        
        return {'chunks' : filtered_results[:k], 
                'embed_tokens' : embed_tokens,
                'faiss_time' : exec_time
                }
    
    def _filter_chunks(

        self,
        chunks: List[Dict],
        date_constraint: Optional[tuple[datetime,int]] = None,
        city_constraint: Optional[str] = None,
        dept_constraint: Optional[str] = None,
    ) -> List[Dict]:
        """
        Filter chunks based on optional date, city, and department constraints.
        Args:
            chunks: List of chunk dictionaries to filter.
            date_constraint: Optional tuple containing a datetime object and an integer
                            representing the date constraint to match against chunks.
            city_constraint: Optional city name string to filter chunks by matching city.
            dept_constraint: Optional department identifier string to filter chunks by
                            matching department.
        Returns:
            List[Dict]: A filtered list of chunks that satisfy all provided constraints.
                       Only chunks matching all non-None constraints are included.
        """    
        filtered = []
        for chunk in chunks:
        # Filter by date
            if date_constraint and len(self._matches_date(chunk, date_constraint)) <= 0:
                continue
        
            # Filter by city
            if city_constraint and not self._matches_city(chunk, city_constraint):
                continue
            
            # Filter by department
            if dept_constraint and not self._matches_dept(chunk, dept_constraint):
                continue
            filtered.append(chunk)
            
        return filtered
    

    @staticmethod
    def _matches_date(chunk: Dict, date_range: Optional[tuple[datetime,int]],only_first=True) -> list:
        """
        Filter chunks by date range, returning dates that fall within a specified tolerance.
        Args:
            chunk (Dict): A dictionary containing a 'dates' key with a list of date objects.
                         Each date object should have a 'begin' key with an ISO format date string.
            date_range (Optional[tuple[datetime, int]]): A tuple containing:
                         - datetime: The target date to match against
                         - int: The tolerance in days (inclusive range)
                         If None, no date filtering is applied.
            only_first (bool, optional): If True, return only the first matching date and stop processing.
                                         If False, return all matching dates. Defaults to True.
        Returns:
            list: A list of datetime objects from the chunk that fall within the date range
                  (delta >= 0 and delta <= tolerance_days). Returns an empty list if no matches
                  are found or if an exception occurs during processing.
        Raises:
            No explicit exceptions are raised; all exceptions are caught and an empty list is returned.
        """
        
        selected_dates = []
        try:
            timings = chunk.get('dates', '')
            if date_range:
                for timing in timings:
                    begin = timing['begin']
                    chunk_date = datetime.fromisoformat(begin)
                    target = date_range[0].date()
                    tolerance_days = date_range[1]
                    delta = (chunk_date.date() - target).days
                    if delta >=0 and delta <= tolerance_days :
                        selected_dates.append(chunk_date)
                        if only_first : return selected_dates
            return selected_dates
        except:
            return []
    
    @staticmethod
    def _matches_city(chunk: Dict, target_city: str) -> bool:
        """
        Check if a target city matches the city or address information in a chunk.
        Normalizes the city and address strings from the chunk and the target city,
        then checks if the target city is contained within either the chunk's city
        or address field.
        Args:
            chunk (Dict): A dictionary containing optional 'city' and 'address' keys.
            target_city (str): The city name to search for within the chunk.
        Returns:
            bool: True if the target city is found in the chunk's city or address
                  (after normalization), False otherwise. Returns False if any
                  exception occurs during processing.
        Example:
            >>> chunk = {'city': 'New York', 'address': '123 Main St, New York'}
            >>> _matches_city(chunk, 'new york')
            True
        """
        
        try:
            chunk_city = normalize_str(chunk.get('city', ''))
            chunk_address = normalize_str(chunk.get('address', ''))
            target_city = normalize_str(target_city)
            return target_city in chunk_city or target_city in chunk_address
        except:
            return False
    
    @staticmethod
    def _matches_dept(chunk: Dict, target_dept: str) -> bool:
        """
        Check if a chunk's department matches the target department.
        Compares the department value from a chunk dictionary against a target
        department string after normalizing both values for consistent comparison.
        Args:
            chunk (Dict): A dictionary containing chunk data with a 'dept' key.
            target_dept (str): The target department string to match against.
        Returns:
            bool: True if the normalized department values match, False otherwise.
                  Returns False if any exception occurs during comparison.
        Raises:
            None: Exceptions are caught and False is returned instead.
        """
        
        try:
            chunk_dept = normalize_str(chunk.get('dept', ''))
            target_dept = normalize_str(target_dept)
            return chunk_dept == target_dept
        except:
            return False

    def build_context(self,chunks: list[Dict], constraints:dict) -> str:
        def build_context(self, chunks: list[Dict], constraints: dict) -> str:
            """
            Build a formatted context string from a list of event chunks and constraints.
            This method takes a list of event data chunks and constraint filters, then creates
            a human-readable formatted string containing relevant event information. Each event
            is numbered and includes title, location, dates, relevance score, description, and URL.
            Args:
                chunks (list[Dict]): A list of dictionaries containing event data. Each dictionary
                    should have keys: 'title', 'city', 'text', 'url', and optionally 'distance'.
                constraints (dict): A dictionary containing filter constraints, including a 'date'
                    key used for filtering events by date.
            Returns:
                str: A formatted markdown-style string containing:
                    - A message if no chunks are found
                    - Numbered list of events with:
                      - Title (bold)
                      - Location (📍 emoji)
                      - Dates (📅 emoji, formatted as DD/MM/YYYY, HH:MM:SS)
                      - Relevance percentage (⭐ emoji, calculated from distance)
                      - Event description text
                      - URL link (🔗 emoji) if available
                All text is in French with event details separated by newlines.
            """
        
        if not chunks:
            return "Aucun événement n'a été trouvé pour votre recherche."
        
        context = "Voici les événements pertinents trouvés :\n\n"
        
        for i, chunk in enumerate(chunks, 1):
            title = chunk.get('title', 'Sans titre')
            city = chunk.get('city', 'Lieu non spécifié')
            dates = self._matches_date(chunk, constraints['date'],only_first=False)
            dates = " + ".join(date.strftime("%d/%m/%Y, %H:%M:%S") for date in dates)
            text = chunk.get('text', 'Description non disponible')
            url = chunk.get('url', '')
            distance = chunk.get('distance')
            
            context += f"{i}. **{title}**\n"
            context += f"   📍 Lieu: {city}\n"
            context += f"   📅 Dates: {dates}\n"
            
            if distance:
                relevance = int(distance * 100)
                context += f"   ⭐ Pertinence: {relevance}%\n"
            
            context += f"\n   {text}\n"
            
            if url:
                context += f"   🔗 {url}\n"
            
            context += "\n"
        
        return context

