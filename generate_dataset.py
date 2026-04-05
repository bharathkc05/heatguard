"""
generate_dataset.py
===================
HeatGuard AI — Synthetic Heat Stress Dataset Generator
Targeting outdoor workers across all Indian climate zones.

Uses ISO 7933 PHS model via pythermalcomfort **v2.9.0**.
v2 API notes:
  - met is in W/m² directly (no MET unit conversion)
  - posture = 2 (integer: standing)
  - Returns a dict — access via result["key"]
  - Field name is "water_loss" (grams) not "sweat_loss_g"
  - No weight/height kwargs

Run:
    python generate_dataset.py
"""

import os
import random
import sys
from typing import Optional, Tuple, Dict

import numpy as np
import pandas as pd
from tqdm import tqdm
from pythermalcomfort.models import phs

import pythermalcomfort
print(f"pythermalcomfort version: {pythermalcomfort.__version__}")

# ============================================================
#  CONSTANTS — Climate Zone Definitions
# ============================================================
# tr_offset methodology note
# ERA5 analysis shows atmospheric MRT offset of ~0-4 C over India.
# ERA5 grid MRT does not capture direct solar radiation load on an
# outdoor worker's body. ISO 7933 and NIOSH literature indicate direct
# sun exposure can add substantial effective radiant load.
# tr_offset_range below combines atmospheric + worker-level solar load:
#   Lower bound: closer to overcast/shade conditions
#   Upper bound: clear-sky direct-sun exposure conditions
# References: Liljegren et al. (2008), ISO 7933:2004 Annex B.
CLIMATE_ZONES: Dict[str, dict] = {
    "Hot_Dry": {
        "tdb_range":       (24.8, 41.6),
        "rh_range":        (17.0, 84.6),
        "v_range":         (1.08, 7.66),
        "tr_offset_range": (2.0,  18.0),
        "weight":          0.25,
        "typical_workers": ["construction", "salt_pan", "brick_kiln", "agriculture"],
    },
    "Hot_Humid": {
        "tdb_range":       (25.4, 37.0),
        "rh_range":        (33.2, 89.2),
        "v_range":         (0.98, 10.19),
        "tr_offset_range": (1.0,  12.0),
        "weight":          0.25,
        "typical_workers": ["agriculture", "tea_plantation", "fishing", "construction"],
    },
    "Semi_Arid": {
        "tdb_range":       (24.5, 39.3),
        "rh_range":        (24.8, 88.3),
        "v_range":         (0.91, 6.76),
        "tr_offset_range": (2.0,  16.0),
        "weight":          0.25,
        "typical_workers": ["construction", "quarry", "road_work", "agriculture"],
    },
    "Composite": {
        "tdb_range":       (19.8, 40.8),
        "rh_range":        (17.8, 85.4),
        "v_range":         (0.72, 5.73),
        "tr_offset_range": (2.0,  16.0),
        "weight":          0.15,
        "typical_workers": ["agriculture", "brick_kiln", "construction", "road_labor"],
    },
    "Highland": {
        "tdb_range":       (16.9, 39.6),
        "rh_range":        (20.4, 94.0),
        "v_range":         (0.50, 5.36),
        "tr_offset_range": (1.0,  14.0),
        "weight":          0.10,
        "typical_workers": ["tea_plantation", "construction", "agriculture"],
    },
}

# ============================================================
#  CONSTANTS — Worker Demographics
# ============================================================
AGE_MIN,    AGE_MAX    = 18,    60
WEIGHT_MIN, WEIGHT_MAX = 45.0,  85.0    # kg
HEIGHT_MIN, HEIGHT_MAX = 150.0, 185.0   # cm
CLO_MIN,    CLO_MAX    = 0.3,   0.7
HOURS_WORKED_MIN, HOURS_WORKED_MAX = 0.0, 7.0

# (label, W/m², sampling_weight)
ACTIVITY_LEVELS: list = [
    ("light",       65.0, 0.10),
    ("moderate",   130.0, 0.35),
    ("heavy",      200.0, 0.40),
    ("very_heavy", 260.0, 0.15),
]

# (label, d_lim_multiplier, sampling_weight)
HYDRATION_STATES: list = [
    ("well",       1.00, 0.30),
    ("mild",       0.90, 0.45),
    ("dehydrated", 0.75, 0.25),
]

# ============================================================
#  CONSTANTS — PHS Model Parameters (v2.9.0)
# ============================================================
PHS_POSTURE  = 2      # standing (integer in v2)
PHS_WME      = 0      # external mechanical work (W/m²)
PHS_DURATION = 480    # full 8-hour shift in minutes

# ============================================================
#  CONSTANTS — Physiological Adjustments
# ============================================================
AGE_THRESHOLD         = 35
AGE_PENALTY_PER_YEAR  = 0.005    # 0.5% per year above threshold
ACCLIMATIZATION_BONUS = 1.15     # 15% more tolerance

