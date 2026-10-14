"""
build_labels_win_v2.py — Build nhãn cho bài toán Opportunity Win Probability, kèm xác
định snapshot as-of date và loại right-censored / out-of-scope.

Ánh xạ từ build_labels.py (Delay Risk) sang bài toán này:
  Nguồn nhãn:      Opportunity.status (Converted/Lost)     [thay actual_close_date]
  As-of date:      ngày phát sinh Quotation đầu tiên        [thay start_date bộ môn]
  Right-censored:  status vẫn "Open" tại cutoff             [thay chưa đóng mốc]

KHÁC BIỆT so với Delay Risk — 2 điểm quan trọng:

1. Có thêm nhóm loại thứ 3 KHÁC BẢN CHẤT với right-censored: Opportunity CHƯA TỪNG
   CÓ Quotation nào (as-of date không tồn tại) -> "out_of_scope", không phải "chưa
   biết kết quả" mà là "ngoài phạm vi bài toán" (bài toán chỉ trả lời cho các cơ hội
   đã đi đến bước báo giá). Xem feature_dictionary.md phần as-of date Win Probability.

2. GIẢ ĐỊNH NGHIỆP VỤ (đã thống nhất, cần Sales/CRM xác nhận lại): Opportunity đang
   "Open" nhưng đã quá `expected_closing_date` (quá hạn dự kiến chốt) tại cutoff ->
   coi như ĐÃ THUA (label 0), tương tự cơ chế "late_open" bên Delay Risk nhưng NGƯỢC
   CHIỀU (bên đó gán "chắc chắn trễ"=1, bên này gán "chắc chắn thua"=0). Đây KHÔNG
   phải sự thật đã xác nhận từ nghiệp vụ thật, chỉ là quyết định tạm để không loại bỏ
   quá nhiều cơ hội "chết nhưng chưa đóng status" — cần xác nhận lại với Sales/CRM
   trước khi dùng cho báo cáo chính thức. Có thể tắt hành vi này bằng cách set
   ASSUME_STALE_OPEN_AS_LOST = False.
"""

import unittest
import pandas as pd
from labeling_utils import censored_or_implied

# Bật/tắt giả định "Open quá hạn dự kiến chốt -> coi như đã thua" (xem docstring).
ASSUME_STALE_OPEN_AS_LOST = True


# ---------------------------------------------------------------------------
# 1. XÁC ĐỊNH SNAPSHOT AS-OF
# ---------------------------------------------------------------------------

def determine_as_of_win(row: pd.Series):
    """
    as_of = ngày phát sinh Quotation đầu tiên (quotation_date).
    Nếu rỗng -> Opportunity chưa từng có Quotation -> OUT OF SCOPE, không phải
    right-censored (khác bản chất, xem docstring đầu file).
    """
    quotation_date = row.get("quotation_date", pd.NaT)
    if pd.isna(quotation_date):
        return None, "out_of_scope_no_quotation"
    return quotation_date, "ok"


# ---------------------------------------------------------------------------
# 2. BUILD NHÃN
# ---------------------------------------------------------------------------

def build_label_win(row: pd.Series, cutoff: pd.Timestamp):
    """
    Trả về (label, status):
      label:  1 = Won, 0 = Lost, None = không dùng được (loại khỏi train/test)
      status: 'closed_won' | 'closed_lost' | 'censored' | 'stale_open_assumed_lost'
              | 'out_of_scope_no_quotation' | 'invalid_missing_status'
    """
    as_of, as_of_status = determine_as_of_win(row)
    if as_of_status != "ok":
        return None, as_of_status

    status = row.get("status", None)
    if pd.isna(status) or status is None:
        return None, "invalid_missing_status"

    if status == "Converted":
        return 1, "closed_won"
    if status == "Lost":
        return 0, "closed_lost"

    # Còn lại: status chưa ngã ngũ (Open/Replied/Quotation...)
    if pd.isna(cutoff):
        raise ValueError("cutoff (ngày rút dữ liệu) không được rỗng")

    if ASSUME_STALE_OPEN_AS_LOST:
        expected_closing_date = row.get("expected_closing_date", pd.NaT)
        # Dùng hàm dùng chung với build_labels.py (xem labeling_utils.py).
        # implied_label=0 vì bên Win Probability, quá hạn dự kiến chốt = coi như đã thua
        # (GIẢ ĐỊNH NGHIỆP VỤ, xem cảnh báo ở docstring đầu file).
        return censored_or_implied(cutoff, expected_closing_date,
                                    implied_label=0, implied_status="stale_open_assumed_lost")

    return None, "censored"


