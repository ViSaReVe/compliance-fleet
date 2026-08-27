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

    # Recover the two YAML lists (allowed_categories, disallowed_categories) written
    # as "key:\n  - item" block style, which the flat parser above skips.
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    for list_key in ("allowed_categories", "disallowed_categories"):
        match = re.search(rf"{list_key}:\s*\n((?:\s*-\s*.+\n?)*)", text)
        if match and match.group(1).strip():
            items = re.findall(r"-\s*(.+)", match.group(1))
            rules[list_key] = [i.strip() for i in items]

    return rules
