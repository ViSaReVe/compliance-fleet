"""Deploy the fleet to Agent Runtime, with Agent Identity enabled.

Agent Identity gives each deployed agent its own SPIFFE identity and mTLS-bound
credentials, so "the Screening Agent cannot reach PII redaction" becomes an IAM
fact rather than an allowlist in our own code. That is the difference between the
governance story being demonstrated and being described.

Run once to create the Memory Bank instance and deploy:

    python -m fleet.deploy

Then put the printed AGENT_ENGINE_ID into backend/.env.
"""

import vertexai
from vertexai import types
from vertexai.agent_engines import AdkApp

from . import config, orchestrator


def client():
    return vertexai.Client(
        project=config.PROJECT_ID,
        location=config.LOCATION,
        http_options={"api_version": "v1beta1"},
    )


def create_memory_bank():
    """Memory Bank instance. Its id is also the agent engine id used for sessions."""
    engine = client().agent_engines.create(
        config={
            "display_name": "expense-compliance-memory",
            "generation_config": {
                "model": (
                    f"projects/{config.PROJECT_ID}/locations/{config.LOCATION}"
                    f"/publishers/google/models/{config.MODEL}"
                )
            },
        }
    )
    engine_id = engine.api_resource.name.split("/")[-1]
    print(f"[deploy] Memory Bank created: {engine_id}")
    print(f"[deploy] add to backend/.env:  AGENT_ENGINE_ID={engine_id}")
    return engine_id


def deploy_fleet():
    app = AdkApp(agent=orchestrator.build_fleet())
    remote = client().agent_engines.create(
        agent=app,
        config={
            "display_name": "expense-compliance-fleet",
            "identity_type": types.IdentityType.AGENT_IDENTITY,
            "staging_bucket": config.STAGING_BUCKET,
            "requirements": [
                "google-cloud-aiplatform[agent_engines,adk]",
                "google-cloud-modelarmor",
                "google-cloud-dlp",
                "PyYAML",
            ],
        },
    )
    name = remote.api_resource.name
    print(f"[deploy] fleet deployed: {name}")
    print("[deploy] grant it access with the principal set from backend/.env:")
    print(f"           {config.AGENT_PRINCIPAL_SET}")
    return name


def main():
    engine_id = config.AGENT_ENGINE_ID or create_memory_bank()
    if not config.AGENT_ENGINE_ID:
        print("[deploy] set AGENT_ENGINE_ID in backend/.env, then re-run to deploy the fleet")
        return
    print(f"[deploy] using Memory Bank {engine_id}")
    deploy_fleet()


if __name__ == "__main__":
    main()