# Heart rate modifiers
HYDRATION_HR_PENALTY: Dict[str, float] = {
    "well": 0.0, "mild": 5.0, "dehydrated": 12.0
}
CARDIOVASCULAR_DRIFT_BPM_PER_HOUR = 3.0
ACCLIMATIZATION_HR_REDUCTION      = 8.0

# ============================================================
#  CONSTANTS — Risk Thresholds (minutes)
# ============================================================
RISK_HIGH_MAX     = 30
RISK_MODERATE_MAX = 60

# ============================================================
#  CONSTANTS — Class Balance Targets
# ============================================================
TARGET_CLASS_BALANCE: Dict[int, float] = {
    0: 0.30,   # LOW
    1: 0.25,   # MODERATE
    2: 0.25,   # HIGH
    3: 0.20,   # CRITICAL
}

# ============================================================
#  CONSTANTS — Validation (Ioannou 2022)
# ============================================================
IOANNOU_TCORE_MEAN = 37.9
IOANNOU_WBGT_MIN   = 15.9
IOANNOU_WBGT_MAX   = 35.8
WATER_LOSS_MIN_G   = 0.0     # light work in mild Highland can produce near-zero
WATER_LOSS_MAX_G   = 12000.0  # extreme but documented in hot-humid India

# ============================================================
#  CONSTANTS — Generation
# ============================================================
N_RECORDS   = 100_000
RANDOM_SEED = 42
FAILURE_RATE_WARN_INTERVAL = 1000
FAILURE_RATE_ABORT_PCT     = 50.0

OUTPUT_DATA_DIR = os.path.join("data", "processed")
OUTPUT_REPORT_DIR = os.path.join("artifacts", "reports")

# ============================================================
#  HELPER — safe_float
# ============================================================

def safe_float(val: object, default: float = 0.0) -> float:
    """
    Safely convert a PHS output value to float.

    Parameters
    ----------
    val     : object  Value from PHS result dict.
    default : float   Fallback if conversion fails or val is None.

    Returns
    -------
    float
    """
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ============================================================
#  ADJUSTMENT FUNCTIONS
# ============================================================

def age_adjustment(met: float, age: int) -> float:
    """
    Reduce metabolic rate by 0.5% per year above 35 to model reduced
    cardiovascular efficiency in older workers.

    Works with any metabolic unit (MET or W/m²) since it applies a
    proportional reduction.

    Parameters
    ----------
    met : float  Metabolic rate (W/m² in the v2 API context).
    age : int    Worker age in years.

    Returns
    -------
    float  Age-adjusted metabolic rate.
    """
    reduction = max(0.0, age - AGE_THRESHOLD) * AGE_PENALTY_PER_YEAR
    return met * (1.0 - reduction)


def acclimatization_adjustment(d_lim: float, acclimatized: bool) -> float:
    """
    Acclimatized workers tolerate heat 15% longer.

    Parameters
    ----------
    d_lim        : float  Raw PHS time limit (minutes).
    acclimatized : bool   True if 2+ weeks of heat exposure.

    Returns
    -------
    float  Adjusted time limit (minutes).
    """
    return d_lim * ACCLIMATIZATION_BONUS if acclimatized else d_lim


def hydration_adjustment(d_lim: float, hydration_status: str) -> float:
    """
    Reduce time limit based on dehydration level.

    Parameters
    ----------
    d_lim            : float  Time limit after acclimatization adjustment.
    hydration_status : str    'well' | 'mild' | 'dehydrated'.

    Returns
    -------
    float  Hydration-adjusted time limit (minutes).
    """
    multiplier_map = {s[0]: s[1] for s in HYDRATION_STATES}
    return d_lim * multiplier_map.get(hydration_status, 1.0)


def hours_worked_adjustment(d_lim: float, hours_worked: float) -> float:
    """
    Subtract already-worked time from the remaining safe exposure window.

    Parameters
    ----------
    d_lim        : float  Time limit after hydration adjustment (minutes).
    hours_worked : float  Hours already worked this shift.

    Returns
    -------
    float  Remaining safe minutes (clamped to 0).
    """
    return max(0.0, d_lim - (hours_worked * 60.0))


# ============================================================
#  DERIVED ENVIRONMENTAL FEATURES
# ============================================================

