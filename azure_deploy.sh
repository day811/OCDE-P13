#!/bin/bash
# =============================================================
# deploy_azure.sh — Puls-Events Azure Container Apps Deployment
# Reads credentials from .env file (same directory as script)
# Usage: bash deploy_azure.sh
# =============================================================
set -e  # Stop on first error

# ── 0. Load .env ──────────────────────────────────────────────
ENV_FILE="$(dirname "$0")/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env file not found at $ENV_FILE"
    exit 1
fi

# Export all non-comment, non-empty lines from .env
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

echo "✅ .env loaded"

# ── 1. Deployment variables — edit these to match your Azure setup ──
RESOURCE_GROUP="OpenClassrooms_P13"
LOCATION="francecentral"
ACR_NAME="acrpulsevents"           # Must be globally unique, lowercase, no hyphens
ACA_ENV="env-pulsevents"
APP_API="pulsevents-api"
APP_UI="pulsevents-ui"
JOB_INGESTOR="pulsevents-ingestor"
ACR_SERVER="$ACR_NAME.azurecr.io"

# ── 2. Retrieve ACR credentials ────────────────────────────────

az acr update -n acrpulsevents --admin-enabled true
echo ""
echo "🔑 Retrieving ACR credentials..."
ACR_USERNAME=$(az acr credential show --name "$ACR_NAME" --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)

# ── 3. Build & push Docker images ─────────────────────────────
echo ""
echo "🐳 Building and pushing Docker images..."
az acr login --name "$ACR_NAME"

docker build -t "$ACR_SERVER/pulsevents-api:latest" .
docker push "$ACR_SERVER/pulsevents-api:latest"
echo "✅ Image pushed: pulsevents-api"

# UI uses the same Dockerfile, different start command
docker build -t "$ACR_SERVER/pulsevents-ui:latest" .
docker push "$ACR_SERVER/pulsevents-ui:latest"
echo "✅ Image pushed: pulsevents-ui"

# ── 4. Create Container Apps Environment (skip if exists) ─────

echo ""
echo "🌐 Creating Container Apps Environment..."
az provider register -n Microsoft.OperationalInsights --wait
az provider register -n Microsoft.App --wait
az containerapp env create \
    --name "$ACA_ENV" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    2>/dev/null || echo "ℹ️  Environment already exists, skipping."

# ── 5. Deploy API (internal ingress) ──────────────────────────
echo ""
echo "🚀 Deploying API container app..."
az containerapp create \
    --name "$APP_API" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ACA_ENV" \
    --image "$ACR_SERVER/pulsevents-api:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_USERNAME" \
    --registry-password "$ACR_PASSWORD" \
    --command "uvicorn" \
    --args "app.main:app" "--host" "0.0.0.0" "--port" "8000" \
    --target-port 8000 \
    --ingress internal \
    --min-replicas 0 \
    --max-replicas 2 \
    --cpu 0.5 \
    --memory 1.0Gi \
    --secrets \
        azure-search-endpoint="$AZURE_SEARCH_ENDPOINT" \
        azure-search-key="$AZURE_SEARCH_API_KEY" \
        cosmos-endpoint="$COSMOS_ENDPOINT" \
        cosmos-key="$COSMOS_KEY" \
        storage-conn-string="$AZURE_STORAGE_CONNECTION_STRING" \
        openai-endpoint="$AZURE_OPENAI_ENDPOINT" \
        openai-key="$AZURE_OPENAI_API_KEY" \
        chainlit-secret="$CHAINLIT_AUTH_SECRET" \
    --env-vars \
        ENV=AZURE \
        APP_NAME="$APP_NAME" \
        AZURE_SEARCH_INDEX_NAME="$AZURE_SEARCH_INDEX_NAME" \
        AZURE_OPENAI_DEPLOYMENT="$AZURE_OPENAI_DEPLOYMENT" \
        AZURE_EMBEDDING_DEPLOYMENT="$AZURE_EMBEDDING_DEPLOYMENT" \
        AZURE_OPENAI_API_VERSION="$AZURE_OPENAI_API_VERSION" \
        COSMOS_DATABASE="$COSMOS_DATABASE" \
        COSMOS_CONTAINER_USERS="$COSMOS_CONTAINER_USERS" \
        COSMOS_CONTAINER_CONVERSATIONS="conversations" \
        MAX_RECORDS="$MAX_RECORDS" \
        AZURE_SEARCH_ENDPOINT=secretref:azure-search-endpoint \
        AZURE_SEARCH_API_KEY=secretref:azure-search-key \
        COSMOS_ENDPOINT=secretref:cosmos-endpoint \
        COSMOS_KEY=secretref:cosmos-key \
        AZURE_STORAGE_CONNECTION_STRING=secretref:storage-conn-string \
        AZURE_OPENAI_ENDPOINT=secretref:openai-endpoint \
        AZURE_OPENAI_API_KEY=secretref:openai-key \
        CHAINLIT_AUTH_SECRET=secretref:chainlit-secret \
        SERVICE=api


echo "✅ API deployed"

