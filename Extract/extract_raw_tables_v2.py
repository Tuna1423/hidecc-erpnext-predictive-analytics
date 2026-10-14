"""
extract_raw_tables.py — Trích xuất REST/CSV các DocType, tạo 2 bảng phẳng RAW:
  1. project_task_timesheet.csv  (Project ⨝ Task ⨝ Timesheet Detail)
  2. opportunity_quotation_so.csv (Opportunity ⨝ Quotation; Sales Order xuất riêng)

MỤC ĐÍCH: đây là bước trích xuất THÔ (raw), tách riêng khỏi bước build feature/nhãn
(xem extract.py cho Delay Risk, extract_win.py cho Win Probability). File này chỉ
ghép nối (join) dữ liệu gốc từ ERPNext thành bảng phẳng. KHÔNG tính as-of date /
feature / nhãn ở đây.

ĐÃ XÁC MINH qua verify_win_fields.py trên dữ liệu thật:
1. Timesheet Detail RỖNG (đúng như dự đoán — hidecc không ghi giờ công qua Timesheet
   theo ngày). Vẫn giữ tham số parent="Timesheet" khi fetch vì đây là child table.
2. QUOTATION_OPPORTUNITY_FIELD = "opportunity" -> ĐÚNG, xác nhận trên dữ liệu thật.
3. Sales Order KHÔNG có field trỏ thẳng tới Quotation ở cấp chứng từ — không thể
   merge trực tiếp như dự tính ban đầu. Sales Order được xuất RIÊNG (sales_order_raw.csv),
   không join vào opportunity_quotation_so.csv. Nếu cần liên kết chính xác, phải qua
   child table "Sales Order Item" (field prevdoc_docname) — CHƯA xác minh field này.
4. Opportunity KHÔNG có field "customer" hay "lead_source" — dùng "customer_group"/
   "territory" (đổi tên thành customer_segment/territory) và "utm_source" (đổi tên
   thành lead_source, xem cảnh báo về độ chính xác ngữ nghĩa trong extract_win.py).
"""

import os
import json
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
 
load_dotenv()
# ---------------------------------------------------------------------------
# CẤU HÌNH
# ---------------------------------------------------------------------------
USE_REAL_DATA = False

ERPNEXT_BASE_URL = os.environ.get("ERPNEXT_BASE_URL", "")
ERPNEXT_API_KEY = os.environ.get("ERPNEXT_API_KEY", "")
ERPNEXT_API_SECRET = os.environ.get("ERPNEXT_API_SECRET", "")

# Đã xác minh trên dữ liệu thật (verify_win_fields.py) — ĐÚNG, giữ nguyên.
QUOTATION_OPPORTUNITY_FIELD = "opportunity"
# SO_QUOTATION_FIELD đã bỏ — Sales Order không có field này (xem docstring đầu file).

RNG_SEED = 42
rng = np.random.default_rng(RNG_SEED)


# ---------------------------------------------------------------------------
# 1. FETCH HELPER (tái dùng đúng pattern đã kiểm chứng ở extract.py)
# ---------------------------------------------------------------------------

def make_fetch(base_url: str, api_key: str, api_secret: str):
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

    return fetch


# ---------------------------------------------------------------------------
# 2a. BẢNG PHẲNG: Project - Task - Timesheet
# ---------------------------------------------------------------------------

