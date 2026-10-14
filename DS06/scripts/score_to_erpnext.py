import argparse
import os
from typing import Any, Dict

import requests
from dotenv import load_dotenv

from app.erpnext_client import ERPNextClient
from app.feature_builder import build_delay_features
from app.win_feature_builder import build_win_features
from app.predictors import predict_delay, predict_win


load_dotenv()


# ============================================================
# CONFIG
# ============================================================

DELAY_MEDIUM = float(
    os.getenv("DELAY_MEDIUM_THRESHOLD", "0.40")
)

DELAY_HIGH = float(
    os.getenv("DELAY_HIGH_THRESHOLD", "0.70")
)

WIN_MEDIUM = float(
    os.getenv("WIN_MEDIUM_THRESHOLD", "0.40")
)

WIN_HIGH = float(
    os.getenv("WIN_HIGH_THRESHOLD", "0.70")
)


# ============================================================
# ERPNext WHITELIST CALL
# ============================================================

def call_whitelisted_method(
    client: ERPNextClient,
    method: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:

    url = f"{client.base_url}/api/method/{method}"

    response = requests.post(
        url,
        headers=client.headers,
        json=payload,
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            f"ERPNext whitelist method failed: "
            f"status={response.status_code}, "
            f"url={url}, "
            f"response={response.text}"
        )

    return response.json()


# ============================================================
# VERIFY
# ============================================================

def verify_project(
    client: ERPNextClient,
    project: str,
) -> Dict[str, Any]:

    doc = client.get_doc(
        "Project",
        project,
    )

    delay_field = os.getenv(
        "DELAY_PROBABILITY_FIELD",
        "custom_delay_risk_score",
    )

    band_field = os.getenv(
        "DELAY_BAND_FIELD",
        "custom_risk_band",
    )

    return {
        delay_field: doc.get(delay_field),
        band_field: doc.get(band_field),
    }


def verify_opportunity(
    client: ERPNextClient,
    opportunity: str,
) -> Dict[str, Any]:

    doc = client.get_doc(
        "Opportunity",
        opportunity,
    )

    probability_field = os.getenv(
        "WIN_PROBABILITY_FIELD",
        "custom_win_probability",
    )

    band_field = os.getenv(
        "WIN_BAND_FIELD",
        "custom_win_band",
    )

    return {
        probability_field: doc.get(probability_field),
        band_field: doc.get(band_field),
    }


# ============================================================
# DELAY RISK
# ============================================================

def score_project(project: str) -> Dict[str, Any]:

    client = ERPNextClient()

    # --------------------------------------------------------
    # 1. Get ERPNext data
    # --------------------------------------------------------

    bundle = client.get_project_bundle(project)

    # --------------------------------------------------------
    # 2. Build exact DS-05 features
    # --------------------------------------------------------

    features = build_delay_features(bundle)

    if features.empty:
        raise ValueError(
            f"No Delay Risk features found for {project}"
        )

    # --------------------------------------------------------
    # 3. Predict
    # --------------------------------------------------------

    probability, band = predict_delay(
        features,
        DELAY_MEDIUM,
        DELAY_HIGH,
    )

    probability = float(probability)
    band = str(band)

    # --------------------------------------------------------
    # 4. DIRECT ERPNext WHITELIST CALL
    # --------------------------------------------------------

    payload = {
        "project": project,
        "score": probability,
        "band": band,
    }

    response = call_whitelisted_method(
        client,
        "hidecc_consulting.api.set_project_delay_score",
        payload,
    )

    # --------------------------------------------------------
    # 5. Verify from ERPNext
    # --------------------------------------------------------

    verified = verify_project(
        client,
        project,
    )

    return {
        "doctype": "Project",
        "name": project,
        "probability": probability,
        "band": band,
        "whitelist_method":
            "hidecc_consulting.api.set_project_delay_score",
        "payload": payload,
        "erpnext_response": response,
        "verified": verified,
    }


# ============================================================
# WIN PROBABILITY
# ============================================================

def score_opportunity(
    opportunity: str,
) -> Dict[str, Any]:

    client = ERPNextClient()

    # --------------------------------------------------------
    # 1. Get ERPNext data
    # --------------------------------------------------------

    bundle = client.get_opportunity_bundle(
        opportunity
    )

    # --------------------------------------------------------
    # 2. Build exact DS-05 features
    # --------------------------------------------------------

    features = build_win_features(bundle)

    if features.empty:
        raise ValueError(
            f"No Win Probability features found "
            f"for {opportunity}"
        )

    # --------------------------------------------------------
    # 3. Predict
    # --------------------------------------------------------

    probability, band = predict_win(
        features,
        WIN_MEDIUM,
        WIN_HIGH,
    )

    probability = float(probability)
    band = str(band)

    # --------------------------------------------------------
    # 4. DIRECT ERPNext WHITELIST CALL
    # --------------------------------------------------------

    payload = {
        "opportunity": opportunity,
        "score": probability,
        "band": band,
    }

    response = call_whitelisted_method(
        client,
        "hidecc_consulting.api.set_opportunity_win_score",
        payload,
    )

    # --------------------------------------------------------
    # 5. Verify from ERPNext
    # --------------------------------------------------------

    verified = verify_opportunity(
        client,
        opportunity,
    )

    return {
        "doctype": "Opportunity",
        "name": opportunity,
        "probability": probability,
        "band": band,
        "whitelist_method":
            "hidecc_consulting.api.set_opportunity_win_score",
        "payload": payload,
        "erpnext_response": response,
        "verified": verified,
    }


# ============================================================
# CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="DS-06 direct ERPNext whitelist scoring"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    project_parser = subparsers.add_parser(
        "project",
        help="Score a Project",
    )

    project_parser.add_argument(
        "name",
        help="ERPNext Project name, e.g. PROJ-0001",
    )

    opportunity_parser = subparsers.add_parser(
        "opportunity",
        help="Score an Opportunity",
    )

    opportunity_parser.add_argument(
        "name",
        help="ERPNext Opportunity name",
    )

    args = parser.parse_args()

    try:

        if args.command == "project":

            result = score_project(
                args.name
            )

        elif args.command == "opportunity":

            result = score_opportunity(
                args.name
            )

        else:
            raise ValueError(
                f"Unsupported command: {args.command}"
            )

        print()
        print("=" * 60)
        print("DS-06 ERPNext SCORING RESULT")
        print("=" * 60)

        print(f"Doctype     : {result['doctype']}")
        print(f"Name        : {result['name']}")
        print(
            f"Probability : "
            f"{result['probability']:.6f}"
        )
        print(f"Band        : {result['band']}")
        print(
            f"Whitelist   : "
            f"{result['whitelist_method']}"
        )

        print()
        print("Payload sent to ERPNext:")
        print(result["payload"])

        print()
        print("ERPNext verification:")
        print(result["verified"])

        print()
        print("SUCCESS")

    except Exception as exc:

        print()
        print("=" * 60)
        print("DS-06 ERPNext SCORING FAILED")
        print("=" * 60)
        print(str(exc))

        raise


if __name__ == "__main__":
    main()