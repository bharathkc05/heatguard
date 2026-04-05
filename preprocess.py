import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
import joblib
from pathlib import Path


DATA_PROCESSED_DIR = Path("data") / "processed"
DATASET_PATH = DATA_PROCESSED_DIR / "heatguard_synthetic_india.parquet"
SPLITS_PATH = DATA_PROCESSED_DIR / "data_splits.pkl"


def main() -> None:
    df = pd.read_parquet(DATASET_PATH)

    # Drop leakage columns
    leakage = [
        "remaining_safe_min",
        "d_lim_t_re_raw",
        "t_re_final",
        "t_sk_final",
        "risk_label",
        "alert_color",
    ]
    df = df.drop(columns=leakage)

    # Encode categoricals
    df["activity_enc"] = df["activity_level"].map(
        {"light": 0, "moderate": 1, "heavy": 2, "very_heavy": 3}
    )
    df["hydration_enc"] = df["hydration_status"].map(
        {"well": 0, "mild": 1, "dehydrated": 2}
    )
    df["zone_enc"] = df["climate_zone"].map(
        {"Highland": 0, "Hot_Humid": 1, "Semi_Arid": 2, "Composite": 3, "Hot_Dry": 4}
    )

    df = df.drop(columns=["activity_level", "hydration_status", "climate_zone", "worker_type"])

    features = [
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

    x = df[features]
    y = df["risk_label_int"]

    # 70 / 15 / 15 split
    x_temp, x_test, y_temp, y_test = train_test_split(
        x, y, test_size=0.15, random_state=42, stratify=y
    )
    x_train, x_val, y_train, y_val = train_test_split(
        x_temp, y_temp, test_size=0.176, random_state=42, stratify=y_temp
    )

    print(f"Train : {x_train.shape}")
    print(f"Val   : {x_val.shape}")
    print(f"Test  : {x_test.shape}")
    print(f"\nClass distribution (train):\n{y_train.value_counts()}")

    # Save splits
    DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump((x_train, x_val, x_test, y_train, y_val, y_test, features), SPLITS_PATH)
    print(f"\nSaved: {SPLITS_PATH}")


if __name__ == "__main__":
    main()
