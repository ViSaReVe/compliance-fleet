"""Minimal parser for policies/rules.yaml — deliberately not a real YAML library
dependency (PyYAML isn't installed anywhere in this repo yet; backend/requirements.txt
doesn't exist until Vidya's Day 2). Only handles the flat key: value / key: [] shape
that rules.yaml actually uses. Once backend/requirements.txt exists with PyYAML,
screening.py should just use yaml.safe_load() instead of this.
"""

import re


def load_rules(path):
    rules = {}
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.split("#", 1)[0].strip()
            if not line or line.endswith(":"):
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value in ("[]", ""):
                rules[key] = []
            elif re.fullmatch(r"-?\d+(\.\d+)?", value):
                rules[key] = float(value) if "." in value else int(value)
            else:
                rules[key] = value.strip('"').strip("'")

    # Recover block-style lists ("key:\n  - item"), which the flat parser above skips.
    #
    # This used to name the two keys it knew about. When rules.yaml later grew
    # `escalating_violations`, this parser silently dropped it — fleet/policy.py read
    # the new rule and devtools did not, and nothing failed, because a missing key is
    # indistinguishable from an unset one. Two engines reading one config file must
    # not disagree about what is in it, so the keys are discovered rather than listed.
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    for match in re.finditer(r"^([A-Za-z_][A-Za-z0-9_]*):\s*\n((?:\s*-\s*.+\n?)+)", text, re.M):
        key, body = match.group(1), match.group(2)
        items = re.findall(r"-\s*(.+)", body)
        rules[key] = [i.split("#", 1)[0].strip() for i in items if i.strip()]

    return rules
