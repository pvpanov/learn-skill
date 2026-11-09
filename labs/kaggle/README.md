# Kaggle lane

This lane runs a three-way comparison on real Kaggle tabular data: **blind XGBoost** (defaults),
**blind TabPFN v2** (defaults), and a **thoughtful solution** (proper validation and feature
engineering). The owner owns the methodology, the predictions and the interpretation. The agent writes
all the code. It is used from `learn` sessions, currently in topic `tabpfn`. There are no
leaderboards, dashboards or submission automation.

## Layout

| Path | What |
| --- | --- |
| `shortlist.md` | 11 candidate datasets by structure (iid, grouped, panel, time, high-card, finance), with a top 3. |
| `bench.py` | Blind baselines from a spec file. Prints a results table. |
| `find_openml.py` | Lists OpenML datasets by rows, features, classes, missing values, name or suite. Read-only. |
| `specs/<name>.json` | One spec per experiment, written **before** the first run. `smoke-*.json` are harness tests. |
| `data/<dataset-slug>/` | Downloaded data. `data/sklearn/` holds the smoke-test CSVs; `data/openml/` is the OpenML cache. |
| `work/<dataset-slug>/` | The thoughtful solution's scripts, written by the agent (create when needed). |

Results go into the learn topic's `log.md` (paste the table), not into a file here.

## How a session uses it

1. The owner picks a dataset (see `shortlist.md`) and states the split, metric, columns to drop
   (leaks, IDs), and a prediction with confidence: which model wins, and by roughly how much.
2. The agent writes `specs/<dataset>-<split>.json` from that. The keys are documented at the top of
   `bench.py`; `why` records the owner's reasoning. Run `--check` first: it prints split sizes, class
   balance and unseen categories, and fits nothing.
3. Run the guard checks, then the bench, attended (see Runtime).
4. The owner interprets the results. The thoughtful solution then goes in `work/<slug>/`, scored on
   **the same spec** (same split and metric).
5. Never edit a spec after seeing results. Write a new spec file instead. The printed `sha256` makes a
   changed spec visible.

```powershell
$py = "$env:LEARN_HOME/.venv/Scripts/python.exe"
cd $env:LEARN_HOME/kaggle
& $py bench.py specs/smoke-breast-cancer.json --check
node <gpu-occupancy>/scripts/gpu-guard.mjs --check
node <gpu-occupancy>/scripts/cpu-guard.mjs --check
& $py bench.py specs/smoke-breast-cancer.json
```

Splits: `random` (stratified for classification), `time:<col>` (the last `test_frac` by time, with
no timestamp on both sides of the cut), `time:@row` (file order is time order), and `group:<col>`
(no group shared between train and test). Metrics: `auc`, `pr_auc`, `logloss`, `accuracy`, `rmse`,
`mae`, `r2`, `rmsle`. A `baseline` row (train prior or train mean) is always printed.

## Runtime and VRAM (measured 2026-10-31, RTX 5080)

- TabPFN predicts in chunks of 500 test rows with `memory_saving_mode=True`. With 10k train rows,
  `auto` peaked at **10.1 GiB**; `True` peaked at **1.6–1.9 GiB** at the same speed.
  `fit_mode="fit_with_cache"` breached the VRAM floor and was killed by the guard. Don't use it.
- Speed is roughly 10 s per 500 test rows with 10k train rows, and 2 s with 2k train rows. A 10k ×
  10k run takes about 3–4 minutes, so attend it, and run the watchdog in a second terminal:
  `node <gpu-occupancy>/scripts/gpu-guard.mjs --watch --match bench.py --kill`.
  To stay under 2 minutes, set `"tabpfn_max_train": 5000` in the spec, or lower `test_frac`.
- Threads are capped at 4 (`OMP_NUM_THREADS`, `torch.set_num_threads`, XGBoost `n_jobs`).
- TabPFN weights are cached in `%APPDATA%/tabpfn` (v2 classifier and regressor, about 30 MB each).
  Always use v2: newer versions need a licence the owner hasn't accepted.

