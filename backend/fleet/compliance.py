"""The PII / Compliance agent's two security calls.

These are separate products doing separate jobs, and conflating them is the single
most common mistake with this stack:

  Model Armor  detects prompt injection and jailbreak attempts, and BLOCKS. With the
               Sensitive Data Protection filter it still blocks rather than returning
               de-identified text — the sanitized data is never passed back.
  Cloud DLP    actually rewrites text, replacing card numbers, SSNs, emails and
               addresses with tokens. This is what makes redaction real.

So: Armor guards the boundary, DLP cleans the payload. Both, in that order.
"""

import google.auth
from google.auth import impersonated_credentials
from google.cloud import dlp_v2, modelarmor_v1
from google.api_core import client_options as client_options_lib

from . import config

# Redaction targets. Deliberately narrow: broad infoType sets produce false positives
# on expense text (merchant names read as person names) which look like bugs on video.
INFO_TYPES = [
    {"name": "CREDIT_CARD_NUMBER"},
    {"name": "US_SOCIAL_SECURITY_NUMBER"},
    {"name": "EMAIL_ADDRESS"},
    {"name": "STREET_ADDRESS"},
    {"name": "PHONE_NUMBER"},
]

_DEIDENTIFY_CONFIG = {
    "info_type_transformations": {
        "transformations": [
            {
                "info_types": [{"name": name["name"]}],
                "primitive_transformation": {
                    "replace_config": {
                        "new_value": {"string_value": f"[REDACTED_{name['name']}]"}
                    }
                },
            }
            for name in INFO_TYPES
        ]
    }
}

_armor_client = None
_dlp_client = None
_security_credentials = None


def _credentials():
    """Credentials for the security-tool clients.

    Agent Identity's bound tokens are accepted by global service endpoints but come
    back 401 ("Expected OAuth 2 access token") from regional rep endpoints, which is
    where Model Armor lives. Impersonating the fleet-security SA turns them into an
    ordinary OAuth token that every endpoint accepts, while IAM on the SA still names
    only the agent principal set. Returns None (ambient credentials) when no SA is
    configured, so local development needs no extra setup.
    """
    global _security_credentials
    if not config.SECURITY_SA:
        return None
    if _security_credentials is None:
        source, _ = google.auth.default()
        _security_credentials = impersonated_credentials.Credentials(
            source_credentials=source,
            target_principal=config.SECURITY_SA,
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    return _security_credentials


def _armor():
    global _armor_client
    if _armor_client is None:
        # Model Armor is regional and requires an explicit endpoint override.
        _armor_client = modelarmor_v1.ModelArmorClient(
            credentials=_credentials(),
            client_options=client_options_lib.ClientOptions(
                api_endpoint=f"modelarmor.{config.SERVICE_LOCATION}.rep.googleapis.com"
            ),
        )
    return _armor_client


def _dlp():
    global _dlp_client
    if _dlp_client is None:
        _dlp_client = dlp_v2.DlpServiceClient(credentials=_credentials())
    return _dlp_client


def screen_for_injection(text):
    """Ask Model Armor whether this free text is trying to steer the agent.

    Returns (blocked: bool, verdict: str | None). Fails closed on transport errors:
    an unreachable guardrail must not become an open door.
    """
    if not text:
        return False, None

    request = modelarmor_v1.SanitizeUserPromptRequest(
        name=config.ARMOR_TEMPLATE,
        user_prompt_data=modelarmor_v1.DataItem(text=text),
    )
    try:
        response = _armor().sanitize_user_prompt(request=request)
    except Exception as exc:  # noqa: BLE001
        return True, f"ARMOR_UNAVAILABLE: {exc}"

    result = response.sanitization_result
    if result.filter_match_state != modelarmor_v1.FilterMatchState.MATCH_FOUND:
        return False, None

    # filter_results is a map of filter name -> FilterResult, and FilterResult is a
    # wrapper holding one populated sub-result per filter type. Each sub-result
    # carries its own match_state; there is no match_state on the wrapper.
    match = modelarmor_v1.FilterMatchState.MATCH_FOUND
    triggered = []
    for name, outcome in result.filter_results.items():
        for field in (
            "pi_and_jailbreak_filter_result",
            "rai_filter_result",
            "malicious_uri_filter_result",
            "csam_filter_filter_result",
        ):
            sub = getattr(outcome, field, None)
            if sub is not None and getattr(sub, "match_state", None) == match:
                triggered.append(name)
                break

    detail = f" ({', '.join(sorted(triggered))})" if triggered else ""
    return True, f"PROMPT_INJECTION_BLOCKED{detail}"


def redact(text):
    """Rewrite PII out of text via Cloud DLP. Returns (clean_text, redaction_count).

    Fails closed too: if DLP is unreachable we return no text at all rather than
    persisting the raw string, because the whole promise is that nothing unredacted
    is ever written down.
    """
    if not text:
        return text, 0

    try:
        response = _dlp().deidentify_content(
            request={
                "parent": f"projects/{config.PROJECT_ID}/locations/{config.SERVICE_LOCATION}",
                "deidentify_config": _DEIDENTIFY_CONFIG,
                "inspect_config": {
                    "info_types": INFO_TYPES,
                    # Pinned rather than left default so behaviour cannot shift under
                    # us. Do NOT lower this to UNLIKELY: at that threshold a card
                    # number also matches PHONE_NUMBER and gets double-redacted as
                    # "[REDACTED_CREDIT_CARD_NUMBER][REDACTED_PHONE_NUMBER]", which
                    # looks like a bug on video. Verified live against the project.
                    "min_likelihood": dlp_v2.Likelihood.POSSIBLE,
                },
                "item": {"value": text},
            }
        )
    except Exception as exc:  # noqa: BLE001
        return f"[REDACTION_UNAVAILABLE: {exc}]", 0

    clean = response.item.value

    # TransformationSummary has no top-level count; the counts live in its `results`
    # list, one SummaryResult per outcome code. Only SUCCESS entries are redactions.
    success = dlp_v2.TransformationSummary.TransformationResultCode.SUCCESS
    count = 0
    if response.overview:
        for summary in response.overview.transformation_summaries:
            for outcome in summary.results:
                if outcome.code == success:
                    count += outcome.count
    return clean, count
