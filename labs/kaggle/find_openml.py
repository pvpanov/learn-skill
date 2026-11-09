"""List OpenML datasets by structure. Read-only: queries metadata, downloads no data.

    python find_openml.py --rows 1000..10000 --features ..100 --classes 2 --missing 0
    python find_openml.py --suite 99 --rows ..10000          # only datasets in a suite; shows task ids
    python find_openml.py --name credit

Ranges are lo..hi, ..hi, lo.. or one number. "features" counts the target column; "classes" is 0 for
regression targets. "cat" is the number of nominal columns (target included when it is nominal) and
"maxcard" the largest number of levels in any of them; -1 means OpenML has not computed it.
Spec keys: see bench.py.
"""
import argparse, os, sys, time
from pathlib import Path
os.environ.setdefault("OPENML_CACHE_DIR", str(Path(__file__).resolve().parent / "data" / "openml"))
import openml, pandas as pd

def call(f, *a, **kw):
    """The OpenML server is flaky: retry with backoff 2, 4, 8, 16 s."""
    for i in range(5):
        try:
            return f(*a, **kw)
        except Exception as e:
            if i == 4:
                raise
            print(f"openml  {type(e).__name__}: {str(e)[:150]} (retry in {2 ** (i + 1)} s)", file=sys.stderr)
            time.sleep(2 ** (i + 1))

def rng(s):
    lo, sep, hi = s.partition("..")
    return f"{int(lo or 0)}..{int(hi or 10**9)}" if sep else str(int(lo))

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("--rows", type=rng)
ap.add_argument("--features", type=rng)
ap.add_argument("--classes", type=rng)
ap.add_argument("--missing", type=rng, help="number of missing values, e.g. 0 or 1..")
ap.add_argument("--name", help="case-insensitive substring of the dataset name")
ap.add_argument("--suite", type=int, help="restrict to a benchmark suite, e.g. 99 (OpenML-CC18)")
ap.add_argument("--limit", type=int, default=50, help="rows to print (default 50)")
a = ap.parse_args()

filters = {k: v for k, v in (("number_instances", a.rows), ("number_features", a.features),
                             ("number_classes", a.classes), ("number_missing_values", a.missing)) if v}
tasks = None
if a.suite:
    suite = call(openml.study.get_suite, a.suite)
    print(f"suite {a.suite}: {suite.name} ({len(suite.data)} datasets)")
    filters["data_id"] = list(suite.data)
    t = call(openml.tasks.list_tasks, task_id=list(suite.tasks), output_format="dataframe")
    tasks = t.set_index("did")["tid"]
try:
    d = call(openml.datasets.list_datasets, output_format="dataframe", **filters)
except openml.exceptions.OpenMLServerNoResult:
    sys.exit("no datasets match")
if a.name:
    d = d[d["name"].str.contains(a.name, case=False, regex=False)]
if d.empty:
    sys.exit("no datasets match")

num = lambda c: pd.to_numeric(d.get(c), errors="coerce").fillna(-1).astype(int)
out = pd.DataFrame({
    "id": d["did"].astype(int), "name": d["name"].str.slice(0, 40), "v": d["version"],
    "rows": num("NumberOfInstances"), "cols": num("NumberOfFeatures"), "cat": num("NumberOfSymbolicFeatures"),
    "maxcard": num("MaxNominalAttDistinctValues"), "classes": num("NumberOfClasses"),
    "missing": num("NumberOfMissingValues"),
}).sort_values(["rows", "id"])
if tasks is not None:
    out.insert(1, "task", out["id"].map(tasks).fillna(-1).astype(int))
out["url"] = "https://www.openml.org/d/" + out["id"].astype(str)
print(f"{len(out)} datasets match" + (f"; showing the first {a.limit} by rows" if len(out) > a.limit else ""))
print(out.head(a.limit).to_string(index=False))
