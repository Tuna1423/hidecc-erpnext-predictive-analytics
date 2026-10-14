from pathlib import Path

import joblib

from app.erpnext_client import ERPNextClient
from app.feature_builder import DELAY_FEATURES, build_delay_features


MODEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "models"
    / "delay_risk_rf.joblib"
)


def main():
    print("=== DS-06 DELAY RISK MODEL TEST ===")

    # ---------------------------------------------------------
    # 1. Load model
    # ---------------------------------------------------------

    print("\n[1] Loading model...")

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found: {MODEL_PATH}"
        )

    model = joblib.load(MODEL_PATH)

    print(f"Model loaded: {MODEL_PATH.name}")
    print(f"Model type: {type(model)}")

    # ---------------------------------------------------------
    # 2. Fetch ERPNext data
    # ---------------------------------------------------------

    print("\n[2] Fetching ERPNext data...")

    client = ERPNextClient()

    project_name = "PROJ-0001"

    bundle = client.get_project_bundle(
        project_name
    )

    print(f"Project: {project_name}")

    # ---------------------------------------------------------
    # 3. Build features
    # ---------------------------------------------------------

    print("\n[3] Building Delay Risk features...")

    features = build_delay_features(
        bundle
    )

    X = features[
        DELAY_FEATURES
    ].copy()

    print(f"Feature rows: {len(X)}")
    print(f"Feature columns: {len(X.columns)}")

    print("\nFeature columns:")
    print(list(X.columns))

    # ---------------------------------------------------------
    # 4. Validate feature schema
    # ---------------------------------------------------------

    print("\n[4] Checking feature schema...")

    if list(X.columns) != DELAY_FEATURES:
        raise ValueError(
            "Feature columns do not match DELAY_FEATURES."
        )

    print("Feature schema: OK")

    # ---------------------------------------------------------
    # 5. Predict probability
    # ---------------------------------------------------------

    print("\n[5] Running model prediction...")

    probabilities = model.predict_proba(X)

    print(
        f"predict_proba shape: {probabilities.shape}"
    )

    if probabilities.shape[1] != 2:
        raise ValueError(
            "Expected binary classification output "
            "with 2 probability columns."
        )

    # Class 1 = Delay Risk
    delay_probabilities = probabilities[:, 1]

    features = features.copy()

    features["delay_probability"] = (
        delay_probabilities
    )

    # ---------------------------------------------------------
    # 6. Display discipline-level predictions
    # ---------------------------------------------------------

    print("\n=== DISCIPLINE-LEVEL PREDICTIONS ===")

    result = features[
        [
            "project_id",
            "discipline",
            "delay_probability",
        ]
    ].copy()

    print(
        result.to_string(
            index=False
        )
    )

    # ---------------------------------------------------------
    # 7. Project-level aggregation
    # ---------------------------------------------------------

    project_score = float(
        result["delay_probability"].mean()
    )

    print("\n=== PROJECT-LEVEL SCORE ===")

    print(
        f"Project: {project_name}"
    )

    print(
        f"Number of disciplines: {len(result)}"
    )

    print(
        f"Mean Delay Risk: {project_score:.6f}"
    )

    # ---------------------------------------------------------
    # 8. Basic probability validation
    # ---------------------------------------------------------

    print("\n=== VALIDATION ===")

    if (
        result["delay_probability"]
        .isna()
        .any()
    ):
        raise ValueError(
            "Prediction contains NaN."
        )

    if (
        (result["delay_probability"] < 0)
        | (result["delay_probability"] > 1)
    ).any():
        raise ValueError(
            "Prediction contains probability "
            "outside [0, 1]."
        )

    print("Probability range: OK")
    print("Model inference: SUCCESS")


if __name__ == "__main__":
    main()