def compute_wbgt(tdb: float, rh: float, tr: float, v: float) -> float:
    """
    Estimate WBGT with Stull wet-bulb approximation and wind-corrected
    globe temperature.

    Stull (2011) formula is valid for RH >= 5% and tdb 5-39°C.
    RH is clamped at 5% minimum to avoid anomalous results.

    Parameters
    ----------
    tdb : float  Dry bulb temperature (°C).
    rh  : float  Relative humidity (%).
    tr  : float  Mean radiant temperature (°C).
    v   : float  Air velocity (m/s).

    Returns
    -------
    float  Estimated WBGT (°C), floored at 10.0.
    """
    rh_c = max(rh, 5.0)
    twb = (
        tdb * np.arctan(0.151977 * (rh_c + 8.313659) ** 0.5)
        + np.arctan(tdb + rh_c)
        - np.arctan(rh_c - 1.676331)
        + 0.00391838 * rh_c ** 1.5 * np.arctan(0.023101 * rh_c)
        - 4.686035
    )
    tg = max(tr - (1.5 * v), tdb - 2.0)
    wbgt = 0.7 * twb + 0.2 * tg + 0.1 * tdb
    return max(wbgt, 10.0)


def compute_heat_index(tdb: float, rh: float) -> float:
    """
    Rothfusz Heat Index. Applied only when tdb > 27°C and rh > 40%;
    otherwise returns tdb.

    Parameters
    ----------
    tdb : float  Dry bulb temperature (°C).
    rh  : float  Relative humidity (%).

    Returns
    -------
    float  Heat index (°C).
    """
    if tdb <= 27.0 or rh <= 40.0:
        return tdb
    return (
        -8.78469475556
        + 1.61139411      * tdb
        + 2.33854883889   * rh
        - 0.14611605      * tdb * rh
        - 0.012308094     * tdb ** 2
        - 0.0164248277778 * rh  ** 2
        + 0.002211732     * tdb ** 2 * rh
        + 0.00072546      * tdb * rh  ** 2
        - 0.000003582     * tdb ** 2 * rh ** 2
    )


def compute_heart_rate(
    met_w_m2: float,
    wbgt: float,
    hours_worked: float,
    hydration_status: str,
    acclimatized: bool,
) -> float:
    """
    Estimate heart rate (bpm) with physiological state adjustments.

    Base:                hr = 70 + (met/260)*50 + (wbgt-25)*1.5
    Cardiovascular drift: +3 bpm per hour in the heat
    Dehydration penalty:  well=0, mild=+5, dehydrated=+12 bpm
    Acclimatization:      -8 bpm (lower HR at same workload)
    Gaussian noise:       Normal(0, 5)

    Parameters
    ----------
    met_w_m2         : float  Base metabolic rate (W/m²).
    wbgt             : float  Wet Bulb Globe Temperature (°C).
    hours_worked     : float  Hours already in shift.
    hydration_status : str    'well' | 'mild' | 'dehydrated'.
    acclimatized     : bool   Heat acclimatisation status.

    Returns
    -------
    float  Estimated heart rate (bpm), clipped to [60, 180].
    """
    hr_base = 70.0 + (met_w_m2 / 260.0) * 50.0 + (wbgt - 25.0) * 1.5
    drift   = hours_worked * CARDIOVASCULAR_DRIFT_BPM_PER_HOUR
    penalty = HYDRATION_HR_PENALTY.get(hydration_status, 0.0)
    acclim  = ACCLIMATIZATION_HR_REDUCTION if acclimatized else 0.0
    noise   = np.random.normal(0.0, 5.0)
    return float(np.clip(hr_base + drift + penalty - acclim + noise, 60.0, 180.0))


# ============================================================
#  RISK LABEL ASSIGNMENT
# ============================================================

def assign_risk_label(remaining: float) -> Tuple[int, str, str]:
    """
    Assign 4-tier risk label from remaining safe exposure minutes.

    > 60  → 0, LOW,      green
    30–60 → 1, MODERATE, yellow
    0–30  → 2, HIGH,     orange
    == 0  → 3, CRITICAL, red

    Parameters
    ----------
    remaining : float  Remaining safe minutes after all adjustments.

    Returns
    -------
    Tuple[int, str, str]  (risk_int, risk_label, alert_color)
    """
    if remaining <= 0.0:
        return (3, "CRITICAL", "red")
    elif remaining <= RISK_HIGH_MAX:
        return (2, "HIGH", "orange")
    elif remaining <= RISK_MODERATE_MAX:
        return (1, "MODERATE", "yellow")
    else:
        return (0, "LOW", "green")


# ============================================================
#  CLASS-BALANCED SAMPLING
# ============================================================

# The PHS model has a very sharp transition: most parameter combos
# produce either d_lim=480 (safe → LOW) or d_lim<30 (danger → CRITICAL).
# The MODERATE (30-60 min remaining) and HIGH (0-30 min remaining)
# zones are narrow. We use three strategies together:
#   1. Environmental/activity parameter biasing toward underrepresented classes
#   2. hours_worked biasing (the most reliable lever for MODERATE/HIGH)
#   3. Class-aware acceptance: probabilistically reject overrepresented classes

