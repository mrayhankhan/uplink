# Baithak: a small business goes digital in one sitting

Team IIITDards, IIIT Delhi. Airtel Sync 2026 Digital Track, case Project Udyam Digital.

**Live prototype: https://mrayhankhan.github.io/baithak/**

The case operator, Accel Telecom, is fictional. All leads, businesses, people, identifiers and documents are synthetic and come from the case pack.

## What is here

| Path | Contents |
|---|---|
| `index.html` | The deployed prototype, a single self-contained file |
| `prototype/` | Prototype source, rules engine, KYC validator, data build and tests |
| `analysis/` | Funnel, propensity and impact model, KYC pipeline and audit script |

## Run the prototype

Open `index.html` in a browser. It needs no server and no API key. Free text goes through the offline parser, and a hosted language model can plug into the same extraction and explanation slots.

To rebuild from source:

```bash
python -I prototype/build_data.py <data_dir> <ocr_raw.json> analysis/results.json analysis/kyc_results.json prototype/src/data.js
python -I prototype/build.py
```

To run the tests:

```bash
node prototype/tests/test_engine.js <data_dir>/product_catalogue.csv
node prototype/tests/test_kyc.js
```

## How it decides

- **Rules engine** (`prototype/src/engine.js`): eligibility, quantities, price, contract and activation order. Deterministic, with 20 scenario tests and an audit on every bundle.
- **Language layer**: reads free text and explains the result. It never sets a price, and every rupee figure in a model reply is checked against the engine.
- **Smart KYC** (`prototype/src/kyc.js`): runs on raw OCR text. Image gate, GSTIN repair by character position, mod-36 checksum, registry lookup, then name, signatory and bill-age checks. It matches `analysis/kyc_pipeline.py` on all 12 applicants.
- **Propensity** (`analysis/model.py`): logistic regression on what is known when a lead arrives. AUC 0.72 on a 30% holdout.
- **Staged activation**: cloud services first, one premises visit, then each SIM as its user is identified, following the Telecommunications (User Identification) Rules 2026.

## Reproduce the analysis

```bash
powershell -File analysis/win_ocr.ps1 -Dir <data_dir>/kyc_documents -Out ocr_raw.json
python -I analysis/kyc_pipeline.py <data_dir> ocr_raw.json kyc_results.json
python -I analysis/model.py <data_dir> results.json
python -I analysis/audit.py <data_dir>
```

Recovery rates are assumptions, listed in `RECOV` in `analysis/model.py`. The base case applies a 0.6 multiplier and the low case 0.35.

## Mocked in the prototype

E-sign, UPI autopay, per-SIM identification, premises visits and Entity Locker. Registry lookups use the mock files in the case pack. OCR ran once with the Windows OCR engine, and the raw text ships with the page. Regional language strings have not been reviewed by native speakers.
