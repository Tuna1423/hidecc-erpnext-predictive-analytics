"""
labeling_utils.py — Phần logic DÙNG CHUNG giữa build_labels.py (Delay Risk) và
build_labels_win.py (Win Probability).

CHỈ tách phần thực sự giống nhau: nhánh "còn đang mở, kiểm tra đã quá deadline chưa
-> nếu quá thì gán nhãn ngầm định (implied), nếu chưa thì right-censored". Đây là
mẫu hình xuất hiện ở cả 2 bài toán (Delay Risk: end_date; Win Probability:
expected_closing_date).

KHÔNG gộp toàn bộ build_label vào đây, vì phần còn lại của 2 hàm khác nhau về bản
chất (Delay Risk so sánh ngày-với-ngày để ra nhãn đã đóng; Win Probability phân loại
theo status categorical) — ép gộp sẽ làm mất đi sự khác biệt cần thiết giữa "right-
censored" và "out of scope" đã thống nhất trước đó.
"""

import pandas as pd


def censored_or_implied(cutoff: pd.Timestamp, deadline_date, implied_label: int, implied_status: str):
    """
    Dùng cho nhánh "còn đang mở tại cutoff, đối chiếu với 1 deadline nào đó":
      - deadline_date rỗng -> không đủ căn cứ áp dụng ngầm định -> (None, 'censored')
      - cutoff đã vượt deadline_date -> trả về nhãn ngầm định kèm tên trạng thái riêng
        do người gọi cung cấp (vd. 'late_open' bên Delay Risk, 'stale_open_assumed_lost'
        bên Win Probability)
      - cutoff chưa vượt deadline_date -> (None, 'censored') — right-censored thật sự

    implied_label/implied_status do nơi gọi quyết định, vì Ý NGHĨA của việc "quá hạn"
    khác nhau hoàn toàn giữa 2 bài toán (Delay Risk: quá hạn = chắc chắn trễ, gán 1;
    Win Probability: quá hạn = coi như đã thua, gán 0) — đây chính là lý do không gộp
    chung thành 1 hàm build_label() duy nhất.
    """
    if pd.isna(deadline_date):
        return None, "censored"
    if cutoff > deadline_date:
        return implied_label, implied_status
    return None, "censored"
