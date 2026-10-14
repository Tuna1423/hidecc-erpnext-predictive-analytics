import os
from typing import Dict, Any

from fastapi import FastAPI, HTTPException

from .erpnext_client import ERPNextClient
from .feature_builder import build_delay_features
from .win_feature_builder import build_win_features
from .predictors import predict_delay, predict_win
from .schemas import FeatureRequest, ScoreRequest, ScoreFromERPNextRequest


app = FastAPI(
    title="HIDECC DS-06 Scoring API",
    version="1.0.0",
)


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


DELAY_PROB_FIELD = os.getenv(
    "DELAY_PROBABILITY_FIELD",
    "custom_delay_risk_score",
)

DELAY_BAND_FIELD = os.getenv(
    "DELAY_BAND_FIELD",
    "custom_risk_band",
)

WIN_PROB_FIELD = os.getenv(
    "WIN_PROBABILITY_FIELD",
    "custom_win_probability",
)

WIN_BAND_FIELD = os.getenv(
    "WIN_BAND_FIELD",
    "custom_win_band",
)


# ============================================================
# HELPERS
# ============================================================

def _client() -> ERPNextClient:
    return ERPNextClient()


def _band(
    probability: float,
    medium_threshold: float,
    high_threshold: float,
) -> str:

    if probability >= high_threshold:
        return "Cao"

    if probability >= medium_threshold:
        return "Trung bình"

    return "Thấp"


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "ok",
        "service": "HIDECC DS-06 Scoring API",
    }


# ============================================================
# DELAY RISK
# ============================================================