def extract_project_task_timesheet_real(fetch) -> pd.DataFrame:
    project = fetch("Project", [
        "name", "project_type", "expected_start_date", "expected_end_date",
        "status", "customer",
    ]).rename(columns={"name": "project_id"})

    task = fetch("Task", [
        "name", "project", "subject", "is_milestone", "status",
        "exp_start_date", "exp_end_date", "completed_on", "act_start_date", "act_end_date",
    ]).rename(columns={"name": "task_id", "project": "project_id"})

    # Timesheet Detail là CHILD TABLE của Timesheet -> bắt buộc parent="Timesheet".
    # Kỳ vọng bảng này RỖNG hoặc gần rỗng (xem docstring đầu file). Nếu API trả về
    # rỗng, pandas tạo DataFrame KHÔNG CÓ CỘT nào cả (kể cả khi ta có request field) —
    # phải tự bù lại đúng cột rỗng, nếu không bước chọn cột/merge phía dưới sẽ lỗi.
    timesheet_detail = fetch("Timesheet Detail", [
        "name", "parent", "task", "project", "hours", "from_time", "to_time",
    ], parent="Timesheet")

    if timesheet_detail.empty:
        print("[GHI CHÚ] Timesheet Detail rỗng — đúng như kỳ vọng nghiệp vụ (hidecc "
              "không ghi giờ công qua Timesheet theo ngày). Bảng flat sẽ không có cột "
              "Timesheet nào khớp được, cột timesheet_id/hours/from_time/to_time sẽ toàn NaN.")
        timesheet_detail = pd.DataFrame(columns=["name", "parent", "task", "project", "hours", "from_time", "to_time"])

    timesheet_detail = timesheet_detail.rename(columns={"parent": "timesheet_id"})

    flat = task.merge(project, on="project_id", how="left")
    flat = flat.merge(
        timesheet_detail[["task", "timesheet_id", "hours", "from_time", "to_time"]],
        left_on="task_id", right_on="task", how="left"
    ).drop(columns=["task"])

    return flat


def generate_mock_project_task_timesheet() -> pd.DataFrame:
    """Mô phỏng để kiểm thử pipeline khi USE_REAL_DATA=False. Timesheet cố tình để
    phần lớn rỗng, khớp kỳ vọng thực tế (hidecc không dùng Timesheet theo ngày)."""
    n_projects = 59
    projects = pd.DataFrame({
        "project_id": [f"PRJ-{i:04d}" for i in range(n_projects)],
        "project_type": rng.choice(["Dân dụng", "Hạ tầng kỹ thuật", "Giao thông", "Thuỷ lợi"], n_projects),
        "expected_start_date": pd.to_datetime("2024-01-01") + pd.to_timedelta(rng.integers(0, 600, n_projects), unit="D"),
        "status": rng.choice(["Open", "Completed"], n_projects),
        "customer": rng.choice([f"CUST-{i:02d}" for i in range(12)], n_projects),
    })
    projects["expected_end_date"] = projects["expected_start_date"] + pd.to_timedelta(rng.integers(60, 400, n_projects), unit="D")

    rows = []
    for _, p in projects.iterrows():
        for i in range(rng.integers(5, 12)):
            rows.append({
                "task_id": f"TASK-{p['project_id']}-{i}",
                "project_id": p["project_id"],
                "subject": f"Task {i}",
                "is_milestone": int(i == 0),
                "status": rng.choice(["Open", "Completed"]),
                "exp_start_date": p["expected_start_date"],
                "exp_end_date": p["expected_start_date"] + pd.Timedelta(days=int(rng.integers(20, 200))),
                "completed_on": pd.NaT,
                "act_start_date": pd.NaT,
                "act_end_date": pd.NaT,  # luôn rỗng, khớp phát hiện trước đó (phụ thuộc Timesheet)
                "timesheet_id": pd.NA,   # Timesheet rỗng theo đúng thực tế nghiệp vụ
                "hours": np.nan,
                "from_time": pd.NaT,
                "to_time": pd.NaT,
            })
    task = pd.DataFrame(rows)
    flat = task.merge(projects, on="project_id", how="left")
    return flat


# ---------------------------------------------------------------------------
# 2b. BẢNG PHẲNG: Opportunity - Quotation - Sales Order
# ---------------------------------------------------------------------------

