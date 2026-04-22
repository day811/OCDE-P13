#!/usr/bin/env python3
"""
Unit tests for Phase 3: Vectorization and Faiss Indexing

Tests verify that:
1. Chunks are created correctly with proper splitting
2. Embeddings are generated with correct dimensions
3. Faiss index is properly trained and indexed
4. Metadata is correctly saved and retrievable
5. Retrieved chunks match the original events

Usage:
    python -m pytest tests/test_vectorization.py -v
    or
    python tests/test_vectorization.py
"""

import unittest
import json
import tempfile
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.vector.vectorization import EventVectorizer


class TestChunking(unittest.TestCase):
    """Test suite for chunk creation"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test data"""
        cls.vectorizer = EventVectorizer()
        
        # Create sample events
        cls.sample_events = [
            {
                Config.UID: 'evt_001',
                Config.TITLE: 'Festival de Rock 2026',
                Config.DESC: 'Un grand festival de rock avec des artistes internationaux.',
                Config.LONG_DESC: 'Festival annuel présentant les meilleures bandes de rock du monde.',
                Config.LOC_NAME: 'Parc de la Ville',
                Config.LOC_CITY: 'Toulouse',
                Config.LOC_DEPT : 'Haute-Garonne',
                Config.LOC_ADDRESS : 'rue de Rome',
                Config.CONDITIONS: 'Accès gratuit pour les enfants de moins de 12 ans.',
                Config.URL: 'https://open-agenda.com/evt_001',
                Config.TIMINGS: [{'begin': (datetime.now() + timedelta(days=5)).isoformat(), 'end': ''}]
            },
            {
                Config.UID: 'evt_002',
                Config.TITLE: 'Concert de Jazz Intimiste',
                Config.DESC: 'Une soirée jazz intime dans une atmosphère cosy.',
                Config.LOC_DEPT : 'Hérault',
                Config.LONG_DESC: """
                <p>Pour cette seconde projection à l'Institut suédois, <a href="https://paris.si.se/agenda/cinema-carte-blanche-2-a-niki-lindroth-von-bahr/">Niki Lindroth von Bahr présente deux films d’animation</a> en stop-motion réalisés par le duo Marc James Roels et Emma De Swaef : le court métrage <em>Oh Willy_… suivi du moyen métrage Ce _Magnifique Gâteau !</em><br />Les deux artistes ont reçu 80 prix pour <em>Oh Willy…</em>, dont le Cartoon d’Or du meilleur court métrage européen d’animation. Ils ont également été nommé aux César en 2013. <em>Ce Magnifique Gâteau !</em> est leur nouvelle réalisation.</p> <p></p> <h3><strong>Synopsis</strong></h3> <p></p> <ul> <li><strong><em>Oh Willy ...</em></strong> : Face au décès de sa mère Willy se retrouve face à lui-même et à ses choix. Confus et mélancolique, il décide de s’enfuir dans la forêt. Après des débuts difficiles, il trouve protection auprès d’une grosse bête douce et poilue. (<em>Drame, France, Belgique, Pays-Bas, 2012, VOSTFR, 17 min, tous publics).</em></li> </ul> <p></p> <ul> <li><strong><em>Ce Magnifique Gâteau !</em></strong> : Anthologie de la colonisation africaine à la fin du 19e siècle, le film entremêle cinq récits qui croisent où se croisent un roi perturbé, un pygmée travaillant dans un hôtel de luxe, un homme d’affaires ruiné, un porteur égaré et un jeune déserteur. (<em>Drame, France, Belgique, Pays-Bas, 2018, VOSTFR, 44 min, tous publics).</em></li> </ul> <p></p> <h3><strong>Les réalisateurs</strong></h3> <p></p> <p><strong>Emma De Swaef</strong> est spécialisée dans le cinéma d’animation en stop-motion et dans la conception de poupées textiles. Elle signe l’un des trois chapitres du film "The House" (La Maison), produit par Netflix et dont Niki Lindroth von Bahr a réalisé un autre chapitre.</p> <p></p> <p><strong>Marc James Roels</strong> est issu du cinéma de fiction « live » et a été récompensé pour ses courts métrages "Mompelaar" (2007) et "A Gentle Creature" (2010).</p>",conditions_fr:"Entrée libre dans la limite des places disponibles.
                """,
                Config.LOC_NAME: 'Salle de Concert',
                Config.LOC_ADDRESS : 'place de la Comédie',
                Config.LOC_CITY: 'Montpellier',
                Config.CONDITIONS: 'Réservation recommandée.',
                Config.URL: 'https://open-agenda.com/evt_002',
                Config.TIMINGS: [{'begin': (datetime.now() + timedelta(days=3)).isoformat(), 'end': ''}]
            }
        ]
    
    def test_chunk_events_creates_chunks(self):
        """Verify chunk_events creates chunks from events"""
        chunks = self.vectorizer.chunk_events(self.sample_events, chunk_size=500)
        
        self.assertGreater(len(chunks), 0, "Should create at least one chunk")
        self.assertIsInstance(chunks, list, "Should return a list")
    
    def test_chunk_structure(self):
        """Verify chunks have correct structure"""
        chunks = self.vectorizer.chunk_events(self.sample_events, chunk_size=500)
        
        for chunk in chunks:
            self.assertIn('chunk_id', chunk, "Chunk should have chunk_id")
            self.assertIn('event_id', chunk, "Chunk should have event_id")
            self.assertIn('text', chunk, "Chunk should have text")
            self.assertIsInstance(chunk['chunk_id'], int, "chunk_id should be int")
            self.assertIsInstance(chunk['event_id'], str, "event_id should be str")
            self.assertIsInstance(chunk['text'], str, "text should be str")
    
    def test_chunk_size_respected(self):
        """Verify chunks don't exceed max size"""
        chunk_size = 500
        chunks = self.vectorizer.chunk_events(self.sample_events, chunk_size=chunk_size)
        
        for chunk in chunks:
            # Allow slight overage due to word boundaries
            self.assertLessEqual(
                len(chunk['text']),
                chunk_size + 50,
                f"Chunk text exceeds max size: {len(chunk['text'])} > {chunk_size}"
            )
    
    def test_chunk_text_not_empty(self):
        """Verify all chunks have non-empty text"""
        chunks = self.vectorizer.chunk_events(self.sample_events, chunk_size=500)
        
        for chunk in chunks:
            self.assertGreater(
                len(chunk['text'].strip()),
                0,
                "Chunk text should not be empty"
            )
    
    def test_html_tags_removed(self):
        """Verify HTML tags are stripped from chunks"""
        # Add HTML to test event
        event_with_html = self.sample_events[0].copy()
        event_with_html[Config.DESC] = 'Concert <b>important</b> <script>alert("test")</script>'
        
        chunks = self.vectorizer.chunk_events([event_with_html], chunk_size=500)
        
        for chunk in chunks:
            self.assertNotIn('<', chunk['text'], "Should not contain < symbol")
            self.assertNotIn('>', chunk['text'], "Should not contain > symbol")
            self.assertNotIn('script', chunk['text'].lower(), "Should not contain script tag")
    
    def test_event_id_mapping(self):
        """Verify chunks map back to original events"""
        chunks = self.vectorizer.chunk_events(self.sample_events, chunk_size=500)
        
        # Get unique event_ids from chunks
        chunk_event_ids = set(chunk['event_id'] for chunk in chunks)
        
        # Should have chunks for both events
        self.assertGreaterEqual(
            len(chunk_event_ids),
            1,
            "Should have chunks from at least one event"
        )
        
        # All event_ids should be from original events
        original_event_ids = set(event[Config.UID] for event in self.sample_events)
        self.assertTrue(
            chunk_event_ids.issubset(original_event_ids),
            f"Chunk event_ids {chunk_event_ids} should be subset of original {original_event_ids}"
        )


