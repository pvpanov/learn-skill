"""Does shuffling the training rows change TabPFN v2's predictions? Same rows, different order."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")
import numpy as np, torch
torch.set_num_threads(4)
from sklearn.datasets import load_breast_cancer
from sklearn.model_selection import train_test_split
from tabpfn import TabPFNClassifier
from tabpfn.constants import ModelVersion

X, y = load_breast_cancer(return_X_y=True)
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=0, stratify=y)
perm = np.random.default_rng(1).permutation(len(ytr))

def proba(Xa, ya):
    m = TabPFNClassifier.create_default_for_version(ModelVersion.V2, device="cuda", random_state=0)
    return m.fit(Xa, ya).predict_proba(Xte)[:, 1]

p1, p2 = proba(Xtr, ytr), proba(Xtr[perm], ytr[perm])
print(f"max |p(original) - p(shuffled)| over {len(yte)} test rows: {np.abs(p1 - p2).max():.2e}")
print(f"same predicted class for all rows: {bool(((p1 > .5) == (p2 > .5)).all())}")
