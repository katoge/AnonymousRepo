This README including the helper scripts to simplify life for our reviewers was created with ChatGPT.

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


## Table 4

To reproduce Table 4, go to `Table4/` and run:

```bash
python3 Statistics2.py > output.txt
```
Statistics2.py traverses all decompiler/repository subdirectories, reads each local function_logs.jsonl, and reports the number of tests, number of compilations, number of passes, compile ratio, and pass ratio for every case.


## Table 5

To reproduce Table 5, enter each decompiler/optimization directory under `Table5/` and first compute the code-similarity metrics from the local `function_logs.jsonl`, `edit_distances.txt`, and `c_trivial_ngrams.json` files:

```bash
cd Table5/LLM4Decompile/O3
python3 tmp.py
```

This generates function_metrics.txt, which contains per-function values and a final AVERAGE line. Then run:
```
python3 Statistics.py > output.txt
```
Use the similarity metrics from function_metrics.txt and the summary statistics from output.txt to fill Table 5. Repeat this for both decompilers (ANGR, LLM4Decompile) across all optimization levels (O0–O3).


`tmp.py` is configured to read `function_logs.jsonl`, `edit_distances.txt`, and `c_trivial_ngrams.json`, then write the computed metrics to `function_metrics.txt`.
`Statistics.py` reads the local `edit_distances.txt` and prints aggregate statistics including similarity, CodeBERTScore, CodeBLEU, CrystalBLEU, and CorpusBLEU.
`function_metrics.txt` contains the metric rows plus a final `AVERAGE` line used as the aggregate output for each directory.


## Table 6

To reproduce Table 6, run the bug-classification pipeline twice in `Table6/`.

In the first pass, `decompiler_bug_finder.py` discovers and stores the category set in `categories.json`. In the second pass, rerun the script with this fixed category set to obtain stable classifications and final summary statistics.

Example:
```bash
python3 decompiler_bug_finder.py
python3 decompiler_bug_finder.py
```

The final category assignments are written to output.jsonl, and the category percentages reported in Table 6 are written to statistics.txt.
