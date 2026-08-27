#!/usr/bin/env bash
# One-time Google Cloud bootstrap for the compliance fleet.
# Safe to re-run: every step is idempotent.
#
#   ./scripts/bootstrap.sh YOUR_PROJECT_ID
#
# Run this as the SAME Google account that holds the hackathon billing credits.
set -euo pipefail

PROJECT_ID="${1:?usage: bootstrap.sh PROJECT_ID}"
LOCATION="${LOCATION:-us-central1}"
BUCKET="gs://${PROJECT_ID}-agent-staging"

command -v gcloud >/dev/null || { echo "gcloud not installed: brew install --cask google-cloud-sdk"; exit 1; }

echo "==> Authenticating"
# Both logins are skipped when already present, so re-running costs no browser round
# trips. Note --brief exists on `auth login` but NOT on `auth application-default
# login`; passing it there fails with "unrecognized arguments".
if gcloud auth list --filter=status:ACTIVE --format='value(account)' | grep -q .; then
  echo "    already signed in as $(gcloud auth list --filter=status:ACTIVE --format='value(account)')"
else
  gcloud auth login --brief
fi

ADC_FILE="${CLOUDSDK_CONFIG:-$HOME/.config/gcloud}/application_default_credentials.json"
if [[ -f "$ADC_FILE" ]]; then
  echo "    application-default credentials already present"
else
  gcloud auth application-default login
fi

gcloud config set project "$PROJECT_ID"
# Without this, client libraries bill quota to gcloud's own client-id project and fail
# with "quota exceeded" or "API not enabled" even though the API is enabled here.
gcloud auth application-default set-quota-project "$PROJECT_ID" 2>/dev/null || true

echo
echo "==> Environment check"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
ORG_ID="$(gcloud projects describe "$PROJECT_ID" --format='value(parent.id)' 2>/dev/null || true)"
ORG_TYPE="$(gcloud projects describe "$PROJECT_ID" --format='value(parent.type)' 2>/dev/null || true)"
BILLING="$(gcloud billing projects describe "$PROJECT_ID" --format='value(billingEnabled)' 2>/dev/null || echo false)"

echo "    project id     : $PROJECT_ID"
echo "    project number : $PROJECT_NUMBER"
echo "    billing enabled: $BILLING"

if [[ "$ORG_TYPE" == "organization" ]]; then
  echo "    organization   : $ORG_ID"
  AGENT_PRINCIPAL_SET="principalSet://agents.global.org-${ORG_ID}.system.id.goog/attribute.platformContainer/aiplatform/projects/${PROJECT_NUMBER}"
else
  echo "    organization   : none (standalone project)"
  AGENT_PRINCIPAL_SET="principalSet://agents.global.project-${PROJECT_NUMBER}.system.id.goog/attribute.platformContainer/aiplatform/projects/${PROJECT_NUMBER}"
fi
echo "    agent principal: $AGENT_PRINCIPAL_SET"

if [[ "$BILLING" != "True" && "$BILLING" != "true" ]]; then
  echo
  echo "!!  Billing is NOT enabled on this project. Link the billing account that holds"
  echo "!!  the hackathon credits, then re-run:"
  echo "!!    gcloud billing projects link $PROJECT_ID --billing-account=BILLING_ACCOUNT_ID"
  exit 1
fi

echo
echo "==> Enabling APIs (this takes a couple of minutes)"
gcloud services enable \
  aiplatform.googleapis.com \
  agentregistry.googleapis.com \
  modelarmor.googleapis.com \
  dlp.googleapis.com \
  cloudtrace.googleapis.com \
  telemetry.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  storage.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project="$PROJECT_ID"

echo
echo "==> Staging bucket"
gcloud storage buckets describe "$BUCKET" >/dev/null 2>&1 \
  || gcloud storage buckets create "$BUCKET" --location="$LOCATION"

echo
echo "==> Model Armor template 'expense-guard'"
gcloud model-armor templates describe expense-guard --location="$LOCATION" >/dev/null 2>&1 \
  || gcloud model-armor templates create expense-guard \
       --location="$LOCATION" \
       --pi-and-jailbreak-filter-settings-enforcement=enabled \
       --pi-and-jailbreak-filter-settings-confidence-level=medium-and-above \
       --malicious-uri-filter-settings-enforcement=enabled \
       --basic-config-filter-enforcement=enabled

echo
echo "==> Security service account 'fleet-security'"
# Model Armor's regional endpoint (modelarmor.LOCATION.rep.googleapis.com) returns
# 401 for the bound tokens Agent Identity issues — they work against global service
# endpoints (aiplatform, iamcredentials) but not rep endpoints. The fix is one hop:
# the agent impersonates this plain service account for its security-tool calls, and
# the resulting ordinary OAuth token is accepted everywhere. IAM still names the
# agent principal set — it alone holds tokenCreator on the SA.
SECURITY_SA="fleet-security@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud services enable iamcredentials.googleapis.com --project="$PROJECT_ID"
gcloud iam service-accounts describe "$SECURITY_SA" --project="$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud iam service-accounts create fleet-security \
       --project="$PROJECT_ID" \
       --display-name="Fleet security-tool caller (Model Armor + DLP)"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SECURITY_SA" --role=roles/modelarmor.user --condition=None >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SECURITY_SA" --role=roles/dlp.user --condition=None >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$SECURITY_SA" \
  --project="$PROJECT_ID" \
  --member="$AGENT_PRINCIPAL_SET" --role=roles/iam.serviceAccountTokenCreator --condition=None >/dev/null
# The developer account too, so the impersonation path is testable locally before a
# deploy rather than only inside the runtime.
DEV_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)')"
gcloud iam service-accounts add-iam-policy-binding "$SECURITY_SA" \
  --project="$PROJECT_ID" \
  --member="user:$DEV_ACCOUNT" --role=roles/iam.serviceAccountTokenCreator --condition=None >/dev/null

echo
echo "==> Writing backend/.env"
mkdir -p backend
# Preserve the Memory Bank engine id across re-runs — deploy.py writes it after the
# first deploy and regenerating .env must not orphan the deployed engine.
EXISTING_ENGINE_ID="$(grep '^AGENT_ENGINE_ID=' backend/.env 2>/dev/null | cut -d= -f2 || true)"
cat > backend/.env <<ENVEOF
GOOGLE_GENAI_USE_ENTERPRISE=TRUE
GOOGLE_CLOUD_PROJECT=$PROJECT_ID
GOOGLE_CLOUD_PROJECT_NUMBER=$PROJECT_NUMBER
GOOGLE_CLOUD_LOCATION=$LOCATION
STAGING_BUCKET=$BUCKET
ARMOR_TEMPLATE=projects/$PROJECT_ID/locations/$LOCATION/templates/expense-guard
AGENT_PRINCIPAL_SET=$AGENT_PRINCIPAL_SET
FLEET_SECURITY_SA=$SECURITY_SA
ENVEOF
[[ -n "$EXISTING_ENGINE_ID" ]] && echo "AGENT_ENGINE_ID=$EXISTING_ENGINE_ID" >> backend/.env

echo
echo "Done. backend/.env written (gitignored)."
echo "Next: set a budget alert, then build backend/fleet/."