def apply_labels_win(df: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    labels, statuses = [], []
    for _, row in df.iterrows():
        label, status = build_label_win(row, cutoff)
        labels.append(label)
        statuses.append(status)

    out = df.copy()
    out["label"] = pd.Series(labels, index=df.index, dtype="object")
    out["censor_status"] = pd.Series(statuses, index=df.index, dtype="object")
    return out


def report_label_summary_win(df_with_labels: pd.DataFrame):
    total = len(df_with_labels)
    counts = df_with_labels["censor_status"].value_counts()
    print(f"Tổng số Opportunity: {total}")
    print(counts.to_string())

    out_of_scope = counts.get("out_of_scope_no_quotation", 0)
    print(f"\nNgoài phạm vi bài toán (chưa từng có Quotation): {out_of_scope} "
          f"({out_of_scope/total:.1%}) — KHÁC với right-censored, không tính vào tỷ lệ loại do thiếu thông tin.")

    stale = counts.get("stale_open_assumed_lost", 0)
    if stale > 0:
        print(f"[GIẢ ĐỊNH NGHIỆP VỤ] {stale} dòng được gán 'đã thua' do Open quá hạn "
              f"dự kiến chốt — cần Sales/CRM xác nhận lại giả định này trước khi dùng "
              f"cho báo cáo chính thức.")

    trainable = df_with_labels["label"].notna().sum()
    print(f"\nSố dòng dùng được để train/test: {trainable} ({trainable/total:.1%})")


# ---------------------------------------------------------------------------
# UNIT TESTS
# ---------------------------------------------------------------------------

class TestBuildLabelWin(unittest.TestCase):

    def setUp(self):
        self.cutoff = pd.Timestamp("2026-07-28")
        self.quotation_date = pd.Timestamp("2026-02-01")

    def _row(self, status, quotation_date=None, expected_closing_date=pd.NaT):
        return pd.Series({
            "quotation_date": self.quotation_date if quotation_date is None else quotation_date,
            "status": status,
            "expected_closing_date": expected_closing_date,
        })

    def test_won(self):
        row = self._row(status="Converted")
        label, status = build_label_win(row, self.cutoff)
        self.assertEqual(label, 1)
        self.assertEqual(status, "closed_won")

    def test_lost(self):
        row = self._row(status="Lost")
        label, status = build_label_win(row, self.cutoff)
        self.assertEqual(label, 0)
        self.assertEqual(status, "closed_lost")

    def test_open_not_stale_censored(self):
        # Open, chưa qua expected_closing_date -> right-censored, loại
        row = self._row(status="Open", expected_closing_date=pd.Timestamp("2026-12-01"))
        label, status = build_label_win(row, self.cutoff)
        self.assertIsNone(label)
        self.assertEqual(status, "censored")

    def test_open_stale_assumed_lost(self):
        # Open, đã qua expected_closing_date -> giả định đã thua (label 0)
        row = self._row(status="Open", expected_closing_date=pd.Timestamp("2026-04-01"))
        label, status = build_label_win(row, self.cutoff)
        self.assertEqual(label, 0)
        self.assertEqual(status, "stale_open_assumed_lost")

    def test_open_missing_expected_closing_date_falls_back_to_censored(self):
        # Open, KHÔNG có expected_closing_date -> không đủ căn cứ áp giả định -> censored
        row = self._row(status="Open", expected_closing_date=pd.NaT)
        label, status = build_label_win(row, self.cutoff)
        self.assertIsNone(label)
        self.assertEqual(status, "censored")

    def test_out_of_scope_no_quotation(self):
        # Chưa từng có Quotation -> out of scope, KHÁC với censored
        row = self._row(status="Open", quotation_date=pd.NaT)
        label, status = build_label_win(row, self.cutoff)
        self.assertIsNone(label)
        self.assertEqual(status, "out_of_scope_no_quotation")

    def test_missing_status(self):
        row = self._row(status=None)
        label, status = build_label_win(row, self.cutoff)
        self.assertIsNone(label)
        self.assertEqual(status, "invalid_missing_status")

    def test_cutoff_missing_raises(self):
        row = self._row(status="Open", expected_closing_date=pd.Timestamp("2026-12-01"))
        with self.assertRaises(ValueError):
            build_label_win(row, pd.NaT)

    def test_assumption_can_be_disabled(self):
        # Khi tắt giả định, Open quá hạn cũng chỉ là censored, không gán label 0.
        # ĐÃ SỬA (feedback rà soát): không tự import lại chính module này nữa
        # (cách cũ "import build_labels_win as m" bị lỗi path khi file được đặt trong
        # thư mục/tên khác trên máy khác) — dùng "global" để sửa trực tiếp biến module-
        # level, vì test này vốn nằm NGAY TRONG file build_labels_win.py, không cần
        # import gì cả.
        global ASSUME_STALE_OPEN_AS_LOST
        original = ASSUME_STALE_OPEN_AS_LOST
        ASSUME_STALE_OPEN_AS_LOST = False
        try:
            row = self._row(status="Open", expected_closing_date=pd.Timestamp("2026-04-01"))
            label, status = build_label_win(row, self.cutoff)
            self.assertIsNone(label)
            self.assertEqual(status, "censored")
        finally:
            ASSUME_STALE_OPEN_AS_LOST = original


if __name__ == "__main__":
    unittest.main(verbosity=2)