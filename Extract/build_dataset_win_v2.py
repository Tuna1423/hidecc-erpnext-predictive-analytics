"""
build_dataset_win_v2.py — Trích xuất + build feature/nhãn cho bài toán Opportunity Win
Probability. Song song với extract.py (Delay Risk) nhưng khác đơn vị phân tích,
as-of date, và nguồn nhãn — xem feature_dictionary.md mục Subtask 2.2.

Đơn vị phân tích: 1 dòng = 1 Opportunity (chỉ những Opportunity ĐÃ CÓ ít nhất 1
Quotation — xem "out_of_scope_no_quotation" trong build_labels_win.py).
As-of date: ngày phát sinh Quotation ĐẦU TIÊN của Opportunity đó.

CẢNH BÁO QUAN TRỌNG — CÁC FIELD CHƯA ĐƯỢC XÁC MINH TRÊN HỆ THỐNG THẬT:
Khác với Delay Risk (đã xác minh field qua biên bản khảo sát + đã chạy API thật),
phần Win Probability CHƯA có bước xác minh tên field nghiệp vụ tương tự. Các hằng số
ở khối CONFIG bên dưới (OPPORTUNITY_OWNER_FIELD, QUOTATION_DISCOUNT_FIELD,
CUSTOMER_SEGMENT_FIELD...) là PHỎNG ĐOÁN dựa theo tên field chuẩn của ERPNext gốc —
RẤT CÓ THỂ SAI nếu hidecc đã customize. Trước khi chạy USE_REAL_DATA = True, LÀM
THEO HƯỚNG DẪN Ở CUỐI FILE để xác minh từng field trước.

tech_score, comm_score: KHÔNG đưa vào feature (đã chốt lớp X trong feature_dictionary.md,
chờ Đội kế hoạch xác nhận ai chấm/chấm lúc nào — nguy cơ rò rỉ nặng nếu là điểm chấm thầu).
"""

import os
import json
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
 
load_dotenv()
from build_labels_win_v2 import build_label_win, apply_labels_win, report_label_summary_win

# ---------------------------------------------------------------------------
# CẤU HÌNH KẾT NỐI + NGÀY RÚT DỮ LIỆU
# ---------------------------------------------------------------------------
USE_REAL_DATA = True  

ERPNEXT_BASE_URL = os.environ.get("ERPNEXT_BASE_URL", "")
ERPNEXT_API_KEY = os.environ.get("ERPNEXT_API_KEY", "")
ERPNEXT_API_SECRET = os.environ.get("ERPNEXT_API_SECRET", "")

DATA_CUTOFF = pd.Timestamp("2026-08-18")  # đổi thành đúng ngày pull dữ liệu thật

# --- CÁC FIELD ĐÃ XÁC MINH QUA verify_win_fields.py (2026-08-xx) ---
QUOTATION_OPPORTUNITY_FIELD = "opportunity"          # xác nhận ĐÚNG
QUOTATION_DISCOUNT_FIELD = "additional_discount_percentage"  # xác nhận ĐÚNG (tồn tại, giá trị mẫu 0.0)
OPPORTUNITY_OWNER_FIELD = "opportunity_owner"        # xác nhận ĐÚNG (tồn tại, có thể rỗng ở 1 số dòng)
OPPORTUNITY_FROM_FIELD = "opportunity_from"          # xác nhận ĐÚNG
OPPORTUNITY_PARTY_FIELD = "party_name"               # xác nhận ĐÚNG
EXPECTED_CLOSING_FIELD = "expected_closing"          # SỬA: trước đoán "expected_closing_date", tên thật ngắn hơn
LEAD_SOURCE_FIELD = "utm_source"                     # SỬA: Opportunity KHÔNG có "lead_source", dùng "utm_source"
                                                       # làm field gần nghĩa nhất — ĐÂY LÀ SUY ĐOÁN THAY THẾ,
                                                       # cần Sales xác nhận utm_source có phản ánh đúng "nguồn
                                                       # dẫn đến cơ hội" như lead_source hay không.