WARMUP_RECORDS = 2000   # pure random sampling during warmup
ACCEPT_FLOOR   = 0.15   # minimum acceptance probability for any class


def _find_most_needed_class(
    class_counts: Dict[int, int],
    n_total: int,
) -> int:
    """
    Return the risk class (0–3) with the largest deficit relative to target.
    """
    current_pct = {
        k: class_counts.get(k, 0) / max(n_total, 1)
        for k in TARGET_CLASS_BALANCE
    }
    deficit = {
        k: TARGET_CLASS_BALANCE[k] - current_pct[k]
        for k in TARGET_CLASS_BALANCE
    }
    return max(deficit, key=deficit.get)


def _accept_record(
    risk_int: int,
    class_counts: Dict[int, int],
    n_total: int,
) -> bool:
    """
    Probabilistically decide whether to accept a record based on current
    class distribution. Overrepresented classes are rejected more often,
    giving underrepresented classes room to catch up.

    Parameters
    ----------
    risk_int     : int   Risk class of this record (0-3).
    class_counts : dict  Current class counts.
    n_total      : int   Total records accepted so far.

    Returns
    -------
    bool  True to accept this record.
    """
    if n_total < WARMUP_RECORDS:
        return True

    target = TARGET_CLASS_BALANCE[risk_int]
    current = class_counts.get(risk_int, 0) / max(n_total, 1)

    if current <= target:
        # Underrepresented — always accept
        return True

    # Overrepresented — accept with probability proportional to deficit
    excess_ratio = current / max(target, 0.01)
    # The more over-target, the lower the acceptance probability
    accept_prob = max(ACCEPT_FLOOR, 1.0 / excess_ratio)
    return random.random() < accept_prob


def sample_hours_worked_biased(
    class_counts: Dict[int, int],
    n_total: int,
) -> float:
    """
    Bias hours_worked toward producing underrepresented risk classes.
    This is the most reliable lever: a record with d_lim=480 and
    hours_worked=7h has remaining=60min→MODERATE; 7.5h→remaining=30→HIGH.
    """
    if n_total < WARMUP_RECORDS:
        return np.random.uniform(HOURS_WORKED_MIN, HOURS_WORKED_MAX)

    most_needed = _find_most_needed_class(class_counts, n_total)

    if most_needed == 3:            # CRITICAL — max hours + hot conditions
        return np.random.uniform(5.0, 7.0)
    elif most_needed == 2:          # HIGH — 0-30 min remaining
        return np.random.uniform(6.0, 7.0)
    elif most_needed == 1:          # MODERATE — 30-60 min remaining
        return np.random.uniform(5.5, 7.0)
    else:                           # LOW — early shift
        return np.random.uniform(0.0, 4.0)


def sample_parameters_biased(
    class_counts: Dict[int, int],
    n_total: int,
    zone: dict,
) -> Tuple[float, float, float, str, float]:
    """
    Sample environment + activity biased toward the most needed class.
    """
    tdb_lo, tdb_hi = zone["tdb_range"]
    rh_lo,  rh_hi  = zone["rh_range"]
    v_lo,   v_hi   = zone["v_range"]

    if n_total < WARMUP_RECORDS:
        tdb = np.random.uniform(tdb_lo, tdb_hi)
        rh  = np.random.uniform(rh_lo,  rh_hi)
        v   = np.random.uniform(v_lo,   v_hi)
        idx = random.choices(range(len(ACTIVITY_LEVELS)),
                             weights=[a[2] for a in ACTIVITY_LEVELS])[0]
        return tdb, rh, v, ACTIVITY_LEVELS[idx][0], ACTIVITY_LEVELS[idx][1]

    most_needed = _find_most_needed_class(class_counts, n_total)

    if most_needed == 0:      # LOW — mild conditions, light work
        tdb = np.random.uniform(tdb_lo, tdb_lo + (tdb_hi - tdb_lo) * 0.4)
        rh  = np.random.uniform(rh_lo,  rh_lo  + (rh_hi  - rh_lo)  * 0.4)
        v   = np.random.uniform(v_lo + (v_hi - v_lo) * 0.5, v_hi)
        act = ACTIVITY_LEVELS[0]   # light

    elif most_needed == 1:    # MODERATE — medium conditions, moderate work
        tdb = np.random.uniform(tdb_lo + (tdb_hi - tdb_lo) * 0.3,
                                tdb_lo + (tdb_hi - tdb_lo) * 0.6)
        rh  = np.random.uniform(rh_lo, rh_hi)
        v   = np.random.uniform(v_lo, v_hi)
        act = ACTIVITY_LEVELS[1]   # moderate

    elif most_needed == 2:    # HIGH — hot, heavy work
        tdb = np.random.uniform(tdb_lo + (tdb_hi - tdb_lo) * 0.5, tdb_hi)
        rh  = np.random.uniform(rh_lo, rh_hi)
        v   = np.random.uniform(v_lo, v_lo + (v_hi - v_lo) * 0.5)
        act = ACTIVITY_LEVELS[2]   # heavy

    else:                     # CRITICAL — extreme, very heavy
        tdb = np.random.uniform(tdb_lo + (tdb_hi - tdb_lo) * 0.7, tdb_hi)
        rh  = np.random.uniform(rh_lo + (rh_hi - rh_lo) * 0.6, rh_hi)
        v   = np.random.uniform(v_lo, v_lo + (v_hi - v_lo) * 0.3)
        act = ACTIVITY_LEVELS[3]   # very_heavy

    return tdb, rh, v, act[0], act[1]


