"""Local stand-in for `adk eval backend/fleet evals/eval_set.json` (README Eval set
section) — runs the same decide() logic local_server.py streams to the radar, but
directly against evals/eval_set.json's expectations, with no SSE/timing involved.
Zero GCP/LLM calls. Delete once the real ADK agents exist and `adk eval` can run
against them directly; the case data in eval_set.json doesn't need to change.

Run: python backend/devtools/run_eval.py
"""

import json
import os
import sys

from decision import decide
from rules_loader import load_rules

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL_SET_PATH = os.path.join(REPO_ROOT, "evals", "eval_set.json")
RULES_PATH = os.path.join(REPO_ROOT, "backend", "policies", "rules.yaml")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run():
    rules = load_rules(RULES_PATH)
    eval_set = load_json(EVAL_SET_PATH)

    passed = 0
    failed = 0

    for case in eval_set["cases"]:
        fixture_path = os.path.join(REPO_ROOT, case["fixture"])
        report = load_json(fixture_path)
        result = decide(report, rules)

        mismatches = []
        if result["verdict"] != case["expected_verdict"]:
            mismatches.append(f"verdict: got {result['verdict']!r}, expected {case['expected_verdict']!r}")

        if "expected_violations" in case and sorted(result["violations"]) != sorted(case["expected_violations"]):
            mismatches.append(f"violations: got {result['violations']}, expected {case['expected_violations']}")

        if "expected_armor_verdict" in case and result["armor_verdict"] != case["expected_armor_verdict"]:
            mismatches.append(
                f"armor_verdict: got {result['armor_verdict']!r}, expected {case['expected_armor_verdict']!r}"
            )

        if "expected_dlp_redactions" in case and result["dlp_redactions"] != case["expected_dlp_redactions"]:
            mismatches.append(
                f"dlp_redactions: got {result['dlp_redactions']}, expected {case['expected_dlp_redactions']}"
            )

        if mismatches:
            failed += 1
            print(f"FAIL  {case['case_id']}")
            for m in mismatches:
                print(f"        {m}")
        else:
            passed += 1
            print(f"PASS  {case['case_id']}  -> {result['verdict']}")

    print(f"\n{passed} passed, {failed} failed, {len(eval_set['cases'])} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
