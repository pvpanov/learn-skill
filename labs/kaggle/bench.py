"""Blind baselines from a spec written in advance: XGBoost (defaults) vs TabPFN v2 (defaults).

    python bench.py specs/<name>.json            # fit, predict, print the results table
    python bench.py specs/<name>.json --check    # split and data summary only, no fitting

The spec is a JSON file fixed BEFORE the first run (metric and split decided in advance).
Comments below are explanation only; JSON has none.

    {
      "name": "bank-marketing-time",
      "csv": "../data/bank-marketing/bank-additional-full.csv",  # relative to the spec file, or absolute
      "read_csv": {"sep": ";"},           # optional pandas.read_csv kwargs
      "target": "y",
      "positive": "yes",                  # binary classification only: which label is class 1
      "task": "classification",           # or "regression"
      "split": "time:@row",               # random | time:<col> | time:@row (file order) | group:<col>
      "test_frac": 0.3,
      "metric": "auc",                    # auc | pr_auc | logloss | accuracy | rmse | mae | r2 | rmsle
      "drop": ["duration"],               # columns removed before modelling
      "seed": 0,
      "tabpfn_max_train": 10000,          # optional; lower it to shorten TabPFN runs
      "why": "one or two lines on why this split and metric, written before running"
    }

"Blind" means: no tuning and no feature engineering. Object columns become pandas `category`
(categories from the train part only; unseen levels become missing). Both models get the same
DataFrame. The split column of a time or group split is dropped from the features.
OpenML instead of a CSV: replace "csv" with "source" (data cached under data/openml/):

      "source": {"openml_dataset": 31},   # a dataset id; "target" defaults to its default target
      "source": {"openml_task": 31},      # or a task id: its dataset, target and predefined splits
      "split": "openml",                  # task only: the task's own split, repeat 0 fold 0
                                          # (test_frac is then ignored); random/time/group also work

TabPFN sees at most 10,000 train rows (fixed-seed random subsample); when that happens, an extra row
`xgboost@sub` fits XGBoost on the same subsample so the comparison is not confounded by size.
"""
import argparse, hashlib, json, os, sys, time
sys.stdout.reconfigure(line_buffering=True)
os.environ.setdefault("OMP_NUM_THREADS", "4")
from pathlib import Path
import numpy as np, pandas as pd, torch
torch.set_num_threads(4)
from sklearn import metrics as skm
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from tabpfn import TabPFNClassifier, TabPFNRegressor
from tabpfn.constants import ModelVersion
from xgboost import XGBClassifier, XGBRegressor

TABPFN_MAX_TRAIN = 10_000  # TabPFN v2's pre-training envelope; a spec may lower it (tabpfn_max_train)
TABPFN_MAX_FEATURES = 500
CHUNK = 500  # TabPFN predicts in chunks of test rows: memory grows with test rows x train rows
# Measured 2026-10-31, RTX 5080, 10k train rows x 500 test rows, 23 features: memory_saving_mode='auto'
# peaked at 10.1 GiB; True at 1.9 GiB reserved, same speed (~10 s per chunk). It is an execution
# setting (batches the computation), not a model setting, so the model stays 'defaults'.
HIGHER_BETTER = {"auc": True, "pr_auc": True, "accuracy": True, "r2": True,
                 "logloss": False, "rmse": False, "mae": False, "rmsle": False}
CLS_METRICS = {"auc", "pr_auc", "logloss", "accuracy"}
OPENML_DIR = Path(__file__).resolve().parent / "data" / "openml"
OPENML_MAX_CELLS = 20_000_000  # rows x features; keeps downloads well under 200 MB

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("spec")
ap.add_argument("--check", action="store_true", help="show split and data summary, fit nothing")
ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
ap.add_argument("--chunk", type=int, default=CHUNK, help="TabPFN test rows per predict call")
args = ap.parse_args()

