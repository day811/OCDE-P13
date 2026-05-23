# Rapport Technique — Monitoring PulsEvents MVP

**Projet** : Puls-Events — Système de recommandation d'événements culturels par IA  
**Document** : Architecture de monitoring et observabilité  
**Version** : 1.0  
**Date** : Mai 2026  
**Auteur** : Data Engineer — Alternance Puls-Events  

---

## Table des matières

1. [Contexte et objectifs](#1-contexte-et-objectifs)  
2. [Architecture de monitoring](#2-architecture-de-monitoring)  
3. [Stack technique](#3-stack-technique)  
4. [Couche 1 — Métriques applicatives PostgreSQL](#4-couche-1--métriques-applicatives-postgresql)  
5. [Couche 2 — Infrastructure Azure Monitor](#5-couche-2--infrastructure-azure-monitor)  
6. [Développements spécifiques — Services de stockage monitoring](#6-développements-spécifiques--services-de-stockage-monitoring)  
7. [Tableaux de bord Grafana](#7-tableaux-de-bord-grafana)  
8. [Système d'alertes](#8-système-dalertes)  
9. [Ressources sous quota surveillées](#9-ressources-sous-quota-surveillées)  
10. [Perspectives d'évolution](#10-perspectives-dévolution)  

---

## 1. Contexte et objectifs

PulsEvents est un chatbot RAG (Retrieval-Augmented Generation) déployé en version MVP sur Microsoft Azure. Le système repose sur une architecture microservices composée de trois Container Apps (API FastAPI, UI Chainlit, Job d'ingestion ETL), Azure AI Search comme moteur de recherche vectorielle, et Azure OpenAI GPT-4o pour la génération de réponses.

En phase alpha/MVP, l'observabilité du système répond à trois impératifs professionnels :

- **Disponibilité** : détecter toute dégradation de service avant les utilisateurs
- **Qualité RAG** : mesurer la pertinence des réponses du moteur de recherche sémantique
- **Maîtrise budgétaire** : piloter la consommation Azure OpenAI en temps réel

Le monitoring est conçu selon le principe **"zéro dépendance externe supplémentaire"** : toutes les métriques applicatives transitent par PostgreSQL, déjà présent dans l'architecture comme data layer Chainlit. Aucun agent Prometheus, aucun SDK de télémétrie tiers n'a été ajouté.

---

## 2. Architecture de monitoring

```
┌─────────────────────────────────────────────────────────────────┐
│                        GRAFANA CLOUD                            │
│                                                                 │
│   ┌─────────────────────┐    ┌──────────────────────────────┐   │
│   │   Azure Monitor     │    │       PostgreSQL              │   │
│   │   Datasource        │    │       Datasource              │   │
│   │                     │    │                              │   │
│   │ • Container Apps    │    │ • feedbacks (Chainlit natif) │   │
│   │ • PostgreSQL PaaS   │    │ • token_usage (Chainlit)     │   │
│   │ • ACR               │    │ • rag_telemetry (custom)     │   │
│   │ • Cosmos DB         │    │ • ingestor_runs (custom)     │   │
│   │ • Blob Storage      │    │ • infrastructure_snapshots   │   │
│   └─────────────────────┘    │   (custom)                   │   │
│                               └──────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
           ▲                              ▲
           │                              │
   Azure Monitor API             asyncpg direct
           │                              │
┌──────────┴──────────┐        ┌──────────┴──────────┐
│   Azure Resources   │        │  Application Code   │
│                     │        │                     │
│ • Container Apps    │        │ • seek_engine.py    │
│ • PostgreSQL Flex   │        │ • ingest_pipeline.py│
│ • ACR Basic         │        │ • monitoring_       │
│ • Cosmos DB         │        │   storage.py        │
│ • Blob Storage      │        └─────────────────────┘
└─────────────────────┘
```

---

## 3. Stack technique

| Composant | Technologie | Rôle |
|---|---|---|
| Visualisation | Grafana Cloud (tier gratuit) | Dashboards et alertes |
| Métriques infrastructure | Azure Monitor via datasource Grafana | CPU, mémoire, storage, connexions |
| Métriques applicatives | PostgreSQL Flexible Server (Azure) | Qualité RAG, tokens, satisfaction |
| Connexion applicative | `asyncpg` (Python) | Écriture asynchrone non-bloquante |
| Service de monitoring | `MonitoringStorageService` (custom) | Couche d'abstraction centralisée |
| Dashboards natifs | Grafana Community IDs 16591 et 16592 | Container Apps overview importés |

---

## 4. Couche 1 — Métriques applicatives PostgreSQL

### 4.1 Tables natives Chainlit

Ces tables sont créées et alimentées automatiquement par Chainlit 2.x. Elles ne nécessitent aucun développement spécifique.

**`feedbacks`** — Votes utilisateurs (👍 / 👎)

| Colonne | Type | Description |
|---|---|---|
| `id` | TEXT | Identifiant unique |
| `threadId` | TEXT | Référence à la conversation |
| `value` | INT | 1 = positif, 0 = négatif |
| `createdAt` | TIMESTAMPTZ | Horodatage UTC |

**`token_usage`** — Consommation de tokens par requête

| Colonne | Type | Description |
|---|---|---|
| `userId` | TEXT | Identifiant utilisateur |
| `prompt_tokens` | INT | Tokens en entrée (contexte + question) |
| `completion_tokens` | INT | Tokens en sortie (réponse générée) |
| `createdAt` | TIMESTAMPTZ | Horodatage UTC |

**`threads`** — Sessions conversationnelles Chainlit (utilisée en jointure)

### 4.2 Tables custom développées

Trois tables ont été ajoutées via migration SQL pour couvrir les besoins de monitoring non adressés par Chainlit.

#### Table `rag_telemetry`

Enregistre la latence et la qualité de retrieval pour chaque requête RAG.

```sql
CREATE TABLE IF NOT EXISTS rag_telemetry (
    id                        SERIAL PRIMARY KEY,
    "userId"                  TEXT,
    "threadId"                TEXT,
    "createdAt"               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    condensation_latency_ms   INT  DEFAULT 0,
    search_latency_ms         INT  DEFAULT 0,
    generation_latency_ms     INT  DEFAULT 0,
    total_latency_ms          INT  DEFAULT 0,
    candidates_retrieved      INT  DEFAULT 0,
    candidates_after_filter   INT  DEFAULT 0,
    query_had_zero_results    BOOLEAN DEFAULT FALSE
);
```

**Champs clés** :
- `condensation_latency_ms` : durée de reformulation de la question par le LLM
- `search_latency_ms` : durée de la requête Azure AI Search (hybride vectoriel + BM25)
- `generation_latency_ms` : durée de génération GPT-4o (token par token, streaming)
- `candidates_retrieved` : documents retournés par Azure Search avant filtrage
- `candidates_after_filter` : documents retenus après validation temporelle et géographique (`_validate_event`)
- `query_had_zero_results` : booléen critique — détecte les dégradations de l'index

#### Table `ingestor_runs`

Enregistre chaque exécution du pipeline ETL (Container App Job planifié à 3h UTC).

```sql
CREATE TABLE IF NOT EXISTS ingestor_runs (
    id               SERIAL PRIMARY KEY,
    "runAt"          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status           VARCHAR(20) NOT NULL
                         CHECK (status IN ('success', 'partial', 'failed')),
    events_fetched   INT          DEFAULT 0,
    events_indexed   INT          DEFAULT 0,
    duration_seconds FLOAT        DEFAULT 0,
    error_message    TEXT
);
```

**Statuts** :
- `success` : pipeline complet, au moins un événement indexé
- `partial` : pipeline terminé sans erreur mais aucun événement nouveau (index à jour)
- `failed` : exception non gérée — `error_message` contient le stacktrace

#### Table `infrastructure_snapshots`

Capture l'état des ressources Azure à chaque exécution de l'ingestor. Permet de suivre la croissance du stockage et de l'index dans le temps.

```sql
CREATE TABLE IF NOT EXISTS infrastructure_snapshots (
    id            SERIAL PRIMARY KEY,
    "snapshotAt"  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bronze_bytes  BIGINT DEFAULT 0,
    silver_bytes  BIGINT DEFAULT 0,
    gold_bytes    BIGINT DEFAULT 0,
    bronze_files  INT DEFAULT 0,
    silver_files  INT DEFAULT 0,
    gold_files    INT DEFAULT 0,
    index_document_count  BIGINT DEFAULT 0,
    index_storage_bytes   BIGINT DEFAULT 0
);
```

**Source des données** :
- Blob Storage : `BlobServiceClient.list_blobs()` sur chaque container (Bronze, Silver, Gold)
- Azure AI Search : `SearchIndexClient.get_index_statistics()` — API officielle Azure SDK

---

## 5. Couche 2 — Infrastructure Azure Monitor

Les métriques d'infrastructure sont interrogées directement depuis Azure Monitor via la datasource Grafana configurée. Aucun développement Python n'est nécessaire pour cette couche.

### Ressources monitorées

| Ressource | SKU / Tier | Métriques configurées |
|---|---|---|
| Container App `pulsevents-ui` | 0.5 vCPU / 1 Gi | CPU, mémoire, replicas, latence HTTP, taux 5xx |
| Container App `pulsevents-api` | 0.5 vCPU / 1 Gi | CPU, mémoire, replicas, latence HTTP, taux 5xx |
| PostgreSQL Flexible | Burstable B1ms / 32 Go | CPU%, storage%, connexions actives |
| ACR Basic | 10 Go | StorageUsed |
| Cosmos DB | Serverless | TotalRequestUnits, ServerSideLatency |

Les dashboards **16591** (Container Apps Environment) et **16592** (Container App single view) ont été importés depuis la bibliothèque communautaire Grafana et configurés sur la datasource Azure Monitor.

---

## 6. Développements spécifiques — Services de stockage monitoring

### 6.1 `MonitoringStorageService`

Fichier : `app/services/storage/monitoring_storage.py`

Service centralisé exposant trois méthodes statiques asynchrones. Il est indépendant de Chainlit et utilisable depuis n'importe quel service de l'application (UI, API, ingestor).

La connexion PostgreSQL réutilise la variable d'environnement `DATABASE_URL` déjà présente dans l'architecture, avec conversion du schéma `postgresql+asyncpg://` vers `postgresql://` requis par `asyncpg` natif.

**Principe de robustesse** : toutes les méthodes encapsulent les exceptions dans un `try/except` avec log `WARNING`. Un échec d'écriture en base ne propage jamais d'erreur vers l'utilisateur — la télémétrie est non-bloquante par conception.

```python
class MonitoringStorageService:
    @staticmethod
    async def record_rag_telemetry(...) -> None
    
    @staticmethod
    async def record_ingestor_run(...) -> None
    
    @staticmethod
    async def record_infrastructure_snapshot(...) -> None
```

### 6.2 Instrumentation de `seek_engine.py`

Le moteur RAG a été instrumenté avec des mesures `time.monotonic()` autour de chacune des cinq étapes du pipeline. L'écriture en base est déclenchée via `asyncio.create_task()` — patron *fire-and-forget* — **après** le dernier `yield` de la réponse streamée, garantissant que la télémétrie n'ajoute aucune latence perçue par l'utilisateur.

Deux chemins sont instrumentés indépendamment :
- **Chemin index** : condensation → search → validation → génération
- **Chemin web fallback** : activé quand `candidates_after_filter == 0`, les latences sont enregistrées avec `candidates_retrieved = 0`

La méthode `_retrieve_and_validate()` a été modifiée pour retourner un tuple `(List[Dict], int)` exposant le nombre brut de candidats avant filtrage, permettant le calcul du ratio de filtrage dans Grafana.

Le `thread_id` Chainlit est passé depuis `ui.py` via `cl.context.session.thread_id` et transmis à `search()` comme paramètre optionnel (valeur par défaut `""`), maintenant la compatibilité avec l'endpoint FastAPI `/ask` qui n'a pas de contexte Chainlit.

### 6.3 Instrumentation de `ingest_pipeline.py`

Le point d'entrée du job ETL a été restructuré avec :

- Un bloc `try/except/finally` encadrant l'appel à `IngestionService.run()`
- La récupération des statistiques depuis `service.stats` (dictionnaire d'instance mis à jour pendant le run : `total_raw`, `indexed`, `skipped`)
- L'appel à `_collect_infrastructure_metrics()` dans le bloc `finally`, garantissant l'écriture d'un snapshot même en cas d'exécution partielle
- La re-levée de l'exception originale pour que le Container App Job retourne un exit code non-nul et soit marqué `Failed` dans Azure

```python
async def main() -> None:
    start = time.monotonic()
    try:
        service = IngestionService()
        await service.run()
        events_fetched = service.stats.get("total_raw", 0)
        events_indexed = service.stats.get("indexed", 0)
        # ...
    except Exception as exc:
        # record failed run
        raise  # non-zero exit → Container App Job marks run as Failed
    finally:
        infra = _collect_infrastructure_metrics()
        await MonitoringStorageService.record_infrastructure_snapshot(**infra)
```

---

## 7. Tableaux de bord Grafana

### Dashboard 1 — Infrastructure Azure (datasource : Azure Monitor)

Panels configurés :
- Container Apps CPU et mémoire (time series, 24h glissantes)
- Replica count (stat panel — détection scale-to-zero)
- Taux d'erreurs HTTP 5xx (time series)
- PostgreSQL connections actives vs quota (gauge)
- PostgreSQL storage % (gauge avec seuils couleur)

Dashboards communautaires importés :
- **ID 16591** : Container Apps Environment overview
- **ID 16592** : Container App single view (configuré sur `pulsevents-ui` et `pulsevents-api`)

### Dashboard 2 — Performance applicative (datasource : PostgreSQL)

#### Panels satisfaction et usage

**Taux de satisfaction quotidien** (bar chart)
```sql
SELECT DATE_TRUNC('day', t."createdAt"::timestamp) AS time,
  COUNT(CASE WHEN f.value = 1 THEN 1 END) AS thumbs_up,
  COUNT(CASE WHEN f.value = 0 THEN 1 END) AS thumbs_down,
  ROUND(100.0 * COUNT(CASE WHEN f.value = 1 THEN 1 END)
    / NULLIF(COUNT(*), 0), 1) AS satisfaction_pct
FROM feedbacks f JOIN threads t ON f."threadId" = t."id"
WHERE t."createdAt"::timestamp >= NOW() - INTERVAL '30 days'
GROUP BY 1 ORDER BY 1;
```

**Projection de coût journalier (€)** (time series)
```sql
SELECT DATE_TRUNC('day', "createdAt") AS time,
  ROUND((SUM("prompt_tokens") / 1e6 * 2.50
    + SUM("completion_tokens") / 1e6 * 10.00) * 0.92, 3) AS cost_eur
FROM token_usage
WHERE "createdAt" >= NOW() - INTERVAL '30 days'
GROUP BY 1 ORDER BY 1;
```

**DAU — Utilisateurs actifs uniques** (time series)
```sql
SELECT DATE_TRUNC('day', "createdAt") AS time,
  COUNT(DISTINCT "userId") AS dau
FROM token_usage
WHERE "createdAt" >= NOW() - INTERVAL '30 days'
GROUP BY 1 ORDER BY 1;
```

**Ratio prompt/completion tokens** (time series)
```sql
SELECT DATE_TRUNC('day', "createdAt") AS time,
  ROUND(SUM("prompt_tokens")::numeric
    / NULLIF(SUM("completion_tokens"), 0), 2) AS ratio
FROM token_usage
WHERE "createdAt" >= NOW() - INTERVAL '14 days'
GROUP BY 1 ORDER BY 1;
```

#### Panels RAG telemetry

**Latence RAG p50 / p95** (time series)
```sql
SELECT DATE_TRUNC('hour', "createdAt") AS time,
  PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY total_latency_ms) AS p50_ms,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_latency_ms) AS p95_ms
FROM rag_telemetry
WHERE "createdAt" >= NOW() - INTERVAL '7 days'
GROUP BY 1 ORDER BY 1;
```

**Taux de zéro-résultats** (time series — indicateur critique de dégradation index)
```sql
SELECT DATE_TRUNC('day', "createdAt") AS time,
  ROUND(100.0 * COUNT(CASE WHEN query_had_zero_results THEN 1 END)
    / NULLIF(COUNT(*), 0), 1) AS zero_result_pct
FROM rag_telemetry
WHERE "createdAt" >= NOW() - INTERVAL '14 days'
GROUP BY 1 ORDER BY 1;
```

#### Panels ingestor et infrastructure

**Dernier run ingestor** (stat panel)
```sql
SELECT "runAt" AS last_run, status, events_indexed,
  ROUND(EXTRACT(EPOCH FROM (NOW() - "runAt")) / 3600, 1) AS hours_ago
FROM ingestor_runs ORDER BY "runAt" DESC LIMIT 1;
```

**Croissance de l'index Azure Search** (time series)
```sql
SELECT "snapshotAt" AS time, index_document_count AS chunks_indexed,
  ROUND(index_storage_bytes / 1048576.0, 1) AS index_mb
FROM infrastructure_snapshots
WHERE "snapshotAt" >= NOW() - INTERVAL '60 days'
ORDER BY 1;
```

**Blob Storage par couche Medallion** (stacked bar chart)
```sql
SELECT "snapshotAt" AS time,
  ROUND(bronze_bytes / 1048576.0, 1) AS bronze_mb,
  ROUND(silver_bytes / 1048576.0, 1) AS silver_mb,
  ROUND(gold_bytes / 1048576.0, 1) AS gold_mb
FROM infrastructure_snapshots
WHERE "snapshotAt" >= NOW() - INTERVAL '90 days'
ORDER BY 1;
```

**Utilisation index en % du quota (15 Go)**
```sql
SELECT
  ROUND(index_storage_bytes / 16106127360.0 * 100, 1) AS storage_pct_of_15gb,
  ROUND(index_document_count / 1000000.0 * 100, 2) AS docs_pct_of_1m
FROM infrastructure_snapshots ORDER BY "snapshotAt" DESC LIMIT 1;
```

---

## 8. Système d'alertes

Les alertes sont organisées en deux dossiers Grafana-managed :
- **PulsEvents-Infrastructure** : alertes Azure Monitor (A1–A9)
- **PulsEvents-Applicatif** : alertes PostgreSQL (B1–B6)

### Alertes Infrastructure (datasource Azure Monitor)

| ID | Ressource | Métrique | Condition | Sévérité |
|---|---|---|---|---|
| A1 | Container Apps | Replicas | = 0 pendant > 3 min (heures ouvrées) | CRITIQUE |
| A2 | Container Apps | Http5xxRequests | > 5% sur 5 min | CRITIQUE |
| A3 | Container Apps | CpuUsage | > 80% sur 10 min | MOYENNE |
| A4 | Container Apps | MemoryUsage | > 85% (850 Mi) | MOYENNE |
| A5 | PostgreSQL | active_connections | > 40 (80% de 50 max) | HAUTE |
| A6 | PostgreSQL | storage_percent | > 70% (~22 Go) | MOYENNE |
| A7 | ACR Basic | StorageUsed | > 8 Go (80% de 10 Go) | HAUTE |
| A8 | Cosmos DB | TotalRequestUnits | > 5 000 RU sur 5 min | MOYENNE |
| A9 | Cosmos DB | ServerSideLatency | > 500 ms en moyenne | MOYENNE |

> **Note** : La métrique `NormalizedRUConsumption` n'est pas disponible en mode Serverless Cosmos DB. `TotalRequestUnits` est utilisée en remplacement.

### Alertes Applicatives (datasource PostgreSQL)

| ID | Table | Condition | Sévérité | No data |
|---|---|---|---|---|
| B1 | `ingestor_runs` | Dernier run > 26h ou status != success | CRITIQUE | Alerting |
| B2 | `rag_telemetry` | p95 latence > 8 000 ms sur 30 min | HAUTE | OK |
| B3 | `rag_telemetry` | Taux zéro-résultats > 20% sur 1h | HAUTE | OK |
| B4 | `feedbacks` | Satisfaction < 50% sur 24h glissantes | HAUTE | OK |
| B5 | `token_usage` | Coût journalier projeté > 5 € | MOYENNE | OK |
| B6 | `infrastructure_snapshots` | Index storage > 10 Go (70% de 15 Go) | MOYENNE | OK |

Le paramètre **No data = Alerting** sur B1 est intentionnel : l'absence de ligne dans `ingestor_runs` est elle-même une anomalie (job qui ne démarre pas).

Le paramètre **No data = OK** sur B2/B3/B4 évite les fausses alertes nocturnes quand aucune requête utilisateur n'est envoyée.

---

## 9. Ressources sous quota surveillées

Inventaire complet des ressources Azure avec quota fixe dans l'architecture PulsEvents :

| Ressource | Quota | Usage actuel | Seuil d'alerte |
|---|---|---|---|
| ACR Basic — Storage | 10 Go | ~1 Go (2 images) | 8 Go (80%) |
| PostgreSQL B1ms — Storage | 32 Go | À surveiller | 22 Go (70%) |
| PostgreSQL B1ms — Connexions | 50 max | À surveiller | 40 (80%) |
| Azure AI Search Basic — Storage index | 15 Go | ~2,8 Go | 10 Go (70%) |
| Azure AI Search Basic — Documents | 1 000 000 | ~93 000 | Informatif |
| Cosmos DB Serverless — Burst RU/s | 5 000 RU/s | Faible | 5 000 RU / 5 min |
| Grafana Cloud Free — Active series | 10 000 | < 100 | Non critique |

---

## 10. Perspectives d'évolution

Les éléments suivants constituent la dette technique identifiée sur la partie monitoring, à adresser lors du passage de la version alpha à une version beta :

**Application Insights (P1)** — L'intégration du SDK Azure Application Insights permettrait des traces distribuées inter-services (corrélation ui → api → search → openai) sans requérir de développement spécifique de collecte. C'est le complément naturel de l'approche PostgreSQL actuelle pour les logs structurés.

**Décomposition de la latence web fallback (P2)** — La recherche web via `smolagents` n'est pas encore décomposée en sous-étapes dans `rag_telemetry`. Une colonne `web_search_latency_ms` permettrait de distinguer le temps de la recherche web du temps de génération dans le chemin fallback.

**Pool de connexions asyncpg (P2)** — Actuellement, `MonitoringStorageService` ouvre et ferme une connexion `asyncpg` à chaque écriture. Sur un volume élevé de requêtes concurrentes, un pool partagé (`asyncpg.create_pool`) serait plus performant.

**Alertes sur `service.stats["skipped"]` (P3)** — Le nombre d'événements ignorés par l'ingestor (transformation échouée) n'est pas encore exposé dans `ingestor_runs`. Son suivi permettrait de détecter une dégradation silencieuse de la qualité des données sources OpenAgenda.

---

*Document généré dans le cadre du projet de formation Data Engineer — OpenClassrooms Parcours 13.*  
*Architecture déployée sur Microsoft Azure — région France Central.*