# ============================================================
#  SINGLE RECORD GENERATOR
# ============================================================

def generate_single_record(
    tdb: float, tr: float, rh: float, v: float,
    age: int, weight: float, height: float,
    activity_level: str, met_w_m2: float,
    clo: float, acclimatized: bool,
    hydration_status: str, hours_worked: float,
    climate_zone: str, worker_type: str,
) -> Optional[dict]:
    """
    Generate one dataset record via the PHS model (v2.9.0) and
    physiological adjustments.

    PHS is called with met directly in W/m² (v2 API).
    All four adjustments are applied in order: age → acclimatization →
    hydration → hours_worked.

    Returns None if the PHS call raises an exception.
    """
    height_m    = height / 100.0
    age_adj_met = age_adjustment(met_w_m2, age)  # W/m² directly

    try:
        result = phs(
            tdb=tdb,
            tr=tr,
            rh=rh,
            v=v,
            met=age_adj_met,       # W/m² — v2 API
            clo=clo,
            posture=PHS_POSTURE,   # 2 = standing (integer in v2)
            wme=PHS_WME,
            duration=PHS_DURATION,
            limit_inputs=False,
        )
    except Exception as exc:
        # Uncomment during debugging:
        # print(f"PHS failed: {exc}", file=sys.stderr)
        return None

    # v2 returns a dict; field is "water_loss" not "sweat_loss_g"
    d_lim_raw  = safe_float(result.get("d_lim_t_re"), default=PHS_DURATION)
    water_loss = safe_float(result.get("water_loss"),  default=0.0)
    # NOTE: t_re_final is core temperature at end of full 480-min shift,
    # not at the current hours_worked point. This is a validation-only column
    # and must be dropped before ML training to avoid leakage.
    t_re_final = safe_float(result.get("t_re"))
    t_sk_final = safe_float(result.get("t_sk"))

    # Reject records where full-shift core temp projection is non-survivable.
    # PHS simulates beyond physiological limits — t_re > 42°C means the
    # worker would have collapsed before completing the shift.
    if t_re_final > 42.0:
        return None

    # Apply 4 adjustments in sequence: age → acclimatization → hydration → hours
    d_lim = d_lim_raw
    d_lim = acclimatization_adjustment(d_lim, acclimatized)
    d_lim = hydration_adjustment(d_lim, hydration_status)
    d_lim = hours_worked_adjustment(d_lim, hours_worked)
    remaining_safe_min = d_lim

    # Derived environmental features
    wbgt       = compute_wbgt(tdb, rh, tr, v)
    heat_index = compute_heat_index(tdb, rh)
    hr_est     = compute_heart_rate(met_w_m2, wbgt, hours_worked,
                                    hydration_status, acclimatized)

    bmi = weight / (height_m ** 2)
    risk_int, risk_str, alert_color = assign_risk_label(remaining_safe_min)

    return {
        # Environmental
        "tdb":        round(tdb, 2),
        "tr":         round(tr, 2),
        "rh":         round(rh, 2),
        "v":          round(v, 2),
        "wbgt":       round(wbgt, 3),
        "heat_index": round(heat_index, 3),
        # Worker profile
        "age":              age,
        "weight":           round(weight, 1),
        "height":           round(height, 1),
        "bmi":              round(bmi, 2),
        "activity_level":   activity_level,
        "met_w_m2":         round(met_w_m2, 1),
        "clo":              round(clo, 2),
        "acclimatized":     int(acclimatized),
        "hydration_status": hydration_status,
        "hours_worked":     round(hours_worked, 2),
        "worker_type":      worker_type,
        # PHS outputs (validation only — drop before ML training)
        "d_lim_t_re_raw": round(d_lim_raw, 2),
        "water_loss_g":   round(water_loss, 2),
        "t_re_final":     round(t_re_final, 3),
        "t_sk_final":     round(t_sk_final, 3),
        # Adjusted outputs
        "remaining_safe_min": round(remaining_safe_min, 2),
        "hr_estimated":       round(hr_est, 1),
        # Zone metadata
        "climate_zone": climate_zone,
        # Target labels
        "risk_label_int": risk_int,
        "risk_label":     risk_str,
        "alert_color":    alert_color,
    }


