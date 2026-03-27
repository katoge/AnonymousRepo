#!/usr/bin/env python3
"""
repo_metrics.py

Traverse C repositories under ./REPOSITORIES and report:
- Avg SLOC (per file)           via lizard
- Avg cyclomatic complexity     via lizard
- Avg call-graph depth          via Tree-sitter + NetworkX (direct calls only)
- Max call-graph depth          (on SCC-condensed DAG)
- Avg Fan-In / Fan-Out          per function
- Median Fan-In / Fan-Out
- Max Fan-In / Max Fan-Out
- (NEW) Cross-repo averages and medians
- (NEW) Radar plot: one semi-transparent polygon per repo (random color),
  a bold black polygon for the cross-repo average, and bold random-colored
  polygons for user-specified reference repos.

Repo discovery:
- Only immediate subdirectories of ./REPOSITORIES that look like C repos.
- "Looks like a C repo" = has at least one .c file (recursively).
- The container directory REPOSITORIES itself is NOT included.

Optional restriction:
- If --logs function_logs.jsonl is provided, only repos whose names appear in that file
  (as the path segment after "C_COMPILE/") will be analyzed.

Dependencies:
  pip install -U lizard networkx tree-sitter tree-sitter-c matplotlib
"""

import argparse
import json
import os
import sys
import math
import random
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple, Optional
from statistics import median

# ----------------------------- Config -----------------------------------------
C_EXTS_ALL = {".c", ".h"}   # analyze these
C_ONLY_EXTS = {".c"}        # repo must have at least one .c
VENDOR_DIR_NAMES = {"vendor", "third_party", "third-party", "3rdparty", "external", "deps", "build", "out"}
ALWAYS_SKIP_DIRS = {".git", ".hg", ".svn", ".idea", ".vscode", "__pycache__", ".tox", "node_modules"}
REPOS_ROOT = Path("REPOSITORIES")
C_COMPILE_ANCHOR = "C_COMPILE/"

# ---- SLOC/Complexity (lizard) ------------------------------------------------
try:
    import lizard
except ImportError:
    print("[error] Missing dependency: lizard. Run: pip install lizard", file=sys.stderr)
    sys.exit(1)

# ---- Call graph (Tree-sitter + NetworkX) -------------------------------------
try:
    from tree_sitter import Language, Parser
    from tree_sitter_c import language as c_language
except Exception:
    print("[error] tree-sitter not available. Run: pip install tree-sitter tree-sitter-c", file=sys.stderr)
    sys.exit(1)

try:
    import networkx as nx
except ImportError:
    print("[error] Missing dependency: networkx. Run: pip install networkx", file=sys.stderr)
    sys.exit(1)


# ----------------------------- Helpers ----------------------------------------
def is_hidden_dir(p: Path) -> bool:
    name = p.name
    return name.startswith(".") and name not in {".", "..", ".git"}

def should_skip_dir(p: Path, include_vendor: bool) -> bool:
    name = p.name
    if name in ALWAYS_SKIP_DIRS:
        return True
    if not include_vendor and name in VENDOR_DIR_NAMES:
        return True
    return False

def iter_files_by_ext(root: Path, include_vendor: bool, exts: Set[str]) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        pruned = []
        for d in list(dirnames):
            dp = Path(dirpath) / d
            if should_skip_dir(dp, include_vendor) or is_hidden_dir(dp):
                continue
            pruned.append(d)
        dirnames[:] = pruned

        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in exts:
                yield p

def iter_c_files_for_analysis(root: Path, include_vendor: bool) -> Iterable[Path]:
    return iter_files_by_ext(root, include_vendor, C_EXTS_ALL)

def repo_has_c_files(root: Path, include_vendor: bool) -> bool:
    for _ in iter_files_by_ext(root, include_vendor, C_ONLY_EXTS):
        return True
    return False

def discover_repos(base: Path, include_vendor: bool, allowed_names: Optional[Set[str]] = None) -> List[Path]:
    """
    Immediate subdirectories of `base` that have at least one .c file.
    If allowed_names is provided, only include folders whose name is in that set.
    """
    repos: List[Path] = []
    if base.is_dir():
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            if allowed_names is not None and child.name not in allowed_names:
                continue
            if repo_has_c_files(child, include_vendor):
                repos.append(child.resolve())
    return repos

