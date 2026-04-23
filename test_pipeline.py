import os
import logging
from app.services.ingestion import OpenAgendaIngestor

# Force debug logging
logging.basicConfig(level=logging.DEBUG)

def run_test():
    """
    Test the ingestion pipeline with a very small batch.
    """

    print("--- Starting Debug Test (Max 5 events) ---")
    ingestor = OpenAgendaIngestor()
    
    # We limit to 5 events to check the logic and the FAISS save
    ingestor.run(max_total=5)
    print("--- Test Complete ---")

if __name__ == "__main__":
    run_test()