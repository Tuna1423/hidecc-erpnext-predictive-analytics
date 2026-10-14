"""
build_labels_delayrisk.py — Build nhãn (label) cho bài toán Delay Risk, kèm xác định snapshot
as-of date và loại right-censored records.

Tách riêng phần build nhãn ra khỏi build_dataset_delayrisk.py để test độc lập (không phụ thuộc vào
toàn bộ pipeline feature engineering).

4 TÌNH HUỐNG BẮT BUỘC (xem class TestBuildLabel ở cuối file):
1. Đúng hạn   — actual_close_date <= end_date              -> label 0
2. Trễ        — actual_close_date >  end_date              -> label 1
3. Chưa xong  — actual_close_date rỗng, tách 2 nhánh:
     a. cutoff đã vượt end_date -> biết chắc trễ dù chưa đóng mốc -> label 1 (KHÔNG loại)
     b. cutoff chưa vượt end_date -> right-censored thật sự       -> label None (LOẠI)
3. Thiếu ngày — end_date hoặc start_date (as_of) rỗng -> label None, đánh dấu "invalid",
   KHÁC với "censored" (thiếu dữ liệu là lỗi cần rà soát, không phải right-censoring).

LƯU Ý QUAN TRỌNG (phát hiện khi viết unit test): nếu end_date rỗng (NaT), phép so sánh
`actual_close_date > end_date` trong pandas/Python luôn trả về False (so sánh với NaT
không bao giờ True) — nếu không kiểm tra end_date rỗng TRƯỚC, bản ghi thiếu end_date sẽ
bị gán NHẦM thành nhãn 0 (đúng hạn) một cách âm thầm, thay vì bị loại vì thiếu dữ liệu.
Đây là lý do bắt buộc phải kiểm tra "thiếu ngày" TRƯỚC khi so sánh ngày.
"""

import unittest
import pandas as pd
from labeling_utils import censored_or_implied


# ---------------------------------------------------------------------------
# 1. XÁC ĐỊNH SNAPSHOT AS-OF
# ---------------------------------------------------------------------------

def determine_as_of(row: pd.Series):
    """
    Trả về (as_of, status).
    as_of = None nếu start_date rỗng -> không xác định được snapshot, phải loại khỏi
    dataset. Đây là lỗi dữ liệu (invalid), khác bản chất với right-censored.
    """
    start_date = row.get("start_date", pd.NaT)
    if pd.isna(start_date):
        return None, "invalid_missing_start_date"
    return start_date, "ok"


# ---------------------------------------------------------------------------
# 2. BUILD NHÃN
# ---------------------------------------------------------------------------

def build_label(row: pd.Series, cutoff: pd.Timestamp):
    """
    Trả về (label, status):
      label:  1 = trễ, 0 = đúng hạn, None = không dùng được (loại khỏi train/test)
      status: 'closed' | 'late_open' | 'censored'
              | 'invalid_missing_end_date' | 'invalid_missing_start_date'
    """
    as_of, as_of_status = determine_as_of(row)
    if as_of_status != "ok":
        return None, as_of_status

    # Kiểm tra thiếu end_date TRƯỚC khi so sánh ngày (xem lưu ý ở docstring đầu file
    # — so sánh với NaT luôn ra False, dễ gây nhãn sai âm thầm nếu bỏ qua bước này).
    end_date = row.get("end_date", pd.NaT)
    if pd.isna(end_date):
        return None, "invalid_missing_end_date"

    actual_close_date = row.get("actual_close_date", pd.NaT)

    if pd.notna(actual_close_date):
        label = int(actual_close_date > end_date)
        return label, "closed"

    if pd.isna(cutoff):
        raise ValueError("cutoff (ngày rút dữ liệu) không được rỗng")

    # Nhánh "còn đang mở" — dùng hàm dùng chung với build_labels_win.py (xem
    # labeling_utils.py). implied_label=1 vì bên Delay Risk, quá hạn = chắc chắn trễ.
    return censored_or_implied(cutoff, end_date, implied_label=1, implied_status="late_open")


