#!/usr/bin/env python3
"""
Unit tests for Phase 2 data quality validation.

Tests verify that:
1. All events have at least some location information
2. All events have valid timings in the last 365 days
3. Required fields are present and non-empty
4. Data is properly structured after preprocessing

Usage:
    python -m pytest tests/test_data_quality.py -v
    or
    python tests/test_data_quality.py
"""

import unittest
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.vector.preprocessing import EventPreprocessor


class TestDataQuality(unittest.TestCase):
    """Test suite for processed event data quality"""
    
    @classmethod
    def setUpClass(cls):
        """Load processed data once for all tests"""
        # Use development snapshot
        snapshot_date = Config.DEV_SNAPSHOT_DATE
        processed_path = Config.get_processed_snapshot_path(snapshot_date)
        
        if not Path(processed_path).exists():
            raise FileNotFoundError(
                f"Processed snapshot not found: {processed_path}\n"
                f"Run: python scripts/run_fetch_pipeline.py "
                f"--snapshot-date {snapshot_date}"
            )
        
        # Load processed data
        with open(processed_path, 'r', encoding='utf-8') as f:
            cls.events = json.load(f)
        
        cls.snapshot_date = datetime.fromisoformat(snapshot_date)
        # Make cutoff_date timezone-aware (UTC) for comparison with timing dates
        cls.cutoff_date = (cls.snapshot_date - timedelta(days=Config.DAYS_BACK)).replace(tzinfo=timezone.utc)
    
    # ============= BASIC STRUCTURE TESTS =============
    
    def test_data_is_not_empty(self):
        """Verify processed dataset contains events"""
        self.assertGreater(
            len(self.events),
            0,
            "Processed dataset is empty"
        )
    
    def test_all_events_are_dicts(self):
        """Verify all events are properly structured dictionaries"""
        for idx, event in enumerate(self.events):
            self.assertIsInstance(
                event,
                dict,
                f"Event {idx} is not a dictionary: {type(event)}"
            )
    
    # ============= REQUIRED FIELDS TESTS =============
    
    def test_all_events_have_required_fields(self):
        """Verify all events have required fields"""
        required_fields = [
            Config.UID,
            Config.TITLE,
            Config.DESC,
            Config.LONG_DESC,
            Config.TIMINGS,
            Config.LOC_NAME,
            Config.LOC_CITY,
            Config.CONDITIONS,
            Config.URL
        ]
        
        for idx, event in enumerate(self.events):
            for field in required_fields:
                self.assertIn(
                    field,
                    event,
                    f"Event {idx} ({event.get(Config.UID, 'UNKNOWN')}) "
                    f"missing required field: {field}"
                )
    
    def test_all_events_have_uid(self):
        """Verify all events have non-empty UID"""
        for idx, event in enumerate(self.events):
            uid = event.get(Config.UID, '')
            self.assertTrue(
                uid and len(str(uid)) > 0,
                f"Event {idx} has empty or missing UID"
            )
    
    def test_all_events_have_title(self):
        """Verify all events have non-empty French title"""
        for idx, event in enumerate(self.events):
            title = event.get(Config.TITLE, '')
            self.assertTrue(
                title and len(str(title).strip()) > 0,
                f"Event {idx} ({event.get(Config.UID)}) has empty title"
            )
    
    def test_all_events_have_location(self):
        """Verify all events have at least some location information"""
        for idx, event in enumerate(self.events):
            location_city = event.get(Config.LOC_CITY, '')
            location_name = event.get(Config.LOC_NAME, '')
            location_address = event.get(Config.LOC_ADDRESS, '')
            
            # At least one location field must have content
            has_location = (
                (location_city and len(str(location_city).strip()) > 0) or
                (location_name and len(str(location_name).strip()) > 0) or
                (location_address and len(str(location_address).strip()) > 0)
            )
            
            self.assertTrue(
                has_location,
                f"Event {idx} ({event.get(Config.UID)}) has no location information "
                f"(city, name, address all empty)"
            )
    
    # ============= TIMING VALIDATION TESTS =============
    
    def test_all_events_have_timings(self):
        """Verify all events have at least one timing"""
        for idx, event in enumerate(self.events):
            timings = event.get(Config.TIMINGS, [])
            self.assertIsInstance(
                timings,
                list,
                f"Event {idx} ({event.get(Config.UID)}) timings is not a list"
            )
            self.assertGreater(
                len(timings),
                0,
                f"Event {idx} ({event.get(Config.UID)}) has no timings"
            )
    
    def test_all_timings_have_begin_and_end(self):
        """Verify all timing entries have begin and end dates"""
        for event_idx, event in enumerate(self.events):
            timings = event.get(Config.TIMINGS, [])
            
            for timing_idx, timing in enumerate(timings):
                self.assertIn(
                    'begin',
                    timing,
                    f"Event {event_idx} ({event.get(Config.UID)}) "
                    f"timing {timing_idx} missing 'begin'"
                )
                self.assertIn(
                    'end',
                    timing,
                    f"Event {event_idx} ({event.get(Config.UID)}) "
                    f"timing {timing_idx} missing 'end'"
                )
    
    def test_all_events_have_recent_timings(self):
        """Verify all events have at least one timing in last 365 days"""
        for idx, event in enumerate(self.events):
            timings = event.get(Config.TIMINGS, [])
            begin_str = ""  # initialization to satisfy the linter
            has_recent = False
            for timing in timings:
                try:
                    begin_str = timing.get('begin', '')
                    # Parse ISO format datetime (with timezone awareness)
                    timing_date = datetime.fromisoformat(
                        begin_str.replace('Z', '+00:00')
                    )
                    
                    if timing_date >= self.cutoff_date:
                        has_recent = True
                        break
                except (ValueError, AttributeError) as e:
                    self.fail(
                        f"Event {idx} ({event.get(Config.UID)}) "
                        f"has unparseable date: {begin_str} - {str(e)}"
                    )
            
            self.assertTrue(
                has_recent,
                f"Event {idx} ({event.get(Config.UID)}) has no timings "
                f"in last 365 days (cutoff: {self.cutoff_date.date()})"
            )
    
    # ============= TEXT CONTENT VALIDATION TESTS =============
    
    def test_all_events_have_sufficient_text_content(self):
        """Verify all events have minimum text length for embedding"""
        min_length = 10  # Matches preprocessing validation
        
        for idx, event in enumerate(self.events):
            title = str(event.get(Config.TITLE, ''))
            description = str(event.get(Config.DESC, ''))
            longdesc = str(event.get(Config.LONG_DESC, ''))
            
            total_length = len(title) + len(description) + len(longdesc)
            
            self.assertGreaterEqual(
                total_length,
                min_length,
                f"Event {idx} ({event.get(Config.UID)}) "
                f"has insufficient text: {total_length} chars "
                f"(min: {min_length})"
            )
    
    def test_no_html_tags_in_descriptions(self):
        """Verify descriptions don't contain uncleaned HTML"""
        html_indicators = ['<html', '<div', '<script', '<iframe']
        
        for idx, event in enumerate(self.events):
            description = str(event.get(Config.DESC, '')).lower()
            longdesc = str(event.get(Config.LONG_DESC, '')).lower()
            
            for indicator in html_indicators:
                self.assertNotIn(
                    indicator,
                    description,
                    f"Event {idx} ({event.get(Config.UID)}) "
                    f"has uncleaned HTML in description_fr: {indicator}"
                )
                self.assertNotIn(
                    indicator,
                    longdesc,
                    f"Event {idx} ({event.get(Config.UID)}) "
                    f"has uncleaned HTML in longdescription_fr: {indicator}"
                )
    
    # ============= UNIQUENESS TESTS =============
    
    def test_all_uids_are_unique(self):
        """Verify no duplicate events by UID"""
        uids = [event.get(Config.UID) for event in self.events]
        unique_uids = set(uids)
        
        self.assertEqual(
            len(uids),
            len(unique_uids),
            f"Found {len(uids) - len(unique_uids)} duplicate UIDs"
        )
    
    # ============= DATA TYPE TESTS =============
    
    def test_coordinates_are_numeric(self):
        """Verify lat/lon coordinates are numeric when present"""
        for idx, event in enumerate(self.events):
            lat = event.get('location_lat')
            lon = event.get('location_lon')
            
            if lat is not None:
                self.assertTrue(
                    isinstance(lat, (int, float)),
                    f"Event {idx} ({event.get(Config.UID)}) "
                    f"has non-numeric latitude: {type(lat)}"
                )
            
            if lon is not None:
                self.assertTrue(
                    isinstance(lon, (int, float)),
                    f"Event {idx} ({event.get(Config.UID)}) "
                    f"has non-numeric longitude: {type(lon)}"
                )
    
    def test_url_fields_are_strings(self):
        """Verify URL fields are strings"""
        for idx, event in enumerate(self.events):
            url = event.get(Config.URL, '')
            self.assertIsInstance(
                url,
                str,
                f"Event {idx} ({event.get(Config.UID)}) "
                f"has non-string URL: {type(url)}"
            )
    
    # ============= SUMMARY STATISTICS =============
    
    def test_print_data_summary(self):
        """Print summary statistics about processed data"""
        print("\n" + "="*70)
        print("DATA QUALITY SUMMARY")
        print("="*70)
        print(f"Tested file date:     {Config.DEV_SNAPSHOT_DATE}")
        print("="*70)
        print(f"Total events:         {len(self.events)}")
        
        # Region distribution
        cities = {}
        for event in self.events:
            city = event.get(Config.LOC_CITY, 'Unknown')
            cities[city] = cities.get(city, 0) + 1
        
        print(f"Unique cities:        {len(cities)}")
        top_cities = sorted(cities.items(), key=lambda x: x[1], reverse=True)[:5]
        for city, count in top_cities:
            print(f"  - {city}: {count}")
        
        # Text length stats
        text_lengths = []
        for event in self.events:
            title = str(event.get(Config.TITLE, ''))
            description = str(event.get(Config.DESC, ''))
            longdesc = str(event.get(Config.LONG_DESC, ''))
            total = len(title) + len(description) + len(longdesc)
            text_lengths.append(total)
        
        print(f"\nText content stats:")
        print(f"  - Min length:       {min(text_lengths)} chars")
        print(f"  - Max length:       {max(text_lengths)} chars")
        print(f"  - Avg length:       {sum(text_lengths)//len(text_lengths)} chars")
        
        # Timing stats
        total_timings = sum(len(e.get(Config.TIMINGS, [])) for e in self.events)
        print(f"\nTiming stats:")
        print(f"  - Total occurrences: {total_timings}")
        print(f"  - Avg per event:    {total_timings//len(self.events)}")
        
        print("="*70 + "\n")


