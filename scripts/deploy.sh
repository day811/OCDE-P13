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

# Use a timestamped tag to guarantee Azure pulls the new image
IMAGE_TAG=$(date +%Y%m%d%H%M%S)

# Build once, tag twice (same Dockerfile, SERVICE env var drives behaviour)
docker build -t "$ACR_SERVER/pulsevents-api:latest" \
             -t "$ACR_SERVER/pulsevents-api:$IMAGE_TAG" \
             -t "$ACR_SERVER/pulsevents-ui:latest" \
             -t "$ACR_SERVER/pulsevents-ui:$IMAGE_TAG" .

docker push "$ACR_SERVER/pulsevents-api:latest"
docker push "$ACR_SERVER/pulsevents-api:$IMAGE_TAG"
docker push "$ACR_SERVER/pulsevents-ui:latest"
docker push "$ACR_SERVER/pulsevents-ui:$IMAGE_TAG"

echo "✅ Images pushed with tags: latest + $IMAGE_TAG"

# ...
# (sections 4, 5, 6 : az containerapp create — inchangées)
# ...

# ── 8. Force update all running services with the new versioned tag ──
echo ""
echo "🔄 Updating Container Apps to image tag: $IMAGE_TAG"

az containerapp update \
    --name "$APP_API" \
    --resource-group "$RESOURCE_GROUP" \
    --image "$ACR_SERVER/pulsevents-api:$IMAGE_TAG"
echo "✅ API updated"

az containerapp update \
    --name "$APP_UI" \
    --resource-group "$RESOURCE_GROUP" \
    --image "$ACR_SERVER/pulsevents-ui:$IMAGE_TAG"
echo "✅ UI updated"

# Fix: --image was missing for the ingestor job
az containerapp job update \
    --name "$JOB_INGESTOR" \
    --resource-group "$RESOURCE_GROUP" \
    --image "$ACR_SERVER/pulsevents-api:$IMAGE_TAG"
echo "✅ Ingestor job updated"

echo ""
echo "Image tag deployed: $IMAGE_TAG"