spec_path = Path(args.spec).resolve()
raw = spec_path.read_bytes()
S = json.loads(raw)
for key in ("task", "split", "metric") + (("source",) if "source" in S else ("csv", "target")):
    if key not in S:
        sys.exit(f"spec is missing '{key}'")
task, metric = S["task"], S["metric"]
if task not in ("classification", "regression") or metric not in HIGHER_BETTER:
    sys.exit(f"bad task/metric: {task}/{metric}")
if (metric in CLS_METRICS) != (task == "classification"):
    sys.exit(f"metric {metric} does not fit task {task}")
seed, test_frac = int(S.get("seed", 0)), float(S.get("test_frac", 0.3))

def openml_call(f, *a, **kw):
    """The OpenML server is flaky (spurious 'Database connection error' or 'dataset not found'):
    retry with backoff 2, 4, 8, 16 s before giving up."""
    for i in range(5):
        try:
            return f(*a, **kw)
        except Exception as e:
            if i == 4:
                raise
            print(f"openml  {type(e).__name__}: {str(e)[:150]} (retry in {2 ** (i + 1)} s)", flush=True)
            time.sleep(2 ** (i + 1))

def load_openml(src):
    os.environ.setdefault("OPENML_CACHE_DIR", str(OPENML_DIR))  # read at import; default is ~/.openml on C:
    import openml
    otask = None
    if "openml_task" in src:
        otask = openml_call(openml.tasks.get_task, int(src["openml_task"]), download_splits=True,
                            download_data=False, download_qualities=False)
        did = otask.dataset_id
        kind = {openml.tasks.TaskType.SUPERVISED_CLASSIFICATION: "classification",
                openml.tasks.TaskType.SUPERVISED_REGRESSION: "regression"}.get(otask.task_type_id)
        if kind != task:
            sys.exit(f"openml task {otask.task_id} is {otask.task_type}, spec says {task}")
    else:
        did = int(src["openml_dataset"])
    ds = openml_call(openml.datasets.get_dataset, did, download_data=False, download_qualities=True)
    q = ds.qualities or {}
    cells = q.get("NumberOfInstances", 0) * q.get("NumberOfFeatures", 0)
    if cells > OPENML_MAX_CELLS:
        sys.exit(f"openml d/{did} has {cells:.0f} cells > {OPENML_MAX_CELLS}: too big to download here")
    data, *_ = openml_call(ds.get_data, dataset_format="dataframe")  # row id and ignored columns excluded
    target = S.get("target") or (otask.target_name if otask else ds.default_target_attribute)
    if not target or "," in target:
        sys.exit(f"openml d/{did}: no single default target ({target!r}); set 'target' in the spec")
    label = f"openml d/{did} {ds.name} v{ds.version}" + (f", task {otask.task_id}" if otask else "")
    return data, target, label, otask

# ---- load
otask = None
if "source" in S:
    df, target, data_label, otask = load_openml(S["source"])
else:
    csv = Path(S["csv"]) if Path(S["csv"]).is_absolute() else spec_path.parent / S["csv"]
    df, target, data_label = pd.read_csv(csv, **S.get("read_csv", {})), S["target"], csv.name
n_raw = len(df)
kept = np.flatnonzero(df[target].notna().to_numpy())  # original row positions (OpenML split indices)
df = df.iloc[kept].reset_index(drop=True)
y_raw = df.pop(target)
df = df.drop(columns=S.get("drop", []))

# ---- split (indices into df)
kind, _, col = S["split"].partition(":")
split_note = kind
if kind == "random":
    strat = y_raw if task == "classification" else None
    tr, te = train_test_split(np.arange(len(df)), test_size=test_frac, random_state=seed, stratify=strat)
