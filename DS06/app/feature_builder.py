from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd


SMOOTHING_K = 5
OVERLOAD_THRESHOLD = 2

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


def is_open_at(
    alloc_subset: pd.DataFrame,
    as_of: pd.Timestamp,
) -> pd.Series:
    """True nếu allocation còn mở tại snapshot."""
    return (
        alloc_subset["actual_close_date"].isna()
        | (alloc_subset["actual_close_date"] > as_of)
    )


def n_open_for_person(
    disc_alloc: pd.DataFrame,
    assignee_id: str,
    as_of: pd.Timestamp,
    exclude_idx=None,
) -> int:
    """Đếm allocation đang mở của một nhân sự tại snapshot."""
    subset = disc_alloc[
        (disc_alloc["assignee_id"] == assignee_id)
        & (disc_alloc["start_date"] <= as_of)
    ]

    if exclude_idx is not None:
        subset = subset[subset.index != exclude_idx]

    return int(is_open_at(subset, as_of).sum())


def smoothed_rate(
    subset_closed_before_t: pd.DataFrame,
    global_rate: float,
    k: int = SMOOTHING_K,
) -> float:
    """Historic late rate với smoothing về global rate."""
    n = len(subset_closed_before_t)

    if n == 0:
        return float(global_rate)

    late = subset_closed_before_t["was_late"].sum()

    return float(
        (late + k * global_rate)
        / (n + k)
    )


def _prepare_data(bundle: Dict[str, Any]):
    """
    Chuyển raw ERPNext response thành DataFrame tương thích với DS-04.

    bundle:
        project       : project đang được score
        projects      : toàn bộ project metadata
        assignments   : toàn bộ Design Discipline Assignment
        allocations   : toàn bộ Discipline Allocation
        sales_orders  : toàn bộ submitted Sales Order
    """

    project_raw = bundle["project"]
    projects_raw = bundle.get("projects")

    assignments = bundle["assignments"]
    allocations = bundle["allocations"]
    sales_orders = bundle["sales_orders"]

    # ---------------------------------------------------------
    # Project metadata
    # ---------------------------------------------------------

    if projects_raw is None:
        # Fallback để code không crash nếu bundle cũ được truyền vào.
        # Production bundle mới phải có "projects".
        projects_raw = [project_raw]

    projects = pd.DataFrame(projects_raw)

    projects = projects.rename(
        columns={
            "name": "project_id",
            "customer": "customer_id",
        }
    )

    for col in [
        "project_id",
        "project_type",
        "expected_start_date",
        "expected_end_date",
        "customer_id",
    ]:
        if col not in projects.columns:
            projects[col] = np.nan

    # ---------------------------------------------------------
    # Design Discipline Assignment
    # ---------------------------------------------------------

    dda = pd.DataFrame(assignments)

    if dda.empty:
        raise ValueError(
            "No Design Discipline Assignment found in ERPNext."
        )

    dda = dda[
        [
            "name",
            "project",
            "project_manager",
        ]
    ].copy()

    # ---------------------------------------------------------
    # Discipline Allocation
    # ---------------------------------------------------------

    disc_alloc = pd.DataFrame(allocations)

    if disc_alloc.empty:
        raise ValueError(
            "No Discipline Allocation found in ERPNext."
        )

    disc_alloc = disc_alloc[
        [
            "name",
            "parent",
            "employee",
            "discipline",
            "workload_percent",
            "planned_hours",
            "start_date",
            "end_date",
            "actual_hours",
            "actual_close_date",
        ]
    ].copy()

    # Allocation -> Design Discipline Assignment
    disc_alloc = disc_alloc.merge(
        dda,
        left_on="parent",
        right_on="name",
        how="inner",
        suffixes=("", "_dda"),
    )

    disc_alloc = disc_alloc.rename(
        columns={
            "project": "project_id",
            "employee": "assignee_id",
            "project_manager": "pm_id",
        }
    )

    # ---------------------------------------------------------
    # Contract value theo từng project
    # ---------------------------------------------------------

    so = pd.DataFrame(sales_orders)

    if so.empty:
        contract_value_by_project = pd.Series(
            dtype=float,
            name="contract_value",
        )
    else:
        so = so.copy()

        so["grand_total"] = pd.to_numeric(
            so["grand_total"],
            errors="coerce",
        ).fillna(0.0)

        so["docstatus"] = pd.to_numeric(
            so["docstatus"],
            errors="coerce",
        )

        submitted_so = so[
            so["docstatus"] == 1
        ].copy()

        contract_value_by_project = (
            submitted_so
            .groupby("project")["grand_total"]
            .sum()
            .rename("contract_value")
        )

    projects = projects.merge(
        contract_value_by_project,
        left_on="project_id",
        right_index=True,
        how="left",
    )

    projects["contract_value"] = (
        pd.to_numeric(
            projects["contract_value"],
            errors="coerce",
        )
        .fillna(0.0)
    )

    # ---------------------------------------------------------
    # Date normalization
    # ---------------------------------------------------------

    for col in [
        "start_date",
        "end_date",
        "actual_close_date",
    ]:
        disc_alloc[col] = pd.to_datetime(
            disc_alloc[col],
            errors="coerce",
        )

    for col in [
        "expected_start_date",
        "expected_end_date",
    ]:
        projects[col] = pd.to_datetime(
            projects[col],
            errors="coerce",
        )

    return projects, disc_alloc


