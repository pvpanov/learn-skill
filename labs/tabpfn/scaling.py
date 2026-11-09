"""TabPFN v2 vs XGBoost vs CatBoost as the training set grows past v2's 10k evaluation limit.

Spec (fixed 2026-10-31 before any result; do not edit after results, add a new spec instead):
- Data: OpenML Grinsztajn numeric classification jannis (45021) and covertype (44121), binary.
- Split: one fixed random test set of 5,000 rows per dataset (seed 0). Training rows are nested
  random subsamples of the rest: per seed one permutation, first n rows.
- Sizes n: 2,500, 5,000, 10,000, 20,000, 40,000. Seeds 0, 1, 2.
- Models, all defaults:
  TabPFN v2 (memory_saving_mode=True, ignore_pretraining_limits=True; see the amendment for chunking);
  XGBoost (n_jobs=4); CatBoost (thread_count=4, verbose off).
- Metrics: ROC AUC (primary), log loss, accuracy; fit+predict seconds; TabPFN peak reserved VRAM.
- Order: sizes ascending, datasets, seeds, models; one JSON line per result, so a stopped run keeps
  everything finished so far.

Amendment 2026-10-31 (execution only, after 18 results at n=2,500; the model and data are unchanged):
the first run predicted all 5,000 test rows in one call; at jannis n=5,000 VRAM reached 15.9 GiB and
gpu-guard stopped it. TabPFN now predicts in chunks of 500 test rows (test rows don't attend to each
other, so outputs are the same up to float error; checked on one n=2,500 result), the process is capped
at 9 GiB VRAM, and an out-of-memory fit is recorded as status "oom" and that model skips larger n for
that dataset. Earlier rows keep the old spec hash.

Amendment 2 (2026-10-31, execution only, after 42 results through jannis n=10,000): TabPFN re-runs
the training rows on every predict call, so 500-row chunks cost 10 training passes (214 s per fit at
n=10,000). Chunks are now 2,500 rows, falling back to 500 on out-of-memory; the VRAM cap is 13 GiB.

Amendment 3 (2026-10-31, owner's choice): 2,500-row chunks exceed 13 GiB at jannis n=10,000 and
fit_with_cache needs 9.5 GiB of cache at n=10,000, so chunks are back to 500 only. TabPFN at jannis
n=40,000 (~2 h per fit) is recorded as status "infeasible" (16 GB card); its trees still run.
tabpfn's own TabPFNOutOfMemoryError is now caught alongside torch's.

Run with the guards attached:
  gpu-guard.mjs --watch --match scaling.py --kill ; cpu-guard.mjs --watch --match scaling.py --throttle
"""
import os, sys, json, time, hashlib
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENML_CACHE_DIR", os.path.join(os.environ.get("LEARN_HOME", os.path.expanduser("~/learning")),
                                                    "kaggle", "data", "openml"))
from pathlib import Path
import numpy as np, torch
torch.set_num_threads(4)
import openml
from sklearn.metrics import roc_auc_score, log_loss, accuracy_score
from tabpfn import TabPFNClassifier
from tabpfn.constants import ModelVersion
from tabpfn.errors import TabPFNOutOfMemoryError
from xgboost import XGBClassifier
from catboost import CatBoostClassifier

DATASETS = {"jannis": 45021, "covertype": 44121}
SIZES = [2_500, 5_000, 10_000, 20_000, 40_000]
SEEDS = [0, 1, 2]
N_TEST = 5_000
CHUNKS = (500,)  # tried in order; the next one after an out-of-memory error
INFEASIBLE = {("jannis", 40_000, "tabpfn-v2")}
OOM_ERRORS = (torch.OutOfMemoryError, TabPFNOutOfMemoryError)
VRAM_CAP_GIB = 13
OUT = Path(__file__).resolve().parent / "results" / "scaling-2026-10-31.jsonl"
SPEC_HASH = hashlib.sha256(__doc__.encode()).hexdigest()[:12]

