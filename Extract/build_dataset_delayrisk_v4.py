"""
extract.py — Trích xuất + build nhãn cho bài toán Delay Risk (đơn vị: Project-Discipline)
v2 — sửa theo feedback rà soát (xem CHANGELOG cuối file)

Đơn vị phân tích: 1 dòng = 1 cặp (project, discipline), snapshot tại ngày bộ môn đó
bắt đầu (Discipline Allocation.start_date).

CHẾ ĐỘ CHẠY:
- Mặc định dùng dữ liệu MÔ PHỎNG (generate_mock_data) để kiểm thử pipeline.
- Khi có dữ liệu thật từ API (đã được cấp quyền), dùng load_from_erpnext_api() —
  xem hướng dẫn chi tiết ở cuối file, phần "HƯỚNG DẪN DÙNG API THẬT".

QUAN TRỌNG — nhãn mô phỏng KHÔNG mang tín hiệu thật (xem CHANGELOG mục 3):
`is_late = rng.random() < 0.30` sinh độc lập hoàn toàn với mọi feature. Vì vậy AUC
của mọi model chạy trên dữ liệu mô phỏng này sẽ luôn xấp xỉ 0.5, BẤT KỂ feature engineering
đúng hay sai. Mục đích duy nhất của phần mô phỏng là kiểm thử pipeline (không lỗi, không
rò rỉ, ra đúng shape dữ liệu) — không dùng kết quả AUC ở đây để đánh giá chất lượng feature.
Khi có dữ liệu thật (đã có), thay load_data() bằng load_from_erpnext_api().
"""

import os
import numpy as np
import pandas as pd
from dotenv import load_dotenv
 
load_dotenv()
from datetime import timedelta

RNG_SEED = 42
RANDOM_STATE = RNG_SEED
rng = np.random.default_rng(RNG_SEED)

DISCIPLINES = [
    "Tổng mặt bằng", "Kiến trúc", "Kết cấu", "Cơ điện nước", "Điện nhẹ",
    "PCCC", "Điều hoà thông gió", "Thuyết minh thiết kế", "Phụ lục tính toán",
    "Quy trình bảo trì", "Dự toán thiết kế",
]

# ---------------------------------------------------------------------------
# CẤU HÌNH KẾT NỐI API THẬT
# ---------------------------------------------------------------------------
# Đặt USE_REAL_DATA = True để chạy bằng dữ liệu ERPNext thật (qua API), hoặc
# False để chạy bằng dữ liệu mô phỏng (mặc định, để kiểm thử pipeline).
USE_REAL_DATA = True

ERPNEXT_BASE_URL = os.environ.get("ERPNEXT_BASE_URL", "")
ERPNEXT_API_KEY = os.environ.get("ERPNEXT_API_KEY", "")
ERPNEXT_API_SECRET = os.environ.get("ERPNEXT_API_SECRET", "")

# NGÀY RÚT DỮ LIỆU — cố định giá trị này (không để trống/dấu ba chấm), vì đây là
# mốc "hôm nay" dùng để tách right-censored và tính n_open_*. Ghi cứng để mọi lần
# chạy lại đều tái lập đúng cùng một tập dữ liệu/kết quả. Khi pull dữ liệu thật,
# ĐỔI GIÁ TRỊ NÀY thành đúng NGÀY THỰC SỰ chạy script lấy dữ liệu (hôm nay), rồi
# ghi giá trị đó vào báo cáo.
DATA_CUTOFF = pd.Timestamp("2026-08-18")

# Ngưỡng "quá tải" (số bộ môn đang mở song song). Đây là giá trị TẠM, cần thống nhất
# lại với trưởng bộ phận thiết kế trước khi dùng cho báo cáo chính thức.
OVERLOAD_THRESHOLD = 2

# Hệ số làm mượt (Điểm 4) cho historic_late_rate — xem hàm smoothed_rate().
SMOOTHING_K = 5


# ---------------------------------------------------------------------------
# 1a. MÔ PHỎNG DỮ LIỆU — chỉ để kiểm thử pipeline, KHÔNG dùng để đánh giá feature
# ---------------------------------------------------------------------------