def parse_repo_names_from_logs(log_path: Path) -> Set[str]:
    """
    Reads a JSONL file and extracts repository names from 'source_file' fields.
    Expected format includes 'C_COMPILE/<repo_name>/'.
    """
    allowed: Set[str] = set()
    if not log_path.exists():
        print(f"[warn] --logs file not found: {log_path}", file=sys.stderr)
        return allowed

    with log_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            src = obj.get("source_file")
            if not src:
                continue
            src_norm = src.replace("\\", "/")
            idx = src_norm.find(C_COMPILE_ANCHOR)
            if idx < 0:
                continue
            rest = src_norm[idx + len(C_COMPILE_ANCHOR):]
            repo_name = rest.split("/", 1)[0].strip()
            if repo_name:
                allowed.add(repo_name)
    return allowed


# --------------------------- Metrics with Lizard -------------------------------
def analyze_with_lizard(files: List[Path]):
    file_count = 0
    total_sloc = 0
    total_functions = 0
    function_ccs: List[int] = []

    for f in files:
        try:
            analysis = lizard.analyze_file(str(f))
        except Exception:
            continue
        file_count += 1
        total_sloc += getattr(analysis, "nloc", 0)
        for fn in getattr(analysis, "function_list", []):
            total_functions += 1
            function_ccs.append(int(getattr(fn, "cyclomatic_complexity", 0)))

    return file_count, total_sloc, total_functions, function_ccs


# ------------------------- Call Graph via Tree-sitter --------------------------
def _load_c_language() -> Language:
    cap_or_lang = c_language()
    try:
        return Language(cap_or_lang)
    except TypeError:
        return cap_or_lang

class TSCallGraphBuilder:
    """
    Build a function-level call graph for C using Tree-sitter (packaged grammar).
    Only links between functions that are defined in the repo are recorded.
    """

    def __init__(self, lang: Language):
        try:
            self.parser = Parser(lang)  # ≥0.22
        except TypeError:
            self.parser = Parser()      # ≤0.21
            try:
                self.parser.set_language(lang)
            except AttributeError:
                self.parser.language = lang

    @staticmethod
    def _node_text(source: bytes, node) -> str:
        return source[node.start_byte:node.end_byte].decode(errors="ignore")

    def _walk(self, node):
        """Iterative DFS to avoid recursion limits."""
        stack = [node]
        while stack:
            n = stack.pop()
            yield n
            if getattr(n, "children", None):
                stack.extend(reversed(n.children))

    def _collect_function_defs(self, source: bytes, root) -> Dict[Tuple[int, int], str]:
        def get_func_name_from_def(def_node) -> Optional[str]:
            decl = def_node.child_by_field_name("declarator")
            if decl is None:
                return None
            while decl is not None and decl.type in (
                "function_declarator",
                "pointer_declarator",
                "parenthesized_declarator",
                "array_declarator",
            ):
                decl = decl.child_by_field_name("declarator")
            if decl is not None and decl.type == "identifier":
                return self._node_text(source, decl)
            return None

        defs: Dict[Tuple[int, int], str] = {}
        for n in self._walk(root):
            if n.type == "function_definition":
                name = get_func_name_from_def(n)
                if name:
                    defs[(n.start_byte, n.end_byte)] = name
        return defs

    def _collect_calls_in_function(self, source: bytes, func_node) -> Set[str]:
        callees: Set[str] = set()
        for n in self._walk(func_node):
            if n.type == "call_expression":
                target = n.child_by_field_name("function")
                if target is not None and target.type == "identifier":
                    name = self._node_text(source, target)
                    if name:
                        callees.add(name)
        return callees

    def build_graph(self, files: List[Path]) -> "nx.DiGraph":
        G = nx.DiGraph()
        defined_names: Set[str] = set()
        file_trees = []

        # First pass: parse and collect function definitions
        for f in files:
            try:
                source = f.read_bytes()
            except Exception:
                continue
            try:
                tree = self.parser.parse(source)
            except Exception:
                continue
            root = tree.root_node
            func_defs = self._collect_function_defs(source, root)
            file_trees.append((source, root, func_defs))
            defined_names.update(func_defs.values())

        for name in defined_names:
            G.add_node(name)

        # Second pass: add edges ONLY if callee is a defined function
        for source, root, func_defs in file_trees:
            func_nodes = {
                (n.start_byte, n.end_byte): n
                for n in (node for node in self._walk(root) if node.type == "function_definition")
                if (n.start_byte, n.end_byte) in func_defs
            }

            for span, fname in func_defs.items():
                fn_node = func_nodes.get(span)
                if fn_node is None:
                    continue
                for callee in self._collect_calls_in_function(source, fn_node):
                    if callee in defined_names:
                        G.add_edge(fname, callee)

        return G


