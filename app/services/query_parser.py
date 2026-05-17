import re
import logging
import pandas as pd
from datetime import datetime, timedelta
from calendar import monthrange
from typing import Optional, Dict, Tuple, List
from app.config import normalize_str


logger = logging.getLogger(__name__)

GEO_PREPOSITIONS = [
    r'a\s+',                     # à/a Toulouse (après normalize_str, à → a)
    r'dans\s+',                  # dans Lyon
    r'sur\s+',                   # sur Paris
    r'autour\s+de\s+',           # autour de Nantes
    r'pres\s+de\s+',             # près de (normalisé)
    r'en\s+',                    # en Occitanie
    r'ville\s+de\s+',            # ville de Montpellier
    r'commune\s+de\s+',          # commune de ...
    r'region\s+de\s+',           # région de (normalisé)
    r'departement\s+du\s+',      # département du Gard
    r'departement\s+de\s+la\s+', # département de la Loire
    r'departement\s+de\s+l\s+',  # département de l'Hérault (normalisé → l espace)
    r'departement\s+des\s+',     # département des Hautes-Pyrénées
    r'departement\s+de\s+',      # département de ...
]

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
    
        
    def parse_date(self,query: str) -> Tuple[datetime, int, str]:
        """
        Extracts start date and duration (tolerance) from the query.
        Uses snapshot date as reference for development reproducibility.
        
        Returns:
            Tuple[datetime, int, str]: target_date, tolerance, cleaned_query

        """

        months = ['janvier', 'fevrier', 'mars', 'avril', 'mai', 'juin', 
                  'juillet', 'aout', 'septembre', 'octobre', 'novembre', 'decembre']
        normalized_query = normalize_str(query) # Fix: Handle accents like "fevrier" 
        
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
                cleaned = normalized_query.replace((match.group()).strip(),"")
                return precise_day if precise_day >= today else datetime(aa + 1, mm, dd), 0, cleaned.strip()

        # 2. Numeric precise date (e.g., "le 15/03") 
        match = re.search(r'\ble\s+(0?[1-9]|[12][0-9]|3[01])[\/\- ](0?[1-9]|1[0,1,2])[\/\-\s ](?:20|)([234][0-9]|)', normalized_query + " ")
        if match:
            dd = int(match.group(1))
            mm = int(match.group(2))
            aa = int("20" + match.group(3) if match.group(3) else today.strftime('%Y'))
            precise_day = datetime(aa, mm, dd)
            cleaned = normalized_query.replace((match.group()).strip(),"")
            return precise_day if precise_day >= today else datetime(aa + 1, mm, dd), 0, cleaned.strip()

        # 3. Today / Tonight keywords 
        match = re.search(r'\b(ce soir|aujourd\'hui|ce jour|ce matin|cet apres[\- ]midi)\b', normalized_query)
        if match:
            cleaned = normalized_query.replace((match.group()).strip(),"")
            return today, 0, cleaned.strip()
        
        # 4. Tomorrow keyword 
        match = re.search(r'\b(demain)\b', normalized_query)
        if match:
            cleaned = normalized_query.replace((match.group()).strip(),"")
            return today + timedelta(days=1), 0, cleaned.strip()
        
        # 5. Relative days (e.g., "dans 3 jours") 
        match = re.search(r'\bdans\s+(\d+)\s+(jour|jours)\b', normalized_query)
        if match:
            days = int(match.group(1))
            cleaned = normalized_query.replace((match.group()).strip(),"")
            return today + timedelta(days=days), 0, cleaned.strip()
        
        # 6. Next weekend logic 
        match = re.search(r'\b(week[\- ]?end)\sprochain', normalized_query)
        if match:
            days_until_friday = (4 - today.weekday()) % 7 
            cleaned = normalized_query.replace((match.group()).strip(),"")
            return today + timedelta(days=days_until_friday + 7), 2, cleaned.strip()
        
        # 7. Current weekend logic 
        match = re.search(r'\b(ce week[\- ]?end)\b', normalized_query)
        if match:
            days_until_friday = (4 - today.weekday()) % 7 
            cleaned = normalized_query.replace((match.group()).strip(),"")
            return today + timedelta(days=days_until_friday), 2, cleaned.strip()
        
        # 8. Next week logic 
        match = re.search(r'\b(semaine\sprochaine)\b', normalized_query)
        if match:
            days_until_monday = (-today.weekday()) % 7 or 7
            cleaned = normalized_query.replace((match.group()).strip(),"")
            return today + timedelta(days=days_until_monday), 6, cleaned.strip()
        
        # 9. Current week logic 
        match = re.search(r'\b(?:cette|la)\s(semaine)\b', normalized_query)
        if match:
            days_until_sunday = (6 - today.weekday()) % 7 
            cleaned = normalized_query.replace((match.group()).strip(),"")
            return today, days_until_sunday, cleaned.strip()

        # 10. Whole month logic (e.g., "en mars") 
        for index, month in enumerate(months):
            match = re.search(fr"\b(?:mois de\s|mois d'|en\s)({month})\b", normalized_query)
            if match:
                index_month = index + 1 
                index_year = today.year if index_month >= today.month else today.year + 1
                first_day = datetime(index_year, index_month, 1)
                first_day = max(first_day, today)
                _, days_in_month = monthrange(first_day.year, first_day.month)
                tolerance = days_in_month - first_day.day
                cleaned = normalized_query.replace((match.group()).strip(),"")
                return first_day, tolerance, cleaned.strip()

        # Default fallback: next 30 days 
        return today, 30, normalized_query

    def _build_geo_pattern(self, name_norm: str) -> str:
        """
        Builds a regex pattern that matches a city or department name
        only when preceded by a geographic preposition.
        This prevents false positives where a city name (e.g. 'Yves', 'Mont')
        appears as a common word or proper noun unrelated to location.

        Args:
            name_norm (str): Normalized location name (lowercase, no accents).

        Returns:
            str: Regex pattern with geographic context requirement.
        """
        prepositions_pattern = '|'.join(GEO_PREPOSITIONS)
        return rf'(?:{prepositions_pattern}){re.escape(name_norm)}\b'

    def parse_geo(self, query: str) -> Dict[str, Optional[str]]:
        """
        Extracts geographic constraints and returns the query cleaned
        of all geographic expressions (preposition + location name).

        Returns:
            dict: {
                'city'   : str|None,
                'dept'   : str|None,
                'cleaned': str  # query with geo spans removed
            }
        """
        q = normalize_str(query)
        cleaned_q = q
        found_city = None
        found_dept = None

        for city in self.cities:
            norm_city = normalize_str(city)
            pattern   = self._build_geo_pattern(norm_city)
            match     = re.search(pattern, q)
            if match:
                found_city = norm_city
                cleaned_q  = cleaned_q.replace(match.group(), " ")
                break

        for dept in self.departments:
            norm_dept = normalize_str(dept)
            pattern   = self._build_geo_pattern(norm_dept)
            match     = re.search(pattern, q)
            if match:
                found_dept = norm_dept
                cleaned_q  = cleaned_q.replace(match.group(), " ")
                break

        return {
            "city":    found_city,
            "dept":    found_dept,
            "cleaned": re.sub(r'\s{2,}', ' ', cleaned_q).strip()
        }