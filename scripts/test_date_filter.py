# Test à lancer dans un script Python standalone
import os
from datetime import datetime, timezone
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()

client = SearchClient(
    endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
    index_name=os.getenv("AZURE_SEARCH_INDEX_NAME"),
    credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_API_KEY"))
)

today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Test 1 — sans guillemets
# Test 3 — filtre combiné geo + date sans guillemets
today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

results = client.search(
    search_text="concert",
    filter=f"location_city eq 'toulouse' and last_date ge {today}",
    top=3,
    select=["location_city", "last_date"]
)
print("Test 3 (geo + date):", sum(1 for _ in results), "résultats")