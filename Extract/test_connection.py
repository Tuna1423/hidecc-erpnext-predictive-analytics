"""Chạy file này TRUOC extract.py de xac nhan key/URL dung, chi fetch 1 doctype nho.
Doc credentials tu file .env cung thu muc (qua python-dotenv), khong hard-code.
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

BASE = os.environ.get("ERPNEXT_BASE_URL", "")
API_KEY = os.environ.get("ERPNEXT_API_KEY", "")
API_SECRET = os.environ.get("ERPNEXT_API_SECRET", "")

if not (BASE and API_KEY and API_SECRET):
    raise RuntimeError(
        "Thiếu ERPNEXT_BASE_URL/ERPNEXT_API_KEY/ERPNEXT_API_SECRET. Tạo file .env cùng "
        "thư mục (xem .env.example) rồi điền giá trị thật vào đó."
    )

print(f"BASE_URL = {BASE!r}")
print(f"API_KEY (masked) = {API_KEY[:4]}...{API_KEY[-2:]}  (do dai: {len(API_KEY)})")
print(f"API_SECRET (masked) = {API_SECRET[:4]}...{API_SECRET[-2:]}  (do dai: {len(API_SECRET)})")

HEADERS = {"Authorization": f"token {API_KEY}:{API_SECRET}"}

r = requests.get(
    f"{BASE}/api/resource/Project",
    headers=HEADERS,
    params={"limit_page_length": 5, "fields": json.dumps(["name", "project_type", "expected_start_date"])},
    timeout=30,
)
print("\nStatus code:", r.status_code)
if r.status_code != 200:
    print("Response body:", r.text[:500])
r.raise_for_status()
print(r.json())