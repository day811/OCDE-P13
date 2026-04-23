## Goal
Design and document a scalable RAG architecture using Azure native services to replace the local POC. Focus on solving the 12-month temporal filtering issue.

## Proposed Stack
* **Web Frontend:** ChainLit (Python) hosted on Azure App Service (Docker).
* **Backend API:** FastAPI for query handling and logic.
* **Vector Database & Search:** Azure AI Search with Hybrid Search (Vector + BM25) and OData metadata filtering.
* **LLM & Embeddings:** Azure OpenAI Service (GPT-4o and text-embedding-3-small).
* **State Management:** Azure Cosmos DB for conversational memory and user preferences.
* **Security:** Azure Key Vault for secret management.

## Definition of Done (DoD)
* Detailed architecture schema integrated into the report.
* Technical justification for Azure AI Search vs. manual FAISS filtering.
* Deployment strategy (CI/CD via GitHub Actions) defined.