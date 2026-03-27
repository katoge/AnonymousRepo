import json
from pathlib import Path

"""
Collect Table 4 statistics from all function_logs.jsonl files under Table4/.

Expected layout:
Table4/
├── Statistics2.py
├── DecompilerA/
│   ├── Repo1/function_logs.jsonl
│   └── Repo2/function_logs.jsonl
└── DecompilerB/
    ├── Repo1/function_logs.jsonl
    └── Repo2/function_logs.jsonl
"""

ROOT = Path(__file__).resolve().parent


def collect_statistics(file_path: Path):
    line_count = 0
    total_compileable = 0
    total_passes = 0

    with file_path.open("r", encoding="utf-8", errors="ignore") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                print(f"Skipping malformed JSON line in {file_path}")
                continue

            if "compilable" not in entry or "pass" not in entry:
                print(f"Skipping line with missing keys in {file_path}")
                continue

            line_count += 1
            total_compileable += int(entry["compilable"])
            total_passes += int(entry["pass"])

    if line_count == 0:
        return None

    compile_ratio = total_compileable / line_count
    pass_ratio = total_passes / line_count

    return {
        "tests": line_count,
        "compilations": total_compileable,
        "passes": total_passes,
        "compile_ratio": compile_ratio,
        "pass_ratio": pass_ratio,
    }


def main():
    jsonl_files = sorted(ROOT.glob("*/*/function_logs.jsonl"))

    if not jsonl_files:
        print("No function_logs.jsonl files found.")
        return

    for file_path in jsonl_files:
        decompiler = file_path.parent.parent.name
        repository = file_path.parent.name

        stats = collect_statistics(file_path)
        if stats is None:
            print(f"{decompiler}/{repository}")
            print("No valid entries found.\n")
            continue

        print(f"{decompiler}/{repository}")
        print(f"Number of Tests: {stats['tests']}")
        print(f"Number of Compilations: {stats['compilations']}")
        print(f"Number of Passes: {stats['passes']}")
        print(f"Compile Ratio: {stats['compile_ratio']:.4f}")
        print(f"Pass Ratio: {stats['pass_ratio']:.4f}")
        print()


if __name__ == "__main__":
    main()