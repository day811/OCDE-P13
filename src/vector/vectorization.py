# src/vectorization.py
"""
Vectorization Module : Chunking, Embedding, Indexation Faiss
"""

import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
from src.utils.token_accounting import get_accounting
import logging

import faiss
from src.config import Config
import re
import time

from src.llm.factory import get_llm

logger = logging.getLogger(__name__)

class EventVectorizer:
    """
    EventVectorizer
    A class for vectorizing event data using language models and creating searchable vector indices.
    This class handles the complete vectorization pipeline including:
    - Text chunking with intelligent splitting strategies
    - Embedding generation via LLM API with batch processing
    - FAISS index creation and persistence
    - Metadata management and persistence
    Attributes:
        llm: Language model instance from the configured provider
    Methods:
        __init__(provider): Initialize vectorizer with specified LLM provider
        split_text(input_text, chunk_size, level): Recursively split text into chunks using separators
        chunk_events(events, chunk_size): Split event descriptions into manageable chunks
        vectorize_chunks(chunks, batch_size): Generate embeddings for chunks via LLM API
        create_faiss_index(embeddings, n_vectors): Create optimized FAISS vector index
        save_index(index, snapshot_date): Persist FAISS index to disk
        save_metadata(chunks, events, snapshot_date): Save chunk metadata with event context
        load_processed_events(processed_path): Load events from JSON file
        run_full_vectorization_pipeline(processed_path, snapshot_date, chunk_size): Execute complete pipeline
    """
    
    def __init__(self, provider = Config.LLM_PROVIDER):

        self.llm = get_llm(provider=provider)
    

    def split_text(self, input_text, chunk_size: int = 500, level=0):
        """
        Recursively split text into chunks of specified size using hierarchical separators.
        This method attempts to split text using different separators (period, comma, space)
        in a hierarchical manner. It starts with the coarsest separator and progressively
        uses finer separators if chunks exceed the specified size.
        Args:
            input_text (str): The text to be split into chunks.
            chunk_size (int, optional): Maximum character length for each chunk. Defaults to 500.
            level (int, optional): Current level of separator hierarchy (0=". ", 1=", ", 2=" "). 
                                  Defaults to 0.
        Returns:
            list: A list of text chunks, each not exceeding chunk_size characters 
                  (except when no separators are available).
        Raises:
            ValueError: If a chunk cannot be split further because all separators 
                       have been exhausted while the text still exceeds chunk_size.
        Note:
            - Chunks retain their original separator at the end.
            - Empty sentences are filtered out.
            - The method recursively calls itself with incrementally finer separators.
        """
        
        sep = (". ", ", ", " ")
        sentences = input_text.split(sep[level])
        output_text_list=[]
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence)>chunk_size:
                if level < len(sep)-1:
                    mini_sentences =  self.split_text(sentence, chunk_size=chunk_size, level = level + 1)
                    output_text_list.extend(mini_sentences)
                else:
                    logger.error(f"\n❌ Chunks splitting - FAILED")
                    raise ValueError(f"Failed to chunk text of length {len(sentence)} with all separators exhausted")
            else:
                if sentence : output_text_list.append(sentence + sep[level] )   
        return output_text_list
    

    def chunk_events(self, events: List[Dict], chunk_size: int = 500) -> List[Dict]:
        """
        Split a list of events into text chunks of a specified maximum size.
        This method processes events by combining their text fields, removing HTML tags,
        and intelligently splitting the resulting text into chunks using sentence-based
        segmentation. Each chunk is tracked with a unique ID and linked to its source event.
        Args:
            events (List[Dict]): A list of event dictionaries to be chunked. Each event
                must contain a 'uid' field for identification and text fields defined in
                Config.CHUNK_FIELDS.
            chunk_size (int, optional): The maximum size (in characters) of each chunk.
                Defaults to 500.
        Returns:
            List[Dict]: A list of chunk dictionaries, each containing:
                - 'chunk_id' (int): Unique identifier for the chunk
                - 'event_id': The source event's unique identifier
                - 'text' (str): The chunk text content
        Example:
            >>> chunks = vectorizer.chunk_events([event1, event2], chunk_size=1000)
            >>> len(chunks)
            5
        """
        
        chunks = []
        chunk_id = 0
        
        for event in events:
            # Combiner tous les textes de l'événement
            full_text = ". ".join(event[field] for field in Config.CHUNK_FIELDS if field)

            #retirer les balises html
            full_text = re.sub(r"<.*?>", " ", full_text)

            # Chunking intelligent (par phrases puis mots)
            sentences = self.split_text(full_text,chunk_size=chunk_size)
            current_chunk = ""
            
            for sentence in sentences:
                if len(current_chunk) + len(sentence) <= chunk_size:
                    current_chunk += sentence
                else:
                    if current_chunk:
                        chunks.append({
                            'chunk_id': chunk_id,
                            'event_id': event['uid'],
                            'text': current_chunk,
                        })
                        chunk_id += 1
                    current_chunk = sentence
        
            # Dernier chunk
            if current_chunk:
                chunks.append({
                    'chunk_id': chunk_id,
                    'event_id': event['uid'],
                    'text': current_chunk,
                })
                chunk_id += 1
        
        logger.info(f"Created {len(chunks)} chunks from {len(events)} events")
        return chunks
    
    def vectorize_chunks(self, chunks: List[Dict], batch_size: int = 100) -> np.ndarray:
        """
        Vectorize a list of text chunks into embeddings using the LLM API in batches.
        This method processes chunks in batches to efficiently generate embeddings while
        tracking token usage and managing API calls with rate limiting.
        Args:
            chunks (List[Dict]): A list of dictionaries containing chunk data. Each dictionary
                must have a 'text' key containing the text to be vectorized.
            batch_size (int, optional): The number of chunks to process per API call. 
                Defaults to 100.
        Returns:
            np.ndarray: A 2D numpy array of float32 embeddings with shape (total_chunks, embedding_dim).
                Each row represents the embedding vector for the corresponding input chunk.
        Raises:
            Exception: Re-raises any exception that occurs during the vectorization process,
                with details logged to the logger.
        Side Effects:
            - Logs vectorization progress and statistics at INFO and DEBUG levels.
            - Tracks token usage per batch and logs aggregated statistics.
            - Records token accounting information for the entire operation.
            - Introduces a 2-second delay between batch API calls.
        """
        
        texts = [chunk['text'] for chunk in chunks]
        total_chunks = len(texts)
        
        logger.info(f"Vectorizing {total_chunks} chunks with {self.llm.NAME}...")
        logger.info(f"Batch size: {batch_size} chunks per API call")
        
        all_embeddings = []
        token_stats = {
            'total_input_tokens': 0,
            'batches': []
        }
        
        try:
            # Process in batches
            num_batches = (total_chunks + batch_size - 1) // batch_size
            batch_tokens=0
            for batch_idx in range(num_batches):
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, total_chunks)
                batch_texts = texts[start_idx:end_idx]
                
                logger.debug(f"Batch {batch_idx + 1}/{num_batches}: Vectorizing chunks {start_idx}-{end_idx}...")
                
                # Call LLM API for this batch
                batch_embeddings = self.llm.embed(batch_texts)  # Pass the entire list
                batch_embeddings = np.array(batch_embeddings).astype(np.float32)
                all_embeddings.append(batch_embeddings)
               
                # ✅ Tracker les tokens par batch
                batch_tokens = len(" ".join(batch_texts).split()) * 1.3 # Approximate
                token_stats['total_input_tokens'] += batch_tokens
                token_stats['batches'].append({
                    'batch_id': batch_idx + 1,
                    'chunk_count': len(batch_texts),
                    'input_tokens': batch_tokens,
                    'tokens_per_chunk': batch_tokens / len(batch_texts) if batch_texts else 0
                })
                
                logger.debug(
                    f"Batch {batch_idx + 1}/{num_batches} | "
                    f"Chunks: {start_idx}-{end_idx} | "
                    f"Tokens: {batch_tokens} | "
                    f"Avg: {batch_tokens / len(batch_texts):.1f} tok/chunk"
                )
                            # Extract embeddings from response
                
                logger.info(f"  ✓ Batch {batch_idx + 1}: {len(batch_embeddings)} embeddings created")

                time.sleep(2)
            
            # Concatenate all batches
            embeddings = np.vstack(all_embeddings)
            logger.info(
                f"Vectorization complete | "
                f"Total tokens: {token_stats['total_input_tokens']} | "
                f"Shape: {embeddings.shape} | "
                f"Avg: {token_stats['total_input_tokens'] / total_chunks:.1f} tok/chunk"
            )
            get_accounting().log_tokens(
                query_tokens=int(batch_tokens),
                context_tokens=0,
                llm_tokens=0,
                operation="vector",
            )

            
            return embeddings
                
        except Exception as e:
            logger.error(f"Vectorization failed: {e}")
            raise  


    def create_faiss_index(self, embeddings: np.ndarray, n_vectors: int) -> faiss.IndexIVFFlat:
        """
        Create a FAISS index for efficient similarity search on embeddings.
        This method initializes an IVFFlat (Inverted File Flat) index, optimized for
        medium-sized datasets. The index is trained on the provided embeddings and
        populated with all vectors for subsequent similarity searches.
        Args:
            embeddings (np.ndarray): 2D array of embedding vectors with shape
                (n_vectors, embedding_dimension).
            n_vectors (int): Total number of vectors in the embeddings array.
        Returns:
            faiss.IndexIVFFlat: A trained FAISS index ready for similarity search queries.
        Raises:
            ValueError: If embeddings array is empty or has invalid dimensions.
            RuntimeError: If index training or population fails.
        Notes:
            - The number of inverted file lists (nlist) is automatically computed as
              a fraction of n_vectors, bounded between 10 and 100.
            - Uses L2 (Euclidean) distance as the distance metric.
            - Index must be trained before adding vectors.
        """
        
        dimension = embeddings.shape[1]  
        
        # IVF : optimisé pour medium-sized datasets
        nlist = min(100, max(10, n_vectors // 100))
        
        quantizer = faiss.IndexFlatL2(dimension)
        index = faiss.IndexIVFFlat(quantizer, dimension, nlist)
        
        logger.info(f"Training index with {len(embeddings)} vectors...")
        index.train(embeddings) # type: ignore
        index.add(embeddings) # type: ignore
        
        logger.info(f"✅ Faiss index created (nlist={nlist}, vectors={len(embeddings)})")
        return index
    
    def save_index(self, index: faiss.IndexIVFFlat, snapshot_date: str) -> str:
        """
        Save a FAISS index to disk.
        Args:
            index (faiss.IndexIVFFlat): The FAISS index to save.
            snapshot_date (str): The snapshot date used to determine the index file path.
        Returns:
            str: The file path where the index was saved.
        Raises:
            Exception: If the index cannot be written to disk or the path cannot be created.
        """
        
        from src.config import Config
        
        index_path = Config.get_index_path(provider = Config.LLM_PROVIDER, snapshot_date= snapshot_date)
        Path(index_path).parent.mkdir(parents=True, exist_ok=True)
        
        faiss.write_index(index, index_path)
        logger.info(f"Index saved to {index_path}")
        return index_path
    
    def save_metadata(self, chunks: List[Dict], events: List[Dict], snapshot_date: str) -> str:
        """
        Save metadata for vectorized chunks to a JSON file.
        Creates a metadata file containing enriched information about chunks by combining
        chunk data with corresponding event details. The metadata is organized by index
        and includes event information such as title, location, dates, and URL.
        Args:
            chunks: List of chunk dictionaries, each containing 'event_id', 'chunk_id', and 'text'.
            events: List of event dictionaries containing event details indexed by 'uid'.
            snapshot_date: The snapshot date used to determine the metadata file path.
        Returns:
            str: The full path to the saved metadata JSON file.
        Raises:
            FileNotFoundError: If the parent directory cannot be created.
            IOError: If the metadata file cannot be written.
        Note:
            - Only chunks with matching events in the event_lookup are included in metadata.
            - The metadata path is determined by Config.get_metadata_path() using the LLM provider name.
            - Parent directories are created automatically if they don't exist.
        """
        
        from src.config import Config
        
        metadata_path = Config.get_metadata_path(provider= Config.LLM_PROVIDER, snapshot_date=snapshot_date)
        Path(metadata_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Build event lookup by uid
        event_lookup = {event['uid']: event for event in events}
        
        # Format: {index: {event_id, chunk_id, text, title, city, date, url}}
        metadata = {}
        for i, chunk in enumerate(chunks):
            event = event_lookup.get(chunk['event_id'])
            if event:
                metadata[i] = {
                    'event_id': chunk['event_id'],
                    'chunk_id': chunk['chunk_id'],
                    'text': chunk['text'],
                    'title': event[Config.TITLE],
                    'city': event[Config.LOC_CITY],
                    'address': event[Config.LOC_ADDRESS],
                    'dept': event[Config.LOC_DEPT],
                    'begin': event[Config.FIRST_DATE],
                    'dates': event[Config.TIMINGS],
                    'url': event[Config.URL]
                }
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Metadata saved to {metadata_path}")
        return metadata_path    

    def load_processed_events(self, processed_path: str) -> List[Dict]:
        """
        Load processed events from a JSON file.
        Args:
            processed_path (str): The file path to the JSON file containing processed events.
        Returns:
            List[Dict]: A list of dictionaries representing the loaded events.
        Raises:
            FileNotFoundError: If the file at processed_path does not exist.
            json.JSONDecodeError: If the file content is not valid JSON.
        Example:
            >>> events = loader.load_processed_events('/path/to/events.json')
            >>> len(events)
            42
        """
        
        logger.info(f"Loading processed events from {processed_path}...")
        
        with open(processed_path, 'r', encoding='utf-8') as f:
            events = json.load(f)
        
        logger.info(f"Loaded {len(events)} events")
        return events

    def run_full_vectorization_pipeline(self, processed_path: str, snapshot_date: str, chunk_size: int = 500) -> Tuple[str, str]:
        """
        Execute the complete vectorization pipeline for processing events into a searchable Faiss index.
        This method orchestrates the following steps:
        1. Load processed events from disk
        2. Chunk events into manageable batches
        3. Generate vector embeddings for each chunk
        4. Create and configure a Faiss index
        5. Persist the index and associated metadata
        Args:
            processed_path (str): File path to the processed events data.
            snapshot_date (str): Date identifier for versioning the index and metadata files.
            chunk_size (int, optional): Number of events per chunk. Defaults to 500.
        Returns:
            Tuple[str, str]: A tuple containing:
                - index_path (str): File path to the saved Faiss index
                - metadata_path (str): File path to the saved metadata file
        Raises:
            Exception: Any exception raised during pipeline execution is logged and re-raised.
                      The pipeline logs error details before raising.
        Logs:
            - Info messages at each pipeline stage with descriptive labels [3a] through [3f]
            - Success/failure status with visual indicators (✅ or ❌)
            - Index and metadata file paths upon successful completion
        """
        
        logger.info(f"\n{'='*70}")
        logger.info("VECTORIZATION PIPELINE - START")
        logger.info(f"{'='*70}")
        
        try:
            logger.info("\n[3a] Loading processed events...")
            events = self.load_processed_events(processed_path)
            
            logger.info(f"\n[3b] Chunking events (chunk_size={chunk_size})...")
            chunks = self.chunk_events(events, chunk_size=chunk_size)
            
            logger.info(f"\n[3c] Vectorizing {len(chunks)} chunks...")
            embeddings = self.vectorize_chunks(chunks)
            
            logger.info(f"\n[3d] Creating Faiss index...")
            index = self.create_faiss_index(embeddings, len(chunks))
            
            logger.info(f"\n[3e] Saving Faiss index...")
            index_path = self.save_index(index, snapshot_date)
            
            logger.info(f"\n[3f] Saving metadata...")
            metadata_path = self.save_metadata(chunks, events, snapshot_date)
            
            logger.info(f"\n{'='*70}")
            logger.info("✅ VECTORIZATION PIPELINE - COMPLETE")
            logger.info(f"{'='*70}")
            logger.info(f"Index: {index_path}")
            logger.info(f"Metadata: {metadata_path}")
            
            return index_path, metadata_path
        
        except Exception as e:
            logger.error(f"\n❌ VECTORIZATION PIPELINE - FAILED")
            logger.error(f"Error: {e}")
            raise
            print(f"✅ Indexed {len(chunks)} chunks in Faiss")