# BỎ: không cần CUSTOMER_SEGMENT_FIELD/CUSTOMER_TERRITORY_FIELD/join Customer nữa —
# Opportunity đã có sẵn "customer_group" và "territory" ngay trên chính nó (xác nhận
# qua verify_win_fields.py), không cần fetch/join thêm bảng Customer.

# CẢNH BÁO RÒ RỈ NGHIÊM TRỌNG — TUYỆT ĐỐI KHÔNG DÙNG 2 FIELD SAU LÀM FEATURE:
# custom_win_probability, custom_win_band — đây CHÍNH LÀ 2 field mục 5.10 đề bài gốc
# dùng để GHI NGƯỢC kết quả model vào ERPNext (qua set_opportunity_win_score). Nếu lỡ
# đưa vào làm feature, model sẽ nhìn thấy đầu ra của chính nó/của lần chạy trước —
# rò rỉ nghiêm trọng, không được đưa vào compute_features_win() dưới bất kỳ hình thức nào.

OVERLOAD_SMOOTHING_K = 5  # cùng cơ chế smoothing như bên Delay Risk

RNG_SEED = 7
rng = np.random.default_rng(RNG_SEED)


# ---------------------------------------------------------------------------
# 1a. TẢI DỮ LIỆU THẬT QUA API
# ---------------------------------------------------------------------------

def make_fetch(base_url, api_key, api_secret):
    headers = {"Authorization": f"token {api_key}:{api_secret}"}

    def fetch(doctype, fields, parent=None, filters=None):
        params = {"limit_page_length": 0, "fields": json.dumps(fields)}
        if parent:
            params["parent"] = parent
        if filters:
            params["filters"] = json.dumps(filters)
        r = requests.get(f"{base_url}/api/resource/{doctype}", headers=headers, params=params, timeout=120)
        r.raise_for_status()
        df = pd.DataFrame(r.json()["data"])
        return df

    return fetch


def load_from_erpnext_api_win(base_url, api_key, api_secret):
    fetch = make_fetch(base_url, api_key, api_secret)

    # ĐÃ SỬA: bỏ "customer" (không tồn tại trên Opportunity), bỏ "lead_source" (không
    # tồn tại, dùng utm_source), đổi "expected_closing_date" -> "expected_closing".
    # customer_group/territory lấy TRỰC TIẾP trên Opportunity, không cần join Customer.
    opportunity = fetch("Opportunity", [
        "name", "customer_group", "territory", OPPORTUNITY_OWNER_FIELD,
        OPPORTUNITY_FROM_FIELD, OPPORTUNITY_PARTY_FIELD, "opportunity_type",
        "opportunity_amount", LEAD_SOURCE_FIELD, "transaction_date", "status",
        EXPECTED_CLOSING_FIELD,
        # KHÔNG bao giờ thêm "custom_win_probability"/"custom_win_band" vào đây —
        # xem cảnh báo rò rỉ ở khối CONFIG đầu file.
    ]).rename(columns={
        "name": "opportunity_id",
        "customer_group": "customer_segment",
        OPPORTUNITY_OWNER_FIELD: "owner_id",
        LEAD_SOURCE_FIELD: "lead_source",
        EXPECTED_CLOSING_FIELD: "expected_closing_date",  # giữ tên cột nội bộ cũ để
                                                            # build_labels_win.py không cần sửa
    })

    quotation = fetch("Quotation", [
        "name", QUOTATION_OPPORTUNITY_FIELD, "transaction_date", QUOTATION_DISCOUNT_FIELD,
    ]).rename(columns={
        "name": "quotation_id", QUOTATION_OPPORTUNITY_FIELD: "opportunity_id",
        "transaction_date": "quotation_date", QUOTATION_DISCOUNT_FIELD: "discount_rate",
    })

    lead = fetch("Lead", ["name", "creation"]).rename(columns={"name": "lead_id", "creation": "lead_creation"})

    for col in ["transaction_date", "expected_closing_date"]:
        opportunity[col] = pd.to_datetime(opportunity[col], errors="coerce")
    quotation["quotation_date"] = pd.to_datetime(quotation["quotation_date"], errors="coerce")
    lead["lead_creation"] = pd.to_datetime(lead["lead_creation"], errors="coerce")

    return opportunity, quotation, lead


