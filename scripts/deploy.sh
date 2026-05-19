ACA_ENV="env-pulsevents"
RESOURCE_GROUP="OpenClassrooms_P13"       
ACR_NAME="acrpulsevents"             
LOCATION="francecentral"             
APP_API="pulsevents-api"
APP_UI="pulsevents-ui"
JOB_INGESTOR="pulsevents-ingestor"
ACR_SERVER="$ACR_NAME.azurecr.io"

# ── 0. Load .env ──────────────────────────────────────────────
ENV_FILE="$(dirname "$0")/../.env"
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

# ── 2. Retrieve ACR credentials ────────────────────────────────
echo ""
echo "🔑 Retrieving ACR credentials..."
ACR_USERNAME=$(az acr credential show --name "$ACR_NAME" --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)
az acr login --name "$ACR_NAME"

docker build -t "$ACR_SERVER/pulsevents-api:latest" .
docker push "$ACR_SERVER/pulsevents-api:latest"
echo "✅ Image pushed: pulsevents-api"

# UI uses the same Dockerfile, different start command
docker build -t "$ACR_SERVER/pulsevents-ui:latest" .
docker push "$ACR_SERVER/pulsevents-ui:latest"
echo "✅ Image pushed: pulsevents-ui"

az containerapp update \
    --name pulsevents-api \
    --resource-group OpenClassrooms_P13 \
    --image acrpulsevents.azurecr.io/pulsevents-api:latest

az containerapp update \
    --name pulsevents-ui \
    --resource-group OpenClassrooms_P13 \
    --image acrpulsevents.azurecr.io/pulsevents-ui:latest

az containerapp job update \
  --name pulsevents-ingestor \
  --resource-group OpenClassrooms_P13 \
