# Feature Dictionary & Metric Plan

**Dự báo Project Delay Risk & Opportunity Win Probability (ERPNext)**
**Phiên bản:** v5.0 — sửa lỗi rò rỉ ở n_open_overdue_tasks_at_snapshot, hoàn thiện workload feature, smoothing historic rate, xác nhận dữ liệu thật

**Changelog v5.0:**
1. Sửa lỗi rò rỉ nghiêm trọng ở `n_open_overdue_tasks_at_snapshot`: gộp 2 nhánh sai thành 1 điều kiện đúng `end_date < as_of AND (actual_close_date IS NULL OR actual_close_date > as_of)`. Áp dụng cùng nguyên tắc để sửa `n_disciplines_known_at_snapshot` (chỉ đếm bộ môn đã start_date ≤ as_of).
2. `extract.py`: cố định `DATA_CUTOFF`, không để trống, ghi rõ lý do cần tái lập được kết quả.
3. Ghi rõ nhãn mô phỏng trong `extract.py` là ngẫu nhiên độc lập với feature — AUC ~0.5 trên dữ liệu mô phỏng là kỳ vọng đúng, không phản ánh chất lượng feature.
4. Historic rate: chọn phương án smoothing về global_rate (point-in-time) với hệ số k=5, thay vì để NaN thô hoặc loại bỏ feature.
5. `past_closed` đưa ra ngoài vòng lặp; thêm assert kiểm tra test set đủ 2 lớp; đã hiện thực tính toán thật cho `total_workload_pct` và `pct_staff_overloaded_at_snapshot` (trước đây tài liệu mô tả nhưng code chưa tính).
6. Xác nhận dữ liệu thật: `start_date`/`end_date` đã được điền đầy đủ (lỗi seed trước đó đã khắc phục). Quy mô: 59 dự án, 620 dòng Discipline Allocation (320 đã đóng), 790 Task, 183 Opportunity, 207 biên bản nghiệm thu.
7. Bổ sung `load_from_erpnext_api()` trong `extract.py` + hướng dẫn sử dụng (biến môi trường cho API key, lưu ý child table Discipline Allocation bắt buộc kèm parent, contract_value cộng dồn từ Sales Order).

**Quy ước lớp:**
- `F` = Feature - biết được tại as-of date, dùng được để huấn luyện.
- `L` = Label-only - chỉ biết được sau khi kết quả đã xảy ra (post-outcome), chỉ dùng để sinh nhãn, cấm đưa vào feature.
- `X` = Loại bỏ hoàn toàn - không dùng cho cả feature lẫn nhãn.

---



## Subtask 2.1 — Feature Dictionary: Bài toán Delay Risk

**As-of date: `Project.expected_start_date`**

**Lý do nghiệp vụ:** Theo biên bản khảo sát Đội thiết kế, một dự án chỉ được mở khi đã xác nhận đủ 3 điều kiện tiên quyết: thiết kế cơ sở đã phê duyệt, nhiệm vụ thiết kế đã phê duyệt, và tiêu chuẩn quy phạm hiện hành. Nghĩa là tại thời điểm `expected_start_date`, phạm vi và các thông tin cơ bản của dự án (loại dự án, giá trị hợp đồng...) đã thực sự chốt về mặt nghiệp vụ, không phải chỉ "có trong hệ thống" một cách hình thức.

Bước đầu tiên ngay sau khi mở dự án là "lập kế hoạch triển khai dưới dạng bảng tiến độ; lập bảng phân công nhiệm vụ" — tức là các feature như `n_milestones`, `planned_duration_days` được xác lập ngay tại/sát thời điểm này, không phải chờ đến giữa dự án mới có. Vì vậy chọn mốc này vừa đảm bảo feature không rỗng, vừa đúng mục tiêu cảnh báo sớm (kịp điều chỉnh kế hoạch trước khi dự án thực sự chạy).

### Tự kiểm tra: as-of date = expected_start_date khiến feature "động" thành hằng số

