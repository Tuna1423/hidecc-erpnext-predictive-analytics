from app.erpnext_client import ERPNextClient
from app.win_feature_builder import build_win_features
from app.predictors import predict_win


OPPORTUNITY = "CRM-OPP-2026-00002"


def main():

    print("=" * 70)
    print("WIN PROBABILITY - CATBOOST INFERENCE TEST")
    print("=" * 70)

    client = ERPNextClient()

    # ---------------------------------------------------------
    # 1. Get ERPNext data
    # ---------------------------------------------------------

    print("\n[1] Fetching ERPNext bundle...")

    bundle = client.get_opportunity_bundle(
        OPPORTUNITY
    )

    # ---------------------------------------------------------
    # 2. Build features
    # ---------------------------------------------------------

    print("[2] Building features...")

    features = build_win_features(
        bundle
    )

    print("\n=== FEATURES ===")
    print(
        features.to_string(index=False)
    )

    # ---------------------------------------------------------
    # 3. CatBoost inference
    # ---------------------------------------------------------

    print("\n[3] Running CatBoost...")

    probability, band = predict_win(
        features,
        medium_threshold=0.40,
        high_threshold=0.70,
    )

    # ---------------------------------------------------------
    # 4. Result
    # ---------------------------------------------------------

    print("\n=== PREDICTION ===")

    print(
        "Opportunity:",
        OPPORTUNITY
    )

    print(
        "Win Probability:",
        probability
    )

    print(
        "Win Band:",
        band
    )

    print(
        "Model:",
        "win_probability_catboost"
    )

    # ---------------------------------------------------------
    # 5. Validation
    # ---------------------------------------------------------

    print("\n=== VALIDATION ===")

    assert 0.0 <= probability <= 1.0

    assert band in [
        "Cao",
        "Trung bình",
        "Thấp",
    ]

    print(
        "Probability range: OK"
    )

    print(
        "Band validation: OK"
    )

    print(
        "CatBoost inference: SUCCESS"
    )


if __name__ == "__main__":
    main()