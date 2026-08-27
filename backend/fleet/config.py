"""Environment configuration, written by scripts/bootstrap.sh into backend/.env.

Imported by every other module in the fleet, so a missing value fails here with a
clear message rather than as an opaque permissions error several layers down.
"""

import os
import pathlib

_ENV_PATH = pathlib.Path(__file__).resolve().parent.parent / ".env"


def _load_env_file():
    """Minimal .env reader. No python-dotenv dependency for six flat keys."""
    if not _ENV_PATH.exists():
        return
    for raw in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file()


def _required(key):
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(
            f"{key} is not set. Run ./scripts/bootstrap.sh PROJECT_ID to generate "
            f"backend/.env, or export {key} manually."
        )
    return value


PROJECT_ID = _required("GOOGLE_CLOUD_PROJECT")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
PROJECT_NUMBER = os.environ.get("GOOGLE_CLOUD_PROJECT_NUMBER", "")
STAGING_BUCKET = os.environ.get("STAGING_BUCKET", f"gs://{PROJECT_ID}-agent-staging")

# Full resource name of the Model Armor template created by bootstrap.sh.
ARMOR_TEMPLATE = os.environ.get(
    "ARMOR_TEMPLATE",
    f"projects/{PROJECT_ID}/locations/{LOCATION}/templates/expense-guard",
)

# Which principal set IAM bindings target. Differs for org vs standalone projects —
# see README engineering notes. bootstrap.sh derives the correct one.
AGENT_PRINCIPAL_SET = os.environ.get("AGENT_PRINCIPAL_SET", "")

# Set by fleet/deploy.py once the Memory Bank instance exists.
AGENT_ENGINE_ID = os.environ.get("AGENT_ENGINE_ID", "")

MODEL = os.environ.get("FLEET_MODEL", "gemini-3.5-flash")

# Routes the GenAI SDK at the enterprise platform rather than the public Gemini API.
os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", LOCATION)

POLICY_PATH = pathlib.Path(__file__).resolve().parent.parent / "policies" / "rules.yaml"
FIXTURES_DIR = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "reports"