def extract_opp_quo_so_real(fetch) -> pd.DataFrame:
    # ĐÃ SỬA theo kết quả verify_win_fields.py: Opportunity không có "customer" và
    # "lead_source" — dùng customer_group/territory trực tiếp trên Opportunity, và
    # utm_source thay cho lead_source (xem ghi chú ở extract_win.py, cùng cảnh báo).
    opportunity = fetch("Opportunity", [
        "name", "customer_group", "territory", "opportunity_type", "opportunity_amount",
        "utm_source", "transaction_date", "status",
    ]).rename(columns={
        "name": "opportunity_id", "customer_group": "customer_segment", "utm_source": "lead_source",
    })

    quotation = fetch("Quotation", [
        "name", QUOTATION_OPPORTUNITY_FIELD, "transaction_date", "grand_total", "status",
    ]).rename(columns={"name": "quotation_id", QUOTATION_OPPORTUNITY_FIELD: "opportunity_id",
                        "transaction_date": "quotation_date"})

    flat = opportunity.merge(quotation, on="opportunity_id", how="left")

    # Sales Order KHÔNG có field trỏ thẳng tới Quotation ở cấp chứng từ (đã xác nhận
    # qua verify_win_fields.py: field "quotation" không tồn tại trên Sales Order). Nếu
    # cần liên kết chính xác Quotation -> Sales Order, phải lấy qua child table
    # "Sales Order Item" (field prevdoc_docname), CHƯA xác minh field này có tồn tại/
    # được điền trên hidecc hay không — không tự đoán thêm. Sales Order fetch riêng
    # ở đây (có "project" để dùng cho mục đích khác, như cộng dồn contract_value bên
    # Delay Risk), KHÔNG merge vào bảng phẳng này.
    sales_order = fetch("Sales Order", ["name", "project", "transaction_date", "grand_total", "docstatus"])
    print(f"[GHI CHÚ] Sales Order KHÔNG được merge vào bảng phẳng (thiếu field liên kết "
          f"trực tiếp tới Quotation) — trả về riêng để tham khảo, {len(sales_order)} dòng.")

    return flat, sales_order


def generate_mock_opp_quo_so() -> pd.DataFrame:
    n_opp = 183
    opp = pd.DataFrame({
        "opportunity_id": [f"OPP-{i:04d}" for i in range(n_opp)],
        "customer": rng.choice([f"CUST-{i:02d}" for i in range(12)], n_opp),
        "opportunity_type": rng.choice(["Sales", "Maintenance"], n_opp),
        "opportunity_amount": rng.integers(200, 15000, n_opp) * 1_000_000,
        "lead_source": rng.choice(["Existing Customer", "Website", "Referral"], n_opp),
        "transaction_date": pd.to_datetime("2024-01-01") + pd.to_timedelta(rng.integers(0, 700, n_opp), unit="D"),
        "status": rng.choice(["Open", "Converted", "Lost"], n_opp, p=[0.3, 0.4, 0.3]),
    })

    rows = []
    for _, o in opp.iterrows():
        if rng.random() < 0.6:  # ~60% có ít nhất 1 quotation (giống nhận định đã bàn trước đó)
            n_quo = rng.integers(1, 4)
            for q in range(n_quo):
                quo_id = f"QUO-{o['opportunity_id']}-{q}"
                quo_date = o["transaction_date"] + pd.Timedelta(days=int(rng.integers(5, 60)))
                has_so = (q == n_quo - 1) and (o["status"] == "Converted")
                rows.append({
                    "opportunity_id": o["opportunity_id"], "quotation_id": quo_id,
                    "quotation_date": quo_date, "grand_total": o["opportunity_amount"] * rng.uniform(0.8, 1.0),
                    "status": "Ordered" if has_so else rng.choice(["Open", "Cancelled"]),
                    "sales_order_id": f"SO-{quo_id}" if has_so else pd.NA,
                    "so_date": quo_date + pd.Timedelta(days=10) if has_so else pd.NaT,
                    "so_grand_total": o["opportunity_amount"] if has_so else np.nan,
                    "docstatus": 1 if has_so else pd.NA,
                })
        else:
            rows.append({
                "opportunity_id": o["opportunity_id"], "quotation_id": pd.NA,
                "quotation_date": pd.NaT, "grand_total": np.nan, "status": pd.NA,
                "sales_order_id": pd.NA, "so_date": pd.NaT, "so_grand_total": np.nan, "docstatus": pd.NA,
            })
    quo_so = pd.DataFrame(rows)
    flat = opp.merge(quo_so, on="opportunity_id", how="left")
    return flat


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    sales_order = None
    if USE_REAL_DATA:
        if not (ERPNEXT_BASE_URL and ERPNEXT_API_KEY and ERPNEXT_API_SECRET):
            raise RuntimeError(
                "USE_REAL_DATA=True nhưng thiếu biến môi trường ERPNEXT_BASE_URL/"
                "ERPNEXT_API_KEY/ERPNEXT_API_SECRET. Set 3 biến này trước khi chạy, "
                "không hard-code vào file."
            )
        print("[CHẾ ĐỘ] Đang tải dữ liệu THẬT từ ERPNext qua API...\n")
        fetch = make_fetch(ERPNEXT_BASE_URL, ERPNEXT_API_KEY, ERPNEXT_API_SECRET)
        ptt = extract_project_task_timesheet_real(fetch)
        oqs, sales_order = extract_opp_quo_so_real(fetch)
    else:
        print("[LƯU Ý] Đang chạy bằng DỮ LIỆU MÔ PHỎNG để kiểm thử pipeline.\n")
        ptt = generate_mock_project_task_timesheet()
        oqs = generate_mock_opp_quo_so()

    print(f"project_task_timesheet: {len(ptt)} dòng, {ptt['project_id'].nunique()} project, "
          f"{ptt['task_id'].nunique()} task")
    n_with_timesheet = ptt["timesheet_id"].notna().sum() if "timesheet_id" in ptt else 0
    print(f"  -> số dòng có Timesheet gắn kèm: {n_with_timesheet} "
          f"(kỳ vọng rất thấp/gần 0 theo nghiệp vụ hidecc — không phải lỗi nếu vậy)")

    print(f"\nopportunity_quotation_so: {len(oqs)} dòng, {oqs['opportunity_id'].nunique()} opportunity")
    n_with_quo = oqs["quotation_id"].notna().sum()
    print(f"  -> số dòng có Quotation: {n_with_quo}")
    if "sales_order_id" in oqs.columns:
        n_with_so = oqs["sales_order_id"].notna().sum()
        print(f"  -> số dòng có Sales Order (chỉ ở chế độ mock): {n_with_so}")

    ptt.to_csv("project_task_timesheet.csv", index=False)
    oqs.to_csv("opportunity_quotation_so.csv", index=False)
    print("\nĐã ghi: project_task_timesheet.csv, opportunity_quotation_so.csv (vào thư mục hiện tại)")

    if sales_order is not None:
        sales_order.to_csv("sales_order_raw.csv", index=False)
        print(f"Đã ghi riêng: sales_order_raw.csv ({len(sales_order)} dòng, chưa join với "
              f"Quotation — xem ghi chú trong extract_opp_quo_so_real()).")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# GHI CHÚ SỬ DỤNG