def generate_mock_projects(n_projects: int = 59) -> pd.DataFrame:
    """Quy mô mô phỏng theo đúng số liệu thật đã có: 59 dự án."""
    start_dates = pd.to_datetime("2024-01-01") + pd.to_timedelta(
        rng.integers(0, 600, size=n_projects), unit="D"
    )
    planned_duration = rng.integers(60, 400, size=n_projects)
    project_types = rng.choice(["Dân dụng", "Hạ tầng kỹ thuật", "Giao thông", "Thuỷ lợi"], n_projects)
    # contract_value mô phỏng ở đây là placeholder — dữ liệu thật phải CỘNG DỒN từ các
    # Sales Order đã submit gắn với project đó (một project có thể nhiều hợp đồng),
    # không đọc trực tiếp 1 field trên Project (xem load_from_erpnext_api).
    contract_value = rng.integers(500, 20000, size=n_projects) * 1_000_000

    df = pd.DataFrame({
        "project_id": [f"PRJ-{i:04d}" for i in range(n_projects)],
        "project_type": project_types,
        "expected_start_date": start_dates,
        "expected_end_date": start_dates + pd.to_timedelta(planned_duration, unit="D"),
        "contract_value": contract_value,
        "pm_id": rng.choice([f"PM-{i:02d}" for i in range(8)], n_projects),
        "customer_id": rng.choice([f"CUST-{i:02d}" for i in range(12)], n_projects),
    })
    return df


def generate_mock_discipline_allocations(projects: pd.DataFrame) -> pd.DataFrame:
    """
    Mô phỏng Discipline Allocation — quy mô nhắm tới ~620 dòng, ~320 dòng đã có
    actual_close_date, khớp số liệu thật đã cung cấp, để kiểm thử pipeline ở đúng
    tỷ lệ đóng/mở gần với thực tế.

    LƯU Ý VỀ NHÃN MÔ PHỎNG: is_late được random độc lập với mọi feature — chỉ để
    kiểm thử pipeline chạy đúng, không mang tín hiệu thống kê thật. Xem docstring
    đầu file.
    """
    rows = []
    for _, proj in projects.iterrows():
        n_disc = rng.integers(6, len(DISCIPLINES) + 1)
        chosen = rng.choice(DISCIPLINES, size=n_disc, replace=False)
        proj_span = (proj["expected_end_date"] - proj["expected_start_date"]).days
        for disc in chosen:
            offset_start = rng.integers(0, max(int(proj_span * 0.6), 1))
            disc_duration = rng.integers(20, max(int(proj_span * 0.5), 21))
            planned_start = proj["expected_start_date"] + timedelta(days=int(offset_start))
            planned_end = planned_start + timedelta(days=int(disc_duration))

            # is_late: HOÀN TOÀN NGẪU NHIÊN, không phụ thuộc feature nào (xem lưu ý trên)
            is_late = rng.random() < 0.30
            delay_days = int(rng.integers(5, 60)) if is_late else int(rng.integers(-10, 0))
            actual_close = planned_end + timedelta(days=delay_days)

            # ~48% bộ môn vẫn đang mở tại DATA_CUTOFF, khớp tỷ lệ 320/620 đã đóng
            if rng.random() < 0.48 or actual_close > DATA_CUTOFF:
                actual_close_date = pd.NaT
                actual_hours = np.nan
            else:
                actual_close_date = actual_close
                actual_hours = rng.integers(40, 400)

            rows.append({
                "project_id": proj["project_id"],
                "discipline": disc,
                "assignee_id": f"STAFF-{rng.integers(0, 25):02d}",
                "start_date": planned_start,
                "end_date": planned_end,
                "actual_close_date": actual_close_date,
                "actual_hours": actual_hours,
            })
    return pd.DataFrame(rows)


def load_mock_data():
    projects = generate_mock_projects()
    disc_alloc = generate_mock_discipline_allocations(projects)
    return projects, disc_alloc


