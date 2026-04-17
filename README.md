# HeatGuard AI

HeatGuard AI is an end-to-end heat-risk prediction system for outdoor workers.
It combines:
- Climate-informed synthetic data generation (ISO 7933 PHS)
- A multi-class XGBoost risk model (LOW, MODERATE, HIGH, CRITICAL)
- A FastAPI backend for live prediction and alerting
- A single-page frontend dashboard/check-in/SOS interface

This repository already includes generated datasets, trained models, plots, and reports.

## 1. What This Project Does

HeatGuard AI estimates heat danger in real time by combining:
- Weather context (live API + fallback)
- Worker context (hydration, activity, hours worked, acclimatization)
- Physiological proxies (WBGT, Heat Index, heart-rate estimate, water-loss estimate)

The backend returns:
- Risk score (0-100)
- Risk class label
- Action guidance
- Escalation flags (notify supervisor / trigger emergency)

## 2. Main Components

### Data and Model Pipeline
- [download_era5.py](download_era5.py): Downloads ERA5 summer data (Apr-Jun) per year for India.
- [analyze_era5.py](analyze_era5.py): Computes zone-wise climatology and distribution plots.
- [generate_dataset.py](generate_dataset.py): Generates synthetic worker heat-exposure records using pythermalcomfort PHS.
- [preprocess.py](preprocess.py): Encodes features and creates train/validation/test splits.
- [train_model.py](train_model.py): Trains/evaluates XGBoost model and exports artifacts.

### Backend API
- [backend/main.py](backend/main.py): FastAPI service and all REST endpoints.
- [backend/predictor.py](backend/predictor.py): Feature vector construction + model inference + risk logic.
- [backend/weather.py](backend/weather.py): Weather fetch, climate zone detection, WBGT/Heat Index functions.
- [backend/database.py](backend/database.py): SQLAlchemy models and DB setup.
- [backend/alerting.py](backend/alerting.py): Push/SMS/SOS integrations.
- [backend/schemas.py](backend/schemas.py): Pydantic request/response contracts.

### Frontend
- [frontend/index.html](frontend/index.html): Single-page tactical UI with loading/welcome/dashboard/detail/check-in/SOS/settings screens.
- [frontend/manifest.json](frontend/manifest.json): PWA manifest.
- [frontend/sw.js](frontend/sw.js): Service worker cache logic.
- [mobile](mobile): React Native (Expo + TypeScript) app wired to all backend endpoints.

## 3. Current Repository Layout

- [backend](backend): API app, DB file, runtime model
- [frontend](frontend): web UI app
- [mobile](mobile): React Native mobile app
- [data](data): curated data bundles and summaries
- [data/processed](data/processed): generated ML-ready dataset and split file
- [data/era5/summary](data/era5/summary): ERA5 statistical summaries
- [era5_data](era5_data): ERA5 source files (tracked yearly NetCDF + split NetCDF files)
- [models](models): training-exported model artifacts
- [artifacts/plots](artifacts/plots): visual outputs (confusion matrix, feature importance, climate distributions)
- [artifacts/reports](artifacts/reports): validation and metric reports
- [scripts/debug](scripts/debug): utility/debug scripts

## 4. Quick Start

## 4.1 Prerequisites

- Python 3.10+ (3.12 tested in this workspace)
- Windows PowerShell or any shell
- Optional for SQL Server mode: ODBC Driver 17 for SQL Server

## 4.2 Create Virtual Environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

## 4.3 Install Dependencies

The project uses backend and pipeline dependencies.

```powershell
pip install -r backend/requirements.txt
pip install pythermalcomfort==2.9.0 tqdm xarray matplotlib cdsapi pyarrow
```

Notes:
- `pyarrow` is needed for Parquet write/read convenience.
- `cdsapi` is needed only if you download fresh ERA5 files.

## 5. Environment Configuration

Create a local [.env](.env) file at repo root (already ignored by git):

```env
# Weather
OWM_API_KEY=your_openweathermap_key

# Alerts
FCM_SERVER_KEY=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

# Database mode
DB_USE_SQLITE=1

# Optional SQL Server settings (only used when DB_USE_SQLITE=0)
DATABASE_URL=
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_SERVER=localhost\SQLEXPRESS
DB_NAME=heatguard
DB_USERNAME=
DB_PASSWORD=
DB_TRUSTED_CONNECTION=yes
DB_TRUST_SERVER_CERT=yes
```

Default behavior:
- Uses SQLite file at [backend/heatguard.db](backend/heatguard.db)
- Uses weather fallback if OpenWeather API call fails

## 6. Reproduce the Pipeline

Run from project root unless noted.

## 6.1 Download ERA5 (optional if data already present)

```powershell
python download_era5.py --start-year 2010 --end-year 2025 --skip-existing
```

## 6.2 Analyze ERA5 and generate climate summaries

```powershell
python analyze_era5.py --metric median
```

Outputs:
- [data/era5/summary/era5_zone_statistics_by_year.csv](data/era5/summary/era5_zone_statistics_by_year.csv)
- [data/era5/summary/era5_zone_statistics_climatology.csv](data/era5/summary/era5_zone_statistics_climatology.csv)
- [data/era5/summary/era5_zone_statistics.csv](data/era5/summary/era5_zone_statistics.csv)
- [artifacts/plots/era5_zone_distributions_latest.png](artifacts/plots/era5_zone_distributions_latest.png)

## 6.3 Generate synthetic dataset

```powershell
python generate_dataset.py
```

Main outputs:
- [data/processed/heatguard_synthetic_india.csv](data/processed/heatguard_synthetic_india.csv)
- [data/processed/heatguard_synthetic_india.parquet](data/processed/heatguard_synthetic_india.parquet)
- [artifacts/reports/validation_report.txt](artifacts/reports/validation_report.txt)