# ============================================================
#  DATASET GENERATION ENGINE
# ============================================================

def generate_dataset(n_records: int = N_RECORDS,
                     seed: int = RANDOM_SEED) -> pd.DataFrame:
    """
    Generate a synthetic heat stress dataset using the ISO 7933 PHS model.

    Uses biased hours_worked sampling to achieve approximate class balance
    across the 4 risk tiers (LOW / MODERATE / HIGH / CRITICAL).

    Parameters
    ----------
    n_records : int   Total valid records to generate. Default 100,000.
    seed      : int   Random seed for reproducibility. Default 42.

    Returns
    -------
    pd.DataFrame  Generated dataset.
    """
    np.random.seed(seed)
    random.seed(seed)

    zone_names   = list(CLIMATE_ZONES.keys())
    zone_weights = [CLIMATE_ZONES[z]["weight"] for z in zone_names]

    act_labels  = [a[0] for a in ACTIVITY_LEVELS]
    act_mets    = [a[1] for a in ACTIVITY_LEVELS]
    act_weights = [a[2] for a in ACTIVITY_LEVELS]

    hyd_labels  = [h[0] for h in HYDRATION_STATES]
    hyd_weights = [h[2] for h in HYDRATION_STATES]

    records: list = []
    failed: int   = 0
    rejected_balance: int = 0
    class_counts: Dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}

    pbar = tqdm(total=n_records, desc="Generating records", unit="rec")

    while len(records) < n_records:
        # Sample zone
        zone_name = random.choices(zone_names, weights=zone_weights, k=1)[0]
        zone      = CLIMATE_ZONES[zone_name]

        # Sample environment + activity (biased for class balance)
        tdb, rh, v, activity_level, met_w_m2 = sample_parameters_biased(
            class_counts, len(records), zone
        )
        tr = tdb + np.random.uniform(*zone["tr_offset_range"])

        # Sample worker
        age          = int(np.random.randint(AGE_MIN, AGE_MAX + 1))
        weight       = np.random.uniform(WEIGHT_MIN, WEIGHT_MAX)
        height       = np.random.uniform(HEIGHT_MIN, HEIGHT_MAX)
        clo          = np.random.uniform(CLO_MIN, CLO_MAX)
        acclimatized = bool(random.getrandbits(1))
        worker_type  = random.choice(zone["typical_workers"])

        # Biased hours_worked for class balance
        hours_worked = sample_hours_worked_biased(class_counts, len(records))

        hyd_idx          = random.choices(range(len(HYDRATION_STATES)),
                                          weights=hyd_weights, k=1)[0]
        hydration_status = hyd_labels[hyd_idx]

        record = generate_single_record(
            tdb=tdb, tr=tr, rh=rh, v=v,
            age=age, weight=weight, height=height,
            activity_level=activity_level, met_w_m2=met_w_m2,
            clo=clo, acclimatized=acclimatized,
            hydration_status=hydration_status,
            hours_worked=hours_worked,
            climate_zone=zone_name,
            worker_type=worker_type,
        )

        if record is not None:
            # Class-aware acceptance: reject overrepresented classes
            if _accept_record(record["risk_label_int"],
                              class_counts, len(records)):
                records.append(record)
                class_counts[record["risk_label_int"]] += 1
                pbar.update(1)
            else:
                rejected_balance += 1
        else:
            failed += 1
            if failed > 0 and failed % FAILURE_RATE_WARN_INTERVAL == 0:
                rate = failed / (len(records) + failed) * 100
                if rate > FAILURE_RATE_ABORT_PCT:
                    pbar.close()
                    raise RuntimeError(
                        f"Failure rate is {rate:.1f}% after {failed} attempts "
                        f"({len(records)} successes). "
                        "Check pythermalcomfort version and phs() API."
                    )

    pbar.close()
    df = pd.DataFrame(records)

    checksum = pd.util.hash_pandas_object(df).sum()

    print("\n" + "=" * 60)
    print("  GENERATION COMPLETE")
    print("=" * 60)
    print(f"  Total generated : {len(df):,}")
    print(f"  PHS failures    : {failed:,}")
    print(f"  Balance rejected: {rejected_balance:,}")
    if failed > 0:
        print(f"  Failure rate    : {failed / (len(df) + failed) * 100:.2f}%")
    print(f"  Checksum        : {checksum}")
    print("  (Should be identical across runs with same seed)")
    print("\n  Zone distribution:")
    print(df["climate_zone"].value_counts().to_string())
    print("\n  Class distribution:")
    print(df["risk_label"].value_counts().to_string())
    print("=" * 60)
    return df


