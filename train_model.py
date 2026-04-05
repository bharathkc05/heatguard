from pathlib import Path

from xgboost import XGBClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.utils.class_weight import compute_sample_weight
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import joblib


CLASS_NAMES = ["LOW", "MODERATE", "HIGH", "CRITICAL"]
MIN_TARGETS = {
    "accuracy": 0.88,
    "critical_recall": 0.93,
    "high_recall": 0.85,
    "moderate_recall": 0.78,
    "auc_roc": 0.95,
}

DATA_SPLITS_PATH = Path("data") / "processed" / "data_splits.pkl"
PLOTS_DIR = Path("artifacts") / "plots"
REPORTS_DIR = Path("artifacts") / "reports"


def fit_with_gpu_fallback(x_train, y_train, x_val, y_val, sample_weight):
    base_params = {
        "n_estimators": 500,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 3,
        "eval_metric": "mlogloss",
        "early_stopping_rounds": 30,
        "random_state": 42,
        "n_jobs": -1,
    }

    # Try modern CUDA config first, then legacy GPU mode, then CPU.
    candidates = [
        {"tree_method": "hist", "device": "cuda"},
        {"tree_method": "gpu_hist", "predictor": "gpu_predictor"},
        {"tree_method": "hist"},
    ]

    last_exc = None
    for idx, extra in enumerate(candidates, start=1):
        params = {**base_params, **extra}
        print(f"\n[TRAIN] Attempt {idx} with params: {extra}")
        model = XGBClassifier(**params)
        try:
            model.fit(
                x_train,
                y_train,
                sample_weight=sample_weight,
                eval_set=[(x_val, y_val)],
                verbose=50,
            )
            print(f"[TRAIN] Success using: {extra}")
            return model, extra
        except Exception as exc:
            last_exc = exc
            print(f"[TRAIN] Failed with {extra}: {exc}")

    raise RuntimeError(f"All training attempts failed. Last error: {last_exc}")


def save_confusion_matrix_plot(cm: np.ndarray, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(np.arange(len(CLASS_NAMES)))
    ax.set_yticks(np.arange(len(CLASS_NAMES)))
    ax.set_xticklabels(CLASS_NAMES, rotation=45, ha="right")
    ax.set_yticklabels(CLASS_NAMES)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title("HeatGuard AI - Confusion Matrix")

    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center")

    fig.colorbar(im, ax=ax)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {output_path}")


def print_target_checks(metrics: dict) -> None:
    print("\n" + "=" * 72)
    print("Minimum Targets Before Backend")
    print("=" * 72)

    rows = [
        ("Overall accuracy", metrics["accuracy"], MIN_TARGETS["accuracy"]),
        ("CRITICAL recall", metrics["critical_recall"], MIN_TARGETS["critical_recall"]),
        ("HIGH recall", metrics["high_recall"], MIN_TARGETS["high_recall"]),
        ("MODERATE recall", metrics["moderate_recall"], MIN_TARGETS["moderate_recall"]),
        ("AUC-ROC", metrics["auc_roc"], MIN_TARGETS["auc_roc"]),
    ]

    all_passed = True
    for label, actual, target in rows:
        passed = actual >= target
        all_passed = all_passed and passed
        status = "PASS" if passed else "FAIL"
        print(f"{label:<20} actual={actual:.4f}  target>={target:.2f}  [{status}]")

    verdict = "ALL TARGETS MET" if all_passed else "TARGETS NOT FULLY MET"
    print("-" * 72)
    print(verdict)


def main() -> None:
    x_train, x_val, x_test, y_train, y_val, y_test, features = joblib.load(DATA_SPLITS_PATH)

    # Sample weights to handle remaining imbalance.
    weights = compute_sample_weight("balanced", y_train)

    model, used_backend = fit_with_gpu_fallback(
        x_train=x_train,
        y_train=y_train,
        x_val=x_val,
        y_val=y_val,
        sample_weight=weights,
    )

    # Evaluate
    y_pred = model.predict(x_test)
    y_proba = model.predict_proba(x_test)

    print("\n" + "=" * 50)
    print("Backend used:", used_backend)
    print(
        classification_report(
            y_test,
            y_pred,
            target_names=CLASS_NAMES,
            digits=4,
        )
    )

    acc = accuracy_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_proba, multi_class="ovr", average="weighted")

    report_dict = classification_report(
        y_test,
        y_pred,
        target_names=CLASS_NAMES,
        output_dict=True,
    )

    metrics = {
        "accuracy": float(acc),
        "critical_recall": float(report_dict["CRITICAL"]["recall"]),
        "high_recall": float(report_dict["HIGH"]["recall"]),
        "moderate_recall": float(report_dict["MODERATE"]["recall"]),
        "auc_roc": float(auc),
    }

    print_target_checks(metrics)

    # Feature importance
    imp = pd.DataFrame(
        {
            "feature": features,
            "importance": model.feature_importances_,
        }
    ).sort_values("importance", ascending=True)

    imp.plot(
        kind="barh",
        x="feature",
        y="importance",
        figsize=(10, 8),
        legend=False,
        title="HeatGuard AI - Feature Importance",
    )
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "feature_importance.png", dpi=150)
    plt.close()
    print(f"Saved: {PLOTS_DIR / 'feature_importance.png'}")

    cm = confusion_matrix(y_test, y_pred)
    save_confusion_matrix_plot(cm, PLOTS_DIR / "confusion_matrix.png")

    metrics_df = pd.DataFrame([metrics])
    metrics_df.to_csv(REPORTS_DIR / "model_metrics.csv", index=False)
    print(f"Saved: {REPORTS_DIR / 'model_metrics.csv'}")

    model_dir = Path("models")
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "xgboost_heatguard.pkl"
    joblib.dump(model, model_path)
    print(f"Saved: {model_path}")


if __name__ == "__main__":
    main()
