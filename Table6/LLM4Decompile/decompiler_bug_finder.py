#!/usr/bin/env python3
"""
classify_decompiler_bugs.py (live stats + Output folder)
──────────────────────────────────────────────────────
Hard‑wired paths:
  • input  →  function_logs.jsonl
  • output →  Output/output.jsonl
  • stats  →  Output/statistics.txt
  • live category store →  Output/categories.json

Requires `openai` 1.14+  (pip install --upgrade openai)
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from typing import Any, Dict, Tuple

from openai import OpenAI

# export OPENAI_API_KEY=sk- ..



BASE_OUTPUT_DIR = "Output"               # all generated files live here
os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)

OPENAI_MODEL = "gpt-4o"                  # or "4o"
RATE_LIMIT_SLEEP = 0.0                   # seconds between API calls (0 = none)

INPUT_FILE   = "function_logs.jsonl"
OUTPUT_FILE  = os.path.join(BASE_OUTPUT_DIR, "output.jsonl")
STATS_FILE   = os.path.join(BASE_OUTPUT_DIR, "statistics.txt")
CATEGORIES_FILE = os.path.join(BASE_OUTPUT_DIR, "categories.json")

# Core categories
'''_CORE_CATEGORIES: Dict[str, str] = {
    "Type Recovery Bugs":
        "Incorrect or imprecise inference of data types.",
    "Variable Recovery Bugs":
        "Failure to correctly recover local/global variables — including name clashes, overlapping stack slots, or missing variables due to memory layout misinterpretation.",
    "Control-Flow Recovery Bugs":
        "Incorrect reconstruction of control structures (branches, loops, fallthroughs), including changes in block ordering or erroneous dead/live code analysis.",
    "Syntax":
        "",
    "Function Prototype Recovery Bugs":
        "Incorrect recovery of function signatures — such as the wrong number of parameters, argument types, or return types — typically due to failed stack analysis or call-site reconstruction.",
}*/'''

_CORE_CATEGORIES = {
    "Type Recovery Bugs":
        # The paper calls this “the lack of fool‑proof type recovery”.
        # Examples include a variable that is “incorrectly annotated” as
        # unsigned so a loop that should execute zero times suddenly runs,
        # or a 32‑bit value truncated to 16 bits, both of which “alter the
        # control‑ or data‑flow semantics” of the program. :contentReference[oaicite:0]{index=0}
        "Bugs where the decompiler’s type‑inference mis‑annotates or truncates "
        "data (e.g., signed→unsigned, 32‑bit→16‑bit), breaking semantics because "
        "the recovered type is wrong.",

    "Variable Recovery Bugs":
        "Missing / phantom variables, Duplicate declarations or uninitialised reads that produce undefined behaviour.",

    "Control-Flow Recovery Bugs":
        "Mis-reconstruction of high‑level control structures-branches become "
        "reachable/unreachable or are reordered—because the recovered CFG is "
        "wrong or later optimisations mis-handle it.",

    "Invalid C Syntax":
        "Invalid C Syntax that will not even compile. Illegal operations like -> dereferencing a non-pointer, not properly enclosed scopes, code abrupty ending, etc.",

    "Function Prototype Recovery Bugs":
        "Errors in reconstructing function signatures—missing or extra "
        "parameters, wrong argument types or return type—that stem from "
        "mis‑analysed stack‑based call sites."
}


# ────────────────────────────────
# Load / persist taxonomy
# ────────────────────────────────

def load_categories() -> Dict[str, str]:
    cats = dict(_CORE_CATEGORIES)
    if os.path.exists(CATEGORIES_FILE):
        try:
            with open(CATEGORIES_FILE, encoding="utf-8") as fh:
                cats.update(json.load(fh))
        except Exception as exc:
            print(f"[WARN] Failed to read {CATEGORIES_FILE}: {exc}", file=sys.stderr)
    return cats


BUG_CATEGORIES: Dict[str, str] = load_categories()
CATEGORY_NAMES = list(BUG_CATEGORIES.keys())

# ────────────────────────────────
# Prompt templates
# ────────────────────────────────
SYSTEM_MSG = (
    "You are a professional reverse‑engineer helping to categorize decompiler errors."
    "Choose only one category from the list that fits the most. "
    "Invent a new granular category if none apply. Be precise of the characteristic and make sure it does not apply to existing ones already."
    "Return strictly one‑line JSON:\n"
    '  {"category": "<name>"}\n'
    '  or, if new,\n'
    '  {"category": "<name>", "description": "<short definition>"}'
)

def make_prompt(entry: Dict[str, Any]) -> str:
    orig = entry["function"].rstrip()
    pred = entry["function_prediction"].rstrip()
    compilable = entry["compilable"]
    category_list = "\n".join(f"- {n}: {BUG_CATEGORIES[n]}" for n in CATEGORY_NAMES)

    return (
        "Below is an original C function followed by the decompiler's prediction.\n\n"
        f"Original Function:\n{orig}\n\n"
        f"Decompiled Function:\n{pred}\n\n"
        f"Ignore function names ending with name conflict.\n"
        f"Decompilation Compilable: {compilable}\n"
        "Existing categories:\n"
        f"{category_list}\n\n"
        "Which ONE category best matches the primary mistake? "
        "If none apply, invent a concise new category with description. "
        "Respond with the required one‑line JSON only."
    )

# ────────────────────────────────
# LLM helper
# ────────────────────────────────

def ask_llm(client: OpenAI, entry: Dict[str, Any]) -> Tuple[str, str | None]:
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.0,
        max_tokens=60,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_MSG},
            {"role": "user",   "content": make_prompt(entry)},
        ],
    )
    raw = resp.choices[0].message.content.strip()
    try:
        data = json.loads(raw)
        return data["category"].strip(), data.get("description")
    except Exception:
        print(f"[WARN] Non‑JSON reply, fallback: {raw}", file=sys.stderr)
        return raw, None

# ────────────────────────────────
# Helper: live statistics output
# ────────────────────────────────

def _print_live_stats(total: int, counts: Counter[str]) -> None:
    """Render a one‑line overview of current category distribution."""
    if not total:
        return
    top = counts.most_common()
    distr = " | ".join(f"{cat}: {num/total:.1%}" for cat, num in top[:6])  # show up to 6 cats
    sys.stdout.write(f"\rProcessed {total} failures – {distr}")
    sys.stdout.flush()

# ────────────────────────────────
# Main processing
# ────────────────────────────────

def main() -> None:
    client = OpenAI()   # uses OPENAI_API_KEY from environment

    counts: Counter[str] = Counter()
    total_fail = 0

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fout, \
         open(INPUT_FILE,  "r", encoding="utf-8") as fin:

        for line in fin:
            if not line.strip():
                continue
            entry = json.loads(line)

            if entry.get("pass", 0) == 0:
                total_fail += 1
                try:
                    category, desc = ask_llm(client, entry)
                except Exception as exc:
                    print(f"[WARN] OpenAI call failed: {exc}", file=sys.stderr)
                    category, desc = "Unclassified (API error)", None

                # Learn new category
                if category not in BUG_CATEGORIES:
                    BUG_CATEGORIES[category] = desc or "Description TBD."
                    CATEGORY_NAMES.append(category)

                entry["category"] = category
                if desc:
                    entry["category_description"] = desc
                counts[category] += 1

                # Live stats update
                _print_live_stats(total_fail, counts)

                if RATE_LIMIT_SLEEP:
                    time.sleep(RATE_LIMIT_SLEEP)
            else:
                entry["category"] = None

            json.dump(entry, fout, ensure_ascii=False)
            fout.write("\n")

    # ensure the final stats line ends properly
    if total_fail:
        sys.stdout.write("\n")
        sys.stdout.flush()

    # Stats file
    if total_fail:
        with open(STATS_FILE, "w", encoding="utf-8") as fs:
            for cat, num in counts.most_common():
                fs.write(f"{cat}: {num / total_fail:.2%}\n")

    # Persist taxonomy
    try:
        with open(CATEGORIES_FILE, "w", encoding="utf-8") as fh:
            json.dump(BUG_CATEGORIES, fh, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"[WARN] Could not write {CATEGORIES_FILE}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
