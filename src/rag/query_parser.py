# src/rag/query_parser.py
import re
from datetime import datetime, timedelta
from calendar import monthrange
from typing import Optional, Dict
from src.utils.utils import normalize_str
from src.config import Config
import pandas as pd

class QueryParser:
    """Extract date and city constraints from user questions"""
    
    CITIES = []
    DEPARTMENTS = []
    
    
    @staticmethod
    def parse_date(query: str, today = None) -> tuple[datetime,int]:
        
        """Extract date from query"""
        months = ['janvier',"fevrier", "mars", "avril", "mai","juin", "juillet","aout", "septembre", "octobre", "novembre", "decembre"]
        normalized_query = normalize_str(query)
        # En mode développement, repositionne aujourd'hui sur snapshot_date
        today = datetime.fromisoformat(today) if today and today == Config.DEV_SNAPSHOT_DATE else datetime.today()
        today = datetime(today.year,today.month,today.day)


        #On a precise date in %d %B (%y)
        for index, month in enumerate(months):
            match = re.search(fr'\ble\s+(0?[1-9]|[12][0-9]|3[01])[\/\- ]({month})[\/\-\s ](?:20|)([234][0-9]|)', normalized_query +" ")
            if match and match.lastindex >= 2: # pyright: ignore[reportOptionalOperand]
                dd = int(match[1])
                mm = int(index+1)
                aa = int("20" + match[3] if match[3] else datetime.now().strftime('%Y'))
                precise_day = datetime(aa,mm,dd)
                if precise_day < today : 
                    return (datetime(aa+1,mm,dd),0)
                else :
                    return (precise_day,0)
            
        #On a precise date in number %d %m (%y)
        match = re.search(r'\ble\s+(0?[1-9]|[12][0-9]|3[01])[\/\- ](0?[1-9]|1[0,1,2])[\/\-\s ](?:20|)([234][0-9]|)', normalized_query +" ")
        if match and match.lastindex >= 2: # pyright: ignore[reportOptionalOperand]
            dd = int(match[1])
            mm = int(match[2])
            aa = int("20" + match[3] if match[3] else datetime.now().strftime('%Y'))
            precise_day = datetime(aa,mm,dd)
            if precise_day < today : 
                return (datetime(aa+1,mm,dd),0)
            else :
                return (precise_day,0)

        # Today/tonight
        if re.search(r'\b(ce soir|aujourd\'hui|ce jour|ce matin|cet apres[\- ]midi)\b', normalized_query):
            return (today,0)
        
        # Tomorrow
        if re.search(r'\b(demain)\b', normalized_query):
            return (today+ timedelta(days=1), 0)
        
        # Relative days: "dans X jours"
        match = re.search(r'\bdans\s+(\d+)\s+(jour|jours)\b', normalized_query)
        if match:
            days = int(match.group(1))
            return (today + timedelta(days=days), 0)
        
        # Next weekend including friday
        if re.search(r'\b(week[\- ]?end)\sprochain', normalized_query):
            days_until_friday = (4 - today.weekday()) % 7 
            
            return (today + timedelta(days=days_until_friday+7) ,2)
        
        # This weekend including friday
        if re.search(r'\b(ce week[\- ]?end)\b', normalized_query):
            days_until_friday = (4 - today.weekday()) % 7 
            
            return (today + timedelta(days=days_until_friday) ,2)
        
        # Next week
        if re.search(r'\b(semaine\sprochaine)\b', normalized_query):
            days_until_monday = (- today.weekday()) % 7 or 7
                
            return (today + timedelta(days=days_until_monday) ,6)
        
        # Current week
        if re.search(r'\b(?:cette|la)\s(semaine)\b', normalized_query):
            days_until_sunday = (6 - today.weekday()) % 7 
                
            return (today  , days_until_sunday)

        # On precise month
        for index, month in enumerate(months):
            if re.search(fr"\b(?:mois de\s|mois d'|en\s)({month})\b", normalized_query):
                index_month = (index + 1) 
                index_year = today.year if index_month>= today.month else today.year+1
                first_day = datetime(index_year, index_month,1)
                first_day = max( first_day,today)
                days_in_months = monthrange(first_day.year, first_day.month)[1] - first_day.day
                return (first_day ,days_in_months)
                

        # return the next 30 days
        return (today, 30)
    
    @staticmethod
    def parse_city(query: str) -> Optional[str]:
        """Extract city from query"""
        query = normalize_str(query)

        clean_cities = [normalize_str(city) for city in QueryParser.CITIES]

        for index, city in enumerate(clean_cities):
            if re.search(rf'\b{city}\b', query):
                return QueryParser.CITIES[index]
        
        return None
    
    @staticmethod
    def parse_department(query: str) -> Optional[str]:
        """Extract department from query"""
        query = normalize_str(query)
        
        clean_depts = [normalize_str(dept) for dept in QueryParser.DEPARTMENTS]

        for index, dept in enumerate(clean_depts):
            if re.search(rf'\b{dept}\b', query):
                return QueryParser.DEPARTMENTS[index]
        
        return None

    @staticmethod
    def parse_constraints(query: str, snapshot_date:str = Config.DEV_SNAPSHOT_DATE) -> Dict:
        """Parse date and city from query"""
        metadata_path = Config.get_processed_snapshot_path(snapshot_date)
        # make list of cities and department
        df = pd.read_json(metadata_path)

        mask = df.duplicated(Config.LOC_CITY)
        cities = df[~mask][Config.LOC_CITY].sort_values()
        QueryParser.CITIES = cities.to_list()

        mask = df.duplicated(Config.LOC_DEPT)
        depts = df[~mask][Config.LOC_DEPT].sort_values()
        QueryParser.DEPARTMENTS = depts.to_list()

        return {
            'date': QueryParser.parse_date(query, today=snapshot_date),
            'city': QueryParser.parse_city(query),
            'dept': QueryParser.parse_department(query)
        }