## Kaggle access

Credentials are an API token in `~/.kaggle/access_token`. The `kaggle` CLI (2.2.5) and `kagglehub`
(1.0.3) both read that file directly; both were verified 2026-10-31 (`ACCESS_TOKEN` auth, competition
file listing). No environment variable is needed. If some other tool insists on `KAGGLE_API_TOKEN`,
set it for that shell only, without printing it:

```powershell
$env:KAGGLE_API_TOKEN = (Get-Content -Raw "$HOME/.kaggle/access_token").Trim()
```

The old `~/.kaggle/kaggle.json` (2024 legacy key) now returns 401. It is unused, because the token
is tried first.

**Datasets** need no rules acceptance:

```powershell
$k = "$env:LEARN_HOME/.venv/Scripts/kaggle.exe"
& $k datasets files fedesoriano/company-bankruptcy-prediction
& $k datasets download fedesoriano/company-bankruptcy-prediction -p $env:LEARN_HOME/kaggle/data/company-bankruptcy-prediction --unzip
```

**Competitions** follow these steps:
1. The owner opens `https://www.kaggle.com/competitions/<slug>/rules` in a browser and clicks
   *I Understand and Accept*. This is the owner's step; agents never accept rules.
2. Download:

   ```powershell
   & $k competitions download -c <slug> -p $env:LEARN_HOME/kaggle/data/<slug>
   Expand-Archive $env:LEARN_HOME/kaggle/data/<slug>/<slug>.zip -DestinationPath $env:LEARN_HOME/kaggle/data/<slug>
   ```
3. Submitting is optional, manual, and initiated by the owner only:

   ```powershell
   & $k competitions submit -c <slug> -f submission.csv -m "short description"
   ```

Keep downloads under 200 MB. `kagglehub` caches in `~/.cache/kagglehub` (C:), so prefer
the CLI with `-p`, or first set `$env:KAGGLEHUB_CACHE = "$env:LEARN_HOME/kaggle/data/kagglehub"`.

## OpenML (second source)

OpenML has curated suites of tasks (a dataset plus a target, fixed splits and a metric) and searchable
metadata, so it is the place to pick a dataset **by structure**. Suites are listed in `shortlist.md`.
`openml` 0.15.1 is in the venv; no account or key is needed to read.

```powershell
$py = "$env:LEARN_HOME/.venv/Scripts/python.exe"
cd $env:LEARN_HOME/kaggle
& $py find_openml.py --rows 1000..10000 --features ..100 --classes 2 --missing 1..
& $py find_openml.py --suite 99 --rows ..10000      # within OpenML-CC18; also prints task ids
& $py find_openml.py --name credit
```

In a spec, replace `csv` with `source`. `target` defaults to the dataset's (or task's) target:

```json
"source": {"openml_task": 31}, "split": "openml"
"source": {"openml_dataset": 31}, "split": "random"
```

`"split": "openml"` uses the task's own split (repeat 0, fold 0; for 10-fold CV that is 90/10), so
results line up with published OpenML numbers for that task. The other splits work on either source.
`specs/smoke-openml-credit-g.json` is the harness test. Data is cached in `data/openml/`; datasets
over 20M cells are refused. Importing `openml` also creates an empty `~/.openml` config folder on C:.

The OpenML server is flaky: it has returned "Database connection error" and a spurious "dataset not
found" for a valid id. `bench.py` and `find_openml.py` retry 4 times (2, 4, 8, 16 s). If it still
fails, wait a few minutes; the id is probably fine.

## Owner actions

- None blocking. Credentials work, and the top-3 datasets are already in `data/`.
- Per competition, only when one is chosen: accept its rules in the browser (step 1 above).
  As of 2026-10-31, no shortlisted competition has been entered.