## 6.4 Build train/validation/test splits

```powershell
python preprocess.py
```

Output:
- [data/processed/data_splits.pkl](data/processed/data_splits.pkl)

## 6.5 Train model

```powershell
python train_model.py
```

Outputs:
- [models/xgboost_heatguard.pkl](models/xgboost_heatguard.pkl)
- [artifacts/reports/model_metrics.csv](artifacts/reports/model_metrics.csv)
- [artifacts/plots/confusion_matrix.png](artifacts/plots/confusion_matrix.png)
- [artifacts/plots/feature_importance.png](artifacts/plots/feature_importance.png)

## 6.6 Backend runtime model

Backend loads:
- [backend/models/xgboost_heatguard_cpu.pkl](backend/models/xgboost_heatguard_cpu.pkl)

If you retrain and want backend to use the new model, copy/rename accordingly.

## 7. Run the Backend

From root:

```powershell
Push-Location .\backend
..\venv\Scripts\python.exe .\main.py
Pop-Location
```

API host:
- http://localhost:8000

Interactive docs:
- http://localhost:8000/docs

## 8. Run the Frontend

## 8.1 Web Frontend (Static HTML)

The frontend is static HTML.

Option A (quick): open [frontend/index.html](frontend/index.html) directly.

Option B (recommended): serve the folder.

```powershell
Push-Location .\frontend
..\venv\Scripts\python.exe -m http.server 5500
Pop-Location
```

Then open:
- http://localhost:5500

Frontend API target is currently hardcoded in [frontend/index.html](frontend/index.html) as:
- `const API_BASE = "http://localhost:8000"`

## 8.2 Mobile Frontend (React Native)

The mobile app lives in [mobile](mobile) and uses Expo.

Install and run:

```powershell
Push-Location .\mobile
npm install
npm run start
Pop-Location
```

Backend URL configuration:
- Set runtime API URL inside app (registration/settings screen), or
- set `EXPO_PUBLIC_API_BASE_URL` before launch.

Recommended API values:
- Android Emulator: `http://10.0.2.2:8000`
- iOS Simulator: `http://localhost:8000`
- Physical device: `http://<your-lan-ip>:8000`

## 9. API Endpoints

Defined in [backend/main.py](backend/main.py).

### POST /worker/register
Registers worker profile.

### POST /predict
Main prediction endpoint.

Request body (core fields):
- worker_id
- lat, lon
- hours_worked
- hydration_status
- activity_level
- acclimatized
- optional hr_bpm

Returns:
- risk_score, risk_label, risk_label_int
- alert_color, action_message, time_to_danger
- notify_supervisor, trigger_emergency
- tdb, rh, wbgt, climate_zone, timestamp

### POST /checkin
Updates working-state context for a worker.

### GET /history/{worker_id}
Returns non-LOW recent prediction logs.

### GET /supervisor/workers
Returns latest risk per worker, sorted by risk score.

### POST /sos
Triggers SOS flow and logs event.

### GET /settings/{worker_id}
Fetch worker settings.

### PUT /settings/{worker_id}
Update worker settings.

## 10. Model Performance Snapshot

From [artifacts/reports/model_metrics.csv](artifacts/reports/model_metrics.csv):
- Accuracy: 0.9766
- CRITICAL recall: 0.9546
- HIGH recall: 0.9833
- MODERATE recall: 0.9901
- Weighted AUC-ROC: 0.9991

From [artifacts/reports/validation_report.txt](artifacts/reports/validation_report.txt):
- 100,000 generated records
- 27 columns
- no missing values
- all validation checks passed

## 11. Data Notes

- This repository intentionally tracks substantial data files in [data](data) and [era5_data/yearly](era5_data/yearly).
- Intermediate extraction cache is ignored via [.gitignore](.gitignore):
  - [era5_data/extracted](era5_data/extracted)

Current tracked artifacts include:
- synthetic dataset (CSV + Parquet)
- split file for modeling
- ERA5 yearly NetCDF files
- plot/report outputs

## 12. Debug Utilities

- [scripts/debug/_smoke_test.py](scripts/debug/_smoke_test.py): PHS API smoke checks.
- [scripts/debug/_sanity_test.py](scripts/debug/_sanity_test.py): class-balance mini generation test.
- [scripts/debug/_tmp_risk_label_search.py](scripts/debug/_tmp_risk_label_search.py): brute-force search for each risk class via API.
- [scripts/debug/_probe_phs.py](scripts/debug/_probe_phs.py): legacy probing script (uses older object-style assumptions).

## 13. Known Technical Caveats

- FastAPI startup uses `@app.on_event("startup")`, which is deprecated in favor of lifespan handlers (warning only).
- Frontend includes PWA files, but explicit service worker registration is not wired in current page logic.
- Frontend currently uses worker_id=1 flow by default.
- [data/README.md](data/README.md) references external validation scripts that are not currently present in the repository snapshot.

## 14. Suggested Next Improvements

1. Add root-level `requirements.txt` or split `requirements-pipeline.txt` and `requirements-backend.txt`.
2. Add `.env.example` with documented defaults.
3. Add pytest-based tests for backend endpoint contracts and predictor consistency.
4. Add model promotion script to sync [models/xgboost_heatguard.pkl](models/xgboost_heatguard.pkl) into [backend/models/xgboost_heatguard_cpu.pkl](backend/models/xgboost_heatguard_cpu.pkl).
5. Add CI workflow for lint, unit tests, and artifact sanity checks.

---

If you want, I can next generate:
- a concise `.env.example`
- separate requirements files for pipeline and backend
- and a contributor-oriented DEVELOPMENT.md with command recipes.