# ---------------------------------------------------------------------------
# 1b. MÔ PHỎNG DỮ LIỆU (kiểm thử pipeline khi USE_REAL_DATA=False)
# ---------------------------------------------------------------------------

def generate_mock_win_data():
    n_opp = 183  # khớp số liệu thật đã biết
    segments = ["SME", "Enterprise", "Government"]
    territories = ["Miền Bắc", "Miền Trung", "Miền Nam", "Rest Of The World"]

    lead = pd.DataFrame({
        "lead_id": [f"LEAD-{i:04d}" for i in range(n_opp)],
        "lead_creation": pd.to_datetime("2023-06-01") + pd.to_timedelta(rng.integers(0, 800, n_opp), unit="D"),
    })

    owners = [f"OWNER-{i:02d}" for i in range(6)]
    opp_rows = []
    for i in range(n_opp):
        txn_date = lead["lead_creation"].iloc[i] + pd.Timedelta(days=int(rng.integers(1, 30)))
        status = rng.choice(["Open", "Converted", "Lost"], p=[0.30, 0.40, 0.30])
        opp_rows.append({
            "opportunity_id": f"OPP-{i:04d}",
            # customer_segment/territory nằm TRỰC TIẾP trên Opportunity (khớp dữ liệu
            # thật đã xác nhận), không cần bảng customer riêng nữa.
            "customer_segment": rng.choice(segments),
            "territory": rng.choice(territories),
            "owner_id": rng.choice(owners),
            "opportunity_from": "Lead",
            "party_name": lead["lead_id"].iloc[i],
            "opportunity_type": rng.choice(["Sales", "Maintenance"]),
            "opportunity_amount": rng.integers(200, 15000) * 1_000_000,
            "lead_source": rng.choice(["Existing Customer", "Website", "Referral"]),  # proxy cho utm_source
            "transaction_date": txn_date,
            "status": status,
            "expected_closing_date": txn_date + pd.Timedelta(days=int(rng.integers(30, 120))),
        })
    opportunity = pd.DataFrame(opp_rows)

    quo_rows = []
    for _, o in opportunity.iterrows():
        if rng.random() < 0.55:  # ~55% có ít nhất 1 Quotation
            n_quo = rng.integers(1, 4)
            first_quo_date = o["transaction_date"] + pd.Timedelta(days=int(rng.integers(5, 45)))
            for q in range(n_quo):
                quo_rows.append({
                    "opportunity_id": o["opportunity_id"],
                    "quotation_id": f"QUO-{o['opportunity_id']}-{q}",
                    "quotation_date": first_quo_date + pd.Timedelta(days=q * 10),
                    "discount_rate": rng.uniform(0, 15),
                })
    quotation = pd.DataFrame(quo_rows)

    return opportunity, quotation, lead


# ---------------------------------------------------------------------------
# 2. TÍNH FEATURE — mỗi feature tự hỏi "tại as-of đã tồn tại chưa?"
# ---------------------------------------------------------------------------

# HIỆN CHƯA DÙNG trong compute_features_win() (owner_historic_win_rate đã bị bỏ khỏi
# baseline do lỗi rò rỉ — xem ghi chú trong compute_features_win). Giữ lại hàm này để
# dùng lại ngay khi có field ngày đóng (resolution date) đáng tin từ Đội kế hoạch.
def smoothed_rate(subset_closed_before_T: pd.DataFrame, global_rate: float, k: int = OVERLOAD_SMOOTHING_K) -> float:
    n = len(subset_closed_before_T)
    if n == 0:
        return global_rate
    won = subset_closed_before_T["was_won"].sum()
    return (won + k * global_rate) / (n + k)


