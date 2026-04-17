# HeatGuard Mobile (React Native)

This folder contains the React Native frontend for HeatGuard AI using Expo + TypeScript.

## Features Covered

The mobile app is wired to all backend endpoints:

- `POST /worker/register`
- `POST /predict`
- `POST /checkin`
- `GET /history/{worker_id}`
- `GET /supervisor/workers`
- `POST /sos`
- `GET /settings/{worker_id}`
- `PUT /settings/{worker_id}`

## 1. Install

From this folder:

```powershell
npm install
```

## 2. Configure Backend URL

Option A: runtime setting inside app:

- Open app and set API Base URL on registration/settings screen.

Option B: environment variable:

```powershell
$env:EXPO_PUBLIC_API_BASE_URL = "http://192.168.1.10:8000"
```

Recommended values:

- Android Emulator -> `http://10.0.2.2:8000`
- iOS Simulator -> `http://localhost:8000`
- Physical Phone -> `http://<your-lan-ip>:8000`

## 3. Run App

```powershell
npm run start
```

Then launch Android/iOS/Web from Expo terminal.

## 4. Typecheck

```powershell
npm run typecheck
```

## 5. Backend Requirement

Start backend first from `backend` folder:

```powershell
python main.py
```

API docs:

- `http://localhost:8000/docs`
