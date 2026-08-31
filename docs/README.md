# Docs

Start with the top two. They are where the interesting work is.

## The engineering

| | |
| :--- | :--- |
| **[EVALUATION.md](EVALUATION.md)** | We attacked our own system and it approved an $840 expense with no receipt — three runs out of three, on one sentence, with no prompt injection involved. The finding, the reproduction, the architectural fix, the regression gate, and what is still weak. |
| **[REVIEW.md](REVIEW.md)** | The same codebase read by five different reviewers — a judge, a red teamer, an SRE, the finance reviewer who has to use it, and a staff engineer. Every finding has a command that reproduces it. |
| **[SYSTEM.md](SYSTEM.md)** | What this system actually is: four layers, each with a different trust level, and why naming them made the vulnerability obvious in hindsight. Positioned against CaMeL, AgentDojo, τ-bench and Anthropic's workflow-vs-agent guidance. |
| **[architecture.png](architecture.png)** | The diagram. Source in [architecture.svg](architecture.svg). |

## Running it

| | |
| :--- | :--- |
| **[FRONTEND.md](FRONTEND.md)** | Running the radar with no Google Cloud account at all. `backend/devtools/` has zero third-party dependencies and serves the identical contract on system Python. |

The full setup — bootstrap, deploy, verify — is in the [root README](../README.md).

## How it was submitted

Kept because a hackathon submission is part of the project's history, not separate
from it. Also useful if you are doing one.

| | |
| :--- | :--- |
| [SUBMISSION.md](SUBMISSION.md) | Every requirement checked against the posted official rules, plus the per-track scoring sub-criteria and where this project was weakest against them. |
| [DEMO.md](DEMO.md) | The operational half of the video: pre-flight, capture settings, what to do when something breaks mid-take. |
| [SCRIPT.md](SCRIPT.md) | The speaking script — screen map, narration, measured to 3:47 against a 3:55 cut. |
| [DEVPOST.md](DEVPOST.md) · [devpost-story.md](devpost-story.md) | The submission form answers and the project story. |
| [SOHAN-BRIEF.md](SOHAN-BRIEF.md) | Onboarding written for a teammate who had never touched the backend. |
| [HANDOFF.md](HANDOFF.md) | Running state between working sessions — what was verified, what was still broken, and the traps already paid for. |