elif kind == "time":
    if col == "@row":
        key = pd.Series(np.arange(len(df)))
    else:
        key = df.pop(col)
        if key.dtype == object:
            parsed = pd.to_datetime(key, errors="coerce")
            key = parsed if parsed.notna().mean() > 0.99 else key
    order = np.argsort(key.to_numpy(), kind="stable")
    cut = int(round((1 - test_frac) * len(df)))
    ks = key.to_numpy()[order]
    while 0 < cut < len(ks) and ks[cut] == ks[cut - 1]:  # no timestamp on both sides of the cut
        cut += 1
    tr, te = order[:cut], order[cut:]
    split_note = (f"time by {'file order' if col == '@row' else col}: "
                  f"train {ks[0]} .. {ks[cut - 1]}, test {ks[cut]} .. {ks[-1]}")
elif kind == "openml":
    if otask is None:
        sys.exit("split 'openml' needs \"source\": {\"openml_task\": <id>}")
    otr, ote = otask.get_train_test_split_indices(repeat=0, fold=0, sample=0)
    pos = pd.Series(np.arange(len(kept)), index=kept)  # original row -> row after dropping NaN targets
    tr, te = pos.reindex(otr).dropna().to_numpy(int), pos.reindex(ote).dropna().to_numpy(int)
    test_frac = len(te) / (len(tr) + len(te))
    split_note = (f"openml task {otask.task_id} predefined split, repeat 0 fold 0 "
                  f"({otask.estimation_procedure.get('type', '?')}); test_frac from spec ignored")
elif kind == "group":
    groups = df.pop(col)
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=test_frac, random_state=seed)
                  .split(df, groups=groups))
    split_note = (f"group by {col}: {groups.iloc[tr].nunique()} train groups, "
                  f"{groups.iloc[te].nunique()} test groups, none shared")
else:
    sys.exit(f"unknown split: {S['split']}")

# ---- types: object/bool/category -> category with train-only levels
cat_cols = [c for c in df.columns if df[c].dtype == object or str(df[c].dtype) in ("category", "bool", "string", "str")]
Xtr, Xte = df.iloc[tr].copy(), df.iloc[te].copy()
for c in cat_cols:
    levels = pd.Index(Xtr[c].dropna().astype(str).unique())
    for X in (Xtr, Xte):
        v = X[c].astype(str).where(X[c].notna())
        X[c] = pd.Categorical(v.where(v.isin(levels)), categories=levels)

if task == "classification":
    if "positive" in S:
        pos = S["positive"]
        y = ((y_raw == pos) | (y_raw.astype(str) == str(pos))).astype(int).to_numpy()
        classes = [f"not {S['positive']}", str(S["positive"])]
    else:
        classes, y = np.unique(y_raw.astype(str), return_inverse=True)
        classes = list(classes)
    k = len(classes)
    if metric == "pr_auc" and k != 2:
        sys.exit("pr_auc needs a binary target")
else:
    y = y_raw.astype(float).to_numpy()
ytr, yte = y[tr], y[te]

def score(pred):
    """pred: class probabilities (n, k) for classification, values (n,) for regression."""
    if metric == "auc":
        return skm.roc_auc_score(yte, pred[:, 1]) if k == 2 else \
            skm.roc_auc_score(yte, pred, multi_class="ovr", labels=list(range(k)))
    if metric == "pr_auc":
        return skm.average_precision_score(yte, pred[:, 1])
    if metric == "logloss":
        return skm.log_loss(yte, np.clip(pred, 1e-15, 1), labels=list(range(k)))
    if metric == "accuracy":
        return skm.accuracy_score(yte, pred.argmax(1))
    if metric == "rmse":
        return skm.root_mean_squared_error(yte, pred)
    if metric == "mae":
        return skm.mean_absolute_error(yte, pred)
    if metric == "r2":
        return skm.r2_score(yte, pred)
    return skm.root_mean_squared_error(np.log1p(np.clip(yte, 0, None)), np.log1p(np.clip(pred, 0, None)))

# ---- header
print(f"spec    {spec_path.name}  sha256:{hashlib.sha256(raw).hexdigest()[:12]}  ({S.get('name', '')})")
if S.get("why"):
    print(f"why     {S['why']}")
print(f"data    {data_label}: {n_raw} rows; {df.shape[1]} features ({len(cat_cols)} categorical)"
      + (f"; dropped {S['drop']}" if S.get("drop") else ""))