# ---------------------- Depth & FanIn/FanOut Utilities ------------------------
def _condense_to_dag(G: "nx.DiGraph") -> Tuple["nx.DiGraph", Dict[str, int]]:
    if G.number_of_nodes() == 0:
        return nx.DiGraph(), {}
    sccs = list(nx.strongly_connected_components(G))
    comp_index: Dict[str, int] = {}
    for idx, comp in enumerate(sccs):
        for n in comp:
            comp_index[n] = idx

    DAG = nx.DiGraph()
    for i in range(len(sccs)):
        DAG.add_node(i)
    for u, v in G.edges():
        cu, cv = comp_index[u], comp_index[v]
        if cu != cv:
            DAG.add_edge(cu, cv)
    return DAG, comp_index


def average_callgraph_depth(G: "nx.DiGraph") -> Optional[float]:
    DAG, _ = _condense_to_dag(G)
    if DAG.number_of_nodes() == 0:
        return None
    topo = list(nx.topological_sort(DAG))
    paths = {n: 0 for n in topo}
    sums  = {n: 0 for n in topo}

    for n in reversed(topo):
        succs = list(DAG.successors(n))
        if not succs:
            paths[n] = 1
            sums[n] = 0
        else:
            p = 0
            s = 0
            for w in succs:
                p += paths[w]
                s += sums[w] + paths[w]
            paths[n] = p
            sums[n] = s

    roots = [n for n in topo if DAG.in_degree(n) == 0]
    total_paths = sum(paths[r] for r in roots)
    if total_paths == 0:
        return None
    total_len = sum(sums[r] for r in roots)
    return total_len / total_paths


def max_callgraph_depth(G: "nx.DiGraph") -> Optional[int]:
    DAG, _ = _condense_to_dag(G)
    if DAG.number_of_nodes() == 0:
        return None
    topo = list(nx.topological_sort(DAG))
    dist = {n: 0 for n in topo}
    for n in topo:
        for w in DAG.successors(n):
            if dist[w] < dist[n] + 1:
                dist[w] = dist[n] + 1
    return max(dist.values()) if dist else None


def average_fanin_fanout(G: "nx.DiGraph") -> Tuple[Optional[float], Optional[float]]:
    n = G.number_of_nodes()
    if n == 0:
        return None, None
    fanins = [G.in_degree(v) for v in G.nodes()]
    fanouts = [G.out_degree(v) for v in G.nodes()]
    return (sum(fanins) / n, sum(fanouts) / n)

def median_fanin_fanout(G: "nx.DiGraph") -> Tuple[Optional[float], Optional[float]]:
    n = G.number_of_nodes()
    if n == 0:
        return None, None
    fanins = [G.in_degree(v) for v in G.nodes()]
    fanouts = [G.out_degree(v) for v in G.nodes()]
    return (median(fanins), median(fanouts))

def max_fanin_fanout(G: "nx.DiGraph") -> Tuple[Optional[int], Optional[int]]:
    n = G.number_of_nodes()
    if n == 0:
        return None, None
    fanins = [G.in_degree(v) for v in G.nodes()]
    fanouts = [G.out_degree(v) for v in G.nodes()]
    return (max(fanins), max(fanouts))


