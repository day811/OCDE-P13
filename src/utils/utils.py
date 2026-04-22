from typing import Optional
from datetime import datetime, timedelta

def normalize_str(text:str) -> str:
    location = text.strip().lower()
    """ Remove accents from text """
    accents = { 'a': ['à', 'ã', 'á', 'â'],
                'e': ['é', 'è', 'ê', 'ë'],
                'i': ['î', 'ï'],
                'u': ['ù', 'ü', 'û'],
                'o': ['ô', 'ö'],
                ' ': ['-','/'] 
                }
    for (char, accented_chars) in accents.items():
        for accented_char in accented_chars:
            location = location.replace(accented_char, char)
    return location    

def flat_date_constraints(
    date_constraint: Optional[tuple[datetime,int]] = None,
    format:str = "%A %-d %B %Y",
):
    
    import locale
    locale.setlocale(locale.LC_TIME,'')
    result = ""
    if date_constraint and len(date_constraint):
        begin  = date_constraint[0]
        end = datetime = date_constraint[0] + timedelta(date_constraint[1])
        if not date_constraint[1]:
            result = f" Date : le {begin.date().strftime(format)}"    
        else:
            result = f" Date : du {begin.date().strftime(format)} au {end.date().strftime(format)}"  
    return result

