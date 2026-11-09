"""Random split vs time split: does TabPFN v2's edge over XGBoost survive time order?

Data: OpenML 151 "electricity" (NSW market, 30-min periods, 1996-98, label UP/DOWN), already in time
order. Three contiguous windows of N rows; in each, compare a random 70/30 split (3 seeds) with a
time split (first 70% train, last 30% test). The `date` column is the time index and is dropped
unless --with-date.
"""
import argparse, os, time
os.environ.setdefault("OMP_NUM_THREADS", "4")
import numpy as np, torch
torch.set_num_threads(4)
from pathlib import Path
import pandas as pd
from scipy.io import arff
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from tabpfn import TabPFNClassifier
from tabpfn.constants import ModelVersion
from xgboost import XGBClassifier

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=6000)
ap.add_argument("--starts", type=int, nargs="+", default=[18000, 28000, 38000])
ap.add_argument("--seeds", type=int, default=3)
ap.add_argument("--with-date", action="store_true")
args = ap.parse_args()

# data/electricity.arff: OpenML file 2419, downloaded 2026-10-30 (offline from here on)
df = pd.DataFrame(arff.loadarff(Path(__file__).parent / "data" / "electricity.arff")[0])
y_all = (df.pop("class").str.decode("ascii") == "UP").astype(int).to_numpy()
df["day"] = df["day"].str.decode("ascii").astype(int)
if not args.with_date:
    df = df.drop(columns=["date"])
X_all = df.astype(float).to_numpy()
device = "cuda" if torch.cuda.is_available() else "cpu"

def models():
    return [("tabpfn-v2", TabPFNClassifier.create_default_for_version(ModelVersion.V2, device=device)),
            ("xgboost", XGBClassifier(n_estimators=300, n_jobs=4))]

def auc(model, Xtr, ytr, Xte, yte):
    model.fit(Xtr, ytr)
    # predict in chunks: TabPFN's memory grows with test rows x train rows
    proba = np.concatenate([model.predict_proba(Xte[i:i + 500])[:, 1] for i in range(0, len(yte), 500)])
    return roc_auc_score(yte, proba)

print(f"features: {list(df.columns)}  rows/window: {args.n}  device: {device}")
print(f"{'window':>12} {'model':10} {'random (mean±sd)':>18} {'time':>7} {'drop':>7}")
t0 = time.perf_counter()
for s in args.starts:
    X, y = X_all[s:s + args.n], y_all[s:s + args.n]
    cut = int(0.7 * len(y))
    rand = {}
    for seed in range(args.seeds):
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=seed, stratify=y)
        for name, m in models():
            rand.setdefault(name, []).append(auc(m, Xtr, ytr, Xte, yte))
    for name, m in models():
        t = auc(m, X[:cut], y[:cut], X[cut:], y[cut:])
        r = np.array(rand[name])
        print(f"{s:>6}-{s + args.n:<5} {name:10} {r.mean():.4f}±{r.std():.4f} {t:7.4f} {r.mean() - t:7.4f}")
print(f"total {time.perf_counter() - t0:.0f}s" + (f", peak vram {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB" if device == "cuda" else ""))