# ---------------------------------------------------------------------------
# 1b. TẢI DỮ LIỆU THẬT QUA API — xem "HƯỚNG DẪN DÙNG API THẬT" ở cuối file
# ---------------------------------------------------------------------------

def load_from_erpnext_api(base_url: str, api_key: str, api_secret: str):
    """
    Scaffold gọi API thật. KHÔNG chạy mặc định (cần base_url/key/secret thật).
    Xem hướng dẫn sử dụng chi tiết ở cuối file — phần "HƯỚNG DẪN DÙNG API THẬT".
    """
    import json
    import requests

    headers = {"Authorization": f"token {api_key}:{api_secret}"}

    def fetch(doctype, fields, parent=None, filters=None):
        params = {"limit_page_length": 0, "fields": json.dumps(fields)}
        if parent:
            params["parent"] = parent
        if filters:
            params["filters"] = json.dumps(filters)
        r = requests.get(f"{base_url}/api/resource/{doctype}", headers=headers, params=params, timeout=120)
        r.raise_for_status()
        return pd.DataFrame(r.json()["data"])

    # Discipline Allocation là child table -> BẮT BUỘC có parent, nếu không sẽ báo
    # lỗi permission (không phải lỗi phân quyền thật, chỉ là cách Frappe chặn child table).
    alloc = fetch("Discipline Allocation", [
        "name", "parent", "employee", "discipline", "workload_percent",
        "planned_hours", "start_date", "end_date", "actual_hours", "actual_close_date",
    ], parent="Design Discipline Assignment")

    dda = fetch("Design Discipline Assignment", ["name", "project", "project_manager"])

    disc_alloc = alloc.merge(
        dda, left_on="parent", right_on="name", suffixes=("", "_dda")
    ).rename(columns={"project": "project_id", "employee": "assignee_id", "project_manager": "pm_id"})

    projects_raw = fetch("Project", ["name", "project_type", "expected_start_date", "expected_end_date", "customer"])
    projects_raw = projects_raw.rename(columns={"name": "project_id", "customer": "customer_id"})

    # contract_value KHÔNG đọc trực tiếp từ Project — phải cộng dồn Sales Order đã submit
    # vì một dự án có thể có nhiều hợp đồng.
    sales_orders = fetch("Sales Order", ["project", "grand_total", "docstatus"],
                          filters=[["docstatus", "=", 1]])
    contract_value_by_project = (
        sales_orders.groupby("project")["grand_total"].sum().rename("contract_value")
    )
    projects = projects_raw.merge(contract_value_by_project, left_on="project_id", right_index=True, how="left")
    projects["contract_value"] = projects["contract_value"].fillna(0)

    for col in ["start_date", "end_date", "actual_close_date"]:
        disc_alloc[col] = pd.to_datetime(disc_alloc[col], errors="coerce")
    for col in ["expected_start_date", "expected_end_date"]:
        projects[col] = pd.to_datetime(projects[col], errors="coerce")

    # DATA QUALITY GUARD — một actual_close_date không thể xảy ra trước start_date.
    # Lỗi patch lịch trước đây có thể để lại ngày đóng cũ khi dòng chuyển
    # Completed -> Open. Những ngày đóng < start_date là bằng chứng của stale
    # actual_close_date, không phải một completion hợp lệ.
    invalid_close = (
        disc_alloc["actual_close_date"].notna()
        & disc_alloc["start_date"].notna()
        & (disc_alloc["actual_close_date"] < disc_alloc["start_date"])
    )
    n_invalid_close = int(invalid_close.sum())

    print(
        f"[DATA QUALITY] actual_close_date < start_date: "
        f"{n_invalid_close} dòng"
    )

    if n_invalid_close > 0:
        disc_alloc.loc[invalid_close, "actual_close_date"] = pd.NaT
        # actual_hours là kết quả đóng mốc; khi ngày đóng bị xóa vì stale
        # completion thì effort cuối mốc cũng không được coi là completion.
        if "actual_hours" in disc_alloc.columns:
            disc_alloc.loc[invalid_close, "actual_hours"] = np.nan

    remaining_invalid_close = (
        disc_alloc["actual_close_date"].notna()
        & disc_alloc["start_date"].notna()
        & (disc_alloc["actual_close_date"] < disc_alloc["start_date"])
    )
    assert not remaining_invalid_close.any(), (
        "DATA QUALITY ERROR: vẫn còn actual_close_date < start_date "
        "sau khi chuẩn hóa."
    )

    return projects, disc_alloc