# ----------------------------- Repo Analyzer ----------------------------------
def analyze_repo(root: Path, include_vendor: bool, ts_lang: Language) -> Dict:
    files = list(iter_c_files_for_analysis(root, include_vendor))
    source_files_c = sum(1 for f in files if f.suffix.lower() == ".c")
    source_files_h = sum(1 for f in files if f.suffix.lower() == ".h")
    fcount, total_sloc, total_funcs, function_ccs = analyze_with_lizard(files)

    if fcount == 0:
        return {"repo": str(root), "skipped": True, "reason": "no analyzable files"}

    avg_sloc_per_file = (total_sloc / fcount) if fcount else 0.0
    avg_cc_per_function = (sum(function_ccs) / len(function_ccs)) if function_ccs else None

    ts_builder = TSCallGraphBuilder(ts_lang)
    G = ts_builder.build_graph(files)
    avg_depth = average_callgraph_depth(G)     # None if empty
    max_depth = max_callgraph_depth(G)         # None if empty
    avg_fanin, avg_fanout = average_fanin_fanout(G)
    med_fanin, med_fanout = median_fanin_fanout(G)
    max_fanin, max_fanout = max_fanin_fanout(G)

    nodes = G.number_of_nodes()
    edges = G.number_of_edges()

    return {
        "repo": str(root),
        "name": root.name,
        "skipped": False,
        "files_analyzed": fcount,
        "total_sloc": total_sloc,
        "avg_sloc_per_file": avg_sloc_per_file,
        "functions": total_funcs,
        "avg_cyclomatic_complexity": avg_cc_per_function,  # None if no functions
        "callgraph_nodes": nodes,
        "callgraph_edges": edges,
        "avg_callgraph_depth": avg_depth,                  # None if graph empty
        "max_callgraph_depth": max_depth,                  # None if graph empty
        "avg_fan_in": avg_fanin,                           # None if graph empty
        "avg_fan_out": avg_fanout,                         # None if graph empty
        "median_fan_in": med_fanin,
        "median_fan_out": med_fanout,
        "max_fan_in": max_fanin,
        "max_fan_out": max_fanout,
        "source_files_c": source_files_c,
        "source_files_h": source_files_h,
    }


# ---------------------------------- CLI ---------------------------------------
def fmt_num(x, nd=2, na="n/a"):
    if x is None:
        return na
    if isinstance(x, int):
        return str(x)
    try:
        return f"{x:.{nd}f}"
    except Exception:
        return str(x)

def _avg_or_na(vals: List[Optional[float]]) -> Optional[float]:
    nums = [v for v in vals if isinstance(v, (int, float))]
    return (sum(nums) / len(nums)) if nums else None

def _median_or_na(vals: List[Optional[float]]) -> Optional[float]:
    nums = [v for v in vals if isinstance(v, (int, float))]
    return median(nums) if nums else None

def _parse_ref_repos(arg: Optional[str]) -> Set[str]:
    """
    Accepts a comma-separated list OR a path to a text file (one name per line).
    """
    if not arg:
        return set()
    p = Path(arg)
    if p.exists() and p.is_file():
        names = set()
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            name = line.strip()
            if name:
                names.add(name)
        return names
    # comma-separated list
    return {s.strip() for s in arg.split(",") if s.strip()}