Áp đúng lập luận đã dùng ở Subtask 2.2 (as-of date quá sớm → feature hành vi thành hằng số) vào đây: tại đúng lúc `expected_start_date`, `n_open_overdue_tasks_at_snapshot` **chắc chắn = 0 cho mọi dự án** (chưa chạy thì chưa thể có gì quá hạn) — dead feature giống hệt `has_quotation`. Tương tự, đếm bộ môn "đang mở" tại đúng lúc mở dự án cũng chỉ trả về đúng số bộ môn được giao ban đầu (vì chưa bộ môn nào kịp đóng), không phản ánh workload thực sự khác biệt giữa các dự án.

Đề bài gốc cho phép snapshot "tại thời điểm dự án bắt đầu **hoặc đang chạy**" — nên as-of date không bắt buộc cố định ở lúc mở dự án. Quyết định đổi đơn vị phân tích sang cấp mốc/bộ môn (xem mục dưới) giải quyết vấn đề này một cách tự nhiên: mỗi dòng snapshot tại thời điểm bộ môn đó bắt đầu, rải rác khắp vòng đời dự án, nên các feature động này có phương sai thật thay vì là hằng số.

### Đơn vị phân tích: đổi từ cấp Project sang cấp (Project, Discipline)

Với seed hiện tại chỉ 15-50 dự án và khoảng 10 feature, nếu 1 dòng = 1 dự án và tỷ lệ trễ ~30%, số ca dương chỉ còn 5-15 — không đạt quy tắc tối thiểu 10 ca dương/biến, mô hình sẽ học nhiễu và mọi chỉ số đều vô nghĩa.

**Quyết định: đổi đơn vị phân tích thành 1 dòng = 1 cặp (Project, Discipline), snapshot tại ngày bộ môn đó bắt đầu (`start_date` kế hoạch của Discipline Allocation)** — thay vì cắt bớt còn 3-4 feature ở cấp Project. Lý do chọn hướng này:
- Với ~8-11 bộ môn/dự án, số dòng tăng lên khoảng 150-500 — cải thiện đáng kể tỷ lệ ca dương/biến so với giữ nguyên cấp Project.
- Giải quyết đồng thời vấn đề as-of date "chết" nêu ở mục tự kiểm tra trên — không phải đánh đổi thêm, mà cùng một quyết định giải quyết cả hai vấn đề.
- Khớp với đề bài gốc, vốn đã cho phép nhãn ở cấp milestone.

**Bắt buộc đi kèm:** vì các dòng cùng một dự án không độc lập (chia sẻ chung feature cấp dự án như contract_value, pm_id...), phải chia train/test theo **nhóm project_id** (mọi bộ môn của 1 dự án nằm trọn 1 phía), kết hợp với nguyên tắc chia theo thời gian đã chốt trước đó (dự án có as-of date sớm hơn vào train, muộn hơn vào test) — không chia ngẫu nhiên theo dòng.

### `actual_end_date`/`act_end_date` luôn rỗng

Mã nguồn ERPNext v16 cho thấy `Project.actual_end_date`, `Project.actual_start_date`, `Task.act_end_date` đều được hệ thống tự điền dựa trên dữ liệu Timesheet (giờ công log theo ngày). Vì hidecc không ghi giờ theo ngày (không dùng Timesheet để chấm công theo cách đó), ba trường này sẽ luôn rỗng trong dữ liệu thật. Nếu vẫn dùng chúng làm nhãn như bản v1.0, quy tắc "loại bản ghi chưa có ngày thực tế" sẽ áp dụng cho toàn bộ dòng dữ liệu → tập huấn luyện rỗng, không train được gì.

Nguồn nhãn được đổi sang trường sau, vì đây là các trường **nhập tay**, không phụ thuộc vào Timesheet nên không bị rỗng theo lý do trên:
- `Discipline Allocation.actual_close_date` (xem chi tiết field này ở mục workload bên dưới) — do chủ trì thiết kế nhập khi đóng mốc bộ môn.