# ── 6. Deploy UI (external ingress) ───────────────────────────
echo ""
echo "🎨 Deploying UI container app..."
az containerapp create \
    --name "$APP_UI" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ACA_ENV" \
    --image "$ACR_SERVER/pulsevents-ui:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_USERNAME" \
    --registry-password "$ACR_PASSWORD" \
    --target-port 8001 \
    --ingress external \
    --min-replicas 0 \
    --max-replicas 2 \
    --cpu 0.5 \
    --memory 1.0Gi \
    --secrets \
        azure-search-endpoint="$AZURE_SEARCH_ENDPOINT" \
        azure-search-key="$AZURE_SEARCH_API_KEY" \
        cosmos-endpoint="$COSMOS_ENDPOINT" \
        cosmos-key="$COSMOS_KEY" \
        storage-conn-string="$AZURE_STORAGE_CONNECTION_STRING" \
        openai-endpoint="$AZURE_OPENAI_ENDPOINT" \
        openai-key="$AZURE_OPENAI_API_KEY" \
        chainlit-secret="$CHAINLIT_AUTH_SECRET" \
    --env-vars \
        ENV=AZURE \
        APP_NAME="$APP_NAME" \
        AZURE_SEARCH_INDEX_NAME="$AZURE_SEARCH_INDEX_NAME" \
        AZURE_OPENAI_DEPLOYMENT="$AZURE_OPENAI_DEPLOYMENT" \
        AZURE_EMBEDDING_DEPLOYMENT="$AZURE_EMBEDDING_DEPLOYMENT" \
        AZURE_OPENAI_API_VERSION="$AZURE_OPENAI_API_VERSION" \
        COSMOS_DATABASE="$COSMOS_DATABASE" \
        COSMOS_CONTAINER_USERS="$COSMOS_CONTAINER_USERS" \
        COSMOS_CONTAINER_CONVERSATIONS="conversations" \
        MAX_RECORDS="$MAX_RECORDS" \
        AZURE_SEARCH_ENDPOINT=secretref:azure-search-endpoint \
        AZURE_SEARCH_API_KEY=secretref:azure-search-key \
        COSMOS_ENDPOINT=secretref:cosmos-endpoint \
        COSMOS_KEY=secretref:cosmos-key \
        AZURE_STORAGE_CONNECTION_STRING=secretref:storage-conn-string \
        AZURE_OPENAI_ENDPOINT=secretref:openai-endpoint \
        AZURE_OPENAI_API_KEY=secretref:openai-key \
        CHAINLIT_AUTH_SECRET=secretref:chainlit-secret \
        SERVICE=ui


echo "✅ UI deployed"

# ── 7. Deploy Ingestor as a Container App Job ──────────────────
echo ""
echo "⚙️  Creating Ingestor job..."
az containerapp job create \
    --name "$JOB_INGESTOR" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ACA_ENV" \
    --image "$ACR_SERVER/pulsevents-api:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_USERNAME" \
    --registry-password "$ACR_PASSWORD" \
    --replica-timeout 1800 \
    --replica-retry-limit 1 \
    --trigger-type Schedule \
    --cron-expression "0 3 * * *" \
    --parallelism 1 \
    --replica-completion-count 1 \
    --secrets \
        azure-search-endpoint="$AZURE_SEARCH_ENDPOINT" \
        azure-search-key="$AZURE_SEARCH_API_KEY" \
        cosmos-endpoint="$COSMOS_ENDPOINT" \
        cosmos-key="$COSMOS_KEY" \
        storage-conn-string="$AZURE_STORAGE_CONNECTION_STRING" \
        openai-key="$AZURE_OPENAI_API_KEY" \
        openai-endpoint="$AZURE_OPENAI_ENDPOINT" \
    --env-vars \
        SERVICE=ingestor \
        ENV=AZURE \
        MAX_RECORDS="$MAX_RECORDS" \
        OPENAGENDA_URL="$OPENAGENDA_URL" \
        AZURE_SEARCH_INDEX_NAME="$AZURE_SEARCH_INDEX_NAME" \
        AZURE_EMBEDDING_DEPLOYMENT="$AZURE_EMBEDDING_DEPLOYMENT" \
        AZURE_OPENAI_API_VERSION="$AZURE_OPENAI_API_VERSION" \
        AZURE_SEARCH_ENDPOINT=secretref:azure-search-endpoint \
        AZURE_SEARCH_API_KEY=secretref:azure-search-key \
        COSMOS_ENDPOINT=secretref:cosmos-endpoint \
        COSMOS_KEY=secretref:cosmos-key \
        AZURE_STORAGE_CONNECTION_STRING=secretref:storage-conn-string \
        AZURE_OPENAI_API_KEY=secretref:openai-key \
        AZURE_OPENAI_ENDPOINT=secretref:openai-endpoint


echo "✅ Ingestor job created"

# ── 8. Print summary ───────────────────────────────────────────
echo ""
echo "=============================================="
echo "✅ DEPLOYMENT COMPLETE"
echo "=============================================="
UI_URL=$(az containerapp show \
    --name "$APP_UI" \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.configuration.ingress.fqdn" -o tsv)
echo "🌐 UI public URL : https://$UI_URL"
echo ""
echo "To run the ingestor manually:"
echo "  az containerapp job start --name $JOB_INGESTOR --resource-group $RESOURCE_GROUP"
echo ""
echo "To stream UI logs:"
echo "  az containerapp logs show --name $APP_UI --resource-group $RESOURCE_GROUP --follow"
echo "=============================================="