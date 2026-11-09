# Kaggle lane: dataset shortlist

Checked 2026-10-31. Kaggle file sizes, competition metrics, licences and "rules accepted" status come
from the Kaggle API, using the owner's token. Rows × cols come from loading the file where it is
already in `data/`, and from secondary sources (marked *ext*) where the competition's rules have not
been accepted yet. None of the competitions below has had its rules accepted yet.

TabPFN v2's paper evidence covers ≤10k train rows, ≤500 features, and random (iid) splits.
`bench.py` subsamples to 10k train rows for TabPFN, and adds an `xgboost@sub` row so that size is not
confounded with model.

Structure tags: **iid**, **grouped** (rows share an entity), **panel** (entity × time), **time**,
**high-card** (high-cardinality categoricals), **finance**.

| # | Dataset | Rows × cols (train) | Structure | Local? |
| --- | --- | --- | --- | --- |
| 1 | House Prices | 1,460 × 81 | iid (sale year 2006–10) | no (rules) |
| 2 | Company Bankruptcy (Taiwan) | 6,819 × 96 | iid, finance | yes |
| 3 | Default of Credit Card Clients | 30,000 × 25 | iid, finance | yes |
| 4 | Spaceship Titanic | 8,693 × 14 *ext* | grouped | no (rules) |
| 5 | Parkinson's Telemonitoring | 5,875 × 22 | grouped (42 patients) | yes |
| 6 | Amazon Employee Access | 32,769 × 10 *ext* | high-card | no (rules) |
| 7 | Bike Sharing Demand | 10,886 × 12 *ext* | time | no (rules) |
| 8 | Bank Marketing | 41,188 × 21 | time (hidden), finance/econ | yes |
| 9 | Credit Card Fraud | 284,807 × 31 *ext* | time, extreme imbalance, finance | no (69 MB) |
| 10 | Rossmann Store Sales | 1,017,209 × 9 *ext* (+ store.csv) | panel, high-card | no (rules) |
| 11 | S&P 500 daily, 5 years | 619,040 × 7 | panel, time, finance | yes |

Rows marked **>50k** below are larger than ideal: TabPFN sees a 10k subsample, so they test its
scale limit rather than its home turf.

---

### 1. House Prices: Advanced Regression Techniques (competition)
- URL: https://www.kaggle.com/competitions/house-prices-advanced-regression-techniques
- 1,460 × 81 (Id, 79 features, SalePrice) *ext*; test 1,459 rows. Many categoricals and missing values.
- Target `SalePrice`. Metric: RMSLE (Kaggle states RMSE of log price), so use `rmsle`.
- Structure: iid-ish. `YrSold` spans 2006–2010, across the housing crash.
- Teaches: TabPFN regression at small n with mixed types, on the classic feature-engineering problem.
  Do the gains from the known fixes (log target, outliers, quality × area) survive with TabPFN?
- Access: Getting Started competition; accept the rules. Files: train 461 KB, test 451 KB.

### 2. Company Bankruptcy Prediction (dataset)
- URL: https://www.kaggle.com/datasets/fedesoriano/company-bankruptcy-prediction
- 6,819 × 96 (target + 95 financial ratios). 3.2% bankrupt (Taiwan Economic Journal, 1999–2009).
- Target `Bankrupt?`. Metric: `pr_auc` (heavy imbalance); `auc` is the common one.
- Structure: iid (no firm or date column), so this is TabPFN's home turf: ≤10k rows, <500 features.
- Teaches: the **control**. If blind TabPFN does not beat blind XGBoost here, the paper's claim fails on
  its own ground. It also probes many correlated, heavy-tailed ratio features.
- Access: dataset, no rules. Licence "Data files © Original Authors" (from UCI). Zip 4.9 MB.
  Already in `data/company-bankruptcy-prediction/`.

### 3. Default of Credit Card Clients (dataset)
- URL: https://www.kaggle.com/datasets/uciml/default-of-credit-card-clients-dataset
- 30,000 × 25. 22.1% default. Taiwan, April–September 2005.
- Target `default.payment.next.month`. Metric: `auc`.
- Structure: iid across clients. Six months of history are flattened into wide columns
  (`PAY_0..6`, `BILL_AMT1..6`).
- Teaches: whether hand-built history features (trend, utilisation) beat what TabPFN infers from the raw
  wide columns, and what the 10k subsample costs. This is the bench smoke-test dataset.