def apply_labels(df: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """
    Áp build_label cho toàn bộ dataframe, trả về df có thêm 2 cột: label, censor_status.
    Dùng dtype="object" tường minh cho cột label — nếu không, pandas sẽ tự ép kiểu
    (None + int trộn lẫn) thành float và None biến thành NaN, gây khó phân biệt "nhãn 0"
    với "không có nhãn" khi kiểm tra bằng .isna() ở bước lọc trainable.
    """
    labels, statuses = [], []
    for _, row in df.iterrows():
        label, status = build_label(row, cutoff)
        labels.append(label)
        statuses.append(status)

    out = df.copy()
    out["label"] = pd.Series(labels, index=df.index, dtype="object")
    out["censor_status"] = pd.Series(statuses, index=df.index, dtype="object")
    return out


def report_label_summary(df_with_labels: pd.DataFrame):
    """In thống kê phân bố censor_status + tỷ lệ trainable, để đối chiếu khi chạy thật."""
    total = len(df_with_labels)
    counts = df_with_labels["censor_status"].value_counts()
    print(f"Tổng số dòng: {total}")
    print(counts.to_string())
    trainable = df_with_labels["label"].notna().sum()
    print(f"Số dòng dùng được để train/test: {trainable} ({trainable/total:.1%})")

    invalid = counts.get("invalid_missing_end_date", 0) + counts.get("invalid_missing_start_date", 0)
    if invalid > 0:
        print(f"[CẢNH BÁO] {invalid} dòng bị loại do THIẾU DỮ LIỆU (invalid), khác với "
              f"right-censored — cần rà lại nguồn dữ liệu, đây là lỗi dữ liệu chứ không "
              f"phải hiện tượng dự án chưa xong.")


# ---------------------------------------------------------------------------
# UNIT TESTS — 4 tình huống bắt buộc: đúng hạn, trễ, chưa xong, thiếu ngày
# ---------------------------------------------------------------------------

class TestBuildLabel(unittest.TestCase):

    def setUp(self):
        self.cutoff = pd.Timestamp("2026-07-28")
        self.start_date = pd.Timestamp("2026-01-01")
        self.end_date = pd.Timestamp("2026-03-01")

    def _row(self, actual_close_date=pd.NaT, end_date=None, start_date=None):
        return pd.Series({
            "start_date": self.start_date if start_date is None else start_date,
            "end_date": self.end_date if end_date is None else end_date,
            "actual_close_date": actual_close_date,
        })

    # ---- 1. ĐÚNG HẠN ----
    def test_on_time(self):
        row = self._row(actual_close_date=pd.Timestamp("2026-02-20"))  # trước end_date
        label, status = build_label(row, self.cutoff)
        self.assertEqual(label, 0)
        self.assertEqual(status, "closed")

    def test_on_time_exact_end_date(self):
        # đóng đúng NGÀY end_date -> không tính là trễ (điều kiện là > end_date, không phải >=)
        row = self._row(actual_close_date=self.end_date)
        label, status = build_label(row, self.cutoff)
        self.assertEqual(label, 0)
        self.assertEqual(status, "closed")

    # ---- 2. TRỄ ----
    def test_late(self):
        row = self._row(actual_close_date=pd.Timestamp("2026-03-15"))  # sau end_date
        label, status = build_label(row, self.cutoff)
        self.assertEqual(label, 1)
        self.assertEqual(status, "closed")

    # ---- 3. CHƯA XONG (2 nhánh) ----
    def test_still_open_already_overdue(self):
        # end_date đã qua so với cutoff, nhưng chưa đóng mốc -> biết chắc trễ, KHÔNG loại
        row = self._row(actual_close_date=pd.NaT, end_date=pd.Timestamp("2026-05-01"))
        label, status = build_label(row, self.cutoff)  # cutoff 2026-07-28 > 2026-05-01
        self.assertEqual(label, 1)
        self.assertEqual(status, "late_open")

    def test_still_open_not_yet_due(self):
        # end_date chưa tới so với cutoff, chưa đóng mốc -> right-censored thật sự, LOẠI
        row = self._row(actual_close_date=pd.NaT, end_date=pd.Timestamp("2026-12-01"))
        label, status = build_label(row, self.cutoff)  # cutoff 2026-07-28 < 2026-12-01
        self.assertIsNone(label)
        self.assertEqual(status, "censored")

    # ---- 4. THIẾU NGÀY ----
    def test_missing_end_date(self):
        row = self._row(actual_close_date=pd.NaT, end_date=pd.NaT)
        label, status = build_label(row, self.cutoff)
        self.assertIsNone(label)
        self.assertEqual(status, "invalid_missing_end_date")

    def test_missing_start_date(self):
        row = self._row(actual_close_date=pd.NaT, start_date=pd.NaT)
        label, status = build_label(row, self.cutoff)
        self.assertIsNone(label)
        self.assertEqual(status, "invalid_missing_start_date")

    def test_missing_end_date_even_if_closed(self):
        # Bug đã phát hiện: dù actual_close_date có giá trị, nếu end_date rỗng thì so
        # sánh actual_close_date > NaT sẽ luôn False -> nhầm thành "đúng hạn" nếu không
        # chặn trường hợp này trước. Test này khẳng định phải trả về invalid, không phải 0.
        row = self._row(actual_close_date=pd.Timestamp("2026-03-15"), end_date=pd.NaT)
        label, status = build_label(row, self.cutoff)
        self.assertIsNone(label)
        self.assertEqual(status, "invalid_missing_end_date")

    def test_cutoff_missing_raises(self):
        row = self._row(actual_close_date=pd.NaT, end_date=pd.Timestamp("2026-05-01"))
        with self.assertRaises(ValueError):
            build_label(row, pd.NaT)


class TestApplyLabels(unittest.TestCase):
    def test_apply_labels_on_dataframe(self):
        cutoff = pd.Timestamp("2026-07-28")
        df = pd.DataFrame([
            {"start_date": pd.Timestamp("2026-01-01"), "end_date": pd.Timestamp("2026-03-01"),
             "actual_close_date": pd.Timestamp("2026-02-20")},   # đúng hạn
            {"start_date": pd.Timestamp("2026-01-01"), "end_date": pd.Timestamp("2026-03-01"),
             "actual_close_date": pd.Timestamp("2026-03-15")},   # trễ
            {"start_date": pd.Timestamp("2026-01-01"), "end_date": pd.Timestamp("2026-05-01"),
             "actual_close_date": pd.NaT},                        # chưa xong - đã quá hạn
            {"start_date": pd.Timestamp("2026-01-01"), "end_date": pd.Timestamp("2026-12-01"),
             "actual_close_date": pd.NaT},                        # chưa xong - censored
            {"start_date": pd.Timestamp("2026-01-01"), "end_date": pd.NaT,
             "actual_close_date": pd.NaT},                        # thiếu ngày
        ])
        out = apply_labels(df, cutoff)
        self.assertEqual(
            list(out["censor_status"]),
            ["closed", "closed", "late_open", "censored", "invalid_missing_end_date"],
        )
        self.assertEqual(list(out["label"]), [0, 1, 1, None, None])


if __name__ == "__main__":
    unittest.main(verbosity=2)