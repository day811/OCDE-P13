from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
import json

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

    @validator('timings', pre=True)
    def parse_timings_field(cls, v):
        """ Parses the timings string from ODS into a list of EventTiming objects. """
        if isinstance(v, str):
            try:
                data = json.loads(v)
                return [{"start": t.get('start') or t.get('begin'), "end": t.get('end')} for t in data]
            except:
                return []
        return v