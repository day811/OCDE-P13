from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from app.services.seek_engine import SeekEngine


app = FastAPI(title="Puls-Events API")
engine = SeekEngine()

class QueryRequest(BaseModel):
    """ Data model for incoming API requests. """
    user_id: str
    query: str
    fav_city: Optional[str] = None
    fav_dept: Optional[str] = None
    top_k: int = 5

@app.post("/ask")
async def ask_question(request: QueryRequest):
    """
    Exposes the SeekEngine search via a REST API endpoint.
    This allows external systems to query the RAG engine.
    """
    try:
        # We pass all required parameters to the engine.
        # Since it's a direct API call, history is empty [].
        results = engine.search(
            user_query=request.query,
            user_id=request.user_id,
            chat_history=[], 
            fav_city=request.fav_city,
            fav_dept=request.fav_dept,
            top_k=request.top_k
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


@app.get("/health")
async def health():
    return {"status": "ok"}