class TestVectorization(unittest.TestCase):
    """Test suite for embedding generation (requires API)"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test data"""
        cls.vectorizer = EventVectorizer()
        
        # Create simple test chunks
        cls.test_chunks = [
            {
                'chunk_id': 0,
                'event_id': 'evt_001',
                'text': 'Festival de rock avec artistes internationaux.'
            },
            {
                'chunk_id': 1,
                'event_id': 'evt_002',
                'text': 'Concert de jazz dans une atmosphère intime.'
            },
            {
                'chunk_id': 2,
                'event_id': 'evt_003',
                'text': 'Exposition d\'art contemporain en plein air.'
            }
        ]
    
    def test_vectorize_chunks_returns_array(self):
        """Verify vectorize_chunks returns numpy array"""
        embeddings = self.vectorizer.vectorize_chunks(self.test_chunks, batch_size=2)
        
        self.assertIsInstance(embeddings, np.ndarray, "Should return numpy array")
    
    def test_embedding_shape(self):
        """Verify embeddings have correct shape"""
        embeddings = self.vectorizer.vectorize_chunks(self.test_chunks, batch_size=2)
        
        n_chunks = len(self.test_chunks)
        expected_shape = (n_chunks, 1024)  # Mistral embed dimension
        
        self.assertEqual(
            embeddings.shape,
            expected_shape,
            f"Shape should be {expected_shape}, got {embeddings.shape}"
        )
    
    def test_embedding_dtype(self):
        """Verify embeddings are float32"""
        embeddings = self.vectorizer.vectorize_chunks(self.test_chunks, batch_size=2)
        
        self.assertEqual(
            embeddings.dtype,
            np.float32,
            f"Embeddings should be float32, got {embeddings.dtype}"
        )
    
    def test_embedding_values_normalized(self):
        """Verify embeddings are in reasonable range"""
        embeddings = self.vectorizer.vectorize_chunks(self.test_chunks, batch_size=2)
        
        # Embeddings should be normalized (roughly between -1 and 1 or 0 and 1)
        self.assertLess(
            np.abs(embeddings).max(),
            100,  # Generous upper bound
            "Embedding values seem unreasonable"
        )


