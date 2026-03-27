#!/usr/bin/env python3
"""
clean_logs_all8.py  –  keep only the functions common to *all eight* files

Creates
    function_logs_<flavour>_<level>.jsonl.cleaned
    edit_distances_<flavour>_<level>.txt.cleaned
for   flavour ∈ {a, l}  and  level ∈ {O0, O1, O2, O3}

The originals are left untouched so you can verify the result first.
"""

import json
import itertools
from collections import Counter
from pathlib import Path

FLAVOURS = ["a", "l"]
LEVELS   = ["O0", "O1", "O2", "O3"]

# ---------------------------------------------------------------------------

def load_funcs(path: Path):
    """Return list[(raw_json_line, function_string | None)]."""
    items = []
    with path.open() as fh:
        for line in fh:
            try:
                func = json.loads(line)["function"]
            except Exception:
                func = None          # malformed JSON → drop later everywhere
            items.append((line, func))
    return items

def multiset_intersection(counters):
    """
    Given list[Counter], return dict func→min(count) (multiset intersection).
    Only functions present in *every* counter are retained.
    """
    all_funcs = set(itertools.chain.from_iterable(counters))
    return {
        f: min(c[f] for c in counters)
        for f in all_funcs
        if all(c[f] for c in counters)
    }

def choose_indices(pairs, quota):
    """
    Decide which line indices to keep so that each function appears exactly
    quota[func] times in the list.  Lines whose function is missing in quota
    (i.e. not part of the intersection) are always discarded.
    """
    kept  = Counter()
    idxs  = set()

    for i, (_, func) in enumerate(pairs):
        # DISCARD malformed lines or functions not in the intersection
        if func is None or func not in quota:
            continue
        if kept[func] < quota[func]:
            kept[func] += 1
            idxs.add(i)

    return idxs

# ---------------------------------------------------------------------------

def main():
    # 1) read all eight files
    func_pairs    = {}   # (flav,lvl) → list[(json_line, func)]
    dist_lines    = {}   # (flav,lvl) → list[str]
    counters      = []   # list of Counter

    for flav in FLAVOURS:
        for lvl in LEVELS:
            tag   = (flav, lvl)
            fpath = Path(f"function_logs_{flav}_{lvl}.jsonl")
            dpath = Path(f"edit_distances_{flav}_{lvl}.txt")

            func_pairs[tag] = load_funcs(fpath)
            with dpath.open() as fh:
                dist_lines[tag] = fh.readlines()

            if len(func_pairs[tag]) != len(dist_lines[tag]):
                raise ValueError(f"{fpath} and {dpath} differ in length")

            counters.append(
                Counter(f for _, f in func_pairs[tag] if f is not None)
            )

    # 2) global multiset intersection across all eight files
    quota = multiset_intersection(counters)
    if not quota:
        raise RuntimeError("No common functions across all files!")

    # 3) figure out which rows to keep in every file
    keep_idxs = {tag: choose_indices(func_pairs[tag], quota)
                 for tag in func_pairs}

    # 4) write cleaned outputs
    for (flav, lvl), idxs in keep_idxs.items():
        f_in  = Path(f"function_logs_{flav}_{lvl}.jsonl")
        f_out = f_in.with_suffix(".jsonl.cleaned")
        d_in  = Path(f"edit_distances_{flav}_{lvl}.txt")
        d_out = d_in.with_suffix(".txt.cleaned")

        with f_out.open("w") as fout, d_out.open("w") as dout:
            for i, ((raw_json, _), dist) in enumerate(
                    zip(func_pairs[(flav, lvl)], dist_lines[(flav, lvl)])):
                if i in idxs:
                    fout.write(raw_json)
                    dout.write(dist)

        print(f"[{flav} {lvl}] kept {len(idxs)} lines  →  {f_out.name}")

    print("\nDone. All eight *.cleaned files now have identical line counts.")

# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