Nhãn được sinh bằng cách so `actual_close_date` với `end_date` (kế hoạch) của **chính bộ môn đó**: muộn hơn → nhãn 1 (trễ); đúng hạn hoặc sớm hơn → nhãn 0. Cần kiểm tra tỷ lệ null của field này trên dữ liệu thật trước khi chốt, không giả định luôn sẵn có.

### Loại right-censored làm lệch tập dữ liệu, đo mức lệch

Vấn đề: những bộ môn trễ **nặng nhất** thường là những bộ môn **vẫn đang mở, chưa đóng mốc** vì trễ càng nặng thì càng có khả năng chưa kết thúc tại thời điểm rút dữ liệu. Nếu áp dụng quy tắc "chưa có ngày đóng mốc thực tế → loại khỏi tập huấn luyện", ta sẽ loại đúng nhóm rủi ro cao nhất, khiến mô hình chỉ học trên các bộ môn đã đóng, thường ít trễ nặng hơn → mô hình đánh giá rủi ro thấp hơn thực tế khi đưa vào vận hành.

Cách xử lý — tách rõ hai loại bản ghi chưa đóng mốc thay vì gộp chung là "right-censored":
- **Đã trễ nhưng chưa đóng** (`actual_close_date` rỗng, nhưng ngày rút dữ liệu đã vượt qua `end_date`): đây là trường hợp **đã biết chắc kết quả là trễ** tại thời điểm rút dữ liệu, dù bộ môn chưa đóng mốc. Không cần đợi đến khi đóng mốc mới biết nó trễ — chỉ cần đối chiếu ngày rút dữ liệu với ngày kỳ vọng. Nhóm này **gán nhãn 1**, không loại.
- **Chưa trễ và chưa đóng** (`actual_close_date` rỗng, ngày rút dữ liệu vẫn còn trong hạn `end_date`): đây mới thực sự là right-censored đúng nghĩa — chưa đủ căn cứ để biết bộ môn cuối cùng có trễ hay không. Nhóm này **loại khỏi tập huấn luyện**.

Cách tách này giữ lại được phần lớn các bộ môn trễ nặng (vì phần lớn chúng rơi vào nhóm đầu — "đã trễ nhưng chưa đóng"), giảm đáng kể độ lệch so với việc loại toàn bộ bản ghi chưa đóng mốc.

Yêu cầu bắt buộc — đo mức lệch còn lại: sau khi tách theo quy tắc trên, vẫn cần định lượng phần dữ liệu bị loại (nhóm "chưa trễ và chưa đóng") ảnh hưởng thế nào đến bức tranh tổng thể, bằng cách báo cáo tối thiểu hai con số trong notebook/báo cáo:
- Tỷ lệ số bộ môn bị loại thật sự (right-censored đúng nghĩa) trên tổng số dòng.
- So sánh phân bố `planned_duration_days` (hoặc contract_value cấp dự án) giữa nhóm bị loại và nhóm được giữ lại — nếu nhóm bị loại có xu hướng là các dự án dài hơn/phức tạp hơn, đây là dấu hiệu mô hình vẫn thiên lệch về phía "dự án đơn giản, dễ dự đoán", cần nêu rõ trong phần giới hạn của báo cáo.

### Feature thay cho workload — dùng field thật đã bổ sung vào Discipline Allocation

Discipline Allocation nay có thêm 2 trường thật (DocType riêng của hidecc, không có tiền tố `custom_`):
- `actual_hours`: công thực tế, do chủ trì nhập khi đóng mốc bộ môn.
- `actual_close_date`: ngày đóng mốc thực tế; rỗng nghĩa là bộ môn còn đang mở.

Đây là 2 mốc/giá trị có thật, không cần suy diễn qua Task nữa như đề xuất trước đó.

**Định nghĩa:** `n_open_disciplines_at_snapshot` (theo từng người) — tại as-of date T, đếm số cặp (dự án, bộ môn) mà người đó đang được phân công, thoả: `actual_close_date` rỗng HOẶC `actual_close_date` > T.

