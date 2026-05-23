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
- [Initialisation des tables PostgreSQL](#-initialisation-des-tables-postgresql)
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
| Recherche web fallback | Absente | smolagents + DuckDuckGo (whitelist événementielle) |
| Télémétrie RAG | Absente | `rag_telemetry` + `infrastructure_snapshots` PostgreSQL |

### Cas d'usage

- **Recherche directe** : *"Quels sont les concerts de jazz à Toulouse ce week-end ?"*
- **Recherche personnalisée** : *"Trouve-moi d'autres événements comme celui que j'ai aimé hier"*
- **Fallback web** : si aucun événement n'est trouvé dans l'index, recherche automatique sur billetweb, eventbrite, openagenda, fnacspectacles…
- **Démonstration portfolio** : Profil `guest` avec quota journalier (5 questions / 10 000 tokens)

---

## ✅ Fonctionnalités

Toutes les fonctionnalités **Must-Have** et **Should-Have** de la classification MoSCoW ont été livrées :

| Fonctionnalité | Description technique | Priorité | Statut |
|---|---|---|---|
| Interface Chainlit | UI conversationnelle, API FastAPI (`/ask`, `/health`) | Must-Have | ✅ Livré |
| Authentification | Auth par mot de passe, profil `guest` avec quota journalier | Must-Have | ✅ Livré |
| Pipeline ETL incrémental | Bronze → Silver → Gold, manifest high-watermark, cron Azure | Must-Have | ✅ Livré |
| Filtrage temporel | `QueryParser` dates relatives, validation post-retrieval Python | Must-Have | ✅ Livré |
| Mémoire conversationnelle | Data layer PostgreSQL + Chainlit, historique, `on_chat_resume` | Must-Have | ✅ Livré |
| Déploiement Azure | 3 Container Apps (api, ui, ingestor job), scripts `deploy.sh` | Must-Have | ✅ Livré |
| Monitoring satisfaction | Grafana Cloud + feedbacks/tokens PostgreSQL | Must-Have | ✅ Livré |
| Cache applicatif | `warm_location_cache()`, `SeekEngine` singleton, `locations.json` | Must-Have | ✅ Livré |
| **Recherche web temps réel** | **`WebSearchService` smolagents + DuckDuckGo, whitelist 10 sites événementiels** | **Should-Have** | **✅ Livré** |
| **Télémétrie RAG** | **`MonitoringStorageService` : latences par étape, taux fallback, snapshots infra** | **Should-Have** | **✅ Livré** |

> La fonctionnalité "Architecture DualIndex" (séparation index passé/futur) reste différée post-MVP.

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
   ┌─────▼──────┐  ┌────────────────▼──┐  ┌─────────────┐
   │ Azure AI   │  │  Azure OpenAI     │  │ Azure Blob  │
   │ Search     │  │  GPT-4o           │  │ Storage     │
   │ (93k+ docs)│  │  text-embed-3-sm  │  │ Bronze/     │
   └────────────┘  └───────────────────┘  │ Silver/Gold │
                                          └─────────────┘
   ┌──────────────┐  ┌─────────────────┐
   │ PostgreSQL   │  │ Azure Cosmos DB │
   │ feedbacks    │  │ Users & Settings│
   │ token_usage  │  └─────────────────┘
   │ rag_telemetry│
   │ ingestor_runs│
   │ infra_snaps  │
   └──────┬───────┘
          │
   ┌──────▼──────────────────────┐
   │      Grafana Cloud          │
   │ • Azure Monitor             │
   │ • PostgreSQL (satisfaction) │
   │ • PostgreSQL (télémétrie)   │
   └─────────────────────────────┘

   ┌──────────────────────────────────────────────┐
   │  DuckDuckGo via smolagents — Web Fallback    │
   │  Whitelist : billetweb, eventbrite,          │
   │  openagenda, fnacspectacles, sortiraparis…   │
   └──────────────────────────────────────────────┘
```

### Moteur RAG — SeekEngine (pipeline en 6 étapes)

1. **Geo enrichment** : injection de `fav_city` au premier tour si la requête manque de contexte géographique
2. **Condensation** : reformulation de la question via le LLM en intégrant l'historique (last 10 turns)
3. **`QueryParser`** : extraction des contraintes temporelles (dates relatives, week-end, mois) et géographiques
4. **Recherche hybride** : Azure AI Search (vectoriel + BM25) + filtres OData géographiques
5a. **Web search fallback** (`WebSearchService`) : si l'index retourne zéro résultat validé, un `CodeAgent` smolagents interroge DuckDuckGo restreint à 10 sites événementiels français (`max_steps=3`)
5b. **Génération streamée** : GPT-4o produit la réponse token par token via `astream()`
6. **Télémétrie** (fire-and-forget) : `MonitoringStorageService.record_rag_telemetry()` écrit les latences via `asyncio.create_task()` sans bloquer le stream

### WebSearchService — Whitelist des sites ciblés

```
openagenda.com    billetweb.fr      eventbrite.fr
fnacspectacles.com  sortiraparis.com  sortirtoulouse.com
sortirabordeaux.com  agendaculturel.fr  tourisme.fr  france.fr
```

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
      │                                    │
      └──────────────────┬─────────────────┘
                         ▼
              MonitoringStorageService
              infrastructure_snapshots
              (Grafana: suivi croissance index)
```

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
| **Recherche web fallback** | smolagents + DuckDuckGoSearchTool | — |
| **Pipeline ETL** | Python + Pydantic | — |
| **Persistance conversations** | PostgreSQL asyncpg | Flexible B1ms |
| **Télémétrie RAG** | asyncpg → `rag_telemetry` / `infrastructure_snapshots` | — |
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
│   ├── core/                          # FastAPI routes (/ask, /health, /settings)
│   │   └── llm_factory.py        # Factory pattern LLM (LOCAL vs AZURE)
│   │   ├── embedding_factory.py  # Factory pattern Embeddings (LOCAL vs AZURE)
│   ├── services/
│   │   ├── seek_engine.py            # Core RAG engine (SeekEngine, pipeline 6 étapes)
│   │   ├── query_parser.py           # Temporal & geographic entity extraction
│   │   ├── processor.py              # EventProcessor (Bronze → Silver)
│   │   ├── indexer.py                # Azure AI Search indexation (Silver → Gold)
│   │   ├── ingestion_service.py      # ETL orchestration, high-watermark manifest
│   │   ├── web_search_service.py     # ← NEW : smolagents fallback DuckDuckGo
│   │   └── storage/
│   │       ├── storage_base.py
│   │       ├── azure_provider.py
│   │       ├── local_provider.py
│   │       ├── storage_factory.py
│   │       ├── chainlit_storage.py   # Chainlit data layer (Azure Blob)
│   │       └── monitoring_storage.py # MonitoringStorageService (asyncpg)
│   └── schemas/
│       └── event.py                  # Pydantic EventSchema (Silver layer)
│
├── ui.py                             # Chainlit entrypoint (chat handlers + step UI)
├── main.py                           # FastAPI entrypoint
├── ingest_pipeline.py                # Ingestor + _collect_infrastructure_metrics()
├── Dockerfile
├── entrypoint.sh                     # Service selector (api | ui | ingestor)
├── docker-compose.yml
├── azure_deploy.sh
├── requirements.txt
├── tests/
│   ├── test_processor_unit.py        # Unit tests — EventProcessor
│   ├── test_seek_engine.py           # Unit tests — SeekEngine
│   ├── test_api_integration.py       # Integration tests — FastAPI endpoints
│   └── test_azure_index.py           # Vérification index Azure AI Search
│
└── scripts/
    ├── azure_deploy.sh                # CLI user creation (Cosmos DB)
    ├── create_user.py                # CLI user creation (Cosmos DB)
    └── test_infra_snapshot.py        # ← NEW : test collecte métriques infra
 
```

---

## 🚀 Installation et démarrage local

### Prérequis

- Python 3.11+
- Docker & Docker Compose
- Compte Azure actif (pour les services cloud)

### 1. Cloner le dépôt

```bash
git clone https://github.com/day811/OCDE-P13.git
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
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Démarrer l'API
SERVICE=api python main.py

# Démarrer l'UI (dans un autre terminal)
SERVICE=ui chainlit run ui.py --port 8001
```

### 5. Créer un utilisateur

```bash
python scripts/create_user.py -u mon_utilisateur -p mon_mot_de_passe -r user
# Compte guest avec quota journalier :
python scripts/create_user.py -u demo -p demo123 -r guest
```

---

## ☁️ Déploiement Azure

```bash
bash azure_deploy.sh
```

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

| Variable | Service(s) | Description |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | api, ui | Endpoint Azure OpenAI |
| `AZURE_OPENAI_API_KEY` | api, ui | Clé API Azure OpenAI |
| `AZURE_OPENAI_DEPLOYMENT` | api, ui | Nom du déploiement GPT-4o (ex. `gpt-4o`) |
| `AZURE_OPENAI_API_VERSION` | api, ui | Version de l'API (ex. `2024-02-15-preview`) |
| `AZURE_SEARCH_ENDPOINT` | api, ui, ingestor | Endpoint Azure AI Search |
| `AZURE_SEARCH_API_KEY` | api, ui, ingestor | Clé API Azure AI Search |
| `AZURE_SEARCH_INDEX_NAME` | api, ui, ingestor | Nom de l'index (ex. `puls-events-index`) |
| `AZURE_EMBEDDING_DEPLOYMENT` | api, ingestor | Nom du déploiement embedding |
| `COSMOS_ENDPOINT` | api, ui | Endpoint Azure Cosmos DB |
| `COSMOS_KEY` | api, ui | Clé Cosmos DB |
| `AZURE_STORAGE_CONNECTION_STRING` | tous | Connection string Blob Storage |
| `DATABASE_URL` | ui, ingestor | `postgresql+asyncpg://...` PostgreSQL |
| `CHAINLIT_AUTH_SECRET` | ui | Secret JWT Chainlit (`openssl rand -hex 32`) |
| `SERVICE` | tous | `api` \| `ui` \| `ingestor` |
| `ENV` | tous | `LOCAL` (FAISS + Gemini) \| `AZURE` (Azure AI Search + GPT-4o) |
| `MAX_RECORDS` | ingestor | Limite d'événements par run ETL |
| `OPENAGENDA_URL` | ingestor | URL de l'API OpenAgenda |

---

## 🗃️ Initialisation des tables PostgreSQL

Avant le premier démarrage en production, exécuter la migration de monitoring :

```bash
psql $DATABASE_URL -f migrations/migration_monitoring.sql
```

Ce script crée les tables suivantes en complément des tables natives Chainlit :

| Table | Rôle | Écrit par |
|---|---|---|
| `feedbacks` | Votes 👍/👎 par réponse | Chainlit natif |
| `token_usage` | Tokens consommés par session | Chainlit natif |
| `rag_telemetry` | Latences par étape RAG + flag fallback web | `MonitoringStorageService` |
| `ingestor_runs` | Historique ETL (status, events, durée) | `MonitoringStorageService` |
| `infrastructure_snapshots` | Taille Bronze/Silver/Gold + stats index | `MonitoringStorageService` |

### Tester la collecte d'une snapshot d'infrastructure

```bash
python scripts/test_infra_snapshot.py
# Vérifie la table infrastructure_snapshots dans Grafana
```

---

## 🧪 Tests

```bash
# Tous les tests
python -m pytest tests/ -v

# Tests unitaires
python -m pytest tests/test_processor_unit.py tests/test_seek_engine.py -v

# Vérification de l'index Azure AI Search
python tests/test_azure_index.py

# Tests d'intégration (nécessite les services Azure)
python -m pytest tests/test_api_integration.py -v
```

---

## 📊 Monitoring

Le monitoring est centralisé dans **Grafana Cloud** avec trois datasources :

### 1. Azure Monitor
Dashboards natifs Container Apps (IDs 16591 et 16592) : CPU, mémoire, requêtes HTTP, replicas.

### 2. PostgreSQL — Satisfaction & tokens (tables Chainlit)

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
GROUP BY 1 ORDER BY 1;
```

### 3. PostgreSQL — Télémétrie RAG & infrastructure

```sql
-- Latences moyennes et taux de fallback web par heure
SELECT
    DATE_TRUNC('hour', created_at),
    AVG(condensation_latency_ms)  AS avg_condensation_ms,
    AVG(search_latency_ms)        AS avg_search_ms,
    AVG(generation_latency_ms)    AS avg_generation_ms,
    AVG(total_latency_ms)         AS avg_total_ms,
    SUM(CASE WHEN query_had_zero_results THEN 1 ELSE 0 END) AS web_fallback_count
FROM rag_telemetry
GROUP BY 1 ORDER BY 1;

-- Croissance de l'index au fil des ingestions
SELECT created_at,
       index_document_count,
       index_storage_bytes / 1048576.0 AS index_mb
FROM infrastructure_snapshots
ORDER BY created_at;
```

---

## 🔧 Dette technique et évolutions

### Dette technique identifiée

| Item | Cause | Compensation actuelle |
|---|---|---|
| Reprocessing Bronze→Silver incomplet | Bug `silver_name` fixe écrasant le fichier | Script correctif développé, à exécuter |
| Filtre OData `last_date` non fonctionnel | Type mismatch `Edm.DateTimeOffset` Azure Search | Validation post-retrieval Python `_validate_event()` |
| Champs `facetable` manquants | `location_city` / `location_department` non indexés | Réindexation nécessaire pour activer les facets Grafana |

### Évolutions prioritaires post-MVP

- **Architecture DualIndex** : séparation index passé/futur pour optimiser la pertinence temporelle
- **Application Insights** : traces distribuées et alertes automatiques Azure
- **CI/CD GitHub Actions** : build / push / deploy automatisés au merge sur `main`

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

> **Optimisations actives** : scale-to-zero Container Apps, `text-embedding-3-small`, cache applicatif `SeekEngine` singleton, ingestor job planifié, télémétrie fire-and-forget (`asyncio.create_task()`).

---

## 📄 Licence

Projet réalisé dans le cadre du parcours **Data Engineer** — OpenClassrooms (Projet 13).

---

*Puls-Events MVP — OCDE-P13 | github.com/day811/OCDE-P13*