def build_delay_features(
    bundle: Dict[str, Any],
) -> pd.DataFrame:
    """
    Build Delay Risk features at discipline level.

    Output:
        1 row = 1 (project, discipline)

    Snapshot:
        Discipline Allocation.start_date
    """

    projects, disc_alloc = _prepare_data(bundle)

    projects_idx = projects.set_index("project_id")

    # ---------------------------------------------------------
    # Add customer_id to allocations
    # ---------------------------------------------------------

    if "customer_id" not in disc_alloc.columns:
        disc_alloc = disc_alloc.merge(
            projects[
                [
                    "project_id",
                    "customer_id",
                ]
            ],
            on="project_id",
            how="left",
        )

    if "pm_id" not in disc_alloc.columns:
        raise ValueError(
            "pm_id is missing after DDA join."
        )

    # ---------------------------------------------------------
    # Historical closed allocations
    # ---------------------------------------------------------

    past_closed_all = disc_alloc[
        disc_alloc["actual_close_date"].notna()
    ].copy()

    past_closed_all["was_late"] = (
        past_closed_all["actual_close_date"]
        > past_closed_all["end_date"]
    )

    out_rows = []

    # ---------------------------------------------------------
    # Snapshot feature construction
    # ---------------------------------------------------------

    for idx, row in disc_alloc.iterrows():

        as_of = row["start_date"]

        if pd.isna(as_of):
            raise ValueError(
                f"Allocation {row['name']} has no start_date."
            )

        project_id = row["project_id"]

        if project_id not in projects_idx.index:
            raise ValueError(
                f"Project {project_id} not found."
            )

        proj = projects_idx.loc[project_id]

        # -----------------------------------------------------
        # planned_duration_days
        # -----------------------------------------------------

        planned_duration_days = (
            proj["expected_end_date"]
            - proj["expected_start_date"]
        ).days

        # -----------------------------------------------------
        # n_disciplines_known_at_snapshot
        # -----------------------------------------------------

        same_proj_all = disc_alloc[
            disc_alloc["project_id"] == project_id
        ]

        n_disciplines_known_at_snapshot = int(
            (
                same_proj_all["start_date"]
                <= as_of
            ).sum()
        )

        # -----------------------------------------------------
        # n_open_disciplines_at_snapshot
        # -----------------------------------------------------

        n_open = n_open_for_person(
            disc_alloc,
            row["assignee_id"],
            as_of,
            exclude_idx=idx,
        )

        # -----------------------------------------------------
        # total_workload_pct
        # -----------------------------------------------------

        total_assigned_so_far = int(
            (
                (disc_alloc["assignee_id"] == row["assignee_id"])
                & (disc_alloc["start_date"] <= as_of)
            ).sum()
        )

        total_workload_pct = (
            n_open
            / max(total_assigned_so_far, 1)
        )

        # -----------------------------------------------------
        # n_open_overdue_tasks_at_snapshot
        #
        # Giữ nguyên logic DS-04:
        # Discipline Allocation khác trong cùng project,
        # đã quá end_date nhưng vẫn đang mở tại snapshot.
        # -----------------------------------------------------

        same_proj_others = disc_alloc[
            (disc_alloc["project_id"] == project_id)
            & (disc_alloc.index != idx)
        ]

        overdue_mask = (
            (same_proj_others["end_date"] < as_of)
            & is_open_at(
                same_proj_others,
                as_of,
            )
        )

        n_open_overdue = int(
            overdue_mask.sum()
        )

        # -----------------------------------------------------
        # pct_staff_overloaded_at_snapshot
        # -----------------------------------------------------

        active_staff = disc_alloc.loc[
            disc_alloc["start_date"] <= as_of,
            "assignee_id",
        ].dropna().unique()

        if len(active_staff) > 0:

            overloaded_count = sum(
                1
                for staff_id in active_staff
                if n_open_for_person(
                    disc_alloc,
                    staff_id,
                    as_of,
                ) > OVERLOAD_THRESHOLD
            )

            pct_staff_overloaded_at_snapshot = (
                overloaded_count
                / len(active_staff)
            )

        else:
            pct_staff_overloaded_at_snapshot = np.nan

        # -----------------------------------------------------
        # Historic rates
        # -----------------------------------------------------

        closed_before_t = past_closed_all[
            past_closed_all["actual_close_date"] <= as_of
        ]

        global_rate = (
            float(closed_before_t["was_late"].mean())
            if len(closed_before_t) > 0
            else 0.5
        )

        pm_subset = closed_before_t[
            closed_before_t["pm_id"]
            == row["pm_id"]
        ]

        pm_historic_late_rate = smoothed_rate(
            pm_subset,
            global_rate,
        )

        cust_subset = closed_before_t[
            closed_before_t["customer_id"]
            == row["customer_id"]
        ]

        customer_historic_late_rate = smoothed_rate(
            cust_subset,
            global_rate,
        )

        # -----------------------------------------------------
        # Output
        # -----------------------------------------------------

        out_rows.append(
            {
                "project_id": project_id,
                "discipline": row["discipline"],
                "assignee_id": row["assignee_id"],
                "as_of_date": as_of,
                "project_type": proj["project_type"],
                "contract_value": proj["contract_value"],
                "planned_duration_days": planned_duration_days,
                "n_disciplines_known_at_snapshot": (
                    n_disciplines_known_at_snapshot
                ),
                "n_open_disciplines_at_snapshot": n_open,
                "total_workload_pct": total_workload_pct,
                "pct_staff_overloaded_at_snapshot": (
                    pct_staff_overloaded_at_snapshot
                ),
                "n_open_overdue_tasks_at_snapshot": (
                    n_open_overdue
                ),
                "pm_historic_late_rate": (
                    pm_historic_late_rate
                ),
                "customer_historic_late_rate": (
                    customer_historic_late_rate
                ),
            }
        )

    features = pd.DataFrame(out_rows)

    # ---------------------------------------------------------
    # Chỉ trả về feature rows của project đang được score
    #
    # Toàn bộ projects / allocations vẫn được sử dụng ở trên
    # để tính historical và workload features.
    # ---------------------------------------------------------

    target_project_id = bundle["project"]["name"]

    features = features[
        features["project_id"] == target_project_id
    ].copy()

    if features.empty:
        raise ValueError(
            f"No Delay Risk feature rows found for target project "
            f"{target_project_id}."
        )

    # ---------------------------------------------------------
    # Model input validation
    # ---------------------------------------------------------

    missing = [
        col
        for col in DELAY_FEATURES
        if col not in features.columns
    ]

    if missing:
        raise ValueError(
            f"Missing Delay Risk features: {missing}"
        )

    return features