Từ đó suy ra:
- `total_workload_pct`: tỷ lệ bộ môn đang mở của một người trên tổng số bộ môn người đó từng được phân công tính đến T.
- `pct_staff_overloaded`: % nhân sự có `n_open_disciplines_at_snapshot` vượt ngưỡng quá tải (ngưỡng cụ thể cần thống nhất với trưởng bộ phận thiết kế).

**Giới hạn 1 — `start_date`/`end_date` là ngày kế hoạch và có thể bị sửa đè:** hai trường này là ngày kế hoạch, có thể sửa lại sau khi tạo. Nếu một bộ môn bị dời `end_date` vì dự án chậm, thì đọc giá trị "hiện tại" của trường này tại thời điểm rút dữ liệu tức là đang lấy thông tin phát sinh **sau** as-of date (chính bộ môn đó đã thể hiện dấu hiệu trễ trước khi bị dời lịch). Vì Discipline Allocation không lưu lịch sử thay đổi, không thể khôi phục lại giá trị `end_date` gốc tại đúng lúc snapshot. Đây là giới hạn cần nêu rõ trong báo cáo, không tự sửa được nếu không có version history — giả định tạm thời là `start_date`/`end_date` không bị dời đáng kể so với lúc tạo.

**Giới hạn 2 — phân công không có lịch sử (giả định phân công ổn định):** Discipline Allocation là bảng con, bị sửa đè tại chỗ, nên tại as-of date chỉ nhìn thấy được phân công **hiện tại** (tại lúc rút dữ liệu), không phải phân công tại đúng thời điểm as-of date trong quá khứ. Nếu một dự án gặp khó khăn rồi được bổ sung thêm người giữa chừng, việc tính `n_open_disciplines_at_snapshot` có thể vô tình đếm luôn cả phân công phát sinh sau as-of date của dòng đang xét (lookahead nhẹ). Đây là giả định (không phải sự thật đã kiểm chứng) cần ghi rõ trong phần giới hạn của báo cáo: *giả định phân công tại thời điểm rút dữ liệu xấp xỉ đúng phân công tại as-of date, tức phân công ít thay đổi giữa chừng dự án.*

Nếu qua kiểm tra dữ liệu thật, `actual_close_date` không được nhập đều đặn hoặc không gán được người cụ thể cho từng bản ghi, feature này cần bị loại khỏi baseline và ghi nhận là giới hạn dữ liệu.

### Sửa lỗi rò rỉ ở `n_open_overdue_tasks_at_snapshot` (bản trước có bug)

Bản trước tách 2 nhánh: (1) chưa đóng và đã quá hạn tại as_of, (2) đã đóng nhưng đóng muộn hơn kế hoạch. Nhánh (2) sai — nó dùng thông tin "cuối cùng có đóng muộn không", một sự thật chỉ biết được **sau** khi bản ghi đó đã đóng, tức là thông tin từ tương lai so với as_of của dòng đang xét. Nhánh (1) cũng sai theo hướng ngược lại — dùng `isna()` (trạng thái tại lúc rút dữ liệu) thay vì trạng thái đúng tại as_of, nên bỏ sót các bản ghi đang mở tại as_of nhưng đã đóng (dù trễ hay đúng hạn) trước lúc rút dữ liệu.

**Sửa lại thành đúng 1 điều kiện duy nhất**, cùng logic đã dùng đúng ở `n_open_disciplines_at_snapshot`:

```
end_date < as_of  AND  (actual_close_date IS NULL OR actual_close_date > as_of)
```

Tức là: tại as_of, bản ghi đã quá hạn kế hoạch "VÀ" vẫn đang mở tại đúng thời điểm as_of — không quan tâm sau này nó đóng đúng hay đóng muộn, vì tại as_of không thể biết trước điều đó. `n_disciplines_known_at_snapshot` cũng được sửa theo cùng nguyên tắc: chỉ đếm các bộ môn có `start_date ≤ as_of`, không đếm toàn bộ bộ môn của dự án như bản trước (bản trước vô tình đếm cả bộ môn sẽ bắt đầu sau as_of của dòng đang xét).

