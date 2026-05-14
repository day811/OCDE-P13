# 🎭 Puls-Events — Chatbot RAG Culturel (OCDE-P13)

> **POC → MVP** : Transition d'un moteur de recherche sémantique local vers un système RAG hybride scalable, déployé sur Azure Container Apps, couvrant **250 000+ événements culturels** à l'échelle nationale.

---

## 📋 Table des matières

- [Présentation du projet](#-présentation-du-projet)
- [Fonctionnalités](#-fonctionnalités)
- [Architecture technique](#-architecture-technique)
- [Pipeline de données — Modèle Medallion](#-pipeline-de-données--modèle-medallion)
- [Stack technologique](#-stack-technologique)
- [Structure du projet](#-structure-du-projet)
- [Installation et démarrage local](#-installation-et-démarrage-local)
- [Déploiement Azure](#-déploiement-azure)
- [Variables d'environnement](#-variables-denvironnement)
- [Tests](#-tests)
- [Monitoring](#-monitoring)
- [Dette technique et évolutions](#-dette-technique-et-évolutions)
- [Coûts OPEX estimés](#-coûts-opex-estimés)

---

## 🎯 Présentation du projet

**Puls-Events** est une plateforme de recommandation d'événements culturels en France. Ce dépôt correspond au projet **OCDE-P13** (OpenClassrooms Data Engineer, Projet 13), qui constitue la transition du POC initial vers un **MVP scalable et déployé en production**.

### Contexte

| Dimension | POC (avant) | MVP (ce projet) |
|---|---|---|
| Couverture géographique | Occitanie (~5 000 événements) | France entière (~250 000+ événements) |
| Interface utilisateur | Streamlit local | Chainlit 2.x conversationnel |
| Index vectoriel | FAISS en mémoire | Azure AI Search (hybride vectoriel + BM25) |
| Persistance | Aucune | PostgreSQL + Azure Blob Storage |
| Déploiement | Local uniquement | Azure Container Apps (HTTPS public) |
| Mémoire conversationnelle | Absente | Data layer PostgreSQL + historique |

### Cas d'usage

- **Recherche directe** : *"Quels sont les concerts de jazz à Toulouse ce week-end ?"*
- **Recherche personnalisée** : *"Trouve-moi d'autres événements comme celui que j'ai aimé hier"*
- **Démonstration portfolio** : Profil `guest` avec quota journalier (5 questions / 10 000 tokens)

---

## ✅ Fonctionnalités

Toutes les fonctionnalités **Must-Have** (classification MoSCoW) ont été livrées :

| Fonctionnalité | Description technique | Statut |
|---|---|---|
| Interface Chainlit | UI conversationnelle, API FastAPI (`/ask`, `/health`) | ✅ Livré |
| Authentification | Auth par mot de passe, profil `guest` avec quota journalier | ✅ Livré |
| Pipeline ETL incrémental | Bronze → Silver → Gold, manifest high-watermark, cron Azure | ✅ Livré |
| Filtrage temporel | `QueryParser` dates relatives, validation post-retrieval Python | ✅ Livré |
| Mémoire conversationnelle | Data layer PostgreSQL + Chainlit, historique, `on_chat_resume` | ✅ Livré |
| Déploiement Azure | 3 Container Apps (api, ui, ingestor job), scripts `deploy.sh` | ✅ Livré |
| Monitoring satisfaction | Grafana Cloud + Azure Monitor + PostgreSQL feedbacks/tokens | ✅ Livré |
| Cache applicatif | `warm_location_cache()`, `SeekEngine` singleton, `locations.json` | ✅ Livré |

---

## 🏗️ Architecture technique

L'application repose sur une **architecture micro-services conteneurisée** déployée sur Azure Container Apps :

```
┌─────────────────────────────────────────────────────────────┐
│                    Azure Container Apps                      │
│                                                             │
│  ┌──────────────────┐    ┌──────────────────┐              │
│  │  pulsevents-ui   │───▶│  pulsevents-api  │              │
│  │  Chainlit 2.11   │    │  FastAPI + RAG   │              │
│  │  (Public HTTPS)  │    │  (Interne)       │              │
│  └──────────────────┘    └────────┬─────────┘              │
│                                   │                         │
│  ┌──────────────────┐             │                         │
│  │pulsevents-ingest │             │                         │
│  │  ETL Job (cron)  │             │                         │
│  └──────────────────┘             │                         │
└───────────────────────────────────┼─────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────┐
         │                          │                      │
   ┌─────▼──────┐  ┌────────────────▼──┐  ┌─────────────┐ │
   │ Azure AI   │  │  Azure OpenAI     │  │ Azure Blob  │ │
   │ Search     │  │  GPT-4o           │  │ Storage     │ │
   │ (93k+ docs)│  │  text-embed-3-sm  │  │ Bronze/     │ │
   └────────────┘  └───────────────────┘  │ Silver/Gold │ │
                                          └─────────────┘ │
   ┌──────────────┐  ┌─────────────────┐                  │
   │ PostgreSQL   │  │ Azure Cosmos DB │                  │
   │ (Data layer, │  │ (Users &        │                  │
   │  feedbacks,  │  │  Settings)      │                  │
   │  tokens)     │  └─────────────────┘                  │
   └──────────────┘                                        │
         │                                                  │
   ┌─────▼──────────────────────────────────────────────┐  │
   │              Grafana Cloud (Monitoring)             │  │
   └─────────────────────────────────────────────────────┘  │
```

### Moteur RAG — SeekEngine

Le moteur de recherche (`SeekEngine`) implémente un pipeline RAG hybride :

1. **`QueryParser`** : Extraction des entités temporelles et géographiques depuis la requête naturelle
2. **Recherche hybride** : Requête vectorielle (embeddings `text-embedding-3-small`) + BM25 sur Azure AI Search
3. **Validation post-retrieval** : Filtrage Python `_validate_event()` sur les créneaux temporels
4. **Condensation du contexte** : Réduction de la fenêtre de contexte avant génération
5. **Streaming de la réponse** : Génération GPT-4o avec `async for chunk`

---

## 🗄️ Pipeline de données — Modèle Medallion

```
OpenAgenda API
      │
      ▼
┌──────────┐     ┌──────────┐     ┌──────────┐
│  BRONZE  │────▶│  SILVER  │────▶│   GOLD   │
│  Azure   │     │  Azure   │     │  Azure   │
│  Blob    │     │  Blob    │     │ AI Search│
│ Raw JSON │     │Validated │     │  Index   │
│ ~3 Go    │     │  JSONL   │     │ 93k docs │
│250k evts │     │ Pydantic │     │ + embed. │
└──────────┘     └──────────┘     └──────────┘
    Source          EventProcessor    SeekEngine
  immuable          (validation)      (indexation)
```

- **Bronze** : Données brutes OpenAgenda, source de vérité immuable
- **Silver** : Événements validés par `EventProcessor` (Pydantic), un fichier JSONL par batch
- **Gold** : Index Azure AI Search avec embeddings vectoriels, manifest high-watermark pour l'incrémental

---

## 🛠️ Stack technologique

| Composant | Technologie | Version |
|---|---|---|
| **Langage** | Python | 3.11 |
| **UI conversationnelle** | Chainlit | 2.11 |
| **API backend** | FastAPI | — |
| **Orchestration LLM** | LangChain | — |
| **LLM** | Azure OpenAI GPT-4o | — |
| **Embeddings** | text-embedding-3-small | — |
| **Index vectoriel** | Azure AI Search | Basic tier |
| **Pipeline ETL** | Python + Pydantic | — |
| **Persistance conversations** | PostgreSQL (asyncpg) | Flexible B1ms |
| **Stockage utilisateurs** | Azure Cosmos DB | Serverless |
| **Stockage objets** | Azure Blob Storage | Standard v2 |
| **Conteneurisation** | Docker | — |
| **Orchestration cloud** | Azure Container Apps | — |
| **Registry** | Azure Container Registry | Basic |
| **Monitoring** | Grafana Cloud | Free tier |
| **Tests** | unittest | — |

---

## 📁 Structure du projet

```
OCDE-P13/
│
├── app/
│   ├── api/                    # FastAPI routes (/ask, /health, /settings)
│   ├── services/
│   │   ├── seek_engine.py      # Core RAG engine (SeekEngine)
│   │   ├── query_parser.py     # Temporal & geographic entity extraction
│   │   ├── processor.py        # EventProcessor (Bronze → Silver)
│   │   ├── indexer.py          # Azure AI Search indexation (Silver → Gold)
│   │   ├── ingestor.py         # ETL orchestration with high-watermark manifest
│   │   ├── llm/
│   │   │   └── llm_factory.py  # Factory pattern LLM/Embeddings (LOCAL vs AZURE)
│   │   └── storage/
│   │       ├── storage_base.py
│   │       ├── azure_provider.py
│   │       ├── local_provider.py
│   │       ├── storage_factory.py
│   │       └── chainlit_storage.py  # Chainlit data layer (Azure Blob)
│   └── schemas/
│       └── event.py            # Pydantic EventSchema (Silver layer)
│
├── ui.py                       # Chainlit entrypoint (chat handlers)
├── main.py                     # FastAPI entrypoint
├── Dockerfile                  # Multi-service Docker image
├── entrypoint.sh               # Service selector (api | ui | ingestor)
├── docker-compose.yml          # Local multi-service stack
├── azure_deploy.sh             # Azure Container Apps deployment script
├── requirements.txt
│
├── tests/
│   ├── test_processor_unit.py  # Unit tests — EventProcessor
│   ├── test_seek_engine.py     # Unit tests — SeekEngine
│   └── test_api_integration.py # Integration tests — FastAPI endpoints
│
├── scripts/
│   └── create_user.py          # CLI user creation (Cosmos DB)
│
├── data/
│   └── locations.json          # Gold layer location cache
│
└── .env.example                # Environment variables template
```

---

## 🚀 Installation et démarrage local

### Prérequis

- Python 3.11+
- Docker & Docker Compose
- Compte Azure actif (pour les services cloud)

### 1. Cloner le dépôt

```bash
git clone https://github.com/<username>/OCDE-P13.git
cd OCDE-P13
```

### 2. Configurer les variables d'environnement

```bash
cp .env.example .env
# Éditer .env avec vos credentials Azure
```

### 3. Démarrage via Docker Compose (recommandé)

```bash
docker compose up --build
```

L'API sera disponible sur `http://localhost:8000` et l'UI Chainlit sur `http://localhost:8001`.

### 4. Démarrage sans Docker

```bash
# Créer un environnement virtuel
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt

# Démarrer l'API
SERVICE=api python main.py

# Démarrer l'UI (dans un autre terminal)
SERVICE=ui chainlit run ui.py --port 8001
```

### 5. Créer un utilisateur

```bash
python scripts/create_user.py -u mon_utilisateur -p mon_mot_de_passe -r user
# Pour un compte guest avec quota :
python scripts/create_user.py -u demo -p demo123 -r guest
```

---

## ☁️ Déploiement Azure

Le script `azure_deploy.sh` automatise le déploiement complet :

```bash
# S'assurer que le fichier .env est configuré avec tous les secrets Azure
bash azure_deploy.sh
```

Le script réalise les étapes suivantes :
1. Chargement du fichier `.env`
2. Récupération des credentials ACR
3. Build et push des images Docker vers Azure Container Registry
4. Déploiement ou mise à jour des 3 Container Apps (`api`, `ui`, `ingestor`)
5. Affichage de l'URL publique HTTPS de l'interface

Pour lancer manuellement le job d'ingestion :

```bash
az containerapp job start --name pulsevents-ingestor --resource-group OpenClassrooms_P13
```

Pour suivre les logs en temps réel :

```bash
az containerapp logs show --name pulsevents-ui --resource-group OpenClassrooms_P13 --follow
```

---

## 🔑 Variables d'environnement

Copier `.env.example` en `.env` et renseigner toutes les valeurs :

| Variable | Service(s) | Description |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | api, ui | Endpoint Azure OpenAI |
| `AZURE_OPENAI_API_KEY` | api, ui | Clé API Azure OpenAI |
| `AZURE_SEARCH_ENDPOINT` | api, ui, ingestor | Endpoint Azure AI Search |
| `AZURE_SEARCH_API_KEY` | api, ui, ingestor | Clé API Azure AI Search |
| `COSMOS_ENDPOINT` | api, ui | Endpoint Azure Cosmos DB |
| `COSMOS_KEY` | api, ui | Clé Cosmos DB |
| `AZURE_STORAGE_CONNECTION_STRING` | tous | Connection string Blob Storage |
| `DATABASE_URL` | ui | `postgresql+asyncpg://...` PostgreSQL |
| `CHAINLIT_AUTH_SECRET` | ui | Secret JWT Chainlit (générer avec `openssl rand -hex 32`) |
| `SERVICE` | tous | Sélecteur de service : `api` \| `ui` \| `ingestor` |
| `ENV` | tous | `LOCAL` (FAISS + Gemini) \| `AZURE` (Azure AI Search + GPT-4o) |

---

## 🧪 Tests

```bash
# Lancer tous les tests
python -m pytest tests/ -v

# Tests unitaires uniquement
python -m pytest tests/test_processor_unit.py tests/test_seek_engine.py -v

# Tests d'intégration (nécessite les services Azure)
python -m pytest tests/test_api_integration.py -v
```

---

## 📊 Monitoring

Le monitoring est centralisé dans **Grafana Cloud** avec deux datasources :

- **Azure Monitor** : CPU, mémoire, requêtes HTTP, nombre de replicas (dashboards IDs 16591 et 16592)
- **PostgreSQL** : Taux de satisfaction (feedback 👍/👎) et consommation de tokens par session

### Métriques de satisfaction (requête PostgreSQL)

```sql
SELECT
    DATE_TRUNC('day', t."createdAt"::timestamp),
    COUNT(CASE WHEN f.value = 1 THEN 1 END) AS thumbs_up,
    ROUND(
        100.0 * COUNT(CASE WHEN f.value = 1 THEN 1 END)
        / NULLIF(COUNT(*), 0), 1
    ) AS satisfaction_pct
FROM feedbacks f
JOIN threads t ON f."threadId" = t."id"
GROUP BY 1
ORDER BY 1;
```

---

## 🔧 Dette technique et évolutions

### Dette technique identifiée

| Item | Cause | Compensation actuelle |
|---|---|---|
| Reprocessing Bronze→Silver incomplet | Bug `silver_name` fixe écrasant le fichier | Script correctif développé, à exécuter |
| Filtre OData `last_date` non fonctionnel | Type mismatch `Edm.DateTimeOffset` Azure Search | Validation post-retrieval Python |
| Champs `facetable` manquants | `location_city` / `location_department` non indexés | Réindexation nécessaire |

### Évolutions prioritaires post-MVP

- **Recherche web temps réel** : Intégration `smolagents` / Hugging Face
- **Architecture DualIndex** : Séparation index passé/futur (FAISS + Azure AI Search)
- **Application Insights** : Traces distribuées et alertes automatiques Azure
- **CI/CD GitHub Actions** : Build / push / deploy automatisés au merge sur `main`

---

## 💰 Coûts OPEX estimés

| Service Azure | Configuration | Coût mensuel estimé |
|---|---|---|
| Azure OpenAI (GPT-4o + text-embedding-3-small) | Usage | ~15–30 € |
| Azure AI Search | Basic tier, 1 réplica, 93k documents | ~75 € |
| Azure Container Apps | 3 services, scale-to-zero | ~5–10 € |
| Azure Container Registry | Basic SKU | ~5 € |
| Azure Cosmos DB | Serverless | ~3–5 € |
| Azure Blob Storage | Standard v2, Bronze/Silver/Gold | ~2–4 € |
| Azure PostgreSQL | Flexible Burstable B1ms, 32 Go | ~12 € |
| Grafana Cloud | Free tier (10k métriques, 50 Go logs) | 0 € |
| **TOTAL ESTIMÉ** | | **~115–140 €/mois** |

> **Optimisations actives** : scale-to-zero Container Apps, `text-embedding-3-small`, cache applicatif `SeekEngine` singleton, ingestor job planifié (non continu).

---

## 📄 Licence

Projet réalisé dans le cadre du parcours **Data Engineer** — OpenClassrooms (Projet 13).

---

*Puls-Events MVP — OCDE-P13 | Data Engineer en alternance*