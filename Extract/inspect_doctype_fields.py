"""
inspect_doctype_fields.py — Xem TẤT CẢ field thật của 1 DocType bằng cách lấy 1-3
bản ghi MẪU với fields=["*"] (lấy toàn bộ cột), thay vì đọc bảng metadata DocType
(bảng đó có thể bị chặn quyền, như đã gặp lỗi 401/403).

Cách này dùng ĐÚNG quyền đọc dữ liệu bạn đã có sẵn (đã chứng minh hoạt động khi tải
Project/Discipline Allocation trước đó), không cần quyền đặc biệt nào thêm.

CÁCH DÙNG:
  python3 inspect_doctype_fields.py "Opportunity"
  python3 inspect_doctype_fields.py "Quotation"
  python3 inspect_doctype_fields.py "Sales Order"

Với CHILD TABLE (như Discipline Allocation, Timesheet Detail...), phải truyền thêm
tên DocType cha ở tham số thứ 2:
  python3 inspect_doctype_fields.py "Discipline Allocation" "Design Discipline Assignment"
"""

import sys
import json
import requests

BASE_URL = "http://103.63.111.136:8100"
API_KEY = "b703d1745c6807d"
API_SECRET = "da8dbd5700ca5d2"

HEADERS = {"Authorization": f"token {API_KEY}:{API_SECRET}"}


def inspect(doctype: str, parent: str = None, limit: int = 3):
    params = {"limit_page_length": limit, "fields": json.dumps(["*"])}
    if parent:
        params["parent"] = parent

    r = requests.get(f"{BASE_URL}/api/resource/{doctype}", headers=HEADERS, params=params, timeout=60)
    print(f"Status code: {r.status_code}")

    if r.status_code != 200:
        print("Response body:", r.text[:800])
        if r.status_code in (401, 403) and not parent:
            print("\n[GỢI Ý] Nếu đây là child table (bảng con), lỗi permission này có thể "
                  "do THIẾU tham số parent — thử lại với:")
            print(f'  python3 inspect_doctype_fields.py "{doctype}" "<Tên DocType cha>"')
        return

    rows = r.json()["data"]
    if not rows:
        print("Không có bản ghi nào trả về (bảng đang rỗng, hoặc filter/parent chưa đúng).")
        return

    print(f"\nSố bản ghi mẫu lấy được: {len(rows)}")
    print(f"Số field tìm thấy trong bản ghi đầu tiên: {len(rows[0])}\n")
    print(f"{'fieldname (tên field thật)':35s} | giá trị mẫu (bản ghi đầu tiên)")
    print("-" * 90)
    for key, value in rows[0].items():
        display_value = str(value)
        if len(display_value) > 45:
            display_value = display_value[:45] + "..."
        print(f"{key:35s} | {display_value}")

    print(f"\n(Đây là field + giá trị THẬT lấy trực tiếp từ dữ liệu, không phải đoán)")


def main():
    if len(sys.argv) < 2:
        print("Thiếu tên DocType. Cách dùng:")
        print('  python3 inspect_doctype_fields.py "Opportunity"')
        print('  python3 inspect_doctype_fields.py "Discipline Allocation" "Design Discipline Assignment"')
        return

    doctype = sys.argv[1]
    parent = sys.argv[2] if len(sys.argv) > 2 else None
    inspect(doctype, parent=parent)


if __name__ == "__main__":
    main()