### Historic rate — xử lý NaN bằng smoothing (Điểm 4)

Chọn phương án smoothing thay vì loại bỏ feature: `rate = (n_late + k × global_rate) / (n + k)` với `k = 5` (giá trị tạm, cần tinh chỉnh khi có đủ dữ liệu thật). `global_rate` cũng được tính point-in-time (chỉ từ các bản ghi đã đóng trước as_of trong toàn hệ thống, không lấy từ toàn bộ dataset để tránh rò rỉ). Cách này giúp: n=0 trả về đúng `global_rate` (không NaN), n nhỏ bị kéo về gần `global_rate`, n lớn thì gần với tỷ lệ thực đo được — tránh việc vài quan sát đầu tiên (n=1, n=2) tạo ra giá trị 0% hoặc 100% cực đoan.

### Lưu ý về dữ liệu mô phỏng dùng để kiểm thử pipeline (Điểm 3)

Trong `extract.py`, nhãn mô phỏng (`is_late = rng.random() < 0.30`) được sinh **hoàn toàn độc lập** với mọi feature. Vì vậy AUC đo được trên dữ liệu mô phỏng sẽ luôn xấp xỉ 0.5 dù code đúng hay sai — đây KHÔNG phải dấu hiệu feature kém, chỉ là bản chất của dữ liệu giả lập dùng để kiểm thử pipeline (đúng shape, không lỗi, không rò rỉ). Không dùng số AUC ở bước này để đánh giá chất lượng feature; chỉ đánh giá được khi chạy trên dữ liệu thật.

### Xác nhận dữ liệu thật (đã có, thay cho giả định trước đây)

`start_date`/`end_date` của Discipline Allocation trước đó bị rỗng toàn bộ do lỗi seed dữ liệu, nay đã được khắc phục và điền đầy đủ — đúng như khuyến nghị trước đó là phải kiểm tra tỷ lệ null trên dữ liệu thật thay vì giả định sẵn có. Quy mô dữ liệu thật: 59 dự án, 620 dòng Discipline Allocation (320 dòng đã có `actual_close_date`), 790 Task, 183 Opportunity, 207 biên bản nghiệm thu — ở cấp (Project, Discipline), ~620 dòng là dư so với quy tắc 10 ca dương/biến. `extract.py` đã có `load_from_erpnext_api()` để tải dữ liệu thật qua API (xem hướng dẫn cuối file `extract.py`); lưu ý bắt buộc: Discipline Allocation là child table nên phải gọi kèm `parent="Design Discipline Assignment"`, và `contract_value` phải cộng dồn từ các Sales Order đã submit, không đọc trực tiếp field trên Project.

### Bảng feature

**Đơn vị:** 1 dòng = 1 cặp (Project, Discipline). **As-of date:** `Discipline Allocation.start_date` (ngày kế hoạch bộ môn đó bắt đầu).

| Feature | Nguồn | Lớp |
|---|---|---|
| project_type, service_type | tabProject | F |
| contract_value | Sales Order (cộng dồn các Sales Order đã submit của project) | F |
| planned_duration_days | expected_end_date − expected_start_date (cấp dự án) | F |
| n_disciplines_known_at_snapshot | Discipline Allocation, đếm các bộ môn có `start_date ≤ as_of` (đã sửa, xem mục trên) | F |
| n_open_disciplines_at_snapshot, total_workload_pct | đếm/tỷ lệ bộ môn đang mở (`actual_close_date` rỗng hoặc > T) mà cùng một người đang phụ trách song song, tính tại as-of date T | F (có giới hạn — xem 2 mục giới hạn ở trên) |
| pct_staff_overloaded_at_snapshot | % nhân sự (đã hoạt động tính đến T) có số bộ môn đang mở vượt ngưỡng quá tải (tạm đặt = 2, cần thống nhất lại) | F (có giới hạn — xem 2 mục giới hạn ở trên) |
| pm_historic_late_rate, customer_historic_late_rate | các bản ghi đã đóng trước as-of, có smoothing (xem mục Historic rate ở trên) | F |
| n_open_overdue_tasks_at_snapshot | Discipline Allocation khác cùng dự án: `end_date < as_of` VÀ đang mở tại as_of (đã sửa lỗi rò rỉ, xem mục trên) | F |
| actual_close_date (Discipline Allocation) | Discipline Allocation (nhập tay bởi chủ trì khi đóng mốc) | L |
| percent_complete (giá trị cuối), status (giá trị cuối) | tabProject/tabTask | L |
| actual_end_date, actual_start_date, act_end_date | tabProject/tabTask | X (luôn rỗng do phụ thuộc Timesheet — không dùng được cho cả feature lẫn nhãn) |
| modified | mọi Doctype | X |