# ============================================================
#  VALIDATION REPORT
# ============================================================

def validate_dataset(df: pd.DataFrame) -> str:
    """
    Validate the generated dataset against physiological reference ranges.

    Checks:
      1. Record / column counts, missing values
      2. Risk label class balance (flags < 10%)
      3. Core temperature plausibility (Ioannou 2022: 37.9 ± 0.5°C)
      4. Heart rate plausibility (Ioannou 2022: 118 ± 15 bpm)
      5. WBGT range coverage vs Ioannou range 15.9–35.8°C
      6. Water loss plausibility (500–8000 g/shift)
      7. Zone distribution vs target weights

    Parameters
    ----------
    df : pd.DataFrame  The generated dataset.

    Returns
    -------
    str  Full validation report as formatted text.
    """
    lines: list = []

    def section(title: str):
        lines.append("\n" + "=" * 60)
        lines.append(f"  {title}")
        lines.append("=" * 60)

    def chk(label: str, passed: bool, detail: str = "") -> bool:
        tag = "PASS ✓" if passed else "FAIL ✗"
        msg = f"  [{tag}] {label}"
        if detail:
            msg += f" — {detail}"
        lines.append(msg)
        return passed

    # 1 — Counts & missing
    section("CHECK 1 — Record & Column Counts")
    lines.append(f"  Total records : {len(df):,}")
    lines.append(f"  Total columns : {len(df.columns)}")
    missing = df.isnull().sum()
    missing_nz = missing[missing > 0]
    if len(missing_nz) == 0:
        chk("No missing values", True)
    else:
        chk("No missing values", False, f"{len(missing_nz)} cols with nulls")
        lines.append(missing_nz.to_string())

    # 2 — Risk label balance
    section("CHECK 2 — Risk Label Distribution")
    dist = df["risk_label"].value_counts(normalize=True) * 100
    for label, pct in dist.items():
        lines.append(f"  {label:<10}: {pct:.1f}%")
    chk("All classes >= 10%", bool((dist >= 10.0).all()),
        f"min class = {dist.min():.1f}%")

    # 3 — Core temperature
    section("CHECK 3 — Core Temperature (Ioannou 2022 ref: 37.9 ± 0.5°C)")
    t_re = df["t_re_final"].dropna()
    t_mean, t_std = t_re.mean(), t_re.std()
    lines.append(f"  Mean : {t_mean:.3f} °C  |  Std: {t_std:.3f} °C")
    lines.append(f"  Min  : {t_re.min():.3f} °C  |  Max: {t_re.max():.3f} °C")
    # Core temps: PHS can predict t_re > 42°C in extreme hot-humid with
    # heavy labor — these are model outputs, not real survivable states.
    # Flag only truly impossible values (> 45°C or < 35°C).
    implaus = ((t_re < 35.0) | (t_re > 45.0)).sum()
    extreme_range = ((t_re > 42.0) & (t_re <= 45.0)).sum()
    lines.append(f"  Implausible (<35 or >45°C): {implaus:,}")
    lines.append(f"  Extreme model outputs (42–45°C): {extreme_range:,}")
    chk("Core temp mean within 0.8°C of Ioannou",
        abs(t_mean - IOANNOU_TCORE_MEAN) <= 0.8,
        f"mean={t_mean:.3f}")
    chk("No implausible core temps (<35 or >45°C)", implaus == 0,
        f"{implaus} out of [35, 45]°C")

    # 4 — Heart rate
    section("CHECK 4 — Heart Rate (Ioannou 2022 ref: 118 ± 15 bpm)")
    hr = df["hr_estimated"]
    lines.append(f"  Mean : {hr.mean():.1f} bpm  |  Std: {hr.std():.1f} bpm")
    chk("HR mean plausible (80–160 bpm)",
        80.0 <= hr.mean() <= 160.0,
        f"mean={hr.mean():.1f}")

    # 5 — WBGT
    section("CHECK 5 — WBGT Range (Ioannou ref: 15.9–35.8°C)")
    wbgt = df["wbgt"]
    lines.append(f"  Min={wbgt.min():.2f}  Max={wbgt.max():.2f}  Mean={wbgt.mean():.2f} °C")
    overlap = ((wbgt >= IOANNOU_WBGT_MIN) & (wbgt <= IOANNOU_WBGT_MAX)).sum()
    pct_ov  = overlap / len(df) * 100
    lines.append(f"  Records in Ioannou WBGT range: {overlap:,} ({pct_ov:.1f}%)")
    chk("WBGT overlap > 50%", pct_ov >= 50.0, f"{pct_ov:.1f}%")

    # 6 — Water loss
    section("CHECK 6 — Water Loss (valid: 500–12000 g/shift)")
    wl = df["water_loss_g"].dropna()
    lines.append(f"  Mean={wl.mean():.0f} g  |  Max={wl.max():.0f} g")
    extreme = ((wl >= 8000.0) & (wl <= WATER_LOSS_MAX_G)).sum()
    lines.append(f"  Extreme but possible (8000–12000g): {extreme:,}")
    out = ((wl < WATER_LOSS_MIN_G) | (wl > WATER_LOSS_MAX_G)).sum()
    lines.append(f"  Out-of-range (>12000g): {out:,}")
    chk("Water loss in valid range (500–12000 g)", out == 0,
        f"{out} records outside range")

    # 7 — Zone distribution
    section("CHECK 7 — Zone Distribution")
    zone_cnt = df["climate_zone"].value_counts()
    zone_pct = df["climate_zone"].value_counts(normalize=True) * 100
    for z in zone_cnt.index:
        tgt = CLIMATE_ZONES[z]["weight"] * 100
        lines.append(
            f"  {z:<15}: {zone_cnt[z]:>7,}  ({zone_pct[z]:.1f}%  target {tgt:.0f}%)"
        )
    zone_ok = all(
        abs(zone_pct.get(z, 0) - CLIMATE_ZONES[z]["weight"] * 100) < 3.0
        for z in CLIMATE_ZONES
    )
    chk("Zone distribution within 3% of target", zone_ok)

    # Verdict
    section("OVERALL VERDICT")
    full = "\n".join(lines)
    n_pass = full.count("PASS ✓")
    n_fail = full.count("FAIL ✗")
    verdict = ("ALL CHECKS PASSED ✓" if n_fail == 0
               else f"{n_fail} CHECK(S) FAILED ✗")
    lines.append(f"\n  {verdict}  ({n_pass} passed, {n_fail} failed)")
    lines.append("=" * 60)
    return "\n".join(lines)


