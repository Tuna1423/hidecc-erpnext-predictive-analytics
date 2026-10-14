import json
import os
from typing import Any, Dict, List

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIG
# ============================================================

FASTAPI_BASE_URL = os.getenv(
    "FASTAPI_BASE_URL",
    "http://127.0.0.1:8001",
).rstrip("/")

ERPNext_BASE_URL = os.getenv(
    "ERPNEXT_BASE_URL",
    "",
).rstrip("/")

ERPNext_API_KEY = os.getenv("ERPNEXT_API_KEY", "")
ERPNext_API_SECRET = os.getenv("ERPNEXT_API_SECRET", "")

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
# PAGE
# ============================================================

st.set_page_config(
    page_title="HIDECC DS-06 Dashboard",
    page_icon="",
    layout="wide",
)


# ============================================================
# HELPERS
# ============================================================

def erpnext_headers() -> Dict[str, str]:
    if not ERPNext_API_KEY or not ERPNext_API_SECRET:
        raise RuntimeError(
            "ERPNEXT_API_KEY / ERPNEXT_API_SECRET chưa được cấu hình."
        )

    return {
        "Authorization": f"token {ERPNext_API_KEY}:{ERPNext_API_SECRET}",
        "Accept": "application/json",
    }


def erpnext_list(
    doctype: str,
    fields: List[str],
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    if not ERPNext_BASE_URL:
        raise RuntimeError(
            "ERPNEXT_BASE_URL chưa được cấu hình."
        )

    url = f"{ERPNext_BASE_URL}/api/resource/{doctype}"

    params = {
        "fields": json.dumps(fields, ensure_ascii=False),
        "limit_page_length": limit,
    }

    response = requests.get(
        url,
        headers=erpnext_headers(),
        params=params,
        timeout=60,
    )
    response.raise_for_status()

    return response.json().get("data", [])


def call_fastapi_score(path: str) -> Dict[str, Any]:
    url = f"{FASTAPI_BASE_URL}{path}"

    response = requests.post(
        url,
        timeout=120,
    )

    if not response.ok:
        raise RuntimeError(
            f"FastAPI {response.status_code}: {response.text}"
        )

    return response.json()


def score_many(
    names: List[str],
    endpoint_template: str,
    label: str,
) -> Dict[str, Any]:
    """Run the existing single-record FastAPI scoring endpoint for each record."""
    results = []
    failures = []

    progress = st.progress(0, text=label)
    total = len(names)

    for index, name in enumerate(names, start=1):
        try:
            result = call_fastapi_score(
                endpoint_template.format(name=name)
            )

            score = result.get("score", {})

            results.append({
                "name": name,
                "probability": score.get("probability"),
                "band": score.get("band"),
                "status": "Thành công",
            })

        except Exception as exc:
            failures.append({
                "name": name,
                "error": str(exc),
            })

        progress.progress(
            index / total,
            text=f"{label}: {index}/{total}",
        )

    progress.empty()

    return {
        "results": results,
        "failures": failures,
    }


@st.cache_data(ttl=60)
def load_projects() -> pd.DataFrame:
    rows = erpnext_list(
        "Project",
        [
            "name",
            "project_type",
            "expected_start_date",
            "expected_end_date",
            "customer",
            DELAY_PROB_FIELD,
            DELAY_BAND_FIELD,
        ],
    )

    df = pd.DataFrame(rows)

    if df.empty:
        return pd.DataFrame(
            columns=[
                "name",
                "project_type",
                "customer",
                DELAY_PROB_FIELD,
                DELAY_BAND_FIELD,
            ]
        )

    df["delay_probability"] = pd.to_numeric(
        df[DELAY_PROB_FIELD],
        errors="coerce",
    )

    return df


@st.cache_data(ttl=60)
def load_opportunities() -> pd.DataFrame:
    rows = erpnext_list(
        "Opportunity",
        [
            "name",
            "opportunity_from",
            "party_name",
            "transaction_date",
            "opportunity_amount",
            "status",
            WIN_PROB_FIELD,
            WIN_BAND_FIELD,
        ],
    )

    df = pd.DataFrame(rows)

    if df.empty:
        return pd.DataFrame(
            columns=[
                "name",
                "opportunity_from",
                "party_name",
                "opportunity_amount",
                WIN_PROB_FIELD,
                WIN_BAND_FIELD,
            ]
        )

    df["win_probability"] = pd.to_numeric(
        df[WIN_PROB_FIELD],
        errors="coerce",
    )

    df["opportunity_amount"] = pd.to_numeric(
        df["opportunity_amount"],
        errors="coerce",
    )

    return df

@st.cache_data(ttl=60)
def load_quotation_opportunities() -> set:
    rows = erpnext_list(
        "Quotation",
        [
            "name",
            "opportunity",
        ],
    )

    return {
        row["opportunity"]
        for row in rows
        if row.get("opportunity")
    }

def band_counts(
    df: pd.DataFrame,
    column: str,
) -> pd.DataFrame:
    order = ["Cao", "Trung bình", "Thấp"]

    if df.empty or column not in df.columns:
        return pd.DataFrame({"Số lượng": []})

    counts = (
        df[column]
        .fillna("Chưa có score")
        .replace("", "Chưa có score")
        .value_counts()
        .reindex(order + ["Chưa có score"], fill_value=0)
    )

    return counts.to_frame("Số lượng")


def format_money(value: Any) -> str:
    if pd.isna(value):
        return "—"

    return f"{value:,.0f} ₫"


# ============================================================
# HEADER
# ============================================================

st.title(" HIDECC — DS-06 Scoring Dashboard")
st.caption(
    "Dashboard thử nghiệm — đọc score hiện có từ ERPNext; "
    "không tự huấn luyện hoặc tính lại model."
)

with st.sidebar:
    st.header("Điều khiển")

    if st.button("Làm mới dữ liệu", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()

    st.write("**Data source**")
    st.code(
        ERPNext_BASE_URL or "Chưa cấu hình",
        language=None,
    )

    st.write("**Scoring API**")
    st.code(
        FASTAPI_BASE_URL,
        language=None,
    )


# ============================================================
# LOAD
# ============================================================

try:
    projects = load_projects()
    opportunities = load_opportunities()
    quotation_opportunities = load_quotation_opportunities()
except Exception as exc:
    st.error(f"Không thể tải dữ liệu: {exc}")
    st.stop()


# ============================================================
# KPI
# ============================================================

delay_scored = projects["delay_probability"].notna().sum() if not projects.empty else 0
delay_high = (
    (projects[DELAY_BAND_FIELD] == "Cao").sum()
    if not projects.empty and DELAY_BAND_FIELD in projects.columns
    else 0
)

win_scored = opportunities["win_probability"].notna().sum() if not opportunities.empty else 0
win_high = (
    (opportunities[WIN_BAND_FIELD] == "Cao").sum()
    if not opportunities.empty and WIN_BAND_FIELD in opportunities.columns
    else 0
)

total_pipeline = (
    opportunities["opportunity_amount"].sum(min_count=1)
    if not opportunities.empty
    else 0
)

k1, k2, k3, k4, k5 = st.columns(5)

k1.metric("Projects", f"{len(projects):,}")
k2.metric("Delay đã score", f"{delay_scored:,}")
k3.metric("Delay risk cao", f"{delay_high:,}")
k4.metric("Opportunities", f"{len(opportunities):,}")
k5.metric("Win risk cao", f"{win_high:,}")

st.divider()

# ============================================================
# TABS
# ============================================================

tab_overview, tab_delay, tab_win = st.tabs(
    [
        "Tổng quan",
        "Delay Risk",
        "Win Probability",
    ]
)


# ============================================================
# OVERVIEW
# ============================================================

with tab_overview:
    st.subheader("Tổng quan scoring")

    left, right = st.columns(2)

    with left:
        st.markdown("### Delay Risk")
        delay_counts = band_counts(
            projects,
            DELAY_BAND_FIELD,
        )
        st.bar_chart(delay_counts)

        st.dataframe(
            projects[
                [
                    "name",
                    "project_type",
                    "customer",
                    DELAY_PROB_FIELD,
                    DELAY_BAND_FIELD,
                ]
            ]
            .sort_values(
                DELAY_PROB_FIELD,
                ascending=False,
                na_position="last",
            )
            .head(10),
            use_container_width=True,
            hide_index=True,
        )

    with right:
        st.markdown("### Win Probability")
        win_counts = band_counts(
            opportunities,
            WIN_BAND_FIELD,
        )
        st.bar_chart(win_counts)

        top_win = opportunities[
            [
                "name",
                "party_name",
                "opportunity_amount",
                WIN_PROB_FIELD,
                WIN_BAND_FIELD,
            ]
        ].copy()

        top_win["opportunity_amount"] = top_win[
            "opportunity_amount"
        ].map(format_money)

        st.dataframe(
            top_win.sort_values(
                WIN_PROB_FIELD,
                ascending=False,
                na_position="last",
            ).head(10),
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# DELAY
# ============================================================

with tab_delay:
    st.subheader(" Delay Risk")

    if projects.empty:
        st.info("Không có Project.")
    else:
        c1, c2 = st.columns(2)

        with c1:
            selected_band = st.selectbox(
                "Lọc theo risk band",
                [
                    "Tất cả",
                    "Cao",
                    "Trung bình",
                    "Thấp",
                    "Chưa có score",
                ],
                key="delay_band",
            )

        with c2:
            min_score = st.slider(
                "Probability tối thiểu",
                0.0,
                1.0,
                0.0,
                0.05,
                key="delay_min_score",
            )

        filtered = projects.copy()

        if selected_band != "Tất cả":
            if selected_band == "Chưa có score":
                filtered = filtered[
                    filtered[DELAY_BAND_FIELD].fillna("") == ""
                ]
            else:
                filtered = filtered[
                    filtered[DELAY_BAND_FIELD] == selected_band
                ]

        filtered = filtered[
            filtered["delay_probability"].fillna(-1) >= min_score
        ]

        display = filtered[
            [
                "name",
                "project_type",
                "customer",
                "expected_start_date",
                "expected_end_date",
                DELAY_PROB_FIELD,
                DELAY_BAND_FIELD,
            ]
        ].copy()

        display["delay_probability"] = display[
            DELAY_PROB_FIELD
        ].apply(
            lambda x: f"{x:.2%}" if pd.notna(x) else "Chưa score"
        )

        st.write(f"Hiển thị **{len(display)}** Project")
        st.dataframe(
            display.drop(columns=[DELAY_PROB_FIELD]),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        st.markdown("### Score hàng loạt")

        pending_projects = projects.loc[
            projects[DELAY_BAND_FIELD].fillna("") == "",
            "name",
        ].dropna().tolist()

        st.info(
            f"Có **{len(pending_projects)}** Project chưa score. "
            "Bấm nút bên dưới để chạy toàn bộ."
        )

        if pending_projects:
            if st.button(
                f"Score tất cả {len(pending_projects)} Project chưa score",
                key="score_all_projects",
                type="primary",
            ):
                with st.spinner(
                    "Đang score các Project chưa score..."
                ):
                    batch_result = score_many(
                        pending_projects,
                        "/score_project_from_erpnext/{name}",
                        "Đang score Project",
                    )

                success_count = len(batch_result["results"])
                failure_count = len(batch_result["failures"])

                if success_count:
                    st.success(
                        f"Đã score thành công {success_count} Project."
                    )

                if failure_count:
                    st.warning(
                        f"Có {failure_count} Project không score được."
                    )
                    st.dataframe(
                        pd.DataFrame(batch_result["failures"]),
                        use_container_width=True,
                        hide_index=True,
                    )

                if success_count:
                    st.dataframe(
                        pd.DataFrame(batch_result["results"]),
                        use_container_width=True,
                        hide_index=True,
                    )

                st.cache_data.clear()

        else:
            st.success("Tất cả Project hiện đã có score.")

        st.divider()
        st.markdown("### Score lại một Project")

        project_names = projects["name"].dropna().tolist()

        if project_names:
            selected_project = st.selectbox(
                "Project",
                project_names,
                key="score_project_name",
            )

            if st.button(
                "Score Project",
                key="score_project",
                type="primary",
            ):
                try:
                    with st.spinner("Đang score Project..."):
                        result = call_fastapi_score(
                            f"/score_project_from_erpnext/{selected_project}"
                        )

                    st.success(
                        f"Đã score {selected_project}"
                    )
                    st.json(result)

                    st.cache_data.clear()

                except Exception as exc:
                    st.error(str(exc))


# ============================================================
# WIN
# ============================================================

with tab_win:
    st.subheader(" Win Probability")

    if opportunities.empty:
        st.info("Không có Opportunity.")
    else:
        c1, c2 = st.columns(2)

        with c1:
            selected_band = st.selectbox(
                "Lọc theo win band",
                [
                    "Tất cả",
                    "Cao",
                    "Trung bình",
                    "Thấp",
                    "Chưa có score",
                ],
                key="win_band",
            )

        with c2:
            min_probability = st.slider(
                "Probability tối thiểu",
                0.0,
                1.0,
                0.0,
                0.05,
                key="win_min_probability",
            )

        filtered = opportunities.copy()

        if selected_band != "Tất cả":
            if selected_band == "Chưa có score":
                filtered = filtered[
                    filtered[WIN_BAND_FIELD].fillna("") == ""
                ]
            else:
                filtered = filtered[
                    filtered[WIN_BAND_FIELD] == selected_band
                ]

        filtered = filtered[
            filtered["win_probability"].fillna(-1)
            >= min_probability
        ]

        display = filtered[
            [
                "name",
                "opportunity_from",
                "party_name",
                "transaction_date",
                "opportunity_amount",
                WIN_PROB_FIELD,
                WIN_BAND_FIELD,
            ]
        ].copy()

        display["opportunity_amount"] = display[
            "opportunity_amount"
        ].map(format_money)

        display["win_probability"] = display[
            WIN_PROB_FIELD
        ].apply(
            lambda x: f"{x:.2%}" if pd.notna(x) else "Chưa score"
        )

        st.write(
            f"Hiển thị **{len(display)}** Opportunity"
        )

        st.dataframe(
            display.drop(columns=[WIN_PROB_FIELD]),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        st.markdown("### Score hàng loạt")

        # Opportunity chưa score nhưng đã có ít nhất một Quotation
        pending_opportunities = opportunities.loc[
            opportunities[WIN_BAND_FIELD].fillna("").eq("")
            & opportunities["name"].isin(quotation_opportunities),
            "name",
        ].dropna().tolist()

        # Opportunity chưa score và chưa có Quotation
        pending_without_quotation = opportunities.loc[
            opportunities[WIN_BAND_FIELD].fillna("").eq("")
            & ~opportunities["name"].isin(quotation_opportunities),
            "name",
        ].dropna().tolist()

        st.info(
            f"Có **{len(pending_opportunities)}** Opportunity đủ điều kiện scoring "
            f"(đã có ít nhất 1 Quotation)."
        )

        if pending_without_quotation:
            st.caption(
                f"{len(pending_without_quotation)} Opportunity chưa có Quotation "
                "nên được bỏ qua."
            )

        if pending_opportunities:
            if st.button(
                f"Score tất cả {len(pending_opportunities)} Opportunity đủ điều kiện",
                key="score_all_opportunities",
                type="primary",
            ):
                with st.spinner(
                    "Đang score các Opportunity chưa score..."
                ):
                    batch_result = score_many(
                        pending_opportunities,
                        "/score_opportunity_from_erpnext/{name}",
                        "Đang score Opportunity",
                    )

                success_count = len(batch_result["results"])
                failure_count = len(batch_result["failures"])

                if success_count:
                    st.success(
                        f"Đã score thành công {success_count} Opportunity."
                    )

                if failure_count:
                    st.warning(
                        f"Có {failure_count} Opportunity không score được."
                    )
                    st.dataframe(
                        pd.DataFrame(batch_result["failures"]),
                        use_container_width=True,
                        hide_index=True,
                    )

                if success_count:
                    st.dataframe(
                        pd.DataFrame(batch_result["results"]),
                        use_container_width=True,
                        hide_index=True,
                    )

                st.cache_data.clear()

        else:
            st.success("Tất cả Opportunity hiện đã có score.")

        st.divider()
        st.markdown("### Score lại một Opportunity")

        opportunity_names = (
            opportunities["name"]
            .dropna()
            .tolist()
        )

        if opportunity_names:
            selected_opportunity = st.selectbox(
                "Opportunity",
                opportunity_names,
                key="score_opportunity_name",
            )

            if st.button(
                "Score Opportunity",
                key="score_opportunity",
                type="primary",
            ):
                try:
                    with st.spinner(
                        "Đang score Opportunity..."
                    ):
                        result = call_fastapi_score(
                            "/score_opportunity_from_erpnext/"
                            f"{selected_opportunity}"
                        )

                    st.success(
                        f"Đã score {selected_opportunity}"
                    )
                    st.json(result)

                    st.cache_data.clear()

                except Exception as exc:
                    st.error(str(exc))


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "DS-06 prototype • Scores displayed here are read from ERPNext. "
    "Prediction is performed by the FastAPI scoring service."
)