---

## Subtask 2.2 — Feature Dictionary: Bài toán Win Probability

**As-of date: ngày phát sinh Quotation đầu tiên gắn với Opportunity**

### Chọn lại as-of date, không chỉ xóa feature rỗng

`has_quotation` có variance ≈ 0 tại as-of date là `transaction_date` (ngày tạo Opportunity), vì báo giá hầu như luôn phát sinh sau đó. Nhưng đây không chỉ là lỗi của riêng feature đó — nếu tại as-of date gần như chưa có sự kiện nghiệp vụ nào xảy ra, thì mọi feature gắn với giai đoạn xử lý cơ hội (báo giá, số lần chỉnh sửa, chiết khấu, điểm chấm thầu) đều sẽ rỗng hoặc gần như hằng số, không riêng gì `has_quotation`. Cứ loại dần từng feature rỗng sẽ dẫn đến việc xóa hết nhóm feature quan trọng nhất của bài toán, chỉ còn lại vài thuộc tính tĩnh (lead_source, customer_segment...) — không đủ để dự đoán khả năng thắng một cách có ý nghĩa.

Gốc vấn đề là **as-of date chọn quá sớm so với nhịp độ nghiệp vụ thực tế** của quy trình bán hàng: Lead → Opportunity → (khảo sát, trao đổi kỹ thuật) → Quotation → chốt/thua. Ngày tạo Opportunity chỉ là điểm khởi đầu hồ sơ, chưa phải điểm có đủ thông tin để đánh giá khả năng thắng.

Cách chọn lại: dời as-of date sang **thời điểm phát sinh Quotation đầu tiên** (`Quotation.transaction_date` sớm nhất gắn với Opportunity đó), thay vì `Opportunity.transaction_date`. Lý do nghiệp vụ:
- Đây là điểm mà đội sales đã đầu tư đủ công sức để tin cơ hội này có khả năng thật (không phải cơ hội "chết" bị bỏ ngay từ đầu), nên các feature như has_quotation, n_quotation_revisions, discount_rate sẽ có giá trị thật, không còn là hằng số.
- Vẫn còn đủ thời gian để hành động (chưa chốt/thua), nên dự đoán tại mốc này vẫn có giá trị vận hành — sales có thể dùng điểm số để quyết định tiếp tục đầu tư nguồn lực hay không.

Rủi ro cần lưu ý khi đổi as-of date theo cách này: dời as-of date đến "thời điểm có Quotation đầu tiên" đồng nghĩa với việc bài toán bây giờ **chỉ áp dụng cho các Opportunity đã có ít nhất 1 Quotation** — những Opportunity bị loại/bỏ ngay từ giai đoạn đầu (chưa từng có báo giá) sẽ không nằm trong phạm vi dự đoán của mô hình này. Đây là một dạng chọn mẫu có chủ đích (selection) 
Báo cáo: mô hình này trả lời câu hỏi "trong số các cơ hội đã đi đến bước báo giá, khả năng thắng là bao nhiêu", chứ không phải "mọi cơ hội mới tạo có khả năng thắng bao nhiêu". Nếu ban điều hành cần dự đoán ngay từ lúc tạo cơ hội (as-of date = transaction_date), thì bắt buộc chấp nhận bỏ hẳn nhóm feature liên quan đến Quotation, chỉ dùng các thuộc tính tĩnh — đây là đánh đổi cần nêu rõ, không phải lỗi kỹ thuật.

