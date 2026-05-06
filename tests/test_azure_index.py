import os
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from dotenv import load_dotenv

load_dotenv()

def verify_index():
    client = SearchClient(
        endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
        index_name=os.getenv("AZURE_SEARCH_INDEX_NAME"),
        credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_API_KEY"))
    )

    # Fetch the 3 most recent documents
    results = client.search(search_text="*", top=3)
    
    print("--- DEBUT DE VERIFICATION ---")
    for doc in results:
        print(f"ID: {doc.get('id')}")
        print(f"Titre: {doc.get('title_fr')}")
        print(f"Ville: {doc.get('location_city')}")
        print(f"Dernière date: {doc.get('last_date')}")
        print(f"Vecteur présent: {'Oui' if doc.get('content_vector') else 'Non'}")
        print("-" * 30)

if __name__ == "__main__":
    verify_index()