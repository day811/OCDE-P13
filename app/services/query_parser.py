import re
import logging
import pandas as pd
from datetime import datetime, timedelta
from calendar import monthrange
from typing import Optional, Dict, Tuple, List
import app.config 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QueryParser:
    """
    Complete Query Parser service for P13, fully restored from P11 functionality.
    Handles temporal relative dates, city/department extraction, and string normalization.
    """

    def __init__(self, cities: List[str], departments: List[str]):
        """
        Initializes parser with known locations from the dataset. 
        """
        self.cities = cities
        self.departments = departments
    
        
    @staticmethod
    def normalize_str(text: str) -> str:
        """
        Normalizes a string by converting to lowercase, stripping whitespace,
        and removing common French accents.
        
        """
        if not text:
            return ""
        
        normalized = text.strip().lower()
        # Mapping for French accent removal 
        accents = {
            'a': ['à', 'ã', 'á', 'â'],
            'e': ['é', 'è', 'ê', 'ë'],
            'i': ['î', 'ï'],
            'u': ['ù', 'ü', 'û'],
            'o': ['ô', 'ö'],
            ' ': ['-', '/']
        }
        for char, accented_chars in accents.items():
            for accented_char in accented_chars:
                normalized = normalized.replace(accented_char, char)
        return normalized


    def parse_date(self,query: str) -> Tuple[datetime, int]:
        """
        Extracts start date and duration (tolerance) from the query.
        Uses snapshot date as reference for development reproducibility.
        
        """
        months = ['janvier', 'fevrier', 'mars', 'avril', 'mai', 'juin', 
                  'juillet', 'aout', 'septembre', 'octobre', 'novembre', 'decembre']
        normalized_query = self.normalize_str(query) # Fix: Handle accents like "fevrier" 
        
        today = datetime.now()
        
        today = datetime(today.year, today.month, today.day)

        # 1. Precise date with month names (e.g., "le 15 mars") 
        for index, month in enumerate(months):
            match = re.search(fr'\ble\s+(0?[1-9]|[12][0-9]|3[01])[\/\- ]({month})[\/\-\s ](?:20|)([234][0-9]|)', normalized_query + " ")
            if match:
                dd = int(match.group(1))
                mm = index + 1
                aa = int("20" + match.group(3) if match.group(3) else today.strftime('%Y'))
                precise_day = datetime(aa, mm, dd)
                return (precise_day if precise_day >= today else datetime(aa + 1, mm, dd), 0)

        # 2. Numeric precise date (e.g., "le 15/03") 
        match = re.search(r'\ble\s+(0?[1-9]|[12][0-9]|3[01])[\/\- ](0?[1-9]|1[0,1,2])[\/\-\s ](?:20|)([234][0-9]|)', normalized_query + " ")
        if match:
            dd = int(match.group(1))
            mm = int(match.group(2))
            aa = int("20" + match.group(3) if match.group(3) else today.strftime('%Y'))
            precise_day = datetime(aa, mm, dd)
            return (precise_day if precise_day >= today else datetime(aa + 1, mm, dd), 0)

        # 3. Today / Tonight keywords 
        if re.search(r'\b(ce soir|aujourd\'hui|ce jour|ce matin|cet apres[\- ]midi)\b', normalized_query):
            return (today, 0)
        
        # 4. Tomorrow keyword 
        if re.search(r'\b(demain)\b', normalized_query):
            return (today + timedelta(days=1), 0)
        
        # 5. Relative days (e.g., "dans 3 jours") 
        match = re.search(r'\bdans\s+(\d+)\s+(jour|jours)\b', normalized_query)
        if match:
            days = int(match.group(1))
            return (today + timedelta(days=days), 0)
        
        # 6. Next weekend logic 
        if re.search(r'\b(week[\- ]?end)\sprochain', normalized_query):
            days_until_friday = (4 - today.weekday()) % 7 
            return (today + timedelta(days=days_until_friday + 7), 2)
        
        # 7. Current weekend logic 
        if re.search(r'\b(ce week[\- ]?end)\b', normalized_query):
            days_until_friday = (4 - today.weekday()) % 7 
            return (today + timedelta(days=days_until_friday), 2)
        
        # 8. Next week logic 
        if re.search(r'\b(semaine\sprochaine)\b', normalized_query):
            days_until_monday = (-today.weekday()) % 7 or 7
            return (today + timedelta(days=days_until_monday), 6)
        
        # 9. Current week logic 
        if re.search(r'\b(?:cette|la)\s(semaine)\b', normalized_query):
            days_until_sunday = (6 - today.weekday()) % 7 
            return (today, days_until_sunday)

        # 10. Whole month logic (e.g., "en mars") 
        for index, month in enumerate(months):
            if re.search(fr"\b(?:mois de\s|mois d'|en\s)({month})\b", normalized_query):
                index_month = index + 1 
                index_year = today.year if index_month >= today.month else today.year + 1
                first_day = datetime(index_year, index_month, 1)
                first_day = max(first_day, today)
                _, days_in_month = monthrange(first_day.year, first_day.month)
                tolerance = days_in_month - first_day.day
                return (first_day, tolerance)

        # Default fallback: next 30 days 
        return (today, 30)

    def parse_geo(self, query: str) -> Dict[str, Optional[str]]:
        """
        Matches query against the pre-loaded city and department lists. 
        """
        q = self.normalize_str(query)
        found_city = None
        found_dept = None

        # Check Cities
        for city in self.cities:
            if re.search(rf'\b{self.normalize_str(city)}\b', q):
                found_city = city
                break

        # Check Departments
        for dept in self.departments:
            if re.search(rf'\b{self.normalize_str(dept)}\b', q):
                found_dept = dept
                break

        return {"city": found_city, "dept": found_dept}