# ---------------------------------------------------------------------------
# 2. BUILD NHÃN — dùng chung logic đã tách riêng + có unit test ở build_labels.py
# ---------------------------------------------------------------------------
# Không định nghĩa lại build_label() ở đây nữa (tránh trùng lặp code với 2 nguồn sự
# thật khác nhau) — import thẳng từ build_labels.py. File này PHẢI nằm cùng thư mục
# với extract.py, nếu không sẽ báo lỗi "ModuleNotFoundError: No module named 'build_labels'".
from build_labels_delayrisk_v1 import build_label  # noqa: E402 (import sau code khác vì cần pd đã import ở trên)


# ---------------------------------------------------------------------------
# 3. FEATURE HELPERS
# ---------------------------------------------------------------------------

def is_open_at(alloc_subset: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    """True nếu bản ghi đang mở tại as_of: chưa đóng, hoặc đóng sau as_of."""
    return alloc_subset["actual_close_date"].isna() | (alloc_subset["actual_close_date"] > as_of)


def n_open_for_person(disc_alloc: pd.DataFrame, assignee_id: str, as_of: pd.Timestamp,
                       exclude_idx=None) -> int:
    subset = disc_alloc[(disc_alloc["assignee_id"] == assignee_id) & (disc_alloc["start_date"] <= as_of)]
    if exclude_idx is not None:
        subset = subset[subset.index != exclude_idx]
    return int(is_open_at(subset, as_of).sum())


def smoothed_rate(subset_closed_before_T: pd.DataFrame, global_rate: float, k: int = SMOOTHING_K) -> float:
    """
    Điểm 4 — xử lý NaN / nhiễu ở historic rate bằng smoothing về giá trị trung bình
    chung, có ngưỡng: n càng nhỏ, kết quả càng bị kéo về global_rate; n=0 trả thẳng
    global_rate (không NaN). k=5 tương đương "cần ~5 quan sát mới tin số riêng hơn
    là tin số chung" — hệ số này cần tinh chỉnh lại khi có đủ dữ liệu thật.
    """
    n = len(subset_closed_before_T)
    if n == 0:
        return global_rate
    late = subset_closed_before_T["was_late"].sum()
    return (late + k * global_rate) / (n + k)


# ---------------------------------------------------------------------------
# 4. TÍNH FEATURE — mỗi feature đều tự hỏi "tại as_of, thông tin này đã tồn tại chưa?"
# ---------------------------------------------------------------------------

def compute_features(disc_alloc: pd.DataFrame, projects: pd.DataFrame,
                      cutoff: pd.Timestamp = DATA_CUTOFF) -> pd.DataFrame:
    projects_idx = projects.set_index("project_id")

    # Chuẩn hoá pm_id/customer_id ngay tại disc_alloc, không phụ thuộc việc 2 field
    # này nằm ở bảng nào của nguồn dữ liệu (mock: cả 2 nằm ở projects; dữ liệu thật:
    # pm_id nằm sẵn ở disc_alloc do join từ Design Discipline Assignment, chỉ
    # customer_id nằm ở projects) — merge bù cái nào còn thiếu.
    disc_alloc = disc_alloc.copy()
    if "pm_id" not in disc_alloc.columns:
        disc_alloc = disc_alloc.merge(projects[["project_id", "pm_id"]], on="project_id", how="left")
    if "customer_id" not in disc_alloc.columns:
        disc_alloc = disc_alloc.merge(projects[["project_id", "customer_id"]], on="project_id", how="left")

    # past_closed_all: TOÀN BỘ bản ghi đã đóng trong toàn hệ thống, kèm was_late — tính
    # 1 LẦN ngoài vòng lặp (Điểm II.1), không tính lại ở mỗi dòng. disc_alloc ở đây đã
    # chắc chắn có sẵn pm_id/customer_id sau bước chuẩn hoá trên, không cần merge lại.
    past_closed_all = disc_alloc[disc_alloc["actual_close_date"].notna()].copy()
    past_closed_all["was_late"] = past_closed_all["actual_close_date"] > past_closed_all["end_date"]

    out_rows = []

    for idx, row in disc_alloc.iterrows():
        as_of = row["start_date"]
        proj = projects_idx.loc[row["project_id"]]

        # --- static project-level (biết ngay từ lúc mở dự án, chắc chắn hợp lệ) ---
        planned_duration_days = (proj["expected_end_date"] - proj["expected_start_date"]).days

        # --- n_disciplines_known_at_snapshot: SỬA — chỉ đếm bộ môn đã start_date <= as_of,
        # không đếm toàn bộ bộ môn của dự án như bản trước (bản trước đếm cả bộ môn sẽ bắt
        # đầu SAU as_of của dòng đang xét -> rò rỉ nhẹ tương tự lỗi ở n_open_overdue). Đây là
        # lựa chọn AN TOÀN theo cùng nguyên tắc "phân công chưa chắc ổn định" đã nêu trong
        # feature_dictionary.md; nếu xác nhận được toàn bộ danh mục bộ môn chốt 1 lần lúc mở
        # dự án, có thể đổi lại dùng tổng số cố định.
        same_proj_all = disc_alloc[disc_alloc["project_id"] == row["project_id"]]
        n_disciplines_known_at_snapshot = (same_proj_all["start_date"] <= as_of).sum()

        # --- n_open_disciplines_at_snapshot (đã đúng từ bản trước, giữ nguyên logic) ---
        other_rows = disc_alloc[
            (disc_alloc["assignee_id"] == row["assignee_id"]) & (disc_alloc.index != idx)
        ]
        n_open = n_open_for_person(disc_alloc, row["assignee_id"], as_of, exclude_idx=idx)
        total_assigned_so_far = ((disc_alloc["assignee_id"] == row["assignee_id"]) &
                                  (disc_alloc["start_date"] <= as_of)).sum()  # gồm cả dòng hiện tại

        # total_workload_pct (ĐIỂM II.3 — trước đây tài liệu có mô tả nhưng code chưa tính)
        total_workload_pct = n_open / max(total_assigned_so_far, 1)

        # --- n_open_overdue_tasks_at_snapshot — SỬA THEO ĐIỂM I.1 ---
        # Gộp về ĐÚNG MỘT điều kiện duy nhất, không phân 2 nhánh như bản trước:
        #   end_date < as_of  AND  (actual_close_date IS NULL OR actual_close_date > as_of)
        # Tức là: tại as_of, bản ghi đã quá hạn kế hoạch VÀ CÒN ĐANG MỞ tại đúng as_of.
        # Không quan tâm bản ghi đó SAU NÀY đóng đúng hay đóng muộn — vì tại as_of ta
        # không thể biết trước điều đó (đó chính là lỗi rò rỉ ở bản cũ).
        same_proj_others = disc_alloc[
            (disc_alloc["project_id"] == row["project_id"]) & (disc_alloc.index != idx)
        ]
        overdue_mask = (same_proj_others["end_date"] < as_of) & is_open_at(same_proj_others, as_of)
        n_open_overdue = int(overdue_mask.sum())

        # --- pct_staff_overloaded_at_snapshot (ĐIỂM II.3 — bổ sung tính toán) ---
        # % nhân sự (đã có hoạt động tính đến as_of) có n_open vượt ngưỡng quá tải.
        active_staff = disc_alloc.loc[disc_alloc["start_date"] <= as_of, "assignee_id"].unique()
        if len(active_staff) > 0:
            overloaded_count = sum(
                1 for s in active_staff
                if n_open_for_person(disc_alloc, s, as_of) > OVERLOAD_THRESHOLD
            )
            pct_staff_overloaded_at_snapshot = overloaded_count / len(active_staff)
        else:
            pct_staff_overloaded_at_snapshot = np.nan

        # --- historic late rate — ĐIỂM 4: smoothing thay vì để NaN thô ---
        # Dùng row["pm_id"]/row["customer_id"] (đã chuẩn hoá ở disc_alloc), KHÔNG dùng
        # proj["pm_id"] vì bảng projects (Project doctype) không có cột này ở dữ liệu thật.
        closed_before_T = past_closed_all[past_closed_all["actual_close_date"] <= as_of]
        global_rate = closed_before_T["was_late"].mean() if len(closed_before_T) > 0 else 0.5

        pm_subset = closed_before_T[closed_before_T["pm_id"] == row["pm_id"]]
        pm_historic_late_rate = smoothed_rate(pm_subset, global_rate)

        cust_subset = closed_before_T[closed_before_T["customer_id"] == row["customer_id"]]
        customer_historic_late_rate = smoothed_rate(cust_subset, global_rate)

        label, censor_status = build_label(row, cutoff)

        out_rows.append({
            "project_id": row["project_id"],
            "discipline": row["discipline"],
            "assignee_id": row["assignee_id"],
            "as_of_date": as_of,
            "project_type": proj["project_type"],
            "contract_value": proj["contract_value"],
            "planned_duration_days": planned_duration_days,
            "n_disciplines_known_at_snapshot": n_disciplines_known_at_snapshot,
            "n_open_disciplines_at_snapshot": n_open,
            "total_workload_pct": total_workload_pct,
            "pct_staff_overloaded_at_snapshot": pct_staff_overloaded_at_snapshot,
            "n_open_overdue_tasks_at_snapshot": n_open_overdue,
            "pm_historic_late_rate": pm_historic_late_rate,
            "customer_historic_late_rate": customer_historic_late_rate,
            "label": label,
            "end_date": row["end_date"],
            "censor_status": censor_status,
        })

    return pd.DataFrame(out_rows)


# ---------------------------------------------------------------------------
# 5. CHIA TẬP — holdout ngẫu nhiên theo NHÓM project_id
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 5. CHIA TẬP — holdout ngẫu nhiên theo NHÓM project_id
# ---------------------------------------------------------------------------

def group_random_split(
    dataset: pd.DataFrame,
    test_frac: float = 0.3,
    random_state: int = RANDOM_STATE,
):
    """
    Random holdout at PROJECT level.

    All disciplines belonging to one project stay on the same side, so the
    primary holdout still prevents project leakage. Unlike the previous
    "latest projects" split, test projects are not selected by time.

    Project assignment is performed on the FULL population before censored rows
    are removed, so the same project groups are used for the censoring audit and
    the model train/test evaluation.
    """
    project_ids = pd.Series(dataset["project_id"].dropna().unique())
    n_test_projects = max(1, int(len(project_ids) * test_frac))

    rng_local = np.random.default_rng(random_state)
    shuffled_ids = project_ids.iloc[
        rng_local.permutation(len(project_ids))
    ].tolist()

    test_project_ids = set(shuffled_ids[:n_test_projects])
    train_project_ids = set(shuffled_ids[n_test_projects:])

    assert train_project_ids.isdisjoint(test_project_ids)

    is_test = dataset["project_id"].isin(test_project_ids)
    train = dataset[~is_test].copy()
    test = dataset[is_test].copy()

    return train, test


# ---------------------------------------------------------------------------
# 6. ĐO MỨC LỆCH DO LOẠI RIGHT-CENSORED
# ---------------------------------------------------------------------------

def report_censoring_bias(dataset: pd.DataFrame, train_projects=None, test_projects=None):
    """
    Audit right-censoring toàn pool và, quan trọng hơn, so sánh censoring giữa
    hai nhóm project của primary train/test split.

    Train/test CSV đã loại true-censored, nên phép kiểm phải quay lại FULL
    population theo project_id để quan sát các dòng bị cắt khỏi mỗi nhóm.
    """
    total = len(dataset)
    counts = dataset["censor_status"].value_counts(dropna=False)
    censored = counts.get("censored", 0)

    print("== Censoring audit — full population ==")
    print("Total:", total)
    print(counts.to_string())
    print(f"Censored thật sự: {censored} / {total} = {censored/total:.1%}")

    if train_projects is None or test_projects is None:
        return

    train_group = dataset[dataset["project_id"].isin(train_projects)].copy()
    test_group = dataset[dataset["project_id"].isin(test_projects)].copy()

    rows = []
    for group_name, group_df in [("train projects", train_group), ("test projects", test_group)]:
        cens_mask = group_df["censor_status"].eq("censored")
        trainable = group_df[group_df["label"].notna()].copy()

        rows.append({
            "group": group_name,
            "projects": group_df["project_id"].nunique(),
            "full_rows": len(group_df),
            "censored_rows": int(cens_mask.sum()),
            "censored_rate": float(cens_mask.mean()) if len(group_df) else np.nan,
            "trainable_rows": len(trainable),
            "positive_rate": float(trainable["label"].astype(int).mean())
                if len(trainable) else np.nan,
        })

    audit = pd.DataFrame(rows)

    print("\n== Train/Test censoring & label distribution audit ==")
    print(audit.to_string(index=False))

    train_cens = audit.loc[audit["group"] == "train projects", "censored_rate"].iloc[0]
    test_cens = audit.loc[audit["group"] == "test projects", "censored_rate"].iloc[0]

    print(
        f"Chênh lệch tỷ lệ censored: "
        f"{train_cens:.1%} (train) → {test_cens:.1%} (test)"
    )
    print(
        f"Tỷ lệ censored của test tương đương khoảng "
        f"{test_cens:.1%} ≈ {test_cens*10:.1f}/10 quan sát trong test-group."
    )

    return audit


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print(f"DATA_CUTOFF (ngày rút dữ liệu, cố định để tái lập): {DATA_CUTOFF.date()}")
    if USE_REAL_DATA:
        if not (ERPNEXT_BASE_URL and ERPNEXT_API_KEY and ERPNEXT_API_SECRET):
            raise RuntimeError(
                "USE_REAL_DATA=True nhưng thiếu biến môi trường ERPNEXT_BASE_URL/"
                "ERPNEXT_API_KEY/ERPNEXT_API_SECRET. Set 3 biến này trước khi chạy "
                "(PowerShell: $env:ERPNEXT_API_KEY=\"...\"), không hard-code vào file."
            )
        print("[CHẾ ĐỘ] Đang tải dữ liệu THẬT từ ERPNext qua API...\n")
        projects, disc_alloc = load_from_erpnext_api(
            base_url=ERPNEXT_BASE_URL,
            api_key=ERPNEXT_API_KEY,
            api_secret=ERPNEXT_API_SECRET,
        )
        print(f"Đã tải: {len(projects)} project, {len(disc_alloc)} dòng Discipline Allocation")
        print("Đối chiếu số liệu tham khảo: kỳ vọng ~59 project, ~620 dòng (320 đã có actual_close_date).")
        print("Nếu lệch nhiều so với số trên, kiểm tra lại bước merge/filter trước khi tin dữ liệu.\n")
    else:
        print("[LƯU Ý] Đang chạy bằng DỮ LIỆU MÔ PHỎNG — nhãn ngẫu nhiên, AUC sẽ ~0.5, "
              "không dùng để đánh giá chất lượng feature. Xem docstring đầu file.\n")
        projects, disc_alloc = load_mock_data()

    dataset = compute_features(disc_alloc, projects, cutoff=DATA_CUTOFF)

    print(f"Tổng số dòng (project-discipline): {len(dataset)}")

    # PRIMARY HOLDOUT: random split at PROJECT level.
    # Project groups are assigned on the FULL population first. Only after that
    # assignment are true censored rows removed from the model train/test sets.
    full_train_group, full_test_group = group_random_split(
        dataset,
        test_frac=0.3,
        random_state=RANDOM_STATE,
    )

    train_projects = set(full_train_group["project_id"])
    test_projects = set(full_test_group["project_id"])

    train = full_train_group[full_train_group["label"].notna()].copy()
    test = full_test_group[full_test_group["label"].notna()].copy()

    train["label"] = train["label"].astype(int)
    test["label"] = test["label"].astype(int)

    trainable = pd.concat([train, test], ignore_index=True)

    print(f"\nSố dòng dùng được để train/test: {len(trainable)}")
    print(f"Tỷ lệ nhãn 1 (trễ): {trainable['label'].mean():.1%}")
    print(f"Số project distinct: {trainable['project_id'].nunique()}")

    print(f"\nTrain: {len(train)} dòng / {len(train_projects)} project")
    print(f"Test:  {len(test)} dòng / {len(test_projects)} project")

    # Censoring audit PHẢI so sánh theo hai nhóm project train/test trên FULL pool.
    report_censoring_bias(
        dataset,
        train_projects=train_projects,
        test_projects=test_projects,
    )

    overlap = set(train["project_id"]) & set(test["project_id"])
    assert len(overlap) == 0, f"Rò rỉ nhóm: {overlap}"
    print("Đã kiểm tra: không có project nào xuất hiện ở cả train và test.")

    # ĐIỂM II.2 — assert test set có đủ 2 lớp
    test_classes = set(test["label"].unique())
    assert test_classes == {0, 1}, (
        f"Test set thiếu 1 lớp ({test_classes}) — không thể tính AUC/Precision/Recall "
        f"có ý nghĩa. Cần tăng test_frac hoặc đổi cách chọn nhóm project vào test."
    )
    print("Đã kiểm tra: test set có đủ cả 2 lớp (0 và 1).")

    dataset.to_csv("delay_risk_discipline_level_full.csv", index=False)
    train.to_csv("delay_risk_train.csv", index=False)
    test.to_csv("delay_risk_test.csv", index=False)
    print("\nĐã ghi 3 file vào đúng thư mục đang chạy script:")
    print("  delay_risk_discipline_level_full.csv, delay_risk_train.csv, delay_risk_test.csv")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# HƯỚNG DẪN DÙNG API THẬT (không tự chạy — làm theo các bước sau)
# ---------------------------------------------------------------------------
"""
1. Lưu API_KEY/API_SECRET vào biến môi trường, KHÔNG hard-code vào file:
   export ERPNEXT_API_KEY="..."
   export ERPNEXT_API_SECRET="..."
   export ERPNEXT_BASE_URL="https://<domain-erpnext-cua-hidecc>"

2. Cài requests nếu chưa có: pip install requests --break-system-packages

3. Gọi hàm load_from_erpnext_api() thay vì load_mock_data() trong main():

   import os
   projects, disc_alloc = load_from_erpnext_api(
       base_url=os.environ["ERPNEXT_BASE_URL"],
       api_key=os.environ["ERPNEXT_API_KEY"],
       api_secret=os.environ["ERPNEXT_API_SECRET"],
   )

4. Lưu ý bắt buộc: Discipline Allocation là CHILD TABLE — Frappe sẽ báo lỗi permission
   nếu gọi mà thiếu tham số `parent`. Lỗi đó không liên quan đến phân quyền thật, chỉ vì
   thiếu parent. Hàm load_from_erpnext_api() ở trên đã truyền đúng parent="Design
   Discipline Assignment" — giữ nguyên, đừng bỏ tham số này.

5. contract_value không đọc trực tiếp field nào trên Project — phải cộng dồn từ các
   Sales Order đã submit (docstatus=1) gắn với project đó, vì 1 dự án có thể có nhiều
   hợp đồng. Hàm trên đã xử lý bước groupby-sum này.

6. Sau khi tải xong, đổi DATA_CUTOFF ở đầu file thành đúng NGÀY THỰC SỰ chạy lệnh tải
   dữ liệu (không phải ngày chạy lại notebook sau này), rồi ghi giá trị đó vào báo cáo
   để đảm bảo tái lập được đúng kết quả khi chạy lại.

7. Trước khi chạy toàn bộ pipeline, nên test nhanh 1 doctype trước (ví dụ chỉ fetch
   Project) để xác nhận BASE_URL/API_KEY đúng, tránh việc lỗi ở giữa pipeline dài
   rồi phải dò ngược lại xem lỗi do đâu.
"""