@app.post("/predict_project_delay")
def predict_project_delay(request: FeatureRequest):

    try:

        probability, band = predict_delay(
            request.features,
            DELAY_MEDIUM,
            DELAY_HIGH,
        )

        return {
            "probability": probability,
            "band": band,
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@app.get(
    "/erpnext/project/{project_name}/features"
)
def get_project_features(project_name: str):

    try:

        client = _client()

        bundle = client.get_project_bundle(
            project_name
        )

        features = build_delay_features(
            bundle
        )

        return {
            "doctype": "Project",
            "name": project_name,
            "n_rows": len(features),
            "features": features.to_dict(
                orient="records"
            ),
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@app.post(
    "/set_project_delay_score/{project_name}"
)
def set_project_delay_score(
    project_name: str,
    request: ScoreRequest,
):

    client = _client()

    fields = {
        DELAY_PROB_FIELD: request.probability,
        DELAY_BAND_FIELD: request.band,
    }

    try:

        written = client.update_doc(
            "Project",
            project_name,
            fields,
        )

        verified = client.get_doc(
            "Project",
            project_name,
        )

        return {
            "doctype": "Project",
            "name": project_name,
            "written": fields,
            "verified": {
                DELAY_PROB_FIELD:
                    verified.get(DELAY_PROB_FIELD),

                DELAY_BAND_FIELD:
                    verified.get(DELAY_BAND_FIELD),
            },
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@app.post(
    "/score_project_from_erpnext/{project_name}"
)
def score_project_from_erpnext(
    project_name: str
):

    try:

        client = _client()

        # ----------------------------------------------------
        # 1. GET ERPNext data
        # ----------------------------------------------------

        bundle = client.get_project_bundle(
            project_name
        )

        # ----------------------------------------------------
        # 2. Build point-in-time features
        # ----------------------------------------------------

        features = build_delay_features(
            bundle
        )

        if features.empty:

            raise ValueError(
                f"No delay feature rows found "
                f"for project {project_name}"
            )

        # ----------------------------------------------------
        # 3. Predict
        # ----------------------------------------------------

        probability, band = predict_delay(
            features,
            DELAY_MEDIUM,
            DELAY_HIGH,
        )

        # ----------------------------------------------------
        # 4. Write back to ERPNext
        # ----------------------------------------------------

        fields = {
            DELAY_PROB_FIELD:
                probability,

            DELAY_BAND_FIELD:
                band,
        }

        client.update_doc(
            "Project",
            project_name,
            fields,
        )

        # ----------------------------------------------------
        # 5. Verify
        # ----------------------------------------------------

        verified = client.get_doc(
            "Project",
            project_name,
        )

        return {
            "doctype": "Project",
            "name": project_name,

            "feature_summary": {
                "n_rows": len(features),
                "feature_columns":
                    features.columns.tolist(),
            },

            "score": {
                "probability": probability,
                "band": band,
            },

            "written": fields,

            "verified": {
                DELAY_PROB_FIELD:
                    verified.get(
                        DELAY_PROB_FIELD
                    ),

                DELAY_BAND_FIELD:
                    verified.get(
                        DELAY_BAND_FIELD
                    ),
            },
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


# ============================================================
# WIN PROBABILITY
# ============================================================

@app.post("/predict_opportunity_success")
def predict_opportunity_success(
    request: FeatureRequest
):

    try:

        probability, band = predict_win(
            request.features,
            WIN_MEDIUM,
            WIN_HIGH,
        )

        return {
            "probability": probability,
            "band": band,
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@app.get(
    "/erpnext/opportunity/{opportunity_name}/features"
)
def get_opportunity_features(
    opportunity_name: str
):

    try:

        client = _client()

        bundle = client.get_opportunity_bundle(
            opportunity_name
        )

        features = build_win_features(
            bundle
        )

        return {
            "doctype": "Opportunity",
            "name": opportunity_name,
            "n_rows": len(features),
            "features": features.to_dict(
                orient="records"
            ),
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@app.post(
    "/set_opportunity_win_score/{opportunity_name}"
)
def set_opportunity_win_score(
    opportunity_name: str,
    request: ScoreRequest,
):

    client = _client()

    fields = {
        WIN_PROB_FIELD:
            request.probability,

        WIN_BAND_FIELD:
            request.band,
    }

    try:

        written = client.update_doc(
            "Opportunity",
            opportunity_name,
            fields,
        )

        verified = client.get_doc(
            "Opportunity",
            opportunity_name,
        )

        return {
            "doctype": "Opportunity",
            "name": opportunity_name,

            "written": fields,

            "verified": {
                WIN_PROB_FIELD:
                    verified.get(
                        WIN_PROB_FIELD
                    ),

                WIN_BAND_FIELD:
                    verified.get(
                        WIN_BAND_FIELD
                    ),
            },
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@app.post(
    "/score_opportunity_from_erpnext/{opportunity_name}"
)
def score_opportunity_from_erpnext(
    opportunity_name: str
):

    try:

        client = _client()

        # ----------------------------------------------------
        # 1. GET ERPNext Opportunity bundle
        # ----------------------------------------------------

        bundle = client.get_opportunity_bundle(
            opportunity_name
        )

        # ----------------------------------------------------
        # 2. Build DS-05 features
        # ----------------------------------------------------

        features = build_win_features(
            bundle
        )

        if features.empty:
            raise ValueError(
                f"No win-probability features "
                f"found for opportunity "
                f"{opportunity_name}"
            )

        # ----------------------------------------------------
        # 3. CatBoost prediction
        # ----------------------------------------------------

        probability, band = predict_win(
            features,
            WIN_MEDIUM,
            WIN_HIGH,
        )

        probability = float(probability)
        band = str(band)

        # ----------------------------------------------------
        # 4. Convert feature values to JSON-safe types
        # ----------------------------------------------------

        feature_summary = {}

        for column in features.columns:

            value = features.iloc[0][column]

            if hasattr(value, "item"):
                value = value.item()

            feature_summary[column] = value

        # ----------------------------------------------------
        # 5. Write prediction to ERPNext
        # ----------------------------------------------------

        fields = {
            WIN_PROB_FIELD: probability,
            WIN_BAND_FIELD: band,
        }

        client.update_doc(
            "Opportunity",
            opportunity_name,
            fields,
        )

        # ----------------------------------------------------
        # 6. Verify
        # ----------------------------------------------------

        verified = client.get_doc(
            "Opportunity",
            opportunity_name,
        )

        # ----------------------------------------------------
        # 7. Return JSON-safe response
        # ----------------------------------------------------

        verified_probability = verified.get(
            WIN_PROB_FIELD
        )

        verified_band = verified.get(
            WIN_BAND_FIELD
        )

        if hasattr(verified_probability, "item"):
            verified_probability = (
                verified_probability.item()
            )

        if verified_band is not None:
            verified_band = str(verified_band)

        return {
            "doctype": "Opportunity",
            "name": opportunity_name,

            "feature_summary": feature_summary,

            "score": {
                "probability": probability,
                "band": band,
            },

            "written": {
                WIN_PROB_FIELD: probability,
                WIN_BAND_FIELD: band,
            },

            "verified": {
                WIN_PROB_FIELD:
                    verified_probability,

                WIN_BAND_FIELD:
                    verified_band,
            },
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )
def score_opportunity_from_erpnext(
    opportunity_name: str
):

    try:

        client = _client()

        # ----------------------------------------------------
        # 1. GET ERPNext Opportunity bundle
        # ----------------------------------------------------

        bundle = client.get_opportunity_bundle(
            opportunity_name
        )

        # ----------------------------------------------------
        # 2. Build exact DS-05 feature schema
        # ----------------------------------------------------

        features = build_win_features(
            bundle
        )

        if features.empty:

            raise ValueError(
                f"No win-probability features "
                f"found for opportunity "
                f"{opportunity_name}"
            )

        # ----------------------------------------------------
        # 3. CatBoost prediction
        # ----------------------------------------------------

        probability, band = predict_win(
            features,
            WIN_MEDIUM,
            WIN_HIGH,
        )

        # ----------------------------------------------------
        # 4. Write prediction to ERPNext
        # ----------------------------------------------------

        fields = {
            WIN_PROB_FIELD:
                probability,

            WIN_BAND_FIELD:
                band,
        }

        client.update_doc(
            "Opportunity",
            opportunity_name,
            fields,
        )

        # ----------------------------------------------------
        # 5. Read back and verify
        # ----------------------------------------------------

        verified = client.get_doc(
            "Opportunity",
            opportunity_name,
        )

        return {
            "doctype": "Opportunity",
            "name": opportunity_name,

            "feature_summary": {
                column: (
                    features.iloc[0][column]
                    if column in features.columns
                    else None
                )
                for column in features.columns
            },

            "score": {
                "probability": probability,
                "band": band,
            },

            "written": fields,

            "verified": {
                WIN_PROB_FIELD:
                    verified.get(
                        WIN_PROB_FIELD
                    ),

                WIN_BAND_FIELD:
                    verified.get(
                        WIN_BAND_FIELD
                    ),
            },
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )