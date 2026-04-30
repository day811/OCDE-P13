import os
import asyncio
import dotenv
from app.services.ingestion_service import IngestionService

dotenv.load_dotenv()

async def main():
    """
    Main entry point for the ingestion pipeline.
    Usage: 
    - LOCAL: Fetches Occitanie, saves to files, indexes in FAISS.
    - AZURE: Fetches France, saves to Blobs, indexes in Azure AI Search.
    """
    ingestor = IngestionService()
    
    # Example: Run a batch of 500 events
    # To run the full national ingestion, remove the limit
    await ingestor.run(max_records=500)

if __name__ == "__main__":
    asyncio.run(main())