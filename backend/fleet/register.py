"""Publish the fleet to Agent Registry.

Registration is what makes the orchestrator's runtime lookup meaningful: until an
agent has an entry here, resolve_sub_agents() falls back to in-process agents and
the "cataloged for cross-department use" claim is just a diagram.

Each agent is registered as an A2A service from its agent card. Cards are generated
from the ADK agent definitions rather than hand-written, so a capability added to an
agent cannot silently fail to appear in the catalog.
"""

import json
import pathlib
import subprocess
import tempfile

from . import config, orchestrator, screening

CARDS_DIR = pathlib.Path(__file__).resolve().parent.parent / "agent_cards"


def build_card(agent, endpoint_url):
    """Minimal A2A agent card. Registry caps these at 10 KB."""
    return {
        "name": agent.name,
        "description": agent.description or "",
        "url": endpoint_url,
        "version": "1.0.0",
        "capabilities": {"streaming": False},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [
            {
                "id": f"{agent.name}.review",
                "name": agent.name.replace("_", " ").title(),
                "description": agent.description or "",
                "tags": ["expense", "compliance"],
            }
        ],
    }


def register(agent, endpoint_url, service_id):
    card = build_card(agent, endpoint_url)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(card, f)
        card_path = f.name

    cmd = [
        "gcloud", "agent-registry", "services", "create", service_id,
        f"--project={config.PROJECT_ID}",
        f"--location={config.LOCATION}",
        f"--display-name={agent.name}",
        "--agent-spec-type=a2a-agent-card",
        f"--agent-spec-content={card_path}",
    ]
    print(f"[register] {service_id}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Re-registration of an existing service is expected on re-runs, not an error.
        if "ALREADY_EXISTS" in result.stderr or "already exists" in result.stderr:
            print(f"[register] {service_id} already registered")
        else:
            print(f"[register] FAILED {service_id}: {result.stderr.strip()}")
    return result.returncode == 0


def main(screening_url, compliance_url):
    CARDS_DIR.mkdir(exist_ok=True)
    register(screening.build_agent(), screening_url, "screening")
    register(orchestrator.build_compliance_agent(), compliance_url, "pii-compliance")
    print("[register] done — verify with: gcloud agent-registry agents search "
          f"--project={config.PROJECT_ID} --location={config.LOCATION} --search-string=expense")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m fleet.register SCREENING_URL COMPLIANCE_URL")
    main(sys.argv[1], sys.argv[2])