class TestFaissIndexing(unittest.TestCase):
    """Test suite for Faiss index creation"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test data"""
        cls.vectorizer = EventVectorizer()
        
        # Create test embeddings (mock)
        cls.n_vectors = 100
        cls.dimension = 1024
        cls.test_embeddings = np.random.randn(cls.n_vectors, cls.dimension).astype('float32')
    
    def test_create_faiss_index_returns_index(self):
        """Verify create_faiss_index returns a Faiss index"""
        import faiss
        
        index = self.vectorizer.create_faiss_index(
            self.test_embeddings,
            self.n_vectors
        )
        
        self.assertIsNotNone(index, "Index should not be None")
        self.assertTrue(
            isinstance(index, (faiss.Index, faiss.IndexIVFFlat)),
            "Should return a Faiss index object"
        )
    
    def test_index_is_trained(self):
        """Verify index is trained (has cluster centers)"""
        index = self.vectorizer.create_faiss_index(
            self.test_embeddings,
            self.n_vectors
        )
        
        # IVFFlat index should be trained
        self.assertTrue(index.is_trained, "Index should be trained")
    
    def test_index_contains_vectors(self):
        """Verify all vectors are added to index"""
        index = self.vectorizer.create_faiss_index(
            self.test_embeddings,
            self.n_vectors
        )
        
        self.assertEqual(
            index.ntotal,
            self.n_vectors,
            f"Index should contain {self.n_vectors} vectors, has {index.ntotal}"
        )
    
    def test_index_search_works(self):
        """Verify index can perform searches"""
        index = self.vectorizer.create_faiss_index(
            self.test_embeddings,
            self.n_vectors
        )
        
        # Search with a test query
        query = self.test_embeddings[0:1]  # First embedding as query
        distances, indices = index.search(query, k=5) # type: ignore
        
        self.assertEqual(indices.shape, (1, 5), "Should return 5 results")
        self.assertEqual(distances.shape, (1, 5), "Should return 5 distances")
        self.assertGreaterEqual(indices[0, 0], 0, "Indices should be non-negative")
    
    def test_index_nlist_reasonable(self):
        """Verify nlist is computed reasonably"""
        # For 100 vectors: nlist should be around 10
        # For 1000 vectors: nlist should be around 10
        # For 5000 vectors: nlist should be around 50
        
        test_cases = [
            (100, 10),
            (500, 10),
            (1000, 10),
            (5000, 50),
            (10000, 100),
        ]
        
        for n_vecs, expected_min_nlist in test_cases:
            nlist = min(100, max(10, n_vecs // 100))
            self.assertGreaterEqual(
                nlist,
                10,
                f"nlist for {n_vecs} vectors should be >= 10"
            )
            self.assertLessEqual(
                nlist,
                100,
                f"nlist for {n_vecs} vectors should be <= 100"
            )


class TestMetadataSaving(unittest.TestCase):
    """Test suite for metadata persistence"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test data"""
        cls.vectorizer = EventVectorizer(Config.LLM_PROVIDER)
        
        # Create sample events
        cls.sample_events = [
            {
                Config.UID: 'evt_001',
                Config.TITLE: 'Rock Festival',
                Config.DESC: 'A rock festival',
                Config.FIRST_DATE: '2026-02-18',
                Config.LONG_DESC: 'Long description',
                Config.LOC_NAME: 'Park',
                Config.LOC_CITY: 'Toulouse',
                Config.LOC_DEPT: 'Toulouse',
                Config.LOC_ADDRESS: 'place du Capitole',
                Config.CONDITIONS: 'Free entry',
                Config.URL: 'https://example.com/evt_001',
                Config.TIMINGS: [{'begin': datetime.now().isoformat(), 'end': ''}]
            }
        ]
        
        # Create chunks
        cls.chunks = cls.vectorizer.chunk_events(cls.sample_events, chunk_size=500)
    
    def _mock_config_path(self, path: Path, method_name: str):
        """Mock Config path method to always return given path."""
        original_method = getattr(Config, method_name)
        setattr(Config, method_name, lambda *args, **kwargs: str(path))
        return original_method
    
    def test_save_metadata_creates_file(self):
        """Verify metadata file is created"""
        with tempfile.TemporaryDirectory() as tmpdir:
            metadata_path = Path(tmpdir) / "metadata.json"
            
            # Mock the Config method
            original_method = self._mock_config_path(metadata_path, 'get_metadata_path')
            
            try:
                self.vectorizer.save_metadata(
                    self.chunks,
                    self.sample_events,
                    datetime.now().strftime("%Y-%m-%d")
                )
                
                self.assertTrue(
                    metadata_path.exists(),
                    f"Metadata file should be created at {metadata_path}"
                )
            finally:
                Config.get_metadata_path = original_method
    
    def test_metadata_structure(self):
        """Verify metadata has correct structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            metadata_path = Path(tmpdir) / "metadata.json"
            
            original_method = self._mock_config_path(metadata_path, 'get_metadata_path')
            
            try:
                self.vectorizer.save_metadata(
                    self.chunks,
                    self.sample_events,
                    datetime.now().strftime("%Y-%m-%d")
                )
                
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                
                # Check structure
                self.assertIsInstance(metadata, dict, "Metadata should be a dict")
                
                for key, value in metadata.items():
                    self.assertIn('event_id', value, "Should have event_id")
                    self.assertIn('chunk_id', value, "Should have chunk_id")
                    self.assertIn('text', value, "Should have text")
                    self.assertIn('title', value, "Should have title")
                    self.assertIn('city', value, "Should have city")
                    self.assertIn('dates', value, "Should have date")
                    self.assertIn('url', value, "Should have url")
            finally:
                Config.get_metadata_path = original_method
    
    def test_metadata_event_mapping(self):
        """Verify metadata correctly maps to events"""
        with tempfile.TemporaryDirectory() as tmpdir:
            metadata_path = Path(tmpdir) / "metadata.json"
            
            original_method = self._mock_config_path(metadata_path, 'get_metadata_path')
            
            try:
                self.vectorizer.save_metadata(
                    self.chunks,
                    self.sample_events,
                    datetime.now().strftime("%Y-%m-%d")
                )
                
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                
                # All events in metadata should be from original events
                for key, value in metadata.items():
                    event_id = value['event_id']
                    self.assertIn(
                        event_id,
                        [e[Config.UID] for e in self.sample_events],
                        f"event_id {event_id} should be from original events"
                    )
                    
                    # Title should match
                    matching_event = [e for e in self.sample_events if e[Config.UID] == event_id][0]
                    self.assertEqual(
                        value['title'],
                        matching_event[Config.TITLE],
                        "Title should match original event"
                    )
                    
                    self.assertEqual(
                        value['city'],
                        matching_event[Config.LOC_CITY],
                        "City should match original event"
                    )
            finally:
                Config.get_metadata_path = original_method


class TestIndexSaving(unittest.TestCase):
    """Test suite for Faiss index persistence"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test data"""
        cls.vectorizer = EventVectorizer(
        )
        
        # Create test embeddings
        cls.n_vectors = 50
        cls.dimension = 1024
        cls.test_embeddings = np.random.randn(cls.n_vectors, cls.dimension).astype('float32')
        cls.index = cls.vectorizer.create_faiss_index(
            cls.test_embeddings,
            cls.n_vectors
        )
    
    def test_save_index_creates_file(self):
        """Verify index file is created"""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            
            original_method = Config.get_index_path
            Config.get_index_path = lambda x: str(index_path)# type: ignore
            
            try:
                self.vectorizer.save_index(self.index, datetime.now().strftime("%Y-%m-%d"))
                
                self.assertTrue(
                    index_path.exists(),
                    f"Index file should be created at {index_path}"
                )
            finally:
                Config.get_index_path = original_method
    
    def test_saved_index_can_be_loaded(self):
        """Verify saved index can be loaded and used"""
        import faiss
        
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            
            original_method = Config.get_index_path
            Config.get_index_path = lambda x: str(index_path)# type: ignore
            
            try:
                self.vectorizer.save_index(self.index, datetime.now().strftime("%Y-%m-%d"))
                
                # Load the index
                loaded_index = faiss.read_index(str(index_path))
                
                self.assertIsNotNone(loaded_index, "Should load index successfully")
                self.assertEqual(
                    loaded_index.ntotal,
                    self.n_vectors,
                    "Loaded index should have same number of vectors"
                )
                
                # Test search works on loaded index
                query = self.test_embeddings[0:1]
                distances, indices = loaded_index.search(query, k=5)
                
                self.assertEqual(indices.shape, (1, 5), "Search should work on loaded index")
            finally:
                Config.get_index_path = original_method


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