def load(did):
    ds = openml.datasets.get_dataset(did, download_data=True, download_qualities=False)
    X, y, _, _ = ds.get_data(target=ds.default_target_attribute, dataset_format="dataframe")
    y = (y.astype(str) == sorted(y.astype(str).unique())[1]).astype(int).to_numpy()
    X = X.astype("float32").to_numpy()
    rng = np.random.default_rng(0)
    idx = rng.permutation(len(y))
    te, pool = idx[:N_TEST], idx[N_TEST:]
    return X[pool], y[pool], X[te], y[te]

def models(seed):
    return {
        "tabpfn-v2": lambda: TabPFNClassifier.create_default_for_version(
            ModelVersion.V2, device="cuda", random_state=seed,
            memory_saving_mode=True, ignore_pretraining_limits=True),
        "xgboost": lambda: XGBClassifier(n_jobs=4, random_state=seed),
        "catboost": lambda: CatBoostClassifier(thread_count=4, random_seed=seed, verbose=0),
    }

def predict(m, X, chunks):
    for k, chunk in enumerate(chunks):
        try:
            if chunk is None:
                return m.predict_proba(X)[:, 1]
            return np.concatenate([m.predict_proba(X[i:i + chunk])[:, 1] for i in range(0, len(X), chunk)])
        except OOM_ERRORS:
            torch.cuda.empty_cache()
            if k == len(chunks) - 1:
                raise
            print(f"        out of memory with chunks of {chunk}; retrying with {chunks[k + 1]}", flush=True)

def main():
    OUT.parent.mkdir(exist_ok=True)
    torch.cuda.set_per_process_memory_fraction(
        VRAM_CAP_GIB * 2**30 / torch.cuda.get_device_properties(0).total_memory)
    done, oom = set(), set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            r = json.loads(line)
            done.add((r["dataset"], r["n"], r["seed"], r["model"]))
            if r.get("status") == "oom":
                oom.add((r["dataset"], r["model"]))
    data = {name: load(did) for name, did in DATASETS.items()}
    print(f"spec {SPEC_HASH}; " + ", ".join(f"{k}: pool {len(v[1])}, test {len(v[3])}, "
          f"{v[0].shape[1]} features" for k, v in data.items()), flush=True)
    for n in SIZES:
        for name, (Xp, yp, Xt, yt) in data.items():
            for seed in SEEDS:
                tr = np.random.default_rng(seed).permutation(len(yp))[:n]
                for model, make in models(seed).items():
                    if (name, n, seed, model) in done:
                        continue
                    torch.cuda.reset_peak_memory_stats()
                    t0 = time.perf_counter()
                    if (name, model) in oom:
                        continue
                    if (name, n, model) in INFEASIBLE:
                        with OUT.open("a") as f:
                            f.write(json.dumps({"spec": SPEC_HASH, "dataset": name, "n": n, "seed": seed,
                                                "model": model, "status": "infeasible"}) + "\n")
                        continue
                    try:
                        m = make().fit(Xp[tr], yp[tr])
                        p = predict(m, Xt, CHUNKS if model == "tabpfn-v2" else (None,))
                    except OOM_ERRORS:
                        m = None
                        oom.add((name, model))
                        with OUT.open("a") as f:
                            f.write(json.dumps({"spec": SPEC_HASH, "dataset": name, "n": n, "seed": seed,
                                                "model": model, "status": "oom"}) + "\n")
                        print(f"{name:9} n={n:6} seed={seed} {model:9} OOM at {VRAM_CAP_GIB} GiB cap; "
                              f"skipping larger n", flush=True)
                        torch.cuda.empty_cache()
                        continue
                    secs = time.perf_counter() - t0
                    r = {"spec": SPEC_HASH, "dataset": name, "n": n, "seed": seed, "model": model,
                         "auc": roc_auc_score(yt, p), "logloss": log_loss(yt, p),
                         "accuracy": accuracy_score(yt, p > 0.5), "seconds": round(secs, 1),
                         "vram_gib": round(torch.cuda.max_memory_reserved() / 2**30, 2)
                         if model == "tabpfn-v2" else None}
                    with OUT.open("a") as f:
                        f.write(json.dumps(r) + "\n")
                    print(f"{name:9} n={n:6} seed={seed} {model:9} auc={r['auc']:.4f} "
                          f"{secs:6.1f}s vram={r['vram_gib']}", flush=True)
                    del m
                    torch.cuda.empty_cache()

if __name__ == "__main__":
    main()
