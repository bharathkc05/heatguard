from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WorkerProfile(BaseModel):
    name: Optional[str] = "Worker"
    age: int = Field(..., ge=18, le=60)
    work_type: str
    activity_level: str = "moderate"  # light/moderate/heavy/very_heavy
    acclimatized: bool = False
    supervisor_phone: Optional[str] = None
    fcm_token: Optional[str] = None


class PredictRequest(BaseModel):
    # Location (used for weather fetch)
    lat: float
    lon: float
    # Worker state
    worker_id: int
    hours_worked: float = Field(..., ge=0, le=8)
    hydration_status: str = "mild"  # well/mild/dehydrated
    activity_level: str = "moderate"
    acclimatized: bool = False
    # Optional overrides (if sensor data available)
    hr_bpm: Optional[float] = None


class PredictResponse(BaseModel):
    risk_score: float  # 0-100
    risk_label: str  # LOW/MODERATE/HIGH/CRITICAL
    risk_label_int: int  # 0/1/2/3
    alert_color: str  # green/yellow/orange/red
    action_message: str
    time_to_danger: str  # "45 min" or "Limit exceeded"
    notify_supervisor: bool
    trigger_emergency: bool
    # Environmental context
    tdb: float
    rh: float
    wbgt: float
    climate_zone: str
    timestamp: datetime


class CheckInRequest(BaseModel):
    worker_id: int
    hydration_status: str
    activity_level: str
    hours_worked: float
    acclimatized: bool


class SOSRequest(BaseModel):
    worker_id: int
    lat: float
    lon: float
    risk_score: Optional[float] = None


class AlertHistoryItem(BaseModel):
    id: int
    risk_label: str
    risk_score: float
    tdb: float
    rh: float
    wbgt: float
    timestamp: datetime
    climate_zone: str


class SupervisorWorker(BaseModel):
    worker_id: int
    name: str
    risk_label: str
    risk_score: float
    last_updated: datetime
    lat: Optional[float]
    lon: Optional[float]