print(f"split   {split_note}")
print(f"sizes   train {len(tr)}, test {len(te)} (test_frac {test_frac:.3g}, seed {seed})")
if task == "classification":
    rate = lambda v: ", ".join(f"{classes[i]}={np.mean(v == i):.3f}" for i in range(k))
    print(f"target  train [{rate(ytr)}]  test [{rate(yte)}]")
else:
    print(f"target  train mean {ytr.mean():.4g} sd {ytr.std():.4g}; test mean {yte.mean():.4g} sd {yte.std():.4g}")
unseen = {c: int(Xte[c].isna().sum() - df.iloc[te][c].isna().sum()) for c in cat_cols}
unseen = {c: n for c, n in unseen.items() if n}
if unseen:
    print(f"note    test rows with a category level unseen in train (set to missing): {unseen}")
if args.check:
    sys.exit(0)

# ---- models
sub, cap = None, int(S.get("tabpfn_max_train", TABPFN_MAX_TRAIN))
if len(tr) > cap:
    sub = np.sort(np.random.default_rng(seed).choice(len(tr), cap, replace=False))
    print(f"note    train has {len(tr)} rows > {cap}: TabPFN fits on a random subsample of "
          f"{cap} (seed {seed}); xgboost@sub uses the same rows")
skip_tabpfn = df.shape[1] > TABPFN_MAX_FEATURES
if skip_tabpfn:
    print(f"note    {df.shape[1]} features > {TABPFN_MAX_FEATURES}: TabPFN v2 skipped")

def predict(model, X, chunk=None):
    f = model.predict_proba if task == "classification" else model.predict
    if chunk is None:
        return f(X)
    out, t0, n = [], time.perf_counter(), -(-len(X) // chunk)
    for j, i in enumerate(range(0, len(X), chunk)):
        out.append(f(X.iloc[i:i + chunk]))
        if j == 0 and n > 1:
            print(f"        tabpfn: {n} chunks of {chunk}, ~{(time.perf_counter() - t0) * n:.0f}s expected", flush=True)
    return np.concatenate(out)

def xgb():
    return (XGBClassifier(n_jobs=4, enable_categorical=True, random_state=seed) if task == "classification"
            else XGBRegressor(n_jobs=4, enable_categorical=True, random_state=seed))

def tabpfn():
    C = TabPFNClassifier if task == "classification" else TabPFNRegressor
    return C.create_default_for_version(ModelVersion.V2, device=args.device, random_state=seed,
                                        memory_saving_mode=True)

runs = [("xgboost", xgb, None, None)]
if sub is not None:
    runs.append(("xgboost@sub", xgb, sub, None))
if not skip_tabpfn:
    runs.append(("tabpfn-v2", tabpfn, sub, args.chunk))

rows = []
if task == "classification":  # baseline: train class frequencies for every test row
    prior = np.bincount(ytr, minlength=k) / len(ytr)
    rows.append(("baseline", score(np.tile(prior, (len(te), 1))), 0.0, len(tr), "train class prior"))
else:
    rows.append(("baseline", score(np.full(len(te), ytr.mean())), 0.0, len(tr), "train mean"))
for name, make, idx, chunk in runs:
    Xf, yf = (Xtr, ytr) if idx is None else (Xtr.iloc[idx], ytr[idx])
    t = time.perf_counter()
    model = make()
    model.fit(Xf, yf)
    s = score(predict(model, Xte, chunk))
    rows.append((name, s, time.perf_counter() - t, len(yf), "defaults"))

arrow = "higher is better" if HIGHER_BETTER[metric] else "lower is better"
print(f"\n{'model':12} {metric:>9} {'seconds':>8} {'train rows':>10}  note   ({arrow})")
for name, s, sec, n, note in rows:
    print(f"{name:12} {s:9.4f} {sec:8.1f} {n:10d}  {note}")
if args.device == "cuda" and not skip_tabpfn:
    print(f"peak vram {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB")