### Bảng feature 

**As-of date:** ngày phát sinh Quotation đầu tiên gắn với Opportunity (`Quotation.transaction_date` sớm nhất).

| Feature | Nguồn | Lớp |
|---|---|---|
| lead_source, campaign | Opportunity/Lead | F |
| customer_segment, territory | tabCustomer | F |
| opportunity_type, service, opportunity_amount | tabOpportunity | F |
| days_lead_to_opp | Lead.creation → Opportunity.transaction_date | F |
| has_quotation, n_quotation_revisions, discount_rate | tabQuotation (tính đến as-of date mới) | F |
| tech_score, comm_score | custom field (bid scoring) | **X (tạm thời)** — xem ghi chú bên dưới |
| owner_historic_win_rate | các Opportunity khác đã đóng trước as-of | F |
| status (Converted/Lost) | tabOpportunity | L |
| order_lost_reason | tabOpportunity | X |
| probability (đánh giá thủ công của sales) | tabOpportunity | X |
| modified | tabOpportunity | X |

**Ghi chú về `tech_score`/`comm_score`:** hai field này có nguy cơ rò rỉ nặng nếu đây là điểm do bên mời thầu chấm **trong lúc xét thầu** — khi đó dùng làm feature gần như tương đương dùng chính nhãn (kết quả thắng/thua thường bám rất sát điểm xét thầu), khiến AUC cao một cách giả tạo, không phản ánh khả năng dự đoán thật. Đang chờ Đội kế hoạch xác nhận ai chấm và chấm vào lúc nào; trong lúc chờ, tạm để lớp `X` (loại khỏi cả feature lẫn cân nhắc dùng), chưa xếp vào `F`. Nếu xác nhận được điểm này được chấm **trước** as-of date và độc lập với quyết định thắng/thua cuối cùng (ví dụ chấm sơ bộ hồ sơ năng lực, không phải chấm thầu), có thể chuyển lại thành `F`.

Lưu ý: mọi Opportunity chưa từng có Quotation không tham gia vào tập huấn luyện của bài toán này (không phải right-censored, mà là ngoài phạm vi định nghĩa bài toán) — cần báo cáo riêng số lượng/tỷ lệ Opportunity thuộc nhóm này để người đọc hiểu rõ phạm vi áp dụng thực tế của mô hình.

---

## Subtask 2.3 — Metric Plan

Với bài toán Delay Risk, ưu tiên **Recall** hơn Precision: bỏ sót một dự án thực sự sẽ trễ (false negative) tốn kém hơn báo động nhầm (false positive), vì false negative nghĩa là không ai can thiệp cho đến khi dự án đã trễ thật. Báo cáo đầy đủ Precision, Recall, F1-score, Confusion Matrix, kèm ROC-AUC khi phù hợp. Sau khi áp dụng quy tắc tách right-censored ở Điểm sửa 4, cần đối chiếu lại các metric này có thay đổi nhiều so với cách loại toàn bộ bản ghi chưa hoàn thành hay không, như một phép kiểm tra độ nhạy (sensitivity check) của kết quả.

Với bài toán Win Probability, metric chủ đạo là **AUC** để đánh giá khả năng xếp hạng, kèm Precision/Recall/F1 ở ngưỡng được chọn. Vì mục đích chính là xếp hạng để ưu tiên nguồn lực sales (không phải chốt danh sách nhị phân thắng/thua), nên **Top-K Precision** (trong nhóm Top-K cơ hội điểm cao nhất, bao nhiêu % thực sự thắng) là chỉ số vận hành quan trọng hơn việc chọn cứng một ngưỡng Precision/Recall duy nhất — nếu Top-K Precision thấp, sales sẽ mất niềm tin vào hệ thống. Nên bổ sung thêm calibration curve và lift chart nếu có điều kiện.

Cả hai bài toán đều đánh giá bằng cách chia tập theo thời gian (dựa trên as-of date tương ứng của từng bài toán) chứ không chia ngẫu nhiên.
