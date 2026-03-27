## Table 1

To reproduce Table 1, first compute repository-level complexity statistics with `repo_metrics.py` over the target C repositories. The script analyzes `.c` and `.h` files and reports file counts, average SLOC per file, average cyclomatic complexity, average call-graph depth, and average fan-in/fan-out.

Then measure project-wide GCOV line coverage by rebuilding each repository with coverage instrumentation (`gcc`, `-O0 -g --coverage`), running its main test suite, and summarizing results with `gcovr`.

The exact coverage collection commands used for the three repositories in Table 1 are provided in:
- `openssl.txt` for OpenSSL 3.0.15
- `ffmpeg.txt` for FFmpeg 7.1.3
- `coreutils.txt` for Coreutils 9.7

The final Table 1 columns are: repository name, source-file count, average SLOC per file, average cyclomatic complexity, average call-graph depth, average fan-in/fan-out, and GCOV line coverage.


## Table 2

To reproduce Table 2, run `Statistics.py` inside each subdirectory under `Table2/`, where the script and input files are already colocated. Execute this for `Table2/HumanEval/O0`–`O3` and `Table2/ExeBench/O0`–`O3`.

Example:
```bash
cd Table2/HumanEval/O3
python3 Statistics.py > output.txt
```


## Table 3

To reproduce Table 3, enter `Table3/` and first align the ANGR and LLM4Decompile results to the common function set used in the paper:

```bash
cd Table3
python3 match_function_jsonl.py
```

This generates cleaned files with suffix .cleaned.

Then, for each decompiler/optimization pair, copy the corresponding cleaned distance file to edit_distances.txt and run:

```bash
cp edit_distances_a_O0.txt.cleaned edit_distances.txt
python3 Statistics.py > output_a_O0.txt
```

Repeat this for a and l across O0–O3. Use the reported Compile Ratio, Pass Ratio, and Average GCOV Line Coverage values for Table 3.

To compare ANGR and LLM4Decompile directly on compilability/pass mismatches, run:

```bash
python3 hamming_distance.py
```

Then drag and drop the two matching cleaned JSONL files for the same optimization level, e.g. function_logs_a_O0.jsonl.cleaned and function_logs_l_O0.jsonl.cleaned.