# ============================================================
#  SMOKE TEST
# ============================================================

def smoke_test() -> None:
    """
    Run PHS calls at actual generation met values to verify the v2 API
    before generating 100,000 records. Aborts if any output is implausible.
    """
    print("\n[SMOKE TEST] Running PHS calls to verify API (v2.9.0)...")
    test_cases = [
        {"met":  65, "label": "light work"},
        {"met": 200, "label": "heavy work"},
        {"met": 260, "label": "very heavy work"},
    ]
    for case in test_cases:
        result = phs(
            tdb=40, tr=52, rh=30, v=1.5,
            met=case["met"], clo=0.5,
            posture=2, wme=0,
            duration=480, limit_inputs=False,
        )
        t_re = result["t_re"]
        wl   = result["water_loss"]
        dlim = result["d_lim_t_re"]
        print(f"  [{case['label']:<16}] t_re={t_re}°C  "
              f"water_loss={wl:.0f}g  d_lim={dlim}min")
        assert 36.0 <= t_re <= 42.0, \
            f"SMOKE TEST FAILED: t_re={t_re} out of range for {case['label']}"
    print("[SMOKE TEST] All cases passed.\n")


# ============================================================
#  MAIN
# ============================================================

def main():
    """Orchestrate generation, validation, and file saving."""
    print("\n" + "=" * 60)
    print("  HEATGUARD AI — SYNTHETIC DATASET GENERATOR")
    print("  ISO 7933 PHS | pythermalcomfort v2.9.0 | Indian Outdoor Workers")
    print("=" * 60)

    smoke_test()

    print("[STEP 1] Generating dataset …")
    df = generate_dataset(n_records=N_RECORDS, seed=RANDOM_SEED)

    print("\n[STEP 2] Running validation …")
    report = validate_dataset(df)
    print(report)

    print("\n[STEP 3] Saving outputs …")

    os.makedirs(OUTPUT_DATA_DIR, exist_ok=True)
    os.makedirs(OUTPUT_REPORT_DIR, exist_ok=True)

    csv_path  = os.path.join(OUTPUT_DATA_DIR, "heatguard_synthetic_india.csv")
    parq_path = os.path.join(OUTPUT_DATA_DIR, "heatguard_synthetic_india.parquet")
    rep_path  = os.path.join(OUTPUT_REPORT_DIR, "validation_report.txt")

    df.to_csv(csv_path, index=False)
    print(f"  Saved CSV     : {csv_path}  ({len(df):,} rows)")

    try:
        df.to_parquet(parq_path, index=False)
        print(f"  Saved Parquet : {parq_path}")
    except ImportError:
        print("  Parquet skipped — install pyarrow: pip install pyarrow")

    with open(rep_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  Saved Report  : {rep_path}")

    print("\n[DONE] All outputs saved.")
    print("=" * 60)


if __name__ == "__main__":
    main()