# ---------------------------------------------------------------------------
"""
1. Trước khi bật USE_REAL_DATA = True, nên fetch thử 5 dòng Quotation và Sales Order
   để in ra tên cột thật, xác nhận QUOTATION_OPPORTUNITY_FIELD và SO_QUOTATION_FIELD
   đúng tên field trên hidecc (có thể lệch nếu app đã customize):

   fetch = make_fetch(ERPNEXT_BASE_URL, ERPNEXT_API_KEY, ERPNEXT_API_SECRET)
   print(fetch("Quotation", ["name", "opportunity", "customer"]).head())
   print(fetch("Sales Order", ["name", "quotation"]).head())

   Nếu 2 câu trên báo lỗi "field not found", nghĩa là tên field khác — vào ERPNext,
   mở 1 bản ghi Quotation/Sales Order bất kỳ, bật chế độ Developer, xem đúng
   fieldname liên kết rồi sửa lại 2 hằng số đầu file.

2. Nếu Sales Order không có field liên kết Quotation ở cấp header (nhiều bản ERPNext
   lưu liên kết này ở "Sales Order Item.prevdoc_docname" — cấp dòng, không phải cấp
   chứng từ), cần đổi cách lấy: fetch("Sales Order Item", [...], parent="Sales Order")
   rồi lọc theo prevdoc_doctype = "Quotation".

3. project_task_timesheet.csv và opportunity_quotation_so.csv là bảng RAW/phẳng —
   chưa có as-of date, chưa có feature, chưa có nhãn. Bước build feature/nhãn (Delay
   Risk) vẫn nằm ở extract.py riêng; có thể sửa lại extract.py sau để đọc từ 2 file
   CSV này thay vì gọi API lại từ đầu, tránh gọi API nhiều lần cho cùng một lần phân tích.
"""