def compute_features_win(opportunity: pd.DataFrame, quotation: pd.DataFrame,
                          lead: pd.DataFrame,
                          cutoff: pd.Timestamp = DATA_CUTOFF) -> pd.DataFrame:
    # ĐÃ SỬA: không merge Customer nữa — customer_segment/territory đã có sẵn trên
    # chính opportunity (fetch trực tiếp ở load_from_erpnext_api_win).
    opp = opportunity.copy()

    # as_of = ngày Quotation ĐẦU TIÊN của từng Opportunity. Opportunity chưa từng có
    # Quotation -> as_of rỗng -> build_label_win() sẽ tự gắn "out_of_scope_no_quotation".
    first_quo = quotation.groupby("opportunity_id")["quotation_date"].min().rename("quotation_date")
    opp = opp.drop(columns=[c for c in ["quotation_date"] if c in opp.columns])
    opp = opp.merge(first_quo, on="opportunity_id", how="left")

    # ĐÃ BỎ n_quotation_total (Điểm 2, feedback rà soát): tại đúng as_of (ngày
    # quotation đầu tiên), số quotation THẬT SỰ biết được luôn là 1 — đếm toàn bộ
    # quotation của Opportunity (không lọc theo ngày) là đang dùng thông tin PHÁT
    # SINH SAU as_of (các lần chỉnh sửa/quotation tiếp theo chưa xảy ra tại thời điểm
    # snapshot). Đây là rò rỉ, không phải feature hợp lệ — loại khỏi baseline.

    # discount_rate của Quotation ĐẦU TIÊN (vì as_of = đúng ngày quotation đó, chưa
    # có quotation thứ 2 để mà tính "trung bình" tại đúng thời điểm snapshot)
    quotation_sorted = quotation.sort_values("quotation_date")
    first_quo_row = quotation_sorted.drop_duplicates("opportunity_id", keep="first")
    opp = opp.merge(
        first_quo_row[["opportunity_id", "discount_rate"]].rename(columns={"discount_rate": "discount_rate_at_first_quotation"}),
        on="opportunity_id", how="left"
    )

    # days_lead_to_opp: Lead.creation -> Opportunity.transaction_date (chỉ áp dụng
    # nếu opportunity_from == "Lead"; ngược lại để NaN, không suy diễn)
    opp = opp.merge(lead, left_on="party_name", right_on="lead_id", how="left")
    opp["days_lead_to_opp"] = np.where(
        opp["opportunity_from"] == "Lead",
        (opp["transaction_date"] - opp["lead_creation"]).dt.days,
        np.nan,
    )

    # ĐÃ BỎ owner_historic_win_rate (Điểm 1, feedback rà soát) — LỖI RÒ RỈ THẬT SỰ,
    # cùng bản chất với lỗi n_open_overdue_tasks_at_snapshot đã sửa ở Delay Risk
    # (DS-02), chỉ khác chỗ xảy ra:
    #   - Bản cũ lọc lịch sử bằng "opp_closed[transaction_date <= as_of]" — tức NGÀY
    #     TẠO cơ hội khác, không phải ngày BIẾT KẾT QUẢ (thắng/thua) của cơ hội đó.
    #   - Hệ quả: 1 cơ hội được tạo TRƯỚC as_of nhưng có kết quả thắng/thua RA SAU
    #     as_of vẫn lọt vào pool lịch sử — dùng thông tin tương lai.
    #   - Nặng hơn: vì as_of = ngày quotation đầu (luôn SAU transaction_date của
    #     chính dòng đó), chính dòng đang xét, NẾU đã có status Converted/Lost tại
    #     lúc rút dữ liệu, cũng tự lọt vào chính pool lịch sử của nó — tự tính kết
    #     quả của chính mình vào historic rate của chính mình.
    # ERPNext không có sẵn field ngày đóng (resolution date) đáng tin cho Lost —
    # đang chờ Đội kế hoạch xác nhận cách lấy đúng ngày biết kết quả thật. Trong
    # lúc chờ: BỎ HẲN feature này khỏi baseline, không tạm vá bằng cách xấp xỉ.

    # has_quotation: LƯU Ý — vì as_of = ngày quotation đầu tiên, mọi dòng trong phạm
    # vi bài toán (đã merge first_quo) đều có has_quotation = 1 một cách hiển nhiên,
    # đây là hệ quả đã biết trước của việc chọn as-of date này (xem feature_dictionary.md),
    # KHÔNG phải lỗi — cột này gần như hằng số trong tập trainable, cân nhắc bỏ khi train.
    opp["has_quotation"] = opp["quotation_date"].notna().astype(int)

    label_status = apply_labels_win(opp, cutoff)

    keep_cols = [
        "opportunity_id", "quotation_date", "lead_source", "customer_segment", "territory",
        "opportunity_type", "opportunity_amount", "days_lead_to_opp", "has_quotation",
        "discount_rate_at_first_quotation",
        "label", "censor_status",
    ]
    return label_status[keep_cols].rename(columns={"quotation_date": "as_of_date"})