- Access: dataset, CC0. Zip 1.0 MB. Already in `data/`.

### 4. Spaceship Titanic (competition)
- URL: https://www.kaggle.com/competitions/spaceship-titanic
- About 8,693 × 14 *ext*. Target `Transported`. Metric: accuracy (per the Kaggle API).
- Structure: **grouped**. `PassengerId` is `gggg_pp`, where `gggg` is a travel group (often a family),
  and `Cabin` is `deck/num/side`.
- Teaches: whether a random split leaks group information. Compare `random` with
  `group:<group id>` (the group id is derived from `PassengerId`). It fits within TabPFN's ≤10k
  envelope, so any gap comes from structure, not size.
- Access: Getting Started competition; accept the rules. Files: train 805 KB, test 372 KB.

### 5. Parkinson's Telemonitoring (dataset)
- URL: https://www.kaggle.com/datasets/mountainguest/parkinsons-telemonitoring
- 5,875 × 22: about 140 voice recordings from each of 42 patients.
- Target `motor_UPDRS` or `total_UPDRS` (pick one and drop the other). Metric: `mae` or `rmse`.
- Structure: **grouped** (`subject#`), with `test_time` inside each patient.
- Teaches: the sharpest iid-violation test at small n. Rows from one patient are near-duplicates, so a
  random split mostly measures how well a model recognises the patient. `group:subject#` asks the real
  question: does it generalise to a new patient? It fits TabPFN's envelope.
- Access: dataset. Licence "Other" (UCI original, CC BY 4.0). 0.3 MB. Already in `data/`.

### 6. Amazon.com Employee Access Challenge (competition)
- URL: https://www.kaggle.com/competitions/amazon-employee-access-challenge
- 32,769 × 10 *ext* (`ACTION` + 9 categorical ID columns). `RESOURCE` has about 7.5k levels
  (OpenML d/43900). Metric: AUC.
- Structure: **high-card**. Every feature is an ID code, and one column is redundant.
- Teaches: TabPFN's categorical handling at very high cardinality, against XGBoost's native categoricals,
  against thoughtful encodings (target or count encoding inside CV folds, which is itself a leakage
  lesson). The data is >10k, so TabPFN is subsampled.
- Access: Featured competition; accept the rules. Files: train 2.0 MB, test 3.9 MB.

### 7. Bike Sharing Demand (competition)
- URL: https://www.kaggle.com/competitions/bike-sharing-demand
- 10,886 × 12 *ext*, hourly, 2011–2012. Kaggle's test set is days 20 to month end, and train is days
  1–19. Target `count`. Metric: RMSLE.
- Structure: **time**, with a trend (2012 demand above 2011). Kaggle's split is interpolation, not
  forecasting.
- Teaches: TabPFN regression when the test target sits outside the training range: can it extrapolate a
  trend? `casual + registered = count` is a planted leak that must be dropped. Compare Kaggle's
  interpolating split with a real `time:datetime` forecast split.
- Access: Playground competition; accept the rules. Files: train 648 KB, test 324 KB.

### 8. Bank Marketing (dataset)
- URL: https://www.kaggle.com/datasets/henriqueyamahata/bank-marketing
- 41,188 × 21 (`bank-additional-full.csv`, `;`-separated). 11.3% `yes`. Portuguese bank phone campaigns.
- Target `y`. Metric: `auc`.
- Structure: **time, hidden**. Rows are in date order (May 2008 to November 2010) but there is no
  year column. Macro features (`euribor3m`, `emp.var.rate`, `nr.employed`) are near-proxies for the
  date.
- Teaches: random split against `time:@row`, and what macro features do across a regime change. It also
  has a textbook leak: `duration` is only known after the call. Econometrics flavour. The data is
  >10k, so TabPFN is subsampled. A time-split run is about 4 minutes (25 chunks); attend it, or set
  `"tabpfn_max_train": 5000` in the spec.
- Access: dataset. Licence "Other" (UCI original, CC BY 4.0). Zip 0.4 MB. Already in `data/`.

### 9. Credit Card Fraud Detection (dataset) — **>50k**
- URL: https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud
- 284,807 × 31 *ext*: `Time`, PCA features `V1..V28`, `Amount`, `Class`. 492 frauds (0.172%) over 2
  days.
- Target `Class`. Metric: AUPRC (`pr_auc`), as the dataset page recommends.
- Structure: **time** (`Time` in seconds), extreme imbalance, anonymised features.
- Teaches: a hard limit for TabPFN. A 10k subsample holds about 17 frauds. Compare stratified
  subsampling with time order.
