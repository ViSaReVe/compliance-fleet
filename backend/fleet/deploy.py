"""Deploy the fleet to Agent Runtime, with Agent Identity enabled.

Agent Identity gives each deployed agent its own SPIFFE identity and mTLS-bound
credentials, so "the Screening Agent cannot reach PII redaction" becomes an IAM
fact rather than an allowlist in our own code. That is the difference between the
governance story being demonstrated and being described.

Run once to create the Memory Bank instance and deploy:

    python -m fleet.deploy

Then put the printed AGENT_ENGINE_ID into backend/.env.
"""

import agentplatform
from vertexai import types
from vertexai.agent_engines import AdkApp

from . import config, orchestrator


def client():
    # vertexai.Client is deprecated in favour of agentplatform.Client. They are
    # different classes, not an alias, so this is a real swap rather than cosmetic.
    return agentplatform.Client(
        project=config.PROJECT_ID,
        location=config.LOCATION,
        http_options={"api_version": "v1beta1"},
    )


def create_memory_bank():
    """Memory Bank instance. Its id is also the agent engine id used for sessions."""
    # generation_config is NOT a top-level AgentEngineConfig field — passing it there
    # fails pydantic validation with "Extra inputs are not permitted". Memory Bank
    # settings live under context_spec.memory_bank_config.
    engine = client().agent_engines.create(
        config={
            "display_name": "expense-compliance-memory",
            "context_spec": {
                "memory_bank_config": {
                    "generation_config": {
                        "model": config.MODEL_PATH
                    }
                }
            },
        }
    )
    engine_id = engine.api_resource.name.split("/")[-1]
    print(f"[deploy] Memory Bank created: {engine_id}")
    print(f"[deploy] add to backend/.env:  AGENT_ENGINE_ID={engine_id}")
    return engine_id


def deploy_fleet():
    app = AdkApp(agent=orchestrator.build_fleet())
    # The remote GenAI client builds its endpoint from GOOGLE_CLOUD_LOCATION.
    # Left at us-central1 it calls us-central1-aiplatform.googleapis.com, which
    # cannot serve a locations/global publisher model however the path is
    # written — so gemini-3.5-flash 404s in the runtime while working locally.
    env_vars = {
        "GOOGLE_CLOUD_LOCATION": config.MODEL_LOCATION,
        "GOOGLE_GENAI_USE_ENTERPRISE": "TRUE",
        # GOOGLE_CLOUD_PROJECT is reserved by Agent Runtime and rejected
        # with FAILED_PRECONDITION; it is injected for you.
        "FLEET_SERVICE_LOCATION": config.SERVICE_LOCATION,
        "ARMOR_TEMPLATE": config.ARMOR_TEMPLATE,
        # The runtime injects GOOGLE_CLOUD_PROJECT as the project NUMBER; DLP
        # rejects number-form parents, so ship the id under our own key.
        "FLEET_PROJECT_ID": config.PROJECT_ID,
    }
    if config.SECURITY_SA:
        # Model Armor's rep endpoint 401s Agent Identity's bound tokens; the
        # security tools impersonate this SA instead. See compliance.py.
        env_vars["FLEET_SECURITY_SA"] = config.SECURITY_SA
        # The default Context-Aware Access policy binds the agent's tokens to its
        # mTLS certificate, and services that cannot validate that binding reject
        # them outright — iamcredentials.generateAccessToken (the impersonation
        # hop) 401s with "Unable to acquire impersonated credentials". Opting out
        # trades the anti-theft binding for tokens the rest of Google Cloud
        # accepts; scope stays limited because the security tools still run as
        # the narrowly-granted fleet-security SA, not the agent principal.
        env_vars["GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES"] = "False"
    remote = client().agent_engines.create(
        agent=app,
        config={
            "display_name": "expense-compliance-fleet",
            "identity_type": types.IdentityType.AGENT_IDENTITY,
            "env_vars": env_vars,
            "staging_bucket": config.STAGING_BUCKET,
            # Tools are plain functions, so cloudpickle serialises them by module
            # reference rather than by value — the remote environment then dies at
            # startup with "No module named 'fleet'". Shipping the package fixes it.
            # Requires running the deploy from backend/ so this path resolves.
            # policies/ ships too: config.POLICY_PATH resolves to
            # <parent of fleet>/policies/rules.yaml, which remotely is
            # /code/policies/rules.yaml. Without it the policy tool raises
            # FileNotFoundError at call time rather than at startup.
            "extra_packages": ["fleet", "policies"],
            # pydantic and cloudpickle are not optional. The deploy warns
            # "The following requirements are missing: {'pydantic', 'cloudpickle'}"
            # and then succeeds anyway — but the agent object never rehydrates in the
            # remote environment, so the engine comes up exposing only session and
            # memory methods and every query returns "User-specified method
            # `async_stream_query` not found".
            "requirements": [
                "google-cloud-aiplatform[agent_engines,adk]",
                "google-cloud-modelarmor",
                "google-cloud-dlp",
                "cloudpickle",
                "pydantic",
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
