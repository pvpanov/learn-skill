"""Smoke test: does tabpfn 9.2's FinetunedTabPFNClassifier run on open V2 weights?

Prep check, not a lesson. Compares in-context TabPFN v2 vs the same model after a few
epochs of full-weight fine-tuning on one small dataset. A single split on a tiny dataset
says nothing about whether fine-tuning helps in general.
"""
import os, time
os.environ.setdefault("OMP_NUM_THREADS", "4")
import torch
torch.set_num_threads(4)
from sklearn.datasets import load_breast_cancer
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from tabpfn import TabPFNClassifier
from tabpfn.constants import ModelVersion
from tabpfn.finetuning import FinetunedTabPFNClassifier

device = "cuda" if torch.cuda.is_available() else "cpu"
X, y = load_breast_cancer(return_X_y=True)
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=0, stratify=y)

t = time.perf_counter()
base = TabPFNClassifier.create_default_for_version(ModelVersion.V2, device=device, n_estimators=2)
base.fit(Xtr, ytr)
print(f"in-context v2   auc={roc_auc_score(yte, base.predict_proba(Xte)[:, 1]):.4f} time={time.perf_counter() - t:.1f}s")

t = time.perf_counter()
ft = FinetunedTabPFNClassifier(
    model_version=ModelVersion.V2,  # never the gated default (v3.5)
    device=device,
    epochs=5,
    time_limit=60,
    learning_rate=1e-5,
    validation_split_ratio=0.2,
    n_estimators_finetune=2, n_estimators_validation=2, n_estimators_final_inference=2,
    random_state=0,
)
ft.fit(Xtr, ytr)
print(f"fine-tuned v2   auc={roc_auc_score(yte, ft.predict_proba(Xte)[:, 1]):.4f} time={time.perf_counter() - t:.1f}s")
if device == "cuda":
    print(f"peak vram {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB")