- Access: dataset. Licence ODbL / Database Contents. Zip 69 MB, CSV 151 MB. Not downloaded.

### 10. Rossmann Store Sales (competition) — **>50k**
- URL: https://www.kaggle.com/competitions/rossmann-store-sales
- 1,017,209 × 9 *ext* daily sales for 1,115 stores, 2013-01-01 to 2015-07-31, plus `store.csv` (store
  metadata). Target `Sales`. Metric: RMSPE; zero-sales days are not scored.
- Structure: **panel**, **high-card** (`Store`), **time** (the test set is the following 6 weeks).
- Teaches: feature-engineered GBDT (lags, store effects, promotions) against blind TabPFN on 1% of the
  rows, which is the scale limit. It needs a derived CSV (merge `store.csv`, drop closed days), which
  the agent writes.
- Access: Featured competition; accept the rules. Files: train 38 MB, test 1.4 MB.

### 11. S&P 500 stock data, 5 years (dataset) — **>50k**
- URL: https://www.kaggle.com/datasets/camnugent/sandp500
- 619,040 × 7 (`date, open, high, low, close, volume, Name`). 505 tickers, 2013-02-08 to 2018-02-07.
- Target: none is given. The owner defines one, such as the sign of next-day return or next-5-day
  realised volatility, and the agent builds lagged features and a derived CSV.
- Structure: **panel**, **time**, **finance**.
- Teaches: the setting closest to market data. It shows non-stationarity, overlapping-window leakage,
  cross-sectional correlation at each date, and how small the true signal is. A `time:date` split
  keeps all tickers on each side; `group:Name` gives new-ticker generalisation.
- Access: dataset, CC0. Zip 20 MB. Already in `data/sandp500/`.

---

## Top 3 for a first session

All three are already downloaded and need no rules acceptance.

1. **Parkinson's Telemonitoring (#5)**: the clearest iid-violation test inside TabPFN's ≤10k
   envelope. A random split against a patient split isolates structure from size.
2. **Company Bankruptcy (#2)**: the home-turf control. It fixes what "TabPFN wins" looks like before
   the structured cases are judged.
3. **Bank Marketing (#8)**: hidden time order, a regime change, macro proxies and a leak, all in one
   finance and econometrics table. It moves from "does the edge survive?" to "what does a thoughtful
   solution have to catch?"

Runners-up if rules get accepted: Spaceship Titanic (grouped, small) and Bike Sharing (trend
extrapolation in regression).

---

## OpenML benchmark suites

Checked 2026-10-31 against the OpenML API (`openml.study.get_suite`). A suite is a list of tasks, each
with fixed splits; use a task id in a spec (`"source": {"openml_task": <id>}, "split": "openml"`) and
`find_openml.py --suite <id>` to filter a suite by structure.

| Suite | ID | Tasks | What | URL |
| --- | --- | --- | --- | --- |
| OpenML-CC18 | 99 | 72 | Curated classification, 500–100k rows, no artificial data | https://www.openml.org/search?type=benchmark&study_type=task&id=99 |
| AutoML Benchmark, classification | 271 | 71 | AMLB classification tasks (`amlb-classification-all`) | https://www.openml.org/search?type=benchmark&study_type=task&id=271 |
| AutoML Benchmark, regression | 269 | 33 | AMLB regression tasks (`amlb-regression`) | https://www.openml.org/search?type=benchmark&study_type=task&id=269 |
| OpenML-CTR23 | 353 | 35 | Curated regression, 500–100k rows | https://www.openml.org/search?type=benchmark&study_type=task&id=353 |
| TabArena-v0.1 | 457 | 51 | The TabArena living benchmark's iid datasets (tabarena.ai) | https://www.openml.org/search?type=benchmark&study_type=task&id=457 |
| Grinsztajn et al. tabular benchmark | 334–337 | 7/17/19/16 | January 2023 version: categorical classification (334), categorical regression (335), numerical regression (336), numerical classification (337). 297–300 are older suites with the same names. | https://www.openml.org/search?type=benchmark&study_type=task&id=337 |
| TabZilla Hard | 379 | 36 | The hard subset from the TabZilla study | https://www.openml.org/search?type=benchmark&study_type=task&id=379 |

AMLB, Grinsztajn, TabZilla and TabArena suites are marked `in_preparation` on OpenML; that is their
normal state and they load fine.