def _build_radar(results: List[Dict], avg_totals: Dict[str, Optional[float]], ref_names: Set[str], out_path: Path):
    """
    Build a spider/radar chart with one semi-transparent line per repo (random color),
    a bold black line for the averages, and bold random-colored lines for the
    specified reference repos (by folder name). No fill.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless/backends for CLI environments
        import matplotlib.pyplot as plt
    except Exception:
        print("[error] Missing dependency: matplotlib. Run: pip install matplotlib", file=sys.stderr)
        sys.exit(1)

    # Axes / metrics shown on the radar
    axes = [
        ("Avg SLOC/file",           "avg_sloc_per_file"),
        ("Avg CC",                  "avg_cyclomatic_complexity"),
        ("Avg depth",               "avg_callgraph_depth"),
        ("Max depth",               "max_callgraph_depth"),
        ("Avg Fan-In",              "avg_fan_in"),
        ("Avg Fan-Out",             "avg_fan_out"),
        ("Median Fan-In",           "median_fan_in"),
        ("Median Fan-Out",          "median_fan_out"),
        ("Max Fan-In",              "max_fan_in"),
        ("Max Fan-Out",             "max_fan_out"),
    ]

    def vec_from(d: Dict) -> List[float]:
        vals = []
        for _, key in axes:
            v = d.get(key)
            vals.append(float(v) if isinstance(v, (int, float)) else 0.0)
        return vals

    repo_vectors = [(r["name"], vec_from(r)) for r in results]
    avg_vector = [float(avg_totals.get(k, 0.0) or 0.0) for _, k in axes]

    num_axes = len(axes)
    max_per_axis = [0.0] * num_axes
    for _, v in repo_vectors:
        for i in range(num_axes):
            max_per_axis[i] = max(max_per_axis[i], v[i])
    for i in range(num_axes):
        max_per_axis[i] = max(max_per_axis[i], avg_vector[i], 1.0)

    def normalize(vec: List[float]) -> List[float]:
        return [vec[i] / max_per_axis[i] for i in range(num_axes)]

    repo_vectors_norm = [(name, normalize(v)) for name, v in repo_vectors]
    avg_vector_norm = normalize(avg_vector)

    angles = [n / float(num_axes) * 2.0 * math.pi for n in range(num_axes)]
    angles += angles[:1]

    fig = plt.figure(figsize=(8, 8))
    ax = plt.subplot(111, polar=True)
    ax.set_theta_offset(math.pi / 2)
    ax.set_theta_direction(-1)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([label for label, _ in axes])
    ax.set_rlabel_position(0)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.5", "0.75", "1.0"])

    # One semi-transparent line per repo
    for name, vec in repo_vectors_norm:
        values = vec + vec[:1]
        color = (random.random(), random.random(), random.random())
        lw = 1.0
        alpha = 0.7
        ax.plot(angles, values, linewidth=lw, alpha=alpha, color=color)

    # Reference repos (bold random color)
    for name, vec in repo_vectors_norm:
        if name in ref_names:
            values = vec + vec[:1]
            color = (random.random(), random.random(), random.random())
            ax.plot(angles, values, linewidth=2.5, alpha=1, color=color, label=f"REF: {name}")

    # Average (solid black)
    avg_vals = avg_vector_norm + avg_vector_norm[:1]
    ax.plot(angles, avg_vals, linewidth=3.0, color="black", label="Average")

    if ref_names:
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))

    fig.tight_layout()
    try:
        fig.savefig(out_path, dpi=200)
        print(f"[info] Saved radar plot (lines only) to: {out_path}", file=sys.stderr)
    except Exception as e:
        print(f"[warn] Could not save radar plot: {e}", file=sys.stderr)
    finally:
        plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Analyze C repos under ./REPOSITORIES")
    ap.add_argument("--json", action="store_true", help="Also print JSON summary")
    ap.add_argument("--include-vendor", action="store_true", help="Include vendor/third_party/build dirs in scans")
    ap.add_argument("--skip-bad-callgraph", action="store_true",
                    help="Skip repos where Lizard found functions but Tree-sitter found 0 call-graph nodes (likely K&R/implicit-int).")
    ap.add_argument("--min-functions", type=int, default=0,
                    help="Skip repos with fewer than this many functions (by Lizard). Default 0.")
    ap.add_argument("--logs", type=str, default=None,
                    help="Path to function_logs.jsonl; restrict analysis to repos mentioned after 'C_COMPILE/' in 'source_file'.")
    ap.add_argument("--radar-out", type=str, default="repo_metrics_radar.png",
                    help="Path to save the radar (spider) plot PNG.")
    ap.add_argument("--ref-repos", type=str, default=None,
                    help="Comma-separated repo folder names, or a path to a text file with one name per line, to highlight as references.")
    ap.add_argument("--repo", type=str, default="C_COMPILE",
                    help="Root directory containing repositories to analyze. Default: C_COMPILE.")

    args = ap.parse_args()

    repos_root = Path(args.repo).resolve()
    if not repos_root.exists():
        print(f"[error] {repos_root} not found. Create it and put repos inside.", file=sys.stderr)
        sys.exit(1)

    allowed_names: Optional[Set[str]] = None
    if args.logs:
        log_path = Path(args.logs).resolve()
        allowed_names = parse_repo_names_from_logs(log_path)
        if allowed_names:
            print(f"[info] Restricting to {len(allowed_names)} repo name(s) from logs.", file=sys.stderr)
        else:
            print(f"[warn] No repo names parsed from --logs; no repos will match this filter.", file=sys.stderr)

    # Load packaged C grammar
    try:
        c_lang = _load_c_language()
    except Exception as e:
        print(f"[error] Could not load tree-sitter-c language: {e}", file=sys.stderr)
        sys.exit(1)

    repos = discover_repos(repos_root, include_vendor=args.include_vendor, allowed_names=allowed_names)
    if not repos:
        if args.logs:
            print(f"No matching repositories (with at least one .c file) found under {repos_root} after applying --logs filter.", file=sys.stderr)
        else:
            print(f"No C repositories (with at least one .c file) found under {repos_root}", file=sys.stderr)
        sys.exit(1)

    results = []
    for repo in repos:
        res = analyze_repo(repo, include_vendor=args.include_vendor, ts_lang=c_lang)

        if res.get("skipped"):
            print(f"Skipping: {repo}  ({res.get('reason','no reason')})", file=sys.stderr)
            continue

        if args.min_functions and res["functions"] < args.min_functions:
            print(f"Skipping: {repo}  (functions {res['functions']} < --min-functions {args.min_functions})", file=sys.stderr)
            continue

        if args.skip_bad_callgraph and res["functions"] > 0 and res["callgraph_nodes"] == 0:
            print(f"Skipping: {repo}  (--skip-bad-callgraph: functions present but call graph empty)", file=sys.stderr)
            continue

        print(f"Analyzing: {repo}", file=sys.stderr)
        results.append(res)

    if not results:
        print("No usable repositories after filtering.", file=sys.stderr)
        sys.exit(1)

    print("\n=== Summary ===")
    for r in results:
        print(f"\nRepo: {r['repo']}")
        print(f"  Files analyzed:            {r['files_analyzed']}")
        print(f"  Total SLOC:                {r['total_sloc']}")
        print(f"  Avg SLOC per file:         {fmt_num(r['avg_sloc_per_file'])}")
        print(f"  Functions:                 {r['functions']}")
        print(f"  Avg cyclomatic complexity: {fmt_num(r['avg_cyclomatic_complexity'])}")
        print(f"  Call graph nodes/edges:    {r['callgraph_nodes']}/{r['callgraph_edges']}")
        print(f"  Avg call-graph depth:      {fmt_num(r['avg_callgraph_depth'])}")
        print(f"  Max call-graph depth:      {fmt_num(r['max_callgraph_depth'], nd=0)}")
        print(f"  Avg Fan-In / Fan-Out:      {fmt_num(r['avg_fan_in'])} / {fmt_num(r['avg_fan_out'])}")
        print(f"  Median Fan-In / Fan-Out:   {fmt_num(r['median_fan_in'])} / {fmt_num(r['median_fan_out'])}")
        print(f"  Max Fan-In / Fan-Out:      {fmt_num(r['max_fan_in'], nd=0)} / {fmt_num(r['max_fan_out'], nd=0)}")
        print(f"  Source files (.c / .h):    {r['source_files_c']} / {r['source_files_h']}")

    # --- Cross-repo averages ---
    avg_totals = {
        "avg_sloc_per_file":           _avg_or_na([r["avg_sloc_per_file"] for r in results]),
        "avg_cyclomatic_complexity":   _avg_or_na([r["avg_cyclomatic_complexity"] for r in results]),
        "avg_callgraph_depth":         _avg_or_na([r["avg_callgraph_depth"] for r in results]),
        "max_callgraph_depth":         _avg_or_na([r["max_callgraph_depth"] for r in results]),
        "avg_fan_in":                  _avg_or_na([r["avg_fan_in"] for r in results]),
        "avg_fan_out":                 _avg_or_na([r["avg_fan_out"] for r in results]),
        "median_fan_in":               _avg_or_na([r["median_fan_in"] for r in results]),
        "median_fan_out":              _avg_or_na([r["median_fan_out"] for r in results]),
        "max_fan_in":                  _avg_or_na([r["max_fan_in"] for r in results]),
        "max_fan_out":                 _avg_or_na([r["max_fan_out"] for r in results]),
        "source_files_c":              _avg_or_na([r["source_files_c"] for r in results]),
        "source_files_h":              _avg_or_na([r["source_files_h"] for r in results]),
    }

    print("\n=== Averages over usable repos ===")
    print(f"  Avg SLOC per file:         {fmt_num(avg_totals['avg_sloc_per_file'])}")
    print(f"  Avg cyclomatic complexity: {fmt_num(avg_totals['avg_cyclomatic_complexity'])}")
    print(f"  Avg call-graph depth:      {fmt_num(avg_totals['avg_callgraph_depth'])}")
    print(f"  Max call-graph depth:      {fmt_num(avg_totals['max_callgraph_depth'], nd=0)}")
    print(f"  Avg Fan-In / Fan-Out:      {fmt_num(avg_totals['avg_fan_in'])} / {fmt_num(avg_totals['avg_fan_out'])}")
    print(f"  Median Fan-In / Fan-Out:   {fmt_num(avg_totals['median_fan_in'])} / {fmt_num(avg_totals['median_fan_out'])}")
    print(f"  Max Fan-In / Fan-Out:      {fmt_num(avg_totals['max_fan_in'], nd=0)} / {fmt_num(avg_totals['max_fan_out'], nd=0)}")
    print(f"  Source files (.c / .h):    {fmt_num(avg_totals['source_files_c'])} / {fmt_num(avg_totals['source_files_h'])}")

    # --- Cross-repo medians ---
    median_totals = {
        "avg_sloc_per_file":           _median_or_na([r["avg_sloc_per_file"] for r in results]),
        "avg_cyclomatic_complexity":   _median_or_na([r["avg_cyclomatic_complexity"] for r in results]),
        "avg_callgraph_depth":         _median_or_na([r["avg_callgraph_depth"] for r in results]),
        "max_callgraph_depth":         _median_or_na([r["max_callgraph_depth"] for r in results]),
        "avg_fan_in":                  _median_or_na([r["avg_fan_in"] for r in results]),
        "avg_fan_out":                 _median_or_na([r["avg_fan_out"] for r in results]),
        "median_fan_in":               _median_or_na([r["median_fan_in"] for r in results]),
        "median_fan_out":              _median_or_na([r["median_fan_out"] for r in results]),
        "max_fan_in":                  _median_or_na([r["max_fan_in"] for r in results]),
        "max_fan_out":                 _median_or_na([r["max_fan_out"] for r in results]),
        "source_files_c":              _median_or_na([r["source_files_c"] for r in results]),
        "source_files_h":              _median_or_na([r["source_files_h"] for r in results]),
    }

    print("\n=== Medians over usable repos ===")
    print(f"  Avg SLOC per file:         {fmt_num(median_totals['avg_sloc_per_file'])}")
    print(f"  Avg cyclomatic complexity: {fmt_num(median_totals['avg_cyclomatic_complexity'])}")
    print(f"  Avg call-graph depth:      {fmt_num(median_totals['avg_callgraph_depth'])}")
    print(f"  Max call-graph depth:      {fmt_num(median_totals['max_callgraph_depth'], nd=0)}")
    print(f"  Avg Fan-In / Fan-Out:      {fmt_num(median_totals['avg_fan_in'])} / {fmt_num(median_totals['avg_fan_out'])}")
    print(f"  Median Fan-In / Fan-Out:   {fmt_num(median_totals['median_fan_in'])} / {fmt_num(median_totals['median_fan_out'])}")
    print(f"  Max Fan-In / Fan-Out:      {fmt_num(median_totals['max_fan_in'], nd=0)} / {fmt_num(median_totals['max_fan_out'], nd=0)}")
    print(f"  Source files (.c / .h):    {fmt_num(median_totals['source_files_c'])} / {fmt_num(median_totals['source_files_h'])}")

    # --- Radar plot ---
    ref_names = _parse_ref_repos(args.ref_repos)
    _build_radar(results, avg_totals, ref_names, Path(args.radar_out))

    if args.json:
        print("\n=== JSON ===")
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()