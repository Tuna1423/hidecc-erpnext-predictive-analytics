from typing import Dict, Any

import pandas as pd


WIN_FEATURES = [
    "lead_source",
    "customer_segment",
    "territory",
    "opportunity_amount",
    "days_lead_to_opp",
    "discount_rate_at_first_quotation",
]


def build_win_features(
    bundle: Dict[str, Any],
) -> pd.DataFrame:

    opportunity = bundle["opportunity"]
    quotations = bundle.get("quotations", [])
    leads = bundle.get("leads", [])

    opportunity_name = opportunity["name"]

    # =========================================================
    # 1. First quotation
    # =========================================================

    quotation_rows = []

    for quotation in quotations:

        if quotation.get("opportunity") != opportunity_name:
            continue

        quotation_date = pd.to_datetime(
            quotation.get("transaction_date"),
            errors="coerce",
        )

        discount = quotation.get(
            "additional_discount_percentage"
        )

        quotation_rows.append(
            {
                "quotation_date": quotation_date,
                "discount_rate": discount,
            }
        )

    if not quotation_rows:
        raise ValueError(
            f"Opportunity {opportunity_name} chưa có Quotation. "
            "Win Probability chỉ áp dụng cho Opportunity "
            "đã có ít nhất một Quotation."
        )

    quotation_df = pd.DataFrame(
        quotation_rows
    )

    quotation_df = quotation_df.sort_values(
        "quotation_date",
        na_position="last",
    )

    first_quotation = quotation_df.iloc[0]

    # =========================================================
    # 2. Lead → Opportunity
    # =========================================================

    days_lead_to_opp = None

    opportunity_from = opportunity.get(
        "opportunity_from"
    )

    party_name = opportunity.get(
        "party_name"
    )

    if (
        opportunity_from == "Lead"
        and party_name
    ):

        matching_lead = None

        for lead in leads:

            if lead.get("name") == party_name:
                matching_lead = lead
                break

        if matching_lead is not None:

            lead_creation = pd.to_datetime(
                matching_lead.get("creation"),
                errors="coerce",
            )

            opportunity_date = pd.to_datetime(
                opportunity.get("transaction_date"),
                errors="coerce",
            )

            if (
                not pd.isna(lead_creation)
                and not pd.isna(opportunity_date)
            ):
                days_lead_to_opp = (
                    opportunity_date - lead_creation
                ).days

    # =========================================================
    # 3. Build exactly the 6 DS-05 features
    # =========================================================

    row = {
        "lead_source": opportunity.get(
            "utm_source"
        ),

        "customer_segment": opportunity.get(
            "customer_group"
        ),

        "territory": opportunity.get(
            "territory"
        ),

        "opportunity_amount": opportunity.get(
            "opportunity_amount"
        ),

        "days_lead_to_opp": days_lead_to_opp,

        "discount_rate_at_first_quotation":
            first_quotation.get(
                "discount_rate"
            ),
    }

    features = pd.DataFrame(
        [row],
        columns=WIN_FEATURES,
    )

    return features