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
echo "==> Writing backend/.env"
mkdir -p backend
cat > backend/.env <<ENVEOF
GOOGLE_GENAI_USE_ENTERPRISE=TRUE
GOOGLE_CLOUD_PROJECT=$PROJECT_ID
GOOGLE_CLOUD_PROJECT_NUMBER=$PROJECT_NUMBER
GOOGLE_CLOUD_LOCATION=$LOCATION
STAGING_BUCKET=$BUCKET
ARMOR_TEMPLATE=projects/$PROJECT_ID/locations/$LOCATION/templates/expense-guard
AGENT_PRINCIPAL_SET=$AGENT_PRINCIPAL_SET
ENVEOF

echo
echo "Done. backend/.env written (gitignored)."
echo "Next: set a budget alert, then build backend/fleet/."
