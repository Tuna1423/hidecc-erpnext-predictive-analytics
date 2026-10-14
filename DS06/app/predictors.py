from pathlib import Path
from typing import Dict, Any
from catboost import CatBoostClassifier
import joblib
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"

DELAY_MODEL_PATH = MODEL_DIR / "delay_risk_rf.joblib"

DELAY_FEATURES = [
    "contract_value",
    "planned_duration_days",
    "n_disciplines_known_at_snapshot",
    "n_open_disciplines_at_snapshot",
    "total_workload_pct",
    "pct_staff_overloaded_at_snapshot",
    "n_open_overdue_tasks_at_snapshot",
    "pm_historic_late_rate",
    "customer_historic_late_rate",
    "project_type",
    "discipline",
]


class DelayRiskPredictor:
    def __init__(self, model_path: Path = DELAY_MODEL_PATH):
        if not model_path.exists():
            raise FileNotFoundError(
                f"Không tìm thấy Delay Risk model: {model_path}"
            )

        self.model = joblib.load(model_path)

    def predict(self, features: pd.DataFrame) -> Dict[str, Any]:
        """
        Predict Delay Risk ở mức Discipline Allocation.

        Input:
            DataFrame chứa 11 feature đã chốt.

        Output:
            Score của từng discipline.
        """

        missing = [
            col for col in DELAY_FEATURES
            if col not in features.columns
        ]

        if missing:
            raise ValueError(
                f"Thiếu feature bắt buộc: {missing}"
            )

        X = features[DELAY_FEATURES].copy()

        probabilities = self.model.predict_proba(X)[:, 1]

        result = features.copy()

        result["delay_risk_score"] = probabilities

        return {
            "rows": result.to_dict(orient="records"),
            "n_rows": len(result),
        }

    def predict_project(self, features: pd.DataFrame) -> Dict[str, Any]:
        """
        Tạo một project-level Delay Risk score
        từ các discipline-level predictions.

        Mean chỉ được dùng để đưa nhiều discipline scores
        về một score duy nhất để ghi vào Project.
        """

        prediction = self.predict(features)

        rows = prediction["rows"]

        if not rows:
            raise ValueError(
                "Không có discipline nào để tính Project Delay Risk."
            )

        scores = [
            float(row["delay_risk_score"])
            for row in rows
        ]

        project_score = sum(scores) / len(scores)

        return {
            "probability": project_score,
            "n_disciplines": len(scores),
            "discipline_scores": rows,
        }


# Load model một lần khi module được import.
delay_predictor = DelayRiskPredictor()

WIN_MODEL_PATH = MODEL_DIR / "win_probability_catboost.cbm"

WIN_FEATURES = [
    "lead_source",
    "customer_segment",
    "territory",
    "opportunity_amount",
    "days_lead_to_opp",
    "discount_rate_at_first_quotation",
]

WIN_CAT_FEATURES = [
    "lead_source",
    "customer_segment",
    "territory",
]


class WinProbabilityPredictor:

    def __init__(
        self,
        model_path: Path = WIN_MODEL_PATH,
    ):

        if not model_path.exists():
            raise FileNotFoundError(
                f"Không tìm thấy Win Probability model: "
                f"{model_path}"
            )

        self.model = CatBoostClassifier()

        self.model.load_model(
            str(model_path)
        )

    def predict(
        self,
        features: pd.DataFrame,
    ) -> float:

        missing = [
            col
            for col in WIN_FEATURES
            if col not in features.columns
        ]

        if missing:
            raise ValueError(
                f"Thiếu Win Probability feature: {missing}"
            )

        X = features[WIN_FEATURES].copy()

        # CatBoost native categorical.
        # Missing categorical values are represented explicitly.
        for col in WIN_CAT_FEATURES:
            X[col] = (
                X[col]
                .fillna("__MISSING__")
                .astype(str)
            )

        probability = float(
            self.model.predict_proba(X)[0, 1]
        )

        return probability


win_predictor = WinProbabilityPredictor()


def predict_win(
    features: pd.DataFrame,
    medium_threshold: float,
    high_threshold: float,
):

    probability = win_predictor.predict(
        features
    )

    if probability >= high_threshold:
        band = "Cao"
    elif probability >= medium_threshold:
        band = "Trung bình"
    else:
        band = "Thấp"

    return probability, band

def predict_delay(
    features: pd.DataFrame,
    medium_threshold: float,
    high_threshold: float,
):
    """
    Compatibility wrapper cho FastAPI.

    Trả về project-level probability và
    risk band theo đúng giá trị Select
    của ERPNext.
    """

    result = delay_predictor.predict_project(features)

    probability = float(result["probability"])

    if probability >= high_threshold:
        band = "Cao"
    elif probability >= medium_threshold:
        band = "Trung bình"
    else:
        band = "Thấp"

    return probability, band