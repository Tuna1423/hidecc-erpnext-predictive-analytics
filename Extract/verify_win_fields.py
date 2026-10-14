"""
verify_win_fields.py — Kiểm tra TOÀN BỘ field đang bị PHỎNG ĐOÁN trong extract_win.py
(và extract_raw_tables.py phần Opp-Quo-SO), bằng cách lấy 1 bản ghi mẫu thật (fields=["*"])
cho từng DocType liên quan, rồi đối chiếu xem tên field đoán có tồn tại không.

CÁCH DÙNG:
1. Điền API_KEY/API_SECRET bên dưới.
2. Chạy: python3 verify_win_fields.py
"""

import json
import requests

BASE_URL = "http://103.63.111.136:8100"
API_KEY = "b703d1745c6807d"
API_SECRET = "da8dbd5700ca5d2"

HEADERS = {"Authorization": f"token {API_KEY}:{API_SECRET}"}

# Danh sách field đang PHỎNG ĐOÁN cần xác minh, gom theo DocType.
# (tên biến bên trái = đúng tên hằng số trong extract_win.py / extract_raw_tables.py,
# để bạn dễ đối chiếu ngược lại khi sửa code)
FIELDS_TO_VERIFY = {
    "Opportunity": {
        "OPPORTUNITY_OWNER_FIELD": "opportunity_owner",
        "OPPORTUNITY_FROM_FIELD": "opportunity_from",
        "OPPORTUNITY_PARTY_FIELD": "party_name",
        "expected_closing_date (dùng trong build_labels_win.py)": "expected_closing_date",
        "customer (để join Customer)": "customer",
        "opportunity_amount": "opportunity_amount",
        "lead_source": "lead_source",
        "opportunity_type": "opportunity_type",
        "transaction_date": "transaction_date",
        "status": "status",
    },
    "Quotation": {
        "QUOTATION_OPPORTUNITY_FIELD": "opportunity",
        "QUOTATION_DISCOUNT_FIELD": "additional_discount_percentage",
        "transaction_date": "transaction_date",
    },
    "Sales Order": {
        "SO_QUOTATION_FIELD (extract_raw_tables.py)": "quotation",
        "transaction_date": "transaction_date",
        "docstatus": "docstatus",
    },
    "Customer": {
        "CUSTOMER_SEGMENT_FIELD": "customer_group",
        "CUSTOMER_TERRITORY_FIELD": "territory",
    },
    "Lead": {
        "creation (ngày tạo Lead)": "creation",
    },
}


def fetch_sample(doctype: str):
    r = requests.get(
        f"{BASE_URL}/api/resource/{doctype}",
        headers=HEADERS,
        params={"limit_page_length": 1, "fields": json.dumps(["*"])},
        timeout=60,
    )
    if r.status_code != 200:
        return None, f"Status {r.status_code}: {r.text[:300]}"
    rows = r.json()["data"]
    if not rows:
        return None, "Không có bản ghi nào (bảng rỗng hoặc thiếu quyền đọc dữ liệu)."
    return rows[0], None


def main():
    for doctype, guesses in FIELDS_TO_VERIFY.items():
        print(f"\n{'='*70}")
        print(f"DocType: {doctype}")
        print(f"{'='*70}")

        sample, error = fetch_sample(doctype)
        if error:
            print(f"[LỖI] {error}")
            continue

        real_fields = set(sample.keys())
        print(f"(Tổng số field thật trong bản ghi mẫu: {len(real_fields)})\n")

        print(f"{'Hằng số cần sửa trong code':45s} | {'Tên đang đoán':30s} | Kết quả")
        print("-" * 100)
        for constant_name, guessed_fieldname in guesses.items():
            found = guessed_fieldname in real_fields
            result = f"CÓ (giá trị mẫu: {str(sample.get(guessed_fieldname))[:30]})" if found else "KHÔNG TÌM THẤY"
            print(f"{constant_name:45s} | {guessed_fieldname:30s} | {result}")

        # In toàn bộ field thật để bạn tự tìm field đúng nếu có cái "KHÔNG TÌM THẤY"
        print(f"\n--- Toàn bộ field thật của {doctype} (để tự đối chiếu nếu có field sai) ---")
        for k in sorted(real_fields):
            print(f"  {k}")


if __name__ == "__main__":
    main()
