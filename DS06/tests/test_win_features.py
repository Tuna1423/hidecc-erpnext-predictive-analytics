from app.erpnext_client import ERPNextClient
from app.win_feature_builder import build_win_features


OPPORTUNITY = "CRM-OPP-2026-00002"


def main():

    client = ERPNextClient()

    print("=" * 70)
    print("WIN PROBABILITY - FEATURE BUILDER TEST")
    print("=" * 70)

    # ---------------------------------------------------------
    # 1. Fetch ERPNext data
    # ---------------------------------------------------------

    print("\n[1] Fetching Opportunity bundle...")

    bundle = client.get_opportunity_bundle(
        OPPORTUNITY
    )

    opportunity = bundle["opportunity"]

    print(
        "Opportunity:",
        opportunity.get("name")
    )

    print(
        "Opportunity From:",
        opportunity.get("opportunity_from")
    )

    print(
        "Party:",
        opportunity.get("party_name")
    )

    print(
        "Quotation count:",
        len(bundle["quotations"])
    )

    print(
        "Lead count:",
        len(bundle["leads"])
    )

    # ---------------------------------------------------------
    # 2. Build features
    # ---------------------------------------------------------

    print("\n[2] Building Win Probability features...")

    features = build_win_features(
        bundle
    )

    # ---------------------------------------------------------
    # 3. Display
    # ---------------------------------------------------------

    print("\n=== WIN FEATURES ===")

    print(
        features.to_string(index=False)
    )

    # ---------------------------------------------------------
    # 4. Validation
    # ---------------------------------------------------------

    print("\n=== VALIDATION ===")

    print(
        "Shape:",
        features.shape
    )

    print(
        "Columns:",
        list(features.columns)
    )

    print(
        "\nMissing values:"
    )

    print(
        features.isna().sum()
    )

    print(
        "\nDtypes:"
    )

    print(
        features.dtypes
    )

    # ---------------------------------------------------------
    # 5. Expected schema
    # ---------------------------------------------------------

    expected = [
        "lead_source",
        "customer_segment",
        "territory",
        "opportunity_amount",
        "days_lead_to_opp",
        "discount_rate_at_first_quotation",
    ]

    assert list(features.columns) == expected

    assert features.shape == (1, 6)

    print(
        "\nSchema validation: OK"
    )


if __name__ == "__main__":
    main()