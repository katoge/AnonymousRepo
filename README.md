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
``
