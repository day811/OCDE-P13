import unittest
from app.services.processor import EventProcessor

class TestEventProcessorUnit(unittest.TestCase):
    """Unit tests for the EventProcessor logic."""

    def setUp(self):
        self.processor = EventProcessor()
        self.valid_raw_event = {
            "uid": "12345",
            "updatedat": "2025-01-01T10:00:00Z",
            "title_fr": "Concert de Jazz",
            "description_fr": "<p>Un concert <b>exceptionnel</b>.</p>",
            "location_city": "Montpellier",
            "timings": '[{"start": "2025-06-01T20:00:00Z", "end": "2025-06-01T22:00:00Z"}]'
        }

    def test_transform_success(self):
        """Test successful transformation and HTML cleaning."""
        result = self.processor.transform(self.valid_raw_event)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "12345")
        # Check if HTML tags were removed 
        self.assertIn("DESCRIPTION: Un concert exceptionnel", result["content"])
        # Check if timings were parsed 
        self.assertIsInstance(result["metadata"]["timings"], str)

    def test_transform_missing_required_field(self):
        """Test that Pydantic rejects events missing mandatory fields like 'uid'."""
        invalid_event = self.valid_raw_event.copy()
        del invalid_event["uid"]
        result = self.processor.transform(invalid_event)
        self.assertIsNone(result) 

    def test_clean_text_utility(self):
        """Test only the HTML cleaning utility."""
        html = "<div>Hello <span>World</span></div>"
        cleaned = self.processor.clean_text(html)
        self.assertEqual(cleaned, "Hello World") 

if __name__ == "__main__":
    unittest.main()