# ---------------------------------------------------------------------------
# 3. CHIA TẬP — theo thời gian (1 dòng = 1 Opportunity, không cần group split)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 3. CHIA TẬP — theo thời gian (1 dòng = 1 Opportunity, không cần group split)
# ---------------------------------------------------------------------------

def time_split(dataset: pd.DataFrame, test_frac: float = 0.3):
    sorted_df = dataset.sort_values("as_of_date")
    n_test = max(1, int(len(sorted_df) * test_frac))
    train = sorted_df.iloc[:-n_test].copy()
    test = sorted_df.iloc[-n_test:].copy()
    return train, test


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print(f"DATA_CUTOFF: {DATA_CUTOFF.date()}")
    print("[GIỚI HẠN] Đã BỎ 2 feature khỏi baseline do rò rỉ dữ liệu (xem chi tiết trong "
          "compute_features_win()): n_quotation_total (đếm cả quotation phát sinh sau "
          "as_of) và owner_historic_win_rate (gate sai bằng transaction_date thay vì "
          "ngày biết kết quả thật, khiến 1 cơ hội có thể tự tính chính nó vào historic "
          "rate của nó). tech_score/comm_score vẫn giữ lớp X, chờ Đội kế hoạch xác nhận.\n")

    if USE_REAL_DATA:
        if not (ERPNEXT_BASE_URL and ERPNEXT_API_KEY and ERPNEXT_API_SECRET):
            raise RuntimeError(
                "USE_REAL_DATA=True nhưng thiếu biến môi trường ERPNEXT_BASE_URL/"
                "ERPNEXT_API_KEY/ERPNEXT_API_SECRET. Set 3 biến này trước khi chạy, "
                "không hard-code vào file."
            )
        print("[CHẾ ĐỘ] Đang tải dữ liệu THẬT từ ERPNext qua API...\n")
        opportunity, quotation, lead = load_from_erpnext_api_win(
            ERPNEXT_BASE_URL, ERPNEXT_API_KEY, ERPNEXT_API_SECRET
        )
        print(f"Đã tải: {len(opportunity)} opportunity, {len(quotation)} quotation")
        print("Đối chiếu tham khảo: kỳ vọng ~183 opportunity, ~207 biên bản nghiệm thu (không cùng bảng này).")
    else:
        print("[LƯU Ý] Đang chạy bằng DỮ LIỆU MÔ PHỎNG để kiểm thử pipeline — nhãn/feature "
              "ở đây KHÔNG đại diện cho dữ liệu thật.\n")
        opportunity, quotation, lead = generate_mock_win_data()

    dataset = compute_features_win(opportunity, quotation, lead, cutoff=DATA_CUTOFF)

    print(f"\nTổng số Opportunity: {len(dataset)}")
    report_label_summary_win(dataset)

    trainable = dataset[dataset["label"].notna()].copy()
    trainable["label"] = trainable["label"].astype(int)
    print(f"\nTỷ lệ Won trong tập trainable: {trainable['label'].mean():.1%}")

    train, test = time_split(trainable, test_frac=0.3)
    print(f"\nTrain: {len(train)} dòng | Test: {len(test)} dòng")

    test_classes = set(test["label"].unique())
    assert test_classes == {0, 1}, (
        f"Test set thiếu 1 lớp ({test_classes}) — cần tăng test_frac hoặc kiểm tra lại dữ liệu."
    )
    print("Đã kiểm tra: test set có đủ cả 2 lớp (0 và 1).")

    dataset.to_csv("win_probability_full.csv", index=False)
    train.to_csv("win_probability_train.csv", index=False)
    test.to_csv("win_probability_test.csv", index=False)
    print("\nĐã ghi: win_probability_full.csv, win_probability_train.csv, win_probability_test.csv")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# TRẠNG THÁI XÁC MINH FIELD (đã chạy verify_win_fields.py trên dữ liệu thật)
