"""Smoke test: TabPFN v2 vs a tuned-default XGBoost on a small dataset. Prep check, not a lesson."""
import os, time
os.environ.setdefault("OMP_NUM_THREADS", "4")
import torch
torch.set_num_threads(4)
from sklearn.datasets import load_breast_cancer
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from tabpfn import TabPFNClassifier
from tabpfn.constants import ModelVersion
from xgboost import XGBClassifier

X, y = load_breast_cancer(return_X_y=True)
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=0, stratify=y)
for name, model in [("tabpfn-v2", TabPFNClassifier.create_default_for_version(ModelVersion.V2, device="cuda" if torch.cuda.is_available() else "cpu")),
                    ("xgboost", XGBClassifier(n_estimators=300, n_jobs=4))]:
    t = time.perf_counter()
    model.fit(Xtr, ytr)
    auc = roc_auc_score(yte, model.predict_proba(Xte)[:, 1])
    print(f"{name:10} auc={auc:.4f} time={time.perf_counter() - t:.1f}s")
if torch.cuda.is_available():
    print(f"peak vram {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB")
