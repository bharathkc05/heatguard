from datetime import datetime

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from alerting import send_fcm_push, send_sos_alerts, send_supervisor_sms
from database import PredictionLog, SOSLog, SessionLocal, Worker, create_tables, get_db
from predictor import build_feature_vector, predict_risk
from schemas import AlertHistoryItem, CheckInRequest, PredictRequest, PredictResponse, SOSRequest, WorkerProfile
from weather import compute_heat_index, compute_wbgt, detect_climate_zone, fetch_weather

app = FastAPI(title="HeatGuard AI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    create_tables()
    db = SessionLocal()
    try:
        ensure_default_worker(db)
    finally:
        db.close()
    print("HeatGuard AI API started. Database ready.")


def ensure_default_worker(db: Session) -> Worker:
    worker = db.query(Worker).filter(Worker.id == 1).first()
    if worker:
        return worker

    existing = db.query(Worker).order_by(Worker.id.asc()).first()
    if existing:
        return existing

    worker = Worker(
        name="Worker",
        age=30,
        work_type="construction",
        activity_level="moderate",
        acclimatized=False,
        supervisor_phone=None,
        fcm_token=None,
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return worker


def resolve_worker(db: Session, worker_id: int) -> Worker | None:
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if worker:
        return worker
    if worker_id == 1:
        return ensure_default_worker(db)
    return None


# Worker Registration
@app.post("/worker/register")
def register_worker(profile: WorkerProfile, db: Session = Depends(get_db)):
    worker = Worker(
        name=profile.name,
        age=profile.age,
        work_type=profile.work_type,
        activity_level=profile.activity_level,
        acclimatized=profile.acclimatized,
        supervisor_phone=profile.supervisor_phone,
        fcm_token=profile.fcm_token,
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return {"worker_id": worker.id, "message": "Worker registered successfully"}


# Main Prediction Endpoint
@app.post("/predict", response_model=PredictResponse)
async def predict(req: PredictRequest, db: Session = Depends(get_db)):
    # Get worker profile
    worker = resolve_worker(db, req.worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # Fetch live weather
    weather = await fetch_weather(req.lat, req.lon)
    tdb, tr, rh, v = weather["tdb"], weather["tr"], weather["rh"], weather["v"]

    # Compute derived features
    wbgt = compute_wbgt(tdb, rh, tr, v)
    heat_index = compute_heat_index(tdb, rh)
    zone = detect_climate_zone(req.lat, req.lon)

    # Build feature vector - must match training order
    features = build_feature_vector(
        tdb=tdb,
        tr=tr,
        rh=rh,
        v=v,
        wbgt=wbgt,
        heat_index=heat_index,
        age=worker.age,
        weight=65.0,  # default - add to worker profile in Phase 2
        height=165.0,  # default - add to worker profile in Phase 2
        activity_level=req.activity_level,
        acclimatized=req.acclimatized,
        hydration_status=req.hydration_status,
        hours_worked=req.hours_worked,
        climate_zone=zone,
        hr_bpm=req.hr_bpm,
    )

    # Run model
    result = predict_risk(features)

    # Log prediction to database
    log = PredictionLog(
        worker_id=worker.id,
        tdb=tdb,
        rh=rh,
        v=v,
        wbgt=wbgt,
        heat_index=heat_index,
        hours_worked=req.hours_worked,
        hydration_status=req.hydration_status,
        risk_score=result["risk_score"],
        risk_label=result["risk_label"],
        risk_label_int=result["risk_label_int"],
        lat=req.lat,
        lon=req.lon,
        climate_zone=zone,
    )
    db.add(log)
    db.commit()

    # Send alerts if needed
    if result["notify_supervisor"] and worker.supervisor_phone:
        send_supervisor_sms(
            worker.supervisor_phone,
            worker.name,
            result["risk_label"],
            result["risk_score"],
            req.lat,
            req.lon,
        )
    if result["risk_label_int"] >= 2 and worker.fcm_token:
        await send_fcm_push(
            worker.fcm_token,
            title=f"{result['risk_label']} RISK - HeatGuard",
            body=result["action_message"],
        )

    return PredictResponse(
        **result,
        tdb=tdb,
        rh=rh,
        wbgt=wbgt,
        climate_zone=zone,
        timestamp=datetime.utcnow(),
    )


# Check-In
@app.post("/checkin")
def checkin(req: CheckInRequest, db: Session = Depends(get_db)):
    worker = resolve_worker(db, req.worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    worker.activity_level = req.activity_level
    worker.acclimatized = req.acclimatized
    db.commit()
    return {"message": "Check-in recorded. Refresh your risk score."}


# Alert History
@app.get("/history/{worker_id}")
def get_history(worker_id: int, limit: int = 50, db: Session = Depends(get_db)):
    logs = (
        db.query(PredictionLog)
        .filter(PredictionLog.worker_id == worker_id)
        .filter(PredictionLog.risk_label_int >= 1)  # exclude LOW
        .order_by(PredictionLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    return logs


# Supervisor Dashboard
@app.get("/supervisor/workers")
def supervisor_workers(db: Session = Depends(get_db)):
    workers = db.query(Worker).all()
    result = []
    for w in workers:
        latest = (
            db.query(PredictionLog)
            .filter(PredictionLog.worker_id == w.id)
            .order_by(PredictionLog.timestamp.desc())
            .first()
        )
        if latest:
            result.append(
                {
                    "worker_id": w.id,
                    "name": w.name,
                    "risk_label": latest.risk_label,
                    "risk_score": latest.risk_score,
                    "last_updated": latest.timestamp,
                    "lat": latest.lat,
                    "lon": latest.lon,
                }
            )
    return sorted(result, key=lambda x: x["risk_score"], reverse=True)


# SOS
@app.post("/sos")
async def sos(req: SOSRequest, db: Session = Depends(get_db)):
    worker = resolve_worker(db, req.worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    log = SOSLog(worker_id=worker.id, lat=req.lat, lon=req.lon, risk_score=req.risk_score or 100.0)
    db.add(log)
    db.commit()

    await send_sos_alerts(
        worker_name=worker.name,
        supervisor_phone=worker.supervisor_phone or "",
        fcm_token=worker.fcm_token or "",
        lat=req.lat,
        lon=req.lon,
        risk_score=req.risk_score or 100.0,
    )

    return {
        "message": "SOS sent. Supervisor and emergency services notified.",
        "supervisor_phone": worker.supervisor_phone,
        "location": {"lat": req.lat, "lon": req.lon},
    }


# Settings
@app.get("/settings/{worker_id}")
def get_settings(worker_id: int, db: Session = Depends(get_db)):
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker


@app.put("/settings/{worker_id}")
def update_settings(worker_id: int, profile: WorkerProfile, db: Session = Depends(get_db)):
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    for field, value in profile.dict(exclude_unset=True).items():
        setattr(worker, field, value)
    db.commit()
    return {"message": "Settings updated"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