# ---------------------------------------------------------------------------
"""
Đã xác minh bằng verify_win_fields.py trên dữ liệu thật của hidecc, kết quả:

- QUOTATION_OPPORTUNITY_FIELD = "opportunity"                    -> ĐÚNG, giữ nguyên
- QUOTATION_DISCOUNT_FIELD = "additional_discount_percentage"    -> ĐÚNG, giữ nguyên
- OPPORTUNITY_OWNER_FIELD = "opportunity_owner"                  -> ĐÚNG, giữ nguyên
- OPPORTUNITY_FROM_FIELD = "opportunity_from"                    -> ĐÚNG, giữ nguyên
- OPPORTUNITY_PARTY_FIELD = "party_name"                         -> ĐÚNG, giữ nguyên
- expected_closing_date -> SỬA thành "expected_closing" (tên thật ngắn hơn)
- "customer" trên Opportunity -> KHÔNG TỒN TẠI, đã bỏ hẳn bước join Customer;
  customer_segment/territory lấy trực tiếp từ "customer_group"/"territory" ngay
  trên Opportunity (2 field này tồn tại thật, xác nhận qua verify_win_fields.py)
- "lead_source" -> KHÔNG TỒN TẠI trên Opportunity, đã đổi sang "utm_source"

CÒN 1 ĐIỂM CHƯA CHẮC CHẮN 100%, CẦN SALES XÁC NHẬN THÊM:
"utm_source" có phản ánh đúng ý nghĩa "nguồn dẫn đến cơ hội" (lead_source) hay
không, hay đó là 2 khái niệm khác nhau (utm_source thường dùng cho tracking
marketing digital, có thể không bao phủ hết các kênh như "khách hàng cũ giới
thiệu", "quan hệ trực tiếp"...). Nếu utm_source không phù hợp, cần hỏi Sales xem
có field nào khác đúng nghĩa hơn, hoặc chấp nhận bỏ feature này.

TUYỆT ĐỐI KHÔNG THÊM 2 FIELD SAU VÀO compute_features_win() DƯỚI BẤT KỲ HÌNH THỨC
NÀO: "custom_win_probability", "custom_win_band" — đây là field ĐÍCH để ghi ngược
kết quả model (mục 5.10 đề bài gốc), dùng làm feature sẽ gây rò rỉ nghiêm trọng.

CÁC FIELD MỚI PHÁT HIỆN, CHƯA ĐƯA VÀO FEATURE, CÂN NHẮC BỔ SUNG SAU (KHÔNG tự ý
thêm vào feature_dictionary.md khi chưa thảo luận):
- annual_revenue, industry, no_of_employees, market_segment (trên Opportunity) —
  có thể là feature khách hàng phong phú hơn customer_group/territory hiện tại.
- custom_submission_deadline, custom_tender_no, custom_bid_bond, custom_investor —
  field riêng cho nghiệp vụ đấu thầu (gói thầu), custom_submission_deadline có thể
  hữu ích để tính thêm feature "thời gian còn lại trước hạn nộp thầu".

tech_score, comm_score: đã xác nhận tồn tại dưới tên "custom_tech_score",
"custom_comm_score" — vẫn giữ lớp X theo quyết định trước đó (chờ Đội kế hoạch xác
nhận ai chấm/chấm lúc nào), KHÔNG đưa vào compute_features_win().
"""