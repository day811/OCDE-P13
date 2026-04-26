from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Dict, Any
import json
from bs4 import BeautifulSoup

class EventTiming(BaseModel):
    start: str
    end: str

class EventSchema(BaseModel):
    """
    Pydantic schema for OpenAgenda/ODS event validation (Silver Layer).
    """
    uid: str
    updatedat: str
    title_fr: str
    description_fr: Optional[str] = ""
    longdescription_fr: Optional[str] = ""
    location_name: Optional[str] = ""
    location_city: Optional[str] = ""
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    location_coordinates: Optional[Dict[str, float]] = None # Pour garder la structure ODS si besoin    
    location_department: Optional[str] = ""
    location_region: Optional[str] = ""
    location_address: Optional[str] = ""
    conditions_fr: Optional[str] = ""
    canonicalurl: Optional[str] = ""
    timings: Optional[List[EventTiming]] = []

    @field_validator('timings', mode='before')
    @classmethod
    def parse_timings_field(cls, v: Any) -> Any:    
        """
        Pydantic v2 field validator. Parses the timings string from ODS 
        into a list of EventTiming objects.
        """
        if isinstance(v, str):
            try:
                raw_data = json.loads(v)
                return [
                    {"start": t.get('start') or t.get('begin'), "end": t.get('end')} 
                    for t in raw_data
                ]
            except (json.JSONDecodeError, TypeError):
                return []
        return v    
       
    @model_validator(mode= 'before')
    @classmethod
    def extract_nested_coordinates(cls, data: Any) -> Any:
        """
        Pydantic v2 model validator. Extracts lat and lon from 
        location_coordinates before field assignment.
        """
        if isinstance(data, dict):
            coords = data.get('location_coordinates')
            if isinstance(coords, dict):
                # Ensure values are mapped to root fields for persistence
                if data.get('location_lat') is None:
                    data['location_lat'] = coords.get('lat')
                if data.get('location_lon') is None:
                    data['location_lon'] = coords.get('lon')
        return data
    
    @field_validator('longdescription_fr', 'description_fr', 'conditions_fr', mode='before')
    @classmethod
    def clean_html_fields(cls, v: Any) -> str:
        """ Removes HTML tags from any string field. """
        if not isinstance(v, str) or not v.strip():
            return ""
        # BeautifulSoup processes text (urls included) safely
        return " ".join(BeautifulSoup(v, "html.parser").get_text(separator=" ").split())