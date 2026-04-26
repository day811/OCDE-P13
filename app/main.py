from fastapi import FastAPI
from app.services.seek_engine import SeekEngine

app = FastAPI(title="Puls-Events API")
engine = SeekEngine()

@app.post("/ask")
async def ask_question(query: str):
    return engine.search(query)

@app.get("/health")
async def health():
    return {"status": "ok"}