class TestPreprocessingPipeline(unittest.TestCase):
    """Test preprocessing pipeline execution"""
    
    def test_preprocessor_initialization(self):
        """Verify preprocessor can be initialized"""
        snapshot_date = Config.DEV_SNAPSHOT_DATE
        raw_path = Config.get_raw_snapshot_path(snapshot_date)
        
        if not Path(raw_path).exists():
            self.skipTest(f"Raw snapshot not found: {raw_path}")
        
        preprocessor = EventPreprocessor(raw_path)
        self.assertIsNotNone(preprocessor)
        self.assertGreater(len(preprocessor.df), 0)
    
    def test_pipeline_produces_output(self):
        """Verify preprocessing pipeline produces output file"""
        snapshot_date = Config.DEV_SNAPSHOT_DATE
        processed_path = Config.get_processed_snapshot_path(snapshot_date)
        
        self.assertTrue(
            Path(processed_path).exists(),
            f"Processed data file not found: {processed_path}\n"
            f"Run: python scripts/run_fetch_pipeline.py "
            f"--snapshot-date {snapshot_date}"
        )
    
    def test_processed_file_is_valid_json(self):
        """Verify processed data is valid JSON"""
        snapshot_date = Config.DEV_SNAPSHOT_DATE
        processed_path = Config.get_processed_snapshot_path(snapshot_date)
        
        try:
            with open(processed_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertIsInstance(data, list)
            self.assertGreater(len(data), 0)
        except json.JSONDecodeError as e:
            self.fail(f"Processed file is not valid JSON: {str(e)}")


def main():
    """Run all tests with verbose output"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestDataQuality))
    suite.addTests(loader.loadTestsFromTestCase(TestPreprocessingPipeline))
    
    # Run with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return appropriate exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)