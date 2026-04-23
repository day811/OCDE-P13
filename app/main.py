from fastapi import FastAPI

app = FastAPI(title="Puls-Events API")

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "Puls-Events API is running"}