from pathlib import Path

import joblib
import numpy as np

# Load model once at startup - not on every request
MODEL_PATH = Path(__file__).parent / "models" / "xgboost_heatguard_cpu.pkl"
model = joblib.load(MODEL_PATH)
if hasattr(model, "set_param"):
    model.set_param({"device": "cpu"})  # fix GPU/CPU mismatch warning
elif hasattr(model, "set_params"):
    model.set_params(device="cpu")

# Must match preprocess.py FEATURES list exactly - same order
FEATURES = [
    "tdb",
    "tr",
    "rh",
    "v",
    "wbgt",
    "heat_index",
    "age",
    "weight",
    "height",
    "bmi",
    "met_w_m2",
    "clo",
    "acclimatized",
    "hours_worked",
    "water_loss_g",
    "hr_estimated",
    "activity_enc",
    "hydration_enc",
    "zone_enc",
]

ACTIVITY_MAP = {"light": 0, "moderate": 1, "heavy": 2, "very_heavy": 3}
HYDRATION_MAP = {"well": 0, "mild": 1, "dehydrated": 2, "severe": 2}
ZONE_ENC = {"Highland": 0, "Hot_Humid": 1, "Semi_Arid": 2, "Composite": 3, "Hot_Dry": 4}
MET_MAP = {"light": 65.0, "moderate": 130.0, "heavy": 200.0, "very_heavy": 260.0}

RISK_CONFIG = {
    0: {
        "label": "LOW",
        "color": "green",
        "action": "Safe to continue. Drink water every 20 minutes.",
        "notify_supervisor": False,
        "trigger_emergency": False,
    },
    1: {
        "label": "MODERATE",
        "color": "yellow",
        "action": "Take a 10-minute shade break. Drink 500ml water now.",
        "notify_supervisor": False,
        "trigger_emergency": False,
    },
    2: {
        "label": "HIGH",
        "color": "orange",
        "action": "STOP WORK. Rest in shade. Supervisor has been notified.",
        "notify_supervisor": True,
        "trigger_emergency": False,
    },
    3: {
        "label": "CRITICAL",
        "color": "red",
        "action": "EMERGENCY. Move to cool area. Medical help needed.",
        "notify_supervisor": True,
        "trigger_emergency": True,
    },
}


def build_feature_vector(
    tdb: float,
    tr: float,
    rh: float,
    v: float,
    wbgt: float,
    heat_index: float,
    age: int,
    weight: float,
    height: float,
    activity_level: str,
    acclimatized: bool,
    hydration_status: str,
    hours_worked: float,
    climate_zone: str,
    hr_bpm: float = None,
) -> np.ndarray:
    height_m = height / 100.0
    bmi = weight / (height_m**2)
    met_w_m2 = MET_MAP.get(activity_level, 130.0)
    clo = 0.5  # default standard work clothes

    # Estimate water loss proxy - not measured, use PHS approximate
    water_loss_g = met_w_m2 * hours_worked * 0.8

    # HR estimate if not provided by sensor
    if hr_bpm is None:
        hr_bpm = 70.0 + (met_w_m2 / 260.0) * 50.0 + (wbgt - 25.0) * 1.5
        hr_bpm += hours_worked * 3.0
        hr_bpm += {"well": 0, "mild": 5, "dehydrated": 12, "severe": 15}.get(hydration_status, 0)
        hr_bpm -= 8.0 if acclimatized else 0.0
        hr_bpm = float(np.clip(hr_bpm, 60.0, 180.0))

    vector = [
        tdb,
        tr,
        rh,
        v,
        wbgt,
        heat_index,
        float(age),
        weight,
        height,
        bmi,
        met_w_m2,
        clo,
        int(acclimatized),
        hours_worked,
        water_loss_g,
        hr_bpm,
        ACTIVITY_MAP.get(activity_level, 1),
        HYDRATION_MAP.get(hydration_status, 1),
        ZONE_ENC.get(climate_zone, 2),
    ]
    return np.array(vector).reshape(1, -1)


def predict_risk(feature_vector: np.ndarray) -> dict:
    proba = model.predict_proba(feature_vector)[0]
    # Base model score from class probabilities.
    model_score = float(proba[0] * 10 + proba[1] * 40 + proba[2] * 70 + proba[3] * 100)

    # Heuristic stress score (0-100) to avoid binary jumps when model is overconfident.
    tdb = float(feature_vector[0, 0])
    rh = float(feature_vector[0, 2])
    wbgt = float(feature_vector[0, 4])
    hours_worked = float(feature_vector[0, 13])
    hr_bpm = float(feature_vector[0, 15])
    activity_enc = float(feature_vector[0, 16])
    hydration_enc = float(feature_vector[0, 17])
    acclimatized = float(feature_vector[0, 12])

    def _clip01(x: float) -> float:
        return float(np.clip(x, 0.0, 1.0))

    temp_factor = _clip01((tdb - 24.0) / 16.0)
    wbgt_factor = _clip01((wbgt - 24.0) / 10.0)
    rh_factor = _clip01((rh - 30.0) / 60.0)
    hours_factor = _clip01(hours_worked / 8.0)
    hr_factor = _clip01((hr_bpm - 70.0) / 100.0)
    activity_factor = _clip01(activity_enc / 3.0)
    hydration_factor = _clip01(hydration_enc / 2.0)
    accl_penalty = 0.0 if acclimatized >= 0.5 else 0.12

    heuristic_score = 100.0 * (
        0.18 * temp_factor
        + 0.20 * wbgt_factor
        + 0.08 * rh_factor
        + 0.14 * hours_factor
        + 0.18 * hr_factor
        + 0.10 * activity_factor
        + 0.12 * hydration_factor
        + accl_penalty
    )

    risk_score = round(float(np.clip(0.55 * model_score + 0.45 * heuristic_score, 0.0, 100.0)), 1)

    if risk_score < 25:
        risk_int = 0
    elif risk_score < 50:
        risk_int = 1
    elif risk_score < 97:
        risk_int = 2
    else:
        risk_int = 3

    config = RISK_CONFIG[risk_int]

    # Time to danger estimate
    remaining_map = {0: ">60 min", 1: "30-60 min", 2: "0-30 min", 3: "Limit exceeded"}
    time_to_danger = remaining_map[risk_int]

    return {
        "risk_score": risk_score,
        "risk_label": config["label"],
        "risk_label_int": risk_int,
        "alert_color": config["color"],
        "action_message": config["action"],
        "time_to_danger": time_to_danger,
        "notify_supervisor": config["notify_supervisor"],
        "trigger_emergency": config["trigger_emergency"],
        "probabilities": {
            "LOW": round(float(proba[0]), 4),
            "MODERATE": round(float(proba[1]), 4),
            "HIGH": round(float(proba[2]), 4),
            "CRITICAL": round(float(proba[3]), 4),
        },
    }
